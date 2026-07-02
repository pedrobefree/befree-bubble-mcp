"""Execute Figma bridge sync payloads against Bubble.

The Figma plugin posts a rich tree to the local bridge. The bridge must not
acknowledge success until that tree is converted into Bubble editor writes and
the writes complete.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from bubble_mcp.compiler.payload import (
    bubble_element_id,
    bubble_session_id,
    compile_create_group_step,
    compile_create_text_step,
    create_change,
    create_visual_element_changes,
    update_index_change,
)
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.source import load_context
from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.sessions.store import load_session


TEXT_NODE_TYPES = {"TEXT"}
GROUP_NODE_TYPES = {"FRAME", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET"}


def _clean_name(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip() or fallback
    allowed = [char if char.isalnum() else "_" for char in text]
    cleaned = "_".join(part for part in "".join(allowed).split("_") if part)
    return cleaned[:80] or fallback


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _first_text_value(node: dict[str, Any]) -> str:
    for key in ("characters", "text", "content", "name"):
        value = str(node.get(key) or "").strip()
        if value:
            return value
    return ""


def _visible_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = node.get("children")
    if not isinstance(children, list):
        return []
    return [
        child
        for child in children
        if isinstance(child, dict) and child.get("visible", True) is not False
    ]


def _flatten_renderable_nodes(node: dict[str, Any], *, limit: int = 80) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []

    def walk(current: dict[str, Any]) -> None:
        if len(rendered) >= limit or current.get("visible", True) is False:
            return
        node_type = str(current.get("type") or "").upper()
        if node_type in TEXT_NODE_TYPES and _first_text_value(current):
            rendered.append(current)
        elif node_type in GROUP_NODE_TYPES and current is not node:
            name = str(current.get("name") or "").strip().lower()
            if any(token in name for token in ("button", "card", "badge", "container")):
                rendered.append(current)
        for child in _visible_children(current):
            walk(child)

    for child in _visible_children(node):
        walk(child)
    return rendered


def _root_reusable_payload(
    *,
    app_id: str,
    app_version: str,
    name: str,
    element_type: str,
    source_node: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    session_id = bubble_session_id()
    reusable_id = bubble_element_id()
    reusable_slot = bubble_element_id()
    width = max(_as_int(source_node.get("width"), 280), 1)
    height = max(_as_int(source_node.get("height"), 280), 1)
    layout = "row" if str(source_node.get("layout", {}).get("mode") or "").upper() == "HORIZONTAL" else "column"
    body = {
        "%x": "CustomDefinition",
        "%nm": name,
        "%p": {
            "new_responsive": True,
            "%et": element_type,
            "%w": width,
            "%h": height,
            "responsive_version": 1,
            "element_version": 5,
            "custom_element_platform": "web",
            "default_width": width,
            "min_width_px": width,
            "min_height_px": height,
            "container_layout": layout,
            "single_width": False,
            "single_height": False,
        },
        "id": reusable_id,
    }
    changes = [
        update_index_change(["_index", "id_to_path", reusable_id], f"%ed.{reusable_slot}", session_id),
        create_change(["%ed", reusable_slot], body, session_id),
        update_index_change(["_index", "issues_list", reusable_id], "[]", session_id),
        update_index_change(["_index", "issues_sub", reusable_id], "[]", session_id),
    ]
    return (
        {
            "v": 1,
            "appname": app_id,
            "app_version": app_version,
            "appVersion": app_version,
            "changes": changes,
        },
        reusable_slot,
        reusable_id,
    )


def _child_payload(
    *,
    app_id: str,
    app_version: str,
    node: dict[str, Any],
    context_key: str,
    context_type: str,
    parent_id: str,
    existing_children: list[str],
    index: int,
) -> tuple[dict[str, Any], str]:
    node_type = str(node.get("type") or "").upper()
    base_name = _clean_name(node.get("name"), fallback=f"figma_node_{index}")
    args: dict[str, Any] = {
        "context": context_key,
        "context_key": context_key,
        "context_type": context_type,
        "parent": "root",
        "parent_id": parent_id,
        "existing_children": existing_children,
        "name": f"{index:02d}_{base_name}",
        "slot_key": bubble_element_id(),
    }
    if node_type in TEXT_NODE_TYPES:
        args["content"] = _first_text_value(node)
        if node.get("fontSize") is not None:
            args["font_size"] = _as_int(node.get("fontSize"), 16)
        body = compile_create_text_step(args, context=None)
    else:
        args["layout"] = "row" if str(node.get("layout", {}).get("mode") or "").upper() == "HORIZONTAL" else "column"
        args["background_style"] = "none"
        body = compile_create_group_step(args, context=None)

    object_id = str(body["id"])
    changes = create_visual_element_changes(args, body, context=None, session_id=bubble_session_id())
    return (
        {
            "v": 1,
            "appname": app_id,
            "app_version": app_version,
            "appVersion": app_version,
            "changes": changes,
        },
        object_id,
    )


def _execute_payloads(
    payloads: list[dict[str, Any]],
    *,
    profile: str,
    execute: bool,
) -> list[dict[str, Any]]:
    session = load_session(profile)
    if execute and session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")
    client = BubbleEditorClient()
    results: list[dict[str, Any]] = []
    for index, payload in enumerate(payloads, start=1):
        if not execute:
            results.append({"ok": True, "executed": False, "dry_run": True, "payload": payload})
            continue
        assert session is not None
        result = client.write(payload, session, dry_run=False)
        results.append({"ok": bool(result.get("ok")), "executed": True, "result": result})
        if not result.get("ok"):
            break
    return [{"index": index, **result} for index, result in enumerate(results, start=1)]


class _FakeInquirer:
    class List:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    class Text:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    @staticmethod
    def prompt(_questions: Any) -> None:
        return None


def _load_aria_runtime_modules() -> tuple[Any, Any]:
    runtime_dir = Path(__file__).resolve().parent / "aria_runtime"
    runtime_path = str(runtime_dir)
    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)
    bubble_cli = importlib.import_module("bubble_cli")
    bubble_sdk = importlib.import_module("bubble_sdk")
    bubble_cli.inquirer = _FakeInquirer()
    return bubble_cli, bubble_sdk


def _sync_component_with_aria_runtime(
    payload: dict[str, Any],
    *,
    profile: str,
    app_id: str,
    app_version: str,
    execute: bool,
) -> dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    component_name = _clean_name(
        meta.get("component_name") or meta.get("componentName") or payload.get("content", {}).get("name"),
        fallback="figma_component",
    )
    element_type = str(meta.get("element_type") or meta.get("component_type") or "Group")
    import_mode = str(meta.get("import_mode") or meta.get("importMode") or "reusable").lower()
    child_context = str(meta.get("child_context") or meta.get("context") or "").strip() or None
    child_parent = str(meta.get("child_parent") or meta.get("parent") or "").strip() or None
    export_images = meta.get("export_images") is True or meta.get("exportImages") is True

    detected = detect_project_context(profile=profile, app_id=app_id, app_version=app_version)
    bubble_file = detected.context_path.with_name(f"{app_id}.bubble")
    if not bubble_file.exists():
        raise ValueError(f"Bubble export not found for Aria runtime: {bubble_file}")

    session = load_session(profile)
    if execute and session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")

    bubble_cli, bubble_sdk = _load_aria_runtime_modules()
    captured_payloads: list[dict[str, Any]] = []
    captured_results: list[dict[str, Any]] = []

    original_send = bubble_sdk.PayloadBuilder.send_to_webhook

    def send_to_local_bubble(builder: Any, _url: str = "") -> Any:
        write_payload = builder.build()
        captured_payloads.append(write_payload)
        if not execute:
            captured_results.append({"ok": True, "executed": False, "dry_run": True, "payload": write_payload})
            return {"ok": True, "dry_run": True}
        assert session is not None
        result = BubbleEditorClient().write(write_payload, session, dry_run=False)
        captured_results.append({"ok": bool(result.get("ok")), "executed": True, "result": result})
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or result.get("reason") or "Bubble write failed"))
        return result

    stdout = StringIO()
    stderr = StringIO()
    try:
        bubble_sdk.PayloadBuilder.send_to_webhook = send_to_local_bubble
        with redirect_stdout(stdout), redirect_stderr(stderr):
            cli = bubble_cli.BubbleCLI(
                app_json_path=str(bubble_file),
                appname=app_id,
                webhook_url="local://bubble-mcp",
                profile_name=profile,
            )
            success = cli.sync_component(
                bridge_file=str(_current_bridge_payload_path(payload)),
                element_type=element_type,
                name_override=component_name,
                dry_run=not execute,
                import_mode=import_mode,
                context=child_context,
                parent=child_parent,
                export_images=export_images,
            )
    finally:
        bubble_sdk.PayloadBuilder.send_to_webhook = original_send

    if not success:
        raise RuntimeError("Aria Figma sync runtime failed.")

    return {
        "ok": all(bool(item.get("ok")) for item in captured_results),
        "engine": "aria_runtime",
        "profile": profile,
        "app_id": app_id,
        "app_version": app_version,
        "action": payload.get("action") or "sync_component",
        "import_mode": import_mode,
        "component_name": component_name,
        "executed": execute,
        "write_count": len(captured_payloads),
        "results": [{"index": index, **item} for index, item in enumerate(captured_results, start=1)],
        "logs": "\n".join(part for part in (stdout.getvalue().strip(), stderr.getvalue().strip()) if part),
    }


_BRIDGE_PAYLOAD_PATHS: dict[int, Path] = {}


def _current_bridge_payload_path(payload: dict[str, Any]) -> Path:
    path = _BRIDGE_PAYLOAD_PATHS.get(id(payload))
    if path is None:
        raise ValueError("Bridge payload path is required for Aria runtime sync.")
    return path


def sync_component_payload(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    if not content:
        raise ValueError("Figma bridge payload is missing content.")

    profile = str(meta.get("profile") or "").strip()
    if not profile:
        raise ValueError("Figma bridge payload is missing meta.profile.")
    settings = load_settings()
    profile_config = resolve_profile(settings, profile)
    session = load_session(profile)
    app_id = str(
        meta.get("app_id")
        or meta.get("appId")
        or (session.app_id if session else "")
        or (profile_config.app_id if profile_config else "")
    ).strip()
    if not app_id:
        raise ValueError(f"No app_id found for profile '{profile}'.")
    app_version = str(
        meta.get("app_version")
        or meta.get("appVersion")
        or (session.app_version if session and session.app_version else "")
        or (profile_config.app_version if profile_config and profile_config.app_version else "")
        or "test"
    )
    execute = meta.get("dry_run") is not True
    try:
        return _sync_component_with_aria_runtime(
            payload,
            profile=profile,
            app_id=app_id,
            app_version=app_version,
            execute=execute,
        )
    except Exception:
        if str(meta.get("allow_simple_fallback") or "").lower() not in {"1", "true", "yes"}:
            raise

    component_name = _clean_name(
        meta.get("component_name") or meta.get("componentName") or content.get("name"),
        fallback="figma_component",
    )
    requested_type = str(meta.get("element_type") or meta.get("component_type") or "Group")
    element_type = "FloatingGroup" if requested_type.lower().replace(" ", "") == "floatinggroup" else "Group"
    import_mode = str(meta.get("import_mode") or meta.get("importMode") or "reusable").lower()

    payloads: list[dict[str, Any]] = []
    target_context = ""
    created_root_id = ""
    if import_mode == "reusable":
        root_payload, target_context, created_root_id = _root_reusable_payload(
            app_id=app_id,
            app_version=app_version,
            name=component_name,
            element_type=element_type,
            source_node=content,
        )
        payloads.append(root_payload)
        context_type = "reusable"
        parent_id = created_root_id
    else:
        context_name = str(meta.get("child_context") or meta.get("context") or "index")
        detected = detect_project_context(profile=profile, app_id=app_id, app_version=app_version)
        context = load_context(detected.context_path)
        target_context = context_name
        context_type = "page"
        parent_id = ""
        for node in context.nodes:
            if node.type == "page" and node.label == context_name:
                parent_id = str(node.metadata.get("root_id") or "")
                break
        if not parent_id:
            parent_id = context_name

    existing_children: list[str] = []
    for index, node in enumerate(_flatten_renderable_nodes(content), start=1):
        child_payload, child_id = _child_payload(
            app_id=app_id,
            app_version=app_version,
            node=node,
            context_key=target_context,
            context_type=context_type,
            parent_id=parent_id,
            existing_children=existing_children,
            index=index,
        )
        existing_children.append(child_id)
        payloads.append(child_payload)

    results = _execute_payloads(payloads, profile=profile, execute=execute)
    ok = all(bool(result.get("ok")) for result in results)
    return {
        "ok": ok,
        "profile": profile,
        "app_id": app_id,
        "app_version": app_version,
        "action": payload.get("action") or "sync_component",
        "import_mode": import_mode,
        "target_context": target_context,
        "created_root_id": created_root_id or None,
        "rendered_nodes": len(payloads) - (1 if import_mode == "reusable" else 0),
        "executed": execute,
        "results": results,
    }


def sync_bridge_payload_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Bridge payload file must contain a JSON object.")
    action = str(payload.get("action") or "sync_component")
    if action not in {"sync_component", "component", "unknown"}:
        raise ValueError(f"Unsupported Figma bridge action: {action}")
    _BRIDGE_PAYLOAD_PATHS[id(payload)] = path
    try:
        return sync_component_payload(payload)
    finally:
        _BRIDGE_PAYLOAD_PATHS.pop(id(payload), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bubble-mcp-figma-bridge")
    parser.add_argument("--file", required=True, help="Saved Figma bridge payload JSON.")
    args = parser.parse_args(argv)
    result = sync_bridge_payload_file(Path(args.file))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
