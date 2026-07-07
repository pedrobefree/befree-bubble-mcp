"""Dispatch standalone MCP catalog calls through Aria's Bubble runtime."""

from __future__ import annotations

import importlib
import inspect
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, cast

from bubble_mcp.context.detector import default_bubble_export_path, detect_project_context
from bubble_mcp.context.mutation_overlay import mutation_overlay_path, record_mutation_overlay
from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.sessions.store import load_session


CONTROL_ARG_KEYS = {
    "profile",
    "app_id",
    "appname",
    "app_version",
    "execute",
    "dry_run",
    "settings_path",
    "context_file",
    "write_payload",
    "payload",
    "refresh_context",
    "force",
    "bubble_file",
    "app_json_path",
    "consolelog_file",
    "crawler_index_path",
    "mutation_overlay_path",
}

ARG_ALIASES = {
    "context_name": ("context",),
    "parent_name": ("parent",),
    "filter_text": ("query",),
    "html_file": ("file",),
    "file_path": ("file", "input"),
    "as_json": ("json",),
    "search_text": ("element_name", "name", "text"),
    "new_text": ("content", "new_content", "text"),
    "name": ("element_name",),
    "property_name": ("property",),
    "condition_json": ("only_when_json", "condition"),
    "query": ("message", "commands"),
    "icon_name": ("icon",),
    "source": ("image_url", "url"),
    "data_type_key": ("data_type_ref", "data_type"),
    "field_name": ("name",),
    "field_type": ("type",),
    "option_set_key": ("option_set_ref",),
    "rgba": ("value", "color"),
    "event_type": ("event",),
}

RUNTIME_TOOL_ALIASES = {
    "sync_cache": "refresh_profile_cache",
    "list_events": "list_workflow_events",
    "scan_types": "list_data_types",
    "update_layout": "update_layout_property",
    "edit_style": "update_style_definition",
    "map_element_ref": "map_element_ref_alias",
    "map_workflow_ref": "map_workflow_ref_alias",
    "add_event_go_to_page": "add_event_go_to_page_action",
    "set_condition_run_when": "set_condition_event_run_when",
    "set_condition_only_when": "set_condition_event_only_when",
    "batch": "process_batch",
    "natural": "process_natural_language",
    "regenerate_api_token": "regenerate_api_token_private_key",
}

CUSTOM_RUNTIME_TOOLS = {"list_element_ref_maps"}

MUTATING_PREFIXES = (
    "add_",
    "assign_",
    "create_",
    "delete_",
    "import_",
    "move_",
    "replace_",
    "set_",
    "sync_",
    "update_",
)


def _requires_calculate_derived(tool_name: str) -> bool:
    """Return true for schema writes that Bubble finalizes through calculate_derived."""
    return tool_name in {
        "delete_data_field",
        "create_privacy_rule",
        "delete_privacy_rule",
        "set_privacy_rule_name",
        "set_privacy_rule_condition",
        "set_privacy_rule_permission",
        "set_privacy_rule_field_visibility",
        "set_privacy_rule_auto_binding",
    }


@dataclass(frozen=True)
class AriaRuntimeEnvironment:
    profile: str
    app_id: str
    app_version: str
    app_json_path: str | None
    consolelog_json_path: str | None
    crawler_index_path: str | None
    mutation_overlay_path: str | None


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
    setattr(bubble_cli, "inquirer", _FakeInquirer())
    return bubble_cli, bubble_sdk


