from __future__ import annotations

"""High-assurance gate for concrete ReplayMark CompiledContract packaging."""

import argparse
from dataclasses import FrozenInstanceError
from itertools import product
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import replaymark
from replaymark.compiled_contract import (
    ArtifactBindingError,
    ExplicitCompiledContract,
    compile_explicit_contract,
    package_compiled_contract,
)
from replaymark.compiled_contract_codec import (
    ContractDecodeError,
    DuplicateJSONKeyError,
    NonCanonicalContractError,
    load_compiled_contract,
)
from replaymark.contracts import ClaimSpec, CompiledContract, EvidenceSpec, ProjectedAction, Verdict
from replaymark.evidence_image import compile_evidence_image
from replaymark.predictive_witness import compile_predictive_witnesses
from replaymark.rstar import ReuseDisposition
from replaymark.support_envelope import compile_support_envelope
from replaymark.target_provenance import observe_target_semantics
from replaymark_oracle.rstar_oracle import definition_rstar
from replaymark_verification.evidence_models import model_from_expected_inverse
from replaymark_verification.models import BetterThermostatFrozenModel, TableTargetModel


EXPECTED_ROOT_EXPORTS = (
    "ClaimSpec",
    "TargetModel",
    "EvidenceSpec",
    "ProjectedAction",
    "CompiledContract",
    "Verdict",
)


def _action(operation: str, **extra) -> ProjectedAction:
    dimensions = {"operation": operation}
    dimensions.update(extra)
    return ProjectedAction.from_mapping(dimensions)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def thermostat_contract_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec(
        "bt-concrete-contract",
        ("operation",),
        2,
        "consequential-preset-service-action",
    )
    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    non_target_home = target.encode(True, False, False, "sleep")
    at_target_home = target.encode(True, False, False, "home")
    expected = EvidenceSpec(
        "bt-concrete-contract-evidence",
        (
            ("n2b-pair", (n2a, n2b)),
            ("mixed", (non_target_home, at_target_home)),
            ("strong-home", (non_target_home,)),
        ),
    )
    observation_model = model_from_expected_inverse(target, expected)

    contract = compile_explicit_contract(
        target,
        claim,
        observation_model,
        evidence_id=expected.evidence_id,
    )
    assert isinstance(contract, ExplicitCompiledContract)
    assert isinstance(contract, CompiledContract)
    assert tuple(replaymark.__all__) == EXPECTED_ROOT_EXPORTS
    assert [contract.quotient.block_count(d) for d in range(3)] == [5, 14, 16]

    away = _action("SET_AWAY")
    home = _action("SET_HOME")
    no_action = _action("NO_ACTION")

    assert contract.adjudicate("n2b-pair", away).verdict is Verdict.VALID
    assert contract.certify_reuse("n2b-pair", away).disposition is ReuseDisposition.REUSE
    assert contract.reuse_counterexample_world("n2b-pair", away) is None

    mixed_home = contract.adjudicate("mixed", home)
    mixed_none = contract.adjudicate("mixed", no_action)
    mixed_away = contract.adjudicate("mixed", away)
    assert mixed_home.verdict is Verdict.UNRESOLVED
    assert mixed_none.verdict is Verdict.UNRESOLVED
    assert mixed_away.verdict is Verdict.INVALID
    assert contract.certify_reuse("mixed", home).disposition is ReuseDisposition.DO_NOT_REUSE
    assert contract.certify_reuse("mixed", away).disposition is ReuseDisposition.DO_NOT_REUSE

    counterexample = contract.reuse_counterexample_world("mixed", home)
    assert counterexample in contract.compatible_worlds("mixed")
    assert counterexample is not None
    raw = observe_target_semantics(target)
    raw_support = {
        claim.project(action)
        for action, _post, mass in raw.current_law(counterexample)
        if mass > 0
    }
    assert claim.project(home) not in raw_support

    strong = contract.adjudicate("strong-home", home)
    assert strong.verdict is Verdict.VALID
    assert contract.certify_reuse("strong-home", home).reuse_certified
    assert contract.reuse_counterexample_world("strong-home", home) is None

    rich_home = _action("SET_HOME", variant="historical", delay_ms=999)
    assert contract.adjudicate("strong-home", rich_home).canonical_bytes() == strong.canonical_bytes()
    assert contract.certify_reuse("strong-home", rich_home).canonical_bytes() == (
        contract.certify_reuse("strong-home", home).canonical_bytes()
    )

    witness = contract.predictive_witness(n2a, n2b)
    assert witness is not None
    assert witness.first_separation_depth == 1
    assert witness.witness_length == 1
    assert witness.quotient_fingerprint == contract.quotient_fingerprint
    assert contract.quotient.equivalent(n2a, n2b, depth=0)
    assert not contract.quotient.equivalent(n2a, n2b, depth=1)

    adj = contract.adjudicate("mixed", home)
    decision = contract.certify_reuse("mixed", home)
    assert adj.support_envelope_fingerprint == contract.support_envelope_fingerprint
    assert adj.claim_fingerprint == contract.claim_fingerprint
    assert decision.adjudication_fingerprint == adj.fingerprint()
    assert decision.support_envelope_fingerprint == contract.support_envelope_fingerprint

    encoded = contract.canonical_bytes()
    loaded = load_compiled_contract(encoded)
    assert loaded.canonical_bytes() == encoded
    assert loaded.fingerprint() == contract.fingerprint()
    assert loaded.certify_reuse("mixed", home).canonical_bytes() == decision.canonical_bytes()
    assert loaded.predictive_witness(n2a, n2b).canonical_bytes() == witness.canonical_bytes()

    target2 = BetterThermostatFrozenModel()
    second = compile_explicit_contract(
        target2,
        claim,
        model_from_expected_inverse(target2, expected),
        evidence_id=expected.evidence_id,
    )
    assert second.canonical_bytes() == encoded
    assert second.fingerprint() == contract.fingerprint()

    return {
        "q_counts": [contract.quotient.block_count(d) for d in range(3)],
        "n2b_reuse": contract.certify_reuse("n2b-pair", away).disposition.value,
        "mixed_home_verdict": mixed_home.verdict.value,
        "mixed_away_verdict": mixed_away.verdict.value,
        "strong_home_verdict": strong.verdict.value,
        "predictive_witness_length": witness.witness_length,
        "canonical_roundtrip": True,
        "independent_compile_byte_determinism": True,
        "contract_fingerprint": contract.fingerprint(),
    }


