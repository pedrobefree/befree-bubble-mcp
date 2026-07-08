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
    update_index_change,
)
from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.transfer.models import TransferInventory, TransferMappingDecision


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


def _target_ref(decision: TransferMappingDecision, *keys: str) -> str | None:
    reference = _obj(decision.metadata.get("target_reference"))
    for key in keys:
        value = reference.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _add_remap(remap: dict[str, str], source: Any, target: Any) -> None:
    if not isinstance(source, str) or not isinstance(target, str):
        return
    source_value = source.strip()
    target_value = target.strip()
    if source_value and target_value and source_value != target_value:
        remap[source_value] = target_value


def _dependency_remap(decisions: list[TransferMappingDecision] | None) -> dict[str, str]:
    remap: dict[str, str] = {}
    for decision in decisions or []:
        if decision.action != "map_existing":
            continue
        dependency = decision.dependency
        target_id = decision.target_id or _target_ref(decision, "id")
        target_label = decision.target_label or _target_ref(decision, "label", "name")
        target_key = _target_ref(
            decision,
            "key",
            "bubble_id",
            "data_type",
            "field_key",
            "option_set",
            "value_key",
            "api_id",
            "call_id",
            "context",
            "id",
        )
        target_bubble_id = _target_ref(decision, "bubble_id", "id")
        source_metadata = _obj(dependency.metadata)
        _add_remap(remap, dependency.key, target_key or target_label or target_id)
        _add_remap(remap, dependency.label, target_label or target_key or target_id)
        _add_remap(remap, dependency.source_id, target_bubble_id or target_id)
        for source_key, target_keys in {
            "api_id": ("api_id", "key", "id"),
            "bubble_id": ("bubble_id", "id"),
            "call_id": ("call_id", "key", "id"),
            "context": ("context", "key", "id"),
            "data_type": ("data_type", "key", "id"),
            "field_key": ("field_key", "key", "id"),
            "key": ("key", "id"),
            "name": ("name", "label"),
            "option_set": ("option_set", "key", "id"),
            "value_key": ("value_key", "key", "id"),
        }.items():
            _add_remap(remap, source_metadata.get(source_key), _target_ref(decision, *target_keys))
    return remap


def _remap_value(value: Any, remap: dict[str, str]) -> Any:
    if isinstance(value, str):
        return remap.get(value, value)
    if isinstance(value, list):
        return [_remap_value(item, remap) for item in value]
    if isinstance(value, dict):
        return {key: _remap_value(item, remap) for key, item in value.items()}
    return value


def _raw_reusable_definition(inventory: TransferInventory) -> dict[str, Any]:
    metadata = _obj(inventory.root.get("metadata"))
    raw = metadata.get("raw_definition")
    return raw if isinstance(raw, dict) else {}


