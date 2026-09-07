from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "agentmark_e3b_lab"
for path in (ROOT, LEGACY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agentmark.kernel import ReactiveKernel

from replaymark import ClaimSpec, EvidenceSpec, ProjectedAction, TargetModel
from replaymark.compat_agentmark import (
    claim_from_agentmark_projection,
    compatibility_map,
    target_model_from_agentmark_kernel,
)


def main() -> None:
    kernel = ReactiveKernel(
        {
            "initial_state": "s",
            "feedback_alphabet": ["home", "away"],
            "states": {
                "s": {
                    "home": [
                        {
                            "p": 1,
                            "operation": "climate.set_preset_mode",
                            "target_class": "climate",
                            "variant": "preset=home",
                            "next_state": "s",
                        },
                        {
                            "p": 0,
                            "operation": "never",
                            "target_class": "climate",
                            "variant": "zero-mass",
                            "next_state": "s",
                        },
                    ],
                    "away": [
                        {
                            "p": 1,
                            "operation": "climate.set_preset_mode",
                            "target_class": "climate",
                            "variant": "preset=away",
                            "next_state": "s",
                        }
                    ],
                }
            },
        }
    )

    model = target_model_from_agentmark_kernel(kernel)
    assert isinstance(model, TargetModel)
    assert len(model.decision_states) == 2
    assert model.continuation_alphabet == ("home", "away")
    assert len(model.fingerprint) == 64

    current = [model.current_distribution(state) for state in model.decision_states]
    assert all(sum(dist.values(), Fraction()) == 1 for dist in current)
    assert all(len(dist) == 1 for dist in current)
    post_states = {next(iter(dist))[1] for dist in current}
    assert post_states == {"s"}
    for feedback in model.continuation_alphabet:
        advanced = model.advance_distribution("s", feedback)
        assert sum(advanced.values(), Fraction()) == 1
        assert next(iter(advanced)) in model.decision_states
    try:
        model.advance_distribution("s", "unknown")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown future feedback must fail closed")

    actions = [next(iter(dist))[0] for dist in current]
    op_claim = claim_from_agentmark_projection("operation")
    action_claim = claim_from_agentmark_projection("action")
    assert op_claim.project(actions[0]) == op_claim.project(actions[1])
    assert action_claim.project(actions[0]) != action_claim.project(actions[1])
    exact_target_claim = ClaimSpec(
        "exact-target",
        ("operation", "target_identity", "variant"),
        0,
        "controller-event",
    )
    try:
        exact_target_claim.project(actions[0])
    except KeyError:
        pass
    else:
        raise AssertionError("legacy adapter must not invent exact target identity")
    try:
        claim_from_agentmark_projection("full")
    except ValueError:
        pass
    else:
        raise AssertionError("legacy full signature must remain structural precedent")

    a = ProjectedAction.from_mapping({"variant": "x", "operation": "op"})
    b = ProjectedAction.from_mapping({"operation": "op", "variant": "x"})
    assert a == b

    c1 = ClaimSpec("c", ("variant", "operation"), 1, "endpoint")
    c2 = ClaimSpec("c", ("operation", "variant"), 1, "endpoint")
    assert c1 == c2
    assert c1.fingerprint() == c2.fingerprint()

    decision_states = model.decision_states
    e1 = EvidenceSpec(
        "e",
        (("obs-b", (decision_states[1], decision_states[0])), ("obs-a", (decision_states[0],))),
    )
    e2 = EvidenceSpec(
        "e",
        (("obs-a", (decision_states[0],)), ("obs-b", tuple(sorted(decision_states)))),
    )
    assert e1 == e2
    assert e1.fingerprint() == e2.fingerprint()
    assert e1.compatible_states("obs-b") == tuple(sorted(decision_states))
    try:
        e1.compatible_states("unknown")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown evidence must fail closed")

    mapping = compatibility_map()
    assert "agentmark.minimize.quotient" in mapping
    assert "NOT q_{C,H}" in mapping["agentmark.minimize.quotient"]
    assert "two-phase" in mapping["agentmark.kernel.ReactiveKernel"]

    print(
        "REPLAYMARK_COMPILER_CONTRACT_SEED_V2: PASS "
        f"target_model={model.fingerprint} claim={c1.fingerprint()} "
        f"evidence={e1.fingerprint()}"
    )


if __name__ == "__main__":
    main()
