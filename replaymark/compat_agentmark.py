from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import hashlib
import json
from typing import Any, Mapping

from .contracts import ClaimSpec, ProjectedAction, TargetModel


_ADAPTER_SCHEMA = "replaymark.compat.agentmark-reactive-kernel.v2-decision-state"
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


def _decision_state_id(controller_state: str, feedback: str) -> str:
    """Unambiguous stable ID for one legacy controller decision condition."""
    return json.dumps(
        [str(controller_state), str(feedback)],
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _parse_decision_state_id(value: str) -> tuple[str, str]:
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise KeyError(f"invalid legacy decision-state id: {value!r}") from exc
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not all(isinstance(x, str) for x in decoded)
    ):
        raise KeyError(f"invalid legacy decision-state id: {value!r}")
    return decoded[0], decoded[1]


class _AgentMarkReactiveKernelAdapter:
    """Read-only two-phase lift of the frozen AgentMark ReactiveKernel.

    A legacy decision condition is `(controller_state, current_feedback)`.
    Executing that condition yields the legacy action and its post-controller
    state. A future feedback symbol then forms the next decision condition.
    This exactly matches the previously frozen E3b q_{C,H} semantics while
    leaving the historical AgentMark package byte-untouched.
    """

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
        self._controller_states = tuple(sorted(str(s) for s in kernel.states))
        self._continuations = tuple(str(y) for y in kernel.feedback_alphabet)
        if len(set(self._continuations)) != len(self._continuations):
            raise ValueError("legacy feedback alphabet contains duplicate symbols")

        decision_states: list[str] = []
        pairs: dict[str, tuple[str, str]] = {}
        for state in self._controller_states:
            for feedback in self._continuations:
                if kernel.has_feedback(state, feedback):
                    identifier = _decision_state_id(state, feedback)
                    decision_states.append(identifier)
                    pairs[identifier] = (state, feedback)
        if not decision_states:
            raise ValueError("legacy kernel exposes no supported decision conditions")
        self._decision_states = tuple(sorted(decision_states))
        self._pairs = pairs

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def decision_states(self) -> tuple[str, ...]:
        return self._decision_states

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return self._continuations

    def current_distribution(
        self,
        decision_state: str,
    ) -> Mapping[tuple[ProjectedAction, str], Fraction]:
        decision_state = str(decision_state)
        try:
            state, feedback = self._pairs[decision_state]
        except KeyError as exc:
            _parse_decision_state_id(decision_state)
            raise KeyError(f"unknown legacy decision state: {decision_state!r}") from exc

        out: dict[tuple[ProjectedAction, str], Fraction] = defaultdict(Fraction)
        for atom in self._kernel.atoms(state, feedback):
            probability = Fraction(atom.probability)
            if probability < 0:
                raise ValueError("legacy kernel emitted negative probability")
            if probability == 0:
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
            post_state = str(event.next_state)
            if post_state not in self._controller_states:
                raise ValueError(
                    f"legacy kernel emitted unknown post-controller state: {post_state!r}"
                )
            out[(action, post_state)] += probability

        total = sum(out.values(), Fraction(0, 1))
        if total != 1:
            raise ValueError(
                f"adapted current transition mass for {state}/{feedback} is {total}, not 1"
            )
        return dict(out)

    def advance_distribution(
        self,
        post_state: str,
        continuation: str,
    ) -> Mapping[str, Fraction]:
        post_state = str(post_state)
        continuation = str(continuation)
        if post_state not in self._controller_states:
            raise KeyError(f"unknown legacy post-controller state: {post_state!r}")
        if continuation not in self._continuations:
            raise KeyError(f"unknown legacy future feedback: {continuation!r}")
        if not self._kernel.has_feedback(post_state, continuation):
            raise KeyError(
                "future feedback is not admitted after legacy post-state: "
                f"{post_state!r}/{continuation!r}"
            )
        next_decision = _decision_state_id(post_state, continuation)
        if next_decision not in self._pairs:
            raise AssertionError("adapter decision-state lift is internally inconsistent")
        return {next_decision: Fraction(1, 1)}


def target_model_from_agentmark_kernel(kernel: Any) -> TargetModel:
    """Lift the frozen AgentMark ReactiveKernel without rewriting it."""
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
            "replaymark.TargetModel via read-only two-phase decision-state adapter"
        ),
        "legacy decision condition": (
            "TargetModel decision_state = canonical JSON [controller_state,current_feedback]"
        ),
        "agentmark.kernel.EventKey.operation": "ProjectedAction.dimension['operation']",
        "agentmark.kernel.EventKey.target_class": (
            "ProjectedAction.dimension['target_class']"
        ),
        "agentmark.kernel.EventKey.variant": "ProjectedAction.dimension['variant']",
        "agentmark.kernel.EventKey.delay_ms": "ProjectedAction.dimension['delay_ms']",
        "agentmark.kernel.EventKey.next_state": (
            "TargetModel current_distribution post-decision state"
        ),
        "future AgentMark feedback": (
            "TargetModel advance_distribution continuation -> next decision condition"
        ),
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
            "structural precedent only; successor state remains model structure and "
            "is not exposed as a claim projection"
        ),
        "agentmark.minimize.quotient": (
            "algorithmic precedent only; NOT q_{C,H}; ReplayMark compiler is "
            "claim-relative and stops exactly at declared horizon"
        ),
        "agentmark.semantics.step_replay_validity": (
            "point-support precedent; later compiler stage generalizes to evidence-set "
            "VALID/INVALID/UNRESOLVED"
        ),
        "agentmark_theory.verify_theory": (
            "independent oracle; must not be imported by compiler"
        ),
        "n2_horizon_validate.py": (
            "independent live oracle; must not be imported by compiler"
        ),
    }


__all__ = (
    "claim_from_agentmark_projection",
    "compatibility_map",
    "target_model_from_agentmark_kernel",
)
