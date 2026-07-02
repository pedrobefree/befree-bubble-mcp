"""Tool implementations for the initial MCP server."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from bubble_mcp import __version__
from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.queries import search_context
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.config import load_settings
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.html_runtime import create_from_html_runtime
from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
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
                "aria_tool_catalog_count": len(ARIA_BUBBLE_TOOL_NAMES),
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
    if name == "bubble_context_import":
        args = arguments or {}
        context = import_context_artifact(
            Path(str(args.get("file") or "")),
            kind=str(args.get("kind") or "auto"),
        )
        output = str(args.get("output") or "").strip()
        if output:
            save_context(context, Path(output))
        return {"ok": True, "summary": context.summary(), "output": output or None}
    if name in {"bubble_context_detect", "crawl_project", "get_project_index"}:
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError(f"{name} requires a profile.")
        result = detect_project_context(
            profile=profile,
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            force=bool(args.get("force")),
            output=Path(str(args.get("output"))) if str(args.get("output") or "").strip() else None,
            bubble_file=Path(str(args.get("bubble_file"))) if str(args.get("bubble_file") or "").strip() else None,
            consolelog_file=Path(str(args.get("consolelog_file")))
            if str(args.get("consolelog_file") or "").strip()
            else None,
            include_id_to_path=not bool(args.get("skip_id_to_path")),
        )
        return result.to_dict()
    if name in {"bubble_plan", "bubble_plan_dry_run"}:
        args = arguments or {}
        plan = plan_message(
            str(args.get("message") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "index"),
        ).to_dict()
        return {"ok": True, "plan": plan, "validation": validate_plan(plan)}
    if name in {"bubble_import_html", "bubble_import_html_dry_run"}:
        args = arguments or {}
        plan = html_to_plan(
            str(args.get("html") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "index"),
        ).to_dict()
        if bool(args.get("compile")):
            app_id = str(args.get("app_id") or "").strip()
            if not app_id:
                raise ValueError("bubble_import_html compilation requires app_id.")
            plan = compile_plan_to_write_payloads(
                plan,
                app_id=app_id,
                app_version=str(args.get("app_version") or "test"),
            )
        return {"ok": True, "plan": plan, "validation": validate_plan(plan)}
    if name == "bubble_eval_run":
        args = arguments or {}
        return {
            "ok": True,
            "report": run_eval(
                Path(str(args.get("dataset") or "")),
                app_id=str(args.get("app_id") or "") or None,
                compile_plans=bool(args.get("compile")),
            ),
        }
    if name == "bubble_compile_plan":
        args = arguments or {}
        compile_plan = args.get("plan")
        if not isinstance(compile_plan, dict):
            raise ValueError("bubble_compile_plan requires a plan object.")
        app_id = str(args.get("app_id") or "").strip()
        if not app_id:
            raise ValueError("bubble_compile_plan requires app_id.")
        compile_context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            compile_context = load_context(Path(context_file))
        return {
            "ok": True,
            "plan": compile_plan_to_write_payloads(
                compile_plan,
                app_id=app_id,
                app_version=str(args.get("app_version") or "test"),
                context=compile_context,
            ),
        }
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
        execution_context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            execution_context = load_context(Path(context_file))
        return execute_plan(
            execution_plan,
            profile=profile,
            execute=bool(args.get("execute")),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            compile_missing=bool(args.get("compile")),
            context=execution_context,
        )
    if name in ARIA_BUBBLE_TOOL_NAMES:
        return call_legacy_catalog_tool(name, arguments or {})
    raise ValueError(f"Unknown Bubble MCP tool: {name}")


def call_legacy_catalog_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Handle a ported Aria Bubble MCP tool name.

    The standalone package exposes every Aria tool name. Families implemented by
    the local compiler can be compiled/executed directly. Any family can execute
    when the caller provides an exact Bubble ``write_payload``.
    """

    if name == "create_from_html":
        html_file = str(args.get("html_file") or "").strip()
        html = str(args.get("html") or "").strip()
        return create_from_html_runtime(
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or ""),
            parent=str(args.get("parent") or ""),
            html_file=html_file or None,
            html=html or None,
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            execute=bool(args.get("execute")),
            selector=str(args.get("selector") or "") or None,
            placement=str(args.get("placement") or "") or None,
            translate_to_existing_styles=bool(args.get("translate_to_existing_styles")),
            style_match_threshold=float(args.get("style_match_threshold") or 0.78),
            rendered_html=args.get("rendered_html") if isinstance(args.get("rendered_html"), bool) else None,
            strict_validate=bool(args.get("strict_validate")),
            validation_out_dir=str(args.get("validation_out_dir") or "") or None,
        )

    write_payload = args.get("write_payload") or args.get("payload")
    profile = str(args.get("profile") or "").strip()
    execute = bool(args.get("execute"))

    if isinstance(write_payload, dict):
        if not profile:
            return {
                "ok": True,
                "tool_name": name,
                "executed": False,
                "requires_profile": execute,
                "plan": {
                    "steps": [
                        {"id": "step_1", "tool_name": name, "args": {"write_payload": write_payload}}
                    ]
                },
                "validation": validate_plan(
                    {"steps": [{"id": "step_1", "tool_name": "bubble_editor_write", "args": {"write_payload": write_payload}}]}
                ),
            }
        session = load_session(profile)
        if session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        return BubbleEditorClient().write(write_payload, session, dry_run=not execute)

    app_id = str(args.get("app_id") or args.get("appname") or "").strip()
    plan = {"steps": [{"id": "step_1", "tool_name": name, "args": dict(args)}]}
    if app_id:
        context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            context = load_context(Path(context_file))
        compiled_plan = compile_plan_to_write_payloads(
            plan,
            app_id=app_id,
            app_version=str(args.get("app_version") or "test"),
            context=context,
        )
        can_execute = any(
            isinstance(step, dict)
            and isinstance(step.get("args"), dict)
            and isinstance(step["args"].get("write_payload"), dict)
            for step in compiled_plan.get("steps", [])
        )
        if profile and can_execute:
            return execute_plan(
                compiled_plan,
                profile=profile,
                execute=execute,
                app_id=app_id,
                app_version=str(args.get("app_version") or "test"),
            )
        return {
            "ok": can_execute,
            "tool_name": name,
            "compiled": can_execute,
            "executed": False,
            "plan": compiled_plan,
            "validation": validate_plan(compiled_plan),
        }

    return {
        "ok": False,
        "tool_name": name,
        "compiled": False,
        "executed": False,
        "error": "This tool is exposed from the full Aria catalog, but standalone execution requires app_id for compiler support or write_payload for exact execution.",
        "plan": plan,
    }
