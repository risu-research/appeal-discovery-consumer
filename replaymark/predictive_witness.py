from __future__ import annotations

"""Production shortest predictive-continuation witnesses over bounded q_{C,H}.

A predictive witness answers exactly one question:

    why are two target decision worlds not equivalent under q_{C,H}?

It is a shortest admitted continuation word whose claim-projected output traces
separate the two worlds. This object is intentionally independent of retained
evidence, recorded historical actions, support adjudication, and R*.

R* counterexamples are different objects: a raw compatible world excluding one
recorded action. They are not continuation words and are not computed here.
"""

from dataclasses import dataclass
import hashlib
import json

from .contracts import ProjectedAction
from .q_compiler import BoundedQuotient


_SCHEMA = "replaymark.predictive-continuation-witness.v1"
_INDEX_SCHEMA = "replaymark.predictive-continuation-witness-index.v1"


class PredictiveWitnessError(ValueError):
    """Base class for fail-closed production witness synthesis errors."""


class MalformedQuotientWitnessError(PredictiveWitnessError):
    """Raised when the bounded-q artifact cannot justify its own separation."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _pair(left: str, right: str) -> tuple[str, str]:
    left = str(left)
    right = str(right)
    if left == right:
        raise ValueError("predictive witness requires two distinct decision worlds")
    return (left, right) if left < right else (right, left)


def _action_record(action: ProjectedAction) -> dict[str, object]:
    return action.as_dict()


@dataclass(frozen=True)
class PredictiveContinuationWitness:
    """Canonical shortest q-separating continuation certificate.

    `continuation_word` has minimum length among all admitted words that make the
    two claim-projected output traces differ. Length zero means the current
    projected actions already differ. `first_separation_depth` equals that
    minimum length.
    """

    schema_version: str
    quotient_fingerprint: str
    claim_fingerprint: str
    compiled_depth: int
    left_state: str
    right_state: str
    first_separation_depth: int
    continuation_word: tuple[str, ...]
    left_trace: tuple[ProjectedAction, ...]
    right_trace: tuple[ProjectedAction, ...]

    def __post_init__(self) -> None:
        if self.left_state >= self.right_state:
            raise ValueError("witness state pair must be canonical left < right")
        if self.compiled_depth < 0:
            raise ValueError("compiled_depth must be >= 0")
        if self.first_separation_depth < 0:
            raise ValueError("first_separation_depth must be >= 0")
        if self.first_separation_depth != len(self.continuation_word):
            raise ValueError(
                "first_separation_depth must equal shortest continuation length"
            )
        if self.first_separation_depth > self.compiled_depth:
            raise ValueError("witness exceeds the compiled q depth")
        if len(self.left_trace) != len(self.continuation_word) + 1:
            raise ValueError("left trace length must equal |word| + 1")
        if len(self.right_trace) != len(self.continuation_word) + 1:
            raise ValueError("right trace length must equal |word| + 1")
        if self.left_trace == self.right_trace:
            raise ValueError("predictive witness traces must actually differ")
        if not self.quotient_fingerprint or not self.claim_fingerprint:
            raise ValueError("witness provenance fingerprints must be nonempty")
        if any(not isinstance(item, str) or not item for item in self.continuation_word):
            raise ValueError("continuation witness contains an invalid symbol")
        if any(not isinstance(action, ProjectedAction) for action in self.left_trace):
            raise TypeError("left trace contains a non-ProjectedAction")
        if any(not isinstance(action, ProjectedAction) for action in self.right_trace):
            raise TypeError("right trace contains a non-ProjectedAction")

    @property
    def witness_length(self) -> int:
        return len(self.continuation_word)

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "quotient_fingerprint": self.quotient_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "compiled_depth": self.compiled_depth,
            "left_state": self.left_state,
            "right_state": self.right_state,
            "first_separation_depth": self.first_separation_depth,
            "continuation_word": list(self.continuation_word),
            "left_trace": [_action_record(action) for action in self.left_trace],
            "right_trace": [_action_record(action) for action in self.right_trace],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class PredictiveWitnessIndex:
    """All shortest pairwise q-separation witnesses through one compiled depth."""

    schema_version: str
    quotient_fingerprint: str
    claim_fingerprint: str
    depth: int
    decision_states: tuple[str, ...]
    continuation_alphabet: tuple[str, ...]
    witnesses: tuple[PredictiveContinuationWitness, ...]

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("witness-index depth must be >= 0")
        if tuple(sorted(self.decision_states)) != self.decision_states:
            raise ValueError("decision_states must be canonical and sorted")
        if len(set(self.decision_states)) != len(self.decision_states):
            raise ValueError("decision_states contains duplicates")
        if len(set(self.continuation_alphabet)) != len(self.continuation_alphabet):
            raise ValueError("continuation_alphabet contains duplicates")

        keys = []
        for witness in self.witnesses:
            if not isinstance(witness, PredictiveContinuationWitness):
                raise TypeError("witness index contains a foreign object")
            if witness.quotient_fingerprint != self.quotient_fingerprint:
                raise ValueError("witness is bound to a different quotient")
            if witness.claim_fingerprint != self.claim_fingerprint:
                raise ValueError("witness is bound to a different claim")
            if witness.compiled_depth != self.depth:
                raise ValueError("witness depth differs from index depth")
            if witness.left_state not in self.decision_states or witness.right_state not in self.decision_states:
                raise ValueError("witness names a world outside the index domain")
            keys.append((witness.left_state, witness.right_state))
        if tuple(sorted(keys)) != tuple(keys):
            raise ValueError("witness rows must be canonically sorted by state pair")
        if len(set(keys)) != len(keys):
            raise ValueError("witness index contains duplicate state pairs")

    @property
    def distinguishable_pair_count(self) -> int:
        return len(self.witnesses)

    def witness(self, left: str, right: str) -> PredictiveContinuationWitness | None:
        left = str(left)
        right = str(right)
        admitted = set(self.decision_states)
        unknown = tuple(sorted({left, right} - admitted))
        if unknown:
            raise KeyError(f"unknown target decision world(s): {unknown!r}")
        if left == right:
            return None
        key = _pair(left, right)
        for witness in self.witnesses:
            if (witness.left_state, witness.right_state) == key:
                return witness
        return None

    def equivalent(self, left: str, right: str) -> bool:
        return self.witness(left, right) is None

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "quotient_fingerprint": self.quotient_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "depth": self.depth,
            "decision_states": list(self.decision_states),
            "continuation_alphabet": list(self.continuation_alphabet),
            "witnesses": [witness.canonical_record() for witness in self.witnesses],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _validate_refinement(quotient: BoundedQuotient, depth: int) -> None:
    states = quotient.decision_states
    if len(quotient.layers) != quotient.horizon + 1:
        raise MalformedQuotientWitnessError("bounded quotient has the wrong number of layers")
    for d in range(1, depth + 1):
        previous = quotient.layer(d - 1)
        current = quotient.layer(d)
        for i, left in enumerate(states):
            for right in states[i + 1 :]:
                if current.equivalent(left, right) and not previous.equivalent(left, right):
                    raise MalformedQuotientWitnessError(
                        "q layers are not monotone refinements: "
                        f"pair=({left!r},{right!r}), depth={d}"
                    )


def _artifact_maps(quotient: BoundedQuotient):
    actions = dict(quotient.current_projected_actions)
    if set(actions) != set(quotient.decision_states):
        raise MalformedQuotientWitnessError(
            "current_projected_actions does not cover the q decision-state domain"
        )

    successors: dict[str, dict[str, str]] = {}
    for state, rows in quotient.deterministic_successors:
        if state in successors:
            raise MalformedQuotientWitnessError(
                f"duplicate deterministic-successor row for {state!r}"
            )
        row = dict(rows)
        if len(row) != len(rows):
            raise MalformedQuotientWitnessError(
                f"duplicate continuation in deterministic-successor row {state!r}"
            )
        successors[state] = row

    if set(successors) != set(quotient.decision_states):
        raise MalformedQuotientWitnessError(
            "deterministic_successors does not cover the q decision-state domain"
        )
    if quotient.horizon > 0:
        expected = set(quotient.continuation_alphabet)
        admitted = set(quotient.decision_states)
        for state, row in successors.items():
            if set(row) != expected:
                raise MalformedQuotientWitnessError(
                    f"successor row {state!r} does not cover the continuation alphabet"
                )
            if not set(row.values()).issubset(admitted):
                raise MalformedQuotientWitnessError(
                    f"successor row {state!r} reaches an undeclared decision world"
                )
    return actions, successors


def _trace(
    start: str,
    word: tuple[str, ...],
    actions: dict[str, ProjectedAction],
    successors: dict[str, dict[str, str]],
) -> tuple[ProjectedAction, ...]:
    state = start
    out = [actions[state]]
    for continuation in word:
        try:
            state = successors[state][continuation]
        except KeyError as exc:
            raise MalformedQuotientWitnessError(
                f"cannot replay witness continuation {continuation!r} from {state!r}"
            ) from exc
        out.append(actions[state])
    return tuple(out)


def compile_predictive_witnesses(
    quotient: BoundedQuotient,
    *,
    depth: int | None = None,
) -> PredictiveWitnessIndex:
    """Derive canonical shortest q-separation witnesses from compiled refinement.

    The algorithm never calls the TargetModel. It consumes the sealed q artifact
    and uses its already-computed layers plus deterministic successor table.

    For a pair that first separates at depth d:

    - d=0: the empty continuation word is the shortest witness;
    - d>0: choose an admitted continuation whose successor pair is separated by
      q_{C,d-1}, then prepend that continuation to the already-shortest successor
      witness. Among equal-length witnesses, use the declared continuation order
      as the canonical tie break.

    Because q_{C,d-1} equality means equality for *all* words of length <= d-1,
    first separation at depth d proves that the returned word length d is globally
    minimal, not merely locally greedy.
    """

    if not isinstance(quotient, BoundedQuotient):
        raise TypeError("quotient must be a BoundedQuotient")
    if isinstance(depth, bool):
        raise TypeError("predictive witness depth must be an integer or None")
    depth = quotient.horizon if depth is None else int(depth)
    if depth < 0 or depth > quotient.horizon:
        raise IndexError(
            f"predictive witness depth {depth} outside compiled horizon "
            f"[0,{quotient.horizon}]"
        )

    _validate_refinement(quotient, depth)
    actions, successors = _artifact_maps(quotient)
    states = quotient.decision_states
    continuations = quotient.continuation_alphabet
    rank = {continuation: index for index, continuation in enumerate(continuations)}

    best: dict[tuple[str, str], tuple[str, ...]] = {}
    separation_depth: dict[tuple[str, str], int] = {}

    # q_{C,0}: current projected output disagreement; no future input is needed.
    for i, left in enumerate(states):
        for right in states[i + 1 :]:
            key = (left, right)
            if actions[left] != actions[right]:
                if quotient.layer(0).equivalent(left, right):
                    raise MalformedQuotientWitnessError(
                        "q0 merges worlds with different current projected actions"
                    )
                best[key] = ()
                separation_depth[key] = 0
            elif not quotient.layer(0).equivalent(left, right):
                raise MalformedQuotientWitnessError(
                    "q0 separates worlds with equal current projected actions"
                )

    def word_rank(word: tuple[str, ...]) -> tuple[int, tuple[int, ...]]:
        try:
            return len(word), tuple(rank[item] for item in word)
        except KeyError as exc:
            raise MalformedQuotientWitnessError(
                f"witness uses continuation outside compiled alphabet: {exc.args[0]!r}"
            ) from exc

    # Each newly split pair receives a backpointer through a pair already split
    # in an earlier layer. Reconstructing those backpointers yields the witness.
    for d in range(1, depth + 1):
        previous = quotient.layer(d - 1)
        current = quotient.layer(d)
        for i, left in enumerate(states):
            for right in states[i + 1 :]:
                key = (left, right)
                if key in best or current.equivalent(left, right):
                    continue
                if not previous.equivalent(left, right):
                    raise MalformedQuotientWitnessError(
                        "pair was already q-separated but has no earlier witness: "
                        f"{key!r} at depth {d}"
                    )

                candidates: list[tuple[str, ...]] = []
                for continuation in continuations:
                    left_next = successors[left][continuation]
                    right_next = successors[right][continuation]
                    if left_next == right_next:
                        continue
                    if previous.equivalent(left_next, right_next):
                        continue
                    successor_pair = _pair(left_next, right_next)
                    suffix = best.get(successor_pair)
                    if suffix is None:
                        raise MalformedQuotientWitnessError(
                            "refinement splitter lacks an earlier successor witness: "
                            f"pair={key!r}, continuation={continuation!r}, "
                            f"successors={successor_pair!r}, depth={d}"
                        )
                    candidates.append((continuation,) + suffix)

                if not candidates:
                    raise MalformedQuotientWitnessError(
                        "q layer separates a pair without any justified splitter: "
                        f"pair={key!r}, depth={d}"
                    )
                word = min(candidates, key=word_rank)
                if len(word) != d:
                    raise MalformedQuotientWitnessError(
                        "first q-separation depth disagrees with derived shortest word: "
                        f"pair={key!r}, depth={d}, word={word!r}"
                    )
                best[key] = word
                separation_depth[key] = d

    rows: list[PredictiveContinuationWitness] = []
    for key in sorted(best):
        left, right = key
        word = best[key]
        left_trace = _trace(left, word, actions, successors)
        right_trace = _trace(right, word, actions, successors)
        if left_trace == right_trace:
            raise MalformedQuotientWitnessError(
                f"derived continuation does not distinguish pair {key!r}: {word!r}"
            )
        rows.append(
            PredictiveContinuationWitness(
                schema_version=_SCHEMA,
                quotient_fingerprint=quotient.fingerprint(),
                claim_fingerprint=quotient.claim.fingerprint(),
                compiled_depth=depth,
                left_state=left,
                right_state=right,
                first_separation_depth=separation_depth[key],
                continuation_word=word,
                left_trace=left_trace,
                right_trace=right_trace,
            )
        )

    # Every pair is represented iff q_{C,depth} separates it.
    represented = {(row.left_state, row.right_state) for row in rows}
    final_layer = quotient.layer(depth)
    for i, left in enumerate(states):
        for right in states[i + 1 :]:
            expected = not final_layer.equivalent(left, right)
            if ((left, right) in represented) != expected:
                raise MalformedQuotientWitnessError(
                    "witness index does not match the selected q partition: "
                    f"pair=({left!r},{right!r}), depth={depth}"
                )

    return PredictiveWitnessIndex(
        schema_version=_INDEX_SCHEMA,
        quotient_fingerprint=quotient.fingerprint(),
        claim_fingerprint=quotient.claim.fingerprint(),
        depth=depth,
        decision_states=states,
        continuation_alphabet=continuations,
        witnesses=tuple(rows),
    )


__all__ = (
    "MalformedQuotientWitnessError",
    "PredictiveContinuationWitness",
    "PredictiveWitnessError",
    "PredictiveWitnessIndex",
    "compile_predictive_witnesses",
)
