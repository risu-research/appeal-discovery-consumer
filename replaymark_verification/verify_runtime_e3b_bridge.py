from __future__ import annotations

import argparse
import ast
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.compiled_contract import compile_explicit_contract
from replaymark.contracts import ClaimSpec, EvidenceSpec, Verdict
from replaymark.rstar import ReuseDisposition
from replaymark.runtime_e3b_action import E3B_ACTION_CAPTURE_POINT, E3B_RAW_ACTION_SCHEMA
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
    e3b_shadow_bridge_rule_record,
)
from replaymark.runtime_e3b_correlation import (
    E3bTaskCorrelationError,
    correlate_e3b_runtime_pair,
)
from replaymark.runtime_e3b_observation import E3B_RAW_OBSERVATION_SCHEMA
from replaymark.runtime_realization import RealizationError
from replaymark_verification.evidence_models import model_from_expected_inverse
from replaymark_verification.models import TableTargetModel


def _obs(task: int = 7, confirmed: bool = True) -> dict[str, object]:
    events = []
    if confirmed:
        events = [{
            "event_id": "state-on",
            "device": f"bridge-{task}-a",
            "on": True,
            "recv_mono_ns": 150,
            "clock_domain": "mono:bridge",
        }]
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": "mono:bridge",
        "expected_device": f"bridge-{task}-a",
        "command_publish_mono_ns": 100,
        "verify_deadline_mono_ns": 200,
        "closed_at_mono_ns": 200,
        "events": events,
    }


def _action(task: int = 7) -> dict[str, object]:
    return {
        "schema": E3B_RAW_ACTION_SCHEMA,
        "capture_point": E3B_ACTION_CAPTURE_POINT,
        "clock_domain": "mono:bridge",
        "publish_mono_ns": 220,
        "topic": f"agentmark/bridge-{task}-b/command",
        "payload_utf8": '{"on": true}',
        "qos": 1,
        "retain": False,
        "properties": None,
    }


def _contract(ambiguous: bool = False):
    target = TableTargetModel(
        outputs=("ACT2", "VERIFY"),
        continuations=("tick",),
        next_state=((0,), (1,)),
    )
    claim = ClaimSpec(
        "e3b-shadow-bridge-verification",
        ("operation",),
        0,
        "controller-decision",
    )
    confirmed = ("s0", "s1") if ambiguous else ("s0",)
    evidence = EvidenceSpec(
        "e3b-shadow-bridge-evidence",
        (
            ("confirmed_by_deadline", confirmed),
            ("not_visible_by_deadline", ("s1",)),
        ),
    )
    return compile_explicit_contract(
        target,
        claim,
        model_from_expected_inverse(target, evidence),
        evidence_id=evidence.evidence_id,
    )


def _chain(contract, *, confirmed: bool = True, task: int = 7):
    pair = correlate_e3b_runtime_pair(_obs(task, confirmed), _action(task))
    return pair, certify_e3b_shadow_reuse(contract, pair)


def semantic_passthrough_gate() -> dict[str, object]:
    separated = _contract()
    valid_pair, valid = _chain(separated, confirmed=True)
    invalid_pair, invalid = _chain(separated, confirmed=False)
    ambiguous = _contract(ambiguous=True)
    unresolved_pair, unresolved = _chain(ambiguous, confirmed=True)

    assert valid.semantic_certificate.adjudication.verdict is Verdict.VALID
    assert valid.semantic_certificate.reuse_decision.disposition is ReuseDisposition.REUSE
    assert invalid.semantic_certificate.adjudication.verdict is Verdict.INVALID
    assert invalid.semantic_certificate.reuse_decision.disposition is ReuseDisposition.DO_NOT_REUSE
    assert unresolved.semantic_certificate.adjudication.verdict is Verdict.UNRESOLVED
    assert unresolved.semantic_certificate.reuse_decision.disposition is ReuseDisposition.DO_NOT_REUSE

    for contract, pair, chained in (
        (separated, valid_pair, valid),
        (separated, invalid_pair, invalid),
        (ambiguous, unresolved_pair, unresolved),
    ):
        token = pair.observation.evidence_token
        action = pair.historical_action.action
        expected_adj = contract.adjudicate(token, action)
        expected_reuse = contract.certify_reuse(token, action)
        semantic = chained.semantic_certificate
        assert semantic.contract_fingerprint == contract.fingerprint()
        assert semantic.claim_fingerprint == contract.claim_fingerprint
        assert semantic.adjudication.canonical_bytes() == expected_adj.canonical_bytes()
        assert semantic.reuse_decision.canonical_bytes() == expected_reuse.canonical_bytes()
        assert semantic.observation.fingerprint() == pair.observation.fingerprint()
        assert semantic.historical_action.fingerprint() == pair.historical_action.fingerprint()

    return {
        "valid": valid.semantic_certificate.adjudication.verdict.value,
        "invalid": invalid.semantic_certificate.adjudication.verdict.value,
        "unresolved": unresolved.semantic_certificate.adjudication.verdict.value,
        "exact_existing_contract_outputs_preserved": True,
    }


