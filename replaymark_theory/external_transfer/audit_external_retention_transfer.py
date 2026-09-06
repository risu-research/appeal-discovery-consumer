#!/usr/bin/env python3
"""Fail-closed ReplayMark audit of pinned third-party replay artifacts.

This program does not decide whether an external benchmark is globally valid.
It checks the predeclared retention invariants in
EXTERNAL_RETENTION_TRANSFER_PROTOCOL.md and emits claim-sensitive verdicts.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    line: int | None = None


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_of(text: str, needle: str) -> int | None:
    idx = text.find(needle)
    if idx < 0:
        return None
    return text.count("\n", 0, idx) + 1


def require_file(root: Path, name: str) -> tuple[Path, bytes, str]:
    p = root / name
    if not p.is_file():
        raise RuntimeError(f"missing required input: {p}")
    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"required input is not UTF-8: {p}") from exc
    return p, data, text


def function_node(tree: ast.AST, cls_name: str | None, fn_name: str) -> ast.AST:
    if cls_name is None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
                return node
    else:
        for node in tree.body:  # type: ignore[attr-defined]
            if isinstance(node, ast.ClassDef) and node.name == cls_name:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == fn_name:
                        return child
    raise RuntimeError(f"function not found: {cls_name + '.' if cls_name else ''}{fn_name}")


def node_source(text: str, node: ast.AST) -> str:
    lines = text.splitlines()
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        raise RuntimeError("AST node lacks source positions")
    return "\n".join(lines[start - 1 : end])


def has_call(node: ast.AST, dotted_suffix: str) -> bool:
    def dotted(n: ast.AST) -> str | None:
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.Attribute):
            base = dotted(n.value)
            return f"{base}.{n.attr}" if base else n.attr
        return None

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = dotted(child.func)
            if name and (name == dotted_suffix or name.endswith("." + dotted_suffix)):
                return True
    return False


def text_check(name: str, text: str, needle: str, detail: str | None = None) -> Check:
    loc = line_of(text, needle)
    return Check(name, loc is not None, detail or needle, loc)


def all_pass(checks: Iterable[Check], prefixes: tuple[str, ...]) -> bool:
    selected = [c for c in checks if c.name.startswith(prefixes)]
    return bool(selected) and all(c.passed for c in selected)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    expected = {
        "nvidia_replay.py": "8561acd566853d9582093aa67af3c468ff87d3da",
        "nvidia_trace.json": "b072d91ba795936957c1d6318f0b0c5e82ea9901",
        "nvidia_README.md": "fcf57ede2452aeee8294fa8990c0976ed3509061",
        "nvidia_blog.md": "9b6a6321f24fb777994c032f9fd96458ea366329",
        "aiperf_weka_trace.md": "8e84b82264750e729ca41a9cdab6c3e237fc6eed",
        "aiperf_agentx_mvp.md": "2a8210ecd31f95c699e53c43f104b620a7c18c80",
        "aiperf_weka_trace.py": "6aa56f42fe83fa443263f0abc6dff0aa6732e245",
    }

    loaded: dict[str, tuple[bytes, str]] = {}
    integrity: dict[str, Any] = {}
    checks: list[Check] = []

    # G0: exact upstream bytes.
    for name, want_blob in expected.items():
        _, data, text = require_file(args.input_dir, name)
        got_blob = git_blob_sha(data)
        loaded[name] = (data, text)
        integrity[name] = {
            "expected_git_blob_sha1": want_blob,
            "observed_git_blob_sha1": got_blob,
            "sha256": sha256(data),
            "bytes": len(data),
        }
        checks.append(
            Check(
                f"G0.integrity.{name}",
                got_blob == want_blob,
                f"expected={want_blob} observed={got_blob}",
            )
        )

    integrity_pass = all(c.passed for c in checks if c.name.startswith("G0.integrity."))
    if not integrity_pass:
        result = {
            "schema": "replaymark.external_retention_transfer.v1",
            "decision": "FAIL_INTEGRITY",
            "integrity": integrity,
            "checks": [asdict(c) for c in checks],
        }
        (args.output_dir / "EXTERNAL_RETENTION_TRANSFER_RESULTS.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print("EXTERNAL RETENTION TRANSFER: FAIL_INTEGRITY")
        return 2

    # ------------------------------------------------------------------
    # Candidate A: NVIDIA TensorRT-LLM
    # ------------------------------------------------------------------
    replay_text = loaded["nvidia_replay.py"][1]
    trace_text = loaded["nvidia_trace.json"][1]
    readme_text = loaded["nvidia_README.md"][1]
    blog_text = loaded["nvidia_blog.md"][1]

    try:
        replay_tree = ast.parse(replay_text)
    except SyntaxError as exc:
        raise RuntimeError("pinned NVIDIA replay.py failed AST parse") from exc

    tool_node = function_node(replay_tree, "QueueExecutor", "_handle_tool_call")
    msg_node = function_node(replay_tree, "QueueExecutor", "_handle_message")
    launch_node = function_node(replay_tree, "ReplayEngine", "launch_trace")
    tool_src = node_source(replay_text, tool_node)
    msg_src = node_source(replay_text, msg_node)
    launch_src = node_source(replay_text, launch_node)

    # A1: fresh target generation.
    checks.append(
        Check(
            "A1.fresh_target_generation.worker_run_task",
            has_call(msg_node, "worker.run_task"),
            "QueueExecutor._handle_message invokes self.worker.run_task for replay generation",
            getattr(msg_node, "lineno", None),
        )
    )
    checks.append(
        Check(
            "A1.fresh_target_generation.assistant_branch",
            'role == "assistant"' in msg_src,
            "target generation path occurs in assistant-message branch",
            line_of(replay_text, 'elif role == "assistant"'),
        )
    )

    # A2: retained historical tool event becomes timed wait, not regenerated tool execution.
    checks.append(
        Check(
            "A2.historical_tool_replay.duration_field",
            "event.duration_ms" in tool_src,
            "_handle_tool_call reads recorded duration_ms",
            line_of(replay_text, "event.duration_ms"),
        )
    )
    checks.append(
        Check(
            "A2.historical_tool_replay.sleep",
            has_call(tool_node, "asyncio.sleep"),
            "_handle_tool_call simulates historical tool latency via asyncio.sleep",
            getattr(tool_node, "lineno", None),
        )
    )
    checks.append(
        Check(
            "A2.historical_tool_replay.no_worker_execution",
            not has_call(tool_node, "worker.run_task"),
            "_handle_tool_call does not regenerate/execute tool choice through worker.run_task",
            getattr(tool_node, "lineno", None),
        )
    )

    # A3: no semantic linkage between fresh target output and later retained tool event.
    checks.append(
        Check(
            "A3.no_semantic_guard.assistant_does_not_consult_trace_tool_calls",
            "event.tool_calls" not in msg_src,
            "assistant replay does not consult historical event.tool_calls to validate fresh output",
            getattr(msg_node, "lineno", None),
        )
    )
    checks.append(
        Check(
            "A3.no_semantic_guard.trace_iteration",
            "trace.events" in launch_src,
            "ReplayEngine.launch_trace iterates the historical event stream",
            line_of(replay_text, "for event in trace.events"),
        )
    )
    checks.append(
        Check(
            "A3.no_semantic_guard.unconditional_queue_route",
            has_call(launch_node, "queue.put") and "await queue.put(event)" in launch_src,
            "non-parallel historical events are enqueued from trace stream",
            line_of(replay_text, "await queue.put(event)"),
        )
    )

    # A4: independently shipped trace contains historical decision + tool event.
    try:
        trace_obj = json.loads(trace_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("pinned NVIDIA trace is invalid JSON") from exc
    events = trace_obj.get("events")
    if not isinstance(events, list):
        raise RuntimeError("pinned NVIDIA trace lacks events list")

    assistant_decisions: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        if ev.get("event_type") == "message" and ev.get("role") == "assistant" and ev.get("tool_calls"):
            assistant_decisions.append({"event_index": i, "tool_calls": ev.get("tool_calls"), "event": ev})
        if ev.get("event_type") == "tool_call":
            tool_events.append({"event_index": i, "tool_name": ev.get("tool_name"), "event": ev})

    first_witness = None
    for d in assistant_decisions:
        historical = d["tool_calls"]
        for t in tool_events:
            if t["event_index"] > d["event_index"] and t["tool_name"] in historical:
                first_witness = {
                    "assistant_event_index": d["event_index"],
                    "historical_tool_calls": historical,
                    "tool_event_index": t["event_index"],
                    "tool_name": t["tool_name"],
                }
                break
        if first_witness:
            break

    checks.append(
        Check(
            "A4.shipped_trace.assistant_historical_tool_decisions",
            len(assistant_decisions) > 0,
            f"assistant messages with non-empty historical tool_calls={len(assistant_decisions)}",
        )
    )
    checks.append(
        Check(
            "A4.shipped_trace.tool_call_events",
            len(tool_events) > 0,
            f"historical tool_call events={len(tool_events)}",
        )
    )
    checks.append(
        Check(
            "A4.shipped_trace.matched_first_witness",
            first_witness is not None,
            f"first matched historical decision/tool event={first_witness}",
        )
    )

    # Declared intent markers are context only; still freeze/check their presence.
    checks.append(
        text_check(
            "A_context.readme.tool_replay_decoupling",
            readme_text,
            "Tool replay decoupling",
            "README explicitly names tool replay decoupling",
        )
    )
    checks.append(
        text_check(
            "A_context.blog.different_model",
            blog_text,
            "replayed against a different model than the one that produced it",
            "official blog permits replay against a different model",
        )
    )
    checks.append(
        text_check(
            "A_context.blog.tool_sleep",
            blog_text,
            "simulates these external delays via sleep operations",
            "official blog declares tool-time simulation",
        )
    )

    nvidia_source_pass = all_pass(checks, ("A1.", "A2.", "A3.", "A4."))

    # ------------------------------------------------------------------
    # Candidate B: AIPerf AgentX
    # ------------------------------------------------------------------
    weka_doc = loaded["aiperf_weka_trace.md"][1]
    agentx_doc = loaded["aiperf_agentx_mvp.md"][1]
    weka_code = loaded["aiperf_weka_trace.py"][1]

    checks.append(
        text_check(
            "B1.model_rewrite.target_model",
            weka_doc,
            "Whatever you pass to `--model` becomes the model the server actually sees.",
            "AIPerf states configured --model is the served model",
        )
    )
    checks.append(
        text_check(
            "B1.model_rewrite.recorded_names_need_not_match",
            weka_doc,
            "the trace's recorded model names don't have to match what you're serving",
            "recorded trace model may differ from served model",
        )
    )
    checks.append(
        text_check(
            "B1.model_rewrite.agentx_recipe",
            agentx_doc,
            "you don't have to match",
            "AgentX recipe independently states model names baked into trace need not match served model",
        )
    )

    checks.append(
        text_check(
            "B2.topology_retain.doc_child_sessions",
            weka_doc,
            "AIPerf replays them as separate concurrent child sessions that the parent waits on before resuming.",
            "recorded subagent topology is replayed as concurrent children with parent wait",
        )
    )
    checks.append(
        text_check(
            "B2.topology_retain.code_spawn_join",
            weka_code,
            "SPAWN + SPAWN_JOIN prerequisites",
            "loader source declares reconstructed SPAWN/SPAWN_JOIN dependencies",
        )
    )
    checks.append(
        text_check(
            "B2.topology_retain.code_child_conversations",
            weka_code,
            "one root Conversation plus one or more child Conversations",
            "loader source reconstructs recorded child conversations",
        )
    )

    aiperf_source_pass = all_pass(checks, ("B1.", "B2."))

    g3 = integrity_pass and nvidia_source_pass and aiperf_source_pass

    verdicts = {
        "nvidia_tensorrt_llm": {
            "C_fixed": "LICENSED_AS_FIXED_WORKLOAD_OBJECT" if nvidia_source_pass else "NOT_ADJUDICATED",
            "C_native": "UNRESOLVED" if nvidia_source_pass else "NOT_ADJUDICATED",
            "invalidity_promoted": False,
        },
        "aiperf_agentx": {
            "C_fixed": "LICENSED_AS_FIXED_WORKLOAD_OBJECT" if aiperf_source_pass else "NOT_ADJUDICATED",
            "C_native": "UNRESOLVED" if aiperf_source_pass else "NOT_ADJUDICATED",
            "invalidity_promoted": False,
        },
    }

    result = {
        "schema": "replaymark.external_retention_transfer.v1",
        "protocol_commit_required_before_audit": True,
        "upstream_pins": {
            "NVIDIA/TensorRT-LLM": "26092ade9de608a71695bfc5800c956b8658ee98",
            "ai-dynamo/aiperf": "13ae4f6b6b5363007ad52ee2470c3b49c9403b34",
        },
        "integrity": integrity,
        "checks": [asdict(c) for c in checks],
        "nvidia_trace_summary": {
            "trace_id": trace_obj.get("trace_id"),
            "event_count": len(events),
            "assistant_messages_with_historical_tool_calls": len(assistant_decisions),
            "historical_tool_call_events": len(tool_events),
            "first_witness": first_witness,
        },
        "gates": {
            "G0_integrity": integrity_pass,
            "G1_nvidia_source_transfer": nvidia_source_pass,
            "G2_aiperf_source_transfer": aiperf_source_pass,
            "G3_external_retention_transfer": g3,
            "G4_external_invalidity": False,
            "G5_external_downstream_flip": False,
        },
        "verdicts": verdicts,
        "decision": "PROMOTED_SOURCE_TRANSFER" if g3 else "FAIL_SOURCE_TRANSFER",
        "licensed_claim": (
            "Two independently authored agent-serving trace-replay implementations retain "
            "historical agent structure while permitting a different/fresh serving target. "
            "ReplayMark does not reject fixed-workload serving claims; the same replay "
            "evidence alone leaves a stronger target-native agent-path claim UNRESOLVED."
            if g3
            else None
        ),
        "forbidden_claims": [
            "TensorRT-LLM trace replay is globally invalid",
            "AgentX is globally invalid",
            "the replay target definitely chooses a different tool/path",
            "source audit establishes target-native INVALID",
            "source audit establishes an external downstream performance flip",
        ],
    }

    out_json = args.output_dir / "EXTERNAL_RETENTION_TRANSFER_RESULTS.json"
    out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    md: list[str] = []
    md.append("# ReplayMark External Retention-Transfer Audit")
    md.append("")
    md.append(f"**Decision:** `{result['decision']}`")
    md.append("")
    md.append("## Gates")
    md.append("")
    for key, value in result["gates"].items():
        md.append(f"- `{key}`: **{'PASS' if value else 'NOT SATISFIED'}**")
    md.append("")
    md.append("## Candidate A — NVIDIA TensorRT-LLM")
    md.append("")
    md.append(
        f"Pinned shipped trace: {len(events)} events; "
        f"{len(assistant_decisions)} assistant events carry historical tool decisions; "
        f"{len(tool_events)} historical tool-call events."
    )
    md.append("")
    md.append(f"First matched witness: `{json.dumps(first_witness, sort_keys=True)}`")
    md.append("")
    md.append(f"- Fixed historical serving-workload claim: `{verdicts['nvidia_tensorrt_llm']['C_fixed']}`")
    md.append(f"- Target-native agent-path claim: `{verdicts['nvidia_tensorrt_llm']['C_native']}`")
    md.append("")
    md.append("## Candidate B — AIPerf AgentX")
    md.append("")
    md.append(f"- Fixed historical serving-workload claim: `{verdicts['aiperf_agentx']['C_fixed']}`")
    md.append(f"- Target-native agent-path claim: `{verdicts['aiperf_agentx']['C_native']}`")
    md.append("")
    md.append("## Mechanical checks")
    md.append("")
    for c in checks:
        suffix = f" (line {c.line})" if c.line else ""
        md.append(f"- {'PASS' if c.passed else 'FAIL'} `{c.name}`{suffix}: {c.detail}")
    md.append("")
    md.append("## Licensed interpretation")
    md.append("")
    if g3:
        md.append(result["licensed_claim"])
    else:
        md.append("No external-transfer claim is promoted because at least one frozen source predicate failed.")
    md.append("")
    md.append("This audit does **not** claim that either external benchmark is globally invalid. ")
    md.append("`INVALID` requires a separately frozen target-native comparator or structural exclusion proof.")
    md.append("")
    (args.output_dir / "EXTERNAL_RETENTION_TRANSFER_REPORT.md").write_text("\n".join(md) + "\n")

    print(f"EXTERNAL RETENTION TRANSFER: {result['decision']}")
    print(json.dumps(result["gates"], sort_keys=True))
    return 0 if g3 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"AUDIT ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
