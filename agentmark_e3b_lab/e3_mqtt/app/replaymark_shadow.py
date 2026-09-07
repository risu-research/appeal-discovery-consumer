from __future__ import annotations

"""Non-interfering shadow capture for the frozen E3b R1 timing replay.

The canonical R1 implementation in ``ladder.py`` is intentionally not modified.
During one R1 condition this module temporarily wraps only two observable runtime
boundaries:

1. ``ladder.time``/``sleep_until`` to capture the exact task-local ``t0`` used by
   the frozen R1 verify deadline; and
2. the Harness MQTT client to observe the exact arguments passed to
   ``Client.publish`` while delegating every invocation exactly once.

All ReplayMark realization, same-task correlation, and semantic certification run
*after* ``ladder.cond`` has returned and the wrappers have been removed.  No
certificate computation therefore executes concurrently with the R1 network
workload.
"""

from dataclasses import dataclass
import json
import threading
import time as _real_time
from typing import Any

from agentmark.kernel import ReactiveKernel
import ladder

from replaymark.compat_agentmark import (
    claim_from_agentmark_projection,
    target_model_from_agentmark_kernel,
)
from replaymark.compiled_contract import ExplicitCompiledContract, compile_explicit_contract
from replaymark.runtime_e3b_action import E3B_ACTION_CAPTURE_POINT, E3B_RAW_ACTION_SCHEMA
from replaymark.runtime_e3b_bridge import (
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_e3b_observation import E3B_RAW_OBSERVATION_SCHEMA


E3B_R1_SHADOW_CLOCK_DOMAIN = "python.time.monotonic_ns:e3b-runner-process.v1"
E3B_R1_SHADOW_EVIDENCE_ID = "replaymark.e3b-r1-shadow-evidence.v1"
E3B_R1_SHADOW_CLAIM_ID = "replaymark.e3b-r1-shadow-operation-h0.v1"


@dataclass(frozen=True)
class CapturedPublish:
    thread_id: int
    task_t0_ns: int | None
    publish_mono_ns: int
    topic: object
    payload: object
    qos: object
    retain: object
    properties: object


@dataclass(frozen=True)
class ShadowTaskMaterial:
    task_id: int
    raw_observation: dict[str, object]
    raw_historical_action: dict[str, object]
    certificate: E3bShadowRuntimeReuseCertificate


@dataclass(frozen=True)
class R1ShadowRun:
    legacy_result: dict[str, object]
    task_material: tuple[ShadowTaskMaterial, ...]
    captured_publish_count: int


class _AfterAct1EvidenceModel:
    """Bind runtime feedback tokens specifically to the frozen after_act1 boundary.

    The full adapted AgentMark target contains later controller states too.  Their
    forward evidence is deliberately namespaced so a bare runtime feedback token
    can denote only an ``after_act1`` decision world.
    """

    def observation_support(self, decision_state: str) -> tuple[str, ...]:
        try:
            decoded = json.loads(str(decision_state))
        except json.JSONDecodeError as exc:
            raise KeyError(decision_state) from exc
        if (
            not isinstance(decoded, list)
            or len(decoded) != 2
            or not all(isinstance(value, str) for value in decoded)
        ):
            raise KeyError(decision_state)
        controller_state, feedback = decoded
        if controller_state == "after_act1":
            return (feedback,)
        return (f"__e3b_nonruntime__:{controller_state}:{feedback}",)


def compile_e3b_r1_shadow_contract() -> ExplicitCompiledContract:
    """Compile the frozen H=0 operation contract used by the R1 shadow hook."""

    kernel = ReactiveKernel(ladder.spec())
    target = target_model_from_agentmark_kernel(kernel)
    claim = claim_from_agentmark_projection(
        "operation",
        horizon=0,
        claim_id=E3B_R1_SHADOW_CLAIM_ID,
        consequence_endpoint="e3b-stage2-controller-decision",
    )
    return compile_explicit_contract(
        target,
        claim,
        _AfterAct1EvidenceModel(),
        evidence_id=E3B_R1_SHADOW_EVIDENCE_ID,
    )


class _TimeProxy:
    def __init__(self, real_module: Any, tls: threading.local):
        self._real = real_module
        self._tls = tls

    def monotonic_ns(self) -> int:
        value = self._real.monotonic_ns()
        if getattr(self._tls, "capture_next_t0", False):
            self._tls.task_t0_ns = value
            self._tls.capture_next_t0 = False
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _ClientProxy:
    def __init__(self, client: Any, tls: threading.local, records: list[CapturedPublish]):
        self._client = client
        self._tls = tls
        self._records = records

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def publish(self, *args: object, **kwargs: object):
        # Timestamp immediately before delegating to the actual Paho call.  The
        # wrapper never alters or normalizes arguments before delegation.
        stamp = _real_time.monotonic_ns()
        result = self._client.publish(*args, **kwargs)

        topic = args[0] if args else kwargs.get("topic")
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        qos = args[2] if len(args) > 2 else kwargs.get("qos", 0)
        retain = args[3] if len(args) > 3 else kwargs.get("retain", False)
        properties = args[4] if len(args) > 4 else kwargs.get("properties")
        if isinstance(topic, str) and topic.startswith("agentmark/") and topic.endswith("/command"):
            self._records.append(
                CapturedPublish(
                    thread_id=threading.get_ident(),
                    task_t0_ns=getattr(self._tls, "task_t0_ns", None),
                    publish_mono_ns=stamp,
                    topic=topic,
                    payload=payload,
                    qos=qos,
                    retain=retain,
                    properties=properties,
                )
            )
        return result


class _CaptureScope:
    """Install capture wrappers only for the duration of one frozen R1 cond()."""

    def __init__(self, harness: Any):
        self._harness = harness
        self._tls = threading.local()
        self.records: list[CapturedPublish] = []
        self._original_time = None
        self._original_sleep_until = None
        self._original_target_task = None
        self._original_client = None

    def __enter__(self) -> "_CaptureScope":
        self._original_time = ladder.time
        self._original_sleep_until = ladder.sleep_until
        self._original_target_task = ladder.target_task
        self._original_client = self._harness.client

        ladder.time = _TimeProxy(self._original_time, self._tls)
        original_sleep = self._original_sleep_until
        original_target = self._original_target_task
        tls = self._tls

        def captured_sleep_until(deadline_ns: int) -> None:
            original_sleep(deadline_ns)
            if getattr(tls, "arm_first_sleep", False):
                tls.capture_next_t0 = True
                tls.arm_first_sleep = False

        def captured_target_task(*args: object, **kwargs: object):
            # This setup happens before the frozen offer-time sleep, so it cannot
            # delay the scheduled task start.  The first monotonic_ns call after
            # that sleep is exactly the canonical R1 t0 assignment.
            tls.arm_first_sleep = True
            tls.capture_next_t0 = False
            tls.task_t0_ns = None
            return original_target(*args, **kwargs)

        ladder.sleep_until = captured_sleep_until
        ladder.target_task = captured_target_task
        self._harness.client = _ClientProxy(self._original_client, tls, self.records)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Restore every patched object before any semantic work is permitted.
        self._harness.client = self._original_client
        ladder.target_task = self._original_target_task
        ladder.sleep_until = self._original_sleep_until
        ladder.time = self._original_time


def _parse_device(topic: str) -> tuple[str, int, str, str]:
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
        raise ValueError(f"unexpected E3b command topic: {topic!r}")
    device = parts[1]
    prefix, task_text, role = device.rsplit("-", 2)
    if not task_text.isascii() or not task_text.isdigit() or str(int(task_text)) != task_text:
        raise ValueError(f"noncanonical E3b task id: {task_text!r}")
    return prefix, int(task_text), role, device


def _payload_utf8(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    if isinstance(payload, bytearray):
        return bytes(payload).decode("utf-8")
    raise TypeError(f"captured MQTT payload is not UTF-8 text/bytes: {type(payload).__name__}")


def _snapshot_events_through(harness: Any, device: str, boundary_ns: int) -> list[dict[str, object]]:
    # cond() has already returned, including the stage-2 completion wait. Paho's
    # callback thread is serial; therefore all callbacks with runner receive time
    # <= the earlier decision boundary have been committed to state_events.
    with harness.cv:
        rows = list(harness.state_events.get(device, ()))
    out: list[dict[str, object]] = []
    for index, event in enumerate(rows):
        recv = event.get("recv_mono_ns")
        if isinstance(recv, bool) or not isinstance(recv, int):
            raise TypeError("Harness state event lacks integer recv_mono_ns")
        if recv > boundary_ns:
            continue
        out.append(
            {
                "event_id": f"harness:{device}:{index}",
                "device": str(event.get("device")),
                "on": event.get("on"),
                "recv_mono_ns": recv,
                "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
            }
        )
    return out


def _materialize_tasks(
    harness: Any,
    records: list[CapturedPublish],
    verify_ms: float,
    contract: ExplicitCompiledContract,
) -> tuple[ShadowTaskMaterial, ...]:
    by_task: dict[tuple[str, int], dict[str, CapturedPublish]] = {}
    for record in records:
        if not isinstance(record.topic, str):
            raise TypeError("captured MQTT topic must be a string")
        prefix, task_id, role, _device = _parse_device(record.topic)
        if role not in ("a", "b"):
            raise ValueError(f"unexpected E3b command role: {role!r}")
        key = (prefix, task_id)
        role_map = by_task.setdefault(key, {})
        if role in role_map:
            raise ValueError(f"duplicate captured role {role!r} for task {key!r}")
        role_map[role] = record

    materials: list[ShadowTaskMaterial] = []
    verify_delta_ns = int(verify_ms * 1e6)
    for (prefix, task_id), role_map in sorted(by_task.items()):
        if set(role_map) != {"a", "b"}:
            raise ValueError(f"incomplete captured publish pair for {(prefix, task_id)!r}")
        act1 = role_map["a"]
        act2 = role_map["b"]
        if act1.task_t0_ns is None or act2.task_t0_ns is None:
            raise ValueError("exact R1 task t0 was not captured")
        if act1.task_t0_ns != act2.task_t0_ns:
            raise ValueError("captured ACT1/ACT2 calls disagree on task-local t0")

        _p1, _i1, _r1, device_a = _parse_device(str(act1.topic))
        deadline = act1.task_t0_ns + verify_delta_ns
        observation = {
            "schema": E3B_RAW_OBSERVATION_SCHEMA,
            "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
            "expected_device": device_a,
            "command_publish_mono_ns": act1.publish_mono_ns,
            "verify_deadline_mono_ns": deadline,
            "closed_at_mono_ns": deadline,
            "events": _snapshot_events_through(harness, device_a, deadline),
        }
        action = {
            "schema": E3B_RAW_ACTION_SCHEMA,
            "capture_point": E3B_ACTION_CAPTURE_POINT,
            "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
            "publish_mono_ns": act2.publish_mono_ns,
            "topic": str(act2.topic),
            "payload_utf8": _payload_utf8(act2.payload),
            "qos": act2.qos,
            "retain": act2.retain,
            "properties": act2.properties,
        }
        pair = correlate_e3b_runtime_pair(observation, action)
        certificate = certify_e3b_shadow_reuse(contract, pair)
        materials.append(
            ShadowTaskMaterial(
                task_id=task_id,
                raw_observation=observation,
                raw_historical_action=action,
                certificate=certificate,
            )
        )
    return tuple(materials)


def run_r1_shadow_condition(
    harness: Any,
    traces: list[dict[str, object]],
    wave_size: int,
    wave_period_ms: float,
    prefix: str,
    verify_ms: float,
    post_completion_gap_ms: float,
    task_timeout_ms: int,
    contract: ExplicitCompiledContract,
) -> R1ShadowRun:
    """Run the frozen R1 condition with capture-only wrappers, then certify offline."""

    if not isinstance(contract, ExplicitCompiledContract):
        raise TypeError("contract must be ExplicitCompiledContract")
    with _CaptureScope(harness) as capture:
        legacy_result = ladder.cond(
            harness,
            "R1_timing",
            traces,
            wave_size,
            wave_period_ms,
            prefix,
            verify_ms,
            post_completion_gap_ms,
            task_timeout_ms,
        )

    # The capture scope is already gone here. No semantic work is concurrent with
    # the R1 network execution.
    materials = _materialize_tasks(harness, capture.records, verify_ms, contract)
    return R1ShadowRun(
        legacy_result=legacy_result,
        task_material=materials,
        captured_publish_count=len(capture.records),
    )


__all__ = (
    "E3B_R1_SHADOW_CLOCK_DOMAIN",
    "E3B_R1_SHADOW_EVIDENCE_ID",
    "E3B_R1_SHADOW_CLAIM_ID",
    "CapturedPublish",
    "ShadowTaskMaterial",
    "R1ShadowRun",
    "compile_e3b_r1_shadow_contract",
    "run_r1_shadow_condition",
)