def _resolve_optional_path(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _resolve_runtime_environment(args: dict[str, Any]) -> AriaRuntimeEnvironment:
    profile = str(args.get("profile") or "").strip()
    if not profile:
        raise ValueError("Aria runtime dispatch requires profile.")

    settings = load_settings()
    profile_config = resolve_profile(settings, profile)
    session = load_session(profile)
    app_id = str(
        args.get("app_id")
        or args.get("appname")
        or (session.app_id if session else "")
        or (profile_config.app_id if profile_config else "")
    ).strip()
    if not app_id:
        raise ValueError(f"No Bubble app_id found for profile '{profile}'.")

    app_version = str(
        args.get("app_version")
        or (session.app_version if session and session.app_version else "")
        or (profile_config.app_version if profile_config and profile_config.app_version else "")
        or "test"
    )

    explicit_bubble_file = _resolve_optional_path(args.get("bubble_file") or args.get("app_json_path"))
    app_json_path = explicit_bubble_file or (profile_config.app_json_path if profile_config else None)
    default_export = default_bubble_export_path(profile, app_id)
    if not app_json_path and default_export.exists():
        app_json_path = str(default_export)

    should_detect = bool(args.get("refresh_context") or args.get("force")) or not (
        app_json_path and Path(app_json_path).expanduser().exists()
    )
    if should_detect:
        detected = detect_project_context(
            profile=profile,
            app_id=app_id,
            app_version=app_version,
            force=bool(args.get("refresh_context") or args.get("force")),
            bubble_file=Path(explicit_bubble_file).expanduser() if explicit_bubble_file else None,
            consolelog_file=Path(str(args.get("consolelog_file"))).expanduser()
            if str(args.get("consolelog_file") or "").strip()
            else None,
        )
        candidate = default_bubble_export_path(profile, app_id)
        if candidate.exists():
            app_json_path = str(candidate)
        elif detected.source.endswith("bubble") and Path(detected.context_path).exists():
            app_json_path = app_json_path

    if not app_json_path and not args.get("consolelog_file") and not args.get("crawler_index_path"):
        raise ValueError(
            "Aria runtime dispatch requires a .bubble export, consolelog JSON, or crawler index. "
            "Run bubble-mcp context detect for this profile first."
        )

    return AriaRuntimeEnvironment(
        profile=profile,
        app_id=app_id,
        app_version=app_version,
        app_json_path=app_json_path,
        consolelog_json_path=_resolve_optional_path(args.get("consolelog_file")),
        crawler_index_path=_resolve_optional_path(args.get("crawler_index_path")),
        mutation_overlay_path=_resolve_optional_path(args.get("mutation_overlay_path"))
        or str(mutation_overlay_path(profile, app_id)),
    )


def _method_kwargs(method: Any, args: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    signature = inspect.signature(method)
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
    kwargs: dict[str, Any] = {}

    for name, param in signature.parameters.items():
        if name == "self" or param.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        if name == "dry_run":
            kwargs[name] = not execute
            continue
        if name in args:
            kwargs[name] = args[name]
            continue
        aliases = ARG_ALIASES.get(name, ())
        for alias in aliases:
            if alias in args:
                kwargs[name] = args[alias]
                break

    if accepts_kwargs:
        for key, value in args.items():
            if key in CONTROL_ARG_KEYS or key in kwargs:
                continue
            if key == "context":
                continue
            if key == "parent":
                continue
            kwargs.setdefault(key, value)

    if method.__name__ == "add_event_go_to_page_action" and args.get("same_tab") is True:
        kwargs["open_in_new_tab"] = False
    if method.__name__ == "delete_data_field" and "field_key" not in kwargs:
        raw_field_ref = args.get("name") or args.get("field_name")
        if raw_field_ref is not None:
            kwargs["field_key"] = raw_field_ref

    if "dry_run" in signature.parameters:
        kwargs["dry_run"] = not execute
    return kwargs


def _list_element_ref_maps(cli: Any, args: dict[str, Any]) -> dict[str, Any]:
    context_name = str(args.get("context") or "").strip()
    rows: list[dict[str, Any]] = []
    cache = cli._schema_element_refs_cache()
    if context_name:
        context_id, context_type = cli._find_context(context_name)
        if not context_id:
            return {"ok": False, "error": f"Context '{context_name}' not found.", "rows": []}
        context_keys = [cli._cache_element_ref_context_key(context_id, context_type)]
    else:
        context_keys = sorted(cache)

    for context_key in context_keys:
        bucket = cache.get(context_key)
        if not isinstance(bucket, dict):
            continue
        for alias_key, payload in sorted(bucket.items()):
            if not isinstance(payload, dict):
                continue
            row = dict(payload)
            row.setdefault("alias_key", alias_key)
            row.setdefault("context_key", context_key)
            rows.append(row)
    limit = args.get("limit")
    if isinstance(limit, int) and limit > 0:
        rows = rows[:limit]
    return {"ok": True, "rows": rows, "count": len(rows)}


def _call_custom_runtime_tool(name: str, cli: Any, args: dict[str, Any]) -> dict[str, Any] | None:
    if name == "list_element_ref_maps":
        return _list_element_ref_maps(cli, args)
    return None


def dispatch_aria_runtime_tool(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Execute an Aria BubbleCLI method when the standalone catalog tool maps to one."""

    profile = str(args.get("profile") or "").strip()
    if not profile:
        return None

    bubble_cli, bubble_sdk = _load_aria_runtime_modules()
    method_name = RUNTIME_TOOL_ALIASES.get(name, name)
    has_runtime_method = hasattr(bubble_cli.BubbleCLI, method_name)
    if not has_runtime_method and name not in CUSTOM_RUNTIME_TOOLS:
        return None
    signature = inspect.signature(getattr(bubble_cli.BubbleCLI, method_name)) if has_runtime_method else None
    if (
        signature is not None
        and not bool(args.get("execute"))
        and name.startswith(MUTATING_PREFIXES)
        and "dry_run" not in signature.parameters
    ):
        return None

    execute = bool(args.get("execute")) and not bool(args.get("dry_run"))
    session = load_session(profile)
    if execute and session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")

    env = _resolve_runtime_environment(args)
    captured_payloads: list[dict[str, Any]] = []
    captured_results: list[dict[str, Any]] = []
    captured_builder_ids: set[int] = set()
    original_builder_init = bubble_sdk.PayloadBuilder.__init__
    builder_init_signature = inspect.signature(original_builder_init)
    builder_accepts_app_version = "app_version" in builder_init_signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in builder_init_signature.parameters.values()
    )
    original_send = bubble_sdk.PayloadBuilder.send_to_webhook
    original_to_json = bubble_sdk.PayloadBuilder.to_json

    def init_builder_with_target_version(builder: Any, *init_args: Any, **init_kwargs: Any) -> None:
        if (
            builder_accepts_app_version
            and len(init_args) < 2
            and not str(init_kwargs.get("app_version") or "").strip()
        ):
            init_kwargs["app_version"] = env.app_version
        original_builder_init(builder, *init_args, **init_kwargs)

    def capture_payload(builder: Any) -> dict[str, Any]:
        builder_id = id(builder)
        write_payload = cast("dict[str, Any]", builder.build())
        write_payload["app_version"] = env.app_version
        if builder_id not in captured_builder_ids:
            captured_builder_ids.add(builder_id)
            captured_payloads.append(write_payload)
        return write_payload

    def send_to_local_bubble(builder: Any, _url: str = "") -> Any:
        write_payload = capture_payload(builder)
        if not execute:
            result = {"ok": True, "dry_run": True, "payload": write_payload}
            captured_results.append({"ok": True, "executed": False, "dry_run": True, "payload": write_payload})
            return result
        assert session is not None
        result = BubbleEditorClient().write(
            write_payload,
            session,
            dry_run=False,
            calculate_derived=_requires_calculate_derived(name),
        )
        captured_results.append({"ok": bool(result.get("ok")), "executed": True, "result": result})
        if result.get("ok"):
            request = result.get("request")
            request_payload = request.get("payload") if isinstance(request, dict) else None
            overlay_payload = request_payload if isinstance(request_payload, dict) else write_payload
            record_mutation_overlay(
                profile=profile,
                app_id=str(overlay_payload.get("appname") or env.app_id),
                payload=overlay_payload,
                source=name,
                response=result.get("response"),
            )
            return result
        raise RuntimeError(str(result.get("error") or result.get("reason") or "Bubble write failed"))

    def to_json_with_capture(builder: Any) -> str:
        write_payload = capture_payload(builder)
        if not execute:
            captured_results.append({"ok": True, "executed": False, "dry_run": True, "payload": write_payload})
        return cast(str, original_to_json(builder))

    stdout = StringIO()
    stderr = StringIO()
    return_value: Any = None
    try:
        bubble_sdk.PayloadBuilder.__init__ = init_builder_with_target_version
        bubble_sdk.PayloadBuilder.send_to_webhook = send_to_local_bubble
        bubble_sdk.PayloadBuilder.to_json = to_json_with_capture
        with redirect_stdout(stdout), redirect_stderr(stderr):
            cli = bubble_cli.BubbleCLI(
                app_json_path=env.app_json_path,
                consolelog_json_path=env.consolelog_json_path,
                crawler_index_path=env.crawler_index_path,
                mutation_overlay_path=env.mutation_overlay_path,
                appname=env.app_id,
                webhook_url="local://bubble-mcp",
                profile_name=env.profile,
            )
            custom_return = _call_custom_runtime_tool(name, cli, args)
            if custom_return is not None:
                return_value = custom_return
            elif name == "batch" and isinstance(args.get("commands"), list):
                return_value = cli.execute_commands(args["commands"], dry_run=not execute)
            else:
                method = getattr(cli, method_name)
                return_value = method(**_method_kwargs(method, args, execute=execute))
    finally:
        bubble_sdk.PayloadBuilder.__init__ = original_builder_init
        bubble_sdk.PayloadBuilder.send_to_webhook = original_send
        bubble_sdk.PayloadBuilder.to_json = original_to_json

    logs = "\n".join(part for part in (stdout.getvalue().strip(), stderr.getvalue().strip()) if part)
    ok = bool(return_value) if captured_results else return_value is not False
    if captured_results:
        ok = all(bool(item.get("ok")) for item in captured_results)
    return {
        "ok": ok,
        "engine": "aria_runtime",
        "tool_name": name,
        "profile": profile,
        "app_id": env.app_id,
        "app_version": env.app_version,
        "executed": execute,
        "compiled": bool(captured_payloads),
        "write_count": len(captured_payloads),
        "return_value": return_value,
        "results": [{"index": index, **item} for index, item in enumerate(captured_results, start=1)],
        "logs": logs,
    }
