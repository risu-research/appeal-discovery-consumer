from __future__ import annotations

"""Concrete, self-contained packaging for the frozen ReplayMark semantic contract.

This module does not add a new theorem. It packages already-established finite
semantics into one immutable, provider-free runtime object:

    sealed target semantics
      + bounded q_{C,H}
      + compiler-owned evidence semantics
      + q evidence image
      + support envelope
      + predictive witness index
        -> ExplicitCompiledContract

The object implements the re-frozen CompiledContract Protocol exactly. Runtime
queries consume only sealed artifacts; the original TargetModel and
ObservationSupportModel are not retained or called after compilation.
"""

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
from typing import Final

from .adjudicator import Adjudication, adjudicate_support
from .contracts import ClaimSpec, CompiledContract, ProjectedAction, TargetModel
from .evidence_image import QEvidenceImage, compile_evidence_image
from .evidence_semantics import (
    CompiledEvidenceSemantics,
    ObservationSupportModel,
    compile_evidence_semantics,
)
from .predictive_witness import (
    PredictiveContinuationWitness,
    PredictiveWitnessIndex,
    compile_predictive_witnesses,
)
from .q_compiler import BoundedQuotient, compile_bounded_q
from .rstar import RStarDecision, ReuseDisposition, maximal_certified_reuse
from .support_envelope import SupportEnvelope, compile_support_envelope
from .target_provenance import ObservedTargetSemantics, observe_target_semantics


_SCHEMA: Final = "replaymark.compiled-contract.explicit.v1"
_COMPILER_ID: Final = "replaymark.reference-packager.explicit.v1"
_Q_SCHEMA: Final = "replaymark.qch.deterministic.v2"
_EVIDENCE_SCHEMA: Final = "replaymark.evidence-semantics-closure.v1"
_IMAGE_SCHEMA: Final = "replaymark.qch-evidence-image.v2-derived-evidence"
_SUPPORT_SCHEMA: Final = "replaymark.support-envelope.deterministic.v1"
_WITNESS_INDEX_SCHEMA: Final = "replaymark.predictive-continuation-witness-index.v1"


class CompiledContractPackagingError(ValueError):
    """Base class for fail-closed concrete contract packaging errors."""


class ArtifactBindingError(CompiledContractPackagingError):
    """Raised when sealed compiler artifacts do not belong to one semantic object."""


class UnstablePackagingTargetError(CompiledContractPackagingError):
    """Raised when the TargetModel changes across end-to-end compilation."""


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
            raise TypeError("support element is not a ProjectedAction")
        unique[_action_key(action)] = action
    return tuple(unique[key] for key in sorted(unique))


def _partition_groups(layer) -> tuple[tuple[str, ...], ...]:
    groups = tuple(tuple(members) for _block, members in layer.blocks)
    if tuple(sorted(groups)) != groups:
        raise ArtifactBindingError(
            f"q layer {layer.depth} block membership is not canonical"
        )
    return groups


