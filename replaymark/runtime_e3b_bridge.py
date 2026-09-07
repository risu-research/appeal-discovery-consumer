from __future__ import annotations

"""Shadow-only E3b bridge from correlated runtime material to frozen semantics.

This module performs orchestration only. It consumes an already-proved
``E3bCorrelatedRuntimePair`` and delegates semantic judgment exclusively to the
existing ``ExplicitCompiledContract`` API. It does not execute, block, publish,
regenerate, or choose fallback policy.
"""

from dataclasses import dataclass
import hashlib
import json

from .compiled_contract import ExplicitCompiledContract
from .runtime_contract_identity import verified_runtime_contract_identity
from .runtime_e3b_correlation import E3bCorrelatedRuntimePair
from .runtime_realization import RuntimeReuseCertificate


E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA = (
    "replaymark.runtime.e3b-shadow-reuse-certificate.v1"
)
E3B_SHADOW_BRIDGE_ID = "replaymark.e3b-shadow-runtime-bridge.v1"
_RUNTIME_REUSE_CERTIFICATE_SCHEMA = "replaymark.runtime.reuse-certificate.v1"

_RULE_RECORD = {
    "schema": "replaymark.runtime.e3b-shadow-bridge-semantics.v1",
    "input": "E3bCorrelatedRuntimePair",
    "contract": "ExplicitCompiledContract",
    "semantic_calls": [
        "ExplicitCompiledContract.adjudicate",
        "ExplicitCompiledContract.certify_reuse",
    ],
    "semantic_reimplementation": False,
    "correlation_proof_embedded_in_output": True,
    "execution": {
        "publish": False,
        "block": False,
        "fallback": False,
        "regenerate": False,
    },
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


E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST = _sha256(_canonical_json_bytes(_RULE_RECORD))


@dataclass(frozen=True)
class E3bShadowRuntimeReuseCertificate:
    """Single audit object binding same-task proof to frozen semantic judgment."""

    schema_version: str
    bridge_id: str
    bridge_semantic_digest: str
    contract_fingerprint: str
    claim_fingerprint: str
    correlated_pair: E3bCorrelatedRuntimePair
    semantic_certificate: RuntimeReuseCertificate

    def __post_init__(self) -> None:
        if self.schema_version != E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA:
            raise ValueError("foreign E3b shadow runtime-certificate schema")
        if self.bridge_id != E3B_SHADOW_BRIDGE_ID:
            raise ValueError("foreign E3b shadow runtime bridge")
        if self.bridge_semantic_digest != E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST:
            raise ValueError("foreign E3b shadow runtime bridge semantics")
        for name, value in (
            ("contract_fingerprint", self.contract_fingerprint),
            ("claim_fingerprint", self.claim_fingerprint),
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError(f"{name} must be canonical lowercase sha256 hex")
        if not isinstance(self.correlated_pair, E3bCorrelatedRuntimePair):
            raise TypeError("correlated_pair must be E3bCorrelatedRuntimePair")
        if not isinstance(self.semantic_certificate, RuntimeReuseCertificate):
            raise TypeError("semantic_certificate must be RuntimeReuseCertificate")

        pair = self.correlated_pair
        semantic = self.semantic_certificate
        if semantic.contract_fingerprint != self.contract_fingerprint:
            raise ValueError("semantic certificate contract binding disagrees with chain")
        if semantic.claim_fingerprint != self.claim_fingerprint:
            raise ValueError("semantic certificate claim binding disagrees with chain")
        if semantic.observation.fingerprint() != pair.observation.fingerprint():
            raise ValueError(
                "semantic certificate is bound to a different realized observation"
            )
        if (
            semantic.historical_action.fingerprint()
            != pair.historical_action.fingerprint()
        ):
            raise ValueError(
                "semantic certificate is bound to a different realized historical action"
            )

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "bridge_id": self.bridge_id,
            "bridge_semantic_digest": self.bridge_semantic_digest,
            "contract_fingerprint": self.contract_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "correlated_pair": self.correlated_pair.canonical_record(),
            "semantic_certificate": self.semantic_certificate.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


def certify_e3b_shadow_reuse(
    contract: ExplicitCompiledContract,
    correlated_pair: E3bCorrelatedRuntimePair,
) -> E3bShadowRuntimeReuseCertificate:
    """Construct a proof-carrying, shadow-only runtime reuse certificate.

    The function accepts no raw observation/action values, so individual
    realization and same-task correlation must already have succeeded. All
    semantic reasoning is delegated to the frozen concrete contract.

    Contract/claim identities are verified from the exact immutable contract
    object on first use and reused from a bounded runtime cache thereafter. The
    cache is non-semantic: certificate bytes are identical to recomputing the
    same identities on every call.
    """

    if not isinstance(contract, ExplicitCompiledContract):
        raise TypeError("contract must be ExplicitCompiledContract")
    if not isinstance(correlated_pair, E3bCorrelatedRuntimePair):
        raise TypeError("correlated_pair must be E3bCorrelatedRuntimePair")

    observation = correlated_pair.observation
    historical_action = correlated_pair.historical_action
    token = observation.evidence_token
    action = historical_action.action

    identity = verified_runtime_contract_identity(contract)
    adjudication = contract.adjudicate(token, action)
    reuse_decision = contract.certify_reuse(token, action)

    semantic_certificate = RuntimeReuseCertificate(
        schema_version=_RUNTIME_REUSE_CERTIFICATE_SCHEMA,
        contract_fingerprint=identity.contract_fingerprint,
        claim_fingerprint=identity.claim_fingerprint,
        observation=observation,
        historical_action=historical_action,
        adjudication=adjudication,
        reuse_decision=reuse_decision,
    )
    return E3bShadowRuntimeReuseCertificate(
        schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
        bridge_id=E3B_SHADOW_BRIDGE_ID,
        bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        contract_fingerprint=identity.contract_fingerprint,
        claim_fingerprint=identity.claim_fingerprint,
        correlated_pair=correlated_pair,
        semantic_certificate=semantic_certificate,
    )


def e3b_shadow_bridge_rule_record() -> dict[str, object]:
    """Return a defensive copy of the bridge's normative orchestration record."""

    return json.loads(_canonical_json_bytes(_RULE_RECORD).decode("utf-8"))


__all__ = (
    "E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA",
    "E3B_SHADOW_BRIDGE_ID",
    "E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST",
    "E3bShadowRuntimeReuseCertificate",
    "certify_e3b_shadow_reuse",
    "e3b_shadow_bridge_rule_record",
)
