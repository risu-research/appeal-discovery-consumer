from __future__ import annotations

"""Static/runtime gate for the re-frozen CompiledContract semantic API.

This gate does not implement a concrete compiled contract. It verifies that the
normative Protocol itself exposes exactly the established semantic products and
that the provisional conflated surface cannot silently return.
"""

import inspect
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import replaymark
from replaymark.contracts import ClaimSpec, CompiledContract, ProjectedAction


EXPECTED_ROOT_EXPORTS = (
    "ClaimSpec",
    "TargetModel",
    "EvidenceSpec",
    "ProjectedAction",
    "CompiledContract",
    "Verdict",
)

EXPECTED_PROPERTIES = {
    "schema_version",
    "compiler_id",
    "claim",
    "claim_fingerprint",
    "target_provider_fingerprint",
    "target_semantic_digest",
    "target_snapshot_fingerprint",
    "evidence_semantics_fingerprint",
    "evidence_relation_fingerprint",
    "quotient_fingerprint",
    "support_envelope_fingerprint",
    "predictive_witness_index_fingerprint",
}

EXPECTED_METHODS = {
    "canonical_bytes",
    "fingerprint",
    "compatible_worlds",
    "adjudicate",
    "certify_reuse",
    "reuse_counterexample_world",
    "predictive_witness",
}

FORBIDDEN_LEGACY_MEMBERS = {
    "target_model_fingerprint",
    "evidence_fingerprint",
    "reusable_observations",
    "shortest_witness",
}

FORBIDDEN_POLICY_NAMES = {
    "execute",
    "regenerate",
    "fallback",
    "retry",
    "abort",
    "refine_evidence",
}


def _properties(cls: type) -> set[str]:
    return {
        name
        for name, value in cls.__dict__.items()
        if isinstance(value, property)
    }


def _protocol_methods(cls: type) -> set[str]:
    return {
        name
        for name, value in cls.__dict__.items()
        if inspect.isfunction(value) and not name.startswith("__")
    }


def _parameter_names(name: str) -> tuple[str, ...]:
    return tuple(inspect.signature(getattr(CompiledContract, name)).parameters)


def _return_annotation(name: str) -> str:
    annotation = inspect.signature(getattr(CompiledContract, name)).return_annotation
    return str(annotation).replace("'", "")


class _SurfaceConformer:
    """Shape-only object proving the runtime-checkable Protocol is realizable."""

    schema_version = "test"
    compiler_id = "test"
    claim = ClaimSpec("api-freeze", ("operation",), 0, "event")
    claim_fingerprint = claim.fingerprint()
    target_provider_fingerprint = "provider"
    target_semantic_digest = "target-semantic"
    target_snapshot_fingerprint = "target-snapshot"
    evidence_semantics_fingerprint = "evidence-semantics"
    evidence_relation_fingerprint = "evidence-relation"
    quotient_fingerprint = "quotient"
    support_envelope_fingerprint = "support"
    predictive_witness_index_fingerprint = "witness-index"

    def canonical_bytes(self) -> bytes:
        return b"test"

    def fingerprint(self) -> str:
        return "contract"

    def compatible_worlds(self, observation_token: str) -> tuple[str, ...]:
        return ("w",)

    def adjudicate(self, observation_token: str, historical_action: ProjectedAction):
        raise NotImplementedError

    def certify_reuse(self, observation_token: str, historical_action: ProjectedAction):
        raise NotImplementedError

    def reuse_counterexample_world(
        self, observation_token: str, historical_action: ProjectedAction
    ) -> str | None:
        return None

    def predictive_witness(self, left_world: str, right_world: str):
        return None


def main() -> None:
    assert tuple(replaymark.__all__) == EXPECTED_ROOT_EXPORTS

    properties = _properties(CompiledContract)
    methods = _protocol_methods(CompiledContract)
    assert properties == EXPECTED_PROPERTIES, (properties, EXPECTED_PROPERTIES)
    assert methods == EXPECTED_METHODS, (methods, EXPECTED_METHODS)

    for name in FORBIDDEN_LEGACY_MEMBERS | FORBIDDEN_POLICY_NAMES:
        assert not hasattr(CompiledContract, name), name

    assert _parameter_names("canonical_bytes") == ("self",)
    assert _parameter_names("fingerprint") == ("self",)
    assert _parameter_names("compatible_worlds") == ("self", "observation_token")
    assert _parameter_names("adjudicate") == (
        "self",
        "observation_token",
        "historical_action",
    )
    assert _parameter_names("certify_reuse") == (
        "self",
        "observation_token",
        "historical_action",
    )
    assert _parameter_names("reuse_counterexample_world") == (
        "self",
        "observation_token",
        "historical_action",
    )
    assert _parameter_names("predictive_witness") == (
        "self",
        "left_world",
        "right_world",
    )

    assert _return_annotation("canonical_bytes") == "bytes"
    assert _return_annotation("fingerprint") == "str"
    assert _return_annotation("compatible_worlds") == "tuple[str, ...]"
    assert _return_annotation("adjudicate") == "Adjudication"
    assert _return_annotation("certify_reuse") == "RStarDecision"
    assert _return_annotation("reuse_counterexample_world") == "str | None"
    assert _return_annotation("predictive_witness") == (
        "PredictiveContinuationWitness | None"
    )

    # Predictive witness must not accept evidence/action parameters; reuse
    # counterexample must not accept a world-pair or depth parameter.
    predictive = set(_parameter_names("predictive_witness"))
    assert "observation_token" not in predictive
    assert "historical_action" not in predictive
    assert "depth" not in predictive

    reuse_counterexample = set(_parameter_names("reuse_counterexample_world"))
    assert "left_world" not in reuse_counterexample
    assert "right_world" not in reuse_counterexample

    # The runtime-checkable protocol must be structurally implementable without
    # importing concrete backend modules into contracts.py at runtime.
    assert isinstance(_SurfaceConformer(), CompiledContract)

    source = inspect.getsource(CompiledContract)
    assert "already-canonical retained-evidence" in source
    assert "does not execute" in source
    assert "certificates and semantic provenance" in source

    print(
        "PASS CompiledContract API re-freeze: "
        f"{len(properties)} provenance/identity properties, "
        f"{len(methods)} normative methods; provisional conflated API removed"
    )


if __name__ == "__main__":
    main()
