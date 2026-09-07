from __future__ import annotations

"""High-assurance differential verification for three-valued adjudication."""

import argparse
from dataclasses import replace
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.adjudicator import ClaimArtifactMismatchError, MalformedSupportEnvelopeError, adjudicate_support
from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction, Verdict
from replaymark.evidence_image import compile_evidence_image
from replaymark.q_compiler import compile_bounded_q
from replaymark.support_envelope import ObservationSupportEnvelope, compile_support_envelope
from replaymark_oracle.adjudication_oracle import OracleAdjudicationError, definition_adjudicate
from replaymark_verification.evidence_models import compile_expected_evidence
from replaymark_verification.models import BetterThermostatFrozenModel, TableTargetModel


def _action(operation: str, **extra) -> ProjectedAction:
    values = {"operation": operation}; values.update(extra)
    return ProjectedAction.from_mapping(values)


def _pipeline(target, claim, expected, depth: int):
    quotient = compile_bounded_q(target, claim)
    compiled_evidence = compile_expected_evidence(target, expected)
    image = compile_evidence_image(quotient, compiled_evidence, depth=depth)
    envelope = compile_support_envelope(quotient, image)
    return quotient, image, envelope


def _assert_matches_oracle(target, claim, expected, envelope, token, action):
    production = adjudicate_support(envelope, claim, token, action)
    oracle = definition_adjudicate(target, claim, expected, token, action)
    assert production.projected_action == oracle.projected_action
    assert production.verdict is oracle.verdict
    if production.verdict is Verdict.VALID:
        assert production.in_guaranteed_support and production.in_possible_support
        assert oracle.supporting_states == oracle.compatible_states and not oracle.excluding_states
    elif production.verdict is Verdict.INVALID:
        assert not production.in_guaranteed_support and not production.in_possible_support
        assert not oracle.supporting_states and oracle.excluding_states == oracle.compatible_states
    else:
        assert production.verdict is Verdict.UNRESOLVED
        assert not production.in_guaranteed_support and production.in_possible_support
        assert oracle.supporting_states and oracle.excluding_states
    return production, oracle


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec("bt-three-valued-adjudication", ("operation",), 2, "consequential-preset-service-action")
    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    nt_sleep = target.encode(True, False, False, "sleep")
    at_target = target.encode(True, False, False, "home")
    expected = EvidenceSpec("bt-adjudication-evidence", (("n2b-pair", (n2a, n2b)), ("with-at-target", (nt_sleep, at_target)), ("stronger-single", (nt_sleep,))))
    quotient = compile_bounded_q(target, claim)
    compiled_evidence = compile_expected_evidence(target, expected)
    n2b_verdicts = []; n2b_q_counts = []
    for depth in range(3):
        image = compile_evidence_image(quotient, compiled_evidence, depth=depth)
        envelope = compile_support_envelope(quotient, image)
        n2b_q_counts.append(image.observation("n2b-pair").predictive_world_count)
        valid, _ = _assert_matches_oracle(target, claim, expected, envelope, "n2b-pair", _action("SET_AWAY"))
        invalid, _ = _assert_matches_oracle(target, claim, expected, envelope, "n2b-pair", _action("SET_HOME"))
        assert valid.verdict is Verdict.VALID and invalid.verdict is Verdict.INVALID
        n2b_verdicts.append(valid.verdict.value)
    assert n2b_q_counts == [1, 2, 2]
    image2 = compile_evidence_image(quotient, compiled_evidence, depth=2)
    envelope2 = compile_support_envelope(quotient, image2)
    unresolved_home, oracle_home = _assert_matches_oracle(target, claim, expected, envelope2, "with-at-target", _action("SET_HOME"))
    unresolved_noop, oracle_noop = _assert_matches_oracle(target, claim, expected, envelope2, "with-at-target", _action("NO_ACTION"))
    invalid_away, _ = _assert_matches_oracle(target, claim, expected, envelope2, "with-at-target", _action("SET_AWAY"))
    assert unresolved_home.verdict is Verdict.UNRESOLVED and unresolved_noop.verdict is Verdict.UNRESOLVED and invalid_away.verdict is Verdict.INVALID
    assert len(oracle_home.supporting_states) == len(oracle_home.excluding_states) == 1
    assert len(oracle_noop.supporting_states) == len(oracle_noop.excluding_states) == 1
    stronger, _ = _assert_matches_oracle(target, claim, expected, envelope2, "stronger-single", _action("SET_HOME"))
    stronger_noop, _ = _assert_matches_oracle(target, claim, expected, envelope2, "stronger-single", _action("NO_ACTION"))
    assert stronger.verdict is Verdict.VALID and stronger_noop.verdict is Verdict.INVALID
    plain = adjudicate_support(envelope2, claim, "stronger-single", _action("SET_HOME"))
    decorated = adjudicate_support(envelope2, claim, "stronger-single", _action("SET_HOME", variant="ignored", delay_ms=999))
    assert plain.projected_action == decorated.projected_action
    assert plain.canonical_bytes() == decorated.canonical_bytes() and plain.fingerprint() == decorated.fingerprint()
    return {"q_counts": [layer.block_count for layer in quotient.layers], "n2b_q_image_counts": n2b_q_counts, "n2b_recorded_set_away": n2b_verdicts, "mixed_set_home": unresolved_home.verdict.value, "mixed_no_action": unresolved_noop.verdict.value, "mixed_set_away": invalid_away.verdict.value, "stronger_set_home": stronger.verdict.value, "stronger_no_action": stronger_noop.verdict.value, "projection_invariance": True, "sample_adjudication_fingerprint": plain.fingerprint()}


