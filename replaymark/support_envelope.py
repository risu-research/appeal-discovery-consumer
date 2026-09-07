from __future__ import annotations

"""Deterministic support-envelope compiler over a frozen q evidence image.

This module implements exactly the next Replay-Sufficiency Factorization arrow:

    q_{C,H}[Omega(e)] -> S_C^-(e), S_C^+(e)

It does not classify recorded actions, return three-valued verdicts, choose
regeneration, or implement maximal reuse. Those remain separate stages.
"""

from dataclasses import dataclass
import hashlib
import json

from .contracts import ProjectedAction
from .evidence_image import QEvidenceImage
from .q_compiler import BoundedQuotient


_SCHEMA = "replaymark.support-envelope.deterministic.v1"


class SupportEnvelopeError(ValueError):
    """Base class for fail-closed support-envelope compilation errors."""


class ArtifactMismatchError(SupportEnvelopeError):
    """Raised when q/evidence artifacts do not belong to the same semantic object."""


class InconsistentQuotientSupportError(SupportEnvelopeError):
    """Raised when a q block violates current-support constancy."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _action_key(action: ProjectedAction) -> bytes:
    return _canonical_json_bytes(action.as_dict())


def _sorted_actions(actions) -> tuple[ProjectedAction, ...]:
    unique: dict[bytes, ProjectedAction] = {}
    for action in actions:
        if not isinstance(action, ProjectedAction):
            raise TypeError("support elements must be ProjectedAction")
        unique[_action_key(action)] = action
    return tuple(unique[key] for key in sorted(unique))


@dataclass(frozen=True)
class BlockSupport:
    """Projected current support attached to one q block.

    Deterministic q compiler v1 makes this a singleton, but the explicit tuple
    keeps the artifact semantically honest and leaves no room for block-id-only
    reasoning in later stages.
    """

    q_block: str
    support: tuple[ProjectedAction, ...]

    def canonical_record(self) -> dict[str, object]:
        return {
            "q_block": self.q_block,
            "support": [action.as_dict() for action in self.support],
        }


@dataclass(frozen=True)
class ObservationSupportEnvelope:
    """Exact guaranteed/possible projected support under one evidence token."""

    token: str
    q_blocks: tuple[str, ...]
    guaranteed_support: tuple[ProjectedAction, ...]
    possible_support: tuple[ProjectedAction, ...]

    def canonical_record(self) -> dict[str, object]:
        return {
            "token": self.token,
            "q_blocks": list(self.q_blocks),
            "guaranteed_support": [
                action.as_dict() for action in self.guaranteed_support
            ],
            "possible_support": [
                action.as_dict() for action in self.possible_support
            ],
        }


@dataclass(frozen=True)
class SupportEnvelope:
    """Auditable S^- / S^+ artifact for one bounded q evidence image."""

    schema_version: str
    quotient_fingerprint: str
    claim_fingerprint: str
    evidence_image_fingerprint: str
    evidence_fingerprint: str
    depth: int
    block_supports: tuple[BlockSupport, ...]
    observations: tuple[ObservationSupportEnvelope, ...]

    def observation(self, token: str) -> ObservationSupportEnvelope:
        token = str(token)
        for row in self.observations:
            if row.token == token:
                return row
        raise KeyError(f"unknown evidence observation: {token!r}")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "quotient_fingerprint": self.quotient_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "evidence_image_fingerprint": self.evidence_image_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "depth": self.depth,
            "block_supports": [row.canonical_record() for row in self.block_supports],
            "observations": [row.canonical_record() for row in self.observations],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _derive_block_supports(
    quotient: BoundedQuotient,
    depth: int,
) -> tuple[BlockSupport, ...]:
    """Derive support per q block and verify the quotient-preservation lemma.

    Because every bounded layer refines q_{C,0}, all members of a valid q block
    must have identical current claim-projected output. For deterministic v1,
    each raw world therefore has singleton support and each q block must inherit
    exactly one singleton support. We check this invariant rather than assume it.
    """

    current_by_state = dict(quotient.current_projected_actions)
    if set(current_by_state) != set(quotient.decision_states):
        raise InconsistentQuotientSupportError(
            "quotient current-action table does not cover exactly its decision states"
        )

    rows: list[BlockSupport] = []
    for q_block, members in quotient.layer(depth).blocks:
        actions = _sorted_actions(current_by_state[state] for state in members)
        if len(actions) != 1:
            raise InconsistentQuotientSupportError(
                "q block does not preserve deterministic current projected support: "
                f"block={q_block!r}, members={members!r}, actions={actions!r}"
            )
        rows.append(BlockSupport(q_block=q_block, support=actions))
    rows.sort(key=lambda row: row.q_block)
    return tuple(rows)


def compile_support_envelope(
    quotient: BoundedQuotient,
    evidence_image: QEvidenceImage,
) -> SupportEnvelope:
    """Compile exact deterministic S_C^-(e) and S_C^+(e).

    Production consumes only previously sealed compiler artifacts. It does not
    query the target model again. This makes the support stage reproducible from
    the same frozen semantic inputs that produced q_{C,H} and its evidence image.
    """

    if not isinstance(quotient, BoundedQuotient):
        raise TypeError("quotient must be a BoundedQuotient")
    if not isinstance(evidence_image, QEvidenceImage):
        raise TypeError("evidence_image must be a QEvidenceImage")

    quotient_fp = quotient.fingerprint()
    claim_fp = quotient.claim.fingerprint()
    if evidence_image.quotient_fingerprint != quotient_fp:
        raise ArtifactMismatchError(
            "evidence image was not compiled from the supplied quotient"
        )
    if evidence_image.claim_fingerprint != claim_fp:
        raise ArtifactMismatchError(
            "evidence image claim fingerprint does not match quotient claim"
        )
    if evidence_image.depth < 0 or evidence_image.depth > quotient.horizon:
        raise ArtifactMismatchError(
            "evidence image references a q depth outside the supplied quotient"
        )

    block_supports = _derive_block_supports(quotient, evidence_image.depth)
    support_by_block = {row.q_block: set(row.support) for row in block_supports}
    declared_blocks = set(support_by_block)

    observations: list[ObservationSupportEnvelope] = []
    for image_row in evidence_image.observations:
        q_blocks = tuple(image_row.q_blocks)
        if not q_blocks:
            raise SupportEnvelopeError(
                f"evidence token {image_row.token!r} has empty q image"
            )
        unknown = tuple(sorted(set(q_blocks) - declared_blocks))
        if unknown:
            raise ArtifactMismatchError(
                f"evidence token {image_row.token!r} references unknown q blocks: "
                f"{unknown!r}"
            )

        supports = [support_by_block[q_block] for q_block in q_blocks]
        guaranteed = set(supports[0])
        possible: set[ProjectedAction] = set()
        for support in supports:
            guaranteed.intersection_update(support)
            possible.update(support)

        if not possible:
            raise SupportEnvelopeError(
                f"evidence token {image_row.token!r} produced empty possible support"
            )
        if not guaranteed.issubset(possible):
            raise AssertionError("guaranteed support must be a subset of possible support")

        observations.append(
            ObservationSupportEnvelope(
                token=image_row.token,
                q_blocks=q_blocks,
                guaranteed_support=_sorted_actions(guaranteed),
                possible_support=_sorted_actions(possible),
            )
        )

    observations.sort(key=lambda row: row.token)
    return SupportEnvelope(
        schema_version=_SCHEMA,
        quotient_fingerprint=quotient_fp,
        claim_fingerprint=claim_fp,
        evidence_image_fingerprint=evidence_image.fingerprint(),
        evidence_fingerprint=evidence_image.evidence_fingerprint,
        depth=evidence_image.depth,
        block_supports=block_supports,
        observations=tuple(observations),
    )


__all__ = (
    "ArtifactMismatchError",
    "BlockSupport",
    "InconsistentQuotientSupportError",
    "ObservationSupportEnvelope",
    "SupportEnvelope",
    "SupportEnvelopeError",
    "compile_support_envelope",
)
