from __future__ import annotations

"""Compiler-observed provenance for finite ReplayMark TargetModel semantics.

A provider-supplied fingerprint is useful metadata, but it is not a semantic
commitment: an adapter can forget to update it or can reuse the same label after
its behavior changes. ReplayMark therefore enumerates the finite two-phase target
semantics itself and computes a content-derived semantic digest.

The semantic digest covers positive-probability behavior only. Mapping insertion
order, decision-state enumeration order, and explicit zero-mass branches are
nonsemantic and therefore do not change it. Declared continuation *order* is
stored in the snapshot because production witness tie-breaking uses it, but the
semantic digest treats the continuation alphabet as a set of named inputs. The
snapshot fingerprint, unlike the semantic digest, binds that declared order and
the provider fingerprint as artifact metadata.
"""

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Mapping

from .contracts import ProjectedAction, TargetModel


_SCHEMA = "replaymark.target-semantics-snapshot.v1"
_DOMAIN_SCHEMA = "replaymark.target-semantics-domain.v1"
_CURRENT_SCHEMA = "replaymark.target-current-law.v1"
_ADVANCE_SCHEMA = "replaymark.target-advance-law.v1"
_ROOT_SCHEMA = "replaymark.target-semantic-root.v1"


class TargetProvenanceError(ValueError):
    """Base class for fail-closed target-provenance observation errors."""


class InvalidObservedTargetError(TargetProvenanceError):
    """Raised when the TargetModel boundary is malformed."""


class IncompleteObservedTargetError(TargetProvenanceError):
    """Raised when a declared part of the finite target has no semantics."""


