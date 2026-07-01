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
    if tool_name == "create_text":
        body = compile_create_text_step(args, context=context)
    elif tool_name == "create_group":
        body = compile_create_group_step(args, context=context)
    else:
        return None

    session_id = bubble_session_id()
    return {
        "v": 1,
        "appname": app_id,
        "app_version": app_version,
        "changes": [
            create_change(resolve_parent_path(args, context=context), body, session_id),
        ],
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
