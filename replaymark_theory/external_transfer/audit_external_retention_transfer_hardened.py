#!/usr/bin/env python3
"""Post-result artifact hardening for ReplayMark external retention transfer.

This verifier is intentionally *not* the frozen scientific auditor.  It runs
additional artifact checks after the original decisive result:

* exhaustive NVIDIA historical-decision/tool-event pairing;
* executable AIPerf SPAWN/SPAWN_JOIN construction + consumption checks;
* exact upstream blob verification including bundled licenses;
* machine-readable provenance suitable for a standalone capsule.

Passing this program does not upgrade the original scientific result to G4/G5.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

NVIDIA_COMMIT = "26092ade9de608a71695bfc5800c956b8658ee98"
AIPERF_COMMIT = "13ae4f6b6b5363007ad52ee2470c3b49c9403b34"
SCIENTIFIC_EXECUTION_HEAD = "96edce97f4b79641dcf4b1975e18218f39e37c97"
FROZEN_PROTOCOL_COMMIT = "c7e60c5e03712e7a30ac1e53bccfa2025bfb6fa1"
FROZEN_AUDITOR_COMMIT = "920b759c660a711d94f7aa92bd8059acba8965dc"
ORIGINAL_RUN_ID = 34014534101

UPSTREAM: dict[str, dict[str, str]] = {
    "nvidia_replay.py": {
        "repo": "NVIDIA/TensorRT-LLM",
        "commit": NVIDIA_COMMIT,
        "path": "tensorrt_llm/scaffolding/trace_replay/replay.py",
        "git_blob_sha1": "8561acd566853d9582093aa67af3c468ff87d3da",
    },
    "nvidia_trace.json": {
        "repo": "NVIDIA/TensorRT-LLM",
        "commit": NVIDIA_COMMIT,
        "path": "examples/scaffolding/trace_replay/trace_example/matplotlib__matplotlib-23412/matplotlib__matplotlib-23412.trace.json",
        "git_blob_sha1": "b072d91ba795936957c1d6318f0b0c5e82ea9901",
    },
    "nvidia_README.md": {
        "repo": "NVIDIA/TensorRT-LLM",
        "commit": NVIDIA_COMMIT,
        "path": "examples/scaffolding/trace_replay/README.md",
        "git_blob_sha1": "fcf57ede2452aeee8294fa8990c0976ed3509061",
    },
    "nvidia_blog.md": {
        "repo": "NVIDIA/TensorRT-LLM",
        "commit": NVIDIA_COMMIT,
        "path": "docs/source/blogs/tech_blog/blog27_Evaluating_Agentic_Serving_with_Trace_Replay_and_Job_Level_Metrics.md",
        "git_blob_sha1": "9b6a6321f24fb777994c032f9fd96458ea366329",
    },
    "nvidia_LICENSE": {
        "repo": "NVIDIA/TensorRT-LLM",
        "commit": NVIDIA_COMMIT,
        "path": "LICENSE",
        "git_blob_sha1": "bf9a933a66974480a8ddaaf395b526bfc1f018bd",
    },
    "aiperf_weka_trace.md": {
        "repo": "ai-dynamo/aiperf",
        "commit": AIPERF_COMMIT,
        "path": "docs/tutorials/weka-trace.md",
        "git_blob_sha1": "8e84b82264750e729ca41a9cdab6c3e237fc6eed",
    },
    "aiperf_agentx_mvp.md": {
        "repo": "ai-dynamo/aiperf",
        "commit": AIPERF_COMMIT,
        "path": "docs/tutorials/agentx-mvp.md",
        "git_blob_sha1": "2a8210ecd31f95c699e53c43f104b620a7c18c80",
    },
    "aiperf_weka_trace.py": {
        "repo": "ai-dynamo/aiperf",
        "commit": AIPERF_COMMIT,
        "path": "src/aiperf/dataset/loader/weka_trace.py",
        "git_blob_sha1": "6aa56f42fe83fa443263f0abc6dff0aa6732e245",
    },
    "aiperf_branch_orchestrator.py": {
        "repo": "ai-dynamo/aiperf",
        "commit": AIPERF_COMMIT,
        "path": "src/aiperf/timing/branch_orchestrator.py",
        "git_blob_sha1": "5cdd508134b380cad3a754e66a4ac915f472a41d",
    },
    "aiperf_LICENSE": {
        "repo": "ai-dynamo/aiperf",
        "commit": AIPERF_COMMIT,
        "path": "LICENSE",
        "git_blob_sha1": "261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64",
    },
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    line: int | None = None


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_of(text: str, needle: str) -> int | None:
    idx = text.find(needle)
    return None if idx < 0 else text.count("\n", 0, idx) + 1


def read_utf8(root: Path, name: str) -> tuple[bytes, str]:
    path = root / name
    if not path.is_file():
        raise RuntimeError(f"missing required input: {path}")
    data = path.read_bytes()
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"required input is not UTF-8: {path}") from exc


def function_node(tree: ast.AST, fn_name: str, cls_name: str | None = None) -> ast.AST:
    if cls_name is None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
                return node
    else:
        for node in getattr(tree, "body", []):
            if isinstance(node, ast.ClassDef) and node.name == cls_name:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == fn_name:
                        return child
    raise RuntimeError(f"function not found: {cls_name + '.' if cls_name else ''}{fn_name}")


def node_source(text: str, node: ast.AST) -> str:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        raise RuntimeError("AST node lacks source positions")
    lines = text.splitlines()
    return "\n".join(lines[start - 1 : end])


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def has_call(node: ast.AST, suffix: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = dotted_name(child.func)
            if name and (name == suffix or name.endswith("." + suffix)):
                return True
    return False


def call_count(node: ast.AST, suffix: str) -> int:
    total = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = dotted_name(child.func)
            if name and (name == suffix or name.endswith("." + suffix)):
                total += 1
    return total


def has_spawn_join_constructor(tree: ast.AST) -> bool:
    """True iff executable code constructs TurnPrerequisite(kind=...SPAWN_JOIN)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if not name or not (name == "TurnPrerequisite" or name.endswith(".TurnPrerequisite")):
            continue
        for kw in node.keywords:
            if kw.arg == "kind" and isinstance(kw.value, ast.Attribute) and kw.value.attr == "SPAWN_JOIN":
                return True
    return False


