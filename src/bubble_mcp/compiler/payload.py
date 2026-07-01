"""Minimal Bubble editor payload compiler.

This module intentionally keeps the payload surface small and explicit. It
compiles supported plan steps into Bubble `/appeditor/write` `CreateElement`
changes, using the same high-level envelope shape as Aria's Bubble SDK.
"""

from __future__ import annotations

import random
import string
import time
from typing import Any

from bubble_mcp.context.models import BubbleProjectContext


ROOT_PARENT_NAMES = {"", "root", "page", "index"}


def bubble_element_id(length: int = 5) -> str:
    chars = string.ascii_letters + string.digits
    return "b" + "".join(random.choice(chars) for _ in range(length - 1))


def bubble_session_id() -> str:
    return f"{int(time.time() * 1000)}x{random.randint(10, 99)}"


def resolve_context_key(name: str, context: BubbleProjectContext | None = None) -> str:
    target = str(name or "index").strip()
    if context is not None:
        for node in context.nodes:
            if node.type not in {"page", "reusable"}:
                continue
            if node.label == target or node.id == target or node.id.endswith(f":{target}"):
                meta_key = node.metadata.get("bubble_id") or node.metadata.get("key")
                return str(meta_key or node.label or target)
    if ":" in target:
        return target.split(":", 1)[1]
    return target


def resolve_parent_path(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None = None,
) -> list[str]:
    context_key = resolve_context_key(str(args.get("context") or "index"), context)
    parent = str(args.get("parent") or "").strip()
    path = ["%p3", context_key]
    if parent.lower() in ROOT_PARENT_NAMES or parent == context_key:
        return path

    if context is not None:
        for node in context.nodes:
            if node.type != "element":
                continue
            if node.label == parent or node.id == parent or node.id.endswith(f":{parent}"):
                raw_path = node.metadata.get("path_array")
                if isinstance(raw_path, list) and raw_path:
                    return [str(item) for item in raw_path]
                element_key = str(node.metadata.get("bubble_id") or node.metadata.get("key") or "").strip()
                if element_key:
                    return [*path, "%el", element_key]

    return [*path, "%el", parent]


