from __future__ import annotations

"""Independent literal definition oracle for the E3b same-task relation.

The oracle intentionally does not import the production correlation module.
Individual observation/action realization has separate independent gates; this
oracle checks only the newly introduced pairwise task/context relation.
"""

from dataclasses import dataclass
import re
from typing import Mapping


_OBS = re.compile(r"^(?P<prefix>[^/+#\x00]+)-(?P<task>0|[1-9][0-9]*)-a$")
_ACT = re.compile(
    r"^agentmark/(?P<prefix>[^/+#\x00]+)-(?P<task>0|[1-9][0-9]*)-b/command$"
)


@dataclass(frozen=True)
class OracleE3bCorrelation:
    ok: bool
    error_code: str | None
    task_prefix: str | None
    task_id: int | None


def definition_correlate_e3b_task(
    raw_observation: object,
    raw_historical_action: object,
) -> OracleE3bCorrelation:
    if not isinstance(raw_observation, Mapping) or not isinstance(
        raw_historical_action, Mapping
    ):
        return OracleE3bCorrelation(False, "MALFORMED_IDENTITY", None, None)

    expected_device = raw_observation.get("expected_device")
    topic = raw_historical_action.get("topic")
    if not isinstance(expected_device, str) or not isinstance(topic, str):
        return OracleE3bCorrelation(False, "MALFORMED_IDENTITY", None, None)

    obs = _OBS.fullmatch(expected_device)
    if obs is None:
        # Keep role failures distinct when the identity shape is otherwise clear.
        try:
            _prefix, task, role = expected_device.rsplit("-", 2)
        except ValueError:
            return OracleE3bCorrelation(False, "MALFORMED_IDENTITY", None, None)
        if role != "a" and task.isascii() and task.isdigit():
            return OracleE3bCorrelation(False, "ROLE_MISMATCH", None, None)
        return OracleE3bCorrelation(False, "MALFORMED_IDENTITY", None, None)

    act = _ACT.fullmatch(topic)
    if act is None:
        return OracleE3bCorrelation(False, "MALFORMED_IDENTITY", None, None)

    obs_prefix = obs.group("prefix")
    act_prefix = act.group("prefix")
    obs_task = int(obs.group("task"))
    act_task = int(act.group("task"))
    if obs_prefix != act_prefix or obs_task != act_task:
        return OracleE3bCorrelation(False, "TASK_MISMATCH", None, None)

    obs_domain = raw_observation.get("clock_domain")
    act_domain = raw_historical_action.get("clock_domain")
    if obs_domain != act_domain:
        return OracleE3bCorrelation(False, "CLOCK_DOMAIN_MISMATCH", None, None)

    command = raw_observation.get("command_publish_mono_ns")
    publish = raw_historical_action.get("publish_mono_ns")
    if (
        isinstance(command, bool)
        or not isinstance(command, int)
        or isinstance(publish, bool)
        or not isinstance(publish, int)
    ):
        return OracleE3bCorrelation(False, "MALFORMED_IDENTITY", None, None)
    if publish < command:
        return OracleE3bCorrelation(False, "TEMPORAL_INCONSISTENCY", None, None)

    return OracleE3bCorrelation(True, None, obs_prefix, obs_task)


__all__ = ("OracleE3bCorrelation", "definition_correlate_e3b_task")
