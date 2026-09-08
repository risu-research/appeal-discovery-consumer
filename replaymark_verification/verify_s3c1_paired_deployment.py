from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence


SCHEMA = "replaymark.s3c1-independent-deployment-validator.v1"
CELL_SCHEMA = "replaymark.s3c1-paired-four-arm-live-cell.v1"
PROTOCOL_HEAD = "274b870313696adaf2f80b52632e9b6ea854fd90"
PROTOCOL_SHA256 = "ac50c3b7ac69397c3af0c5344f85c5eeb7bd77ee5535af920db41564304e5d0f"
BROKER_VERSION = "mosquitto version 2.1.2"
BROKER_CONFIG_SHA256 = "886f26936b560ebfbf584744c8c4f5f2dd3eeeba946313ad1d2f7f8848bf0858"
BROKER_IMAGE_DIGEST = "sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797"
HISTORICAL_TEMPLATE_SHA256 = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"
BATCH_SIZES = (192, 196, 200, 204, 208)
TRIALS = 6
REPLICAS = ("A", "B")
ARMS = ("ALWAYS_REUSE", "DIRECT_NATIVE", "REPLAYMARK_NATIVE", "ALWAYS_NATIVE")
ARM_CODES = {"ru": "ALWAYS_REUSE", "dn": "DIRECT_NATIVE", "rn": "REPLAYMARK_NATIVE", "an": "ALWAYS_NATIVE"}
LOGICAL_WAVE_SIZE = 4
PHYSICAL_TWINS_PER_WAVE = 16
WAVE_PERIOD_MS = 500.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000
POST_CONFIRMATION_GAP_MS = 20.0
QUEUE_LIMIT = 1000
TERMINAL_ROLES = ("command", "query", "state")
CONFIRMED = "confirmed_by_deadline"
NOT_VISIBLE = "not_visible_by_deadline"
FORBIDDEN_QUEUE_DIRECTIVES = {
    "max_queued_messages",
    "max_queued_bytes",
    "max_inflight_messages",
    "queue_qos0_messages",
}
DEVICE_RE = re.compile(
    r"^s3c1-r(?P<replica>[AB])-n(?P<batch>[0-9]+)-t(?P<trial>[0-9]+)-"
    r"(?P<nonce>[A-Za-z0-9]+)-(?P<arm>ru|dn|rn|an)-(?P<task>[0-9]+)-(?P<role>a|b)$"
)


class ValidationFailure(ValueError):
    pass


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _fail(message: str) -> None:
    raise ValidationFailure(message)


def parse_device(device: object) -> dict[str, object]:
    if not isinstance(device, str):
        _fail("device must be a string")
    m = DEVICE_RE.fullmatch(device)
    if m is None:
        _fail(f"foreign device namespace: {device!r}")
    g = m.groupdict()
    batch, trial, task_id = int(g["batch"]), int(g["trial"]), int(g["task"])
    if str(batch) != g["batch"] or str(trial) != g["trial"] or str(task_id) != g["task"]:
        _fail("non-canonical decimal namespace")
    if batch not in BATCH_SIZES or trial not in range(TRIALS) or task_id not in range(batch):
        _fail("device outside frozen matrix")
    return {
        "replica": g["replica"],
        "batch_size": batch,
        "trial": trial,
        "nonce": g["nonce"],
        "arm": ARM_CODES[g["arm"]],
        "task_id": task_id,
        "role": g["role"],
    }


def topic_identity(topic: object) -> dict[str, object]:
    if not isinstance(topic, str):
        _fail("topic must be a string")
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] not in TERMINAL_ROLES:
        _fail(f"unexpected terminal topic: {topic!r}")
    out = parse_device(parts[1])
    out["terminal_role"] = parts[2]
    return out


