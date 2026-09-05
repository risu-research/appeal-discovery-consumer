from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

EXPECTED_CONTROLLER_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
EXPECTED_BT_COMMIT = "b86561f61e5ba1259fc63e590f4847e9ac743d7f"
EXPECTED_BT_VERSION = "1.9.2"
EXPECTED_BT_DOMAIN = "better_thermostat"
EXPECTED_BT_MANIFEST_SHA = "710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28"
EXPECTED_OWNERSHIP_MODE = "upstream-qualified-persisted-disabled-config-entry-controlled-device"
EXPECTED_REGISTRATION_PATH = "core.config_entries Store -> ConfigEntries.async_initialize"
HOME_VARIANT = '{"preset_mode":"home"}'
AWAY_VARIANT = '{"preset_mode":"away"}'
TARGET_KEYS = frozenset({"entity_id", "device_id", "area_id", "floor_id", "label_id"})
EXPECTED_PROTOCOL = {
    "current_preset": "sleep",
    "source_feedback": "HOME",
    "target_feedback": "AWAY",
    "trials": 6,
    "writeback_enable": False,
    "writeback_bounds_enable": False,
    "boost_entity": "",
    "eco_entity": "",
    "activity_entity": "",
}


def canonical_variant(service_data: Mapping[str, Any]) -> str:
    semantic = {k: v for k, v in service_data.items() if k not in TARGET_KEYS}
    return json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def target_class(service_data: Mapping[str, Any]) -> str | None:
    raw = service_data.get("entity_id")
    values = [raw] if isinstance(raw, str) else list(raw or [])
    domains = sorted(
        {str(v).split(".", 1)[0] for v in values if "." in str(v)}
    )
    if not domains:
        return None
    if len(domains) == 1:
        return domains[0]
    return "mixed:" + ",".join(domains)


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise AssertionError("empty upstream component tree")
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        body = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return digest.hexdigest()


def verify_upstream(root: Path) -> dict[str, Any]:
    payload = (root / "manifest.json").read_bytes()
    manifest_sha = hashlib.sha256(payload).hexdigest()
    assert manifest_sha == EXPECTED_BT_MANIFEST_SHA
    manifest = json.loads(payload)
    assert manifest["domain"] == EXPECTED_BT_DOMAIN
    assert manifest["version"] == EXPECTED_BT_VERSION
    return {
        "manifest_sha256": manifest_sha,
        "domain": manifest["domain"],
        "version": manifest["version"],
        "tree_sha256": tree_sha256(root),
    }