def create_change(path_array: list[str], body: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "CreateElement",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def set_data_change(path_array: list[str], body: Any, session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "SetData",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def delete_change(path_array: list[str], session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "Delete",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": None,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def slug_key(value: str, prefix: str = "") -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in str(value).strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return f"{prefix}{normalized}" if prefix and not normalized.startswith(prefix) else normalized


def resolve_element_path(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None = None,
) -> list[str]:
    element_name = str(args.get("element_name") or args.get("name") or args.get("target") or "").strip()
    if not element_name:
        raise ValueError("element_name is required.")
    context_key = resolve_context_key(str(args.get("context") or "index"), context)
    root_path = ["%p3", context_key]
    if context is not None:
        for node in context.nodes:
            if node.type != "element":
                continue
            if node.label == element_name or node.id == element_name or node.id.endswith(f":{element_name}"):
                raw_path = node.metadata.get("path_array")
                if isinstance(raw_path, list) and raw_path:
                    return [str(item) for item in raw_path]
                element_key = str(node.metadata.get("bubble_id") or node.metadata.get("key") or "").strip()
                if element_key:
                    return [*root_path, "%el", element_key]
    return [*root_path, "%el", element_name]


def compile_create_text_step(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
) -> dict[str, Any]:
    content = str(args.get("content") or "").strip()
    if not content:
        raise ValueError("create_text requires content.")
    name = str(args.get("name") or "").strip() or f"Text {content[:24]}".strip()
    element_id = bubble_element_id()
    properties: dict[str, Any] = {
        "%nm": name,
        "%3": content,
        "%fs": int(args.get("font_size") or 16),
    }
    if args.get("font_color"):
        properties["%fc"] = args["font_color"]
    if args.get("font_alignment"):
        properties["%fa"] = args["font_alignment"]
    return {
        "%x": "Text",
        "%p": properties,
        "id": element_id,
    }


def compile_create_group_step(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
) -> dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        raise ValueError("create_group requires name.")
    element_id = bubble_element_id()
    layout = str(args.get("layout") or "column").strip().lower().replace("-", "_").replace(" ", "_")
    if layout == "align_parent":
        layout = "align_to_parent"
    wire_layout = "relative" if layout == "align_to_parent" else layout
    properties: dict[str, Any] = {
        "%nm": name,
        "container_layout": wire_layout,
    }
    for source_key, wire_key in (
        ("row_gap", "row_gap"),
        ("column_gap", "column_gap"),
        ("background_style", "%bas"),
        ("bg_color", "%bgc"),
        ("border_radius", "%br"),
    ):
        if args.get(source_key) is not None:
            properties[wire_key] = args[source_key]
    return {
        "%x": "Group",
        "%p": properties,
        "id": element_id,
    }


def compile_update_text_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    content = str(args.get("content") or args.get("new_text") or "").strip()
    if not content:
        raise ValueError("update_text requires content/new_text.")
    path = [*resolve_element_path(args, context=context), "%p", "%3"]
    return [set_data_change(path, content, session_id)]


def compile_update_group_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    path = [*resolve_element_path(args, context=context), "%p"]
    properties: dict[str, Any] = {}
    for source_key, wire_key in (
        ("layout", "container_layout"),
        ("row_gap", "row_gap"),
        ("column_gap", "column_gap"),
        ("background_style", "%bas"),
        ("bg_color", "%bgc"),
        ("border_radius", "%br"),
        ("name", "%nm"),
    ):
        if args.get(source_key) is not None:
            value = args[source_key]
            if source_key == "layout":
                value = str(value).strip().lower().replace("-", "_").replace(" ", "_")
                if value == "align_to_parent":
                    value = "relative"
            properties[wire_key] = value
    if not properties:
        raise ValueError("update_group requires at least one supported property.")
    return [set_data_change(path, properties, session_id)]


def compile_delete_element_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    return [delete_change(resolve_element_path(args, context=context), session_id)]


def compile_schema_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    if tool_name == "create_data_type":
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("create_data_type requires name.")
        key = str(args.get("key") or slug_key(name)).strip()
        return [
            set_data_change(
                ["data_types", key],
                {"%nm": name, "name": name, "key": key, "fields": {}},
                session_id,
            )
        ]
    if tool_name == "create_data_field":
        data_type = str(args.get("data_type_key") or args.get("type") or "").strip()
        field_name = str(args.get("field_name") or args.get("name") or "").strip()
        field_type = str(args.get("field_type") or "text").strip()
        if not data_type or not field_name:
            raise ValueError("create_data_field requires data_type_key and field_name.")
        field_key = str(args.get("field_key") or slug_key(field_name)).strip()
        return [
            set_data_change(
                ["data_types", data_type, "fields", field_key],
                {"%nm": field_name, "name": field_name, "type": field_type, "key": field_key},
                session_id,
            )
        ]
    return []


def compile_option_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    if tool_name == "create_option_set":
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("create_option_set requires name.")
        key = str(args.get("key") or slug_key(name, "os_")).strip()
        return [
            set_data_change(
                ["option_sets", key],
                {"%nm": name, "name": name, "key": key, "values": {}},
                session_id,
            )
        ]
    if tool_name == "create_option_value":
        option_set = str(args.get("option_set_key") or "").strip()
        label = str(args.get("label") or args.get("name") or "").strip()
        if not option_set or not label:
            raise ValueError("create_option_value requires option_set_key and label.")
        value_key = str(args.get("value_key") or bubble_element_id()).strip()
        db_value = str(args.get("db_value") or slug_key(label)).strip()
        return [
            set_data_change(
                ["option_sets", option_set, "values", value_key],
                {"%nm": label, "label": label, "db_value": db_value, "key": value_key},
                session_id,
            )
        ]
    return []


def compile_theme_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    if tool_name in {"create_color", "update_color"}:
        name = str(args.get("name") or "").strip()
        rgba = str(args.get("rgba") or args.get("color") or "").strip()
        if not name or not rgba:
            raise ValueError(f"{tool_name} requires name and rgba/color.")
        key = str(args.get("key") or slug_key(name, "color_")).strip()
        return [
            set_data_change(
                ["styles", "colors", key],
                {"%nm": name, "name": name, "rgba": rgba, "description": args.get("description") or ""},
                session_id,
            )
        ]
    if tool_name == "create_style":
        name = str(args.get("name") or "").strip()
        element_type = str(args.get("element_type") or args.get("type") or "").strip()
        if not name or not element_type:
            raise ValueError("create_style requires name and element_type.")
        key = str(args.get("key") or slug_key(name, "style_")).strip()
        properties = {"%nm": name, "name": name, "element_type": element_type}
        for source_key in ("font_size", "font_color", "bg_color", "border_radius", "font_weight"):
            if args.get(source_key) is not None:
                properties[source_key] = args[source_key]
        return [set_data_change(["styles", key], properties, session_id)]
    return []


def compile_workflow_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    context_key = resolve_context_key(str(args.get("context") or "index"))
    if tool_name == "create_workflow":
        event = str(args.get("event") or "click").strip()
        element_name = str(args.get("element_name") or "").strip()
        workflow_id = str(args.get("workflow_id") or bubble_element_id()).strip()
        workflow_body: dict[str, Any] = {
            "%p": {
                "%nm": str(args.get("name") or f"{event} {element_name}".strip()),
                "event": event,
                "element_name": element_name,
            },
            "actions": {},
        }
        return [set_data_change(["%p3", context_key, "%wf", workflow_id], workflow_body, session_id)]
    if tool_name == "add_action":
        workflow_id = str(args.get("workflow_id") or args.get("event_id") or "").strip()
        action_type = str(args.get("action_type") or "navigate").strip()
        if not workflow_id:
            raise ValueError("add_action requires workflow_id/event_id.")
        action_index = str(args.get("action_index") or "0")
        action_body: dict[str, Any] = {
            "%x": action_type,
            "%p": {
                "param": args.get("param"),
                "target": args.get("target"),
                "name": args.get("name") or action_type,
            },
        }
        return [
            set_data_change(
                ["%p3", context_key, "%wf", workflow_id, "actions", action_index],
                action_body,
                session_id,
            )
        ]
    return []


def compile_step_to_payload(
    step: dict[str, Any],
    *,
    app_id: str,
    app_version: str = "test",
    context: BubbleProjectContext | None = None,
) -> dict[str, Any] | None:
    tool_name = str(step.get("tool_name") or "")
    raw_args = step.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}

    existing_payload = args.get("write_payload")
    if isinstance(existing_payload, dict):
        return existing_payload
    changes: list[dict[str, Any]]
    session_id = bubble_session_id()
    if tool_name == "create_text":
        body = compile_create_text_step(args, context=context)
        changes = [create_change(resolve_parent_path(args, context=context), body, session_id)]
    elif tool_name == "create_group":
        body = compile_create_group_step(args, context=context)
        changes = [create_change(resolve_parent_path(args, context=context), body, session_id)]
    elif tool_name == "update_text":
        changes = compile_update_text_changes(args, context=context, session_id=session_id)
    elif tool_name == "update_group":
        changes = compile_update_group_changes(args, context=context, session_id=session_id)
    elif tool_name == "delete_element":
        changes = compile_delete_element_changes(args, context=context, session_id=session_id)
    elif tool_name in {"create_data_type", "create_data_field"}:
        changes = compile_schema_changes(tool_name, args, session_id)
    elif tool_name in {"create_option_set", "create_option_value"}:
        changes = compile_option_changes(tool_name, args, session_id)
    elif tool_name in {"create_color", "update_color", "create_style"}:
        changes = compile_theme_changes(tool_name, args, session_id)
    elif tool_name in {"create_workflow", "add_action"}:
        changes = compile_workflow_changes(tool_name, args, session_id)
    else:
        return None

    return {
        "v": 1,
        "appname": app_id,
        "app_version": app_version,
        "changes": changes,
    }


def compile_plan_to_write_payloads(
    plan: dict[str, Any],
    *,
    app_id: str,
    app_version: str = "test",
    context: BubbleProjectContext | None = None,
) -> dict[str, Any]:
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Plan must include a steps array.")

    compiled_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Plan step {index + 1} must be an object.")
        step = dict(raw_step)
        raw_args = step.get("args")
        args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
        payload = compile_step_to_payload(step, app_id=app_id, app_version=app_version, context=context)
        if payload is not None:
            args["write_payload"] = payload
            step["args"] = args
        compiled_steps.append(step)

    compiled = dict(plan)
    compiled["steps"] = compiled_steps
    compiled["compiled"] = True
    compiled["app_id"] = app_id
    return compiled
