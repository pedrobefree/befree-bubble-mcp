"""Dependency extraction for Bubble transfer inventory."""

from __future__ import annotations

from typing import Any, Iterable

from bubble_mcp.compiler.payload import VISUAL_CREATE_TYPES
from bubble_mcp.context.models import BubbleContextNode
from bubble_mcp.transfer.models import DependencyKind, TransferDependency


_METADATA_DEPENDENCY_KEYS: dict[str, DependencyKind] = {
    "api_connector": "api_connector",
    "api_connector_call": "api_connector_call",
    "asset_url": "asset",
    "color": "color",
    "custom_state": "custom_state",
    "data_field": "data_field",
    "data_type": "data_type",
    "data_type_key": "data_type",
    "font": "font",
    "image_url": "asset",
    "option_set": "option_set",
    "plugin": "plugin",
    "privacy_rule": "privacy_rule",
    "style": "style",
    "workflow": "workflow",
}

_CORE_ELEMENT_TYPES = {
    *VISUAL_CREATE_TYPES.values(),
    "AutocompleteDropdown",
    "BuiltOnBubble",
    "Checkbox",
    "CustomDefinition",
    "DateInput",
    "Dropdown",
    "FileInput",
    "FloatingGroup",
    "Group",
    "GroupFocus",
    "HTML",
    "Icon",
    "Image",
    "Input",
    "Link",
    "Map",
    "MultiLineInput",
    "Page",
    "PictureInput",
    "Popup",
    "RadioButtons",
    "RepeatingGroup",
    "Shape",
    "SliderInput",
    "Table",
    "TableCrossAxis",
    "TableMainAxis",
    "Text",
    "VideoPlayer",
}


def _iter_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            yield normalized
        return
    if isinstance(value, (int, float, bool)):
        yield str(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_values(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_values(item)


def _plugin_element_type(value: Any) -> str | None:
    element_type = str(value or "").strip()
    if not element_type or element_type in _CORE_ELEMENT_TYPES:
        return None
    if "-" in element_type or "x" in element_type:
        return element_type
    return None


def _plugin_install_metadata(plugin_type: str, source_plugins: dict[str, Any]) -> dict[str, Any]:
    install_key = plugin_type.split("-", 1)[0].strip() if "-" in plugin_type else plugin_type
    metadata: dict[str, Any] = {"install_key": install_key}
    if install_key in source_plugins:
        metadata["source_plugin_value"] = source_plugins[install_key]
        metadata["source_plugin_value_type"] = type(source_plugins[install_key]).__name__
    return metadata


def extract_node_dependencies(
    nodes: list[BubbleContextNode],
    *,
    source_plugins: dict[str, Any] | None = None,
) -> list[TransferDependency]:
    """Extract stable dependency references from node metadata."""

    plugin_registry = source_plugins if isinstance(source_plugins, dict) else {}
    seen: set[tuple[DependencyKind, str]] = set()
    dependencies: list[TransferDependency] = []
    for node in nodes:
        plugin_type = _plugin_element_type(node.metadata.get("element_type"))
        if plugin_type:
            key = ("plugin", plugin_type)
            if key not in seen:
                seen.add(key)
                dependencies.append(
                    TransferDependency(
                        kind="plugin",
                        key=plugin_type,
                        label=f"Bubble plugin element/action type {plugin_type}",
                        source_id=node.metadata.get("bubble_id") or node.id,
                        required=True,
                        metadata={
                            "source_node_id": node.id,
                            "metadata_key": "element_type",
                            "install_required": True,
                            **_plugin_install_metadata(plugin_type, plugin_registry),
                        },
                    )
                )
        for metadata_key, kind in _METADATA_DEPENDENCY_KEYS.items():
            if metadata_key not in node.metadata:
                continue
            for value in _iter_values(node.metadata.get(metadata_key)):
                key = (kind, value)
                if key in seen:
                    continue
                seen.add(key)
                dependencies.append(
                    TransferDependency(
                        kind=kind,
                        key=value,
                        label=value,
                        source_id=node.metadata.get("bubble_id") or node.id,
                        secret=kind in {"api_connector", "api_connector_call"},
                        metadata={"source_node_id": node.id, "metadata_key": metadata_key},
                    )
                )
    return dependencies
