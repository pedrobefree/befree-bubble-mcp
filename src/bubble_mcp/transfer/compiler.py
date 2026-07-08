"""Compile transfer inventories into target Bubble editor payloads."""

from __future__ import annotations

import json
from typing import Any

from bubble_mcp.compiler.payload import (
    bubble_element_id,
    bubble_session_id,
    change_app_setting_change,
    compile_step_to_payload,
    create_change,
    resolve_parent_path,
)
from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.transfer.models import TransferInventory


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _source_element_id(node: dict[str, Any]) -> str:
    metadata = _obj(node.get("metadata"))
    return str(metadata.get("bubble_id") or node.get("id", "").split(":", 1)[-1]).strip()


def _source_parent_id(node: dict[str, Any]) -> str | None:
    metadata = _obj(node.get("metadata"))
    raw_path = metadata.get("path") or metadata.get("path_array")
    if not isinstance(raw_path, list):
        return None
    path = [str(item) for item in raw_path]
    if "%el" not in path:
        return None
    last_el_index = len(path) - 1 - path[::-1].index("%el")
    if last_el_index >= 3:
        return path[last_el_index - 1]
    return None


def _element_body(node: dict[str, Any], *, new_id: str, target_name: str | None) -> dict[str, Any]:
    metadata = _obj(node.get("metadata"))
    raw_properties = _obj(metadata.get("properties"))
    element_type = str(raw_properties.get("%x") or metadata.get("element_type") or "Group")
    props = _obj(raw_properties.get("%p"))
    if not props:
        props = {key: value for key, value in raw_properties.items() if key != "%x"}
    props = json.loads(json.dumps(props))
    if target_name:
        props["%nm"] = target_name
    elif "%nm" not in props:
        props["%nm"] = str(node.get("label") or new_id)
    return {"id": new_id, "%x": element_type, "%p": props}


def compile_inventory_to_target_payloads(
    *,
    inventory: TransferInventory,
    target_context: BubbleProjectContext,
    target_app_id: str,
    target_app_version: str,
    target_context_ref: str,
    target_parent_ref: str | None = "root",
    target_name: str | None = None,
) -> list[dict[str, Any]]:
    """Compile element transfer inventory into an ordered target write payload."""

    element_nodes = [node for node in inventory.nodes if node.get("type") == "element"]
    if not element_nodes:
        return []

    session_id = bubble_session_id()
    id_map: dict[str, str] = {}
    changes: list[dict[str, Any]] = []
    base_parent_path = resolve_parent_path(
        {"context": target_context_ref, "parent": target_parent_ref or "root"},
        context=target_context,
    )

    for index, node in enumerate(element_nodes):
        source_id = _source_element_id(node)
        target_id = bubble_element_id()
        id_map[source_id] = target_id
        source_parent = _source_parent_id(node)
        parent_path = [*base_parent_path]
        if source_parent and source_parent in id_map:
            parent_path = [*base_parent_path, "%el", id_map[source_parent]]
        body = _element_body(node, new_id=target_id, target_name=target_name if index == 0 else None)
        changes.append(create_change(parent_path, body, session_id))

    return [
        {
            "v": 1,
            "appname": target_app_id,
            "app_version": target_app_version or "test",
            "appVersion": target_app_version or "test",
            "changes": changes,
        }
    ]


def compile_collection_actions_to_payloads(
    *,
    actions: list[dict[str, Any]],
    target_context: BubbleProjectContext,
    target_app_id: str,
    target_app_version: str,
) -> list[dict[str, Any]]:
    """Compile planned collection schema actions into target write payloads."""

    payloads: list[dict[str, Any]] = []
    for action in actions:
        action_name = str(action.get("action") or "")
        if action_name == "create_data_type":
            payload = compile_step_to_payload(
                {
                    "tool_name": "create_data_type",
                    "args": {
                        "name": str(action.get("label") or action.get("data_type") or ""),
                        "key": str(action.get("data_type") or ""),
                    },
                },
                app_id=target_app_id,
                app_version=target_app_version,
                context=target_context,
            )
        elif action_name == "create_data_field":
            payload = compile_step_to_payload(
                {
                    "tool_name": "create_data_field",
                    "args": {
                        "data_type_key": str(action.get("data_type") or ""),
                        "field_name": str(action.get("field_key") or ""),
                        "field_key": str(action.get("field_key") or ""),
                        "field_type": str(action.get("field_type") or "text"),
                    },
                },
                app_id=target_app_id,
                app_version=target_app_version,
                context=target_context,
            )
        elif action_name == "create_option_set":
            payload = compile_step_to_payload(
                {
                    "tool_name": "create_option_set",
                    "args": {
                        "name": str(action.get("label") or action.get("option_set") or ""),
                        "key": str(action.get("option_set") or ""),
                    },
                },
                app_id=target_app_id,
                app_version=target_app_version,
                context=target_context,
            )
        elif action_name == "create_option_value":
            payload = compile_step_to_payload(
                {
                    "tool_name": "create_option_value",
                    "args": {
                        "option_set_key": str(action.get("option_set") or ""),
                        "label": str(action.get("label") or ""),
                        "value_key": str(action.get("value_key") or ""),
                        "db_value": str(action.get("db_value") or ""),
                    },
                },
                app_id=target_app_id,
                app_version=target_app_version,
                context=target_context,
            )
        elif action_name == "ensure_privacy_rule":
            session_id = bubble_session_id()
            data_type = str(action.get("data_type") or "")
            rule_key = str(action.get("rule_key") or "")
            body = _obj(action.get("payload"))
            if not body:
                body = {
                    "%d": str(action.get("label") or rule_key or "New rule"),
                    "permissions": {
                        "view_all": True,
                        "view_attachments": True,
                        "search_for": True,
                        "auto_binding": False,
                    },
                }
            payload = {
                "v": 1,
                "appname": target_app_id,
                "app_version": target_app_version or "test",
                "appVersion": target_app_version or "test",
                "changes": [
                    change_app_setting_change(
                        ["user_types", data_type, "privacy_role", rule_key],
                        body,
                        session_id,
                    )
                ],
            }
        else:
            payload = None
        if payload is not None:
            payload["appVersion"] = target_app_version or "test"
            payloads.append(payload)
    return payloads