def fail_closed_and_binding_gate() -> dict[str, bool]:
    target = TableTargetModel(outputs=("A", "B"), continuations=("x",), next_state=((0,), (1,)))
    claim = ClaimSpec("binding-claim", ("operation",), 1, "event")
    expected = EvidenceSpec("binding-evidence", (("both", ("s0", "s1")),))
    _q, _image, envelope = _pipeline(target, claim, expected, 1)
    foreign_claim = ClaimSpec("different-claim-id", ("operation",), 1, "event")
    try: adjudicate_support(envelope, foreign_claim, "both", _action("A"))
    except ClaimArtifactMismatchError: foreign_claim_rejected = True
    else: raise AssertionError("foreign claim must fail")
    try: adjudicate_support(envelope, claim, "both", ProjectedAction.from_mapping({"variant": "missing-operation"}))
    except KeyError: missing_dimension_rejected = True
    else: raise AssertionError("missing dimension must fail")
    try: adjudicate_support(envelope, claim, "unknown-token", _action("A"))
    except KeyError: unknown_token_rejected = True
    else: raise AssertionError("unknown token must fail")
    valid_row = envelope.observation("both")
    malformed_row = ObservationSupportEnvelope(token="both", q_blocks=valid_row.q_blocks, guaranteed_support=(_action("A"),), possible_support=(_action("B"),))
    malformed = replace(envelope, observations=(malformed_row,))
    try: adjudicate_support(malformed, claim, "both", _action("A"))
    except MalformedSupportEnvelopeError: malformed_envelope_rejected = True
    else: raise AssertionError("malformed S-/S+ must fail")
    try: definition_adjudicate(target, claim, expected, "unknown-token", _action("A"))
    except OracleAdjudicationError: oracle_unknown_token_rejected = True
    else: raise AssertionError("oracle unknown token must fail")
    return {"foreign_claim_rejected": foreign_claim_rejected, "missing_dimension_rejected": missing_dimension_rejected, "unknown_token_rejected": unknown_token_rejected, "malformed_envelope_rejected": malformed_envelope_rejected, "oracle_unknown_token_rejected": oracle_unknown_token_rejected}


