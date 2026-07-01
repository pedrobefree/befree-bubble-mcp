"""Tool implementations for the initial MCP server."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from bubble_mcp import __version__
from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.context.queries import search_context
from bubble_mcp.context.source import load_context
from bubble_mcp.core.config import load_settings
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.planner.deterministic import plan_message
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
                "mutations": False,
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
    raise ValueError(f"Unknown Bubble MCP tool: {name}")
