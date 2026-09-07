from __future__ import annotations

"""Fail-closed E3b execution gate for certified historical reuse.

The safe dispatch entry point reconstructs the complete frozen E3b runtime chain
from raw observation/action material and the supplied ExplicitCompiledContract,
byte-compares the reconstructed chained certificate to the presented certificate,
maps the validated semantic certificate through the no-fallback admission policy,
and only then may invoke the concrete MQTT publish sink.

There is no fallback branch. BLOCK_REUSE, validation failure, duplicate
consumption, and sink failure never select another action.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import threading
from typing import Any

from .compiled_contract import ExplicitCompiledContract
from .execution_admission import (
    CertifiedExecutionAdmission,
    ExecutionAdmissionDisposition,
    admit_validated_runtime_certificate,
)
from .runtime_e3b_action import (
    E3bHistoricalActionRecord,
    parse_e3b_historical_action_record,
)
from .runtime_e3b_bridge import (
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from .runtime_e3b_correlation import correlate_e3b_runtime_pair


E3B_EXECUTION_GATE_ID = "replaymark.e3b-certified-execution-gate.no-fallback.v1"
E3B_EXECUTION_RECEIPT_SCHEMA = "replaymark.runtime.e3b-execution-receipt.v1"

_RULE_RECORD = {
    "schema": "replaymark.runtime.e3b-certified-execution-gate.v1",
    "input": {
        "contract": "ExplicitCompiledContract",
        "raw_observation": "frozen E3b observation schema",
        "raw_action": "frozen E3b pre-send action schema",
        "presented_certificate": "E3bShadowRuntimeReuseCertificate",
    },
    "validation": {
        "recompute_pair_from_raw": True,
        "recompute_certificate_through_frozen_bridge": True,
        "presented_vs_recomputed_canonical_bytes": "exact",
        "caller_supplied_same_task_flag": False,
        "caller_supplied_semantic_verdict": False,
    },
    "policy": "validated certificate -> ADMIT_REUSE | BLOCK_REUSE",
    "dispatch": {
        "ADMIT_REUSE": "exact validated E3b action -> one Client.publish invocation",
        "BLOCK_REUSE": "zero Client.publish invocations",
        "caller_action_override": False,
        "single_use_per_gate_instance": True,
        "mark_consumed_before_delegate": True,
        "automatic_retry": False,
    },
    "fallback": False,
    "regeneration": False,
    "durable_cross_process_deduplication": False,
    "broker_delivery_claim": False,
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


E3B_EXECUTION_GATE_SEMANTIC_DIGEST = _sha256(_canonical_json_bytes(_RULE_RECORD))


class E3bExecutionGateFailureCode(str, Enum):
    CERTIFICATE_MISMATCH = "CERTIFICATE_MISMATCH"
    DUPLICATE_CONSUMPTION = "DUPLICATE_CONSUMPTION"
    SINK_FAILURE = "SINK_FAILURE"


class E3bExecutionGateError(RuntimeError):
    def __init__(
        self,
        code: E3bExecutionGateFailureCode,
        message: str,
        *,
        certificate_fingerprint: str | None = None,
    ):
        if not isinstance(code, E3bExecutionGateFailureCode):
            raise TypeError("code must be E3bExecutionGateFailureCode")
        self.code = code
        self.certificate_fingerprint = certificate_fingerprint
        super().__init__(f"{code.value}: {message}")


@dataclass(frozen=True)
class E3bValidatedExecutionAdmission:
    gate_id: str
    gate_semantic_digest: str
    chained_certificate_fingerprint: str
    correlated_pair_fingerprint: str
    action_raw_digest: str
    admission: CertifiedExecutionAdmission

    def __post_init__(self) -> None:
        if self.gate_id != E3B_EXECUTION_GATE_ID:
            raise ValueError("foreign E3b execution gate")
        if self.gate_semantic_digest != E3B_EXECUTION_GATE_SEMANTIC_DIGEST:
            raise ValueError("foreign E3b execution-gate semantics")
        if not isinstance(self.admission, CertifiedExecutionAdmission):
            raise TypeError("admission must be CertifiedExecutionAdmission")
        for name, value in (
            ("chained_certificate_fingerprint", self.chained_certificate_fingerprint),
            ("correlated_pair_fingerprint", self.correlated_pair_fingerprint),
            ("action_raw_digest", self.action_raw_digest),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError(f"{name} must be canonical lowercase sha256 hex")

    def canonical_record(self) -> dict[str, object]:
        return {
            "gate_id": self.gate_id,
            "gate_semantic_digest": self.gate_semantic_digest,
            "chained_certificate_fingerprint": self.chained_certificate_fingerprint,
            "correlated_pair_fingerprint": self.correlated_pair_fingerprint,
            "action_raw_digest": self.action_raw_digest,
            "admission": self.admission.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


@dataclass(frozen=True)
class E3bExecutionReceipt:
    schema_version: str
    gate_id: str
    gate_semantic_digest: str
    validated_admission_fingerprint: str
    chained_certificate_fingerprint: str
    execution_disposition: ExecutionAdmissionDisposition
    application_publish_invocations: int
    wait_for_publish_invocations: int
    action_raw_digest: str
    sink_result: str

    def __post_init__(self) -> None:
        if self.schema_version != E3B_EXECUTION_RECEIPT_SCHEMA:
            raise ValueError("foreign E3b execution-receipt schema")
        if self.gate_id != E3B_EXECUTION_GATE_ID:
            raise ValueError("foreign E3b execution gate")
        if self.gate_semantic_digest != E3B_EXECUTION_GATE_SEMANTIC_DIGEST:
            raise ValueError("foreign E3b execution-gate semantics")
        if not isinstance(self.execution_disposition, ExecutionAdmissionDisposition):
            raise TypeError("execution_disposition must be ExecutionAdmissionDisposition")
        for name, value in (
            ("validated_admission_fingerprint", self.validated_admission_fingerprint),
            ("chained_certificate_fingerprint", self.chained_certificate_fingerprint),
            ("action_raw_digest", self.action_raw_digest),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError(f"{name} must be canonical lowercase sha256 hex")
        for name, value in (
            ("application_publish_invocations", self.application_publish_invocations),
            ("wait_for_publish_invocations", self.wait_for_publish_invocations),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        expected = (
            (1, 1, "PUBLISHED")
            if self.execution_disposition is ExecutionAdmissionDisposition.ADMIT_REUSE
            else (0, 0, "BLOCKED")
        )
        if (
            self.application_publish_invocations,
            self.wait_for_publish_invocations,
            self.sink_result,
        ) != expected:
            raise ValueError("receipt is inconsistent with the no-fallback dispatch rule")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "gate_id": self.gate_id,
            "gate_semantic_digest": self.gate_semantic_digest,
            "validated_admission_fingerprint": self.validated_admission_fingerprint,
            "chained_certificate_fingerprint": self.chained_certificate_fingerprint,
            "execution_disposition": self.execution_disposition.value,
            "application_publish_invocations": self.application_publish_invocations,
            "wait_for_publish_invocations": self.wait_for_publish_invocations,
            "action_raw_digest": self.action_raw_digest,
            "sink_result": self.sink_result,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


def validate_e3b_execution_certificate(
    contract: ExplicitCompiledContract,
    raw_observation: object,
    raw_action: object,
    presented_certificate: E3bShadowRuntimeReuseCertificate,
) -> tuple[E3bValidatedExecutionAdmission, E3bHistoricalActionRecord]:
    """Reconstruct the complete frozen chain and require exact certificate identity."""

    if not isinstance(contract, ExplicitCompiledContract):
        raise TypeError("contract must be ExplicitCompiledContract")
    if not isinstance(presented_certificate, E3bShadowRuntimeReuseCertificate):
        raise TypeError(
            "presented_certificate must be E3bShadowRuntimeReuseCertificate"
        )

    pair = correlate_e3b_runtime_pair(raw_observation, raw_action)
    recomputed = certify_e3b_shadow_reuse(contract, pair)
    if recomputed.canonical_bytes() != presented_certificate.canonical_bytes():
        raise E3bExecutionGateError(
            E3bExecutionGateFailureCode.CERTIFICATE_MISMATCH,
            "presented certificate is not the exact frozen-chain result for these inputs",
            certificate_fingerprint=presented_certificate.fingerprint(),
        )

    action_record = parse_e3b_historical_action_record(raw_action)
    if action_record.fingerprint() != pair.correlation.action_raw_digest:
        raise AssertionError("correlator action raw digest disagrees with parsed action")
    if (
        action_record.fingerprint()
        != pair.historical_action.provenance.raw_record_digest
    ):
        raise AssertionError("realized action provenance disagrees with parsed action")

    admission = admit_validated_runtime_certificate(recomputed.semantic_certificate)
    validated = E3bValidatedExecutionAdmission(
        gate_id=E3B_EXECUTION_GATE_ID,
        gate_semantic_digest=E3B_EXECUTION_GATE_SEMANTIC_DIGEST,
        chained_certificate_fingerprint=recomputed.fingerprint(),
        correlated_pair_fingerprint=pair.fingerprint(),
        action_raw_digest=action_record.fingerprint(),
        admission=admission,
    )
    return validated, action_record


class E3bCertifiedExecutionGate:
    """Single-use, fail-closed owner of the E3b historical-reuse publish sink.

    At-most-once is enforced only within this gate instance/process. A future
    durable capstone may add persistent deduplication, but this gate will not
    silently claim cross-process exactly-once semantics that MQTT does not provide.
    """

    def __init__(self, client: Any):
        publish = getattr(client, "publish", None)
        if not callable(publish):
            raise TypeError("client must expose a callable publish method")
        self._client = client
        self._lock = threading.Lock()
        self._consumed: set[str] = set()

    @property
    def consumed_count(self) -> int:
        with self._lock:
            return len(self._consumed)

    def evaluate(
        self,
        contract: ExplicitCompiledContract,
        raw_observation: object,
        raw_action: object,
        presented_certificate: E3bShadowRuntimeReuseCertificate,
    ) -> E3bValidatedExecutionAdmission:
        validated, _record = validate_e3b_execution_certificate(
            contract,
            raw_observation,
            raw_action,
            presented_certificate,
        )
        return validated

    def dispatch(
        self,
        contract: ExplicitCompiledContract,
        raw_observation: object,
        raw_action: object,
        presented_certificate: E3bShadowRuntimeReuseCertificate,
    ) -> E3bExecutionReceipt:
        """Validate, atomically consume, and admit or block one certified reuse.

        There is intentionally no fallback/action override parameter.
        """

        validated, action_record = validate_e3b_execution_certificate(
            contract,
            raw_observation,
            raw_action,
            presented_certificate,
        )
        key = validated.chained_certificate_fingerprint
        with self._lock:
            if key in self._consumed:
                raise E3bExecutionGateError(
                    E3bExecutionGateFailureCode.DUPLICATE_CONSUMPTION,
                    "this certified execution admission was already consumed",
                    certificate_fingerprint=key,
                )
            self._consumed.add(key)

        admission_fp = validated.fingerprint()
        disposition = validated.admission.disposition
        if disposition is ExecutionAdmissionDisposition.BLOCK_REUSE:
            return E3bExecutionReceipt(
                schema_version=E3B_EXECUTION_RECEIPT_SCHEMA,
                gate_id=E3B_EXECUTION_GATE_ID,
                gate_semantic_digest=E3B_EXECUTION_GATE_SEMANTIC_DIGEST,
                validated_admission_fingerprint=admission_fp,
                chained_certificate_fingerprint=key,
                execution_disposition=disposition,
                application_publish_invocations=0,
                wait_for_publish_invocations=0,
                action_raw_digest=validated.action_raw_digest,
                sink_result="BLOCKED",
            )

        try:
            info = self._client.publish(
                action_record.topic,
                action_record.payload_utf8,
                qos=action_record.qos,
                retain=action_record.retain,
                properties=action_record.properties,
            )
            wait_for_publish = getattr(info, "wait_for_publish", None)
            if not callable(wait_for_publish):
                raise TypeError("publish result must expose callable wait_for_publish")
            wait_for_publish(timeout=5)
        except Exception as exc:
            raise E3bExecutionGateError(
                E3bExecutionGateFailureCode.SINK_FAILURE,
                f"validated reuse delegate failed after admission: {type(exc).__name__}: {exc}",
                certificate_fingerprint=key,
            ) from exc

        return E3bExecutionReceipt(
            schema_version=E3B_EXECUTION_RECEIPT_SCHEMA,
            gate_id=E3B_EXECUTION_GATE_ID,
            gate_semantic_digest=E3B_EXECUTION_GATE_SEMANTIC_DIGEST,
            validated_admission_fingerprint=admission_fp,
            chained_certificate_fingerprint=key,
            execution_disposition=disposition,
            application_publish_invocations=1,
            wait_for_publish_invocations=1,
            action_raw_digest=validated.action_raw_digest,
            sink_result="PUBLISHED",
        )


def e3b_execution_gate_rule_record() -> dict[str, object]:
    return json.loads(_canonical_json_bytes(_RULE_RECORD).decode("utf-8"))


__all__ = (
    "E3B_EXECUTION_GATE_ID",
    "E3B_EXECUTION_GATE_SEMANTIC_DIGEST",
    "E3B_EXECUTION_RECEIPT_SCHEMA",
    "E3bExecutionGateFailureCode",
    "E3bExecutionGateError",
    "E3bValidatedExecutionAdmission",
    "E3bExecutionReceipt",
    "validate_e3b_execution_certificate",
    "E3bCertifiedExecutionGate",
    "e3b_execution_gate_rule_record",
)
