from __future__ import annotations

"""Differential verification for compiler-derived evidence -> q_{C,H} image."""

import argparse
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.contracts import ClaimSpec, EvidenceSpec
from replaymark.evidence_image import compile_evidence_image
from replaymark.q_compiler import compile_bounded_q
from replaymark_oracle.evidence_image_oracle import definition_evidence_image
from replaymark_verification.evidence_models import compile_expected_evidence
from replaymark_verification.models import (
    BetterThermostatFrozenModel,
    TableTargetModel,
)


def _production_semantic_blocks(quotient, image, token: str) -> tuple[tuple[str, ...], ...]:
    members = dict(quotient.layer(image.depth).blocks)
    return tuple(sorted(members[block] for block in image.blocks_for(token)))


def _assert_matches_definition(target, claim, quotient, expected, depth: int) -> None:
    compiled_evidence = compile_expected_evidence(target, expected)
    production = compile_evidence_image(quotient, compiled_evidence, depth=depth)
    oracle = definition_evidence_image(target, claim, expected, depth=depth)
    for token, _ in expected.observations:
        observed = _production_semantic_blocks(quotient, production, token)
        expected_blocks = oracle.observation(token).semantic_blocks
        assert observed == expected_blocks, (depth, token, observed, expected_blocks)


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec(
        "bt-evidence-image",
        ("operation",),
        2,
        "consequential-preset-service-action",
    )
    quotient = compile_bounded_q(target, claim)

    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    nt_home = target.encode(True, False, False, "away")
    nt_comfort = target.encode(True, False, False, "comfort")
    nt_sleep = target.encode(True, False, False, "sleep")
    at_target = target.encode(True, False, False, "home")

    expected = EvidenceSpec(
        "bt-evidence-image-fixture",
        (
            ("n2b-pair", (n2a, n2b)),
            ("overwritten-nontargets", (nt_sleep, nt_home, nt_comfort)),
            ("with-at-target", (nt_sleep, at_target)),
            ("single", (n2a,)),
        ),
    )
    compiled_evidence = compile_expected_evidence(target, expected)

    for depth in range(3):
        _assert_matches_definition(target, claim, quotient, expected, depth)

    image0 = compile_evidence_image(quotient, compiled_evidence, depth=0)
    image1 = compile_evidence_image(quotient, compiled_evidence, depth=1)
    image2 = compile_evidence_image(quotient, compiled_evidence, depth=2)

    assert image0.observation("n2b-pair").predictive_world_count == 1
    assert image1.observation("n2b-pair").predictive_world_count == 2
    assert image2.observation("n2b-pair").predictive_world_count == 2
    assert image2.observation("overwritten-nontargets").raw_world_count == 3
    assert image2.observation("overwritten-nontargets").predictive_world_count == 1
    assert image2.observation("with-at-target").predictive_world_count == 2
    assert image2.observation("single").predictive_world_count == 1

    pair_blocks = set(image2.blocks_for("n2b-pair"))
    single_blocks = set(image2.blocks_for("single"))
    assert single_blocks < pair_blocks

    return {
        "q_counts": [layer.block_count for layer in quotient.layers],
        "n2b_image_counts": [
            image0.observation("n2b-pair").predictive_world_count,
            image1.observation("n2b-pair").predictive_world_count,
            image2.observation("n2b-pair").predictive_world_count,
        ],
        "overwritten_raw_worlds": 3,
        "overwritten_q_worlds_h2": 1,
        "with_at_target_q_worlds_h2": 2,
        "image_fingerprint_h2": image2.fingerprint(),
    }


def canonical_and_fail_closed_gate() -> dict[str, bool]:
    target = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=("x",),
        next_state=((0,), (1,), (2,)),
    )
    claim = ClaimSpec("canonical", ("operation",), 1, "event")
    quotient = compile_bounded_q(target, claim)

    e1 = EvidenceSpec("same", (("beta", ("s2", "s1")), ("alpha", ("s1", "s0"))))
    e2 = EvidenceSpec("same", (("alpha", ("s0", "s1")), ("beta", ("s1", "s2"))))
    c1 = compile_expected_evidence(target, e1)
    c2 = compile_expected_evidence(target, e2)
    i1 = compile_evidence_image(quotient, c1)
    i2 = compile_evidence_image(quotient, c2)
    assert i1.fingerprint() == i2.fingerprint()
    assert i1.canonical_bytes() == i2.canonical_bytes()

    try:
        compile_evidence_image(quotient, e1)  # type: ignore[arg-type]
    except TypeError:
        manual_inverse_rejected = True
    else:
        raise AssertionError("production evidence image must reject manual EvidenceSpec")

    try:
        compile_evidence_image(quotient, c1, depth=2)
    except IndexError:
        deeper_rejected = True
    else:
        raise AssertionError("evidence image must not invent an uncompiled H+1 layer")

    return {
        "canonical_order_invariant": True,
        "manual_inverse_rejected": manual_inverse_rejected,
        "no_hidden_deeper_layer": deeper_rejected,
    }


def exhaustive_h0_set_image_gate() -> dict[str, int]:
    labels = ("A", "B", "C")
    states = ("s0", "s1", "s2")
    checked = 0
    distinct_relations: set[tuple[tuple[str, ...], ...]] = set()

    for outputs in product(labels, repeat=3):
        target = TableTargetModel(
            outputs=tuple(outputs),
            continuations=("x",),
            next_state=((0,), (1,), (2,)),
        )
        claim = ClaimSpec("exhaustive-h0", ("operation",), 0, "event")
        quotient = compile_bounded_q(target, claim)
        distinct_relations.add(tuple(sorted(members for _, members in quotient.layer(0).blocks)))

        for mask in range(1, 1 << len(states)):
            subset = tuple(state for i, state in enumerate(states) if mask & (1 << i))
            expected = EvidenceSpec("subset", (("e", subset),))
            _assert_matches_definition(target, claim, quotient, expected, 0)
            checked += 1

    assert len(distinct_relations) == 5
    assert checked == 27 * 7
    return {
        "output_assignments": 27,
        "nonempty_evidence_sets_per_assignment": 7,
        "evidence_images_checked": checked,
        "distinct_q_relations_exercised": len(distinct_relations),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    result = {
        "schema": "replaymark.qch-evidence-image.gate.v2-derived-evidence",
        "thermostat": thermostat_gate(),
        "boundary": canonical_and_fail_closed_gate(),
        "exhaustive_h0": exhaustive_h0_set_image_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
