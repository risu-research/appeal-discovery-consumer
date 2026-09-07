from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.adjudicator import Adjudication
from replaymark.contracts import ProjectedAction, Verdict
from replaymark.rstar import RStarDecision, ReuseDisposition
from replaymark.runtime_e3b_observation import (
    E3B_CONFIRMED_BY_DEADLINE,
    E3B_NOT_VISIBLE_BY_DEADLINE,
    E3B_OBSERVATION_REALIZER_ID,
    E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST,
    E3B_RAW_OBSERVATION_SCHEMA,
    e3b_observation_realizer_rule_record,
    realize_e3b_observation,
)
from replaymark.runtime_realization import (
    RealizationError,
    RealizationFailureCode,
    RealizationProvenance,
    RealizationStage,
    RealizedHistoricalAction,
    RuntimeReuseCertificate,
)
from replaymark_oracle.e3b_observation_oracle import definition_realize_e3b_observation


def _event(
    event_id: str,
    recv: int,
    *,
    device: str = "device-a",
    on: bool = True,
    domain: str = "mono:test",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "device": device,
        "on": on,
        "recv_mono_ns": recv,
        "clock_domain": domain,
    }


def _raw(
    *,
    command: int = 100,
    deadline: int = 200,
    closed_at: int | None = None,
    domain: str = "mono:test",
    expected_device: str = "device-a",
    events: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if closed_at is None:
        closed_at = deadline
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": domain,
        "expected_device": expected_device,
        "command_publish_mono_ns": command,
        "verify_deadline_mono_ns": deadline,
        "closed_at_mono_ns": closed_at,
        "events": [] if events is None else events,
    }


def _prod(raw: object) -> dict[str, object]:
    try:
        realized = realize_e3b_observation(raw)
    except RealizationError as exc:
        return {
            "ok": False,
            "error_code": exc.failure.code.value,
            "token": None,
            "boundary_timestamp_ns": None,
            "source_event_timestamp_ns": None,
        }
    return {
        "ok": True,
        "error_code": None,
        "token": realized.evidence_token,
        "boundary_timestamp_ns": realized.boundary_timestamp_ns,
        "source_event_timestamp_ns": realized.source_event_timestamp_ns,
    }


def _oracle(raw: object) -> dict[str, object]:
    value = definition_realize_e3b_observation(raw)
    return {
        "ok": value.ok,
        "error_code": value.error_code,
        "token": value.token,
        "boundary_timestamp_ns": value.boundary_timestamp_ns,
        "source_event_timestamp_ns": value.source_event_timestamp_ns,
    }


