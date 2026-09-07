from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from itertools import product
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.contracts import ClaimSpec, ProjectedAction
from replaymark.q_compiler import NonDeterministicTargetError, compile_bounded_q
from replaymark.target_provenance import (
    UnstableObservedTargetError,
    observe_target_semantics,
)
from replaymark_oracle.target_provenance_oracle import definition_target_semantic_digests
from replaymark_verification.models import (
    BetterThermostatFrozenModel,
    StochasticCurrentModel,
    TableTargetModel,
)


class DelegatingTarget:
    def __init__(self, inner, *, fingerprint: str | None = None, reverse_states: bool = False):
        self.inner = inner
        self._fingerprint = fingerprint
        self._reverse_states = reverse_states

    @property
    def fingerprint(self):
        return self.inner.fingerprint if self._fingerprint is None else self._fingerprint

    @property
    def decision_states(self):
        states = tuple(self.inner.decision_states)
        return tuple(reversed(states)) if self._reverse_states else states

    @property
    def continuation_alphabet(self):
        return tuple(self.inner.continuation_alphabet)

    def current_distribution(self, state):
        return self.inner.current_distribution(state)

    def advance_distribution(self, post_state, continuation):
        return self.inner.advance_distribution(post_state, continuation)


class ZeroMassDecorator(DelegatingTarget):
    def current_distribution(self, state):
        out = dict(self.inner.current_distribution(state))
        existing_post = next(iter(out))[1]
        zero = ProjectedAction.from_mapping({"operation": "ZERO", "variant": "ignored"})
        out[(zero, existing_post)] = Fraction(0, 1)
        return dict(reversed(tuple(out.items())))

    def advance_distribution(self, post_state, continuation):
        out = dict(self.inner.advance_distribution(post_state, continuation))
        states = tuple(self.inner.decision_states)
        zero_state = states[-1]
        if zero_state not in out:
            out[zero_state] = Fraction(0, 1)
        return dict(reversed(tuple(out.items())))


class StatefulCurrentTarget(DelegatingTarget):
    def __init__(self, inner):
        super().__init__(inner, fingerprint="stable-provider-label")
        self.calls = 0
        self.first_pass_calls = len(inner.decision_states)

    def current_distribution(self, state):
        self.calls += 1
        out = dict(self.inner.current_distribution(state))
        if self.calls <= self.first_pass_calls:
            return out
        action, post = next(iter(out))
        mutated = ProjectedAction.from_mapping({"operation": "MUTATED", "variant": None})
        return {(mutated, post): Fraction(1, 1)}


class ProbabilityVariant:
    @property
    def fingerprint(self):
        return "same-provider-label"

    @property
    def decision_states(self):
        return ("s",)

    @property
    def continuation_alphabet(self):
        return ("tick",)

    def __init__(self, p: Fraction):
        self.p = p

    def current_distribution(self, state):
        if state != "s":
            raise KeyError(state)
        a = ProjectedAction.from_mapping({"operation": "A"})
        b = ProjectedAction.from_mapping({"operation": "B"})
        return {(a, "s"): self.p, (b, "s"): Fraction(1, 1) - self.p}

    def advance_distribution(self, post_state, continuation):
        if post_state != "s" or continuation != "tick":
            raise KeyError((post_state, continuation))
        return {"s": Fraction(1, 1)}


def _assert_oracle(snapshot, target) -> None:
    expected = definition_target_semantic_digests(target)
    assert snapshot.domain_digest == expected["domain"]
    assert snapshot.current_semantics_digest == expected["current"]
    assert snapshot.advance_semantics_digest == expected["advance"]
    assert snapshot.semantic_digest == expected["root"]


