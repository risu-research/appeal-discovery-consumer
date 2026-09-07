from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.compiled_contract import compile_explicit_contract
from replaymark.contracts import ClaimSpec, EvidenceSpec, Verdict
from replaymark.execution_admission import (
    ExecutionAdmissionDisposition,
    execution_admission_rule_record,
)
from replaymark.runtime_e3b_action import E3B_ACTION_CAPTURE_POINT, E3B_RAW_ACTION_SCHEMA
from replaymark.runtime_e3b_bridge import certify_e3b_shadow_reuse
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_e3b_execution_gate import (
    E3bCertifiedExecutionGate,
    E3bExecutionGateError,
    E3bExecutionGateFailureCode,
    e3b_execution_gate_rule_record,
    validate_e3b_execution_certificate,
)
from replaymark.runtime_e3b_observation import E3B_RAW_OBSERVATION_SCHEMA
from replaymark_oracle.execution_admission_oracle import expected_execution_admission
from replaymark_verification.evidence_models import model_from_expected_inverse
from replaymark_verification.models import TableTargetModel


class _PublishInfo:
    def __init__(self) -> None:
        self.wait_calls = 0

    def wait_for_publish(self, timeout: float | None = None) -> None:
        if timeout != 5:
            raise AssertionError("execution gate changed the frozen wait timeout")
        self.wait_calls += 1


class _RecordingClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []
        self._lock = threading.Lock()

    def publish(
        self,
        topic: object,
        payload: object = None,
        qos: object = 0,
        retain: object = False,
        properties: object = None,
    ):
        with self._lock:
            self.calls.append(
                {
                    "topic": topic,
                    "payload": payload,
                    "qos": qos,
                    "retain": retain,
                    "properties": properties,
                }
            )
        if self.fail:
            raise RuntimeError("injected sink failure")
        return _PublishInfo()


def _obs(task: int = 7, confirmed: bool = True) -> dict[str, object]:
    events: list[dict[str, object]] = []
    if confirmed:
        events.append(
            {
                "event_id": "state-on",
                "device": f"s1-{task}-a",
                "on": True,
                "recv_mono_ns": 150,
                "clock_domain": "mono:s1",
            }
        )
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": "mono:s1",
        "expected_device": f"s1-{task}-a",
        "command_publish_mono_ns": 100,
        "verify_deadline_mono_ns": 200,
        "closed_at_mono_ns": 200,
        "events": events,
    }


def _action(task: int = 7) -> dict[str, object]:
    return {
        "schema": E3B_RAW_ACTION_SCHEMA,
        "capture_point": E3B_ACTION_CAPTURE_POINT,
        "clock_domain": "mono:s1",
        "publish_mono_ns": 220,
        "topic": f"agentmark/s1-{task}-b/command",
        "payload_utf8": '{"on": true}',
        "qos": 1,
        "retain": False,
        "properties": None,
    }