def _child_ids_by_parent(element_nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    source_ids = {_source_element_id(node) for node in element_nodes}
    children: dict[str, list[str]] = {}
    root_children: list[str] = []
    for node in element_nodes:
        source_id = _source_element_id(node)
        source_parent = _source_parent_id(node)
        if source_parent and source_parent in source_ids:
            children.setdefault(source_parent, []).append(source_id)
        else:
            root_children.append(source_id)
    children[""] = root_children
    return children


def _element_body(
    node: dict[str, Any],
    *,
    new_id: str,
    target_name: str | None,
    remap: dict[str, str] | None = None,
) -> dict[str, Any]:
    metadata = _obj(node.get("metadata"))
    raw_properties = _obj(metadata.get("properties"))
    element_type = str(raw_properties.get("%x") or metadata.get("element_type") or "Group")
    props = _obj(raw_properties.get("%p"))
    if not props:
        props = {key: value for key, value in raw_properties.items() if key != "%x"}
    props = json.loads(json.dumps(props))
    if remap:
        props = _remap_value(props, remap)
    if target_name:
        props["%nm"] = target_name
    elif "%nm" not in props:
        props["%nm"] = str(node.get("label") or new_id)
    return {"id": new_id, "%x": element_type, "%p": props}


def _append_reusable_children(
    *,
    body: dict[str, Any],
    source_id: str,
    nodes_by_source_id: dict[str, dict[str, Any]],
    id_map: dict[str, str],
    children_by_parent: dict[str, list[str]],
    remap: dict[str, str],
) -> None:
    child_bodies: dict[str, dict[str, Any]] = {}
    for child_source_id in children_by_parent.get(source_id, []):
        child_target_id = id_map[child_source_id]
        child_node = nodes_by_source_id[child_source_id]
        child_body = _element_body(child_node, new_id=child_target_id, target_name=None, remap=remap)
        _append_reusable_children(
            body=child_body,
            source_id=child_source_id,
            nodes_by_source_id=nodes_by_source_id,
            id_map=id_map,
            children_by_parent=children_by_parent,
            remap=remap,
        )
        child_bodies[child_target_id] = child_body
    if child_bodies:
        body["%el"] = child_bodies


def _collect_nested_ids(body: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    children = body.get("%el")
    if not isinstance(children, dict):
        return ids
    for child_id, child_body in children.items():
        ids.append(str(child_id))
        if isinstance(child_body, dict):
            ids.extend(_collect_nested_ids(child_body))
    return ids


def _nested_child_paths(body: dict[str, Any], root_path: list[str]) -> list[tuple[str, list[str], list[str]]]:
    paths: list[tuple[str, list[str], list[str]]] = []
    children = body.get("%el")
    if not isinstance(children, dict):
        return paths
    child_ids = [str(child_id) for child_id in children]
    for child_id, child_body in children.items():
        child_id_str = str(child_id)
        child_path = [*root_path, "%el", child_id_str]
        nested_ids: list[str] = []
        if isinstance(child_body, dict):
            nested_ids = _collect_nested_ids(child_body)
            paths.extend(_nested_child_paths(child_body, child_path))
        paths.append((child_id_str, child_path, nested_ids))
    if child_ids:
        paths.append(("", root_path, child_ids))
    return paths


def compile_inventory_to_target_payloads(
    *,
    inventory: TransferInventory,
    target_context: BubbleProjectContext,
    target_app_id: str,
    target_app_version: str,
    target_context_ref: str,
    target_parent_ref: str | None = "root",
    target_name: str | None = None,
    target_context_type: str = "page",
    dependency_decisions: list[TransferMappingDecision] | None = None,
) -> list[dict[str, Any]]:
    """Compile element transfer inventory into an ordered target write payload."""

    element_nodes = [node for node in inventory.nodes if node.get("type") == "element"]
    if not element_nodes:
        return []

    session_id = bubble_session_id()
    id_map = {_source_element_id(node): bubble_element_id() for node in element_nodes}
    remap = {**_dependency_remap(dependency_decisions), **id_map}
    changes: list[dict[str, Any]] = []
    base_parent_path = resolve_parent_path(
        {
            "context": target_context_ref,
            "context_type": "reusable" if target_context_type == "reusable" else "page",
            "parent": target_parent_ref or "root",
        },
        context=target_context,
    )

    for index, node in enumerate(element_nodes):
        source_id = _source_element_id(node)
        target_id = id_map[source_id]
        source_parent = _source_parent_id(node)
        parent_path = [*base_parent_path]
        if source_parent and source_parent in id_map:
            parent_path = [*base_parent_path, "%el", id_map[source_parent]]
        body = _element_body(
            node,
            new_id=target_id,
            target_name=target_name if index == 0 else None,
            remap=remap,
        )
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


def compile_reusable_inventory_to_payload(
    *,
    inventory: TransferInventory,
    target_app_id: str,
    target_app_version: str,
    target_name: str | None = None,
    dependency_decisions: list[TransferMappingDecision] | None = None,
) -> tuple[dict[str, Any], str] | None:
    """Compile a reusable transfer as one nested CustomDefinition payload."""

    if inventory.source.source_type != "reusable":
        return None
    raw_definition = _raw_reusable_definition(inventory)
    if raw_definition:
        resolved_name = target_name or inventory.source.ref
        slot_id = bubble_element_id()
        builder = PayloadBuilder(appname=target_app_id, app_version=target_app_version or "test")
        source_slot_id = inventory.source.bubble_id or str(inventory.root.get("id", "")).split(":", 1)[-1]
        builder.add_clone_reusable(source_slot_id, slot_id, resolved_name, raw_definition)
        payload = builder.build()
        payload["appVersion"] = target_app_version or "test"
        return payload, slot_id

    element_nodes = [node for node in inventory.nodes if node.get("type") == "element"]
    session_id = bubble_session_id()
    slot_id = bubble_element_id()
    object_id = bubble_element_id()
    id_map = {_source_element_id(node): bubble_element_id() for node in element_nodes}
    nodes_by_source_id = {_source_element_id(node): node for node in element_nodes}
    children_by_parent = _child_ids_by_parent(element_nodes)
    remap = {**_dependency_remap(dependency_decisions), **id_map}
    metadata = _obj(inventory.root.get("metadata"))
    raw_properties = _obj(metadata.get("properties"))
    props = _obj(raw_properties.get("%p")) or {key: value for key, value in raw_properties.items() if key != "%x"}
    props = _remap_value(json.loads(json.dumps(props)), remap)
    resolved_name = target_name or inventory.source.ref
    props["%nm"] = resolved_name
    props.setdefault("default_width", props.get("%w", 280))
    body: dict[str, Any] = {
        "id": object_id,
        "%x": "CustomDefinition",
        "%nm": resolved_name,
        "%p": props,
    }
    root_children: dict[str, dict[str, Any]] = {}
    for child_source_id in children_by_parent.get("", []):
        child_target_id = id_map[child_source_id]
        child_body = _element_body(nodes_by_source_id[child_source_id], new_id=child_target_id, target_name=None, remap=remap)
        _append_reusable_children(
            body=child_body,
            source_id=child_source_id,
            nodes_by_source_id=nodes_by_source_id,
            id_map=id_map,
            children_by_parent=children_by_parent,
            remap=remap,
        )
        root_children[child_target_id] = child_body
    if root_children:
        body["%el"] = root_children
    root_path = ["%ed", slot_id]
    changes = [
        update_index_change(["_index", "id_to_path", object_id], ".".join(root_path), session_id),
        create_change(root_path, body, session_id),
        update_index_change(["_index", "issues_list", object_id], "[]", session_id),
    ]
    for child_id, child_path, nested_ids in _nested_child_paths(body, root_path):
        if not child_id:
            changes.append(update_index_change(["_index", "issues_sub", object_id], nested_ids, session_id))
            continue
        changes.append(update_index_change(["_index", "id_to_path", child_id], ".".join(child_path), session_id))
        changes.append(update_index_change(["_index", "issues_list", child_id], "[]", session_id))
        if nested_ids:
            changes.append(update_index_change(["_index", "issues_sub", child_id], nested_ids, session_id))
    payload = {
        "v": 1,
        "appname": target_app_id,
        "app_version": target_app_version or "test",
        "appVersion": target_app_version or "test",
        "changes": changes,
    }
    return payload, slot_id


def compile_context_shell_payload(
    *,
    source_type: str,
    source_root: dict[str, Any],
    target_app_id: str,
    target_app_version: str,
    target_name: str,
) -> tuple[dict[str, Any], str, str] | None:
    """Compile a minimal target page/reusable shell and return its context ref."""

    if source_type not in {"page", "reusable"}:
        return None
    context_type = "reusable" if source_type == "reusable" else "page"
    prefix = "%ed" if context_type == "reusable" else "%p3"
    element_type = "CustomDefinition" if context_type == "reusable" else "Page"
    session_id = bubble_session_id()
    slot_id = bubble_element_id()
    object_id = bubble_element_id()
    metadata = _obj(source_root.get("metadata"))
    raw_properties = _obj(metadata.get("properties"))
    props = _obj(raw_properties.get("%p")) or {key: value for key, value in raw_properties.items() if key != "%x"}
    props = json.loads(json.dumps(props))
    props["%nm"] = target_name
    if context_type == "page":
        props.setdefault("default_width", 1080)
        props.setdefault("min_height_px", 767)
    else:
        props.setdefault("%w", 280)
        props.setdefault("%h", 280)
        props.setdefault("default_width", props.get("%w", 280))
    body = {"id": object_id, "%x": element_type, "%p": props, "%nm": target_name}
    payload = {
        "v": 1,
        "appname": target_app_id,
        "app_version": target_app_version or "test",
        "appVersion": target_app_version or "test",
        "changes": [
            update_index_change(["_index", "id_to_path", object_id], f"{prefix}.{slot_id}", session_id),
            create_change([prefix, slot_id], body, session_id),
            update_index_change(["_index", "issues_list", object_id], "[]", session_id),
            update_index_change(["_index", "issues_sub", object_id], "[]", session_id),
        ],
    }
    return payload, slot_id, context_type


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


def _create_api_call_change(path_array: list[str], body: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "intent": {"name": "CreateApiCall"},
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def compile_api_connector_actions_to_payloads(
    *,
    actions: list[dict[str, Any]],
    target_app_id: str,
    target_app_version: str,
) -> list[dict[str, Any]]:
    """Compile structure-only API Connector actions into target write payloads."""

    payloads: list[dict[str, Any]] = []
    for action in actions:
        action_name = str(action.get("action") or "")
        api_id = str(action.get("api_id") or "").strip()
        if not api_id:
            continue
        session_id = bubble_session_id()
        if action_name == "create_api_connector":
            changes = [
                change_app_setting_change(
                    ["settings", "client_safe", "apiconnector2", api_id],
                    {"human": str(action.get("name") or api_id), "calls": {}},
                    session_id,
                )
            ]
        elif action_name == "create_api_connector_call":
            call_id = str(action.get("call_id") or "").strip()
            if not call_id:
                continue
            method = str(action.get("method") or "GET").strip().lower()
            url = str(action.get("url") or "").strip()
            call_path = ["settings", "client_safe", "apiconnector2", api_id, "calls", call_id]
            call_body = {
                "%nm": str(action.get("name") or call_id),
                "method": method,
                "publish_as": str(action.get("publish_as") or "data"),
                "rank": int(action.get("rank") or 0),
                "url_cant_be_private": True,
            }
            changes = [_create_api_call_change(call_path, call_body, session_id)]
            if url:
                changes.append(change_app_setting_change([*call_path, "url"], url, session_id))
            if method:
                changes.append(change_app_setting_change([*call_path, "method"], method, session_id))
        else:
            continue
        payloads.append(
            {
                "v": 1,
                "appname": target_app_id,
                "app_version": target_app_version or "test",
                "appVersion": target_app_version or "test",
                "changes": changes,
            }
        )
    return payloads
