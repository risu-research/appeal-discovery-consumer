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
EXPECTED_OWNERSHIP_MODE = "upstream-domain-pinned-disabled-config-entry-controlled-device"
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


def canonical_variant_independent(service_data: Mapping[str, Any]) -> str:
    """Independent implementation of the frozen generic action-variant rule."""
    semantic = {k: v for k, v in service_data.items() if k not in TARGET_KEYS}
    return json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def target_class_independent(service_data: Mapping[str, Any]) -> str | None:
    raw = service_data.get("entity_id")
    if raw is None:
        return None
    values = [raw] if isinstance(raw, str) else list(raw)
    domains = sorted({str(v).split(".", 1)[0] for v in values if "." in str(v)})
    if len(domains) == 1:
        return domains[0]
    if not domains:
        return None
    return "mixed:" + ",".join(domains)


def deterministic_tree_sha256_independent(root: Path) -> str:
    """Recompute the upstream source-tree digest from raw files, not producer output."""
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise AssertionError(f"ownership component tree is empty: {root}")
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def verify_upstream_component(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    manifest_payload = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_payload).hexdigest()
    if manifest_sha != EXPECTED_BT_MANIFEST_SHA:
        raise AssertionError(
            f"Better Thermostat manifest hash mismatch: {manifest_sha} != {EXPECTED_BT_MANIFEST_SHA}"
        )
    manifest = json.loads(manifest_payload)
    if manifest.get("domain") != EXPECTED_BT_DOMAIN:
        raise AssertionError(f"Better Thermostat manifest domain mismatch: {manifest.get('domain')}")
    if manifest.get("version") != EXPECTED_BT_VERSION:
        raise AssertionError(f"Better Thermostat manifest version mismatch: {manifest.get('version')}")
    return {
        "manifest_sha256": manifest_sha,
        "domain": manifest["domain"],
        "version": manifest["version"],
        "tree_sha256": deterministic_tree_sha256_independent(root),
    }