def _ns(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{name} must be a non-negative integer ns timestamp")
    return value


def independent_evidence_token(raw: object) -> str:
    if not isinstance(raw, Mapping):
        _fail("snapshot must be a mapping")
    required = {
        "schema", "clock_domain", "expected_device", "command_publish_mono_ns",
        "verify_deadline_mono_ns", "closed_at_mono_ns", "events",
    }
    if set(raw) != required:
        _fail("snapshot fields are not exact")
    if raw["schema"] != "replaymark.runtime.e3b-observation-record.v1":
        _fail("foreign snapshot schema")
    domain = raw["clock_domain"]
    expected_device = raw["expected_device"]
    if not isinstance(domain, str) or not domain or not isinstance(expected_device, str):
        _fail("snapshot domain/device malformed")
    parse_device(expected_device)
    command = _ns(raw["command_publish_mono_ns"], "command_publish_mono_ns")
    deadline = _ns(raw["verify_deadline_mono_ns"], "verify_deadline_mono_ns")
    closed = _ns(raw["closed_at_mono_ns"], "closed_at_mono_ns")
    if deadline - command != int(VERIFY_MS * 1e6):
        _fail("snapshot decision interval is not exactly frozen 100ms")
    if closed < deadline:
        _fail("snapshot closed before decision deadline")
    events = raw["events"]
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        _fail("snapshot events must be a sequence")
    seen: set[str] = set()
    matches = 0
    for event in events:
        if not isinstance(event, Mapping):
            _fail("snapshot event must be mapping")
        if set(event) != {"event_id", "device", "on", "recv_mono_ns", "clock_domain"}:
            _fail("snapshot event fields are not exact")
        event_id = event["event_id"]
        if not isinstance(event_id, str) or not event_id or event_id in seen:
            _fail("snapshot event id malformed/duplicate")
        seen.add(event_id)
        recv = _ns(event["recv_mono_ns"], "event recv")
        if event["clock_domain"] != domain or recv > closed:
            _fail("snapshot event violates clock/closure boundary")
        if (
            event["device"] == expected_device and event["on"] is True
            and command <= recv <= deadline
        ):
            matches += 1
    if matches > 1:
        _fail("ambiguous evidence: multiple distinct matching events")
    return CONFIRMED if matches == 1 else NOT_VISIBLE


def _expected_devices(replica: str, batch_size: int, trial: int, nonce: str, arm: str) -> set[str]:
    code = {v: k for k, v in ARM_CODES.items()}[arm]
    return {
        f"s3c1-r{replica}-n{batch_size}-t{trial}-{nonce}-{code}-{task_id}-{role}"
        for task_id in range(batch_size) for role in ("a", "b")
    }


def _raw_role_vector(events: Sequence[Mapping[str, object]], *, cell: Mapping[str, object],
                     arm: str) -> tuple[Counter, list[dict[str, object]]]:
    counts: Counter[str] = Counter()
    selected: list[dict[str, object]] = []
    for event in events:
        identity = topic_identity(event.get("topic"))
        if (
            identity["replica"] == cell["replica"]
            and identity["batch_size"] == cell["batch_size"]
            and identity["trial"] == cell["trial"]
            and identity["nonce"] == cell["nonce"]
            and identity["arm"] == arm
        ):
            role = str(identity["terminal_role"])
            if event.get("qos") != 1 or event.get("retain") is not False:
                _fail(f"{arm}: non-QoS1/non-retained terminal event")
            counts[role] += 1
            selected.append(dict(event))
    return counts, selected


def _duplicate_delivery_count(events: Sequence[Mapping[str, object]]) -> int:
    seen: set[bytes] = set()
    duplicates = 0
    for event in events:
        if event.get("dup") is True:
            duplicates += 1
        key = _canonical_json_bytes({
            "topic": event.get("topic"),
            "payload_utf8": event.get("payload_utf8"),
        })
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def _call_index(calls: Sequence[Mapping[str, object]], *, cell: Mapping[str, object]):
    by: dict[tuple[str, int], list[Mapping[str, object]]] = defaultdict(list)
    for call in calls:
        if not isinstance(call, Mapping):
            _fail("application publish provenance row must be mapping")
        identity = topic_identity(call.get("topic"))
        if (
            identity["replica"] != cell["replica"] or
            identity["batch_size"] != cell["batch_size"] or
            identity["trial"] != cell["trial"] or
            identity["nonce"] != cell["nonce"]
        ):
            _fail("application publish escaped cell namespace")
        if call.get("arm") != identity["arm"] or call.get("task_id") != identity["task_id"]:
            _fail("application publish metadata disagrees with topic")
        if call.get("qos") != 1 or call.get("retain") is not False or call.get("properties") is not None:
            _fail("application publish wire tuple drift")
        channel = call.get("channel")
        role = identity["terminal_role"]
        device_role = identity["role"]
        if channel == "ACT1":
            if role != "command" or device_role != "a" or call.get("payload_utf8") != '{"on": true}':
                _fail("ACT1 wire tuple drift")
        elif channel in {"HISTORICAL_ACT2", "NATIVE_FRESH_ACT2"}:
            if role != "command" or device_role != "b" or call.get("payload_utf8") != '{"on": true}':
                _fail("ACT2 wire tuple drift")
        elif channel == "NATIVE_QUERY_A":
            if role != "query" or device_role != "a" or call.get("payload_utf8") != "{}":
                _fail("native query wire tuple drift")
        else:
            _fail(f"unknown application publish channel {channel!r}")
        by[(str(identity["arm"]), int(identity["task_id"]))].append(call)
    return by


def validate_cell(report: Mapping[str, object]) -> dict[str, object]:
    checks: dict[str, bool] = {}
    detail: dict[str, object] = {}
    try:
        if report.get("schema") != CELL_SCHEMA:
            _fail("foreign cell schema")
        if report.get("protocol_head") != PROTOCOL_HEAD or report.get("protocol_sha256") != PROTOCOL_SHA256:
            _fail("protocol identity drift")
        if report.get("historical_template_sha256") != HISTORICAL_TEMPLATE_SHA256:
            _fail("historical ACT2 template drift")
        if report.get("scientific_verdict_in_live_runner") is not False or report.get("independent_oracle_used_in_live_runner") is not False:
            _fail("live runner contains/uses scientific oracle verdict")
        if report.get("fallback_inside_replaymark") is not False or report.get("regeneration_inside_replaymark") is not False or report.get("automatic_retry") != "ABSENT":
            _fail("semantic no-fallback boundary drift")

        cell = report.get("cell")
        if not isinstance(cell, Mapping):
            _fail("cell metadata malformed")
        replica, batch_size, trial, nonce = (
            cell.get("replica"), cell.get("batch_size"), cell.get("trial"), cell.get("nonce")
        )
        if replica not in REPLICAS or batch_size not in BATCH_SIZES or trial not in range(TRIALS):
            _fail("cell outside canonical matrix")
        if not isinstance(nonce, str) or not nonce.isascii() or not nonce.isalnum():
            _fail("cell nonce malformed")
        cell = dict(cell)

        params = report.get("frozen_parameters")
        expected_params = {
            "arms": list(ARMS),
            "logical_wave_size": LOGICAL_WAVE_SIZE,
            "physical_four_arm_twins_per_wave": PHYSICAL_TWINS_PER_WAVE,
            "wave_period_ms": WAVE_PERIOD_MS,
            "verify_deadline_ms": VERIFY_MS,
            "task_timeout_ms": TASK_TIMEOUT_MS,
            "post_confirmation_gap_ms": POST_CONFIRMATION_GAP_MS,
            "persistent_queue_limit": QUEUE_LIMIT,
        }
        if params != expected_params:
            _fail("frozen workload parameters drift")

        broker = report.get("broker_attestation")
        if not isinstance(broker, Mapping):
            _fail("broker attestation malformed")
        config_utf8 = broker.get("config_utf8")
        if not isinstance(config_utf8, str):
            _fail("raw broker config bytes absent")
        config_bytes = config_utf8.encode("utf-8")
        active = [
            line.strip().split()[0]
            for line in config_utf8.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if hashlib.sha256(config_bytes).hexdigest() != BROKER_CONFIG_SHA256:
            _fail("broker config bytes hash drift")
        if sorted(set(active) & FORBIDDEN_QUEUE_DIRECTIVES):
            _fail("forbidden queue-policy directive present")
        if broker.get("observed_version") != BROKER_VERSION:
            _fail("broker version drift")
        if broker.get("config_sha256") != BROKER_CONFIG_SHA256 or broker.get("required_config_sha256") != BROKER_CONFIG_SHA256:
            _fail("broker config attestation drift")
        if broker.get("supplied_image_digest") != BROKER_IMAGE_DIGEST or broker.get("required_image_digest") != BROKER_IMAGE_DIGEST:
            _fail("broker image digest drift")
        if broker.get("forbidden_queue_directives_present") != []:
            _fail("runner observed forbidden queue directive")

        tasks = report.get("tasks")
        if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)) or len(tasks) != batch_size:
            _fail("task population incomplete")
        rows: dict[int, Mapping[str, object]] = {}
        tokens: dict[str, dict[int, str]] = {arm: {} for arm in ARMS}
        errors: list[str] = []
        for row in tasks:
            if not isinstance(row, Mapping):
                _fail("task row malformed")
            task_id = row.get("task_id")
            if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id in rows:
                _fail("task id malformed/duplicate")
            rows[task_id] = row
            arms = row.get("arms")
            if not isinstance(arms, Mapping) or set(arms) != set(ARMS):
                _fail("task does not contain exact four arms")
            for arm in ARMS:
                armrow = arms[arm]
                if not isinstance(armrow, Mapping):
                    _fail("arm row malformed")
                raw = armrow.get("raw_observation")
                identity = parse_device(raw.get("expected_device") if isinstance(raw, Mapping) else None)
                if (
                    identity["replica"] != replica or identity["batch_size"] != batch_size
                    or identity["trial"] != trial or identity["nonce"] != nonce
                    or identity["arm"] != arm or identity["task_id"] != task_id
                    or identity["role"] != "a"
                ):
                    _fail("snapshot identity/pairing drift")
                tokens[arm][task_id] = independent_evidence_token(raw)
                if armrow.get("errors") not in ([], None):
                    errors.extend([f"{arm}:{task_id}:{x}" for x in armrow.get("errors", [])])
        if set(rows) != set(range(batch_size)):
            _fail("configured task ids not exact")

        mismatches = [
            task_id for task_id in range(batch_size)
            if tokens["DIRECT_NATIVE"][task_id] != tokens["REPLAYMARK_NATIVE"][task_id]
        ]
        U = sum(tokens["DIRECT_NATIVE"][i] == NOT_VISIBLE for i in range(batch_size))

        calls = report.get("application_publish_provenance")
        if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes)):
            _fail("application publish provenance malformed")
        by_call = _call_index(calls, cell=cell)
        route_errors: list[str] = []
        rm_reuse: set[int] = set()
        rm_native: set[int] = set()
        for task_id in range(batch_size):
            for arm in ARMS:
                task_calls = list(by_call.get((arm, task_id), []))
                channels = Counter(str(c.get("channel")) for c in task_calls)
                if channels["ACT1"] != 1:
                    route_errors.append(f"{arm}:{task_id}:ACT1={channels['ACT1']}")
                if arm == "ALWAYS_REUSE":
                    if channels != Counter({"ACT1": 1, "HISTORICAL_ACT2": 1}):
                        route_errors.append(f"{arm}:{task_id}:channels={dict(channels)}")
                elif arm == "ALWAYS_NATIVE":
                    if channels != Counter({"ACT1": 1, "NATIVE_QUERY_A": 1, "NATIVE_FRESH_ACT2": 1}):
                        route_errors.append(f"{arm}:{task_id}:channels={dict(channels)}")
                elif arm == "DIRECT_NATIVE":
                    expected = (
                        Counter({"ACT1": 1, "NATIVE_FRESH_ACT2": 1})
                        if tokens[arm][task_id] == CONFIRMED
                        else Counter({"ACT1": 1, "NATIVE_QUERY_A": 1, "NATIVE_FRESH_ACT2": 1})
                    )
                    if channels != expected:
                        route_errors.append(f"{arm}:{task_id}:channels={dict(channels)} expected={dict(expected)}")
                elif arm == "REPLAYMARK_NATIVE":
                    if channels["HISTORICAL_ACT2"] == 1:
                        rm_reuse.add(task_id)
                    if channels["NATIVE_QUERY_A"] == 1 or channels["NATIVE_FRESH_ACT2"] == 1:
                        rm_native.add(task_id)
                    expected = (
                        Counter({"ACT1": 1, "HISTORICAL_ACT2": 1})
                        if tokens[arm][task_id] == CONFIRMED
                        else Counter({"ACT1": 1, "NATIVE_QUERY_A": 1, "NATIVE_FRESH_ACT2": 1})
                    )
                    if channels != expected:
                        route_errors.append(f"{arm}:{task_id}:channels={dict(channels)} expected={dict(expected)}")

        safe_set = {i for i in range(batch_size) if tokens["REPLAYMARK_NATIVE"][i] == CONFIRMED}
        unsafe_set = set(range(batch_size)) - safe_set

        online = report.get("online_role_ledger")
        if not isinstance(online, Sequence) or isinstance(online, (str, bytes)):
            _fail("online role ledger malformed")
        generated: dict[str, Counter] = {}
        generated_events: dict[str, list[dict[str, object]]] = {}
        for arm in ARMS:
            generated[arm], generated_events[arm] = _raw_role_vector(online, cell=cell, arm=arm)

        expected_vectors = {
            "ALWAYS_REUSE": Counter(command=2 * batch_size, query=0, state=2 * batch_size),
            "DIRECT_NATIVE": Counter(command=2 * batch_size, query=U, state=2 * batch_size + U),
            "REPLAYMARK_NATIVE": Counter(command=2 * batch_size, query=U, state=2 * batch_size + U),
            "ALWAYS_NATIVE": Counter(command=2 * batch_size, query=batch_size, state=3 * batch_size),
        }

        collectors = report.get("persistent_collectors")
        if not isinstance(collectors, Mapping) or set(collectors) != set(ARMS):
            _fail("persistent collectors not exact four-arm set")
        delivered: dict[str, Counter] = {}
        delivered_total: dict[str, int] = {}
        lost_total: dict[str, int] = {}
        classifications: dict[str, str] = {}
        queue_errors: list[str] = []
        for arm in ARMS:
            collector = collectors[arm]
            if not isinstance(collector, Mapping):
                _fail("collector report malformed")
            if collector.get("arm") != arm or collector.get("clean_session") is not False:
                queue_errors.append(f"{arm}:session-contract")
            if collector.get("session_present") is not True:
                queue_errors.append(f"{arm}:session-not-present")
            expected_filters = sorted(f"agentmark/{d}/#" for d in _expected_devices(
                replica, batch_size, trial, nonce, arm
            ))
            if sorted(collector.get("filters", [])) != expected_filters:
                queue_errors.append(f"{arm}:filter-set")
            deliveries = collector.get("deliveries")
            if not isinstance(deliveries, Sequence) or isinstance(deliveries, (str, bytes)):
                _fail("collector deliveries malformed")
            delivered[arm], selected = _raw_role_vector(deliveries, cell=cell, arm=arm)
            if len(selected) != len(deliveries):
                queue_errors.append(f"{arm}:cross-arm-or-foreign-delivery")
            duplicates = _duplicate_delivery_count(deliveries)
            if duplicates != 0:
                queue_errors.append(f"{arm}:duplicate-delivery={duplicates}")
            gtotal = sum(generated[arm].values())
            dtotal = len(deliveries)
            expected_delivered = min(gtotal, QUEUE_LIMIT)
            expected_lost = max(gtotal - QUEUE_LIMIT, 0)
            if dtotal != expected_delivered:
                queue_errors.append(f"{arm}:delivered={dtotal} expected={expected_delivered}")
            delivered_total[arm] = dtotal
            lost_total[arm] = gtotal - dtotal
            if lost_total[arm] != expected_lost:
                queue_errors.append(f"{arm}:lost={lost_total[arm]} expected={expected_lost}")
            classifications[arm] = "LOSSLESS" if lost_total[arm] == 0 else "LOSSY"

        waves = report.get("waves")
        expected_wave_count = (batch_size + LOGICAL_WAVE_SIZE - 1) // LOGICAL_WAVE_SIZE
        wave_errors: list[str] = []
        if not isinstance(waves, Sequence) or isinstance(waves, (str, bytes)) or len(waves) != expected_wave_count:
            wave_errors.append("wave-count")
        else:
            flattened: list[int] = []
            for idx, wave in enumerate(waves):
                if wave.get("wave_index") != idx:
                    wave_errors.append(f"wave-index:{idx}")
                ids = wave.get("task_ids")
                if not isinstance(ids, list) or not (1 <= len(ids) <= LOGICAL_WAVE_SIZE):
                    wave_errors.append(f"wave-size:{idx}")
                else:
                    flattened.extend(ids)
                if wave.get("quiescence_missing") != []:
                    wave_errors.append(f"quiescence:{idx}")
                if wave.get("next_wave_schedule_overrun") is not False:
                    wave_errors.append(f"overrun:{idx}")
                if (
                    isinstance(wave.get("snapshot_closed_at_mono_ns"), int)
                    and isinstance(wave.get("post_decision_quiescence_mono_ns"), int)
                    and wave["post_decision_quiescence_mono_ns"] < wave["snapshot_closed_at_mono_ns"]
                ):
                    wave_errors.append(f"barrier-order:{idx}")
            if flattened != list(range(batch_size)):
                wave_errors.append("wave-task-population")

        temporal_errors: list[str] = []
        online_state_by_device: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        for event in online:
            try:
                ident = topic_identity(event.get("topic"))
            except ValidationFailure:
                continue
            if ident["terminal_role"] != "state":
                continue
            try:
                body = json.loads(str(event.get("payload_utf8")))
            except Exception:
                temporal_errors.append(f"state-json:{event.get('topic')}")
                continue
            if body.get("device") != event.get("topic").split("/")[1]:
                temporal_errors.append(f"state-device:{event.get('topic')}")
                continue
            online_state_by_device[str(body.get("device"))].append({
                "cause": body.get("cause"),
                "on": body.get("on"),
                "recv_mono_ns": event.get("recv_mono_ns"),
            })

        for task_id in range(batch_size):
            for arm in ARMS:
                task_calls = list(by_call.get((arm, task_id), []))
                act1 = [c for c in task_calls if c.get("channel") == "ACT1"]
                act2 = [c for c in task_calls if c.get("channel") in {"HISTORICAL_ACT2", "NATIVE_FRESH_ACT2"}]
                queries = [c for c in task_calls if c.get("channel") == "NATIVE_QUERY_A"]
                if len(act1) == 1:
                    a_name = str(act1[0]["topic"]).split("/")[1]
                    a_effects = [
                        e for e in online_state_by_device.get(a_name, ())
                        if e.get("cause") == "command" and e.get("on") is True
                        and isinstance(e.get("recv_mono_ns"), int)
                        and int(e["recv_mono_ns"]) >= int(act1[0]["publish_mono_ns"])
                    ]
                    if not a_effects:
                        temporal_errors.append(f"{arm}:{task_id}:missing-A-command-effect")
                if len(act2) == 1:
                    b_name = str(act2[0]["topic"]).split("/")[1]
                    b_effects = [
                        e for e in online_state_by_device.get(b_name, ())
                        if e.get("cause") == "command" and e.get("on") is True
                        and isinstance(e.get("recv_mono_ns"), int)
                        and int(e["recv_mono_ns"]) >= int(act2[0]["publish_mono_ns"])
                    ]
                    if not b_effects:
                        temporal_errors.append(f"{arm}:{task_id}:missing-B-command-effect")
                if len(queries) == 1:
                    q = queries[0]
                    a_name = str(q["topic"]).split("/")[1]
                    confirmations = [
                        e for e in online_state_by_device.get(a_name, ())
                        if e.get("cause") == "query" and e.get("on") is True
                        and isinstance(e.get("recv_mono_ns"), int)
                        and int(e["recv_mono_ns"]) >= int(q["publish_mono_ns"])
                    ]
                    if not confirmations:
                        temporal_errors.append(f"{arm}:{task_id}:missing-query-confirmation")
                    elif len(act2) == 1:
                        first = min(confirmations, key=lambda e: int(e["recv_mono_ns"]))
                        minimum_fresh = int(first["recv_mono_ns"]) + int(POST_CONFIRMATION_GAP_MS * 1e6)
                        if int(act2[0]["publish_mono_ns"]) < minimum_fresh:
                            temporal_errors.append(f"{arm}:{task_id}:fresh-before-20ms-gap")

        if isinstance(waves, Sequence) and not isinstance(waves, (str, bytes)):
            for idx, wave in enumerate(waves):
                ids = set(wave.get("task_ids", []))
                close_ns = wave.get("snapshot_closed_at_mono_ns")
                q_ns = wave.get("post_decision_quiescence_mono_ns")
                if not isinstance(close_ns, int) or not isinstance(q_ns, int):
                    temporal_errors.append(f"wave:{idx}:missing-barrier-timestamps")
                    continue
                wave_calls = [c for c in calls if c.get("task_id") in ids]
                for c in wave_calls:
                    stamp = c.get("publish_mono_ns")
                    if not isinstance(stamp, int):
                        temporal_errors.append(f"wave:{idx}:bad-publish-timestamp")
                        continue
                    if c.get("channel") == "ACT1":
                        if stamp > close_ns:
                            temporal_errors.append(f"wave:{idx}:ACT1-after-snapshot-close")
                    elif stamp < close_ns:
                        temporal_errors.append(f"wave:{idx}:decision-traffic-before-all-snapshots-close")
                    if stamp > q_ns:
                        temporal_errors.append(f"wave:{idx}:publish-after-quiescence")
                for task_id in ids:
                    row = rows[int(task_id)]
                    for arm in ARMS:
                        raw = row["arms"][arm]["raw_observation"]
                        if raw.get("closed_at_mono_ns") != close_ns:
                            temporal_errors.append(f"wave:{idx}:{arm}:{task_id}:snapshot-close-not-common-barrier")
                if idx + 1 < len(waves):
                    next_wave = waves[idx + 1]
                    next_start = next_wave.get("actual_start_mono_ns")
                    if not isinstance(next_start, int) or next_start < q_ns:
                        temporal_errors.append(f"wave:{idx}:next-wave-before-quiescence")

        checks["structural_complete"] = not errors and not wave_errors and not temporal_errors
        checks["pairing_taskwise_evidence_equal"] = not mismatches
        checks["direct_and_rm_generated_role_vectors_equal"] = generated["DIRECT_NATIVE"] == generated["REPLAYMARK_NATIVE"]
        checks["direct_and_rm_delivered_lost_equal"] = (
            delivered_total["DIRECT_NATIVE"] == delivered_total["REPLAYMARK_NATIVE"]
            and lost_total["DIRECT_NATIVE"] == lost_total["REPLAYMARK_NATIVE"]
        )
        checks["direct_and_rm_classification_equal"] = classifications["DIRECT_NATIVE"] == classifications["REPLAYMARK_NATIVE"]
        checks["role_conservation_all_arms"] = all(generated[arm] == expected_vectors[arm] for arm in ARMS)
        checks["queue_conservation_all_arms"] = not queue_errors
        checks["direct_reference_routes_exact"] = not route_errors
        checks["rm_reuse_exact_safe_set"] = rm_reuse == safe_set
        checks["rm_native_exact_unsafe_set"] = rm_native == unsafe_set
        checks["rm_unsafe_historical_zero"] = not (rm_reuse & unsafe_set)
        checks["rm_unnecessary_native_zero"] = not (rm_native & safe_set)
        checks["rm_retains_all_safe_history"] = safe_set <= rm_reuse
        checks["broker_authority_exact"] = True
        checks["no_runner_scientific_oracle"] = True

        detail.update({
            "cell": cell,
            "U": U,
            "safe_count": len(safe_set),
            "unsafe_count": len(unsafe_set),
            "evidence_mismatch_tasks": mismatches,
            "implementation_errors": errors,
            "route_errors": route_errors,
            "wave_errors": wave_errors,
            "temporal_errors": temporal_errors,
            "queue_errors": queue_errors,
            "generated_role_vectors": {arm: dict(generated[arm]) for arm in ARMS},
            "delivered_role_vectors": {arm: dict(delivered[arm]) for arm in ARMS},
            "generated_total": {arm: sum(generated[arm].values()) for arm in ARMS},
            "delivered_total": delivered_total,
            "lost_total": lost_total,
            "classification": classifications,
            "rm_reuse_count": len(rm_reuse),
            "rm_native_count": len(rm_native),
        })
        verdict = "PASS" if all(checks.values()) else "FAIL"
    except Exception as exc:
        checks["validator_exception_free"] = False
        detail["validator_exception"] = f"{type(exc).__name__}: {exc}"
        verdict = "FAIL"
    return {
        "schema": SCHEMA,
        "scope": "CELL",
        "checks": checks,
        "detail": detail,
        "verdict": verdict,
    }


