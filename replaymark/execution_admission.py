from __future__ import annotations

"""Certified execution admission over an already-validated runtime certificate.

This module introduces exactly one execution-policy boundary:

    VALID + R*=REUSE             -> ADMIT_REUSE
    INVALID + R*=DO_NOT_REUSE    -> BLOCK_REUSE
    UNRESOLVED + R*=DO_NOT_REUSE -> BLOCK_REUSE

It does not validate substrate provenance, execute an action, choose a fallback,
regenerate, retry, or reinterpret realization failure as semantic UNRESOLVED.
Callers must use a substrate gate that revalidates the complete certificate
chain before passing a certificate into :func:`admit_validated_runtime_certificate`.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from .contracts import Verdict
from .rstar import ReuseDisposition
from .runtime_realization import RuntimeReuseCertificate


EXECUTION_ADMISSION_SCHEMA = "replaymark.execution-admission.v1"
EXECUTION_ADMISSION_POLICY_ID = "replaymark.certified-reuse-admission.no-fallback.v1"

_RULE_RECORD = {
    "schema": "replaymark.execution-admission-policy.v1",
    "input": "validated RuntimeReuseCertificate",
    "mapping": {
        "VALID+REUSE": "ADMIT_REUSE",
        "INVALID+DO_NOT_REUSE": "BLOCK_REUSE",
        "UNRESOLVED+DO_NOT_REUSE": "BLOCK_REUSE",
    },
    "validation": "outside-this-module",
    "execution": "outside-this-module",
    "fallback": False,
    "regeneration": False,
    "retry": False,
    "block_preserves_three_valued_reason": True,
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


EXECUTION_ADMISSION_POLICY_SEMANTIC_DIGEST = _sha256(
    _canonical_json_bytes(_RULE_RECORD)
)


class ExecutionAdmissionDisposition(str, Enum):
    ADMIT_REUSE = "ADMIT_REUSE"
    BLOCK_REUSE = "BLOCK_REUSE"


@dataclass(frozen=True)
class CertifiedExecutionAdmission:
    schema_version: str
    policy_id: str
    policy_semantic_digest: str
    runtime_certificate_fingerprint: str
    contract_fingerprint: str
    claim_fingerprint: str
    observation_fingerprint: str
    historical_action_fingerprint: str
    adjudication_fingerprint: str
    reuse_decision_fingerprint: str
    verdict: Verdict
    reuse_disposition: ReuseDisposition
    disposition: ExecutionAdmissionDisposition

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_ADMISSION_SCHEMA:
            raise ValueError("foreign execution-admission schema")
        if self.policy_id != EXECUTION_ADMISSION_POLICY_ID:
            raise ValueError("foreign execution-admission policy")
        if self.policy_semantic_digest != EXECUTION_ADMISSION_POLICY_SEMANTIC_DIGEST:
            raise ValueError("foreign execution-admission policy semantics")
        if not isinstance(self.verdict, Verdict):
            raise TypeError("verdict must be Verdict")
        if not isinstance(self.reuse_disposition, ReuseDisposition):
            raise TypeError("reuse_disposition must be ReuseDisposition")
        if not isinstance(self.disposition, ExecutionAdmissionDisposition):
            raise TypeError("disposition must be ExecutionAdmissionDisposition")

        for name, value in (
            ("runtime_certificate_fingerprint", self.runtime_certificate_fingerprint),
            ("contract_fingerprint", self.contract_fingerprint),
            ("claim_fingerprint", self.claim_fingerprint),
            ("observation_fingerprint", self.observation_fingerprint),
            ("historical_action_fingerprint", self.historical_action_fingerprint),
            ("adjudication_fingerprint", self.adjudication_fingerprint),
            ("reuse_decision_fingerprint", self.reuse_decision_fingerprint),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError(f"{name} must be canonical lowercase sha256 hex")

        expected_reuse = (
            ReuseDisposition.REUSE
            if self.verdict is Verdict.VALID
            else ReuseDisposition.DO_NOT_REUSE
        )
        if self.reuse_disposition is not expected_reuse:
            raise ValueError("admission input violates the frozen R* theorem")

        expected_admission = (
            ExecutionAdmissionDisposition.ADMIT_REUSE
            if self.reuse_disposition is ReuseDisposition.REUSE
            else ExecutionAdmissionDisposition.BLOCK_REUSE
        )
        if self.disposition is not expected_admission:
            raise ValueError("execution admission disagrees with certified reuse")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "policy_id": self.policy_id,
            "policy_semantic_digest": self.policy_semantic_digest,
            "runtime_certificate_fingerprint": self.runtime_certificate_fingerprint,
            "contract_fingerprint": self.contract_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "observation_fingerprint": self.observation_fingerprint,
            "historical_action_fingerprint": self.historical_action_fingerprint,
            "adjudication_fingerprint": self.adjudication_fingerprint,
            "reuse_decision_fingerprint": self.reuse_decision_fingerprint,
            "verdict": self.verdict.value,
            "reuse_disposition": self.reuse_disposition.value,
            "disposition": self.disposition.value,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


def admit_validated_runtime_certificate(
    certificate: RuntimeReuseCertificate,
) -> CertifiedExecutionAdmission:
    """Map one already-validated runtime certificate to the no-fallback boundary.

    This function deliberately does not establish trust in ``certificate``.
    Substrate gates must reconstruct and byte-compare the complete certificate
    chain from frozen raw runtime material before calling this function.
    """

    if not isinstance(certificate, RuntimeReuseCertificate):
        raise TypeError("certificate must be RuntimeReuseCertificate")

    decision = certificate.reuse_decision
    disposition = (
        ExecutionAdmissionDisposition.ADMIT_REUSE
        if decision.disposition is ReuseDisposition.REUSE
        else ExecutionAdmissionDisposition.BLOCK_REUSE
    )
    return CertifiedExecutionAdmission(
        schema_version=EXECUTION_ADMISSION_SCHEMA,
        policy_id=EXECUTION_ADMISSION_POLICY_ID,
        policy_semantic_digest=EXECUTION_ADMISSION_POLICY_SEMANTIC_DIGEST,
        runtime_certificate_fingerprint=certificate.fingerprint(),
        contract_fingerprint=certificate.contract_fingerprint,
        claim_fingerprint=certificate.claim_fingerprint,
        observation_fingerprint=certificate.observation.fingerprint(),
        historical_action_fingerprint=certificate.historical_action.fingerprint(),
        adjudication_fingerprint=certificate.adjudication.fingerprint(),
        reuse_decision_fingerprint=certificate.reuse_decision.fingerprint(),
        verdict=certificate.adjudication.verdict,
        reuse_disposition=decision.disposition,
        disposition=disposition,
    )


def execution_admission_rule_record() -> dict[str, object]:
    return json.loads(_canonical_json_bytes(_RULE_RECORD).decode("utf-8"))


__all__ = (
    "EXECUTION_ADMISSION_SCHEMA",
    "EXECUTION_ADMISSION_POLICY_ID",
    "EXECUTION_ADMISSION_POLICY_SEMANTIC_DIGEST",
    "ExecutionAdmissionDisposition",
    "CertifiedExecutionAdmission",
    "admit_validated_runtime_certificate",
    "execution_admission_rule_record",
)
