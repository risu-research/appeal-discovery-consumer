from __future__ import annotations

"""Evidence-set image through an already-compiled bounded q_{C,H} quotient.

Production evidence must come from compiler-owned forward observation semantics:

    ObservationSupportModel -> CompiledEvidenceSemantics -> Omega(e)

Only then does this module perform:

    Omega(e) subseteq decision states
        -> q_{C,h}[Omega(e)] subseteq predictive blocks

A hand-authored EvidenceSpec is intentionally not accepted at this production
boundary. It remains a definition/oracle data type only.
"""

from dataclasses import dataclass
import hashlib
import json

from .evidence_semantics import CompiledEvidenceSemantics
from .q_compiler import BoundedQuotient


_SCHEMA = "replaymark.qch-evidence-image.v2-derived-evidence"


class EvidenceImageError(ValueError):
    """Base class for fail-closed evidence-image compilation errors."""


class EvidenceOutsideQuotientError(EvidenceImageError):
    """Raised when compiled evidence and the quotient target domain disagree."""


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
    """Auditable image of compiler-derived retained evidence under q_{C,h}."""

    schema_version: str
    quotient_fingerprint: str
    claim_fingerprint: str
    evidence_semantics_fingerprint: str
    evidence_relation_fingerprint: str
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
            "evidence_semantics_fingerprint": self.evidence_semantics_fingerprint,
            "evidence_relation_fingerprint": self.evidence_relation_fingerprint,
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
    evidence: CompiledEvidenceSemantics,
    *,
    depth: int | None = None,
) -> QEvidenceImage:
    """Map compiler-derived Omega(e) exactly into q_{C,h}.

    `depth=None` means the claim-declared horizon already carried by `quotient`.
    An explicit shallower depth is permitted for audit/refinement diagnostics,
    but no deeper layer can be invented.
    """

    if not isinstance(quotient, BoundedQuotient):
        raise TypeError("quotient must be a BoundedQuotient")
    if not isinstance(evidence, CompiledEvidenceSemantics):
        raise TypeError(
            "production evidence image requires CompiledEvidenceSemantics; "
            "hand-authored EvidenceSpec is not a certification input"
        )
    if isinstance(depth, bool):
        raise TypeError("evidence-image depth must be an integer or None")

    depth = quotient.horizon if depth is None else int(depth)
    if depth < 0 or depth > quotient.horizon:
        raise IndexError(
            f"evidence-image depth {depth} outside compiled horizon "
            f"[0,{quotient.horizon}]"
        )

    if evidence.decision_states != quotient.decision_states:
        raise EvidenceOutsideQuotientError(
            "compiled evidence target domain does not exactly match the quotient domain"
        )

    layer = quotient.layer(depth)
    state_to_block = dict(layer.state_to_block)
    admitted = set(quotient.decision_states)
    spec = evidence.evidence_spec

    observations: list[ObservationImage] = []
    for token, compatible_states in spec.observations:
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
        evidence_semantics_fingerprint=evidence.fingerprint(),
        evidence_relation_fingerprint=evidence.relation_fingerprint,
        evidence_fingerprint=spec.fingerprint(),
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
