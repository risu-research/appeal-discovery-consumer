"""Execution-only $SYS freshness fix for the preregistered causal audit.

Mosquitto may omit unchanged non-static $SYS publish-received counters after a
quiet serial condition. Before every fresh_sys_snapshot we therefore emit one
post-condition measurement PUBLISH to a topic subscribed by the Harness. This
forces received+sent publish counters to change before the next $SYS interval.
The exactly-one measurement PUBLISH is then removed from the received-PUBLISH
delta used by the audit's conservation invariant. No task, deadline, condition,
hypothesis, effect threshold, or decision rule is changed.
"""
from __future__ import annotations

import json
import runpy
import time
import uuid

import experiment

PUB = "$SYS/broker/publish/messages/received"
_original_fresh = experiment.Harness.fresh_sys_snapshot
_original_delta = experiment._sys_delta


def _fresh_with_barrier(self):
    payload = json.dumps({
        "device": f"audit-barrier-{uuid.uuid4().hex[:8]}",
        "on": False,
        "cause": "measurement_barrier",
        "t_mono_ns": time.monotonic_ns(),
    }, separators=(",", ":"))
    info = self.client.publish("agentmark/audit-barrier/state", payload, qos=1)
    info.wait_for_publish()
    return _original_fresh(self)


def _delta_without_after_barrier(before, after):
    out = _original_delta(before, after)
    if PUB in out:
        out[PUB] = float(out[PUB]) - 1.0
    return out


experiment.Harness.fresh_sys_snapshot = _fresh_with_barrier
experiment._sys_delta = _delta_without_after_barrier

runpy.run_path("/app/audit/causal_audit.py", run_name="__main__")