def _validate_quotient_against_snapshot(
    snapshot: ObservedTargetSemantics,
    quotient: BoundedQuotient,
) -> None:
    """Re-derive bounded deterministic partition semantics from the sealed snapshot.

    This is an assembly-time binding check, not a replacement for the independent q
    oracle. It prevents a valid target snapshot from being packaged with a q artifact
    that merely carries copied provenance strings.
    """

    claim = quotient.claim
    states = snapshot.decision_states
    continuations = snapshot.declared_continuation_order

    if quotient.decision_states != states:
        raise ArtifactBindingError("q decision-state domain differs from target snapshot")
    if quotient.continuation_alphabet != continuations:
        raise ArtifactBindingError("q continuation order differs from target snapshot")
    if len(quotient.layers) != claim.horizon + 1:
        raise ArtifactBindingError("q artifact does not contain exactly H+1 layers")
    for depth, layer in enumerate(quotient.layers):
        if layer.depth != depth:
            raise ArtifactBindingError("q layer depth metadata is not contiguous")
        covered = tuple(sorted(state for _block, members in layer.blocks for state in members))
        if covered != states or len(covered) != len(set(covered)):
            raise ArtifactBindingError(
                f"q layer {depth} does not partition the target domain exactly once"
            )

    current: dict[str, ProjectedAction] = {}
    post_state: dict[str, str] = {}
    for state in states:
        law = snapshot.current_law(state)
        if len(law) != 1 or law[0][2] != Fraction(1, 1):
            raise ArtifactBindingError(
                "explicit concrete contract currently packages deterministic "
                "point-mass q semantics only"
            )
        full_action, post, _mass = law[0]
        current[state] = claim.project(full_action)
        post_state[state] = post

    if tuple(state for state, _action in quotient.current_projected_actions) != states:
        raise ArtifactBindingError(
            "q current projected-action rows must cover states exactly once in canonical order"
        )
    q_current = dict(quotient.current_projected_actions)
    if q_current != current:
        raise ArtifactBindingError(
            "q current projected-action table does not match the sealed target snapshot"
        )

    successors: dict[str, dict[str, str]] = {}
    if tuple(state for state, _rows in quotient.deterministic_successors) != states:
        raise ArtifactBindingError(
            "q successor rows must cover states exactly once in canonical order"
        )
    q_successor_rows = dict(quotient.deterministic_successors)

    for state in states:
        q_row = dict(q_successor_rows[state])
        if len(q_row) != len(q_successor_rows[state]):
            raise ArtifactBindingError(f"q successor row for {state!r} has duplicate inputs")
        if claim.horizon == 0:
            if q_row:
                raise ArtifactBindingError("H=0 q artifact must not carry future successors")
            successors[state] = {}
            continue
        if tuple(q_row) != continuations:
            raise ArtifactBindingError(
                f"q successor row for {state!r} does not preserve declared continuation order"
            )
        expected: dict[str, str] = {}
        for continuation in continuations:
            law = snapshot.advance_law(post_state[state], continuation)
            if len(law) != 1 or law[0][1] != Fraction(1, 1):
                raise ArtifactBindingError(
                    "explicit concrete contract currently packages deterministic "
                    "point-mass q semantics only"
                )
            expected[continuation] = law[0][0]
        if q_row != expected:
            raise ArtifactBindingError(
                f"q successor row for {state!r} does not match the sealed target snapshot"
            )
        successors[state] = expected

    buckets0: dict[tuple[tuple[str, object], ...], list[str]] = {}
    for state in states:
        buckets0.setdefault(current[state].canonical_key(), []).append(state)
    expected_groups = tuple(
        sorted(tuple(sorted(members)) for members in buckets0.values())
    )
    expected_blocks = tuple(
        (f"q0_{index}", members)
        for index, members in enumerate(expected_groups)
    )
    if quotient.layer(0).blocks != expected_blocks:
        raise ArtifactBindingError(
            "q0 blocks/identifiers do not equal the canonical current-claim partition"
        )

    previous_group_of: dict[str, tuple[str, ...]] = {}
    for group in expected_groups:
        for state in group:
            previous_group_of[state] = group

    for depth in range(1, claim.horizon + 1):
        buckets: dict[object, list[str]] = {}
        for state in states:
            signature = (
                current[state].canonical_key(),
                tuple(
                    (u, previous_group_of[successors[state][u]])
                    for u in continuations
                ),
            )
            buckets.setdefault(signature, []).append(state)
        expected_groups = tuple(
            sorted(tuple(sorted(members)) for members in buckets.values())
        )
        expected_blocks = tuple(
            (f"q{depth}_{index}", members)
            for index, members in enumerate(expected_groups)
        )
        if quotient.layer(depth).blocks != expected_blocks:
            raise ArtifactBindingError(
                f"q layer {depth} blocks/identifiers do not equal canonical bounded refinement"
            )
        previous_group_of = {}
        for group in expected_groups:
            for state in group:
                previous_group_of[state] = group

    first_fixed: int | None = None
    for depth in range(1, claim.horizon + 1):
        if _partition_groups(quotient.layer(depth - 1)) == _partition_groups(
            quotient.layer(depth)
        ):
            first_fixed = depth - 1
            break
    if quotient.first_observed_fixed_point != first_fixed:
        raise ArtifactBindingError(
            "q first_observed_fixed_point metadata does not match its bounded layers"
        )


