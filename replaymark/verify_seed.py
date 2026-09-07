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
    assert model.initial_state == "s"
    assert model.states == ("s",)
    assert model.feedback_alphabet == ("home", "away")
    assert len(model.fingerprint) == 64

    home_dist = model.distribution("s", "home")
    away_dist = model.distribution("s", "away")
    assert sum(home_dist.values(), Fraction()) == 1
    assert sum(away_dist.values(), Fraction()) == 1
    assert len(home_dist) == 1  # zero-mass legacy syntax is semantically absent
    try:
        model.has_feedback("s", "unknown")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown feedback must fail closed")

    home_action = next(iter(home_dist))[0]
    away_action = next(iter(away_dist))[0]
    op_claim = claim_from_agentmark_projection("operation")
    action_claim = claim_from_agentmark_projection("action")
    assert op_claim.project(home_action) == op_claim.project(away_action)
    assert action_claim.project(home_action) != action_claim.project(away_action)
    exact_target_claim = ClaimSpec(
        "exact-target",
        ("operation", "target_identity", "variant"),
        0,
        "controller-event",
    )
    try:
        exact_target_claim.project(home_action)
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

    # Canonicalization is insertion-order independent.
    a = ProjectedAction.from_mapping({"variant": "x", "operation": "op"})
    b = ProjectedAction.from_mapping({"operation": "op", "variant": "x"})
    assert a == b

    c1 = ClaimSpec("c", ("variant", "operation"), 1, "endpoint")
    c2 = ClaimSpec("c", ("operation", "variant"), 1, "endpoint")
    assert c1 == c2
    assert c1.fingerprint() == c2.fingerprint()

    e1 = EvidenceSpec("e", (("obs-b", ("s2", "s1")), ("obs-a", ("s1",)),))
    e2 = EvidenceSpec("e", (("obs-a", ("s1",)), ("obs-b", ("s1", "s2")),))
    assert e1 == e2
    assert e1.fingerprint() == e2.fingerprint()
    assert e1.compatible_states("obs-b") == ("s1", "s2")
    try:
        e1.compatible_states("unknown")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown evidence must fail closed")

    mapping = compatibility_map()
    assert "agentmark.minimize.quotient" in mapping
    assert "NOT q_{C,H}" in mapping["agentmark.minimize.quotient"]

    print(
        "REPLAYMARK_COMPILER_CONTRACT_SEED: PASS "
        f"target_model={model.fingerprint} claim={c1.fingerprint()} "
        f"evidence={e1.fingerprint()}"
    )


if __name__ == "__main__":
    main()
