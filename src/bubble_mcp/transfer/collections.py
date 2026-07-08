"""Bubble collection schema bundle extraction for transfer planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext


@dataclass(frozen=True)
class CollectionField:
    key: str
    field_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "field_type": self.field_type, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class PrivacyRule:
    key: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class CollectionBundle:
    data_type: str
    label: str
    fields: list[CollectionField]
    privacy_rules: list[PrivacyRule]
    option_sets: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_type": self.data_type,
            "label": self.label,
            "fields": [field.to_dict() for field in self.fields],
            "privacy_rules": [rule.to_dict() for rule in self.privacy_rules],
            "option_sets": list(self.option_sets),
            "metadata": dict(self.metadata),
        }


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _matches(node: BubbleContextNode, ref: str) -> bool:
    normalized = str(ref or "").strip().lower()
    return normalized in {
        node.id.lower(),
        node.label.lower(),
        str(node.metadata.get("bubble_id") or "").strip().lower(),
    }


def _field_type(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return str(raw.get("type") or raw.get("field_type") or raw.get("%x") or "").strip() or None
    return None


def _extract_fields(properties: dict[str, Any]) -> list[CollectionField]:
    raw_fields = _obj(properties.get("fields") or properties.get("%fields") or properties.get("field_types"))
    fields: list[CollectionField] = []
    for key, raw in raw_fields.items():
        fields.append(CollectionField(key=str(key), field_type=_field_type(raw), metadata=_obj(raw)))
    return fields


def _extract_privacy_rules(properties: dict[str, Any]) -> list[PrivacyRule]:
    raw_rules = _obj(properties.get("privacy_role") or properties.get("privacy_roles"))
    rules: list[PrivacyRule] = []
    for key, raw in raw_rules.items():
        metadata = _obj(raw)
        rules.append(PrivacyRule(key=str(key), label=str(metadata.get("%d") or key), metadata=metadata))
    return rules


def _option_sets(context: BubbleProjectContext) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    for node in context.nodes:
        if node.type != "option_set":
            continue
        bundles.append(
            {
                "key": str(node.metadata.get("bubble_id") or node.id.removeprefix("optionset:")),
                "label": node.label,
                "metadata": dict(node.metadata),
            }
        )
    return bundles


def _option_values(option_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = _obj(option_set.get("metadata"))
    raw_values = _obj(_obj(metadata.get("properties")).get("values") or metadata.get("values"))
    values: dict[str, dict[str, Any]] = {}
    for key, raw in raw_values.items():
        value = _obj(raw)
        values[str(key)] = {
            "key": str(key),
            "label": str(value.get("%d") or value.get("label") or value.get("name") or key),
            "db_value": str(value.get("db_value") or value.get("value") or key),
            "metadata": value,
        }
    return values


def extract_collection_bundle(source_context: BubbleProjectContext, data_type: str) -> CollectionBundle:
    """Extract a Bubble data type schema bundle without live records."""

    matches = [node for node in source_context.nodes if node.type == "data_type" and _matches(node, data_type)]
    if not matches:
        raise ValueError(f"Data type not found in source context: {data_type}")
    node = matches[0]
    properties = _obj(node.metadata.get("properties"))
    return CollectionBundle(
        data_type=str(node.metadata.get("bubble_id") or node.id.removeprefix("datatype:")),
        label=node.label,
        fields=_extract_fields(properties),
        privacy_rules=_extract_privacy_rules(properties),
        option_sets=_option_sets(source_context),
        metadata={"source_node_id": node.id},
    )


def _target_data_type_node(target_context: BubbleProjectContext, data_type: str) -> BubbleContextNode | None:
    for node in target_context.nodes:
        if node.type == "data_type" and _matches(node, data_type):
            return node
    return None


def _target_option_set_node(target_context: BubbleProjectContext, option_set_key: str) -> BubbleContextNode | None:
    for node in target_context.nodes:
        if node.type == "option_set" and _matches(node, option_set_key):
            return node
    return None


def _target_option_values(node: BubbleContextNode | None) -> dict[str, dict[str, Any]]:
    if node is None:
        return {}
    return _option_values({"metadata": dict(node.metadata)})


def _target_privacy_rules(target_node: BubbleContextNode | None) -> dict[str, Any]:
    if target_node is None:
        return {}
    properties = _obj(target_node.metadata.get("properties"))
    return _obj(properties.get("privacy_role") or properties.get("privacy_roles"))


def plan_collection_bundle(
    bundle: CollectionBundle,
    target_context: BubbleProjectContext,
    *,
    policy: str,
    data_records_policy: str = "skip",
) -> dict[str, Any]:
    """Plan collection schema actions for a target app."""

    if policy not in {"skip", "map_existing", "create_missing", "replace_schema"}:
        raise ValueError("collection policy must be one of: skip, map_existing, create_missing, replace_schema.")
    if data_records_policy != "skip":
        return {
            "ok": False,
            "policy": policy,
            "data_records_policy": data_records_policy,
            "actions": [],
            "blocked_reasons": ["Live data record migration requires a dedicated explicit preview flow."],
        }
    if policy == "skip":
        return {"ok": True, "policy": policy, "data_records_policy": data_records_policy, "actions": [], "blocked_reasons": []}
    if policy == "replace_schema":
        return {
            "ok": False,
            "policy": policy,
            "data_records_policy": data_records_policy,
            "actions": [],
            "blocked_reasons": ["replace_schema is destructive and requires a dedicated confirmation path."],
        }

    target_node = _target_data_type_node(target_context, bundle.data_type)
    actions: list[dict[str, Any]] = []
    blocked: list[str] = []
    if target_node is None:
        if policy == "map_existing":
            blocked.append(f"Target data type not found: {bundle.data_type}")
        else:
            actions.append({"action": "create_data_type", "data_type": bundle.data_type, "label": bundle.label})

    target_fields = _obj(_obj(target_node.metadata.get("properties") if target_node else {}).get("fields"))
    for field_item in bundle.fields:
        if field_item.key in target_fields:
            continue
        if policy == "map_existing":
            blocked.append(f"Target field not found: {bundle.data_type}.{field_item.key}")
        else:
            actions.append(
                {
                    "action": "create_data_field",
                    "data_type": bundle.data_type,
                    "field_key": field_item.key,
                    "field_type": field_item.field_type,
                }
            )

    for option_set in bundle.option_sets:
        option_key = str(option_set.get("key") or "").strip()
        if not option_key:
            continue
        target_option_set = _target_option_set_node(target_context, option_key)
        if target_option_set is None:
            if policy == "map_existing":
                blocked.append(f"Target option set not found: {option_key}")
                continue
            actions.append(
                {
                    "action": "create_option_set",
                    "option_set": option_key,
                    "label": str(option_set.get("label") or option_key),
                }
            )
        target_values = _target_option_values(target_option_set)
        for value_key, value in _option_values(option_set).items():
            if value_key in target_values:
                continue
            if policy == "map_existing":
                blocked.append(f"Target option value not found: {option_key}.{value_key}")
            else:
                actions.append(
                    {
                        "action": "create_option_value",
                        "option_set": option_key,
                        "value_key": value_key,
                        "label": value["label"],
                        "db_value": value["db_value"],
                    }
                )

    target_privacy_rules = _target_privacy_rules(target_node)
    for rule in bundle.privacy_rules:
        if rule.key in target_privacy_rules:
            continue
        if policy == "map_existing":
            blocked.append(f"Target privacy rule not found: {bundle.data_type}.{rule.key}")
        else:
            actions.append(
                {
                    "action": "ensure_privacy_rule",
                    "data_type": bundle.data_type,
                    "rule_key": rule.key,
                    "label": rule.label,
                    "payload": dict(rule.metadata),
                }
            )
    return {
        "ok": not blocked,
        "policy": policy,
        "data_records_policy": data_records_policy,
        "actions": actions,
        "blocked_reasons": blocked,
    }