def _raw_world_support(
    snapshot: ObservedTargetSemantics,
    claim: ClaimSpec,
    state: str,
) -> frozenset[ProjectedAction]:
    support = {
        claim.project(action)
        for action, _post_state, mass in snapshot.current_law(state)
        if mass > 0
    }
    if not support:
        raise ArtifactBindingError(f"target world {state!r} has empty positive support")
    return frozenset(support)


def _validate_cross_artifacts(
    snapshot: ObservedTargetSemantics,
    quotient: BoundedQuotient,
    evidence: CompiledEvidenceSemantics,
    image: QEvidenceImage,
    envelope: SupportEnvelope,
    witnesses: PredictiveWitnessIndex,
) -> None:
    if not isinstance(snapshot, ObservedTargetSemantics):
        raise TypeError("target_snapshot must be ObservedTargetSemantics")
    if not isinstance(quotient, BoundedQuotient):
        raise TypeError("quotient must be BoundedQuotient")
    if not isinstance(evidence, CompiledEvidenceSemantics):
        raise TypeError("evidence_semantics must be CompiledEvidenceSemantics")
    if not isinstance(image, QEvidenceImage):
        raise TypeError("evidence_image must be QEvidenceImage")
    if not isinstance(envelope, SupportEnvelope):
        raise TypeError("support_envelope must be SupportEnvelope")
    if not isinstance(witnesses, PredictiveWitnessIndex):
        raise TypeError("predictive_witness_index must be PredictiveWitnessIndex")

    expected_schemas = (
        ("bounded quotient", quotient.schema_version, _Q_SCHEMA),
        ("compiled evidence semantics", evidence.schema_version, _EVIDENCE_SCHEMA),
        ("q evidence image", image.schema_version, _IMAGE_SCHEMA),
        ("support envelope", envelope.schema_version, _SUPPORT_SCHEMA),
        ("predictive witness index", witnesses.schema_version, _WITNESS_INDEX_SCHEMA),
    )
    for name, actual, expected in expected_schemas:
        if actual != expected:
            raise ArtifactBindingError(
                f"{name} schema {actual!r} is not the admitted schema {expected!r}"
            )

    claim = quotient.claim
    claim_fp = claim.fingerprint()
    quotient_fp = quotient.fingerprint()
    snapshot_fp = snapshot.fingerprint()
    evidence_fp = evidence.fingerprint()
    image_fp = image.fingerprint()
    envelope_fp = envelope.fingerprint()
    witness_fp = witnesses.fingerprint()

    if quotient.target_model_fingerprint != snapshot.provider_fingerprint:
        raise ArtifactBindingError("q provider metadata differs from target snapshot")
    if quotient.target_semantic_digest != snapshot.semantic_digest:
        raise ArtifactBindingError("q semantic digest differs from target snapshot")
    if quotient.target_snapshot_fingerprint != snapshot_fp:
        raise ArtifactBindingError("q snapshot fingerprint differs from target snapshot")
    if quotient.target_domain_digest != snapshot.domain_digest:
        raise ArtifactBindingError("q target-domain digest differs from target snapshot")
    if quotient.target_current_semantics_digest != snapshot.current_semantics_digest:
        raise ArtifactBindingError("q current-semantics digest differs from target snapshot")
    if quotient.target_advance_semantics_digest != snapshot.advance_semantics_digest:
        raise ArtifactBindingError("q advance-semantics digest differs from target snapshot")

    _validate_quotient_against_snapshot(snapshot, quotient)

    if evidence.decision_states != quotient.decision_states:
        raise ArtifactBindingError("evidence world domain differs from q target domain")

    if image.depth != claim.horizon:
        raise ArtifactBindingError(
            "concrete contract must package the claim-declared H, not a shallower audit image"
        )
    if image.quotient_fingerprint != quotient_fp:
        raise ArtifactBindingError("evidence image is bound to a different q artifact")
    if image.claim_fingerprint != claim_fp:
        raise ArtifactBindingError("evidence image is bound to a different claim")
    if image.evidence_semantics_fingerprint != evidence_fp:
        raise ArtifactBindingError(
            "evidence image is bound to different compiled evidence semantics"
        )
    if image.evidence_relation_fingerprint != evidence.relation_fingerprint:
        raise ArtifactBindingError("evidence image relation identity mismatch")
    if image.evidence_fingerprint != evidence.evidence_spec.fingerprint():
        raise ArtifactBindingError("evidence image inverse-spec identity mismatch")

    expected_image = compile_evidence_image(quotient, evidence)
    if image.canonical_bytes() != expected_image.canonical_bytes():
        raise ArtifactBindingError(
            "packaged evidence image is not the exact H-image of the packaged evidence semantics"
        )

    if envelope.depth != claim.horizon:
        raise ArtifactBindingError("support envelope is not compiled at claim horizon H")
    if envelope.quotient_fingerprint != quotient_fp:
        raise ArtifactBindingError("support envelope is bound to a different q artifact")
    if envelope.claim_fingerprint != claim_fp:
        raise ArtifactBindingError("support envelope is bound to a different claim")
    if envelope.evidence_image_fingerprint != image_fp:
        raise ArtifactBindingError("support envelope is bound to a different evidence image")
    if envelope.evidence_fingerprint != evidence.evidence_spec.fingerprint():
        raise ArtifactBindingError("support envelope inverse-spec identity mismatch")

    expected_envelope = compile_support_envelope(quotient, image)
    if envelope.canonical_bytes() != expected_envelope.canonical_bytes():
        raise ArtifactBindingError(
            "packaged support envelope is not the exact envelope of the packaged q/evidence image"
        )

    if witnesses.depth != claim.horizon:
        raise ArtifactBindingError("predictive witness index is not compiled at claim horizon H")
    if witnesses.quotient_fingerprint != quotient_fp:
        raise ArtifactBindingError("predictive witness index is bound to a different q artifact")
    if witnesses.claim_fingerprint != claim_fp:
        raise ArtifactBindingError("predictive witness index is bound to a different claim")
    if witnesses.decision_states != quotient.decision_states:
        raise ArtifactBindingError("predictive witness world domain differs from q")
    if witnesses.continuation_alphabet != quotient.continuation_alphabet:
        raise ArtifactBindingError("predictive witness continuation order differs from q")

    expected_witnesses = compile_predictive_witnesses(quotient)
    if witnesses.canonical_bytes() != expected_witnesses.canonical_bytes():
        raise ArtifactBindingError(
            "packaged predictive witnesses are not the exact shortest H-witness index"
        )

    image_rows = {row.token: row for row in image.observations}
    envelope_rows = {row.token: row for row in envelope.observations}
    expected_tokens = tuple(token for token, _states in evidence.evidence_spec.observations)
    if tuple(sorted(image_rows)) != expected_tokens:
        raise ArtifactBindingError("evidence image token set differs from compiled evidence")
    if tuple(sorted(envelope_rows)) != expected_tokens:
        raise ArtifactBindingError("support envelope token set differs from compiled evidence")

    final_layer = quotient.layer()
    for token, compatible in evidence.evidence_spec.observations:
        image_row = image_rows[token]
        envelope_row = envelope_rows[token]
        if image_row.compatible_states != compatible:
            raise ArtifactBindingError(
                f"q evidence image changes Omega({token!r})"
            )
        expected_blocks = tuple(
            sorted({final_layer.block_of(state) for state in compatible})
        )
        if image_row.q_blocks != expected_blocks or envelope_row.q_blocks != expected_blocks:
            raise ArtifactBindingError(
                f"q image/support envelope disagree for evidence token {token!r}"
            )

        raw_supports = [
            set(_raw_world_support(snapshot, claim, state))
            for state in compatible
        ]
        guaranteed = set(raw_supports[0])
        possible: set[ProjectedAction] = set()
        for support in raw_supports:
            guaranteed.intersection_update(support)
            possible.update(support)
        if envelope_row.guaranteed_support != _sorted_actions(guaranteed):
            raise ArtifactBindingError(
                f"S^- for {token!r} is not the raw-world support intersection"
            )
        if envelope_row.possible_support != _sorted_actions(possible):
            raise ArtifactBindingError(
                f"S^+ for {token!r} is not the raw-world support union"
            )

    for name, value in (
        ("quotient", quotient_fp),
        ("target_snapshot", snapshot_fp),
        ("evidence_semantics", evidence_fp),
        ("evidence_image", image_fp),
        ("support_envelope", envelope_fp),
        ("predictive_witness_index", witness_fp),
    ):
        if not isinstance(value, str) or len(value) != 64:
            raise ArtifactBindingError(f"{name} fingerprint is not a SHA-256 hex digest")
        try:
            int(value, 16)
        except ValueError as exc:
            raise ArtifactBindingError(
                f"{name} fingerprint is not hexadecimal"
            ) from exc
        if value != value.lower():
            raise ArtifactBindingError(
                f"{name} fingerprint must use canonical lowercase hexadecimal"
            )


