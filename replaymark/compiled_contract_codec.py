from __future__ import annotations

"""Strict canonical JSON codec for ExplicitCompiledContract.

The loader is intentionally fail-closed. It rejects duplicate JSON object keys,
non-finite numeric constants, unknown/missing fields, malformed exact rational
masses, foreign schema layouts, cross-artifact mismatches, and any byte encoding
that is not exactly the canonical serialization of the reconstructed contract.

Parsing never trusts manifest fingerprints: it reconstructs every sealed semantic
artifact, lets each artifact validate itself, runs the concrete package binding
checks, recomputes the manifest, and finally compares canonical bytes.
"""

from fractions import Fraction
import json
from typing import Mapping

from .compiled_contract import ExplicitCompiledContract, package_compiled_contract
from .contracts import ClaimSpec, EvidenceSpec, ProjectedAction
from .evidence_image import ObservationImage, QEvidenceImage
from .evidence_semantics import CompiledEvidenceSemantics
from .predictive_witness import (
    PredictiveContinuationWitness,
    PredictiveWitnessIndex,
)
from .q_compiler import BoundedQuotient, PartitionLayer
from .support_envelope import (
    BlockSupport,
    ObservationSupportEnvelope,
    SupportEnvelope,
)
from .target_provenance import ObservedTargetSemantics


class ContractDecodeError(ValueError):
    """Base class for strict concrete-contract decoding failures."""


class DuplicateJSONKeyError(ContractDecodeError):
    """Raised before object construction when canonical JSON contains duplicate keys."""


class NonCanonicalContractError(ContractDecodeError):
    """Raised when valid-looking JSON is not the exact canonical contract encoding."""


def _reject_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ContractDecodeError(f"non-finite JSON numeric constant is forbidden: {value}")