def proof_chain_gate() -> dict[str, object]:
    contract = _contract()
    pair7, chained7 = _chain(contract, task=7)
    pair8, _ = _chain(contract, task=8)

    assert chained7.schema_version == E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA
    assert chained7.bridge_id == E3B_SHADOW_BRIDGE_ID
    assert chained7.bridge_semantic_digest == E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST
    assert chained7.correlated_pair.correlation.fingerprint() == pair7.correlation.fingerprint()

    try:
        E3bShadowRuntimeReuseCertificate(
            schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
            bridge_id=E3B_SHADOW_BRIDGE_ID,
            bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
            contract_fingerprint=chained7.contract_fingerprint,
            claim_fingerprint=chained7.claim_fingerprint,
            correlated_pair=pair8,
            semantic_certificate=chained7.semantic_certificate,
        )
    except ValueError:
        detached_proof_rejected = True
    else:
        raise AssertionError("same-task proof detached from semantic certificate")

    try:
        correlate_e3b_runtime_pair(_obs(7), _action(8))
    except E3bTaskCorrelationError:
        cross_task_rejected = True
    else:
        raise AssertionError("cross-task pair reached the semantic bridge")

    malformed = _obs()
    del malformed["events"]
    try:
        correlate_e3b_runtime_pair(malformed, _action())
    except RealizationError:
        realization_short_circuit = True
    else:
        raise AssertionError("realization failure did not short-circuit")

    for bad in (object(), pair7.observation, pair7.historical_action):
        try:
            certify_e3b_shadow_reuse(contract, bad)  # type: ignore[arg-type]
        except TypeError:
            pass
        else:
            raise AssertionError("bridge accepted an uncorrelated input type")

    tampered_contract = replace(
        chained7.semantic_certificate,
        contract_fingerprint="0" * 64,
    )
    try:
        replace(chained7, semantic_certificate=tampered_contract)
    except ValueError:
        contract_tamper_rejected = True
    else:
        raise AssertionError("contract binding tamper was accepted")

    try:
        replace(chained7.semantic_certificate, claim_fingerprint="0" * 64)
    except ValueError:
        claim_tamper_rejected = True
    else:
        raise AssertionError("claim binding tamper was accepted")

    return {
        "detached_same_task_proof_rejected": detached_proof_rejected,
        "cross_task_rejected_pre_semantics": cross_task_rejected,
        "realization_failure_short_circuits": realization_short_circuit,
        "contract_binding_tamper_rejected": contract_tamper_rejected,
        "claim_binding_tamper_rejected": claim_tamper_rejected,
        "chained_certificate_fingerprint": chained7.fingerprint(),
    }


def static_boundary_gate() -> dict[str, object]:
    source = (ROOT / "replaymark" / "runtime_e3b_bridge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)

    forbidden_modules = (
        "adjudicator",
        "rstar",
        "support_envelope",
        "evidence_image",
        "evidence_semantics",
        "q_compiler",
        "agentmark_e3b_lab",
    )
    assert not any(fragment in module for fragment in forbidden_modules for module in modules)

    attrs = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
    assert attrs.count("adjudicate") == 1
    assert attrs.count("certify_reuse") == 1
    forbidden_calls = {
        "publish",
        "execute",
        "fallback",
        "regenerate",
        "adjudicate_support",
        "maximal_certified_reuse",
    }
    assert not (set(attrs) & forbidden_calls)

    rule = e3b_shadow_bridge_rule_record()
    assert rule["semantic_reimplementation"] is False
    assert rule["execution"] == {
        "block": False,
        "fallback": False,
        "publish": False,
        "regenerate": False,
    }
    return {
        "semantic_implementation_imports": 0,
        "explicit_contract_adjudicate_calls": 1,
        "explicit_contract_certify_reuse_calls": 1,
        "execution_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = {
        "schema": "replaymark.runtime-e3b-shadow-bridge-gate.v1",
        "verdict": "PASS",
        "semantic_passthrough": semantic_passthrough_gate(),
        "proof_chain": proof_chain_gate(),
        "static_boundary": static_boundary_gate(),
        "runtime_reuse_bridge": "PASS",
        "execution_policy": "NOT_IMPLEMENTED",
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
