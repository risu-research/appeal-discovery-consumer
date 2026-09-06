#!/usr/bin/env python3
"""Deterministic post-result hardening verifier for ReplayMark external transfer.

This v2 verifier deliberately separates canonical scientific/artifact outputs
from volatile runtime metadata so an extracted capsule can reproduce the
canonical JSON/report byte-for-byte on another machine.

It imports the post-result v1 helper library but emits its own deterministic
result schema.  It does not alter or upgrade the frozen G3 scientific result.
"""

from __future__ import annotations

import argparse
import ast
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from audit_external_retention_transfer_hardened import (
    AIPERF_COMMIT,
    FROZEN_AUDITOR_COMMIT,
    FROZEN_PROTOCOL_COMMIT,
    NVIDIA_COMMIT,
    ORIGINAL_RUN_ID,
    SCIENTIFIC_EXECUTION_HEAD,
    UPSTREAM,
    Check,
    call_count,
    exhaustive_trace_pairing,
    function_node,
    git_blob_sha,
    has_child_plan_session_binding,
    has_call,
    has_spawn_join_constructor,
    joined_string_contains,
    line_of,
    node_source,
    read_utf8,
    sha256,
)


def has_spawn_join_compare(tree: ast.AST) -> bool:
    """Require SPAWN_JOIN to participate in executable comparison logic."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        attrs = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Attribute) and n.attr == "SPAWN_JOIN"
        ]
        if attrs:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    checks: list[Check] = []
    integrity: dict[str, Any] = {}
    loaded: dict[str, tuple[bytes, str]] = {}

    for name, meta in UPSTREAM.items():
        data, text = read_utf8(args.input_dir, name)
        got_blob = git_blob_sha(data)
        loaded[name] = (data, text)
        integrity[name] = {
            **meta,
            "observed_git_blob_sha1": got_blob,
            "sha256": sha256(data),
            "bytes": len(data),
        }
        checks.append(
            Check(
                f"H0.integrity.{name}",
                got_blob == meta["git_blob_sha1"],
                f"expected={meta['git_blob_sha1']} observed={got_blob}",
            )
        )

    integrity_pass = all(c.passed for c in checks if c.name.startswith("H0.integrity."))
    if not integrity_pass:
        result = {
            "schema": "replaymark.external_transfer_artifact_hardening.v2",
            "decision": "FAIL_INTEGRITY",
            "scientific_result_unchanged": True,
            "integrity": integrity,
            "checks": [asdict(c) for c in checks],
        }
        (args.output_dir / "HARDENED_EXTERNAL_TRANSFER_RESULTS_V2.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 2

    trace_obj = json.loads(loaded["nvidia_trace.json"][1])
    events = trace_obj.get("events")
    if not isinstance(events, list):
        raise RuntimeError("NVIDIA trace lacks events list")
    pairing = exhaustive_trace_pairing(events)
    checks.extend(
        [
            Check(
                "H1.nvidia_pairing.complete",
                bool(pairing["complete"]),
                (
                    f"matched assistant decisions={pairing['matched_assistant_decisions']}/"
                    f"{pairing['assistant_decisions']}; matched tool events="
                    f"{pairing['matched_tool_events']}/{pairing['historical_tool_events']}"
                ),
            ),
            Check(
                "H1.nvidia_pairing.counts_equal",
                pairing["declared_tool_choices"] == pairing["historical_tool_events"],
                (
                    f"declared tool choices={pairing['declared_tool_choices']} "
                    f"historical tool events={pairing['historical_tool_events']}"
                ),
            ),
            Check(
                "H1.nvidia_pairing.consume_once",
                bool(pairing["all_tool_events_consumed_once"]),
                "every historical tool_call event is consumed exactly once by same-branch pairing",
            ),
        ]
    )

    replay_text = loaded["nvidia_replay.py"][1]
    replay_tree = ast.parse(replay_text)
    msg_node = function_node(replay_tree, "_handle_message", "QueueExecutor")
    tool_node = function_node(replay_tree, "_handle_tool_call", "QueueExecutor")
    launch_node = function_node(replay_tree, "launch_trace", "ReplayEngine")
    msg_src = node_source(replay_text, msg_node)
    tool_src = node_source(replay_text, tool_node)
    launch_src = node_source(replay_text, launch_node)
    checks.extend(
        [
            Check(
                "H2.nvidia_source.fresh_serving_generation",
                has_call(msg_node, "worker.run_task"),
                "assistant replay invokes serving worker.run_task",
                getattr(msg_node, "lineno", None),
            ),
            Check(
                "H2.nvidia_source.tool_delay_sleep",
                "event.duration_ms" in tool_src and has_call(tool_node, "asyncio.sleep"),
                "historical tool_call handler consumes recorded duration as a sleep",
                getattr(tool_node, "lineno", None),
            ),
            Check(
                "H2.nvidia_source.no_trace_tool_choice_guard",
                "event.tool_calls" not in msg_src,
                "assistant serving-generation path does not consult historical event.tool_calls",
                getattr(msg_node, "lineno", None),
            ),
            Check(
                "H2.nvidia_source.trace_event_route",
                "trace.events" in launch_src and "await queue.put(event)" in launch_src,
                "historical event stream is routed to branch queues",
                getattr(launch_node, "lineno", None),
            ),
        ]
    )

    weka_doc = loaded["aiperf_weka_trace.md"][1]
    agentx_doc = loaded["aiperf_agentx_mvp.md"][1]
    weka_code = loaded["aiperf_weka_trace.py"][1]
    orchestrator_code = loaded["aiperf_branch_orchestrator.py"][1]
    weka_tree = ast.parse(weka_code)
    orchestrator_tree = ast.parse(orchestrator_code)
    expand_node = function_node(weka_tree, "_expand_subagent_to_child_plans")
    checks.extend(
        [
            Check(
                "H3.aiperf.model_rewrite_documented",
                "the trace's recorded model names don't have to match what you're serving" in weka_doc,
                "pinned docs explicitly permit a served model different from recorded trace model names",
                line_of(weka_doc, "the trace's recorded model names don't have to match what you're serving"),
            ),
            Check(
                "H3.aiperf.agentx_model_rewrite_corrob",
                "you don't have to match" in agentx_doc,
                "AgentX recipe separately states baked-in model names need not match",
                line_of(agentx_doc, "you don't have to match"),
            ),
            Check(
                "H3.aiperf.expand_subagent_invoked",
                call_count(weka_tree, "_expand_subagent_to_child_plans") >= 1,
                f"loader calls _expand_subagent_to_child_plans {call_count(weka_tree, '_expand_subagent_to_child_plans')} time(s)",
            ),
            Check(
                "H3.aiperf.child_session_constructed",
                joined_string_contains(expand_node, "::sa:") and has_child_plan_session_binding(expand_node),
                "executable subagent expansion builds ::sa: child ids and binds them to _ChildPlan.session_id",
                getattr(expand_node, "lineno", None),
            ),
            Check(
                "H3.aiperf.spawn_join_constructed",
                has_spawn_join_constructor(weka_tree),
                "loader executable code constructs TurnPrerequisite(kind=PrerequisiteKind.SPAWN_JOIN)",
            ),
            Check(
                "H3.aiperf.spawn_join_consumed_in_control_flow",
                has_spawn_join_compare(orchestrator_tree),
                "BranchOrchestrator executable comparison logic consumes SPAWN_JOIN prerequisites",
            ),
        ]
    )

    h1 = all(c.passed for c in checks if c.name.startswith("H1."))
    h2 = all(c.passed for c in checks if c.name.startswith("H2."))
    h3 = all(c.passed for c in checks if c.name.startswith("H3."))
    hardening_pass = integrity_pass and h1 and h2 and h3

    result = {
        "schema": "replaymark.external_transfer_artifact_hardening.v2",
        "decision": "ARTIFACT_HARDENING_PASS" if hardening_pass else "ARTIFACT_HARDENING_FAIL",
        "scientific_result_unchanged": True,
        "original_scientific_result": {
            "execution_head": SCIENTIFIC_EXECUTION_HEAD,
            "frozen_protocol_commit": FROZEN_PROTOCOL_COMMIT,
            "frozen_auditor_commit": FROZEN_AUDITOR_COMMIT,
            "run_id": ORIGINAL_RUN_ID,
            "G3_external_retention_transfer": "PASS",
            "G4_external_invalidity": "NOT_SATISFIED",
            "G5_external_downstream_flip": "NOT_SATISFIED",
        },
        "upstream_commits": {
            "NVIDIA/TensorRT-LLM": NVIDIA_COMMIT,
            "ai-dynamo/aiperf": AIPERF_COMMIT,
        },
        "hardening_gates": {
            "H0_integrity": integrity_pass,
            "H1_exhaustive_nvidia_pairing": h1,
            "H2_nvidia_source_reconfirmation": h2,
            "H3_executable_aiperf_topology": h3,
        },
        "nvidia_pairing": pairing,
        "integrity": integrity,
        "checks": [asdict(c) for c in checks],
    }

    result_path = args.output_dir / "HARDENED_EXTERNAL_TRANSFER_RESULTS_V2.json"
    report_path = args.output_dir / "HARDENED_EXTERNAL_TRANSFER_REPORT_V2.md"
    runtime_path = args.output_dir / "HARDENING_RUNTIME_INFO.json"
    manifest_path = args.output_dir / "UPSTREAM_MANIFEST_V2.json"

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "replaymark.external_transfer_upstream_manifest.v2",
                "scientific_execution_head": SCIENTIFIC_EXECUTION_HEAD,
                "upstream": integrity,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_path.write_text(
        json.dumps(
            {"python": sys.version, "platform": platform.platform()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report: list[str] = [
        "# ReplayMark External Transfer — Deterministic Artifact Hardening v2",
        "",
        f"**Decision:** `{result['decision']}`",
        "",
        "Canonical JSON/report outputs intentionally exclude runtime-specific metadata so independent offline reruns can be compared byte-for-byte.",
        "",
        "The original scientific decision is unchanged: G3 PASS; G4/G5 NOT SATISFIED.",
        "",
        "## Hardened gates",
        "",
    ]
    for name, value in result["hardening_gates"].items():
        report.append(f"- `{name}`: **{'PASS' if value else 'FAIL'}**")
    report.extend(
        [
            "",
            "## NVIDIA exhaustive pairing",
            "",
            f"- Assistant historical-decision events: **{pairing['assistant_decisions']}**",
            f"- Declared historical tool choices: **{pairing['declared_tool_choices']}**",
            f"- Historical `tool_call` events: **{pairing['historical_tool_events']}**",
            f"- Exact same-branch decision blocks matched: **{pairing['matched_assistant_decisions']}/{pairing['assistant_decisions']}**",
            f"- Historical tool events consumed exactly once: **{pairing['matched_tool_events']}/{pairing['historical_tool_events']}**",
            "",
            "## AIPerf executable topology",
            "",
            "The verifier parses the exact pinned loader and branch orchestrator. It confirms executable child-plan construction, executable `SPAWN_JOIN` prerequisite construction, and use of `SPAWN_JOIN` inside orchestrator comparison/control-flow logic.",
            "",
            "## All checks",
            "",
        ]
    )
    for check in checks:
        loc = f" (line {check.line})" if check.line is not None else ""
        report.append(f"- {'PASS' if check.passed else 'FAIL'} `{check.name}`{loc}: {check.detail}")
    report.extend(
        [
            "",
            "## Anti-overclaim boundary",
            "",
            "This remains a post-result artifact confirmation. It does not establish global invalidity, prevalence, target-native zero support, or an external downstream benchmark flip.",
            "",
        ]
    )
    report_path.write_text("\n".join(report), encoding="utf-8")

    print(result["decision"])
    print(
        f"NVIDIA pairing: {pairing['matched_assistant_decisions']}/{pairing['assistant_decisions']} decisions; "
        f"{pairing['matched_tool_events']}/{pairing['historical_tool_events']} tool events"
    )
    return 0 if hardening_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