def spawn_join_attribute_count(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "SPAWN_JOIN"
    )


def has_child_plan_session_binding(fn: ast.AST) -> bool:
    """Check that _ChildPlan is constructed with session_id=child_sid."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if not name or not (name == "_ChildPlan" or name.endswith("._ChildPlan")):
            continue
        for kw in node.keywords:
            if kw.arg == "session_id" and isinstance(kw.value, ast.Name) and kw.value.id == "child_sid":
                return True
    return False


def joined_string_contains(node: ast.AST, needle: str) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.JoinedStr):
            literal = "".join(
                part.value for part in child.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if needle in literal:
                return True
    return False


def normalize_branch(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, tuple):
        return value
    return (value,)


def normalize_tool_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("name"), str):
            return value["name"]
        fn = value.get("function")
        if isinstance(fn, dict) and isinstance(fn.get("name"), str):
            return fn["name"]
    return None


def exhaustive_trace_pairing(events: list[Any]) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    tool_event_indices: set[int] = set()
    all_tool_event_indices: set[int] = set()

    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        if event.get("event_type") == "tool_call":
            all_tool_event_indices.add(idx)
        if (
            event.get("event_type") == "message"
            and event.get("role") == "assistant"
            and event.get("tool_calls")
        ):
            raw_calls = event.get("tool_calls")
            if not isinstance(raw_calls, list):
                raw_calls = [raw_calls]
            expected = [normalize_tool_name(v) for v in raw_calls]
            decisions.append(
                {
                    "event_index": idx,
                    "branch_path": list(normalize_branch(event.get("branch_path"))),
                    "expected_tools": expected,
                }
            )

    matched = 0
    pair_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for decision in decisions:
        idx = decision["event_index"]
        branch = tuple(decision["branch_path"])
        expected = decision["expected_tools"]
        observed_names: list[str | None] = []
        observed_indices: list[int] = []

        for j in range(idx + 1, len(events)):
            ev = events[j]
            if not isinstance(ev, dict):
                continue
            if normalize_branch(ev.get("branch_path")) != branch:
                continue
            if ev.get("event_type") == "message":
                break
            if ev.get("event_type") == "tool_call":
                observed_indices.append(j)
                observed_names.append(normalize_tool_name(ev.get("tool_name")))

        exact = (
            all(name is not None for name in expected)
            and observed_names == expected
            and not any(i in tool_event_indices for i in observed_indices)
        )
        record = {
            **decision,
            "observed_tools": observed_names,
            "tool_event_indices": observed_indices,
            "exact": exact,
        }
        pair_records.append(record)
        if exact:
            matched += 1
            tool_event_indices.update(observed_indices)
        else:
            failures.append(record)

    all_tool_events_consumed = tool_event_indices == all_tool_event_indices
    declared_tool_count = sum(len(d["expected_tools"]) for d in decisions)
    return {
        "assistant_decisions": len(decisions),
        "declared_tool_choices": declared_tool_count,
        "historical_tool_events": len(all_tool_event_indices),
        "matched_assistant_decisions": matched,
        "matched_tool_events": len(tool_event_indices),
        "all_tool_events_consumed_once": all_tool_events_consumed,
        "complete": matched == len(decisions) and all_tool_events_consumed,
        "pairs": pair_records,
        "failures": failures,
    }


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
            "schema": "replaymark.external_transfer_artifact_hardening.v1",
            "decision": "FAIL_INTEGRITY",
            "scientific_result_unchanged": True,
            "integrity": integrity,
            "checks": [asdict(c) for c in checks],
        }
        (args.output_dir / "HARDENED_EXTERNAL_TRANSFER_RESULTS.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        return 2

    # ------------------------------------------------------------------
    # H1: exhaustive NVIDIA trace pairing.
    # ------------------------------------------------------------------
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
                "every historical tool_call event is consumed exactly once by the same-branch pairing",
            ),
        ]
    )

    # Reconfirm the source-level serving-generation / retained-delay separation
    # with wording narrower than target-native semantic generation.
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

    # ------------------------------------------------------------------
    # H3: executable AIPerf topology retention.
    # ------------------------------------------------------------------
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
                "executable _expand_subagent_to_child_plans builds ::sa: child ids and binds them to _ChildPlan.session_id",
                getattr(expand_node, "lineno", None),
            ),
            Check(
                "H3.aiperf.spawn_join_constructed",
                has_spawn_join_constructor(weka_tree),
                "loader executable code constructs TurnPrerequisite(kind=PrerequisiteKind.SPAWN_JOIN)",
            ),
            Check(
                "H3.aiperf.spawn_join_consumed",
                spawn_join_attribute_count(orchestrator_tree) >= 1,
                f"BranchOrchestrator executable AST references SPAWN_JOIN {spawn_join_attribute_count(orchestrator_tree)} time(s)",
            ),
        ]
    )

    h1 = all(c.passed for c in checks if c.name.startswith("H1."))
    h2 = all(c.passed for c in checks if c.name.startswith("H2."))
    h3 = all(c.passed for c in checks if c.name.startswith("H3."))
    hardening_pass = integrity_pass and h1 and h2 and h3

    result = {
        "schema": "replaymark.external_transfer_artifact_hardening.v1",
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
        "hardening_gates": {
            "H0_integrity": integrity_pass,
            "H1_exhaustive_nvidia_pairing": h1,
            "H2_nvidia_source_reconfirmation": h2,
            "H3_executable_aiperf_topology": h3,
        },
        "nvidia_pairing": pairing,
        "integrity": integrity,
        "checks": [asdict(c) for c in checks],
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
        },
    }

    (args.output_dir / "HARDENED_EXTERNAL_TRANSFER_RESULTS.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    (args.output_dir / "UPSTREAM_MANIFEST.json").write_text(
        json.dumps(
            {
                "schema": "replaymark.external_transfer_upstream_manifest.v1",
                "scientific_execution_head": SCIENTIFIC_EXECUTION_HEAD,
                "upstream": integrity,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    report: list[str] = []
    report.append("# ReplayMark External Transfer — Artifact Hardening Report")
    report.append("")
    report.append(f"**Decision:** `{result['decision']}`")
    report.append("")
    report.append("This is a post-result artifact check. The original frozen scientific decision is unchanged: G3 PASS; G4/G5 NOT SATISFIED.")
    report.append("")
    report.append("## Hardened gates")
    report.append("")
    for name, value in result["hardening_gates"].items():
        report.append(f"- `{name}`: **{'PASS' if value else 'FAIL'}**")
    report.append("")
    report.append("## NVIDIA exhaustive pairing")
    report.append("")
    report.append(
        f"- Assistant events carrying historical tool choices: **{pairing['assistant_decisions']}**"
    )
    report.append(f"- Declared historical tool choices: **{pairing['declared_tool_choices']}**")
    report.append(f"- Historical `tool_call` events: **{pairing['historical_tool_events']}**")
    report.append(
        f"- Exact same-branch decision blocks matched: **{pairing['matched_assistant_decisions']}/{pairing['assistant_decisions']}**"
    )
    report.append(
        f"- Historical tool events consumed exactly once: **{pairing['matched_tool_events']}/{pairing['historical_tool_events']}**"
    )
    report.append("")
    report.append("## AIPerf executable topology checks")
    report.append("")
    report.append("The hardened verifier does not rely only on documentation strings: it parses the pinned loader and branch orchestrator, verifies executable child-plan construction, executable `SPAWN_JOIN` prerequisite construction, and orchestrator consumption of `SPAWN_JOIN`.")
    report.append("")
    report.append("## All checks")
    report.append("")
    for check in checks:
        loc = f" (line {check.line})" if check.line is not None else ""
        report.append(f"- {'PASS' if check.passed else 'FAIL'} `{check.name}`{loc}: {check.detail}")
    report.append("")
    report.append("## Anti-overclaim boundary")
    report.append("")
    report.append("This hardening run confirms artifact robustness only. It does not establish that TensorRT-LLM or AIPerf is globally invalid, does not establish prevalence, does not prove a target-native historical action has zero support, and does not establish an external downstream benchmark flip.")
    report.append("")
    (args.output_dir / "HARDENED_EXTERNAL_TRANSFER_REPORT.md").write_text("\n".join(report))

    print(result["decision"])
    print(
        "NVIDIA pairing: "
        f"{pairing['matched_assistant_decisions']}/{pairing['assistant_decisions']} decisions; "
        f"{pairing['matched_tool_events']}/{pairing['historical_tool_events']} tool events"
    )
    return 0 if hardening_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
