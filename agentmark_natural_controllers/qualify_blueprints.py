from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from homeassistant.components.automation import config as automation_config
from homeassistant.components.blueprint import models as blueprint_models
from homeassistant.util import yaml as yaml_util


DECISION_KEYS = {
    "choose",
    "wait_for_trigger",
    "wait_template",
    "repeat",
    "parallel",
    "if",
}
TIMING_KEYS = {"delay", "timeout"}


def is_input(value: Any) -> bool:
    return value.__class__.__name__ == "Input"


def has_template(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return "{{" in value or "{%" in value


def dynamic_kind(value: Any) -> str | None:
    if is_input(value):
        return "blueprint_input"
    if has_template(value):
        return "template"
    return None


def json_static(value: Any) -> tuple[bool, Any]:
    """Return a JSON-safe static value or fail closed.

    Blueprint inputs and templates are not evaluated here. This qualifier is
    intentionally structural and outcome-blind; native execution is required
    when semantics depend on dynamic values.
    """

    if is_input(value) or has_template(value):
        return False, None
    if value is None or isinstance(value, (bool, int, float, str)):
        return True, value
    if isinstance(value, list):
        out = []
        for item in value:
            ok, normalized = json_static(item)
            if not ok:
                return False, None
            out.append(normalized)
        return True, out
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return False, None
            ok, normalized = json_static(item)
            if not ok:
                return False, None
            out[key] = normalized
        return True, out
    return False, None


def selector_action_inputs(blueprint: blueprint_models.Blueprint) -> list[str]:
    found: list[str] = []
    for name, spec in blueprint.inputs.items():
        if not isinstance(spec, dict):
            continue
        selector = spec.get("selector")
        if isinstance(selector, dict) and "action" in selector:
            found.append(str(name))
    return sorted(found)


def count_dynamic_nodes(data: Any) -> Counter[str]:
    """Count dynamic syntax anywhere without interpreting arbitrary payloads."""

    counts: Counter[str] = Counter()

    def walk(node: Any) -> None:
        kind = dynamic_kind(node)
        if kind is not None:
            counts[kind] += 1
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(data)
    return counts


def scan_structure(data: Any) -> dict[str, Any]:
    """Traverse only Home Assistant action-sequence positions.

    The earlier discovery scanner recursively treated every dictionary key named
    ``action`` as an executable HA action. That is wrong for nested payloads such
    as mobile-notification ``data.actions[].action: URI`` and event-data fields.

    Native schema validation establishes that ``data`` is a valid automation
    blueprint. From there this scanner enters only the root automation action
    sequence and recursively follows known script control-flow edges. It never
    searches arbitrary service data, target payloads, trigger event_data, or
    condition dictionaries for action sites.
    """

    constructs: Counter[str] = Counter()
    action_sites: list[dict[str, Any]] = []
    dynamic_action_bodies: list[dict[str, Any]] = []

    def add_action_site(step: dict[str, Any], path: tuple[str, ...]) -> None:
        operation_key: str | None = None
        operation_value: Any = None
        for candidate in ("action", "service"):
            if candidate in step and not isinstance(step[candidate], (dict, list)):
                operation_key = candidate
                operation_value = step[candidate]
                break
        if operation_key is None:
            return

        op_kind = dynamic_kind(operation_value)
        operation_static = isinstance(operation_value, str) and op_kind is None
        operation = str(operation_value) if operation_static else None
        domain = (
            operation.split(".", 1)[0]
            if operation is not None and "." in operation
            else None
        )

        target_value = step.get("target")
        target_static, target_normalized = json_static(target_value)
        if target_value is None:
            target_static = True
            target_normalized = None

        data_key = (
            "data"
            if "data" in step
            else "data_template"
            if "data_template" in step
            else None
        )
        data_value = step.get(data_key) if data_key else None
        data_static, data_normalized = json_static(data_value)
        if data_key is None:
            data_static = True
            data_normalized = None

        static_fingerprint = None
        if operation_static and target_static and data_static:
            material = {
                "operation": operation,
                "target": target_normalized,
                "data": data_normalized,
            }
            static_fingerprint = hashlib.sha256(
                json.dumps(
                    material,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

        action_sites.append(
            {
                "path": "/".join(path),
                "syntax_key": operation_key,
                "operation_static": operation_static,
                "operation": operation,
                "operation_domain": domain,
                "operation_dynamic_kind": op_kind,
                "target_static": target_static,
                "data_static": data_static,
                "static_action_fingerprint": static_fingerprint,
            }
        )

    def scan_sequence(sequence: Any, path: tuple[str, ...]) -> None:
        if is_input(sequence):
            dynamic_action_bodies.append(
                {
                    "path": "/".join(path),
                    "dynamic_kind": "blueprint_input_action_sequence",
                }
            )
            return
        if not isinstance(sequence, list):
            return

        for index, step in enumerate(sequence):
            step_path = path + (str(index),)
            if is_input(step):
                dynamic_action_bodies.append(
                    {
                        "path": "/".join(step_path),
                        "dynamic_kind": "blueprint_input_action_step",
                    }
                )
                continue
            if not isinstance(step, dict):
                continue

            for key in DECISION_KEYS:
                if key in step:
                    constructs[key] += 1
            for key in TIMING_KEYS:
                if key in step:
                    constructs[key] += 1

            add_action_site(step, step_path)

            # Follow only script control-flow fields that contain action
            # sequences. Conditions, trigger definitions, service payloads and
            # target dictionaries are deliberately opaque to this traversal.
            choose = step.get("choose")
            if isinstance(choose, list):
                for choice_index, choice in enumerate(choose):
                    if isinstance(choice, dict):
                        scan_sequence(
                            choice.get("sequence"),
                            step_path + ("choose", str(choice_index), "sequence"),
                        )
                scan_sequence(step.get("default"), step_path + ("default",))

            if "if" in step:
                scan_sequence(step.get("then"), step_path + ("then",))
                scan_sequence(step.get("else"), step_path + ("else",))

            repeat = step.get("repeat")
            if isinstance(repeat, dict):
                scan_sequence(
                    repeat.get("sequence"),
                    step_path + ("repeat", "sequence"),
                )

            parallel = step.get("parallel")
            if isinstance(parallel, list):
                for branch_index, branch in enumerate(parallel):
                    branch_path = step_path + ("parallel", str(branch_index))
                    if isinstance(branch, dict) and "sequence" in branch:
                        scan_sequence(branch.get("sequence"), branch_path + ("sequence",))
                    elif isinstance(branch, list):
                        scan_sequence(branch, branch_path)
                    elif is_input(branch):
                        dynamic_action_bodies.append(
                            {
                                "path": "/".join(branch_path),
                                "dynamic_kind": "blueprint_input_parallel_branch",
                            }
                        )

    if isinstance(data, dict):
        root_actions = data.get("actions")
        root_key = "actions"
        if root_actions is None and isinstance(data.get("action"), list):
            root_actions = data.get("action")
            root_key = "action"
        scan_sequence(root_actions, (root_key,))

    dynamic_nodes = count_dynamic_nodes(data)
    return {
        "scanner": "context_sensitive_ha_action_sequence_v2",
        "construct_counts": dict(sorted(constructs.items())),
        "dynamic_node_counts": dict(sorted(dynamic_nodes.items())),
        "dynamic_action_bodies": dynamic_action_bodies,
        "action_sites": action_sites,
    }


def qualify_one(candidate: dict[str, Any], input_dir: Path) -> dict[str, Any]:
    candidate_id = str(candidate["id"])
    source = input_dir / f"{candidate_id}.yaml"
    payload = source.read_bytes()
    base: dict[str, Any] = {
        "id": candidate_id,
        "repository": candidate["repository"],
        "commit": candidate["commit"],
        "path": candidate["path"],
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "source_bytes": len(payload),
    }

    try:
        data = yaml_util.load_yaml_dict(source)
        blueprint = blueprint_models.Blueprint(
            data,
            expected_domain="automation",
            path=str(candidate["path"]),
            schema=automation_config.AUTOMATION_BLUEPRINT_SCHEMA,
        )
    except Exception as err:  # Preserve exact native rejection class/message.
        return {
            **base,
            "native_schema_valid": False,
            "qualification": "EXCLUDED_NATIVE_SCHEMA",
            "error_type": type(err).__name__,
            "error": str(err),
        }

    structure = scan_structure(blueprint.data)
    action_sites = structure["action_sites"]
    dynamic_action_bodies = structure["dynamic_action_bodies"]
    static_ops = sum(bool(site["operation_static"]) for site in action_sites)
    dynamic_ops = len(action_sites) - static_ops
    decision_constructs = sum(
        count
        for key, count in structure["construct_counts"].items()
        if key in DECISION_KEYS
    )
    action_input_names = selector_action_inputs(blueprint)

    if not action_sites and not dynamic_action_bodies:
        qualification = "EXCLUDED_NO_ACTION_SITES"
    elif decision_constructs == 0:
        qualification = "EXCLUDED_NO_REACTIVE_DECISION_STRUCTURE"
    else:
        qualification = "QUALIFIED_STAGE_A"

    needs_native_instantiation = bool(
        dynamic_ops
        or dynamic_action_bodies
        or action_input_names
        or structure["dynamic_node_counts"].get("template", 0)
    )

    return {
        **base,
        "native_schema_valid": True,
        "blueprint_name": blueprint.name,
        "blueprint_domain": blueprint.domain,
        "input_count": len(blueprint.inputs),
        "action_selector_inputs": action_input_names,
        "qualification": qualification,
        "decision_construct_count": decision_constructs,
        "action_site_count": len(action_sites),
        "dynamic_action_body_count": len(dynamic_action_bodies),
        "static_operation_site_count": static_ops,
        "dynamic_operation_site_count": dynamic_ops,
        "needs_native_instantiation": needs_native_instantiation,
        **structure,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--fetch-provenance", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fetch_provenance = json.loads(Path(args.fetch_provenance).read_text(encoding="utf-8"))
    input_dir = Path(args.input_dir)

    fetched_by_id = {str(row["id"]): row for row in fetch_provenance["sources"]}
    results: list[dict[str, Any]] = []
    for candidate in manifest["candidates"]:
        result = qualify_one(candidate, input_dir)
        fetched = fetched_by_id[result["id"]]
        if result["source_sha256"] != fetched["sha256"]:
            raise RuntimeError(f"source hash mismatch for {result['id']}")
        results.append(result)

    counts = Counter(str(row["qualification"]) for row in results)
    report = {
        "schema": "agentmark.natural_controller_corpus.qualification.v2",
        "home_assistant_parser": "native automation Blueprint + AUTOMATION_BLUEPRINT_SCHEMA",
        "scanner": "context_sensitive_ha_action_sequence_v2",
        "outcome_blind": True,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "qualification_counts": dict(sorted(counts.items())),
        "results": results,
    }
    Path(args.out).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
