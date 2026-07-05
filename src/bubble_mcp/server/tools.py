"""Tool implementations for the initial MCP server."""

from __future__ import annotations

from typing import Any
from pathlib import Path

from bubble_mcp import __version__
from bubble_mcp.aria_dispatch import dispatch_aria_runtime_tool
from bubble_mcp.catalog_quality import catalog_quality_report
from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.context.queries import context_find_payload
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.config import BubbleProfile, load_settings, resolve_profile, save_settings, with_profile
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.execution.client import BubbleEditorClient, build_editor_write_headers
from bubble_mcp.execution.editor_api import (
    create_bubble_branch,
    delete_bubble_branch,
    fetch_changelog_entries,
    list_branch_contributors,
    list_bubble_branches,
)
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.execution.state import next_user_action, operation_snapshot
from bubble_mcp.execution.structural import validate_structure
from bubble_mcp.extensions.store import (
    disable_extension,
    enable_extension,
    import_extension,
    list_extensions,
)
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.harness.expert import export_expert_eval_cases
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.harness.visual import compare_visual_snapshot_files
from bubble_mcp.harness.visual_audit import audit_visual_from_inputs
from bubble_mcp.harness.visual_bubble import capture_bubble_visual_snapshot
from bubble_mcp.harness.visual_capture import capture_visual_snapshot
from bubble_mcp.html_runtime import create_from_html_runtime
from bubble_mcp.knowledge.cache import fetch_knowledge_record, import_knowledge_records, knowledge_search
from bubble_mcp.learning.store import append_learning_record, list_learning_records
from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.profile_status import profile_status
from bubble_mcp.readiness import run_readiness_check
from bubble_mcp.runtime_coverage import catalog_coverage_report
from bubble_mcp.runtime_smoke import run_runtime_smoke
from bubble_mcp.server.agent_guide import agent_guide, search_tool_catalog, task_recipe, task_runbook
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.skills.validator import describe_skill_file, validate_skill_file
from bubble_mcp.sessions.browser import capture_session_with_playwright
from bubble_mcp.sessions.store import list_sessions, load_session, save_session, session_from_payload
from bubble_mcp.tool_authoring.sessions import (
    append_capture_to_authoring_session,
    create_authoring_session,
    describe_authoring_session,
)
from bubble_mcp.validators.semantic import validate_plan