def named_boundary_gate() -> dict[str, object]:
    absent = realize_e3b_observation(_raw())
    assert absent.evidence_token == E3B_NOT_VISIBLE_BY_DEADLINE
    assert absent.boundary_timestamp_ns == 200
    assert absent.source_event_timestamp_ns is None

    before = realize_e3b_observation(_raw(events=[_event("e", 199)]))
    assert before.evidence_token == E3B_CONFIRMED_BY_DEADLINE
    assert before.source_event_timestamp_ns == 199

    exact = realize_e3b_observation(_raw(events=[_event("e", 200)]))
    assert exact.evidence_token == E3B_CONFIRMED_BY_DEADLINE
    assert exact.source_event_timestamp_ns == 200
    assert exact.boundary_timestamp_ns == 200

    old_history = realize_e3b_observation(_raw(events=[_event("old", 99)]))
    assert old_history.evidence_token == E3B_NOT_VISIBLE_BY_DEADLINE

    later_event = realize_e3b_observation(
        _raw(closed_at=250, events=[_event("late", 220)])
    )
    assert later_event.evidence_token == E3B_NOT_VISIBLE_BY_DEADLINE

    irrelevant = realize_e3b_observation(
        _raw(
            events=[
                _event("other-device", 150, device="device-b"),
                _event("off", 160, on=False),
            ]
        )
    )
    assert irrelevant.evidence_token == E3B_NOT_VISIBLE_BY_DEADLINE

    expected_failures = {
        "missing_events": (
            {
                key: value
                for key, value in _raw().items()
                if key != "events"
            },
            RealizationFailureCode.MISSING_REQUIRED_FIELD,
        ),
        "insufficient_closure": (
            _raw(closed_at=199),
            RealizationFailureCode.OUT_OF_BOUNDARY,
        ),
        "duplicate_event": (
            _raw(events=[_event("same", 150), _event("same", 160)]),
            RealizationFailureCode.DUPLICATE_INPUT,
        ),
        "cross_clock": (
            _raw(events=[_event("e", 150, domain="mono:other")]),
            RealizationFailureCode.CLOCK_DOMAIN_MISMATCH,
        ),
        "after_snapshot_close": (
            _raw(closed_at=210, events=[_event("e", 211)]),
            RealizationFailureCode.OUT_OF_BOUNDARY,
        ),
        "multiple_matching": (
            _raw(events=[_event("e1", 150), _event("e2", 160)]),
            RealizationFailureCode.AMBIGUOUS_REALIZATION,
        ),
    }
    seen: dict[str, str] = {}
    for name, (raw, code) in expected_failures.items():
        try:
            realize_e3b_observation(raw)
        except RealizationError as exc:
            assert exc.failure.code is code
            assert "verdict" not in exc.failure.canonical_record()
            seen[name] = exc.failure.code.value
        else:
            raise AssertionError(f"{name} should fail closed")

    reordered = {
        "events": [_event("e", 150)],
        "closed_at_mono_ns": 200,
        "verify_deadline_mono_ns": 200,
        "command_publish_mono_ns": 100,
        "expected_device": "device-a",
        "clock_domain": "mono:test",
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
    }
    a = realize_e3b_observation(_raw(events=[_event("e", 150)]))
    b = realize_e3b_observation(reordered)
    assert a.canonical_bytes() == b.canonical_bytes()
    assert a.fingerprint() == b.fingerprint()

    c = realize_e3b_observation(_raw(command=300, deadline=400))
    assert (
        a.provenance.realizer_semantic_digest
        == c.provenance.realizer_semantic_digest
        == E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST
    )
    assert a.provenance.raw_record_digest != c.provenance.raw_record_digest
    assert a.provenance.realizer_id == E3B_OBSERVATION_REALIZER_ID

    return {
        "complete_snapshot_absence_is_negative_evidence": True,
        "deadline_is_inclusive": True,
        "pre_command_history_ignored": True,
        "post_deadline_preclosure_events_ignored": True,
        "irrelevant_device_and_off_events_ignored": True,
        "boundary_timestamp_preserved": exact.boundary_timestamp_ns,
        "failure_codes": seen,
        "canonical_mapping_order_invariant": True,
        "realizer_semantics_content_addressed": True,
    }