def _mapping(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ContractDecodeError(f"{where} must be a JSON object")
    if any(not isinstance(key, str) for key in value):
        raise ContractDecodeError(f"{where} contains a non-string object key")
    return value


def _list(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise ContractDecodeError(f"{where} must be a JSON array")
    return value


def _exact(record: Mapping[str, object], keys: tuple[str, ...], where: str) -> None:
    actual = set(record)
    expected = set(keys)
    missing = tuple(sorted(expected - actual))
    extra = tuple(sorted(actual - expected))
    if missing or extra:
        raise ContractDecodeError(
            f"{where} field set mismatch: missing={missing!r}, extra={extra!r}"
        )


def _string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractDecodeError(f"{where} must be a non-empty canonical string")
    return value


def _integer(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractDecodeError(f"{where} must be an integer")
    return value


def _optional_integer(value: object, where: str) -> int | None:
    return None if value is None else _integer(value, where)


def _string_tuple(value: object, where: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{where}[]") for item in _list(value, where))


def _fraction(value: object, where: str) -> Fraction:
    record = _mapping(value, where)
    _exact(record, ("numerator", "denominator"), where)
    numerator = _integer(record["numerator"], f"{where}.numerator")
    denominator = _integer(record["denominator"], f"{where}.denominator")
    if denominator <= 0:
        raise ContractDecodeError(f"{where}.denominator must be > 0")
    return Fraction(numerator, denominator)


def _action(value: object, where: str) -> ProjectedAction:
    record = _mapping(value, where)
    if not record:
        raise ContractDecodeError(f"{where} action mapping must not be empty")
    try:
        return ProjectedAction.from_mapping(record)
    except (TypeError, ValueError, KeyError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def _claim(value: object, where: str) -> ClaimSpec:
    record = _mapping(value, where)
    _exact(
        record,
        ("schema", "claim_id", "dimensions", "horizon", "consequence_endpoint"),
        where,
    )
    if record["schema"] != "replaymark.claim.v1":
        raise ContractDecodeError(f"unsupported claim schema: {record['schema']!r}")
    try:
        return ClaimSpec(
            claim_id=_string(record["claim_id"], f"{where}.claim_id"),
            dimensions=_string_tuple(record["dimensions"], f"{where}.dimensions"),
            horizon=_integer(record["horizon"], f"{where}.horizon"),
            consequence_endpoint=_string(
                record["consequence_endpoint"], f"{where}.consequence_endpoint"
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def _evidence_spec(value: object, where: str) -> EvidenceSpec:
    record = _mapping(value, where)
    _exact(record, ("schema", "evidence_id", "observations"), where)
    if record["schema"] != "replaymark.evidence.v1":
        raise ContractDecodeError(
            f"unsupported evidence-spec schema: {record['schema']!r}"
        )
    rows = []
    for index, item in enumerate(_list(record["observations"], f"{where}.observations")):
        row_where = f"{where}.observations[{index}]"
        row = _mapping(item, row_where)
        _exact(row, ("token", "compatible_states"), row_where)
        rows.append(
            (
                _string(row["token"], f"{row_where}.token"),
                _string_tuple(
                    row["compatible_states"], f"{row_where}.compatible_states"
                ),
            )
        )
    try:
        return EvidenceSpec(
            evidence_id=_string(record["evidence_id"], f"{where}.evidence_id"),
            observations=tuple(rows),
        )
    except (TypeError, ValueError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def _target_snapshot(value: object, where: str) -> ObservedTargetSemantics:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "provider_fingerprint",
            "declared_continuation_order",
            "semantic_snapshot",
        ),
        where,
    )
    if record["schema"] != "replaymark.target-semantics-snapshot.v1":
        raise ContractDecodeError(
            f"unsupported target snapshot schema: {record['schema']!r}"
        )

    semantic = _mapping(record["semantic_snapshot"], f"{where}.semantic_snapshot")
    _exact(
        semantic,
        ("schema", "domain", "current", "advance", "component_digests"),
        f"{where}.semantic_snapshot",
    )
    if semantic["schema"] != "replaymark.target-semantic-root.v1":
        raise ContractDecodeError("unsupported target semantic-root schema")

    domain = _mapping(semantic["domain"], f"{where}.semantic_snapshot.domain")
    _exact(
        domain,
        ("schema", "decision_states", "continuation_symbols"),
        f"{where}.semantic_snapshot.domain",
    )
    if domain["schema"] != "replaymark.target-semantics-domain.v1":
        raise ContractDecodeError("unsupported target domain schema")
    states = _string_tuple(
        domain["decision_states"], f"{where}.semantic_snapshot.domain.decision_states"
    )
    semantic_continuations = _string_tuple(
        domain["continuation_symbols"],
        f"{where}.semantic_snapshot.domain.continuation_symbols",
    )

    current_record = _mapping(
        semantic["current"], f"{where}.semantic_snapshot.current"
    )
    _exact(
        current_record,
        ("schema", "current_laws"),
        f"{where}.semantic_snapshot.current",
    )
    if current_record["schema"] != "replaymark.target-current-law.v1":
        raise ContractDecodeError("unsupported target current-law schema")
    current_rows = []
    for i, item in enumerate(
        _list(
            current_record["current_laws"],
            f"{where}.semantic_snapshot.current.current_laws",
        )
    ):
        row_where = f"{where}.semantic_snapshot.current.current_laws[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("decision_state", "branches"), row_where)
        branches = []
        for j, branch_item in enumerate(_list(row["branches"], f"{row_where}.branches")):
            branch_where = f"{row_where}.branches[{j}]"
            branch = _mapping(branch_item, branch_where)
            _exact(branch, ("action", "post_state", "mass"), branch_where)
            branches.append(
                (
                    _action(branch["action"], f"{branch_where}.action"),
                    _string(branch["post_state"], f"{branch_where}.post_state"),
                    _fraction(branch["mass"], f"{branch_where}.mass"),
                )
            )
        current_rows.append(
            (
                _string(row["decision_state"], f"{row_where}.decision_state"),
                tuple(branches),
            )
        )

    advance_record = _mapping(
        semantic["advance"], f"{where}.semantic_snapshot.advance"
    )
    _exact(
        advance_record,
        ("schema", "advance_laws"),
        f"{where}.semantic_snapshot.advance",
    )
    if advance_record["schema"] != "replaymark.target-advance-law.v1":
        raise ContractDecodeError("unsupported target advance-law schema")
    advance_rows = []
    for i, item in enumerate(
        _list(
            advance_record["advance_laws"],
            f"{where}.semantic_snapshot.advance.advance_laws",
        )
    ):
        row_where = f"{where}.semantic_snapshot.advance.advance_laws[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("post_state", "continuation", "branches"), row_where)
        branches = []
        for j, branch_item in enumerate(_list(row["branches"], f"{row_where}.branches")):
            branch_where = f"{row_where}.branches[{j}]"
            branch = _mapping(branch_item, branch_where)
            _exact(branch, ("next_decision_state", "mass"), branch_where)
            branches.append(
                (
                    _string(
                        branch["next_decision_state"],
                        f"{branch_where}.next_decision_state",
                    ),
                    _fraction(branch["mass"], f"{branch_where}.mass"),
                )
            )
        advance_rows.append(
            (
                _string(row["post_state"], f"{row_where}.post_state"),
                _string(row["continuation"], f"{row_where}.continuation"),
                tuple(branches),
            )
        )

    digests = _mapping(
        semantic["component_digests"],
        f"{where}.semantic_snapshot.component_digests",
    )
    _exact(
        digests,
        ("domain", "current", "advance", "root"),
        f"{where}.semantic_snapshot.component_digests",
    )
    declared = _string_tuple(
        record["declared_continuation_order"],
        f"{where}.declared_continuation_order",
    )
    if tuple(sorted(semantic_continuations)) != tuple(sorted(declared)):
        raise ContractDecodeError(
            "target semantic domain and declared continuation order name different alphabets"
        )

    try:
        return ObservedTargetSemantics(
            schema_version=_string(record["schema"], f"{where}.schema"),
            provider_fingerprint=_string(
                record["provider_fingerprint"], f"{where}.provider_fingerprint"
            ),
            decision_states=states,
            declared_continuation_order=declared,
            current_laws=tuple(current_rows),
            advance_laws=tuple(advance_rows),
            domain_digest=_string(digests["domain"], f"{where}.digest.domain"),
            current_semantics_digest=_string(
                digests["current"], f"{where}.digest.current"
            ),
            advance_semantics_digest=_string(
                digests["advance"], f"{where}.digest.advance"
            ),
            semantic_digest=_string(digests["root"], f"{where}.digest.root"),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def _partition_layer(value: object, where: str) -> PartitionLayer:
    record = _mapping(value, where)
    _exact(record, ("depth", "blocks"), where)
    depth = _integer(record["depth"], f"{where}.depth")
    blocks = []
    state_to_block = []
    for i, item in enumerate(_list(record["blocks"], f"{where}.blocks")):
        block_where = f"{where}.blocks[{i}]"
        block = _mapping(item, block_where)
        _exact(block, ("id", "decision_states"), block_where)
        block_id = _string(block["id"], f"{block_where}.id")
        members = _string_tuple(
            block["decision_states"], f"{block_where}.decision_states"
        )
        blocks.append((block_id, members))
        state_to_block.extend((state, block_id) for state in members)
    state_to_block.sort()
    return PartitionLayer(
        depth=depth,
        state_to_block=tuple(state_to_block),
        blocks=tuple(blocks),
    )


def _bounded_quotient(value: object, where: str) -> BoundedQuotient:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "claim",
            "claim_fingerprint",
            "target_provenance",
            "horizon",
            "decision_states",
            "continuation_alphabet",
            "current_projected_actions",
            "deterministic_successors",
            "layers",
            "first_observed_fixed_point",
        ),
        where,
    )
    if record["schema"] != "replaymark.qch.deterministic.v2":
        raise ContractDecodeError(f"unsupported q schema: {record['schema']!r}")
    claim = _claim(record["claim"], f"{where}.claim")
    claim_fp = _string(record["claim_fingerprint"], f"{where}.claim_fingerprint")
    if claim_fp != claim.fingerprint():
        raise ContractDecodeError("q claim_fingerprint does not match embedded claim")
    horizon = _integer(record["horizon"], f"{where}.horizon")
    if horizon != claim.horizon:
        raise ContractDecodeError("q horizon differs from embedded ClaimSpec")

    provenance = _mapping(record["target_provenance"], f"{where}.target_provenance")
    _exact(
        provenance,
        (
            "provider_fingerprint",
            "compiler_observed_semantic_digest",
            "snapshot_fingerprint",
            "component_digests",
        ),
        f"{where}.target_provenance",
    )
    component = _mapping(
        provenance["component_digests"],
        f"{where}.target_provenance.component_digests",
    )
    _exact(
        component,
        ("domain", "current", "advance"),
        f"{where}.target_provenance.component_digests",
    )

    current = []
    for i, item in enumerate(
        _list(record["current_projected_actions"], f"{where}.current_projected_actions")
    ):
        row_where = f"{where}.current_projected_actions[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("decision_state", "action"), row_where)
        current.append(
            (
                _string(row["decision_state"], f"{row_where}.decision_state"),
                _action(row["action"], f"{row_where}.action"),
            )
        )

    successors = []
    for i, item in enumerate(
        _list(record["deterministic_successors"], f"{where}.deterministic_successors")
    ):
        row_where = f"{where}.deterministic_successors[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("decision_state", "successors"), row_where)
        succ = []
        for j, succ_item in enumerate(_list(row["successors"], f"{row_where}.successors")):
            succ_where = f"{row_where}.successors[{j}]"
            srow = _mapping(succ_item, succ_where)
            _exact(srow, ("continuation", "next_decision_state"), succ_where)
            succ.append(
                (
                    _string(srow["continuation"], f"{succ_where}.continuation"),
                    _string(
                        srow["next_decision_state"],
                        f"{succ_where}.next_decision_state",
                    ),
                )
            )
        successors.append(
            (
                _string(row["decision_state"], f"{row_where}.decision_state"),
                tuple(succ),
            )
        )

    layers = tuple(
        _partition_layer(item, f"{where}.layers[{i}]")
        for i, item in enumerate(_list(record["layers"], f"{where}.layers"))
    )

    return BoundedQuotient(
        schema_version=_string(record["schema"], f"{where}.schema"),
        claim=claim,
        target_model_fingerprint=_string(
            provenance["provider_fingerprint"],
            f"{where}.target_provenance.provider_fingerprint",
        ),
        target_semantic_digest=_string(
            provenance["compiler_observed_semantic_digest"],
            f"{where}.target_provenance.compiler_observed_semantic_digest",
        ),
        target_snapshot_fingerprint=_string(
            provenance["snapshot_fingerprint"],
            f"{where}.target_provenance.snapshot_fingerprint",
        ),
        target_domain_digest=_string(
            component["domain"], f"{where}.target_provenance.component.domain"
        ),
        target_current_semantics_digest=_string(
            component["current"], f"{where}.target_provenance.component.current"
        ),
        target_advance_semantics_digest=_string(
            component["advance"], f"{where}.target_provenance.component.advance"
        ),
        decision_states=_string_tuple(
            record["decision_states"], f"{where}.decision_states"
        ),
        continuation_alphabet=_string_tuple(
            record["continuation_alphabet"], f"{where}.continuation_alphabet"
        ),
        layers=layers,
        current_projected_actions=tuple(current),
        deterministic_successors=tuple(successors),
        first_observed_fixed_point=_optional_integer(
            record["first_observed_fixed_point"],
            f"{where}.first_observed_fixed_point",
        ),
    )


def _compiled_evidence(value: object, where: str) -> CompiledEvidenceSemantics:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "evidence_id",
            "target_domain_fingerprint",
            "relation_fingerprint",
            "decision_states",
            "world_observation_supports",
            "derived_evidence_spec",
        ),
        where,
    )
    if record["schema"] != "replaymark.evidence-semantics-closure.v1":
        raise ContractDecodeError(
            f"unsupported compiled-evidence schema: {record['schema']!r}"
        )
    supports = []
    for i, item in enumerate(
        _list(
            record["world_observation_supports"],
            f"{where}.world_observation_supports",
        )
    ):
        row_where = f"{where}.world_observation_supports[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("decision_state", "tokens"), row_where)
        supports.append(
            (
                _string(row["decision_state"], f"{row_where}.decision_state"),
                _string_tuple(row["tokens"], f"{row_where}.tokens"),
            )
        )
    try:
        return CompiledEvidenceSemantics(
            schema_version=_string(record["schema"], f"{where}.schema"),
            evidence_id=_string(record["evidence_id"], f"{where}.evidence_id"),
            target_domain_fingerprint=_string(
                record["target_domain_fingerprint"],
                f"{where}.target_domain_fingerprint",
            ),
            relation_fingerprint=_string(
                record["relation_fingerprint"], f"{where}.relation_fingerprint"
            ),
            decision_states=_string_tuple(
                record["decision_states"], f"{where}.decision_states"
            ),
            world_observation_supports=tuple(supports),
            evidence_spec=_evidence_spec(
                record["derived_evidence_spec"], f"{where}.derived_evidence_spec"
            ),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def _evidence_image(value: object, where: str) -> QEvidenceImage:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "quotient_fingerprint",
            "claim_fingerprint",
            "evidence_semantics_fingerprint",
            "evidence_relation_fingerprint",
            "evidence_fingerprint",
            "depth",
            "observations",
        ),
        where,
    )
    if record["schema"] != "replaymark.qch-evidence-image.v2-derived-evidence":
        raise ContractDecodeError(
            f"unsupported evidence-image schema: {record['schema']!r}"
        )
    rows = []
    for i, item in enumerate(_list(record["observations"], f"{where}.observations")):
        row_where = f"{where}.observations[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("token", "compatible_states", "q_blocks"), row_where)
        rows.append(
            ObservationImage(
                token=_string(row["token"], f"{row_where}.token"),
                compatible_states=_string_tuple(
                    row["compatible_states"], f"{row_where}.compatible_states"
                ),
                q_blocks=_string_tuple(row["q_blocks"], f"{row_where}.q_blocks"),
            )
        )
    return QEvidenceImage(
        schema_version=_string(record["schema"], f"{where}.schema"),
        quotient_fingerprint=_string(
            record["quotient_fingerprint"], f"{where}.quotient_fingerprint"
        ),
        claim_fingerprint=_string(
            record["claim_fingerprint"], f"{where}.claim_fingerprint"
        ),
        evidence_semantics_fingerprint=_string(
            record["evidence_semantics_fingerprint"],
            f"{where}.evidence_semantics_fingerprint",
        ),
        evidence_relation_fingerprint=_string(
            record["evidence_relation_fingerprint"],
            f"{where}.evidence_relation_fingerprint",
        ),
        evidence_fingerprint=_string(
            record["evidence_fingerprint"], f"{where}.evidence_fingerprint"
        ),
        depth=_integer(record["depth"], f"{where}.depth"),
        observations=tuple(rows),
    )


def _support_envelope(value: object, where: str) -> SupportEnvelope:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "quotient_fingerprint",
            "claim_fingerprint",
            "evidence_image_fingerprint",
            "evidence_fingerprint",
            "depth",
            "block_supports",
            "observations",
        ),
        where,
    )
    if record["schema"] != "replaymark.support-envelope.deterministic.v1":
        raise ContractDecodeError(
            f"unsupported support-envelope schema: {record['schema']!r}"
        )
    block_rows = []
    for i, item in enumerate(_list(record["block_supports"], f"{where}.block_supports")):
        row_where = f"{where}.block_supports[{i}]"
        row = _mapping(item, row_where)
        _exact(row, ("q_block", "support"), row_where)
        block_rows.append(
            BlockSupport(
                q_block=_string(row["q_block"], f"{row_where}.q_block"),
                support=tuple(
                    _action(action, f"{row_where}.support[{j}]")
                    for j, action in enumerate(
                        _list(row["support"], f"{row_where}.support")
                    )
                ),
            )
        )

    obs_rows = []
    for i, item in enumerate(_list(record["observations"], f"{where}.observations")):
        row_where = f"{where}.observations[{i}]"
        row = _mapping(item, row_where)
        _exact(
            row,
            ("token", "q_blocks", "guaranteed_support", "possible_support"),
            row_where,
        )
        obs_rows.append(
            ObservationSupportEnvelope(
                token=_string(row["token"], f"{row_where}.token"),
                q_blocks=_string_tuple(row["q_blocks"], f"{row_where}.q_blocks"),
                guaranteed_support=tuple(
                    _action(action, f"{row_where}.guaranteed_support[{j}]")
                    for j, action in enumerate(
                        _list(
                            row["guaranteed_support"],
                            f"{row_where}.guaranteed_support",
                        )
                    )
                ),
                possible_support=tuple(
                    _action(action, f"{row_where}.possible_support[{j}]")
                    for j, action in enumerate(
                        _list(
                            row["possible_support"],
                            f"{row_where}.possible_support",
                        )
                    )
                ),
            )
        )

    return SupportEnvelope(
        schema_version=_string(record["schema"], f"{where}.schema"),
        quotient_fingerprint=_string(
            record["quotient_fingerprint"], f"{where}.quotient_fingerprint"
        ),
        claim_fingerprint=_string(
            record["claim_fingerprint"], f"{where}.claim_fingerprint"
        ),
        evidence_image_fingerprint=_string(
            record["evidence_image_fingerprint"],
            f"{where}.evidence_image_fingerprint",
        ),
        evidence_fingerprint=_string(
            record["evidence_fingerprint"], f"{where}.evidence_fingerprint"
        ),
        depth=_integer(record["depth"], f"{where}.depth"),
        block_supports=tuple(block_rows),
        observations=tuple(obs_rows),
    )