class ExplodingTableTarget(TableTargetModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.explode = False

    def _check(self):
        if self.explode:
            raise AssertionError("sealed contract called its source TargetModel at runtime")

    @property
    def fingerprint(self):
        self._check()
        return super().fingerprint

    @property
    def decision_states(self):
        self._check()
        return super().decision_states

    @property
    def continuation_alphabet(self):
        self._check()
        return super().continuation_alphabet

    def current_distribution(self, decision_state: str):
        self._check()
        return super().current_distribution(decision_state)

    def advance_distribution(self, post_state: str, continuation: str):
        self._check()
        return super().advance_distribution(post_state, continuation)


def provider_free_runtime_gate() -> dict[str, object]:
    target = ExplodingTableTarget(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    claim = ClaimSpec("provider-free-runtime", ("operation",), 1, "event")
    expected = EvidenceSpec(
        "provider-free-evidence",
        (("both", ("s0", "s1")), ("left", ("s0",))),
    )
    model = model_from_expected_inverse(target, expected)
    contract = compile_explicit_contract(
        target, claim, model, evidence_id=expected.evidence_id
    )
    baseline = contract.canonical_bytes()
    target.explode = True

    assert contract.compatible_worlds("both") == ("s0", "s1")
    assert contract.adjudicate("both", _action("A")).verdict is Verdict.UNRESOLVED
    assert not contract.certify_reuse("both", _action("A")).reuse_certified
    assert contract.reuse_counterexample_world("both", _action("A")) == "s1"
    assert contract.predictive_witness("s0", "s1") is not None
    assert contract.canonical_bytes() == baseline
    loaded = load_compiled_contract(baseline)
    assert loaded.fingerprint() == contract.fingerprint()

    return {
        "target_provider_calls_after_compile": 0,
        "runtime_provider_free": True,
        "standalone_reload_provider_free": True,
    }


def tamper_and_fail_closed_gate() -> dict[str, object]:
    target = TableTargetModel(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    claim = ClaimSpec("tamper-gate", ("operation",), 1, "event")
    expected = EvidenceSpec(
        "tamper-evidence",
        (("both", ("s0", "s1")), ("s0-only", ("s0",))),
    )
    model = model_from_expected_inverse(target, expected)
    contract = compile_explicit_contract(
        target, claim, model, evidence_id=expected.evidence_id
    )
    encoded = contract.canonical_bytes()

    try:
        contract.schema_version = "forged"
    except (FrozenInstanceError, AttributeError):
        frozen = True
    else:
        raise AssertionError("ExplicitCompiledContract must be immutable")

    try:
        contract.compatible_worlds("unknown")
    except KeyError:
        unknown_token_rejected = True
    else:
        raise AssertionError("unknown evidence token must fail closed")

    try:
        contract.predictive_witness("s0", "unknown")
    except KeyError:
        unknown_world_rejected = True
    else:
        raise AssertionError("unknown predictive world must fail closed")

    root = json.loads(encoded)
    root["manifest"]["target_semantic_digest"] = "0" * 64
    try:
        load_compiled_contract(_canonical_json(root))
    except ContractDecodeError:
        forged_manifest_rejected = True
    else:
        raise AssertionError("forged manifest must be rejected")

    root = json.loads(encoded)
    row = root["artifacts"]["support_envelope"]["observations"][0]
    row["possible_support"] = []
    try:
        load_compiled_contract(_canonical_json(root))
    except ContractDecodeError:
        forged_support_rejected = True
    else:
        raise AssertionError("forged support envelope must be rejected")

    pretty = json.dumps(json.loads(encoded), indent=2, sort_keys=True).encode("utf-8")
    try:
        load_compiled_contract(pretty)
    except NonCanonicalContractError:
        noncanonical_rejected = True
    else:
        raise AssertionError("noncanonical JSON encoding must be rejected")

    duplicate = (
        b'{"schema":"replaymark.compiled-contract.explicit.v1",'
        b'"schema":"replaymark.compiled-contract.explicit.v1"}'
    )
    try:
        load_compiled_contract(duplicate)
    except DuplicateJSONKeyError:
        duplicate_key_rejected = True
    else:
        raise AssertionError("duplicate JSON keys must be rejected before construction")

    root = json.loads(encoded)
    root["unexpected"] = True
    try:
        load_compiled_contract(_canonical_json(root))
    except ContractDecodeError:
        extra_field_rejected = True
    else:
        raise AssertionError("unknown root fields must be rejected")

    root = json.loads(encoded)
    root["schema"] = "replaymark.compiled-contract.explicit.v999"
    try:
        load_compiled_contract(_canonical_json(root))
    except ContractDecodeError:
        foreign_schema_rejected = True
    else:
        raise AssertionError("unknown concrete schema must be rejected")

    shallow_image = compile_evidence_image(
        contract.quotient, contract.evidence_semantics, depth=0
    )
    shallow_support = compile_support_envelope(contract.quotient, shallow_image)
    try:
        package_compiled_contract(
            target_snapshot=contract.target_snapshot,
            quotient=contract.quotient,
            evidence_semantics=contract.evidence_semantics,
            evidence_image=shallow_image,
            support_envelope=shallow_support,
            predictive_witness_index=contract.predictive_witness_index,
        )
    except ArtifactBindingError:
        shallow_horizon_rejected = True
    else:
        raise AssertionError("concrete contract must package exactly the claim horizon H")

    shallow_witness = compile_predictive_witnesses(contract.quotient, depth=0)
    try:
        package_compiled_contract(
            target_snapshot=contract.target_snapshot,
            quotient=contract.quotient,
            evidence_semantics=contract.evidence_semantics,
            evidence_image=contract.evidence_image,
            support_envelope=contract.support_envelope,
            predictive_witness_index=shallow_witness,
        )
    except ArtifactBindingError:
        shallow_witness_rejected = True
    else:
        raise AssertionError("contract must reject a non-H predictive witness index")

    policy_names = ("execute", "regenerate", "fallback", "retry", "abort", "refine_evidence")
    assert all(not hasattr(contract, name) for name in policy_names)

    return {
        "immutable": frozen,
        "unknown_token_rejected": unknown_token_rejected,
        "unknown_world_rejected": unknown_world_rejected,
        "forged_manifest_rejected": forged_manifest_rejected,
        "forged_support_rejected": forged_support_rejected,
        "noncanonical_encoding_rejected": noncanonical_rejected,
        "duplicate_json_key_rejected": duplicate_key_rejected,
        "unknown_field_rejected": extra_field_rejected,
        "foreign_schema_rejected": foreign_schema_rejected,
        "shallower_evidence_image_rejected": shallow_horizon_rejected,
        "shallower_witness_index_rejected": shallow_witness_rejected,
        "no_execution_policy_surface": True,
    }


def exhaustive_two_state_gate() -> dict[str, object]:
    outputs = ("A", "B")
    continuations = ("0", "1")
    claim = ClaimSpec("packaging-exhaustive", ("operation",), 2, "event")
    expected = EvidenceSpec(
        "packaging-all-subsets",
        (
            ("e1", ("s0",)),
            ("e2", ("s1",)),
            ("e3", ("s0", "s1")),
        ),
    )
    actions = {name: _action(name) for name in outputs}
    machine_count = pair_count = roundtrips = witness_checks = 0
    verdict_counts = {verdict.value: 0 for verdict in Verdict}
    start = time.perf_counter()

    for output_assignment in product(outputs, repeat=2):
        for flat_next in product(range(2), repeat=4):
            target = TableTargetModel(
                outputs=tuple(output_assignment),
                continuations=continuations,
                next_state=(
                    (flat_next[0], flat_next[1]),
                    (flat_next[2], flat_next[3]),
                ),
            )
            model = model_from_expected_inverse(target, expected)
            contract = compile_explicit_contract(
                target, claim, model, evidence_id=expected.evidence_id
            )

            loaded = load_compiled_contract(contract.canonical_bytes())
            assert loaded.fingerprint() == contract.fingerprint()
            roundtrips += 1

            for token, compatible in expected.observations:
                for name, action in actions.items():
                    adjudication = contract.adjudicate(token, action)
                    decision = contract.certify_reuse(token, action)
                    oracle = definition_rstar(target, claim, expected, token, action)
                    assert decision.disposition.value == oracle.disposition.value
                    assert contract.reuse_counterexample_world(
                        token, action
                    ) == oracle.maximality_counterexample

                    supporting = tuple(
                        world
                        for world in compatible
                        if output_assignment[int(world[1:])] == name
                    )
                    expected_verdict = (
                        Verdict.VALID
                        if len(supporting) == len(compatible)
                        else Verdict.INVALID
                        if not supporting
                        else Verdict.UNRESOLVED
                    )
                    assert adjudication.verdict is expected_verdict
                    verdict_counts[adjudication.verdict.value] += 1
                    pair_count += 1

            witness = contract.predictive_witness("s0", "s1")
            equivalent = contract.quotient.equivalent("s0", "s1")
            assert (witness is None) == equivalent
            if witness is not None:
                assert witness.quotient_fingerprint == contract.quotient_fingerprint
                assert witness.claim_fingerprint == contract.claim_fingerprint
            witness_checks += 1
            machine_count += 1

    assert machine_count == 64
    assert pair_count == 384
    assert roundtrips == 64
    assert witness_checks == 64

    return {
        "complete_labeled_two_state_machines": machine_count,
        "contract_vs_raw_oracle_pairs": pair_count,
        "canonical_roundtrips": roundtrips,
        "predictive_witness_completeness_checks": witness_checks,
        "verdict_counts": verdict_counts,
        "elapsed_seconds": round(time.perf_counter() - start, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    report = {
        "schema": "replaymark.compiled-contract.explicit.packaging-gate.v1",
        "thermostat": thermostat_contract_gate(),
        "provider_free_runtime": provider_free_runtime_gate(),
        "tamper_fail_closed": tamper_and_fail_closed_gate(),
        "exhaustive_two_state": exhaustive_two_state_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