def provider_independence_gate() -> dict[str, object]:
    base = TableTargetModel(
        outputs=("A", "B"),
        continuations=("0", "1"),
        next_state=((0, 1), (1, 0)),
    )
    left = DelegatingTarget(base, fingerprint="provider-label-left")
    right = DelegatingTarget(base, fingerprint="provider-label-right")
    s_left = observe_target_semantics(left)
    s_right = observe_target_semantics(right)
    assert s_left.semantic_digest == s_right.semantic_digest
    assert s_left.fingerprint() != s_right.fingerprint()

    changed = TableTargetModel(
        outputs=("A", "C"),
        continuations=("0", "1"),
        next_state=((0, 1), (1, 0)),
    )
    same_label_a = DelegatingTarget(base, fingerprint="shared-stale-label")
    same_label_b = DelegatingTarget(changed, fingerprint="shared-stale-label")
    a = observe_target_semantics(same_label_a)
    b = observe_target_semantics(same_label_b)
    assert a.provider_fingerprint == b.provider_fingerprint
    assert a.semantic_digest != b.semantic_digest
    assert a.domain_digest == b.domain_digest
    assert a.advance_semantics_digest == b.advance_semantics_digest
    assert a.current_semantics_digest != b.current_semantics_digest

    return {
        "same_semantics_different_provider_same_semantic_digest": True,
        "same_provider_changed_semantics_changes_semantic_digest": True,
        "component_localization_current_only": True,
    }


def canonical_semantics_gate() -> dict[str, object]:
    base = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=("0", "1"),
        next_state=((1, 2), (2, 0), (0, 1)),
    )
    baseline = observe_target_semantics(base)
    reverse_states = observe_target_semantics(DelegatingTarget(base, reverse_states=True))
    zero_mass = observe_target_semantics(ZeroMassDecorator(base, fingerprint=base.fingerprint))
    assert baseline.semantic_digest == reverse_states.semantic_digest == zero_mass.semantic_digest

    reverse_order_model = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=("0", "1"),
        next_state=((1, 2), (2, 0), (0, 1)),
        continuation_order=("1", "0"),
    )
    reordered = observe_target_semantics(reverse_order_model)
    assert baseline.semantic_digest == reordered.semantic_digest
    assert baseline.declared_continuation_order != reordered.declared_continuation_order
    assert baseline.fingerprint() != reordered.fingerprint()

    transition_changed = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=("0", "1"),
        next_state=((2, 2), (2, 0), (0, 1)),
    )
    changed = observe_target_semantics(transition_changed)
    assert baseline.domain_digest == changed.domain_digest
    assert baseline.current_semantics_digest == changed.current_semantics_digest
    assert baseline.advance_semantics_digest != changed.advance_semantics_digest
    assert baseline.semantic_digest != changed.semantic_digest

    _assert_oracle(baseline, base)
    _assert_oracle(reordered, reverse_order_model)

    return {
        "decision_state_order_invariant": True,
        "mapping_and_zero_mass_invariant": True,
        "continuation_tiebreak_order_excluded_from_semantic_root": True,
        "snapshot_fingerprint_binds_tiebreak_order": True,
        "component_localization_advance_only": True,
    }


def q_binding_gate() -> dict[str, object]:
    model = TableTargetModel(
        outputs=("climate.set_preset_mode", "climate.set_preset_mode"),
        variants=("preset=home", "preset=away"),
        continuations=("tick",),
        next_state=((0,), (1,)),
    )
    operation_claim = ClaimSpec("op", ("operation",), 1, "service")
    action_claim = ClaimSpec("action", ("operation", "variant"), 1, "service")
    q_op = compile_bounded_q(model, operation_claim)
    q_action = compile_bounded_q(model, action_claim)
    snapshot = observe_target_semantics(model)

    assert q_op.target_semantic_digest == snapshot.semantic_digest
    assert q_action.target_semantic_digest == snapshot.semantic_digest
    assert q_op.target_snapshot_fingerprint == snapshot.fingerprint()
    assert q_op.block_count(0) == 1
    assert q_action.block_count(0) == 2

    liar_a = DelegatingTarget(model, fingerprint="constant-provider-label")
    changed = TableTargetModel(
        outputs=("climate.set_preset_mode", "other.operation"),
        variants=("preset=home", "preset=away"),
        continuations=("tick",),
        next_state=((0,), (1,)),
    )
    liar_b = DelegatingTarget(changed, fingerprint="constant-provider-label")
    q_a = compile_bounded_q(liar_a, operation_claim)
    q_b = compile_bounded_q(liar_b, operation_claim)
    assert q_a.provider_fingerprint == q_b.provider_fingerprint
    assert q_a.target_semantic_digest != q_b.target_semantic_digest

    return {
        "semantic_digest_precedes_claim_projection": True,
        "same_target_digest_across_claims": True,
        "different_claims_can_produce_different_q": True,
        "stale_provider_label_cannot_hide_semantic_change": True,
    }