def exhaustive_definition_gate() -> dict[str, object]:
    cases: list[object] = []
    domains = ("mono:a", "mono:b")
    for record_domain in domains:
        for deadline in (101, 102, 103):
            for closure_delta in (-1, 0, 1):
                closed_at = deadline + closure_delta
                cases.append(
                    _raw(
                        command=100,
                        deadline=deadline,
                        closed_at=closed_at,
                        domain=record_domain,
                    )
                )
                for recv in range(99, 105):
                    for event_domain in domains:
                        for device in ("device-a", "device-b"):
                            for on in (False, True):
                                cases.append(
                                    _raw(
                                        command=100,
                                        deadline=deadline,
                                        closed_at=closed_at,
                                        domain=record_domain,
                                        events=[
                                            _event(
                                                "e0",
                                                recv,
                                                device=device,
                                                on=on,
                                                domain=event_domain,
                                            )
                                        ],
                                    )
                                )

    two_event_templates = (
        [_event("e0", 100), _event("e1", 101)],
        [_event("same", 100), _event("same", 101)],
        [_event("old", 99), _event("match", 100)],
        [_event("other", 100, device="device-b"), _event("match", 101)],
        [_event("off", 100, on=False), _event("match", 101)],
        [_event("late", 103), _event("match", 101)],
        [_event("other-clock", 100, domain="mono:b"), _event("match", 101)],
    )
    for deadline in (101, 102):
        for closed_at in (deadline, deadline + 2):
            for events in two_event_templates:
                cases.append(
                    _raw(
                        command=100,
                        deadline=deadline,
                        closed_at=closed_at,
                        domain="mono:a" if any(e["clock_domain"] == "mono:b" for e in events) else "mono:test",
                        events=events,
                    )
                )

    malformed: list[object] = [
        None,
        [],
        {key: value for key, value in _raw().items() if key != "events"},
        {**_raw(), "unknown": 1},
        {**_raw(), 7: "non-string-key"},
        {**_raw(), "schema": "foreign"},
        {**_raw(), "clock_domain": " mono:test"},
        {**_raw(), "expected_device": ""},
        {**_raw(), "command_publish_mono_ns": True},
        {**_raw(), "verify_deadline_mono_ns": 100},
        {**_raw(), "closed_at_mono_ns": 199},
        {**_raw(), "events": "not-a-sequence"},
        _raw(events=[{"device": "device-a", "on": True, "recv_mono_ns": 150, "clock_domain": "mono:test"}]),
        _raw(events=[{"event_id": "e", "on": True, "recv_mono_ns": 150, "clock_domain": "mono:test"}]),
        _raw(events=[{"event_id": "e", "device": "device-a", "recv_mono_ns": 150, "clock_domain": "mono:test"}]),
        _raw(events=[{"event_id": "e", "device": "device-a", "on": True, "clock_domain": "mono:test"}]),
        _raw(events=[{"event_id": "e", "device": "device-a", "on": True, "recv_mono_ns": 150}]),
        _raw(events=[{**_event("e", 150), "unknown": 1}]),
        _raw(events=[{**_event("e", 150), 7: "non-string-key"}]),
        _raw(events=[{"event_id": " e", "device": "device-a", "on": True, "recv_mono_ns": 150, "clock_domain": "mono:test"}]),
        _raw(events=[{"event_id": "e", "device": "device-a", "on": 1, "recv_mono_ns": 150, "clock_domain": "mono:test"}]),
        _raw(events=[{"event_id": "e", "device": "device-a", "on": True, "recv_mono_ns": True, "clock_domain": "mono:test"}]),
    ]
    cases.extend(malformed)

    agreements = 0
    successes = 0
    failure_counts: dict[str, int] = {}
    for index, raw in enumerate(cases):
        production = _prod(raw)
        definition = _oracle(raw)
        if production != definition:
            raise AssertionError(
                f"production/oracle mismatch at case {index}: "
                f"production={production!r}, definition={definition!r}, raw={raw!r}"
            )
        agreements += 1
        if production["ok"]:
            successes += 1
        else:
            code = str(production["error_code"])
            failure_counts[code] = failure_counts.get(code, 0) + 1

    required_codes = {
        code.value
        for code in (
            RealizationFailureCode.MALFORMED_INPUT,
            RealizationFailureCode.MISSING_REQUIRED_FIELD,
            RealizationFailureCode.DUPLICATE_INPUT,
            RealizationFailureCode.CLOCK_DOMAIN_MISMATCH,
            RealizationFailureCode.OUT_OF_BOUNDARY,
            RealizationFailureCode.AMBIGUOUS_REALIZATION,
            RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
        )
    }
    assert required_codes.issubset(failure_counts)

    return {
        "production_vs_literal_oracle_cases": agreements,
        "successful_realizations": successes,
        "failure_counts": dict(sorted(failure_counts.items())),
        "all_required_failure_classes_exercised": True,
    }


def runtime_boundary_type_gate() -> dict[str, object]:
    assert not (
        {item.value for item in RealizationFailureCode}
        & {item.value for item in Verdict}
    )

    observation = realize_e3b_observation(_raw(events=[_event("e", 150)]))
    action_provenance = RealizationProvenance(
        schema_version="replaymark.runtime.realization-provenance.v1",
        stage=RealizationStage.HISTORICAL_ACTION,
        realizer_id="fixture.action-realizer.v1",
        realizer_semantic_digest="1" * 64,
        source_schema="fixture.raw-action.v1",
        raw_record_digest="2" * 64,
    )
    full_action = ProjectedAction.from_mapping(
        {"operation": "ACT2", "target": "task-7", "variant": "on"}
    )
    action = RealizedHistoricalAction(
        schema_version="replaymark.runtime.realized-historical-action.v1",
        action=full_action,
        provenance=action_provenance,
    )
    projected = ProjectedAction.from_mapping({"operation": "ACT2"})
    adjudication = Adjudication(
        schema_version="replaymark.adjudication.v1",
        support_envelope_fingerprint="support",
        claim_fingerprint="claim",
        evidence_fingerprint="evidence",
        depth=0,
        token=observation.evidence_token,
        projected_action=projected,
        in_guaranteed_support=True,
        in_possible_support=True,
        verdict=Verdict.VALID,
    )
    reuse = RStarDecision(
        schema_version="replaymark.rstar.maximal-certified-reuse.v1",
        adjudication_fingerprint=adjudication.fingerprint(),
        support_envelope_fingerprint=adjudication.support_envelope_fingerprint,
        claim_fingerprint=adjudication.claim_fingerprint,
        evidence_fingerprint=adjudication.evidence_fingerprint,
        depth=adjudication.depth,
        token=adjudication.token,
        projected_action=adjudication.projected_action,
        verdict=adjudication.verdict,
        disposition=ReuseDisposition.REUSE,
    )
    certificate = RuntimeReuseCertificate(
        schema_version="replaymark.runtime.reuse-certificate.v1",
        contract_fingerprint="contract",
        claim_fingerprint="claim",
        observation=observation,
        historical_action=action,
        adjudication=adjudication,
        reuse_decision=reuse,
    )
    assert certificate.reuse_decision.disposition is ReuseDisposition.REUSE
    assert "execution" not in certificate.canonical_record()
    assert "fallback" not in certificate.canonical_record()

    wrong_action = RealizedHistoricalAction(
        schema_version="replaymark.runtime.realized-historical-action.v1",
        action=ProjectedAction.from_mapping(
            {"operation": "OTHER", "target": "task-7", "variant": "on"}
        ),
        provenance=action_provenance,
    )
    try:
        RuntimeReuseCertificate(
            schema_version="replaymark.runtime.reuse-certificate.v1",
            contract_fingerprint="contract",
            claim_fingerprint="claim",
            observation=observation,
            historical_action=wrong_action,
            adjudication=adjudication,
            reuse_decision=reuse,
        )
    except ValueError:
        mismatch_rejected = True
    else:
        mismatch_rejected = False
    assert mismatch_rejected

    field_names = tuple(field.name for field in fields(RuntimeReuseCertificate))
    forbidden = {"execute", "fallback", "regenerate", "abort", "retry"}
    assert not (set(field_names) & forbidden)

    return {
        "failure_is_not_semantic_unresolved": True,
        "runtime_certificate_chain_validated": True,
        "realized_action_projection_mismatch_rejected": True,
        "no_execution_policy_fields": True,
        "runtime_reuse_certificate_fields": list(field_names),
    }