def _predictive_witness(value: object, where: str) -> PredictiveContinuationWitness:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "quotient_fingerprint",
            "claim_fingerprint",
            "compiled_depth",
            "left_state",
            "right_state",
            "first_separation_depth",
            "continuation_word",
            "left_trace",
            "right_trace",
        ),
        where,
    )
    if record["schema"] != "replaymark.predictive-continuation-witness.v1":
        raise ContractDecodeError(
            f"unsupported predictive-witness schema: {record['schema']!r}"
        )
    try:
        return PredictiveContinuationWitness(
            schema_version=_string(record["schema"], f"{where}.schema"),
            quotient_fingerprint=_string(
                record["quotient_fingerprint"], f"{where}.quotient_fingerprint"
            ),
            claim_fingerprint=_string(
                record["claim_fingerprint"], f"{where}.claim_fingerprint"
            ),
            compiled_depth=_integer(
                record["compiled_depth"], f"{where}.compiled_depth"
            ),
            left_state=_string(record["left_state"], f"{where}.left_state"),
            right_state=_string(record["right_state"], f"{where}.right_state"),
            first_separation_depth=_integer(
                record["first_separation_depth"],
                f"{where}.first_separation_depth",
            ),
            continuation_word=_string_tuple(
                record["continuation_word"], f"{where}.continuation_word"
            ),
            left_trace=tuple(
                _action(action, f"{where}.left_trace[{i}]")
                for i, action in enumerate(
                    _list(record["left_trace"], f"{where}.left_trace")
                )
            ),
            right_trace=tuple(
                _action(action, f"{where}.right_trace[{i}]")
                for i, action in enumerate(
                    _list(record["right_trace"], f"{where}.right_trace")
                )
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def _witness_index(value: object, where: str) -> PredictiveWitnessIndex:
    record = _mapping(value, where)
    _exact(
        record,
        (
            "schema",
            "quotient_fingerprint",
            "claim_fingerprint",
            "depth",
            "decision_states",
            "continuation_alphabet",
            "witnesses",
        ),
        where,
    )
    if record["schema"] != "replaymark.predictive-continuation-witness-index.v1":
        raise ContractDecodeError(
            f"unsupported predictive-witness-index schema: {record['schema']!r}"
        )
    witnesses = tuple(
        _predictive_witness(item, f"{where}.witnesses[{i}]")
        for i, item in enumerate(_list(record["witnesses"], f"{where}.witnesses"))
    )
    try:
        return PredictiveWitnessIndex(
            schema_version=_string(record["schema"], f"{where}.schema"),
            quotient_fingerprint=_string(
                record["quotient_fingerprint"], f"{where}.quotient_fingerprint"
            ),
            claim_fingerprint=_string(
                record["claim_fingerprint"], f"{where}.claim_fingerprint"
            ),
            depth=_integer(record["depth"], f"{where}.depth"),
            decision_states=_string_tuple(
                record["decision_states"], f"{where}.decision_states"
            ),
            continuation_alphabet=_string_tuple(
                record["continuation_alphabet"],
                f"{where}.continuation_alphabet",
            ),
            witnesses=witnesses,
        )
    except (TypeError, ValueError) as exc:
        raise ContractDecodeError(f"invalid {where}: {exc}") from exc


def load_compiled_contract(data: bytes) -> ExplicitCompiledContract:
    """Load one exact canonical ExplicitCompiledContract byte string.

    A semantically equivalent but differently formatted JSON document is rejected.
    This makes the artifact fingerprint unambiguous and ensures a successful load
    is also a canonicality check.
    """

    if not isinstance(data, bytes):
        raise TypeError("compiled contract loader requires bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractDecodeError("compiled contract is not valid UTF-8") from exc

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_constant,
        )
    except ContractDecodeError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractDecodeError(f"invalid JSON: {exc}") from exc

    root = _mapping(decoded, "contract")
    _exact(root, ("schema", "compiler_id", "manifest", "artifacts"), "contract")
    if root["schema"] != "replaymark.compiled-contract.explicit.v1":
        raise ContractDecodeError(
            f"unsupported concrete contract schema: {root['schema']!r}"
        )
    if root["compiler_id"] != "replaymark.reference-packager.explicit.v1":
        raise ContractDecodeError(
            f"unsupported concrete compiler id: {root['compiler_id']!r}"
        )

    manifest = _mapping(root["manifest"], "contract.manifest")
    manifest_keys = (
        "claim_fingerprint",
        "target_provider_fingerprint",
        "target_semantic_digest",
        "target_snapshot_fingerprint",
        "evidence_semantics_fingerprint",
        "evidence_relation_fingerprint",
        "quotient_fingerprint",
        "support_envelope_fingerprint",
        "predictive_witness_index_fingerprint",
    )
    _exact(manifest, manifest_keys, "contract.manifest")
    for key in manifest_keys:
        _string(manifest[key], f"contract.manifest.{key}")

    artifacts = _mapping(root["artifacts"], "contract.artifacts")
    _exact(
        artifacts,
        (
            "target_snapshot",
            "bounded_quotient",
            "evidence_semantics",
            "evidence_image",
            "support_envelope",
            "predictive_witness_index",
        ),
        "contract.artifacts",
    )

    try:
        contract = package_compiled_contract(
            target_snapshot=_target_snapshot(
                artifacts["target_snapshot"], "contract.artifacts.target_snapshot"
            ),
            quotient=_bounded_quotient(
                artifacts["bounded_quotient"], "contract.artifacts.bounded_quotient"
            ),
            evidence_semantics=_compiled_evidence(
                artifacts["evidence_semantics"],
                "contract.artifacts.evidence_semantics",
            ),
            evidence_image=_evidence_image(
                artifacts["evidence_image"], "contract.artifacts.evidence_image"
            ),
            support_envelope=_support_envelope(
                artifacts["support_envelope"],
                "contract.artifacts.support_envelope",
            ),
            predictive_witness_index=_witness_index(
                artifacts["predictive_witness_index"],
                "contract.artifacts.predictive_witness_index",
            ),
        )
    except ContractDecodeError:
        raise
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ContractDecodeError(
            f"contract artifact binding validation failed: {exc}"
        ) from exc

    expected_manifest = contract.canonical_record()["manifest"]
    if manifest != expected_manifest:
        raise ContractDecodeError(
            "contract manifest does not equal identities recomputed from embedded artifacts"
        )
    canonical = contract.canonical_bytes()
    if canonical != data:
        raise NonCanonicalContractError(
            "contract JSON is not the exact canonical encoding of its semantic artifacts"
        )
    return contract


__all__ = (
    "ContractDecodeError",
    "DuplicateJSONKeyError",
    "NonCanonicalContractError",
    "load_compiled_contract",
)