def stochastic_and_stability_gate() -> dict[str, object]:
    stochastic = StochasticCurrentModel()
    snapshot = observe_target_semantics(stochastic)
    _assert_oracle(snapshot, stochastic)
    assert len(snapshot.current_law("s")) == 2
    try:
        compile_bounded_q(
            stochastic,
            ClaimSpec("stochastic", ("operation",), 0, "event"),
        )
    except NonDeterministicTargetError:
        q_rejected = True
    else:
        raise AssertionError("deterministic q compiler must still reject stochastic target")

    p_half = observe_target_semantics(ProbabilityVariant(Fraction(1, 2)))
    p_third = observe_target_semantics(ProbabilityVariant(Fraction(1, 3)))
    assert p_half.domain_digest == p_third.domain_digest
    assert p_half.advance_semantics_digest == p_third.advance_semantics_digest
    assert p_half.current_semantics_digest != p_third.current_semantics_digest
    assert p_half.semantic_digest != p_third.semantic_digest

    stable_base = TableTargetModel(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    try:
        observe_target_semantics(StatefulCurrentTarget(stable_base))
    except UnstableObservedTargetError:
        stateful_rejected = True
    else:
        raise AssertionError("stateful target semantics must fail closed")

    original = observe_target_semantics(stable_base)
    try:
        replace(original, semantic_digest="0" * 64)
    except ValueError:
        forged_digest_rejected = True
    else:
        raise AssertionError("forged semantic root must be rejected")

    return {
        "stochastic_semantics_can_be_content_digested": True,
        "deterministic_q_scope_unchanged": q_rejected,
        "exact_probability_change_changes_digest": True,
        "stateful_target_adapter_rejected": stateful_rejected,
        "forged_snapshot_digest_rejected": forged_digest_rejected,
    }


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    snapshot = observe_target_semantics(target)
    _assert_oracle(snapshot, target)
    claim = ClaimSpec("bt-provenance", ("operation",), 4, "preset-action")
    quotient = compile_bounded_q(target, claim)
    assert [layer.block_count for layer in quotient.layers] == [5, 14, 16, 16, 16]
    assert quotient.target_semantic_digest == snapshot.semantic_digest
    return {
        "decision_states": len(snapshot.decision_states),
        "positive_post_states": len(snapshot.positive_post_states),
        "advance_laws": len(snapshot.advance_laws),
        "q_counts": [layer.block_count for layer in quotient.layers],
        "semantic_digest": snapshot.semantic_digest,
        "snapshot_fingerprint": snapshot.fingerprint(),
    }


def exhaustive_small_machine_gate() -> dict[str, object]:
    outputs = ("A", "B")
    continuations = ("0", "1")
    semantic_digests: set[str] = set()
    machines = 0
    oracle_agreements = 0

    for output_assignment in product(outputs, repeat=3):
        for flat_next in product(range(3), repeat=6):
            rows = (
                (flat_next[0], flat_next[1]),
                (flat_next[2], flat_next[3]),
                (flat_next[4], flat_next[5]),
            )
            model = TableTargetModel(
                outputs=tuple(output_assignment),
                continuations=continuations,
                next_state=rows,
            )
            wrapped = DelegatingTarget(model, fingerprint="same-provider-for-all-5832")
            snapshot = observe_target_semantics(wrapped)
            oracle = definition_target_semantic_digests(wrapped)
            assert snapshot.semantic_digest == oracle["root"]
            semantic_digests.add(snapshot.semantic_digest)
            machines += 1
            oracle_agreements += 1

    assert machines == 5832
    assert oracle_agreements == 5832
    assert len(semantic_digests) == 5832
    return {
        "machines": machines,
        "same_provider_label_for_all": True,
        "production_oracle_digest_agreements": oracle_agreements,
        "unique_labeled_semantic_digests": len(semantic_digests),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    report = {
        "schema": "replaymark.target-provenance.gate.v1",
        "provider_independence": provider_independence_gate(),
        "canonical_semantics": canonical_semantics_gate(),
        "q_binding": q_binding_gate(),
        "stochastic_and_stability": stochastic_and_stability_gate(),
        "better_thermostat": thermostat_gate(),
        "exhaustive_small_machine": exhaustive_small_machine_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