def _required_string_arg(arguments: dict[str, Any] | None, key: str, tool_name: str) -> str:
    value = str((arguments or {}).get(key) or "").strip()
    if not value:
        raise ValueError(f"{tool_name} requires {key}.")
    return value


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
                "aria_runtime_dispatch": True,
                "aria_tool_catalog_count": len(ARIA_BUBBLE_TOOL_NAMES),
            },
        }
    if name == "bubble_tool_coverage":
        args = arguments or {}
        return catalog_coverage_report(include_tools=bool(args.get("include_tools") or args.get("include_details")))
    if name == "bubble_catalog_quality":
        return catalog_quality_report()
    if name == "bubble_extension_list":
        return {"ok": True, "extensions": [item.to_dict() for item in list_extensions()]}
    if name == "bubble_extension_validate":
        path = _required_string_arg(arguments, "path", name)
        return validate_extension_pack(Path(path)).to_dict()
    if name == "bubble_extension_import":
        path = _required_string_arg(arguments, "path", name)
        return import_extension(Path(path)).to_dict()
    if name == "bubble_extension_enable":
        extension_id = _required_string_arg(arguments, "extension_id", name)
        return enable_extension(extension_id).to_dict()
    if name == "bubble_extension_disable":
        extension_id = _required_string_arg(arguments, "extension_id", name)
        return disable_extension(extension_id).to_dict()
    if name == "bubble_skill_validate":
        path = _required_string_arg(arguments, "path", name)
        return validate_skill_file(Path(path))
    if name == "bubble_skill_describe":
        path = _required_string_arg(arguments, "path", name)
        return describe_skill_file(Path(path))
    if name == "bubble_tool_wizard_start":
        args = arguments or {}
        session = create_authoring_session(
            intent=_required_string_arg(args, "intent", name),
            target=_required_string_arg(args, "target", name),
            profile=_required_string_arg(args, "profile", name),
        )
        return {"ok": True, "session": session.to_dict()}
    if name == "bubble_tool_wizard_add_capture":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        file_path = _required_string_arg(args, "file", name)
        return append_capture_to_authoring_session(session_id, Path(file_path))
    if name == "bubble_tool_wizard_describe":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        return describe_authoring_session(session_id)
    if name == "bubble_learning_record":
        args = arguments or {}
        value = args.get("value")
        if value is not None and not isinstance(value, dict):
            raise ValueError("bubble_learning_record requires value to be a JSON object.")
        record = append_learning_record(
            scope=str(args.get("scope") or ""),
            key=str(args.get("key") or ""),
            value=value,
            source=str(args.get("source") or ""),
            confidence=str(args.get("confidence") or ""),
            profile=str(args.get("profile") or "") or None,
            project=str(args.get("project") or "") or None,
            extension_id=str(args.get("extension_id") or "") or None,
        )
        return {"ok": True, "record": record.to_dict()}
    if name == "bubble_learning_list":
        args = arguments or {}
        return {
            "ok": True,
            "records": [
                record.to_dict()
                for record in list_learning_records(
                    scope=str(args.get("scope") or "") or None,
                    profile=str(args.get("profile") or "") or None,
                    project=str(args.get("project") or "") or None,
                    extension_id=str(args.get("extension_id") or "") or None,
                )
            ],
        }
    if name == "bubble_knowledge_refresh_source":
        args = arguments or {}
        source = _required_string_arg(args, "source", name)
        file_path = _required_string_arg(args, "file", name)
        return import_knowledge_records(Path(file_path), source=source)
    if name == "bubble_knowledge_search":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        return knowledge_search(query, limit=int(args.get("limit") or 8))
    if name == "bubble_knowledge_fetch":
        args = arguments or {}
        record_id = _required_string_arg(args, "record_id", name)
        return fetch_knowledge_record(record_id)
    if name == "bubble_manual_guidance":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        result = knowledge_search(query, limit=int(args.get("limit") or 5))
        return {
            **result,
            "purpose": "manual_guidance",
            "cache_only": True,
            "remote_docs": "disabled",
        }
    if name == "bubble_manual_context_for_tool_authoring":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        result = knowledge_search(query, limit=int(args.get("limit") or 5))
        return {
            **result,
            "purpose": "tool_authoring",
            "cache_only": True,
            "remote_docs": "disabled",
        }
    if name == "bubble_manual_context_for_validation":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        result = knowledge_search(query, limit=int(args.get("limit") or 5))
        return {
            **result,
            "purpose": "validation",
            "cache_only": True,
            "remote_docs": "disabled",
        }
    if name == "bubble_readiness_check":
        args = arguments or {}
        return run_readiness_check(
            call_tool,
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "root"),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            max_age_hours=int(args.get("max_age_hours") or 24),
            include_family_preview=bool(args.get("include_family_preview")),
            include_details=bool(args.get("include_details")),
            stop_on_failure=bool(args.get("stop_on_failure")),
        )
    if name == "bubble_agent_guide":
        return agent_guide(str((arguments or {}).get("task") or (arguments or {}).get("message") or ""))
    if name == "bubble_tool_search":
        args = arguments or {}
        return search_tool_catalog(str(args.get("query") or ""), limit=int(args.get("limit") or 8))
    if name == "bubble_task_recipe":
        args = arguments or {}
        return task_recipe(
            str(args.get("task") or args.get("message") or ""),
            recipe=str(args.get("recipe") or ""),
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or ""),
            parent=str(args.get("parent") or "root"),
            execute=bool(args.get("execute")),
        )
    if name == "bubble_task_runbook":
        args = arguments or {}
        return task_runbook(
            str(args.get("task") or args.get("message") or ""),
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or ""),
            parent=str(args.get("parent") or "root"),
            execute=bool(args.get("execute")),
            search_limit=int(args.get("search_limit") or args.get("limit") or 6),
            include_profile_status=bool(args.get("include_profile_status")),
        )
    if name == "bubble_runtime_smoke":
        args = arguments or {}
        return run_runtime_smoke(
            call_tool,
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "root"),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            suite=str(args.get("suite") or "coverage"),
            limit=int(args.get("limit") or 0),
            html_url=str(args.get("html_url") or args.get("url") or ""),
            selector=str(args.get("selector") or ""),
            include_details=bool(args.get("include_details")),
            stop_on_failure=bool(args.get("stop_on_failure")),
            execute=bool(args.get("execute")),
            cleanup=bool(args.get("cleanup")),
            run_id=str(args.get("run_id") or ""),
            verify_context=bool(args.get("verify_context")),
            verification_output=str(args.get("verification_output") or ""),
        )
    if name == "bubble_project_bootstrap":
        args = arguments or {}
        profile_name = str(args.get("profile") or args.get("name") or "").strip()
        if not profile_name:
            raise ValueError("bubble_project_bootstrap requires profile.")
        settings = load_settings()
        existing_profile = resolve_profile(settings, profile_name)
        app_id = str(args.get("app_id") or (existing_profile.app_id if existing_profile else "")).strip()
        if app_id:
            updated_profile = BubbleProfile(
                name=profile_name,
                app_id=app_id,
                appname=str(args.get("appname") or (existing_profile.appname if existing_profile else app_id)).strip()
                or app_id,
                editor_url=str(
                    args.get("editor_url") or (existing_profile.editor_url if existing_profile else "")
                ).strip()
                or None,
                app_version=str(
                    args.get("app_version") or (existing_profile.app_version if existing_profile else "test")
                ).strip()
                or None,
                app_json_path=str(
                    args.get("app_json_path") or (existing_profile.app_json_path if existing_profile else "")
                ).strip()
                or None,
                consolelog_json_path=str(
                    args.get("consolelog_json_path")
                    or (existing_profile.consolelog_json_path if existing_profile else "")
                ).strip()
                or None,
            )
            save_settings(with_profile(settings, updated_profile))

        context_detection: dict[str, Any] | None = None
        if bool(args.get("detect_context")) and app_id:
            try:
                detection_result = detect_project_context(
                    profile=profile_name,
                    app_id=app_id,
                    app_version=str(args.get("app_version") or "test"),
                    force=bool(args.get("force_context")),
                )
                context_detection = detection_result.to_dict()
            except Exception as exc:
                context_detection = {"ok": False, "error": str(exc)}

        status = profile_status(
            profile_name,
            max_age_hours=int(args.get("max_age_hours") or 24),
        )
        profile_changed = bool(app_id) and (
            existing_profile is None
            or existing_profile.app_id != app_id
            or bool(
                args.get("appname")
                or args.get("editor_url")
                or args.get("app_version")
                or args.get("app_json_path")
                or args.get("consolelog_json_path")
            )
        )
        return {
            "ok": bool(status.get("ok")),
            "profile": profile_name,
            "profile_changed": profile_changed,
            "context_detection": context_detection,
            "ready": bool(status.get("ready")),
            "next_actions": status.get("next_actions", []),
            "status": status,
        }
    if name == "bubble_profile_add":
        args = arguments or {}
        profile_name = str(args.get("name") or args.get("profile") or "").strip()
        app_id = str(args.get("app_id") or "").strip()
        if not profile_name:
            raise ValueError("bubble_profile_add requires name.")
        if not app_id:
            raise ValueError("bubble_profile_add requires app_id.")
        settings = load_settings()
        new_profile = BubbleProfile(
            name=profile_name,
            app_id=app_id,
            appname=str(args.get("appname") or app_id).strip() or app_id,
            editor_url=str(args.get("editor_url") or "").strip() or None,
            app_version=str(args.get("app_version") or "test").strip() or None,
            app_json_path=str(args.get("app_json_path") or "").strip() or None,
            consolelog_json_path=str(args.get("consolelog_json_path") or "").strip() or None,
        )
        save_settings(with_profile(settings, new_profile))
        return {
            "ok": True,
            "profile": new_profile.name,
            "app_id": new_profile.app_id,
            "settings": str(settings.config_dir / "settings.json"),
        }
    if name == "bubble_profile_list":
        settings = load_settings()
        return {
            "ok": True,
            "default_profile": settings.default_profile,
            "profiles": [
                {
                    "name": profile_item.name,
                    "app_id": profile_item.app_id,
                    "appname": profile_item.appname,
                    "editor_url": profile_item.editor_url,
                }
                for profile_item in settings.profiles.values()
            ],
        }
    if name == "bubble_profile_status":
        args = arguments or {}
        return profile_status(
            str(args.get("profile") or ""),
            max_age_hours=int(args.get("max_age_hours") or 24),
        )
    if name == "bubble_context_summary":
        path = Path(str((arguments or {}).get("file") or ""))
        context = load_context(path)
        return {"ok": True, "summary": context.summary(), "freshness": context_freshness(context, path=path)}
    if name == "bubble_context_find":
        args = arguments or {}
        profile_name = str(args.get("profile") or "").strip()
        if args.get("file"):
            context = load_context(Path(str(args.get("file") or "")))
        else:
            settings = load_settings()
            resolved_profile = resolve_profile(settings, profile_name or None)
            if resolved_profile is None:
                return {
                    "ok": False,
                    "error": "profile_required",
                    "message": "Provide file or a configured profile to search project context.",
                }
            status = profile_status(resolved_profile.name)
            raw_context_status = status.get("context")
            context_status = raw_context_status if isinstance(raw_context_status, dict) else {}
            context_path = str(context_status.get("path") or "").strip()
            if not context_path or not Path(context_path).exists():
                return {
                    "ok": False,
                    "error": "context_missing",
                    "profile": resolved_profile.name,
                    "next_actions": status.get("next_actions", []),
                }
            context = load_context_with_overlay(
                Path(context_path),
                profile=resolved_profile.name,
                app_id=resolved_profile.app_id,
            )
        return {
            "ok": True,
            **({"profile": profile_name} if profile_name and args.get("file") else {}),
            **context_find_payload(
                context,
                str(args.get("query") or ""),
                int(args.get("limit") or 10),
                exact=bool(args.get("exact")),
                include_metadata=bool(args.get("include_metadata", True)),
            ),
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
        validation = validate_plan(plan)
        structural_validation = validate_structure(plan, execute=False)
        return {
            "ok": True,
            "plan": plan,
            "validation": validation,
            "structural_validation": structural_validation,
            "next_user_action": next_user_action(structural_validation),
            "operation_snapshot": operation_snapshot(
                plan=plan,
                validation=structural_validation,
                execute=False,
                phase="planned",
            ),
        }
    if name == "bubble_eval_run":
        args = arguments or {}
        offset_value = str(args.get("offset") or "").strip()
        limit_value = str(args.get("limit") or "").strip()
        failed_from_value = str(args.get("failed_from") or "").strip()
        return {
            "ok": True,
            "report": run_eval(
                Path(str(args.get("dataset") or "")),
                app_id=str(args.get("app_id") or "") or None,
                compile_plans=bool(args.get("compile")),
                case_filter=args.get("filter") or args.get("case_filter") or None,
                failed_from=Path(failed_from_value) if failed_from_value else None,
                offset=int(offset_value) if offset_value else 0,
                limit=int(limit_value) if limit_value else None,
            ),
        }
    if name == "bubble_eval_export_expert":
        args = arguments or {}
        return export_expert_eval_cases(
            Path(str(args.get("input") or "")),
            Path(str(args.get("output") or "")),
            limit=int(args.get("limit") or 250),
        )
    if name == "bubble_visual_compare":
        args = arguments or {}
        return compare_visual_snapshot_files(
            Path(str(args.get("reference") or "")),
            Path(str(args.get("actual") or "")),
            tolerance_px=float(args.get("tolerance_px") or 4),
            tolerance_ratio=float(args.get("tolerance_ratio") or 0.08),
            require_text=bool(args.get("require_text", True)),
            require_images=bool(args.get("require_images")),
        )
    if name == "bubble_visual_audit":
        return audit_visual_from_inputs(arguments or {})
    if name == "bubble_visual_capture":
        args = arguments or {}
        output_value = str(args.get("output") or "").strip()
        return capture_visual_snapshot(
            str(args.get("source") or ""),
            selector=str(args.get("selector") or ""),
            rendered_html=bool(args.get("rendered_html", True)),
            viewport_width=int(args.get("viewport_width") or 1365),
            viewport_height=int(args.get("viewport_height") or 768),
            wait_ms=int(args.get("wait_ms") or 0),
            selector_timeout_ms=int(args.get("selector_timeout_ms") or 5000),
            max_nodes=int(args.get("max_nodes") or 250),
            allow_raw_fallback=bool(args.get("allow_raw_fallback", True)),
            output=Path(output_value) if output_value else None,
        )
    if name == "bubble_visual_capture_actual":
        args = arguments or {}
        output_value = str(args.get("output") or "").strip()
        raw_query = args.get("url_query") or args.get("query")
        query = {str(key): str(value) for key, value in raw_query.items()} if isinstance(raw_query, dict) else {}
        return capture_bubble_visual_snapshot(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            page=str(args.get("page") or args.get("context") or "index"),
            selector=str(args.get("selector") or ""),
            public_base_url=str(args.get("public_base_url") or ""),
            url=str(args.get("url") or ""),
            query=query,
            viewport_width=int(args.get("viewport_width") or 1365),
            viewport_height=int(args.get("viewport_height") or 768),
            wait_ms=int(args.get("wait_ms") or 1000),
            selector_timeout_ms=int(args.get("selector_timeout_ms") or 10000),
            max_nodes=int(args.get("max_nodes") or 250),
            output=Path(output_value) if output_value else None,
        )
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
            compile_context = load_context_with_overlay(
                Path(context_file),
                profile=str(args.get("profile") or "") or None,
                app_id=app_id,
            )
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
    if name == "bubble_session_inspect":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_session_inspect requires a profile.")
        inspected_session = load_session(profile)
        if inspected_session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        app_id = str(args.get("app_id") or inspected_session.app_id or "").strip()
        sample_payload: dict[str, Any] = {
            "appname": app_id,
            "app_version": inspected_session.app_version or "test",
            "changes": [],
        }
        write_headers = build_editor_write_headers(inspected_session, sample_payload)
        return {
            "ok": True,
            "profile": profile,
            "session": inspected_session.to_dict(redact=True),
            "stored_header_keys": sorted(inspected_session.headers.keys()),
            "session_auth_present": bool(inspected_session.cookies),
            "session_auth_value_length": len(inspected_session.cookies or ""),
            "computed_write_header_keys": sorted(write_headers.keys()),
            "computed_write_headers": redact_sensitive(write_headers),
        }
    if name == "bubble_session_login":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_session_login requires a profile.")
        settings = load_settings()
        configured_profile = resolve_profile(settings, profile)
        app_id = str(args.get("app_id") or (configured_profile.app_id if configured_profile else "")).strip()
        if not app_id:
            raise ValueError("bubble_session_login requires app_id when the profile is not configured.")
        app_version = str(
            args.get("app_version") or (configured_profile.app_version if configured_profile else "test")
        ).strip() or "test"
        progress_messages: list[str] = []

        def collect_progress(message: str) -> None:
            progress_messages.append(message)

        session = capture_session_with_playwright(
            app_id=app_id,
            editor_url=str(args.get("editor_url") or "").strip() or None,
            headless=bool(args.get("headless")),
            wait_seconds=int(args.get("wait_seconds") or 180),
            user_data_dir=settings.config_dir / "browser-profiles" / profile,
            app_version=app_version,
            progress=collect_progress,
        )
        path = save_session(profile, session)
        return {
            "ok": True,
            "profile": profile,
            "path": str(path),
            "progress": progress_messages,
            "session": session.to_dict(redact=True),
        }
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
        write_result: dict[str, Any] = BubbleEditorClient().write(
            write_payload,
            write_session,
            dry_run=not execute,
        )
        if execute and write_result.get("ok"):
            record_mutation_overlay(
                profile=profile,
                app_id=str(
                    write_result.get("request", {}).get("payload", {}).get("appname")
                    or write_session.app_id
                ),
                payload=write_result.get("request", {}).get("payload") or write_payload,
                source="bubble_editor_write",
                response=write_result.get("response"),
            )
        return write_result
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
            execution_context = load_context_with_overlay(
                Path(context_file),
                profile=profile,
                app_id=str(args.get("app_id") or "") or None,
            )
        return execute_plan(
            execution_plan,
            profile=profile,
            execute=bool(args.get("execute")),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            compile_missing=bool(args.get("compile")),
            context=execution_context,
        )
    if name == "bubble_branch_list":
        args = arguments or {}
        return list_bubble_branches(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
        )
    if name == "bubble_branch_contributors":
        args = arguments or {}
        return list_branch_contributors(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
        )
    if name == "bubble_changelog_fetch":
        args = arguments or {}
        return fetch_changelog_entries(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
            start_index=int(args.get("start_index") or 0),
            num_fetch=int(args.get("num_fetch") or 50),
            filters=_changelog_filters_from_args(args),
        )
    if name == "bubble_branch_create":
        args = arguments or {}
        return create_bubble_branch(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            name=str(args.get("name") or ""),
            from_app_version=str(args.get("from_app_version") or "") or None,
            description=str(args.get("description") or ""),
            execute=bool(args.get("execute")),
            version_control_api_version=int(args.get("version_control_api_version") or 7),
        )
    if name == "bubble_branch_delete":
        args = arguments or {}
        return delete_bubble_branch(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or ""),
            soft_delete=bool(args.get("soft_delete", True)),
            execute=bool(args.get("execute")),
            confirm=bool(args.get("confirm")),
        )
    if name in ARIA_BUBBLE_TOOL_NAMES:
        return call_legacy_catalog_tool(name, arguments or {})
    raise ValueError(f"Unknown Bubble MCP tool: {name}")


