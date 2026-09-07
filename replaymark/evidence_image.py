from __future__ import annotations

"""Evidence-set image through an already-compiled bounded q_{C,H} quotient.

This module performs exactly one semantic step:

    Omega(e) subseteq decision states
        -> q_{C,h}[Omega(e)] subseteq predictive blocks

It does not compute support envelopes, replay verdicts, or reuse policy.
"""

from dataclasses import dataclass
import hashlib
import json

from .contracts import EvidenceSpec
from .q_compiler import BoundedQuotient


_SCHEMA = "replaymark.qch-evidence-image.v1"


class EvidenceImageError(ValueError):
    """Base class for fail-closed evidence-image compilation errors."""


class EvidenceOutsideQuotientError(EvidenceImageError):
    """Raised when retained evidence names a decision state outside the quotient."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class ObservationImage:
    """One evidence token and the q-blocks its compatible worlds can occupy."""

    token: str
    compatible_states: tuple[str, ...]
    q_blocks: tuple[str, ...]

    @property
    def raw_world_count(self) -> int:
        return len(self.compatible_states)

    @property
    def predictive_world_count(self) -> int:
        return len(self.q_blocks)

    @property
    def collapsed(self) -> bool:
        return self.predictive_world_count == 1

    def canonical_record(self) -> dict[str, object]:
        return {
            "token": self.token,
            "compatible_states": list(self.compatible_states),
            "q_blocks": list(self.q_blocks),
        }


@dataclass(frozen=True)
class QEvidenceImage:
    """Auditable image of finite retained evidence under one compiled q layer."""

    schema_version: str
    quotient_fingerprint: str
    claim_fingerprint: str
    evidence_fingerprint: str
    depth: int
    observations: tuple[ObservationImage, ...]

    def observation(self, token: str) -> ObservationImage:
        token = str(token)
        for row in self.observations:
            if row.token == token:
                return row
        raise KeyError(f"unknown evidence observation: {token!r}")

    def blocks_for(self, token: str) -> tuple[str, ...]:
        return self.observation(token).q_blocks

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "quotient_fingerprint": self.quotient_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "depth": self.depth,
            "observations": [
                row.canonical_record() for row in self.observations
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def compile_evidence_image(
    quotient: BoundedQuotient,
    evidence: EvidenceSpec,
    *,
    depth: int | None = None,
) -> QEvidenceImage:
    """Map each Omega(e) exactly into the requested compiled q_{C,h} layer.

    `depth=None` means the claim-declared horizon already carried by `quotient`.
    An explicit shallower depth is permitted for audit/refinement diagnostics,
    but no deeper layer can be invented.
    """

    if not isinstance(quotient, BoundedQuotient):
        raise TypeError("quotient must be a BoundedQuotient")
    if not isinstance(evidence, EvidenceSpec):
        raise TypeError("evidence must be EvidenceSpec")
    if isinstance(depth, bool):
        raise TypeError("evidence-image depth must be an integer or None")

    depth = quotient.horizon if depth is None else int(depth)
    if depth < 0 or depth > quotient.horizon:
        raise IndexError(
            f"evidence-image depth {depth} outside compiled horizon "
            f"[0,{quotient.horizon}]"
        )

    layer = quotient.layer(depth)
    state_to_block = dict(layer.state_to_block)
    admitted = set(quotient.decision_states)

    observations: list[ObservationImage] = []
    for token, compatible_states in evidence.observations:
        unknown = tuple(sorted(set(compatible_states) - admitted))
        if unknown:
            raise EvidenceOutsideQuotientError(
                f"evidence token {token!r} names decision states outside "
                f"the compiled target domain: {unknown!r}"
            )
        q_blocks = tuple(
            sorted({state_to_block[state] for state in compatible_states})
        )
        if not q_blocks:
            raise EvidenceImageError(
                f"evidence token {token!r} has an empty predictive image"
            )
        observations.append(
            ObservationImage(
                token=token,
                compatible_states=tuple(compatible_states),
                q_blocks=q_blocks,
            )
        )

    observations.sort(key=lambda row: row.token)
    return QEvidenceImage(
        schema_version=_SCHEMA,
        quotient_fingerprint=quotient.fingerprint(),
        claim_fingerprint=quotient.claim.fingerprint(),
        evidence_fingerprint=evidence.fingerprint(),
        depth=depth,
        observations=tuple(observations),
    )


__all__ = (
    "EvidenceImageError",
    "EvidenceOutsideQuotientError",
    "ObservationImage",
    "QEvidenceImage",
    "compile_evidence_image",
)
