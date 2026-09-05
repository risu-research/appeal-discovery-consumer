"""Execution-only $SYS freshness fix for the preregistered causal audit.

Mosquitto may omit unchanged non-static $SYS publish counters after a quiet
serial condition. `fresh_sys_snapshot()` first freezes a monotonic timestamp and
then calls `wait_all_sys_after(stamp)`. We inject exactly one measurement
PUBLISH *inside that wait call*, i.e. after the timestamp is frozen, so the next
$SYS interval must expose counters newer than the frozen stamp.

The measurement PUBLISH targets a Harness-subscribed state topic, forcing both
broker received and sent publish counters to change. The exactly-one received
PUBLISH is removed from every before/after delta used by the audit's PUBLISH
conservation invariant. No task, deadline, condition, hypothesis, effect
threshold, randomization scheme, or decision rule is changed.
"""
from __future__ import annotations

import json
import runpy
import time
import uuid

import experiment

PUB = "$SYS/broker/publish/messages/received"
_original_wait = experiment.Harness.wait_all_sys_after
_original_delta = experiment._sys_delta


def _wait_all_sys_after_with_barrier(self, after_ns, timeout_s=3.5):
    payload = json.dumps({
        "device": f"audit-barrier-{uuid.uuid4().hex[:8]}",
        "on": False,
        "cause": "measurement_barrier",
        "t_mono_ns": time.monotonic_ns(),
    }, separators=(",", ":"))
    info = self.client.publish("agentmark/audit-barrier/state", payload, qos=1)
    info.wait_for_publish()
    return _original_wait(self, after_ns, timeout_s)


def _delta_without_after_barrier(before, after):
    out = _original_delta(before, after)
    if PUB in out:
        out[PUB] = float(out[PUB]) - 1.0
    return out


experiment.Harness.wait_all_sys_after = _wait_all_sys_after_with_barrier
experiment._sys_delta = _delta_without_after_barrier

runpy.run_path("/app/audit/causal_audit.py", run_name="__main__")