class UnstableObservedTargetError(TargetProvenanceError):
    """Raised when repeated target observation yields different semantics."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidObservedTargetError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise InvalidObservedTargetError(
            f"{name} must not contain leading/trailing whitespace"
        )
    return value


def _mass(raw: object, *, where: str) -> Fraction:
    if isinstance(raw, bool) or not isinstance(raw, (int, Fraction)):
        raise InvalidObservedTargetError(
            f"probability at {where} must be an exact Fraction/int, got {type(raw).__name__}"
        )
    value = Fraction(raw)
    if value < 0:
        raise InvalidObservedTargetError(f"negative probability at {where}: {value}")
    return value


def _fraction_record(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


CurrentBranch = tuple[ProjectedAction, str, Fraction]
AdvanceBranch = tuple[str, Fraction]
CurrentLawRow = tuple[str, tuple[CurrentBranch, ...]]
AdvanceLawRow = tuple[str, str, tuple[AdvanceBranch, ...]]


def _current_branch_key(branch: CurrentBranch) -> tuple[object, ...]:
    action, post_state, mass = branch
    return action.canonical_key(), post_state, mass.numerator, mass.denominator


def _advance_branch_key(branch: AdvanceBranch) -> tuple[object, ...]:
    next_state, mass = branch
    return next_state, mass.numerator, mass.denominator


def _read_current_law(target: TargetModel, state: str) -> tuple[CurrentBranch, ...]:
    try:
        distribution = target.current_distribution(state)
    except KeyError as exc:
        raise IncompleteObservedTargetError(
            f"missing current semantics for decision state {state!r}"
        ) from exc
    if not isinstance(distribution, Mapping):
        raise TypeError("TargetModel.current_distribution must return a Mapping")

    total = Fraction(0, 1)
    positive: list[CurrentBranch] = []
    for raw_key, raw_mass in distribution.items():
        mass = _mass(raw_mass, where=f"current_distribution({state!r})")
        total += mass
        if mass == 0:
            continue
        if not isinstance(raw_key, tuple) or len(raw_key) != 2:
            raise InvalidObservedTargetError(
                "positive current_distribution keys must be (ProjectedAction, post_state)"
            )
        action, raw_post_state = raw_key
        if not isinstance(action, ProjectedAction):
            raise InvalidObservedTargetError(
                f"positive current action at {state!r} is not ProjectedAction"
            )
        post_state = _token("post-decision state", raw_post_state)
        positive.append((action, post_state, mass))

    if total != 1:
        raise InvalidObservedTargetError(
            f"probability mass at current_distribution({state!r}) is {total}, expected 1"
        )
    if not positive:
        raise IncompleteObservedTargetError(
            f"current_distribution({state!r}) has no positive semantic branch"
        )
    positive.sort(key=_current_branch_key)
    return tuple(positive)


def _read_advance_law(
    target: TargetModel,
    post_state: str,
    continuation: str,
    admitted_states: set[str],
) -> tuple[AdvanceBranch, ...]:
    try:
        distribution = target.advance_distribution(post_state, continuation)
    except KeyError as exc:
        raise IncompleteObservedTargetError(
            "missing advance semantics for "
            f"post_state={post_state!r}, continuation={continuation!r}"
        ) from exc
    if not isinstance(distribution, Mapping):
        raise TypeError("TargetModel.advance_distribution must return a Mapping")

    total = Fraction(0, 1)
    positive: list[AdvanceBranch] = []
    for raw_next_state, raw_mass in distribution.items():
        mass = _mass(
            raw_mass,
            where=f"advance_distribution({post_state!r},{continuation!r})",
        )
        total += mass
        if mass == 0:
            continue
        next_state = _token("next decision state", raw_next_state)
        if next_state not in admitted_states:
            raise InvalidObservedTargetError(
                "positive advance branch reaches undeclared decision state: "
                f"{next_state!r}"
            )
        positive.append((next_state, mass))

    if total != 1:
        raise InvalidObservedTargetError(
            "probability mass at "
            f"advance_distribution({post_state!r},{continuation!r}) is {total}, expected 1"
        )
    if not positive:
        raise IncompleteObservedTargetError(
            "advance_distribution has no positive semantic branch: "
            f"post_state={post_state!r}, continuation={continuation!r}"
        )
    positive.sort(key=_advance_branch_key)
    return tuple(positive)


def _domain_record(
    states: tuple[str, ...],
    continuation_symbols: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema": _DOMAIN_SCHEMA,
        "decision_states": list(states),
        "continuation_symbols": list(sorted(continuation_symbols)),
    }


def _current_record(rows: tuple[CurrentLawRow, ...]) -> dict[str, object]:
    return {
        "schema": _CURRENT_SCHEMA,
        "current_laws": [
            {
                "decision_state": state,
                "branches": [
                    {
                        "action": action.as_dict(),
                        "post_state": post_state,
                        "mass": _fraction_record(mass),
                    }
                    for action, post_state, mass in branches
                ],
            }
            for state, branches in rows
        ],
    }


def _advance_record(rows: tuple[AdvanceLawRow, ...]) -> dict[str, object]:
    return {
        "schema": _ADVANCE_SCHEMA,
        "advance_laws": [
            {
                "post_state": post_state,
                "continuation": continuation,
                "branches": [
                    {
                        "next_decision_state": next_state,
                        "mass": _fraction_record(mass),
                    }
                    for next_state, mass in branches
                ],
            }
            for post_state, continuation, branches in rows
        ],
    }


def _component_digests(
    states: tuple[str, ...],
    continuation_symbols: tuple[str, ...],
    current_rows: tuple[CurrentLawRow, ...],
    advance_rows: tuple[AdvanceLawRow, ...],
) -> tuple[str, str, str, str]:
    domain_digest = _sha256(_domain_record(states, continuation_symbols))
    current_digest = _sha256(_current_record(current_rows))
    advance_digest = _sha256(_advance_record(advance_rows))
    semantic_digest = _sha256(
        {
            "schema": _ROOT_SCHEMA,
            "domain_digest": domain_digest,
            "current_semantics_digest": current_digest,
            "advance_semantics_digest": advance_digest,
        }
    )
    return domain_digest, current_digest, advance_digest, semantic_digest


@dataclass(frozen=True)
class ObservedTargetSemantics:
    """Content-addressed snapshot of the finite two-phase target semantics."""

    schema_version: str
    provider_fingerprint: str
    decision_states: tuple[str, ...]
    declared_continuation_order: tuple[str, ...]
    current_laws: tuple[CurrentLawRow, ...]
    advance_laws: tuple[AdvanceLawRow, ...]
    domain_digest: str
    current_semantics_digest: str
    advance_semantics_digest: str
    semantic_digest: str

    def __post_init__(self) -> None:
        _token("provider fingerprint", self.provider_fingerprint)
        if self.schema_version != _SCHEMA:
            raise ValueError(f"unexpected target snapshot schema: {self.schema_version!r}")
        if not self.decision_states:
            raise ValueError("observed target semantics requires at least one decision state")
        if tuple(sorted(self.decision_states)) != self.decision_states:
            raise ValueError("decision_states must be canonical and sorted")
        if len(set(self.decision_states)) != len(self.decision_states):
            raise ValueError("decision_states contains duplicates")
        if len(set(self.declared_continuation_order)) != len(self.declared_continuation_order):
            raise ValueError("declared continuation order contains duplicates")

        if tuple(state for state, _ in self.current_laws) != self.decision_states:
            raise ValueError("current_laws must cover every decision state exactly once")
        admitted = set(self.decision_states)
        positive_post_states: set[str] = set()
        for state, branches in self.current_laws:
            if not branches:
                raise ValueError(f"current law for {state!r} is empty")
            total = sum((mass for _, _, mass in branches), Fraction(0, 1))
            if total != 1 or any(mass <= 0 for _, _, mass in branches):
                raise ValueError(f"current law for {state!r} is not a canonical positive law")
            if tuple(sorted(branches, key=_current_branch_key)) != branches:
                raise ValueError(f"current law for {state!r} is not canonically sorted")
            positive_post_states.update(post_state for _, post_state, _ in branches)

        expected_advance_keys = tuple(
            sorted(
                (post_state, continuation)
                for post_state in positive_post_states
                for continuation in self.declared_continuation_order
            )
        )
        actual_advance_keys = tuple(
            (post_state, continuation)
            for post_state, continuation, _ in self.advance_laws
        )
        if actual_advance_keys != expected_advance_keys:
            raise ValueError(
                "advance_laws must cover every positive post-state x continuation exactly once"
            )
        for post_state, continuation, branches in self.advance_laws:
            if not branches:
                raise ValueError(
                    f"advance law for ({post_state!r},{continuation!r}) is empty"
                )
            total = sum((mass for _, mass in branches), Fraction(0, 1))
            if total != 1 or any(mass <= 0 for _, mass in branches):
                raise ValueError("advance law is not a canonical positive probability law")
            if tuple(sorted(branches, key=_advance_branch_key)) != branches:
                raise ValueError("advance law branches are not canonically sorted")
            if any(next_state not in admitted for next_state, _ in branches):
                raise ValueError("advance law reaches an undeclared decision state")

        expected = _component_digests(
            self.decision_states,
            self.declared_continuation_order,
            self.current_laws,
            self.advance_laws,
        )
        actual = (
            self.domain_digest,
            self.current_semantics_digest,
            self.advance_semantics_digest,
            self.semantic_digest,
        )
        if actual != expected:
            raise ValueError("target semantic digest does not match the stored observed laws")

    @property
    def continuation_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.declared_continuation_order))

    @property
    def positive_post_states(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    post_state
                    for _, branches in self.current_laws
                    for _, post_state, _ in branches
                }
            )
        )

    def current_law(self, decision_state: str) -> tuple[CurrentBranch, ...]:
        state = _token("decision state", decision_state)
        try:
            return dict(self.current_laws)[state]
        except KeyError as exc:
            raise KeyError(f"unknown decision state: {state!r}") from exc

    def advance_law(
        self, post_state: str, continuation: str
    ) -> tuple[AdvanceBranch, ...]:
        post_state = _token("post-decision state", post_state)
        continuation = _token("continuation", continuation)
        by_key = {
            (row_post, row_cont): branches
            for row_post, row_cont, branches in self.advance_laws
        }
        try:
            return by_key[(post_state, continuation)]
        except KeyError as exc:
            raise KeyError(
                f"unknown observed advance law: ({post_state!r},{continuation!r})"
            ) from exc

    def semantic_record(self) -> dict[str, object]:
        return {
            "schema": _ROOT_SCHEMA,
            "domain": _domain_record(self.decision_states, self.declared_continuation_order),
            "current": _current_record(self.current_laws),
            "advance": _advance_record(self.advance_laws),
            "component_digests": {
                "domain": self.domain_digest,
                "current": self.current_semantics_digest,
                "advance": self.advance_semantics_digest,
                "root": self.semantic_digest,
            },
        }

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "provider_fingerprint": self.provider_fingerprint,
            "declared_continuation_order": list(self.declared_continuation_order),
            "semantic_snapshot": self.semantic_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        """Artifact identity; unlike semantic_digest, includes provider/order metadata."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _read_domain(target: TargetModel) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    provider = _token("provider fingerprint", target.fingerprint)
    raw_states = target.decision_states
    if not isinstance(raw_states, tuple):
        raise TypeError("TargetModel.decision_states must be tuple[str, ...]")
    states = tuple(sorted(_token("decision state id", state) for state in raw_states))
    if not states:
        raise InvalidObservedTargetError("TargetModel.decision_states must not be empty")
    if len(set(states)) != len(states):
        raise InvalidObservedTargetError("TargetModel.decision_states contains duplicates")

    raw_continuations = target.continuation_alphabet
    if not isinstance(raw_continuations, tuple):
        raise TypeError("TargetModel.continuation_alphabet must be tuple[str, ...]")
    continuations = tuple(
        _token("continuation symbol", continuation)
        for continuation in raw_continuations
    )
    if len(set(continuations)) != len(continuations):
        raise InvalidObservedTargetError(
            "TargetModel.continuation_alphabet contains duplicates"
        )
    return provider, states, continuations