def _contract(*, ambiguous: bool = False):
    target = TableTargetModel(
        outputs=("ACT2", "VERIFY"),
        continuations=("tick",),
        next_state=((0,), (1,)),
    )
    claim = ClaimSpec(
        "s1-certified-execution-admission",
        ("operation",),
        0,
        "controller-decision",
    )
    confirmed = ("s0", "s1") if ambiguous else ("s0",)
    evidence = EvidenceSpec(
        "s1-certified-execution-evidence",
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


def _certificate(contract, *, confirmed: bool, task: int = 7):
    raw_obs = _obs(task=task, confirmed=confirmed)
    raw_action = _action(task=task)
    pair = correlate_e3b_runtime_pair(raw_obs, raw_action)
    cert = certify_e3b_shadow_reuse(contract, pair)
    return raw_obs, raw_action, cert


def policy_mapping_gate() -> dict[str, object]:
    separated = _contract()
    ambiguous = _contract(ambiguous=True)
    cases = [
        (separated, *_certificate(separated, confirmed=True), "ADMIT_REUSE"),
        (separated, *_certificate(separated, confirmed=False, task=8), "BLOCK_REUSE"),
        (ambiguous, *_certificate(ambiguous, confirmed=True, task=9), "BLOCK_REUSE"),
    ]
    observed: dict[str, str] = {}
    for contract, raw_obs, raw_action, cert, expected in cases:
        validated, parsed = validate_e3b_execution_certificate(
            contract,
            raw_obs,
            raw_action,
            cert,
        )
        semantic = cert.semantic_certificate
        oracle = expected_execution_admission(
            certificate_exact=True,
            verdict=semantic.adjudication.verdict.value,
            reuse_disposition=semantic.reuse_decision.disposition.value,
        )
        assert oracle.outcome == expected
        assert validated.admission.disposition.value == expected
        assert parsed.fingerprint() == validated.action_raw_digest
        observed[semantic.adjudication.verdict.value] = expected

    assert observed == {
        "VALID": "ADMIT_REUSE",
        "INVALID": "BLOCK_REUSE",
        "UNRESOLVED": "BLOCK_REUSE",
    }
    return observed


def exact_dispatch_gate() -> dict[str, object]:
    contract = _contract()

    raw_obs, raw_action, cert = _certificate(contract, confirmed=True)
    client = _RecordingClient()
    gate = E3bCertifiedExecutionGate(client)
    receipt = gate.dispatch(contract, raw_obs, raw_action, cert)
    assert receipt.execution_disposition is ExecutionAdmissionDisposition.ADMIT_REUSE
    assert receipt.application_publish_invocations == 1
    assert receipt.wait_for_publish_invocations == 1
    assert len(client.calls) == 1
    assert client.calls[0] == {
        "topic": raw_action["topic"],
        "payload": raw_action["payload_utf8"],
        "qos": 1,
        "retain": False,
        "properties": None,
    }

    nobs, naction, ncert = _certificate(contract, confirmed=False, task=8)
    nclient = _RecordingClient()
    ngate = E3bCertifiedExecutionGate(nclient)
    nreceipt = ngate.dispatch(contract, nobs, naction, ncert)
    assert nreceipt.execution_disposition is ExecutionAdmissionDisposition.BLOCK_REUSE
    assert nreceipt.application_publish_invocations == 0
    assert nreceipt.wait_for_publish_invocations == 0
    assert nclient.calls == []

    ambiguous = _contract(ambiguous=True)
    uobs, uaction, ucert = _certificate(ambiguous, confirmed=True, task=9)
    uclient = _RecordingClient()
    ugate = E3bCertifiedExecutionGate(uclient)
    ureceipt = ugate.dispatch(ambiguous, uobs, uaction, ucert)
    assert ucert.semantic_certificate.adjudication.verdict is Verdict.UNRESOLVED
    assert ureceipt.execution_disposition is ExecutionAdmissionDisposition.BLOCK_REUSE
    assert uclient.calls == []

    return {
        "valid_delegate_calls": len(client.calls),
        "invalid_delegate_calls": len(nclient.calls),
        "unresolved_delegate_calls": len(uclient.calls),
        "exact_valid_publish_material": True,
    }


def validation_fail_closed_gate() -> dict[str, object]:
    contract = _contract()
    raw_obs, raw_action, cert = _certificate(contract, confirmed=True, task=7)
    _obs8, _action8, cert8 = _certificate(contract, confirmed=True, task=8)

    client = _RecordingClient()
    gate = E3bCertifiedExecutionGate(client)

    try:
        gate.dispatch(contract, raw_obs, raw_action, cert8)
    except E3bExecutionGateError as exc:
        assert exc.code is E3bExecutionGateFailureCode.CERTIFICATE_MISMATCH
    else:
        raise AssertionError("mismatched presented certificate reached execution")
    assert client.calls == []

    foreign = _contract(ambiguous=True)
    try:
        gate.dispatch(foreign, raw_obs, raw_action, cert)
    except E3bExecutionGateError as exc:
        assert exc.code is E3bExecutionGateFailureCode.CERTIFICATE_MISMATCH
    else:
        raise AssertionError("foreign-contract certificate reached execution")
    assert client.calls == []

    oracle = expected_execution_admission(
        certificate_exact=False,
        verdict="VALID",
        reuse_disposition="REUSE",
    )
    assert oracle.outcome == "REJECT_CERTIFICATE"

    return {
        "mismatched_certificate_rejected_before_sink": True,
        "foreign_contract_rejected_before_sink": True,
        "invalid_input_is_not_semantic_block": True,
    }


def single_use_gate() -> dict[str, object]:
    contract = _contract()
    raw_obs, raw_action, cert = _certificate(contract, confirmed=True)
    client = _RecordingClient()
    gate = E3bCertifiedExecutionGate(client)

    first = gate.dispatch(contract, raw_obs, raw_action, cert)
    assert first.execution_disposition is ExecutionAdmissionDisposition.ADMIT_REUSE
    try:
        gate.dispatch(contract, raw_obs, raw_action, cert)
    except E3bExecutionGateError as exc:
        assert exc.code is E3bExecutionGateFailureCode.DUPLICATE_CONSUMPTION
    else:
        raise AssertionError("same admission executed twice")
    assert len(client.calls) == 1
    assert gate.consumed_count == 1

    raw_obs2, raw_action2, cert2 = _certificate(contract, confirmed=True, task=11)
    concurrent_client = _RecordingClient()
    concurrent_gate = E3bCertifiedExecutionGate(concurrent_client)

    def worker() -> str:
        try:
            receipt = concurrent_gate.dispatch(contract, raw_obs2, raw_action2, cert2)
            return receipt.execution_disposition.value
        except E3bExecutionGateError as exc:
            if exc.code is E3bExecutionGateFailureCode.DUPLICATE_CONSUMPTION:
                return "DUPLICATE_CONSUMPTION"
            raise

    with ThreadPoolExecutor(max_workers=32) as pool:
        results = list(pool.map(lambda _i: worker(), range(32)))

    assert results.count("ADMIT_REUSE") == 1
    assert results.count("DUPLICATE_CONSUMPTION") == 31
    assert len(concurrent_client.calls) == 1
    assert concurrent_gate.consumed_count == 1

    return {
        "sequential_second_dispatch_rejected": True,
        "concurrent_callers": 32,
        "concurrent_admitted": 1,
        "concurrent_duplicate_rejections": 31,
        "application_publish_calls": len(concurrent_client.calls),
    }


def sink_failure_gate() -> dict[str, object]:
    contract = _contract()
    raw_obs, raw_action, cert = _certificate(contract, confirmed=True, task=13)
    client = _RecordingClient(fail=True)
    gate = E3bCertifiedExecutionGate(client)

    try:
        gate.dispatch(contract, raw_obs, raw_action, cert)
    except E3bExecutionGateError as exc:
        assert exc.code is E3bExecutionGateFailureCode.SINK_FAILURE
    else:
        raise AssertionError("injected sink failure was hidden")

    assert len(client.calls) == 1
    assert gate.consumed_count == 1

    try:
        gate.dispatch(contract, raw_obs, raw_action, cert)
    except E3bExecutionGateError as exc:
        assert exc.code is E3bExecutionGateFailureCode.DUPLICATE_CONSUMPTION
    else:
        raise AssertionError("failed side effect was automatically retried")
    assert len(client.calls) == 1

    return {
        "sink_failure_not_retried": True,
        "consumed_before_delegate": True,
        "fallback_invocations": 0,
    }


def static_boundary_gate() -> dict[str, object]:
    policy_path = ROOT / "replaymark" / "execution_admission.py"
    gate_path = ROOT / "replaymark" / "runtime_e3b_execution_gate.py"
    oracle_path = ROOT / "replaymark_oracle" / "execution_admission_oracle.py"

    policy_source = policy_path.read_text(encoding="utf-8")
    gate_source = gate_path.read_text(encoding="utf-8")
    oracle_source = oracle_path.read_text(encoding="utf-8")

    policy_tree = ast.parse(policy_source)
    gate_tree = ast.parse(gate_source)
    oracle_tree = ast.parse(oracle_source)

    oracle_imports: set[str] = set()
    for node in ast.walk(oracle_tree):
        if isinstance(node, ast.Import):
            oracle_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            oracle_imports.add(node.module)
    assert not any(name.startswith("replaymark") for name in oracle_imports)

    policy_attrs = {
        node.attr for node in ast.walk(policy_tree) if isinstance(node, ast.Attribute)
    }
    assert "adjudicate" not in policy_attrs
    assert "certify_reuse" not in policy_attrs
    assert "publish" not in policy_attrs

    sig = inspect.signature(E3bCertifiedExecutionGate.dispatch)
    forbidden_params = {
        "topic",
        "payload",
        "qos",
        "retain",
        "properties",
        "fallback",
        "regenerate",
        "retry",
        "action_override",
    }
    assert not (set(sig.parameters) & forbidden_params)

    policy_rule = execution_admission_rule_record()
    assert policy_rule["fallback"] is False
    assert policy_rule["regeneration"] is False
    assert policy_rule["retry"] is False

    gate_rule = e3b_execution_gate_rule_record()
    assert gate_rule["fallback"] is False
    assert gate_rule["regeneration"] is False
    assert gate_rule["dispatch"]["caller_action_override"] is False
    assert gate_rule["dispatch"]["automatic_retry"] is False
    assert gate_rule["durable_cross_process_deduplication"] is False
    assert gate_rule["broker_delivery_claim"] is False

    gate_attrs = [
        node.attr for node in ast.walk(gate_tree) if isinstance(node, ast.Attribute)
    ]
    assert gate_attrs.count("publish") == 1

    return {
        "independent_oracle_production_imports": 0,
        "policy_semantic_recomputations": 0,
        "policy_execution_calls": 0,
        "gate_publish_call_sites": 1,
        "caller_action_override_parameters": 0,
        "fallback_surface": 0,
        "automatic_retry_surface": 0,
        "durable_cross_process_exactly_once_claim": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = {
        "schema": "replaymark.gate-s1-certified-execution-admission.v1",
        "verdict": "PASS",
        "policy_mapping": policy_mapping_gate(),
        "exact_dispatch": exact_dispatch_gate(),
        "validation_fail_closed": validation_fail_closed_gate(),
        "single_use": single_use_gate(),
        "sink_failure": sink_failure_gate(),
        "static_boundary": static_boundary_gate(),
        "fallback": "ABSENT",
        "regeneration": "ABSENT",
        "execution_policy": "CERTIFIED_REUSE_ADMISSION_ONLY",
        "selective_capstone": "NOT_CLAIMED",
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