def _changelog_filters_from_args(args: dict[str, Any]) -> dict[str, Any]:
    raw_filters = args.get("filters")
    filters: dict[str, Any] = dict(raw_filters) if isinstance(raw_filters, dict) else {}
    mapping = {
        "start_timestamp": "start_timestamp",
        "end_timestamp": "end_timestamp",
        "change_type": "type",
        "root": "root",
        "change_identifier": "change_identifier",
        "change_path": "change_path",
        "user_id": "user_id",
    }
    for input_key, output_key in mapping.items():
        if input_key not in args:
            continue
        value = args[input_key]
        if value == "":
            continue
        if input_key == "user_id" and isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        filters[output_key] = value
    return filters


def call_legacy_catalog_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Handle a ported Aria Bubble MCP tool name.

    The standalone package exposes every Aria tool name. Families implemented by
    the local compiler can be compiled/executed directly. Any family can execute
    when the caller provides an exact Bubble ``write_payload``.
    """

    if name == "create_from_html":
        html_file = str(args.get("url") or args.get("html_file") or args.get("file") or "").strip()
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
            refresh_context=bool(args.get("refresh_context")),
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
        result = BubbleEditorClient().write(write_payload, session, dry_run=not execute)
        if execute and result.get("ok"):
            record_mutation_overlay(
                profile=profile,
                app_id=str(result.get("request", {}).get("payload", {}).get("appname") or session.app_id),
                payload=result.get("request", {}).get("payload") or write_payload,
                source=name,
                response=result.get("response"),
            )
        return result

    runtime_result = dispatch_aria_runtime_tool(name, args)
    if runtime_result is not None:
        return runtime_result

    app_id = str(args.get("app_id") or args.get("appname") or "").strip()
    plan = {"steps": [{"id": "step_1", "tool_name": name, "args": dict(args)}]}
    if app_id:
        context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            context = load_context_with_overlay(
                Path(context_file),
                profile=profile or None,
                app_id=app_id or None,
            )
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