def _observe_pass(
    target: TargetModel,
    states_in_query_order: tuple[str, ...],
    continuations_in_query_order: tuple[str, ...],
) -> tuple[tuple[CurrentLawRow, ...], tuple[AdvanceLawRow, ...]]:
    current: dict[str, tuple[CurrentBranch, ...]] = {}
    for state in states_in_query_order:
        current[state] = _read_current_law(target, state)

    post_states = tuple(
        sorted(
            {
                post_state
                for branches in current.values()
                for _, post_state, _ in branches
            }
        )
    )
    admitted = set(states_in_query_order)
    advance: dict[tuple[str, str], tuple[AdvanceBranch, ...]] = {}
    for post_state in reversed(post_states):
        for continuation in continuations_in_query_order:
            advance[(post_state, continuation)] = _read_advance_law(
                target, post_state, continuation, admitted
            )

    current_rows = tuple((state, current[state]) for state in sorted(current))
    advance_rows = tuple(
        (post_state, continuation, advance[(post_state, continuation)])
        for post_state, continuation in sorted(advance)
    )
    return current_rows, advance_rows


def observe_target_semantics(target: TargetModel) -> ObservedTargetSemantics:
    """Enumerate, seal, and stability-check the finite TargetModel semantics.

    The adapter is queried twice using opposite decision-state/continuation
    orders. The two canonical positive-probability laws must be identical. This
    makes the semantic digest a compiler observation rather than a provider
    assertion and rejects stateful/order-dependent model adapters before q
    compilation can certify them.
    """

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")

    provider1, states1, continuations1 = _read_domain(target)
    first_current, first_advance = _observe_pass(target, states1, continuations1)

    provider2, states2, continuations2 = _read_domain(target)
    if provider1 != provider2:
        raise UnstableObservedTargetError("provider fingerprint changed during observation")
    if states1 != states2:
        raise UnstableObservedTargetError("decision-state domain changed during observation")
    if continuations1 != continuations2:
        raise UnstableObservedTargetError(
            "declared continuation order changed during observation"
        )

    second_current, second_advance = _observe_pass(
        target,
        tuple(reversed(states2)),
        tuple(reversed(continuations2)),
    )
    if first_current != second_current:
        raise UnstableObservedTargetError(
            "current target semantics changed across repeated observation passes"
        )
    if first_advance != second_advance:
        raise UnstableObservedTargetError(
            "advance target semantics changed across repeated observation passes"
        )

    digests = _component_digests(
        states1,
        continuations1,
        first_current,
        first_advance,
    )
    return ObservedTargetSemantics(
        schema_version=_SCHEMA,
        provider_fingerprint=provider1,
        decision_states=states1,
        declared_continuation_order=continuations1,
        current_laws=first_current,
        advance_laws=first_advance,
        domain_digest=digests[0],
        current_semantics_digest=digests[1],
        advance_semantics_digest=digests[2],
        semantic_digest=digests[3],
    )


__all__ = (
    "AdvanceBranch",
    "AdvanceLawRow",
    "CurrentBranch",
    "CurrentLawRow",
    "IncompleteObservedTargetError",
    "InvalidObservedTargetError",
    "ObservedTargetSemantics",
    "TargetProvenanceError",
    "UnstableObservedTargetError",
    "observe_target_semantics",
)