def check(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise AssertionError(label)


def identity_from_raw(row: dict[str, Any]) -> dict[str, Any]:
    events = row["raw_call_events"]
    counts = Counter(f"{e['domain']}.{e['service']}" for e in events)
    climate = [
        e
        for e in events
        if e.get("domain") == "climate" and e.get("service") == "set_preset_mode"
    ]
    if len(climate) != 1:
        raise AssertionError(
            f"{row['label']}: expected exactly one climate.set_preset_mode; got {dict(counts)}"
        )
    event = climate[0]
    data = dict(event.get("service_data") or {})
    raw_target = data.get("entity_id")
    target_values = [raw_target] if isinstance(raw_target, str) else list(raw_target or [])
    return {
        "counts": dict(sorted(counts.items())),
        "operation": "climate.set_preset_mode",
        "target_class": target_class(data),
        "variant": canonical_variant(data),
        "target_entities": sorted(str(v) for v in target_values),
        "context_nonempty": bool(str(event.get("context_id", ""))),
        "presence_at_issue": event.get("presence_state_at_issue"),
        "pre_issue_preset": event.get("climate_preset_before_issue"),
        "registry": dict(row["registry"]),
    }


def validate_ownership(
    ident: dict[str, Any],
    upstream: dict[str, Any],
    prefix: str,
    checks: dict[str, bool],
) -> None:
    reg = ident["registry"]
    check(reg.get("ownership_mode") == EXPECTED_OWNERSHIP_MODE, f"{prefix}_ownership_mode", checks)
    check(reg.get("config_entry_registration_path") == EXPECTED_REGISTRATION_PATH, f"{prefix}_registration_path", checks)
    check(reg.get("upstream_component_repository") == "KartoffelToby/better_thermostat", f"{prefix}_upstream_repo", checks)
    check(reg.get("upstream_component_commit") == EXPECTED_BT_COMMIT, f"{prefix}_upstream_commit", checks)
    check(reg.get("upstream_component_version") == EXPECTED_BT_VERSION, f"{prefix}_upstream_version", checks)
    check(reg.get("upstream_manifest_sha256") == upstream["manifest_sha256"], f"{prefix}_manifest_sha", checks)
    check(reg.get("upstream_component_tree_sha256") == upstream["tree_sha256"], f"{prefix}_tree_sha", checks)
    check(reg.get("ha_loader_resolved_domain") == EXPECTED_BT_DOMAIN, f"{prefix}_loader_domain", checks)
    check(reg.get("ha_loader_resolved_version") == EXPECTED_BT_VERSION, f"{prefix}_loader_version", checks)
    check(reg.get("loader_qualification_before_outcome") is True, f"{prefix}_loader_before_outcome", checks)
    check(reg.get("loader_integration_setup_invoked") is False, f"{prefix}_loader_no_setup", checks)
    check(reg.get("config_entry_domain") == EXPECTED_BT_DOMAIN, f"{prefix}_entry_domain", checks)
    check(reg.get("config_entry_disabled_by") == "user", f"{prefix}_entry_disabled", checks)
    check(reg.get("config_entry_state") == "not_loaded", f"{prefix}_entry_not_loaded", checks)
    check(reg.get("config_entry_registered") is True, f"{prefix}_entry_registered", checks)
    check(reg.get("device_config_entry_id") == reg.get("config_entry_id"), f"{prefix}_device_entry", checks)
    check(reg.get("device_identifiers") == [[EXPECTED_BT_DOMAIN, "agentmark-device"]], f"{prefix}_device_identifier", checks)
    check(reg.get("entity_id") == "climate.agentmark_thermostat", f"{prefix}_entity_id", checks)
    check(reg.get("entity_platform") == EXPECTED_BT_DOMAIN, f"{prefix}_entity_platform", checks)
    check(reg.get("entity_config_entry_id") == reg.get("config_entry_id"), f"{prefix}_entity_entry", checks)
    check(reg.get("entity_device_id") == reg.get("device_id"), f"{prefix}_entity_device", checks)
    check(reg.get("native_device_entity_link") is True, f"{prefix}_native_device_entity", checks)
    check(reg.get("native_entry_device_link") is True, f"{prefix}_native_entry_device", checks)
    check(reg.get("native_entry_entity_link") is True, f"{prefix}_native_entry_entity", checks)
    check(ident["target_entities"] == ["climate.agentmark_thermostat"], f"{prefix}_raw_target_exact", checks)
    check(ident["pre_issue_preset"] == "sleep", f"{prefix}_pre_issue_sleep", checks)
    check(ident["context_nonempty"], f"{prefix}_context", checks)


def validate(path: Path, component: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    upstream = verify_upstream(component)
    checks: dict[str, bool] = {}

    check(payload["schema"] == "agentmark.natural_controller.better_thermostat_action_identity.v3", "schema_v3", checks)
    check(payload["environment"]["home_assistant_core_version"] == "2026.9.0", "ha_version", checks)
    check(payload["external_controller"]["sha256"] == EXPECTED_CONTROLLER_SHA, "controller_sha", checks)
    check(payload["external_controller"]["source_edited"] is False, "controller_unedited", checks)
    check(payload["frozen_protocol"] == EXPECTED_PROTOCOL, "protocol_exact", checks)

    owner = payload["controlled_device_ownership"]
    check(owner["mode"] == EXPECTED_OWNERSHIP_MODE, "owner_mode", checks)
    check(owner["config_entry_registration_path"] == EXPECTED_REGISTRATION_PATH, "owner_registration_path", checks)
    check(owner["upstream_commit"] == EXPECTED_BT_COMMIT, "owner_commit", checks)
    check(owner["upstream_version"] == EXPECTED_BT_VERSION, "owner_version", checks)
    check(owner["upstream_manifest_sha256"] == upstream["manifest_sha256"], "owner_manifest", checks)
    check(owner["component_tree_sha256"] == upstream["tree_sha256"], "owner_tree", checks)
    check(owner["loader_qualification"]["domain"] == EXPECTED_BT_DOMAIN, "owner_loader_domain", checks)
    check(owner["loader_qualification"]["version"] == EXPECTED_BT_VERSION, "owner_loader_version", checks)
    check(owner["loader_qualification"]["before_outcome"] is True, "owner_loader_before_outcome", checks)
    check(owner["loader_qualification"]["integration_setup_invoked"] is False, "owner_loader_no_setup", checks)
    check(owner["config_entry_intentionally_disabled"] is True, "owner_disabled", checks)
    check(owner["integration_internal_control_logic_executed"] is False, "owner_no_bt_internal_logic", checks)

    source = identity_from_raw(payload["source"])
    check(source["counts"] == {"climate.set_preset_mode": 1}, "source_counts", checks)
    check(source["target_class"] == "climate", "source_target_class", checks)
    check(source["variant"] == HOME_VARIANT, "source_home", checks)
    check(source["presence_at_issue"] == "on", "source_presence_home", checks)
    validate_ownership(source, upstream, "source", checks)

    targets = [identity_from_raw(row) for row in payload["target_native"]]
    replays = [identity_from_raw(row) for row in payload["target_replay"]]
    controls_native = [identity_from_raw(pair["native"]) for pair in payload["no_feedback_shift_control"]]
    controls_replay = [identity_from_raw(pair["replay"]) for pair in payload["no_feedback_shift_control"]]
    check(len(targets) == len(replays) == len(controls_native) == len(controls_replay) == 6, "trial_counts", checks)

    for i, ident in enumerate(targets):
        check(ident["counts"] == {"climate.set_preset_mode": 1}, f"target_{i}_counts", checks)
        check(ident["operation"] == source["operation"], f"target_{i}_same_operation", checks)
        check(ident["target_class"] == "climate", f"target_{i}_target_class", checks)
        check(ident["variant"] == AWAY_VARIANT, f"target_{i}_away", checks)
        check(ident["presence_at_issue"] == "off", f"target_{i}_presence_away", checks)
        validate_ownership(ident, upstream, f"target_{i}", checks)

    for i, ident in enumerate(replays):
        check(ident["counts"] == {"climate.set_preset_mode": 1}, f"replay_{i}_counts", checks)
        check(ident["operation"] == source["operation"], f"replay_{i}_same_operation", checks)
        check(ident["target_class"] == "climate", f"replay_{i}_target_class", checks)
        check(ident["variant"] == HOME_VARIANT, f"replay_{i}_recorded_home", checks)
        check(ident["presence_at_issue"] == "off", f"replay_{i}_target_presence_away", checks)
        validate_ownership(ident, upstream, f"replay_{i}", checks)
        check(ident["operation"] == targets[i]["operation"], f"replay_{i}_operation_supported", checks)
        check(ident["variant"] != targets[i]["variant"], f"replay_{i}_action_unsupported", checks)

    for i, (native, replay) in enumerate(zip(controls_native, controls_replay, strict=True)):
        for name, ident in (("native", native), ("replay", replay)):
            check(ident["counts"] == {"climate.set_preset_mode": 1}, f"control_{i}_{name}_counts", checks)
            check(ident["variant"] == HOME_VARIANT, f"control_{i}_{name}_home", checks)
            check(ident["presence_at_issue"] == "on", f"control_{i}_{name}_presence_home", checks)
            validate_ownership(ident, upstream, f"control_{i}_{name}", checks)
        check(native["operation"] == replay["operation"], f"control_{i}_operation_equal", checks)
        check(native["target_class"] == replay["target_class"], f"control_{i}_target_equal", checks)
        check(native["variant"] == replay["variant"], f"control_{i}_action_equal", checks)

    source_op = {(source["operation"],): 1.0}
    target_op = {(targets[0]["operation"],): 1.0}
    source_action = {(source["operation"], source["target_class"], source["variant"]): 1.0}
    target_action = {(targets[0]["operation"], targets[0]["target_class"], targets[0]["variant"]): 1.0}
    tv_op = 0.5 * sum(abs(source_op.get(k, 0.0) - target_op.get(k, 0.0)) for k in set(source_op) | set(target_op))
    tv_action = 0.5 * sum(abs(source_action.get(k, 0.0) - target_action.get(k, 0.0)) for k in set(source_action) | set(target_action))
    check(tv_op == 0.0, "tv_operation_exact_zero", checks)
    check(tv_action == 1.0, "tv_action_exact_one", checks)
    check(float(payload["theory"]["TV_operation"]) == 0.0, "producer_tv_op", checks)
    check(float(payload["theory"]["TV_action"]) == 1.0, "producer_tv_action", checks)
    check(payload["decision"] == "PROMOTED", "producer_promoted", checks)
    check(all(bool(v) for v in payload["promotion_gates"].values()), "producer_gates_all_true", checks)

    return {
        "schema": "agentmark.natural_controller.better_thermostat.validation.v3",
        "replica": payload["replica"],
        "pass": all(checks.values()),
        "checks": checks,
        "upstream_recomputed": upstream,
        "recomputed": {
            "source_identity": {k: source[k] for k in ("operation", "target_class", "variant")},
            "target_identity": {k: targets[0][k] for k in ("operation", "target_class", "variant")},
            "TV_operation": tv_op,
            "TV_action": tv_action,
            "target_trials": len(targets),
            "replay_trials": len(replays),
            "control_trials": len(controls_native),
            "ownership_mode": EXPECTED_OWNERSHIP_MODE,
            "ownership_component_tree_sha256": upstream["tree_sha256"],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--ownership-component", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = validate(Path(args.result), Path(args.ownership_component))
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"replica": report["replica"], "pass": report["pass"], "upstream_recomputed": report["upstream_recomputed"], "recomputed": report["recomputed"]}, indent=2, sort_keys=True))
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