def validate_matrix(reports: Sequence[Mapping[str, object]]) -> dict[str, object]:
    cell_reports = [validate_cell(report) for report in reports]
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    keys: list[tuple[str, int, int]] = []
    for cell in cell_reports:
        meta = cell.get("detail", {}).get("cell")
        if isinstance(meta, Mapping):
            keys.append((str(meta.get("replica")), int(meta.get("batch_size")), int(meta.get("trial"))))
    expected = {
        (replica, batch, trial)
        for replica in REPLICAS for batch in BATCH_SIZES for trial in range(TRIALS)
    }
    checks["all_60_canonical_cells_present_once"] = len(keys) == 60 and len(set(keys)) == 60 and set(keys) == expected
    checks["all_cell_validators_pass"] = len(cell_reports) == 60 and all(c.get("verdict") == "PASS" for c in cell_reports)

    negative_controls: dict[str, dict[str, list[tuple[int, int]]]] = {}
    frontiers: dict[str, dict[str, int | None]] = {}
    for replica in REPLICAS:
        optimistic: list[tuple[int, int]] = []
        pessimistic: list[tuple[int, int]] = []
        by_batch_direct: dict[int, list[bool]] = defaultdict(list)
        by_batch_rm: dict[int, list[bool]] = defaultdict(list)
        for cell in cell_reports:
            meta = cell.get("detail", {}).get("cell")
            if not isinstance(meta, Mapping) or meta.get("replica") != replica:
                continue
            cls = cell.get("detail", {}).get("classification", {})
            if not isinstance(cls, Mapping):
                continue
            batch, trial = int(meta["batch_size"]), int(meta["trial"])
            if (
                cls.get("ALWAYS_REUSE") == "LOSSLESS"
                and cls.get("DIRECT_NATIVE") == "LOSSY"
                and cls.get("REPLAYMARK_NATIVE") == "LOSSY"
            ):
                optimistic.append((batch, trial))
            if (
                cls.get("ALWAYS_NATIVE") == "LOSSY"
                and cls.get("DIRECT_NATIVE") == "LOSSLESS"
                and cls.get("REPLAYMARK_NATIVE") == "LOSSLESS"
            ):
                pessimistic.append((batch, trial))
            by_batch_direct[batch].append(cls.get("DIRECT_NATIVE") == "LOSSLESS")
            by_batch_rm[batch].append(cls.get("REPLAYMARK_NATIVE") == "LOSSLESS")

        negative_controls[replica] = {
            "blind_reuse_optimistic_error_cells": optimistic,
            "rerun_all_pessimistic_error_cells": pessimistic,
        }
        direct_frontier = max(
            (batch for batch in BATCH_SIZES if len(by_batch_direct[batch]) == TRIALS and all(by_batch_direct[batch])),
            default=None,
        )
        rm_frontier = max(
            (batch for batch in BATCH_SIZES if len(by_batch_rm[batch]) == TRIALS and all(by_batch_rm[batch])),
            default=None,
        )
        frontiers[replica] = {"DIRECT_NATIVE": direct_frontier, "REPLAYMARK_NATIVE": rm_frontier}

    checks["two_sided_negative_controls_each_replica"] = all(
        negative_controls[r]["blind_reuse_optimistic_error_cells"]
        and negative_controls[r]["rerun_all_pessimistic_error_cells"]
        for r in REPLICAS
    )
    checks["tested_frontier_direct_equals_rm_each_replica"] = all(
        frontiers[r]["DIRECT_NATIVE"] == frontiers[r]["REPLAYMARK_NATIVE"] for r in REPLICAS
    )
    checks["no_legacy_166_frontier"] = all(
        166 not in [x for x in frontiers[r].values() if x is not None] for r in REPLICAS
    )

    details["negative_controls"] = negative_controls
    details["tested_frontiers"] = frontiers
    details["cell_reports"] = cell_reports
    verdict = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema": SCHEMA,
        "scope": "FIRST_COMPLETE_60_CELL_MATRIX",
        "protocol_head": PROTOCOL_HEAD,
        "protocol_sha256": PROTOCOL_SHA256,
        "checks": checks,
        "detail": details,
        "first_complete_authority": True,
        "later_exact_runs_replication_only": True,
        "verdict": verdict,
    }


def _load_matrix_dir(path: Path) -> list[Mapping[str, object]]:
    files = sorted(path.rglob("cell-*.json"))
    return [json.loads(file.read_text(encoding="utf-8")) for file in files]


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input")
    group.add_argument("--matrix-dir")
    parser.add_argument("--out", required=True)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    if args.input:
        report = validate_cell(json.loads(Path(args.input).read_text(encoding="utf-8")))
    else:
        report = validate_matrix(_load_matrix_dir(Path(args.matrix_dir)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.enforce and report.get("verdict") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
