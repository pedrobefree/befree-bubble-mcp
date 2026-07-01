"""Tool implementations for the initial MCP server."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from bubble_mcp import __version__
from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.context.queries import search_context
from bubble_mcp.context.source import load_context
from bubble_mcp.core.config import load_settings
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.sessions.store import list_sessions, load_session, save_session, session_from_payload
from bubble_mcp.validators.semantic import validate_plan


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a supported tool and return a JSON-serializable payload."""

    _ = arguments or {}
    if name == "bubble_health_check":
        return {
            "ok": True,
            "version": __version__,
            "capabilities": {
                "profiles": True,
                "session_capture": "manual-interface",
                "context_engine": True,
                "planner": True,
                "html_import": True,
                "evals": True,
                "mutations": True,
                "dry_run": "optional",
                "figma_bridge": True,
                "figma_plugin": False,
            },
        }
    if name == "bubble_profile_list":
        settings = load_settings()
        return {
            "ok": True,
            "default_profile": settings.default_profile,
            "profiles": [
                {
                    "name": profile.name,
                    "app_id": profile.app_id,
                    "appname": profile.appname,
                    "editor_url": profile.editor_url,
                }
                for profile in settings.profiles.values()
            ],
        }
    if name == "bubble_context_summary":
        context = load_context(Path(str((arguments or {}).get("file") or "")))
        return {"ok": True, "summary": context.summary()}
    if name == "bubble_context_find":
        args = arguments or {}
        context = load_context(Path(str(args.get("file") or "")))
        return {
            "ok": True,
            "results": search_context(context, str(args.get("query") or ""), int(args.get("limit") or 10)),
        }
    if name == "bubble_plan_dry_run":
        args = arguments or {}
        plan = plan_message(
            str(args.get("message") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "index"),
        ).to_dict()
        return {"ok": True, "plan": plan, "validation": validate_plan(plan)}
    if name == "bubble_import_html_dry_run":
        args = arguments or {}
        plan = html_to_plan(
            str(args.get("html") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "index"),
        ).to_dict()
        return {"ok": True, "plan": plan, "validation": validate_plan(plan)}
    if name == "bubble_eval_run":
        args = arguments or {}
        return {"ok": True, "report": run_eval(Path(str(args.get("dataset") or "")))}
    if name == "bubble_session_list":
        return {"ok": True, "sessions": list_sessions()}
    if name == "bubble_session_import":
        args = arguments or {}
        raw_session = args.get("session")
        if not isinstance(raw_session, dict):
            raise ValueError("bubble_session_import requires a session object.")
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_session_import requires a profile.")
        imported_session = session_from_payload(
            raw_session,
            default_app_id=str(args.get("app_id") or "") or None,
        )
        path = save_session(profile, imported_session)
        return {
            "ok": True,
            "profile": profile,
            "path": str(path),
            "session": imported_session.to_dict(redact=True),
        }
    if name == "bubble_editor_write":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_editor_write requires a profile.")
        write_payload = args.get("payload")
        if not isinstance(write_payload, dict):
            raise ValueError("bubble_editor_write requires a payload object.")
        write_session = load_session(profile)
        if write_session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        execute = bool(args.get("execute"))
        return BubbleEditorClient().write(write_payload, write_session, dry_run=not execute)
    if name == "bubble_execute_plan":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_execute_plan requires a profile.")
        execution_plan = args.get("plan")
        if not isinstance(execution_plan, dict):
            raise ValueError("bubble_execute_plan requires a plan object.")
        return execute_plan(execution_plan, profile=profile, execute=bool(args.get("execute")))
    raise ValueError(f"Unknown Bubble MCP tool: {name}")
