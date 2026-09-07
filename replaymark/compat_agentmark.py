from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping

from .contracts import ClaimSpec, ProjectedAction, TargetModel


_ADAPTER_SCHEMA = "replaymark.compat.agentmark-reactive-kernel.v1"
_LEGACY_PROJECTIONS: dict[str, tuple[str, ...]] = {
    "operation": ("operation",),
    "action": ("operation", "target_class", "variant"),
    "semantic": ("operation", "target_class", "delay_ms"),
}


def _canonicalize_legacy_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Fraction):
        return {"__fraction__": [value.numerator, value.denominator]}
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite float in legacy kernel spec")
        return value
    if isinstance(value, (list, tuple)):
        return [_canonicalize_legacy_value(item) for item in value]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("legacy kernel spec mappings require string keys")
            out[key] = _canonicalize_legacy_value(item)
        return out
    raise TypeError(
        "unsupported legacy kernel spec value for ReplayMark provenance: "
        f"{type(value).__name__}"
    )


def _canonical_spec_bytes(spec: Mapping[str, Any]) -> bytes:
    normalized = _canonicalize_legacy_value(spec)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class _AgentMarkReactiveKernelAdapter:
    """Read-only compatibility adapter; it never mutates the legacy kernel."""

    def __init__(self, kernel: Any):
        required = (
            "spec",
            "initial_state",
            "states",
            "feedback_alphabet",
            "has_feedback",
            "atoms",
        )
        missing = [name for name in required if not hasattr(kernel, name)]
        if missing:
            raise TypeError(
                "object is not AgentMark ReactiveKernel-compatible; missing: "
                + ", ".join(missing)
            )
        self._kernel = kernel
        spec_bytes = _canonical_spec_bytes(kernel.spec)
        self._fingerprint = hashlib.sha256(
            _ADAPTER_SCHEMA.encode("utf-8") + b"\0" + spec_bytes
        ).hexdigest()
        self._initial_state = str(kernel.initial_state)
        self._states = tuple(sorted(str(s) for s in kernel.states))
        self._feedback_alphabet = tuple(str(y) for y in kernel.feedback_alphabet)
        if self._initial_state not in self._states:
            raise ValueError("legacy kernel initial_state is absent from states")

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def initial_state(self) -> str:
        return self._initial_state

    @property
    def states(self) -> tuple[str, ...]:
        return self._states

    @property
    def feedback_alphabet(self) -> tuple[str, ...]:
        return self._feedback_alphabet

    def has_feedback(self, state: str, feedback: str) -> bool:
        if str(state) not in self._states:
            raise KeyError(f"unknown target state: {state!r}")
        if str(feedback) not in self._feedback_alphabet:
            raise KeyError(f"unknown feedback symbol: {feedback!r}")
        return bool(self._kernel.has_feedback(str(state), str(feedback)))

    def distribution(
        self,
        state: str,
        feedback: str,
    ) -> Mapping[tuple[ProjectedAction, str], Fraction]:
        state = str(state)
        feedback = str(feedback)
        if not self.has_feedback(state, feedback):
            raise KeyError(
                f"legacy kernel has no transition for state={state!r}, "
                f"feedback={feedback!r}"
            )

        out: dict[tuple[ProjectedAction, str], Fraction] = defaultdict(Fraction)
        for atom in self._kernel.atoms(state, feedback):
            probability = Fraction(atom.probability)
            if probability <= 0:
                continue
            event = atom.event
            action = ProjectedAction.from_mapping(
                {
                    "operation": str(event.operation),
                    "target_class": event.target_class,
                    "variant": event.variant,
                    "delay_ms": int(event.delay_ms),
                }
            )
            next_state = str(event.next_state)
            if next_state not in self._states:
                raise ValueError(
                    f"legacy kernel emitted unknown next state: {next_state!r}"
                )
            out[(action, next_state)] += probability

        total = sum(out.values(), Fraction(0, 1))
        if total != 1:
            raise ValueError(
                f"adapted transition mass for {state}/{feedback} is {total}, not 1"
            )
        return dict(out)


def target_model_from_agentmark_kernel(kernel: Any) -> TargetModel:
    """Adapt the frozen AgentMark ReactiveKernel semantics without rewriting it."""
    return _AgentMarkReactiveKernelAdapter(kernel)


def claim_from_agentmark_projection(
    projection: str,
    *,
    horizon: int = 0,
    claim_id: str | None = None,
    consequence_endpoint: str = "legacy-agentmark-controller-event",
) -> ClaimSpec:
    """Create a ReplayMark ClaimSpec observationally matching a legacy projection."""
    projection = str(projection)
    try:
        dimensions = _LEGACY_PROJECTIONS[projection]
    except KeyError as exc:
        raise ValueError(
            f"unsupported legacy AgentMark projection: {projection!r}"
        ) from exc
    return ClaimSpec(
        claim_id=claim_id or f"legacy-agentmark-{projection}",
        dimensions=dimensions,
        horizon=horizon,
        consequence_endpoint=consequence_endpoint,
    )


def compatibility_map() -> dict[str, str]:
    """Machine-readable boundary map for audit/report generation."""
    return {
        "agentmark.kernel.ReactiveKernel": (
            "replaymark.TargetModel via read-only adapter"
        ),
        "agentmark.kernel.EventKey.operation": "ProjectedAction.dimension['operation']",
        "agentmark.kernel.EventKey.target_class": (
            "ProjectedAction.dimension['target_class']"
        ),
        "agentmark.kernel.EventKey.variant": "ProjectedAction.dimension['variant']",
        "agentmark.kernel.EventKey.delay_ms": "ProjectedAction.dimension['delay_ms']",
        "agentmark.kernel.EventKey.next_state": "TargetModel distribution successor",
        "agentmark.semantics projection=operation": (
            "ClaimSpec dimensions=('operation',)"
        ),
        "agentmark.semantics projection=action": (
            "ClaimSpec dimensions=('operation','target_class','variant')"
        ),
        "agentmark.semantics projection=semantic": (
            "ClaimSpec dimensions=('operation','target_class','delay_ms')"
        ),
        "agentmark kernel/minimizer full signature": (
            "structural precedent only; successor state remains a TargetModel edge and "
            "is not exposed as a claim projection"
        ),
        "agentmark.minimize.quotient": (
            "algorithmic precedent only; NOT q_{C,H}; future compiler must be "
            "claim-relative and stop exactly at declared horizon"
        ),
        "agentmark.semantics.step_replay_validity": (
            "point-support precedent; future compiler generalizes to evidence-set "
            "VALID/INVALID/UNRESOLVED"
        ),
        "agentmark_theory.verify_theory": (
            "independent oracle; must not be imported by compiler"
        ),
        "n2_horizon_validate.py": (
            "independent live oracle; must not be imported by compiler"
        ),
    }