class StochasticAdjudicationModel:
    @property
    def fingerprint(self) -> str: return "stochastic-three-valued-adjudication-fixture"
    @property
    def decision_states(self) -> tuple[str, ...]: return ("s0", "s1")
    @property
    def continuation_alphabet(self) -> tuple[str, ...]: return ()
    def current_distribution(self, decision_state: str):
        a,b,c,z = (_action("A"),_action("B"),_action("C"),_action("ZERO"))
        if decision_state == "s0": return {(a,"p0a"):Fraction(1,2),(b,"p0b"):Fraction(1,2),(z,"p0z"):Fraction(0,1)}
        if decision_state == "s1": return {(b,"p1b"):Fraction(1,2),(c,"p1c"):Fraction(1,2),(z,"p1z"):Fraction(0,1)}
        raise KeyError(decision_state)
    def advance_distribution(self, post_state: str, continuation: str): raise KeyError((post_state, continuation))


def stochastic_definition_gate() -> dict[str, object]:
    target = StochasticAdjudicationModel(); claim = ClaimSpec("stochastic-adjudication", ("operation",), 0, "event")
    evidence = EvidenceSpec("stochastic-adjudication-evidence", (("both", ("s0", "s1")),))
    valid = definition_adjudicate(target, claim, evidence, "both", _action("B")); unresolved = definition_adjudicate(target, claim, evidence, "both", _action("A")); invalid = definition_adjudicate(target, claim, evidence, "both", _action("ZERO"))
    assert valid.verdict is Verdict.VALID and unresolved.verdict is Verdict.UNRESOLVED and invalid.verdict is Verdict.INVALID
    return {"B": valid.verdict.value, "A": unresolved.verdict.value, "zero_mass_action": invalid.verdict.value, "zero_mass_is_not_support": True}


def exhaustive_deterministic_gate() -> dict[str, object]:
    outputs=("A","B"); continuations=("0","1"); claim=ClaimSpec("adjudication-exhaustive",("operation",),2,"event"); states=("s0","s1","s2")
    expected=EvidenceSpec("all-nonempty-subsets", tuple((f"e{mask}", tuple(state for i,state in enumerate(states) if mask&(1<<i))) for mask in range(1,8)))
    candidates=tuple(_action(output) for output in outputs); machine_count=0; checked=0; verdict_counts={v.value:0 for v in Verdict}; start=time.perf_counter()
    for output_assignment in product(outputs, repeat=3):
        for flat_next in product(range(3), repeat=6):
            rows=((flat_next[0],flat_next[1]),(flat_next[2],flat_next[3]),(flat_next[4],flat_next[5]))
            target=TableTargetModel(outputs=tuple(output_assignment),continuations=continuations,next_state=rows)
            quotient=compile_bounded_q(target,claim); compiled_evidence=compile_expected_evidence(target,expected); image=compile_evidence_image(quotient,compiled_evidence,depth=2); envelope=compile_support_envelope(quotient,image)
            for token,_subset in expected.observations:
                for candidate in candidates:
                    production,oracle=_assert_matches_oracle(target,claim,expected,envelope,token,candidate); assert production.verdict is oracle.verdict; verdict_counts[production.verdict.value]+=1; checked+=1
            machine_count+=1
    assert machine_count==5832 and checked==5832*7*2 and all(count>0 for count in verdict_counts.values())
    return {"machines":machine_count,"evidence_sets_per_machine":7,"recorded_actions_per_evidence":2,"compiler_oracle_adjudications":checked,"verdict_counts":verdict_counts,"horizon":2,"elapsed_seconds":round(time.perf_counter()-start,6)}


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--out"); args=parser.parse_args()
    report={"schema":"replaymark.three-valued-adjudication.compiler_oracle_gate.v2-derived-evidence","thermostat":thermostat_gate(),"fail_closed_and_binding":fail_closed_and_binding_gate(),"stochastic_definition_oracle":stochastic_definition_gate(),"exhaustive_deterministic":exhaustive_deterministic_gate(),"verdict":"PASS"}
    text=json.dumps(report,indent=2,sort_keys=True); print(text)
    if args.out: Path(args.out).write_text(text+"\n",encoding="utf-8")


if __name__ == "__main__": main()