def assert_check(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise AssertionError(label)


def raw_identity(row: dict[str, Any]) -> dict[str, Any]:
    events = row["raw_call_events"]
    counts = Counter(f"{e['domain']}.{e['service']}" for e in events)
    climate = [
        e
        for e in events
        if e.get("domain") == "climate" and e.get("service") == "set_preset_mode"
    ]
    if len(climate) != 1:
        raise AssertionError(
            f"{row['label']}: expected one raw climate call, got {dict(counts)}"
        )
    event = climate[0]
    data = dict(event.get("service_data") or {})
    raw_target = data.get("entity_id")
    target_values = [raw_target] if isinstance(raw_target, str) else list(raw_target or [])
    return {
        "counts": dict(sorted(counts.items())),
        "operation": "climate.set_preset_mode",
        "target_class": target_class_independent(data),
        "variant": canonical_variant_independent(data),
        "service_data": data,
        "target_entities": sorted(str(v) for v in target_values),
        "contexts_nonempty": all(bool(str(e.get("context_id", ""))) for e in events),
        "presence_at_issue": event.get("presence_state_at_issue"),
        "pre_issue_preset": event.get("climate_preset_before_issue"),
        "registry": dict(row["registry"]),
    }


def is_only_climate(identity: dict[str, Any]) -> bool:
    return identity["counts"] == {"climate.set_preset_mode": 1}


def ownership_checks(
    identity: dict[str, Any],
    upstream: dict[str, Any],
    prefix: str,
    checks: dict[str, bool],
) -> None:
    reg = identity["registry"]
    assert_check(reg.get("ownership_mode") == EXPECTED_OWNERSHIP_MODE, f"{prefix}_ownership_mode", checks)
    assert_check(reg.get("upstream_component_repository") == "KartoffelToby/better_thermostat", f"{prefix}_upstream_repo", checks)
    assert_check(reg.get("upstream_component_commit") == EXPECTED_BT_COMMIT, f"{prefix}_upstream_commit", checks)
    assert_check(reg.get("upstream_component_version") == EXPECTED_BT_VERSION, f"{prefix}_upstream_version", checks)
    assert_check(reg.get("upstream_manifest_sha256") == upstream["manifest_sha256"], f"{prefix}_manifest_hash", checks)
    assert_check(reg.get("upstream_component_tree_sha256") == upstream["tree_sha256"], f"{prefix}_tree_hash", checks)
    assert_check(reg.get("ha_loader_resolved_domain") == EXPECTED_BT_DOMAIN, f"{prefix}_loader_domain", checks)
    assert_check(reg.get("ha_loader_resolved_version") == EXPECTED_BT_VERSION, f"{prefix}_loader_version", checks)
    assert_check(reg.get("config_entry_domain") == EXPECTED_BT_DOMAIN, f"{prefix}_entry_domain", checks)
    assert_check(reg.get("config_entry_disabled_by") == "user", f"{prefix}_entry_disabled", checks)
    assert_check(reg.get("config_entry_state") != "loaded", f"{prefix}_entry_not_loaded", checks)
    assert_check(reg.get("config_entry_registered") is True, f"{prefix}_entry_registered", checks)
    assert_check(reg.get("device_config_entry_id") == reg.get("config_entry_id"), f"{prefix}_device_entry_link", checks)
    assert_check(reg.get("device_identifiers") == [[EXPECTED_BT_DOMAIN, "agentmark-device"]], f"{prefix}_device_identifier", checks)
    assert_check(reg.get("entity_id") == "climate.agentmark_thermostat", f"{prefix}_entity_id", checks)
    assert_check(reg.get("entity_platform") == EXPECTED_BT_DOMAIN, f"{prefix}_entity_platform", checks)
    assert_check(reg.get("entity_config_entry_id") == reg.get("config_entry_id"), f"{prefix}_entity_entry_link", checks)
    assert_check(reg.get("entity_device_id") == reg.get("device_id"), f"{prefix}_entity_device_link", checks)
    assert_check(reg.get("native_device_entity_link") is True, f"{prefix}_native_device_entity", checks)
    assert_check(reg.get("native_entry_device_link") is True, f"{prefix}_native_entry_device", checks)
    assert_check(reg.get("native_entry_entity_link") is True, f"{prefix}_native_entry_entity", checks)
    assert_check(identity["target_entities"] == ["climate.agentmark_thermostat"], f"{prefix}_raw_target_exact", checks)


def validate(path: Path, ownership_component: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    upstream = verify_upstream_component(ownership_component)

    assert_check(
        payload["schema"]
        == "agentmark.natural_controller.better_thermostat_action_identity.v2",
        "schema_v2",
        checks,
    )
    assert_check(
        payload["environment"]["home_assistant_core_version"] == "2026.9.0",
        "ha_version",
        checks,
    )
    assert_check(
        payload["external_controller"]["sha256"] == EXPECTED_CONTROLLER_SHA,
        "external_sha",
        checks,
    )
    assert_check(
        payload["external_controller"]["source_edited"] is False,
        "source_unedited",
        checks,
    )
    assert_check(payload["frozen_protocol"] == EXPECTED_PROTOCOL, "protocol_exact", checks)

    owner = payload["controlled_device_ownership"]
    assert_check(owner["mode"] == EXPECTED_OWNERSHIP_MODE, "owner_mode", checks)
    assert_check(owner["upstream_repository"] == "KartoffelToby/better_thermostat", "owner_repo", checks)
    assert_check(owner["upstream_commit"] == EXPECTED_BT_COMMIT, "owner_commit", checks)
    assert_check(owner["upstream_version"] == EXPECTED_BT_VERSION, "owner_version", checks)
    assert_check(owner["upstream_manifest_sha256"] == upstream["manifest_sha256"], "owner_manifest_hash", checks)
    assert_check(owner["component_tree_sha256"] == upstream["tree_sha256"], "owner_tree_hash", checks)
    assert_check(owner["config_entry_intentionally_disabled"] is True, "owner_disabled_boundary", checks)
    assert_check(owner["integration_internal_control_logic_executed"] is False, "owner_no_internal_control", checks)

    adapter = payload["frozen_adapter"]
    assert_check(adapter["home_variant"] == HOME_VARIANT, "adapter_home", checks)
    assert_check(adapter["away_variant"] == AWAY_VARIANT, "adapter_away", checks)

    source = raw_identity(payload["source"])
    assert_check(is_only_climate(source), "source_counts", checks)
    assert_check(source["operation"] == "climate.set_preset_mode", "source_operation", checks)
    assert_check(source["target_class"] == "climate", "source_target_class", checks)
    assert_check(source["variant"] == HOME_VARIANT, "source_home_variant", checks)
    assert_check(source["pre_issue_preset"] == "sleep", "source_pre_preset", checks)
    assert_check(source["contexts_nonempty"], "source_context", checks)
    ownership_checks(source, upstream, "source", checks)

    targets = payload["target_native"]
    replays = payload["target_replay"]
    controls = payload["no_feedback_shift_control"]
    assert_check(len(targets) == 6, "target_trial_count", checks)
    assert_check(len(replays) == 6, "replay_trial_count", checks)
    assert_check(len(controls) == 6, "control_trial_count", checks)

    target_ids = [raw_identity(row) for row in targets]
    replay_ids = [raw_identity(row) for row in replays]
    control_native_ids = [raw_identity(pair["native"]) for pair in controls]
    control_replay_ids = [raw_identity(pair["replay"]) for pair in controls]

    for i, ident in enumerate(target_ids):
        assert_check(is_only_climate(ident), f"target_t{i}_counts", checks)
        assert_check(ident["operation"] == source["operation"], f"target_t{i}_same_operation", checks)
        assert_check(ident["target_class"] == "climate", f"target_t{i}_target_class", checks)
        assert_check(ident["variant"] == AWAY_VARIANT, f"target_t{i}_away_variant", checks)
        assert_check(ident["pre_issue_preset"] == "sleep", f"target_t{i}_pre_preset", checks)
        assert_check(ident["contexts_nonempty"], f"target_t{i}_context", checks)
        ownership_checks(ident, upstream, f"target_t{i}", checks)

    for i, ident in enumerate(replay_ids):
        assert_check(is_only_climate(ident), f"replay_t{i}_counts", checks)
        assert_check(ident["operation"] == source["operation"], f"replay_t{i}_same_operation", checks)
        assert_check(ident["target_class"] == "climate", f"replay_t{i}_target_class", checks)
        assert_check(ident["variant"] == HOME_VARIANT, f"replay_t{i}_recorded_home", checks)
        assert_check(ident["contexts_nonempty"], f"replay_t{i}_context", checks)
        ownership_checks(ident, upstream, f"replay_t{i}", checks)
        assert_check(
            ident["operation"] == target_ids[i]["operation"],
            f"replay_t{i}_operation_supported",
            checks,
        )
        assert_check(
            (ident["operation"], ident["target_class"], ident["variant"])
            != (
                target_ids[i]["operation"],
                target_ids[i]["target_class"],
                target_ids[i]["variant"],
            ),
            f"replay_t{i}_action_unsupported",
            checks,
        )

    for i, (native, replay) in enumerate(
        zip(control_native_ids, control_replay_ids, strict=True)
    ):
        assert_check(
            is_only_climate(native) and is_only_climate(replay),
            f"control_t{i}_counts",
            checks,
        )
        assert_check(native["variant"] == HOME_VARIANT, f"control_t{i}_native_home", checks)
        assert_check(replay["variant"] == HOME_VARIANT, f"control_t{i}_replay_home", checks)
        assert_check(native["operation"] == replay["operation"], f"control_t{i}_operation_support", checks)
        assert_check(
            native["target_class"] == replay["target_class"] == "climate",
            f"control_t{i}_target_support",
            checks,
        )
        assert_check(native["variant"] == replay["variant"], f"control_t{i}_action_support", checks)
        ownership_checks(native, upstream, f"control_native_t{i}", checks)
        ownership_checks(replay, upstream, f"control_replay_t{i}", checks)

    # Deterministic point masses: identical operation keys imply TV=0; disjoint
    # full action keys imply TV=1. Recompute from raw native identities only.
    op_keys_source = {(source["operation"],): 1.0}
    op_keys_target = {(target_ids[0]["operation"],): 1.0}
    action_key_source = {
        (source["operation"], source["target_class"], source["variant"]): 1.0
    }
    action_key_target = {
        (
            target_ids[0]["operation"],
            target_ids[0]["target_class"],
            target_ids[0]["variant"],
        ): 1.0
    }
    tv_operation = 0.5 * sum(
        abs(op_keys_source.get(k, 0.0) - op_keys_target.get(k, 0.0))
        for k in set(op_keys_source) | set(op_keys_target)
    )
    tv_action = 0.5 * sum(
        abs(action_key_source.get(k, 0.0) - action_key_target.get(k, 0.0))
        for k in set(action_key_source) | set(action_key_target)
    )
    assert_check(tv_operation == 0.0, "tv_operation_exact_zero", checks)
    assert_check(tv_action == 1.0, "tv_action_exact_one", checks)

    assert_check(
        all(ident["operation"] == source["operation"] for ident in target_ids),
        "all_target_operations_equal_source",
        checks,
    )
    assert_check(
        all(ident["variant"] == AWAY_VARIANT for ident in target_ids),
        "all_target_actions_away",
        checks,
    )
    assert_check(
        all(ident["variant"] == HOME_VARIANT for ident in replay_ids),
        "all_replays_remain_recorded_home",
        checks,
    )

    # Producer report is cross-checked only after raw evidence independently passes.
    assert_check(float(payload["theory"]["TV_operation"]) == 0.0, "producer_tv_operation", checks)
    assert_check(float(payload["theory"]["TV_action"]) == 1.0, "producer_tv_action", checks)
    assert_check(payload["decision"] == "PROMOTED", "producer_promoted", checks)
    assert_check(
        all(bool(v) for v in payload["promotion_gates"].values()),
        "producer_gates_all_true",
        checks,
    )

    return {
        "schema": "agentmark.natural_controller.better_thermostat.validation.v2",
        "input": str(path),
        "replica": payload["replica"],
        "pass": all(checks.values()),
        "checks": checks,
        "upstream_recomputed": upstream,
        "recomputed": {
            "source_identity": {
                k: source[k] for k in ("operation", "target_class", "variant")
            },
            "target_identity": {
                k: target_ids[0][k] for k in ("operation", "target_class", "variant")
            },
            "TV_operation": tv_operation,
            "TV_action": tv_action,
            "target_trials": len(target_ids),
            "replay_trials": len(replay_ids),
            "control_trials": len(control_native_ids),
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
    Path(args.out).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "replica": report["replica"],
                "pass": report["pass"],
                "upstream_recomputed": report["upstream_recomputed"],
                "recomputed": report["recomputed"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
