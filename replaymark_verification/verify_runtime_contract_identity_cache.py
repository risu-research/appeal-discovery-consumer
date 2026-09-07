from __future__ import annotations

"""Gate for verified immutable-contract identity reuse in the E3b runtime bridge."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.compiled_contract import ExplicitCompiledContract, compile_explicit_contract
from replaymark.contracts import ClaimSpec, EvidenceSpec
from replaymark.rstar import ReuseDisposition
from replaymark.runtime_contract_identity import (
    RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY,
    runtime_contract_identity_cache_info,
    verified_runtime_contract_identity,
)
from replaymark.runtime_e3b_action import E3B_ACTION_CAPTURE_POINT, E3B_RAW_ACTION_SCHEMA
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_e3b_observation import E3B_RAW_OBSERVATION_SCHEMA
from replaymark.runtime_realization import RuntimeReuseCertificate
from replaymark_verification.evidence_models import model_from_expected_inverse
from replaymark_verification.models import TableTargetModel

_PREOPT_BRIDGE_SEMANTIC_DIGEST = "e4db6e24e2da609c3361ef279a465c88c5068c44e7ae902eed75afec42d32a03"
_RUNTIME_REUSE_CERTIFICATE_SCHEMA = "replaymark.runtime.reuse-certificate.v1"


def _obs(task: int, confirmed: bool) -> dict[str, object]:
    events = []
    if confirmed:
        events.append({
            "event_id": f"cache-state-{task}",
            "device": f"cache-{task}-a",
            "on": True,
            "recv_mono_ns": 150,
            "clock_domain": "mono:cache",
        })
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": "mono:cache",
        "expected_device": f"cache-{task}-a",
        "command_publish_mono_ns": 100,
        "verify_deadline_mono_ns": 200,
        "closed_at_mono_ns": 200,
        "events": events,
    }


def _action(task: int) -> dict[str, object]:
    return {
        "schema": E3B_RAW_ACTION_SCHEMA,
        "capture_point": E3B_ACTION_CAPTURE_POINT,
        "clock_domain": "mono:cache",
        "publish_mono_ns": 220,
        "topic": f"agentmark/cache-{task}-b/command",
        "payload_utf8": '{"on": true}',
        "qos": 1,
        "retain": False,
        "properties": None,
    }


def _contract(*, ambiguous: bool = False) -> ExplicitCompiledContract:
    target = TableTargetModel(outputs=("ACT2", "VERIFY"), continuations=("tick",), next_state=((0,), (1,)))
    claim = ClaimSpec("e3b-runtime-identity-cache-verification", ("operation",), 0, "controller-decision")
    confirmed = ("s0", "s1") if ambiguous else ("s0",)
    evidence = EvidenceSpec(
        "e3b-runtime-identity-cache-evidence",
        (("confirmed_by_deadline", confirmed), ("not_visible_by_deadline", ("s1",))),
    )
    return compile_explicit_contract(
        target,
        claim,
        model_from_expected_inverse(target, evidence),
        evidence_id=evidence.evidence_id,
    )


def _pair(task: int, *, confirmed: bool):
    return correlate_e3b_runtime_pair(_obs(task, confirmed), _action(task))


def _legacy_recompute_bridge(contract: ExplicitCompiledContract, pair) -> E3bShadowRuntimeReuseCertificate:
    observation = pair.observation
    historical_action = pair.historical_action
    token = observation.evidence_token
    action = historical_action.action
    adjudication = contract.adjudicate(token, action)
    reuse_decision = contract.certify_reuse(token, action)
    semantic = RuntimeReuseCertificate(
        schema_version=_RUNTIME_REUSE_CERTIFICATE_SCHEMA,
        contract_fingerprint=contract.fingerprint(),
        claim_fingerprint=contract.claim_fingerprint,
        observation=observation,
        historical_action=historical_action,
        adjudication=adjudication,
        reuse_decision=reuse_decision,
    )
    return E3bShadowRuntimeReuseCertificate(
        schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
        bridge_id=E3B_SHADOW_BRIDGE_ID,
        bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        contract_fingerprint=contract.fingerprint(),
        claim_fingerprint=contract.claim_fingerprint,
        correlated_pair=pair,
        semantic_certificate=semantic,
    )


def byte_equivalence_gate() -> dict[str, object]:
    cases = (
        ("VALID", _contract(), _pair(10, confirmed=True)),
        ("INVALID", _contract(), _pair(11, confirmed=False)),
        ("UNRESOLVED", _contract(ambiguous=True), _pair(12, confirmed=True)),
    )
    observed = {}
    for expected, contract, pair in cases:
        legacy = _legacy_recompute_bridge(contract, pair)
        optimized = certify_e3b_shadow_reuse(contract, pair)
        if legacy.canonical_bytes() != optimized.canonical_bytes():
            raise AssertionError(f"optimized certificate bytes drifted for {expected}")
        verdict = optimized.semantic_certificate.adjudication.verdict.value
        reuse = optimized.semantic_certificate.reuse_decision.disposition.value
        if verdict != expected:
            raise AssertionError(f"unexpected verdict {verdict} != {expected}")
        observed[expected] = {"verdict": verdict, "reuse": reuse}
    if observed["VALID"]["reuse"] != ReuseDisposition.REUSE.value:
        raise AssertionError("VALID did not preserve REUSE")
    if observed["INVALID"]["reuse"] != ReuseDisposition.DO_NOT_REUSE.value:
        raise AssertionError("INVALID did not preserve DO_NOT_REUSE")
    if observed["UNRESOLVED"]["reuse"] != ReuseDisposition.DO_NOT_REUSE.value:
        raise AssertionError("UNRESOLVED did not preserve DO_NOT_REUSE")
    return {"legacy_vs_optimized_canonical_bytes_exact": True, "outcomes": observed}


def single_object_once_gate() -> dict[str, object]:
    contract = _contract()
    pairs = [_pair(100 + i, confirmed=(i % 2 == 0)) for i in range(32)]
    original = ExplicitCompiledContract.fingerprint
    calls = 0
    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)
    with patch.object(ExplicitCompiledContract, "fingerprint", counted):
        outputs = [certify_e3b_shadow_reuse(contract, pair) for pair in pairs]
    if calls != 1 or len(outputs) != 32:
        raise AssertionError(f"expected one cold contract fingerprint, observed {calls}")
    return {"bridge_calls": 32, "underlying_contract_fingerprint_calls": calls}


def concurrent_cold_start_gate() -> dict[str, object]:
    contract = _contract()
    original = ExplicitCompiledContract.fingerprint
    calls = 0
    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)
    with patch.object(ExplicitCompiledContract, "fingerprint", counted):
        with ThreadPoolExecutor(max_workers=32) as pool:
            identities = list(pool.map(lambda _i: verified_runtime_contract_identity(contract), range(32)))
    if calls != 1:
        raise AssertionError(f"concurrent cold start computed fingerprint {calls} times")
    if len({item.contract_fingerprint for item in identities}) != 1:
        raise AssertionError("concurrent identity results disagree")
    return {"concurrent_callers": 32, "underlying_contract_fingerprint_calls": calls}


def identity_and_bound_gate() -> dict[str, object]:
    left = _contract()
    right = _contract()
    if left.canonical_bytes() != right.canonical_bytes():
        raise AssertionError("control contracts are not byte-identical")
    original = ExplicitCompiledContract.fingerprint
    calls = 0
    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)
    with patch.object(ExplicitCompiledContract, "fingerprint", counted):
        left_id = verified_runtime_contract_identity(left)
        right_id = verified_runtime_contract_identity(right)
    if calls != 2:
        raise AssertionError("distinct objects incorrectly shared a cache entry")
    if left_id != right_id:
        raise AssertionError("byte-identical contracts should have equal content identities")
    before = runtime_contract_identity_cache_info()
    for _ in range(RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY + 5):
        verified_runtime_contract_identity(_contract())
    after = runtime_contract_identity_cache_info()
    if int(after["size"]) > RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY:
        raise AssertionError("cache exceeded its bound")
    if int(after["evictions"]) <= int(before["evictions"]):
        raise AssertionError("capacity pressure did not cause eviction")
    try:
        left.quotient = right.quotient  # type: ignore[misc]
    except (FrozenInstanceError, AttributeError):
        immutable_surface = True
    else:
        raise AssertionError("ExplicitCompiledContract admitted ordinary mutation")
    return {
        "byte_identical_distinct_objects_require_distinct_cold_verification": True,
        "distinct_object_fingerprint_calls": calls,
        "capacity": RUNTIME_CONTRACT_IDENTITY_CACHE_CAPACITY,
        "bounded_size": int(after["size"]),
        "eviction_observed": True,
        "ordinary_contract_mutation_rejected": immutable_surface,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST != _PREOPT_BRIDGE_SEMANTIC_DIGEST:
        raise AssertionError("bridge semantic digest changed during non-semantic optimization")
    report = {
        "schema": "replaymark.runtime-contract-identity-cache-gate.v1",
        "verdict": "PASS",
        "bridge_semantic_digest_unchanged": True,
        "byte_equivalence": byte_equivalence_gate(),
        "same_object_reuse": single_object_once_gate(),
        "concurrent_cold_start": concurrent_cold_start_gate(),
        "identity_and_bound": identity_and_bound_gate(),
        "cache_info": runtime_contract_identity_cache_info(),
        "semantic_change": False,
        "execution_policy": "NOT_IMPLEMENTED",
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