@dataclass(frozen=True, slots=True)
class ExplicitCompiledContract:
    """Immutable explicit-table implementation of the frozen CompiledContract API.

    The complete semantic derivation artifacts are embedded by value. The runtime
    object therefore requires neither TargetModel nor ObservationSupportModel.
    """

    target_snapshot: ObservedTargetSemantics
    quotient: BoundedQuotient
    evidence_semantics: CompiledEvidenceSemantics
    evidence_image: QEvidenceImage
    support_envelope: SupportEnvelope
    predictive_witness_index: PredictiveWitnessIndex
    schema_version: str = field(init=False, default=_SCHEMA)
    compiler_id: str = field(init=False, default=_COMPILER_ID)

    def __post_init__(self) -> None:
        _validate_cross_artifacts(
            self.target_snapshot,
            self.quotient,
            self.evidence_semantics,
            self.evidence_image,
            self.support_envelope,
            self.predictive_witness_index,
        )
        if not isinstance(self, CompiledContract):
            raise TypeError("concrete contract does not satisfy CompiledContract Protocol")

    @property
    def claim(self) -> ClaimSpec:
        return self.quotient.claim

    @property
    def claim_fingerprint(self) -> str:
        return self.claim.fingerprint()

    @property
    def target_provider_fingerprint(self) -> str:
        return self.target_snapshot.provider_fingerprint

    @property
    def target_semantic_digest(self) -> str:
        return self.target_snapshot.semantic_digest

    @property
    def target_snapshot_fingerprint(self) -> str:
        return self.target_snapshot.fingerprint()

    @property
    def evidence_semantics_fingerprint(self) -> str:
        return self.evidence_semantics.fingerprint()

    @property
    def evidence_relation_fingerprint(self) -> str:
        return self.evidence_semantics.relation_fingerprint

    @property
    def quotient_fingerprint(self) -> str:
        return self.quotient.fingerprint()

    @property
    def support_envelope_fingerprint(self) -> str:
        return self.support_envelope.fingerprint()

    @property
    def predictive_witness_index_fingerprint(self) -> str:
        return self.predictive_witness_index.fingerprint()

    def compatible_worlds(self, observation_token: str) -> tuple[str, ...]:
        return self.evidence_semantics.compatible_states(observation_token)

    def adjudicate(
        self,
        observation_token: str,
        historical_action: ProjectedAction,
    ) -> Adjudication:
        return adjudicate_support(
            self.support_envelope,
            self.claim,
            observation_token,
            historical_action,
        )

    def certify_reuse(
        self,
        observation_token: str,
        historical_action: ProjectedAction,
    ) -> RStarDecision:
        return maximal_certified_reuse(
            self.adjudicate(observation_token, historical_action)
        )

    def reuse_counterexample_world(
        self,
        observation_token: str,
        historical_action: ProjectedAction,
    ) -> str | None:
        decision = self.certify_reuse(observation_token, historical_action)
        if decision.disposition is ReuseDisposition.REUSE:
            return None

        projected = decision.projected_action
        for world in self.compatible_worlds(observation_token):
            if projected not in _raw_world_support(
                self.target_snapshot, self.claim, world
            ):
                return world
        raise ArtifactBindingError(
            "R* blocks reuse but the sealed raw worlds contain no excluding counterexample"
        )

    def predictive_witness(
        self,
        left_world: str,
        right_world: str,
    ) -> PredictiveContinuationWitness | None:
        return self.predictive_witness_index.witness(left_world, right_world)

    def canonical_record(self) -> dict[str, object]:
        """Self-contained canonical contract record.

        The manifest duplicates only content identities; the complete sealed
        semantic artifacts are embedded so a contract file is auditable without
        the original adapters or compilation environment.
        """

        return {
            "schema": self.schema_version,
            "compiler_id": self.compiler_id,
            "manifest": {
                "claim_fingerprint": self.claim_fingerprint,
                "target_provider_fingerprint": self.target_provider_fingerprint,
                "target_semantic_digest": self.target_semantic_digest,
                "target_snapshot_fingerprint": self.target_snapshot_fingerprint,
                "evidence_semantics_fingerprint": self.evidence_semantics_fingerprint,
                "evidence_relation_fingerprint": self.evidence_relation_fingerprint,
                "quotient_fingerprint": self.quotient_fingerprint,
                "support_envelope_fingerprint": self.support_envelope_fingerprint,
                "predictive_witness_index_fingerprint": (
                    self.predictive_witness_index_fingerprint
                ),
            },
            "artifacts": {
                "target_snapshot": self.target_snapshot.canonical_record(),
                "bounded_quotient": self.quotient.canonical_record(),
                "evidence_semantics": self.evidence_semantics.canonical_record(),
                "evidence_image": self.evidence_image.canonical_record(),
                "support_envelope": self.support_envelope.canonical_record(),
                "predictive_witness_index": (
                    self.predictive_witness_index.canonical_record()
                ),
            },
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def package_compiled_contract(
    *,
    target_snapshot: ObservedTargetSemantics,
    quotient: BoundedQuotient,
    evidence_semantics: CompiledEvidenceSemantics,
    evidence_image: QEvidenceImage,
    support_envelope: SupportEnvelope,
    predictive_witness_index: PredictiveWitnessIndex,
) -> ExplicitCompiledContract:
    """Package already-compiled semantic artifacts after exhaustive binding checks."""

    return ExplicitCompiledContract(
        target_snapshot=target_snapshot,
        quotient=quotient,
        evidence_semantics=evidence_semantics,
        evidence_image=evidence_image,
        support_envelope=support_envelope,
        predictive_witness_index=predictive_witness_index,
    )


def compile_explicit_contract(
    target: TargetModel,
    claim: ClaimSpec,
    observation_model: ObservationSupportModel,
    *,
    evidence_id: str,
) -> ExplicitCompiledContract:
    """Compile and package the established finite deterministic semantic chain.

    The target is observed before and after the constituent compiler stages. The
    q artifact must also identify exactly the pre-observed snapshot. Any semantic,
    domain, provider-metadata, or continuation-order drift fails closed.

    This function is an orchestration layer only: every semantic transformation
    is delegated to the already-gated compiler stage that owns it.
    """

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")
    if not isinstance(observation_model, ObservationSupportModel):
        raise TypeError(
            "observation_model does not satisfy ObservationSupportModel protocol"
        )

    before = observe_target_semantics(target)
    quotient = compile_bounded_q(target, claim)
    if quotient.target_snapshot_fingerprint != before.fingerprint():
        raise UnstablePackagingTargetError(
            "TargetModel changed between packaging pre-observation and q compilation"
        )

    evidence = compile_evidence_semantics(
        target,
        observation_model,
        evidence_id=evidence_id,
    )

    after = observe_target_semantics(target)
    if after.canonical_bytes() != before.canonical_bytes():
        raise UnstablePackagingTargetError(
            "TargetModel changed across end-to-end contract compilation"
        )

    image = compile_evidence_image(quotient, evidence)
    envelope = compile_support_envelope(quotient, image)
    witnesses = compile_predictive_witnesses(quotient)

    return package_compiled_contract(
        target_snapshot=before,
        quotient=quotient,
        evidence_semantics=evidence,
        evidence_image=image,
        support_envelope=envelope,
        predictive_witness_index=witnesses,
    )


__all__ = (
    "ArtifactBindingError",
    "CompiledContractPackagingError",
    "ExplicitCompiledContract",
    "UnstablePackagingTargetError",
    "compile_explicit_contract",
    "package_compiled_contract",
)
