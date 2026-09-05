from __future__ import annotations

"""Outcome-independent Home Assistant action identity for AgentMark.

This adapter is intentionally substrate-generic.  It does not know about
climate presets, notifications, lights, or any other service-specific field.
Home Assistant renders templates first; this module canonicalizes the rendered
service call into the AgentMark `action` projection.
"""

from dataclasses import dataclass
import json
import math
from typing import Any, Mapping


# Home Assistant targeting selectors are represented by target identity/class,
# not duplicated inside the semantic service-data variant.  Only top-level
# service-call selectors are removed: nested payload fields with the same names
# are preserved because they may be consequential application data.
TARGETING_KEYS = frozenset(
    {
        "entity_id",
        "device_id",
        "area_id",
        "floor_id",
        "label_id",
    }
)


@dataclass(frozen=True)
class HAActionIdentity:
    operation: str
    target_class: str | None
    variant: str

    def projected_key(self) -> tuple[str, str | None, str]:
        return (self.operation, self.target_class, self.variant)


def _json_safe(value: Any) -> Any:
    """Convert only unambiguous JSON-like rendered service data.

    Fail closed on opaque Python objects instead of inventing a semantic
    serialization.  Lists preserve order because service APIs may attach
    meaning to order.  Mapping keys must already be strings.
    """

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not a canonical action value")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical action mappings require string keys")
            out[key] = _json_safe(item)
        return out
    raise TypeError(
        f"unsupported rendered service-data type for action identity: {type(value).__name__}"
    )


def _as_target_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        if not all(isinstance(item, str) for item in value):
            raise TypeError("target selector list must contain strings")
        return list(value)
    raise TypeError(f"unsupported target selector type: {type(value).__name__}")


def target_class_from_service_data(service_data: Mapping[str, Any]) -> str | None:
    """Return a stable target-domain class without guessing device semantics."""

    entity_ids = _as_target_values(service_data.get("entity_id"))
    domains = sorted(
        {
            entity_id.split(".", 1)[0]
            for entity_id in entity_ids
            if "." in entity_id and entity_id.split(".", 1)[0]
        }
    )
    if not domains:
        return None
    if len(domains) == 1:
        return domains[0]
    return "mixed:" + ",".join(domains)


def canonical_variant(service_data: Mapping[str, Any]) -> str:
    """Canonical JSON of rendered non-target service data."""

    semantic_data = {
        key: value
        for key, value in service_data.items()
        if key not in TARGETING_KEYS
    }
    normalized = _json_safe(semantic_data)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_action_identity(
    domain: str,
    service: str,
    service_data: Mapping[str, Any],
) -> HAActionIdentity:
    domain = str(domain).strip()
    service = str(service).strip()
    if not domain or not service:
        raise ValueError("Home Assistant action requires non-empty domain and service")
    return HAActionIdentity(
        operation=f"{domain}.{service}",
        target_class=target_class_from_service_data(service_data),
        variant=canonical_variant(service_data),
    )
