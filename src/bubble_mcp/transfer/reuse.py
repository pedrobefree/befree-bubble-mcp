"""Compatibility matching for reusable transfer dependencies."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.models import TransferDependency


@dataclass(frozen=True)
class ReuseCandidate:
    target_id: str
    target_label: str
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


_SECRET_KEY_RE = re.compile(r"(auth|bearer|cookie|key|password|secret|token)", re.IGNORECASE)


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _SECRET_KEY_RE.search(key_str):
                continue
            if key_str in {"id", "_id", "bubble_id", "call_id", "api_id", "name", "%nm", "%d", "label", "human"}:
                continue
            cleaned[key_str] = _clean(item)
        return cleaned
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


def _properties(metadata: dict[str, Any]) -> dict[str, Any]:
    properties = _obj(metadata.get("properties"))
    if properties:
        return properties
    for key in ("style", "style_properties", "%p"):
        item = _obj(metadata.get(key))
        if item:
            return item
    return {}


def _style_signature(metadata: dict[str, Any]) -> dict[str, Any]:
    properties = _clean(_properties(metadata))
    if not properties:
        return {}
    element_type = (
        metadata.get("element_type")
        or metadata.get("bubble_element_type")
        or _obj(metadata.get("properties")).get("%x")
        or _obj(metadata.get("style")).get("%x")
    )
    signature: dict[str, Any] = {"properties": properties}
    if element_type:
        signature["element_type"] = str(element_type)
    return signature


def _value_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        items = []
        for key, item in value.items():
            if isinstance(item, dict):
                items.append(str(item.get("%d") or item.get("label") or item.get("name") or key))
            else:
                items.append(str(item))
        return tuple(sorted(item.strip().lower() for item in items if item.strip()))
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                items.append(str(item.get("%d") or item.get("label") or item.get("name") or item.get("key") or ""))
            else:
                items.append(str(item))
        return tuple(sorted(item.strip().lower() for item in items if item.strip()))
    return ()


def _option_set_signature(metadata: dict[str, Any]) -> dict[str, Any]:
    values = _value_list(metadata.get("values") or _obj(metadata.get("properties")).get("values"))
    return {"values": values} if values else {}


def _api_call_signature(metadata: dict[str, Any]) -> dict[str, Any]:
    method = str(metadata.get("method") or _obj(metadata.get("properties")).get("method") or "").strip().upper()
    url = str(metadata.get("url") or _obj(metadata.get("properties")).get("url") or "").strip()
    return {"method": method, "url": url} if method and url else {}


def _simple_value_signature(metadata: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        value = metadata.get(key) or _obj(metadata.get("properties")).get(key)
        if isinstance(value, str) and value.strip():
            return {key: value.strip().lower()}
    return {}


def dependency_signature(dependency: TransferDependency) -> dict[str, Any]:
    """Return a comparable, non-secret signature for a source dependency."""

    metadata = dict(dependency.metadata)
    explicit = _obj(metadata.get("signature"))
    if explicit:
        return _clean(explicit)
    if dependency.kind == "style":
        return _style_signature(metadata)
    if dependency.kind == "option_set":
        return _option_set_signature(metadata)
    if dependency.kind == "api_connector_call":
        return _api_call_signature(metadata)
    if dependency.kind == "api_connector":
        return _simple_value_signature(metadata, ("base_url", "url"))
    if dependency.kind == "color":
        return _simple_value_signature(metadata, ("hex", "rgba", "rgb", "value", "color"))
    if dependency.kind == "font":
        return _simple_value_signature(metadata, ("font_family", "family", "font"))
    if dependency.kind == "asset":
        return _simple_value_signature(metadata, ("url", "src", "asset_url", "image_url"))
    if dependency.kind == "plugin":
        return _simple_value_signature(metadata, ("plugin_id", "package", "package_id"))
    return {}


def node_signature(kind: str, node: BubbleContextNode) -> dict[str, Any]:
    """Return a comparable, non-secret signature for a target context node."""

    metadata = dict(node.metadata)
    if kind == "style":
        return _style_signature(metadata)
    if kind == "option_set":
        return _option_set_signature(metadata)
    if kind == "api_connector_call":
        return _api_call_signature(metadata)
    if kind == "api_connector":
        return _simple_value_signature(metadata, ("base_url", "url"))
    if kind == "color":
        return _simple_value_signature(metadata, ("hex", "rgba", "rgb", "value", "color"))
    if kind == "font":
        return _simple_value_signature(metadata, ("font_family", "family", "font"))
    if kind == "asset":
        return _simple_value_signature(metadata, ("url", "src", "asset_url", "image_url"))
    if kind == "plugin":
        return _simple_value_signature(metadata, ("plugin_id", "package", "package_id"))
    return {}


def _target_reference(node: BubbleContextNode) -> dict[str, str]:
    reference: dict[str, str] = {"id": node.id, "label": node.label}
    for key in (
        "api_id",
        "bubble_id",
        "call_id",
        "context",
        "data_type",
        "field_key",
        "key",
        "name",
        "option_set",
        "value_key",
    ):
        value = node.metadata.get(key)
        if isinstance(value, str) and value.strip():
            reference[key] = value.strip()
    return reference


def find_compatible_target_dependency(
    dependency: TransferDependency,
    target_context: BubbleProjectContext,
) -> ReuseCandidate | None:
    """Find a target dependency that is structurally compatible with the source."""

    source_signature = dependency_signature(dependency)
    if not source_signature:
        return None
    source_digest = _digest(source_signature)
    for node in target_context.nodes:
        if node.type != dependency.kind:
            continue
        target_signature = node_signature(dependency.kind, node)
        if not target_signature or _digest(target_signature) != source_digest:
            continue
        fields = sorted(str(key) for key in source_signature)
        return ReuseCandidate(
            target_id=node.id,
            target_label=node.label,
            confidence=0.95,
            reason=f"Matched compatible target {dependency.kind} by structural signature.",
            metadata={
                "match_type": "compatible",
                "signature_digest": source_digest,
                "signature_fields": fields,
                "target_reference": _target_reference(node),
            },
        )
    return None