def frozen_harness_equivalence_gate() -> dict[str, object]:
    tests = {
        "lower_bound_inclusive": _raw(events=[_event("e", 100)]),
        "deadline_inclusive": _raw(events=[_event("e", 200)]),
        "pre_command_ignored": _raw(events=[_event("e", 99)]),
        "post_deadline_ignored": _raw(closed_at=250, events=[_event("e", 220)]),
        "off_ignored": _raw(events=[_event("e", 150, on=False)]),
        "other_device_ignored": _raw(events=[_event("e", 150, device="device-b")]),
    }
    expected = {
        "lower_bound_inclusive": E3B_CONFIRMED_BY_DEADLINE,
        "deadline_inclusive": E3B_CONFIRMED_BY_DEADLINE,
        "pre_command_ignored": E3B_NOT_VISIBLE_BY_DEADLINE,
        "post_deadline_ignored": E3B_NOT_VISIBLE_BY_DEADLINE,
        "off_ignored": E3B_NOT_VISIBLE_BY_DEADLINE,
        "other_device_ignored": E3B_NOT_VISIBLE_BY_DEADLINE,
    }
    for name, raw in tests.items():
        assert realize_e3b_observation(raw).evidence_token == expected[name]

    return {
        "matches_frozen_after_ns_lower_bound_inclusive": True,
        "matches_frozen_deadline_upper_bound_inclusive": True,
        "pre_command_events_are_history_not_failure": True,
        "post_deadline_events_do_not_relabel_closed_boundary": True,
        "off_and_other_device_events_are_not_matches": True,
        "source_schema_requires_boolean_on": True,
    }


def scope_gate() -> dict[str, object]:
    import replaymark.runtime_e3b_observation as e3b
    import replaymark.runtime_realization as boundary

    assert not hasattr(e3b, "realize_e3b_historical_action")
    assert not hasattr(e3b, "execute")
    assert not hasattr(boundary, "execute")
    assert not hasattr(boundary, "choose_fallback")
    rule = e3b_observation_realizer_rule_record()
    assert rule["capture"]["record_is_complete_snapshot"] is True
    assert rule["selection"]["deadline_inclusive"] is True
    assert rule["capture"]["events_outside_decision_interval"] == "retained-but-ignored"
    return {
        "observation_only_increment": True,
        "historical_action_realizer_not_implemented": True,
        "execution_and_fallback_absent": True,
        "caller_prefilter_not_trusted": True,
        "complete_snapshot_closure_required": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    report = {
        "schema": "replaymark.runtime-realization.e3b-observation-gate.v2",
        "runtime_boundary_types": runtime_boundary_type_gate(),
        "named_boundary": named_boundary_gate(),
        "production_vs_definition": exhaustive_definition_gate(),
        "frozen_harness_equivalence": frozen_harness_equivalence_gate(),
        "scope": scope_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
