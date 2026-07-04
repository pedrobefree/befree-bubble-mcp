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
from copy import deepcopy
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


def _css_px(value: Any) -> str | None:
    try:
        number = int(round(float(value)))
    except Exception:
        return None
    if number < 0:
        return None
    return f"{number}px"


def _figma_parity_set_data_change(create_change_item: dict[str, Any], key: str, value: Any) -> dict[str, Any] | None:
    path_array = create_change_item.get("path_array")
    if not isinstance(path_array, list) or not path_array:
        return None
    return {
        "body": value,
        "path_array": [*path_array, "%p", key],
        "intent": {
            "name": "SetData",
            "id": 977,
            "source_appname": "",
        },
        "version_control_api_version": create_change_item.get("version_control_api_version", 4),
        "changelog_data": create_change_item.get("changelog_data", []),
        "session_id": create_change_item.get("session_id"),
    }


def _harden_figma_write_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Preserve Figma visual constraints that Bubble can otherwise relax.

    The packaged Aria runtime remains the source of truth for Figma conversion.
    This pass only reinforces high-signal defaults that have proven brittle in
    Bubble writes: text height must fit content, and imported image dimensions
    must keep their explicit Figma width/height as min/max CSS bounds.
    """

    hardened = deepcopy(payload)
    changes = hardened.get("changes")
    if not isinstance(changes, list):
        return hardened

    extra_changes: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        body = change.get("body")
        if not isinstance(body, dict):
            continue
        element_type = str(body.get("%x") or body.get("type") or "").strip()
        props = body.get("%p")
        if not isinstance(props, dict):
            props = {}
            body["%p"] = props

        parity_updates: dict[str, Any] = {}
        if element_type == "Text":
            parity_updates = {"fit_height": True, "single_height": False}
        elif element_type == "Image":
            width = props.get("width", props.get("%w"))
            height = props.get("height", props.get("%h"))
            width_css = _css_px(width)
            height_css = _css_px(height)
            parity_updates = {
                "fixed_width": True,
                "single_width": True,
            }
            if width_css:
                parity_updates["min_width_css"] = width_css
                parity_updates["max_width_css"] = width_css
            if height_css:
                parity_updates["fixed_height"] = True
                parity_updates["single_height"] = True
                parity_updates["min_height_css"] = height_css
                parity_updates["max_height_css"] = height_css

        for key, value in parity_updates.items():
            if props.get(key) == value:
                continue
            props[key] = value
            set_data = _figma_parity_set_data_change(change, key, value)
            if set_data is not None:
                extra_changes.append(set_data)

    if extra_changes:
        changes.extend(extra_changes)
    return hardened


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
    sync_type = str(meta.get("sync_type") or meta.get("syncType") or "").strip().lower()
    component_name = _clean_name(
        meta.get("component_name") or meta.get("componentName") or payload.get("content", {}).get("name"),
        fallback="figma_component",
    )
    element_type = str(meta.get("element_type") or meta.get("component_type") or "Group")
    import_mode = str(meta.get("import_mode") or meta.get("importMode") or "reusable").lower()
    child_context = str(meta.get("child_context") or meta.get("context") or "").strip() or None
    child_parent = str(meta.get("child_parent") or meta.get("parent") or "").strip() or None
    export_images = meta.get("export_images") is True or meta.get("exportImages") is True

    detected = detect_project_context(profile=profile, app_id=app_id, app_version=app_version, force=sync_type == "style")
    bubble_file = detected.context_path.with_name(f"{app_id}.bubble")
    if not bubble_file.exists():
        raise ValueError(f"Bubble export not found for Aria runtime: {bubble_file}")
    pruned_style_cache = _prune_stale_style_cache_for_bubble_file(bubble_file) if sync_type == "style" else []

    session = load_session(profile)
    if execute and session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")

    bubble_cli, bubble_sdk = _load_aria_runtime_modules()
    captured_payloads: list[dict[str, Any]] = []
    captured_results: list[dict[str, Any]] = []

    original_send = bubble_sdk.PayloadBuilder.send_to_webhook

    def send_to_local_bubble(builder: Any, _url: str = "") -> Any:
        write_payload = _harden_figma_write_payload(builder.build())
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
            bridge_file = str(_current_bridge_payload_path(payload))
            if sync_type == "style":
                style_element_type = str(
                    meta.get("style_type")
                    or meta.get("styleType")
                    or meta.get("element_type")
                    or meta.get("elementType")
                    or element_type
                    or "Button"
                ).strip() or "Button"
                success = cli.sync_figma_style(
                    bridge_file=bridge_file,
                    style_name=meta.get("style_name") or meta.get("styleName"),
                    element_type=style_element_type,
                    state=meta.get("style_state") or meta.get("styleState") or None,
                    text_alignment=meta.get("text_alignment") or meta.get("textAlignment"),
                    default_style=meta.get("style_default") is True or meta.get("styleDefault") is True,
                    dry_run=not execute,
                )
                action = "sync_style"
            else:
                success = cli.sync_component(
                    bridge_file=bridge_file,
                    element_type=element_type,
                    name_override=component_name,
                    dry_run=not execute,
                    import_mode=import_mode,
                    context=child_context,
                    parent=child_parent,
                    export_images=export_images,
                )
                action = payload.get("action") or "sync_component"
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
        "action": action,
        "import_mode": import_mode,
        "component_name": component_name,
        "executed": execute,
        "write_count": len(captured_payloads),
        "pruned_style_cache": pruned_style_cache,
        "results": [{"index": index, **item} for index, item in enumerate(captured_results, start=1)],
        "logs": "\n".join(part for part in (stdout.getvalue().strip(), stderr.getvalue().strip()) if part),
    }


def _prune_stale_style_cache_for_bubble_file(bubble_file: Path) -> list[str]:
    try:
        app_data = json.loads(bubble_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw_styles = app_data.get("styles")
    if not isinstance(raw_styles, dict):
        raw_styles = {}

    cache_file = bubble_file.parent / ".bubble_cli_cache.json"
    if not cache_file.exists():
        return []
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    cached_styles = cache.get("styles")
    if not isinstance(cached_styles, dict):
        return []

    removed: list[str] = []
    for style_name, style_data in list(cached_styles.items()):
        style_id = ""
        if isinstance(style_data, dict):
            style_id = str(style_data.get("id") or "").strip()
        if style_id and style_id not in raw_styles:
            removed.append(str(style_name))
            cached_styles.pop(style_name, None)

    if not removed:
        return []
    try:
        cache_file.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        return []
    return removed


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
