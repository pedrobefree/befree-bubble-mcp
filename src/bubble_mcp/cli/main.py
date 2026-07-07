"""Command line interface for Befree Bubble MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bubble_mcp.catalog_quality import catalog_quality_report
from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.context.queries import context_find_payload
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.core.config import (
    BubbleMcpSettings,
    BubbleProfile,
    get_config_dir,
    load_settings,
    resolve_profile,
    save_settings,
    with_profile,
)
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
from bubble_mcp.extensions.store import disable_extension, enable_extension, import_extension, list_extensions
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.extension_companion import ExtensionCompanionConfig, serve_extension_companion
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
from bubble_mcp.server.tools import call_tool
from bubble_mcp.skills.authoring import (
    create_skill_authoring_session,
    generate_skill_from_authoring_session,
    update_skill_authoring_session,
)
from bubble_mcp.skills.runner import run_skill
from bubble_mcp.skills.store import (
    disable_skill,
    enable_skill,
    export_skill,
    import_skill,
    list_skills,
)
from bubble_mcp.skills.validator import describe_skill_file, validate_skill_file
from bubble_mcp.sessions.browser import capture_session_with_playwright
from bubble_mcp.sessions.store import list_sessions, load_session, save_session, session_from_payload
from bubble_mcp.tool_authoring.sessions import (
    append_capture_to_authoring_session,
    create_authoring_session,
    describe_authoring_session,
    finalize_authoring_session,
    generate_authoring_extension_pack,
    set_active_authoring_session,
)
from bubble_mcp.validators.semantic import validate_plan


def emit_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def command_init(args: argparse.Namespace) -> int:
    config_dir = Path(args.config_dir).expanduser() if args.config_dir else get_config_dir()
    settings = BubbleMcpSettings(config_dir=config_dir, default_profile=None, profiles={})
    if not (config_dir / "settings.json").exists():
        save_settings(settings)
    emit_json({"ok": True, "config_dir": str(config_dir), "settings": str(config_dir / "settings.json")})
    return 0


def command_profile_add(args: argparse.Namespace) -> int:
    settings = load_settings()
    profile = BubbleProfile(
        name=args.name,
        app_id=args.app_id,
        appname=args.appname or args.app_id,
        editor_url=args.editor_url,
        app_version=args.app_version or None,
        app_json_path=args.app_json_path or None,
        consolelog_json_path=args.consolelog_json_path or None,
    )
    save_settings(with_profile(settings, profile))
    emit_json({"ok": True, "profile": profile.name, "app_id": profile.app_id})
    return 0


def command_profile_list(_args: argparse.Namespace) -> int:
    settings = load_settings()
    emit_json(
        {
            "ok": True,
            "default_profile": settings.default_profile,
            "profiles": [
                {
                    "name": profile.name,
                    "app_id": profile.app_id,
                    "appname": profile.appname,
                    "editor_url": profile.editor_url,
                    "app_version": profile.app_version,
                    "app_json_path": profile.app_json_path,
                    "consolelog_json_path": profile.consolelog_json_path,
                }
                for profile in settings.profiles.values()
            ],
        }
    )
    return 0


def command_profile_status(args: argparse.Namespace) -> int:
    status = profile_status(args.profile or "", max_age_hours=args.max_age_hours)
    emit_json(status)
    return 0 if status.get("ok") else 1


def command_profile_refresh_cache(args: argparse.Namespace) -> int:
    from bubble_mcp.server.tools import call_tool

    result = call_tool(
        "bubble_profile_cache_refresh",
        {
            "profile": args.profile,
            "app_id": args.app_id,
            "app_version": args.app_version,
            "output": args.output,
            "bubble_file": args.bubble_file,
            "consolelog_file": args.consolelog_file,
            "force": not args.no_force,
            "skip_id_to_path": args.skip_id_to_path,
            "max_age_hours": args.max_age_hours,
        },
    )
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_profile_bootstrap(args: argparse.Namespace) -> int:
    from bubble_mcp.server.tools import call_tool

    result = call_tool(
        "bubble_project_bootstrap",
        {
            "profile": args.profile,
            "app_id": args.app_id,
            "appname": args.appname,
            "editor_url": args.editor_url,
            "app_version": args.app_version,
            "app_json_path": args.app_json_path,
            "consolelog_json_path": args.consolelog_json_path,
            "detect_context": args.detect_context,
            "force_context": args.force_context,
            "max_age_hours": args.max_age_hours,
        },
    )
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_context_summary(args: argparse.Namespace) -> int:
    context = load_context(Path(args.file))
    emit_json({"ok": True, "summary": context.summary(), "freshness": context_freshness(context, path=Path(args.file))})
    return 0


def command_context_find(args: argparse.Namespace) -> int:
    profile_name = str(args.profile or "").strip()
    if args.file:
        context = load_context(Path(args.file))
    else:
        settings = load_settings()
        profile = resolve_profile(settings, profile_name or None)
        if profile is None:
            emit_json(
                {
                    "ok": False,
                    "error": "profile_required",
                    "message": "Provide --file or a configured --profile to search project context.",
                }
            )
            return 1
        status = profile_status(profile.name)
        raw_context_status = status.get("context")
        context_status = raw_context_status if isinstance(raw_context_status, dict) else {}
        context_path = str(context_status.get("path") or "").strip()
        if not context_path or not Path(context_path).exists():
            emit_json(
                {
                    "ok": False,
                    "error": "context_missing",
                    "profile": profile.name,
                    "next_actions": status.get("next_actions", []),
                }
            )
            return 1
        context = load_context_with_overlay(Path(context_path), profile=profile.name, app_id=profile.app_id)
    emit_json(
        {
            "ok": True,
            **({"profile": profile_name} if profile_name and args.file else {}),
            **context_find_payload(
                context,
                args.query,
                args.limit,
                exact=args.exact,
                include_metadata=args.include_metadata,
            ),
        }
    )
    return 0


def command_context_import(args: argparse.Namespace) -> int:
    context = import_context_artifact(Path(args.file), kind=args.kind)
    if args.output:
        save_context(context, Path(args.output))
    emit_json({"ok": True, "summary": context.summary(), "output": args.output or None})
    return 0


def command_context_detect(args: argparse.Namespace) -> int:
    result = detect_project_context(
        profile=args.profile,
        app_id=args.app_id or None,
        app_version=args.app_version,
        force=args.force,
        output=Path(args.output) if args.output else None,
        bubble_file=Path(args.bubble_file) if args.bubble_file else None,
        consolelog_file=Path(args.consolelog_file) if args.consolelog_file else None,
        include_id_to_path=not args.skip_id_to_path,
    )
    emit_json(result.to_dict())
    return 0


def command_plan(args: argparse.Namespace) -> int:
    plan = plan_message(args.message, context=args.context, parent=args.parent)
    payload = plan.to_dict()
    structural_validation = validate_structure(payload)
    emit_json(
        {
            "ok": True,
            "plan": payload,
            "validation": validate_plan(payload),
            "structural_validation": structural_validation,
            "next_user_action": next_user_action(structural_validation),
            "operation_snapshot": operation_snapshot(
                plan=payload,
                validation=structural_validation,
                execute=False,
                phase="planned",
            ),
        }
    )
    return 0


def command_validate_plan(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    structural_validation = validate_structure(payload, execute=args.execute)
    emit_json(
        {
            "ok": True,
            "validation": validate_plan(payload),
            "structural_validation": structural_validation,
            "next_user_action": next_user_action(structural_validation, execute=args.execute),
        }
    )
    return 0


def command_import_html(args: argparse.Namespace) -> int:
    html_source = str(getattr(args, "url", "") or args.file or "").strip()
    use_runtime = bool(args.runtime or getattr(args, "url", ""))
    if use_runtime:
        result = create_from_html_runtime(
            profile=args.profile,
            context=args.context,
            parent=args.parent,
            html_file=html_source,
            app_id=args.app_id or None,
            app_version=args.app_version,
            execute=args.execute,
            selector=args.selector or None,
            placement=args.placement or None,
            translate_to_existing_styles=args.translate_to_existing_styles,
            style_match_threshold=args.style_match_threshold,
            rendered_html=args.rendered_html,
            strict_validate=args.strict_validate,
            validation_out_dir=args.validation_out_dir or None,
            refresh_context=args.refresh_context,
        )
        emit_json(result)
        return 0 if result.get("ok") else 1

    if not args.file:
        raise ValueError("Non-runtime HTML import requires --file.")
    html = Path(args.file).read_text(encoding="utf-8")
    plan = html_to_plan(html, context=args.context, parent=args.parent)
    payload = plan.to_dict()
    if args.compile:
        if not args.app_id:
            raise ValueError("HTML import compilation requires --app-id.")
        payload = compile_plan_to_write_payloads(payload, app_id=args.app_id, app_version=args.app_version)
    emit_json({"ok": True, "plan": payload, "validation": validate_plan(payload)})
    return 0


def command_eval_run(args: argparse.Namespace) -> int:
    report = run_eval(
        Path(args.dataset),
        app_id=args.app_id or None,
        compile_plans=args.compile,
        case_filter=args.filter or None,
        failed_from=Path(args.failed_from) if args.failed_from else None,
        offset=args.offset,
        limit=args.limit if args.limit > 0 else None,
    )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json({"ok": True, "report": report})
    return 0


def command_eval_export_expert(args: argparse.Namespace) -> int:
    result = export_expert_eval_cases(
        Path(args.input),
        Path(args.output),
        limit=args.limit,
    )
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_eval_visual(args: argparse.Namespace) -> int:
    result = compare_visual_snapshot_files(
        Path(args.reference),
        Path(args.actual),
        tolerance_px=args.tolerance_px,
        tolerance_ratio=args.tolerance_ratio,
        require_text=not args.no_require_text,
        require_images=args.require_images,
    )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_eval_visual_audit(args: argparse.Namespace) -> int:
    arguments = {
        "reference": args.reference,
        "actual": args.actual,
        "reference_source": args.reference_source,
        "actual_source": args.actual_source,
        "actual_profile": args.actual_profile,
        "actual_app_id": args.actual_app_id,
        "actual_app_version": args.actual_app_version,
        "actual_page": args.actual_page,
        "actual_url": args.actual_url,
        "actual_public_base_url": args.actual_public_base_url,
        "selector": args.selector,
        "reference_selector": args.reference_selector,
        "actual_selector": args.actual_selector,
        "profile": args.profile,
        "context": args.context,
        "parent": args.parent,
        "app_id": args.app_id,
        "app_version": args.app_version,
        "execute": args.execute,
        "tolerance_px": args.tolerance_px,
        "tolerance_ratio": args.tolerance_ratio,
        "require_text": not args.no_require_text,
        "require_images": args.require_images,
        "reference_screenshot": args.reference_screenshot,
        "actual_screenshot": args.actual_screenshot,
        "screenshot_task": args.screenshot_task,
        "rendered_html": args.rendered_html,
        "viewport_width": args.viewport_width,
        "viewport_height": args.viewport_height,
        "wait_ms": args.wait_ms,
        "selector_timeout_ms": args.selector_timeout_ms,
        "max_nodes": args.max_nodes,
        "allow_raw_fallback": args.allow_raw_fallback,
    }
    result = audit_visual_from_inputs(arguments)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.output_plan:
        plan_path = Path(args.output_plan)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan = result.get("repair_plan", {}).get("plan") if isinstance(result.get("repair_plan"), dict) else {}
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_eval_capture_visual(args: argparse.Namespace) -> int:
    result = capture_visual_snapshot(
        str(args.source),
        selector=args.selector or "",
        rendered_html=args.rendered_html,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        wait_ms=args.wait_ms,
        selector_timeout_ms=args.selector_timeout_ms,
        max_nodes=args.max_nodes,
        allow_raw_fallback=args.allow_raw_fallback,
        output=Path(args.output) if args.output else None,
    )
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_eval_capture_bubble_visual(args: argparse.Namespace) -> int:
    query = _load_optional_json_object(args.query) if args.query else {}
    result = capture_bubble_visual_snapshot(
        profile=args.profile or "",
        app_id=args.app_id or "",
        app_version=args.app_version or "test",
        page=args.page or "index",
        selector=args.selector or "",
        public_base_url=args.public_base_url or "",
        url=args.url or "",
        query={str(key): str(value) for key, value in query.items()},
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        wait_ms=args.wait_ms,
        selector_timeout_ms=args.selector_timeout_ms,
        max_nodes=args.max_nodes,
        output=Path(args.output) if args.output else None,
    )
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_session_import(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Session import file must contain a JSON object.")
    session = session_from_payload(payload, default_app_id=args.app_id or None)
    target = save_session(args.profile, session)
    emit_json({"ok": True, "profile": args.profile, "path": str(target), "session": session.to_dict(redact=True)})
    return 0


def command_session_list(_args: argparse.Namespace) -> int:
    emit_json({"ok": True, "sessions": list_sessions()})
    return 0


def command_session_inspect(args: argparse.Namespace) -> int:
    session = load_session(args.profile)
    if session is None:
        raise ValueError(f"No Bubble session stored for profile '{args.profile}'.")
    app_id = args.app_id or session.app_id
    sample_payload: dict[str, object] = {
        "appname": app_id,
        "app_version": session.app_version or "test",
        "changes": [],
    }
    write_headers = build_editor_write_headers(session, sample_payload)
    emit_json(
        {
            "ok": True,
            "profile": args.profile,
            "session": session.to_dict(redact=True),
            "stored_header_keys": sorted(session.headers.keys()),
            "cookie_present": bool(session.cookies),
            "cookie_length": len(session.cookies or ""),
            "computed_write_header_keys": sorted(write_headers.keys()),
            "computed_write_headers": redact_sensitive(write_headers),
        }
    )
    return 0


def command_write(args: argparse.Namespace) -> int:
    session = load_session(args.profile)
    if session is None:
        raise ValueError(f"No Bubble session stored for profile '{args.profile}'.")
    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Write payload file must contain a JSON object.")
    result = BubbleEditorClient().write(payload, session, dry_run=not args.execute)
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_execute_plan(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("Plan file must contain a JSON object.")
    context = (
        load_context_with_overlay(Path(args.context_file), profile=args.profile, app_id=args.app_id or None)
        if args.context_file
        else None
    )
    result = execute_plan(
        plan,
        profile=args.profile,
        execute=args.execute,
        app_id=args.app_id or None,
        app_version=args.app_version,
        context=context,
        compile_missing=args.compile,
        auto_context=not args.no_auto_context,
    )
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_compile_plan(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("Plan file must contain a JSON object.")
    context = (
        load_context_with_overlay(Path(args.context_file), app_id=args.app_id or None)
        if args.context_file
        else None
    )
    compiled = compile_plan_to_write_payloads(
        plan,
        app_id=args.app_id,
        app_version=args.app_version,
        context=context,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(compiled, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json({"ok": True, "plan": compiled})
    return 0


def command_session_login(args: argparse.Namespace) -> int:
    browser_profile_dir = get_config_dir() / "browser-profiles" / args.profile
    settings = load_settings()
    configured_profile = settings.profiles.get(args.profile)
    app_version = args.app_version or (configured_profile.app_version if configured_profile else None)

    def emit_progress(message: str) -> None:
        print(f"[bubble-mcp session] {message}", file=sys.stderr, flush=True)

    session = capture_session_with_playwright(
        app_id=args.app_id,
        editor_url=args.editor_url or None,
        headless=args.headless,
        wait_seconds=args.wait_seconds,
        user_data_dir=browser_profile_dir,
        app_version=app_version or "test",
        progress=None if args.quiet else emit_progress,
    )
    target = save_session(args.profile, session)
    if not args.quiet:
        emit_progress(f"Session saved for profile '{args.profile}' at {target}.")
    emit_json({"ok": True, "profile": args.profile, "path": str(target), "session": session.to_dict(redact=True)})
    return 0


def _load_optional_json_object(value: str) -> dict[str, object]:
    if not value:
        return {}
    path = Path(value).expanduser()
    raw = path.read_text(encoding="utf-8") if path.exists() else value
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _cli_changelog_filters(args: argparse.Namespace) -> dict[str, object]:
    filters: dict[str, object] = _load_optional_json_object(args.filters)
    for attr, key in (
        ("start_timestamp", "start_timestamp"),
        ("end_timestamp", "end_timestamp"),
        ("change_type", "type"),
        ("root", "root"),
        ("change_identifier", "change_identifier"),
        ("change_path", "change_path"),
    ):
        value = getattr(args, attr, None)
        if value not in (None, ""):
            filters[key] = value
    if args.user_id:
        filters["user_id"] = args.user_id
    return filters


def command_branch_list(args: argparse.Namespace) -> int:
    emit_json(list_bubble_branches(profile=args.profile, app_id=args.app_id or None))
    return 0


def command_branch_contributors(args: argparse.Namespace) -> int:
    emit_json(
        list_branch_contributors(
            profile=args.profile,
            app_id=args.app_id or None,
            app_version=args.app_version or None,
        )
    )
    return 0


def command_branch_create(args: argparse.Namespace) -> int:
    emit_json(
        create_bubble_branch(
            profile=args.profile,
            app_id=args.app_id or None,
            name=args.name,
            from_app_version=args.from_app_version or None,
            description=args.description or "",
            execute=args.execute,
            version_control_api_version=args.version_control_api_version,
        )
    )
    return 0


def command_branch_delete(args: argparse.Namespace) -> int:
    emit_json(
        delete_bubble_branch(
            profile=args.profile,
            app_id=args.app_id or None,
            app_version=args.app_version,
            soft_delete=not args.hard_delete,
            execute=args.execute,
            confirm=args.confirm,
        )
    )
    return 0


def command_changelog_fetch(args: argparse.Namespace) -> int:
    emit_json(
        fetch_changelog_entries(
            profile=args.profile,
            app_id=args.app_id or None,
            app_version=args.app_version or None,
            start_index=args.start_index,
            num_fetch=args.num_fetch,
            filters=_cli_changelog_filters(args),
        )
    )
    return 0


def command_extension_list(_args: argparse.Namespace) -> int:
    emit_json({"ok": True, "extensions": [item.to_dict() for item in list_extensions()]})
    return 0


def emit_extension_error(action: str, exc: Exception) -> None:
    emit_json(
        {
            "ok": False,
            "action": action,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "errors": [str(exc)],
        }
    )


def command_extension_validate(args: argparse.Namespace) -> int:
    report = validate_extension_pack(Path(args.path))
    emit_json(report.to_dict())
    return 0 if report.ok else 1


def command_extension_import(args: argparse.Namespace) -> int:
    try:
        report = import_extension(Path(args.path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_extension_error("import", exc)
        return 1
    emit_json(report.to_dict())
    return 0 if report.ok else 1


def command_extension_enable(args: argparse.Namespace) -> int:
    try:
        report = enable_extension(args.extension_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_extension_error("enable", exc)
        return 1
    emit_json(report.to_dict())
    return 0 if report.ok else 1


def command_extension_disable(args: argparse.Namespace) -> int:
    try:
        report = disable_extension(args.extension_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_extension_error("disable", exc)
        return 1
    emit_json(report.to_dict())
    return 0 if report.ok else 1


def command_extension_companion_serve(args: argparse.Namespace) -> int:
    config = ExtensionCompanionConfig(
        host=args.host,
        port=args.port,
        capture_key=args.capture_key or "",
        tool_session_id=args.tool_session_id or None,
    )
    return serve_extension_companion(config)


def emit_skill_error(action: str, exc: Exception) -> None:
    emit_json(
        {
            "ok": False,
            "action": action,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "errors": [str(exc)],
        }
    )


def command_skill_validate(args: argparse.Namespace) -> int:
    try:
        report = validate_skill_file(Path(args.path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("validate", exc)
        return 1
    emit_json(report)
    return 0 if report.get("ok") else 1


def command_skill_describe(args: argparse.Namespace) -> int:
    try:
        if args.skill_id:
            from bubble_mcp.skills.store import get_skill

            report = describe_skill_file(get_skill(args.skill_id).path)
        elif args.path:
            report = describe_skill_file(Path(args.path))
        else:
            raise ValueError("skill describe requires --path or --skill-id.")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("describe", exc)
        return 1
    emit_json(report)
    return 0 if report.get("ok") else 1


def command_skill_import(args: argparse.Namespace) -> int:
    try:
        result = import_skill(Path(args.path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("import", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_export(args: argparse.Namespace) -> int:
    try:
        result = export_skill(args.skill_id, Path(args.output))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("export", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_list(args: argparse.Namespace) -> int:
    try:
        result = {"ok": True, "skills": [skill.to_dict() for skill in list_skills()]}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("list", exc)
        return 1
    emit_json(result)
    return 0


def command_skill_enable(args: argparse.Namespace) -> int:
    try:
        result = enable_skill(args.skill_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("enable", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_disable(args: argparse.Namespace) -> int:
    try:
        result = disable_skill(args.skill_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("disable", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_run(args: argparse.Namespace) -> int:
    try:
        inputs = _load_optional_json_object(args.inputs) if args.inputs else {}
        result = run_skill(
            args.skill_id,
            inputs=inputs,
            execute=bool(args.execute),
            approve_execution=bool(args.approve_execution),
            run_id=args.run_id or None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("run", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_author_start(args: argparse.Namespace) -> int:
    try:
        result = create_skill_authoring_session(
            objective=args.objective,
            risk=args.risk,
            profile=args.profile or None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("author-start", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_author_update(args: argparse.Namespace) -> int:
    try:
        result = update_skill_authoring_session(args.session_id, answer=args.answer, field=args.field or None)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("author-update", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_skill_author_generate(args: argparse.Namespace) -> int:
    try:
        result = generate_skill_from_authoring_session(
            args.session_id,
            skill_id=args.skill_id or None,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_skill_error("author-generate", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def emit_tool_wizard_error(action: str, exc: Exception) -> None:
    emit_json(
        {
            "ok": False,
            "action": action,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "errors": [str(exc)],
        }
    )


def command_tool_wizard_start(args: argparse.Namespace) -> int:
    try:
        session = create_authoring_session(
            intent=args.intent,
            target=args.target,
            profile=args.profile,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_tool_wizard_error("start", exc)
        return 1
    emit_json(
        {
            "ok": True,
            "session": session.to_dict(),
            "active": True,
            "workflow": {
                "next_user_action": (
                    "Open the Bubble editor, enable the Chrome companion, perform the target actions, "
                    "then return and finalize this same session."
                ),
                "finish_with": "tool-wizard finalize <session_id>",
            },
        }
    )
    return 0


def command_tool_wizard_add_capture(args: argparse.Namespace) -> int:
    try:
        result = append_capture_to_authoring_session(args.session_id, Path(args.file))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_tool_wizard_error("add-capture", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_tool_wizard_activate(args: argparse.Namespace) -> int:
    try:
        result = set_active_authoring_session(args.session_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_tool_wizard_error("activate", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_tool_wizard_describe(args: argparse.Namespace) -> int:
    try:
        result = describe_authoring_session(args.session_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_tool_wizard_error("describe", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_tool_wizard_finalize(args: argparse.Namespace) -> int:
    try:
        if args.generate_pack:
            result = generate_authoring_extension_pack(
                args.session_id,
                extension_id=args.extension_id or None,
                tool_name=args.tool_name or None,
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
        else:
            result = finalize_authoring_session(args.session_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_tool_wizard_error("finalize", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_tool_wizard_generate(args: argparse.Namespace) -> int:
    try:
        result = generate_authoring_extension_pack(
            args.session_id,
            extension_id=args.extension_id or None,
            tool_name=args.tool_name or None,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_tool_wizard_error("generate", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def emit_learning_error(action: str, exc: Exception) -> None:
    emit_json(
        {
            "ok": False,
            "action": action,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "errors": [str(exc)],
        }
    )


def command_learning_record(args: argparse.Namespace) -> int:
    try:
        value = _load_optional_json_object(args.value)
        record = append_learning_record(
            scope=args.scope,
            key=args.key,
            value=value,
            source=args.source,
            confidence=args.confidence,
            profile=args.profile or None,
            project=args.project or None,
            extension_id=args.extension_id or None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_learning_error("record", exc)
        return 1
    emit_json({"ok": True, "record": record.to_dict()})
    return 0


def command_learning_list(args: argparse.Namespace) -> int:
    try:
        records = list_learning_records(
            scope=args.scope or None,
            profile=args.profile or None,
            project=args.project or None,
            extension_id=args.extension_id or None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_learning_error("list", exc)
        return 1
    emit_json({"ok": True, "records": [record.to_dict() for record in records]})
    return 0


def emit_knowledge_error(action: str, exc: Exception) -> None:
    emit_json(
        {
            "ok": False,
            "action": action,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "errors": [str(exc)],
        }
    )


def command_knowledge_refresh_source(args: argparse.Namespace) -> int:
    try:
        result = import_knowledge_records(Path(args.file), source=args.source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_knowledge_error("refresh-source", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_knowledge_search(args: argparse.Namespace) -> int:
    try:
        result = knowledge_search(args.query, limit=args.limit)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_knowledge_error("search", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_knowledge_fetch(args: argparse.Namespace) -> int:
    try:
        result = fetch_knowledge_record(args.record_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_knowledge_error("fetch", exc)
        return 1
    emit_json(result)
    return 0 if result.get("ok") else 1


def command_knowledge_guidance(args: argparse.Namespace) -> int:
    try:
        result = knowledge_search(args.query, limit=args.limit)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_knowledge_error("guidance", exc)
        return 1
    emit_json(
        {
            **result,
            "purpose": "manual_guidance",
            "cache_only": True,
            "remote_docs": "disabled",
        }
    )
    return 0 if result.get("ok") else 1


def command_tools_guide(args: argparse.Namespace) -> int:
    emit_json(agent_guide(task=args.task or ""))
    return 0


def command_tools_search(args: argparse.Namespace) -> int:
    emit_json(search_tool_catalog(args.query, limit=args.limit))
    return 0


def command_tools_recipe(args: argparse.Namespace) -> int:
    emit_json(
        task_recipe(
            args.task,
            recipe=args.recipe or "",
            profile=args.profile or "",
            context=args.context or "",
            parent=args.parent or "root",
            execute=args.execute,
        )
    )
    return 0


def command_tools_runbook(args: argparse.Namespace) -> int:
    emit_json(
        task_runbook(
            args.task,
            profile=args.profile or "",
            context=args.context or "",
            parent=args.parent or "root",
            execute=args.execute,
            search_limit=args.search_limit,
            include_profile_status=args.include_profile_status,
        )
    )
    return 0


def command_tools_coverage(args: argparse.Namespace) -> int:
    report = catalog_coverage_report(include_tools=bool(args.include_tools))
    emit_json(report)
    return 0 if report.get("ok") else 1


def command_tools_quality(_args: argparse.Namespace) -> int:
    report = catalog_quality_report()
    emit_json(report)
    return 0 if report.get("ok") else 1


def command_readiness(args: argparse.Namespace) -> int:
    report = run_readiness_check(
        call_tool,
        profile=args.profile or "",
        context=args.context,
        parent=args.parent,
        app_id=args.app_id or "",
        app_version=args.app_version,
        max_age_hours=args.max_age_hours,
        include_family_preview=args.include_family_preview,
        include_details=args.include_details,
        stop_on_failure=args.stop_on_failure,
    )
    emit_json(report)
    return 0 if report.get("ok") else 1


def command_smoke_runtime(args: argparse.Namespace) -> int:
    result = run_runtime_smoke(
        call_tool,
        profile=args.profile or "",
        context=args.context,
        parent=args.parent,
        app_id=args.app_id or "",
        app_version=args.app_version,
        suite=args.suite,
        limit=args.limit,
        html_url=args.html_url or "",
        selector=args.selector or "",
        include_details=args.include_details,
        stop_on_failure=args.stop_on_failure,
        execute=args.execute,
        cleanup=args.cleanup,
        run_id=args.run_id or "",
        verify_context=args.verify_context,
        verification_output=args.verification_output or "",
    )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json(result)
    return 0 if result.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bubble-mcp")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create local Bubble MCP settings.")
    init_parser.add_argument("--config-dir", default="", help="Override config directory.")
    init_parser.set_defaults(func=command_init)

    profile_parser = subparsers.add_parser("profile", help="Manage Bubble app profiles.")
    profile_subparsers = profile_parser.add_subparsers(dest="profile_command", required=True)

    add_parser = profile_subparsers.add_parser("add", help="Add or update a profile.")
    add_parser.add_argument("name")
    add_parser.add_argument("--app-id", required=True)
    add_parser.add_argument("--appname", default="")
    add_parser.add_argument("--editor-url", default=None)
    add_parser.add_argument("--app-version", default="test")
    add_parser.add_argument(
        "--app-json-path",
        default="",
        help="Path to a local .bubble export. Used before consolelog/crawler context fallbacks.",
    )
    add_parser.add_argument(
        "--consolelog-json-path",
        default="",
        help="Path to a local console.log(app) JSON/text capture. Used after .bubble and before crawler.",
    )
    add_parser.set_defaults(func=command_profile_add)

    list_parser = profile_subparsers.add_parser("list", help="List configured profiles.")
    list_parser.set_defaults(func=command_profile_list)

    status_parser = profile_subparsers.add_parser("status", help="Show read-only readiness status for a profile.")
    status_parser.add_argument("--profile", default="", help="Profile to inspect. Defaults to settings.default_profile.")
    status_parser.add_argument("--max-age-hours", type=int, default=24)
    status_parser.set_defaults(func=command_profile_status)

    refresh_cache_parser = profile_subparsers.add_parser(
        "refresh-cache",
        help="Force refresh local cache/context artifacts for one configured profile.",
    )
    refresh_cache_parser.add_argument("--profile", required=True)
    refresh_cache_parser.add_argument("--app-id", default="")
    refresh_cache_parser.add_argument("--app-version", default="")
    refresh_cache_parser.add_argument("--output", default="")
    refresh_cache_parser.add_argument("--bubble-file", default="")
    refresh_cache_parser.add_argument("--consolelog-file", default="")
    refresh_cache_parser.add_argument("--no-force", action="store_true")
    refresh_cache_parser.add_argument("--skip-id-to-path", action="store_true")
    refresh_cache_parser.add_argument("--max-age-hours", type=int, default=24)
    refresh_cache_parser.set_defaults(func=command_profile_refresh_cache)

    bootstrap_parser = profile_subparsers.add_parser(
        "bootstrap",
        help="Create/update a profile and return setup readiness plus next actions.",
    )
    bootstrap_parser.add_argument("profile")
    bootstrap_parser.add_argument("--app-id", default="")
    bootstrap_parser.add_argument("--appname", default="")
    bootstrap_parser.add_argument("--editor-url", default="")
    bootstrap_parser.add_argument("--app-version", default="test")
    bootstrap_parser.add_argument("--app-json-path", default="")
    bootstrap_parser.add_argument("--consolelog-json-path", default="")
    bootstrap_parser.add_argument("--detect-context", action="store_true")
    bootstrap_parser.add_argument("--force-context", action="store_true")
    bootstrap_parser.add_argument("--max-age-hours", type=int, default=24)
    bootstrap_parser.set_defaults(func=command_profile_bootstrap)

    context_parser = subparsers.add_parser("context", help="Inspect compact Bubble context.")
    context_subparsers = context_parser.add_subparsers(dest="context_command", required=True)

    summary_parser = context_subparsers.add_parser("summary", help="Summarize a context file.")
    summary_parser.add_argument("--file", required=True, help="Path to compact context JSON.")
    summary_parser.set_defaults(func=command_context_summary)

    find_parser = context_subparsers.add_parser("find", help="Search a context file.")
    find_parser.add_argument("query")
    find_parser.add_argument("--file", default="", help="Path to compact context JSON. Optional when --profile is provided.")
    find_parser.add_argument("--profile", default="", help="Configured profile whose active compact context should be searched.")
    find_parser.add_argument("--limit", type=int, default=10)
    find_parser.add_argument("--exact", action="store_true", help="Match exact ids, labels, Bubble ids, or context refs.")
    find_parser.add_argument(
        "--include-metadata",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include full node metadata in results. Disable for compact agent verification output.",
    )
    find_parser.set_defaults(func=command_context_find)

    import_context_parser = context_subparsers.add_parser(
        "import",
        help="Import a Bubble .bubble/consolelog JSON or crawler-index JSON into compact context.",
    )
    import_context_parser.add_argument("--file", required=True)
    import_context_parser.add_argument("--kind", choices=["auto", "bubble", "crawler"], default="auto")
    import_context_parser.add_argument("--output", default="")
    import_context_parser.set_defaults(func=command_context_import)

    detect_context_parser = context_subparsers.add_parser(
        "detect",
        help="Detect and materialize context using .bubble/consolelog fallback and editor crawler.",
    )
    detect_context_parser.add_argument("--profile", required=True)
    detect_context_parser.add_argument("--app-id", default="")
    detect_context_parser.add_argument("--app-version", default="test")
    detect_context_parser.add_argument("--output", default="")
    detect_context_parser.add_argument("--bubble-file", default="")
    detect_context_parser.add_argument("--consolelog-file", default="")
    detect_context_parser.add_argument("--force", action="store_true")
    detect_context_parser.add_argument("--skip-id-to-path", action="store_true")
    detect_context_parser.set_defaults(func=command_context_detect)

    plan_parser = subparsers.add_parser("plan", help="Create a Bubble plan.")
    plan_parser.add_argument("message")
    plan_parser.add_argument("--context", default="index")
    plan_parser.add_argument("--parent", default="index")
    plan_parser.set_defaults(func=command_plan)

    validate_parser = subparsers.add_parser("validate-plan", help="Validate a plan JSON file.")
    validate_parser.add_argument("--file", required=True)
    validate_parser.add_argument("--execute", action="store_true")
    validate_parser.set_defaults(func=command_validate_plan)

    import_parser = subparsers.add_parser("import", help="Import external design artifacts.")
    import_subparsers = import_parser.add_subparsers(dest="import_command", required=True)
    html_parser = import_subparsers.add_parser("html", help="Convert HTML to a Bubble plan.")
    html_parser.add_argument("--file", default="", help="Path to an HTML file. Runtime mode also accepts URLs here for compatibility.")
    html_parser.add_argument("--url", default="", help="URL to hydrate with the advanced runtime importer.")
    html_parser.add_argument("--context", default="index")
    html_parser.add_argument("--parent", default="index")
    html_parser.add_argument("--runtime", action="store_true", help="Use Aria's advanced create-from-html runtime.")
    html_parser.add_argument("--profile", default="")
    html_parser.add_argument("--execute", action="store_true")
    html_parser.add_argument("--selector", default="")
    html_parser.add_argument("--placement", choices=["top", "bottom"], default="")
    html_parser.add_argument("--translate-to-existing-styles", action="store_true")
    html_parser.add_argument("--style-match-threshold", type=float, default=0.78)
    html_parser.add_argument("--rendered-html", dest="rendered_html", action="store_true")
    html_parser.add_argument("--no-rendered-html", dest="rendered_html", action="store_false")
    html_parser.set_defaults(rendered_html=None)
    html_parser.add_argument("--strict-validate", action="store_true")
    html_parser.add_argument("--validation-out-dir", default="")
    html_parser.add_argument("--refresh-context", action="store_true")
    html_parser.add_argument("--compile", action="store_true")
    html_parser.add_argument("--app-id", default="")
    html_parser.add_argument("--app-version", default="test")
    html_parser.set_defaults(func=command_import_html)

    eval_parser = subparsers.add_parser("eval", help="Run planning evals.")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command", required=True)
    run_parser = eval_subparsers.add_parser("run", help="Run an eval dataset.")
    run_parser.add_argument("--dataset", required=True)
    run_parser.add_argument("--report", default="")
    run_parser.add_argument("--compile", action="store_true")
    run_parser.add_argument("--app-id", default="")
    run_parser.add_argument("--filter", default="", help="Comma-separated case ids to run.")
    run_parser.add_argument("--failed-from", default="", help="Run only failure ids from a prior JSON report.")
    run_parser.add_argument("--offset", type=int, default=0, help="Skip this many cases after filtering.")
    run_parser.add_argument("--limit", type=int, default=0, help="Run at most this many cases after filtering.")
    run_parser.set_defaults(func=command_eval_run)

    export_expert_parser = eval_subparsers.add_parser(
        "export-expert",
        help="Export redacted captured Bubble editor writes into eval cases.",
    )
    export_expert_parser.add_argument("--input", required=True)
    export_expert_parser.add_argument("--output", required=True)
    export_expert_parser.add_argument("--limit", type=int, default=250)
    export_expert_parser.set_defaults(func=command_eval_export_expert)

    visual_parser = eval_subparsers.add_parser(
        "visual",
        help="Compare two structured visual snapshots for layout/text/image/style drift.",
    )
    visual_parser.add_argument("--reference", required=True)
    visual_parser.add_argument("--actual", required=True)
    visual_parser.add_argument("--report", default="")
    visual_parser.add_argument("--tolerance-px", type=float, default=4)
    visual_parser.add_argument("--tolerance-ratio", type=float, default=0.08)
    visual_parser.add_argument("--no-require-text", action="store_true")
    visual_parser.add_argument("--require-images", action="store_true")
    visual_parser.set_defaults(func=command_eval_visual)

    visual_audit_parser = eval_subparsers.add_parser(
        "visual-audit",
        help="Audit visual drift, generate a Bubble repair plan, and optionally execute the repairs.",
    )
    visual_audit_parser.add_argument("--reference", default="", help="Reference visual snapshot JSON path.")
    visual_audit_parser.add_argument("--actual", default="", help="Actual visual snapshot JSON path.")
    visual_audit_parser.add_argument("--reference-source", default="", help="URL, file, or raw HTML to capture as reference.")
    visual_audit_parser.add_argument("--actual-source", default="", help="URL, file, or raw HTML to capture as actual.")
    visual_audit_parser.add_argument("--actual-profile", default="", help="Profile used to capture rendered Bubble actual output.")
    visual_audit_parser.add_argument("--actual-app-id", default="", help="App id used to capture rendered Bubble actual output.")
    visual_audit_parser.add_argument("--actual-app-version", default="test")
    visual_audit_parser.add_argument("--actual-page", default="", help="Bubble page/reusable path for actual capture.")
    visual_audit_parser.add_argument("--actual-url", default="", help="Explicit actual URL override.")
    visual_audit_parser.add_argument("--actual-public-base-url", default="")
    visual_audit_parser.add_argument("--selector", default="", help="Shared selector for reference/actual capture.")
    visual_audit_parser.add_argument("--reference-selector", default="", help="Reference selector override.")
    visual_audit_parser.add_argument("--actual-selector", default="", help="Actual selector override.")
    visual_audit_parser.add_argument("--profile", default="", help="Profile used when execute=true.")
    visual_audit_parser.add_argument("--context", default="index", help="Bubble page/reusable context for repair steps.")
    visual_audit_parser.add_argument("--parent", default="root", help="Bubble parent fallback for repair steps.")
    visual_audit_parser.add_argument("--app-id", default="", help="Bubble app id used when compiling repair steps.")
    visual_audit_parser.add_argument("--app-version", default="test")
    visual_audit_parser.add_argument("--execute", action="store_true", help="Execute generated repair steps through Bubble.")
    visual_audit_parser.add_argument("--report", default="", help="Optional output path for the full audit report.")
    visual_audit_parser.add_argument("--output-plan", default="", help="Optional output path for just the generated repair plan.")
    visual_audit_parser.add_argument("--tolerance-px", type=float, default=4)
    visual_audit_parser.add_argument("--tolerance-ratio", type=float, default=0.08)
    visual_audit_parser.add_argument("--no-require-text", action="store_true")
    visual_audit_parser.add_argument("--require-images", action="store_true")
    visual_audit_parser.add_argument("--reference-screenshot", default="", help="Reference screenshot path for LLM review payload.")
    visual_audit_parser.add_argument("--actual-screenshot", default="", help="Actual screenshot path for LLM review payload.")
    visual_audit_parser.add_argument("--screenshot-task", default="", help="Extra instruction for screenshot LLM review.")
    visual_audit_parser.add_argument("--rendered-html", dest="rendered_html", action="store_true")
    visual_audit_parser.add_argument("--no-rendered-html", dest="rendered_html", action="store_false")
    visual_audit_parser.set_defaults(rendered_html=True)
    visual_audit_parser.add_argument("--viewport-width", type=int, default=1365)
    visual_audit_parser.add_argument("--viewport-height", type=int, default=768)
    visual_audit_parser.add_argument("--wait-ms", type=int, default=0)
    visual_audit_parser.add_argument("--selector-timeout-ms", type=int, default=5000)
    visual_audit_parser.add_argument("--max-nodes", type=int, default=250)
    visual_audit_parser.add_argument("--allow-raw-fallback", action=argparse.BooleanOptionalAction, default=True)
    visual_audit_parser.set_defaults(func=command_eval_visual_audit)

    capture_visual_parser = eval_subparsers.add_parser(
        "capture-visual",
        help="Capture a structured visual snapshot from a URL, HTML file, or HTML string.",
    )
    capture_visual_parser.add_argument("--source", required=True, help="URL, local HTML file path, or raw HTML source.")
    capture_visual_parser.add_argument("--selector", default="", help="Optional CSS selector to capture.")
    capture_visual_parser.add_argument("--output", default="", help="Optional output JSON snapshot path.")
    capture_visual_parser.add_argument("--rendered-html", dest="rendered_html", action="store_true")
    capture_visual_parser.add_argument("--no-rendered-html", dest="rendered_html", action="store_false")
    capture_visual_parser.set_defaults(rendered_html=True)
    capture_visual_parser.add_argument("--viewport-width", type=int, default=1365)
    capture_visual_parser.add_argument("--viewport-height", type=int, default=768)
    capture_visual_parser.add_argument("--wait-ms", type=int, default=0)
    capture_visual_parser.add_argument("--selector-timeout-ms", type=int, default=5000)
    capture_visual_parser.add_argument("--max-nodes", type=int, default=250)
    capture_visual_parser.add_argument("--allow-raw-fallback", action=argparse.BooleanOptionalAction, default=True)
    capture_visual_parser.set_defaults(func=command_eval_capture_visual)

    capture_bubble_visual_parser = eval_subparsers.add_parser(
        "capture-bubble-visual",
        help="Capture the rendered Bubble app/preview output for a profile, app, page, or explicit URL.",
    )
    capture_bubble_visual_parser.add_argument("--profile", default="")
    capture_bubble_visual_parser.add_argument("--app-id", default="")
    capture_bubble_visual_parser.add_argument("--app-version", default="test")
    capture_bubble_visual_parser.add_argument("--page", default="index")
    capture_bubble_visual_parser.add_argument("--selector", default="")
    capture_bubble_visual_parser.add_argument("--public-base-url", default="")
    capture_bubble_visual_parser.add_argument("--url", default="", help="Explicit Bubble app URL override.")
    capture_bubble_visual_parser.add_argument("--query", default="", help="JSON object or file path with URL query params.")
    capture_bubble_visual_parser.add_argument("--output", default="")
    capture_bubble_visual_parser.add_argument("--viewport-width", type=int, default=1365)
    capture_bubble_visual_parser.add_argument("--viewport-height", type=int, default=768)
    capture_bubble_visual_parser.add_argument("--wait-ms", type=int, default=1000)
    capture_bubble_visual_parser.add_argument("--selector-timeout-ms", type=int, default=10000)
    capture_bubble_visual_parser.add_argument("--max-nodes", type=int, default=250)
    capture_bubble_visual_parser.set_defaults(func=command_eval_capture_bubble_visual)

    session_parser = subparsers.add_parser("session", help="Manage local Bubble editor sessions.")
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)

    session_import_parser = session_subparsers.add_parser(
        "import",
        help="Import a Bubble editor session JSON with headers/cookies.",
    )
    session_import_parser.add_argument("--profile", required=True)
    session_import_parser.add_argument("--file", required=True)
    session_import_parser.add_argument("--app-id", default="")
    session_import_parser.set_defaults(func=command_session_import)

    session_login_parser = session_subparsers.add_parser(
        "login",
        help="Open a local browser and capture Bubble cookies for a profile.",
    )
    session_login_parser.add_argument("--profile", required=True)
    session_login_parser.add_argument("--app-id", required=True)
    session_login_parser.add_argument("--editor-url", default="")
    session_login_parser.add_argument("--app-version", default="")
    session_login_parser.add_argument(
        "--wait-seconds",
        type=int,
        default=120,
        help="Maximum time to keep the browser open while polling and saving the latest Bubble cookies.",
    )
    session_login_parser.add_argument("--headless", action="store_true")
    session_login_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable capture progress on stderr.",
    )
    session_login_parser.set_defaults(func=command_session_login)

    session_list_parser = session_subparsers.add_parser("list", help="List imported session metadata.")
    session_list_parser.set_defaults(func=command_session_list)

    session_inspect_parser = session_subparsers.add_parser(
        "inspect",
        help="Inspect redacted session data and computed Bubble write headers.",
    )
    session_inspect_parser.add_argument("--profile", required=True)
    session_inspect_parser.add_argument("--app-id", default="")
    session_inspect_parser.set_defaults(func=command_session_inspect)

    write_parser = subparsers.add_parser("write", help="Send a Bubble /appeditor/write payload.")
    write_parser.add_argument("--profile", required=True)
    write_parser.add_argument("--payload", required=True)
    write_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually post to Bubble. Without this flag the command validates and prints the request.",
    )
    write_parser.set_defaults(func=command_write)

    branch_parser = subparsers.add_parser("branch", help="Inspect and manage Bubble editor branches.")
    branch_subparsers = branch_parser.add_subparsers(dest="branch_command", required=True)

    branch_list_parser = branch_subparsers.add_parser("list", help="List Bubble branches for a profile.")
    branch_list_parser.add_argument("--profile", required=True)
    branch_list_parser.add_argument("--app-id", default="")
    branch_list_parser.set_defaults(func=command_branch_list)

    branch_contributors_parser = branch_subparsers.add_parser(
        "contributors",
        help="List contributors for a Bubble branch/version.",
    )
    branch_contributors_parser.add_argument("--profile", required=True)
    branch_contributors_parser.add_argument("--app-id", default="")
    branch_contributors_parser.add_argument("--app-version", default="")
    branch_contributors_parser.set_defaults(func=command_branch_contributors)

    branch_create_parser = branch_subparsers.add_parser("create", help="Create a Bubble branch or sub-branch.")
    branch_create_parser.add_argument("--profile", required=True)
    branch_create_parser.add_argument("--name", required=True, help="Display name for the new Bubble branch.")
    branch_create_parser.add_argument("--app-id", default="")
    branch_create_parser.add_argument(
        "--from-app-version",
        default="",
        help="Source branch/version. Use an existing branch id to create a sub-branch.",
    )
    branch_create_parser.add_argument("--description", default="")
    branch_create_parser.add_argument("--version-control-api-version", type=int, default=7)
    branch_create_parser.add_argument("--execute", action="store_true")
    branch_create_parser.set_defaults(func=command_branch_create)

    branch_delete_parser = branch_subparsers.add_parser("delete", help="Delete a Bubble branch/version.")
    branch_delete_parser.add_argument("--profile", required=True)
    branch_delete_parser.add_argument("--app-version", required=True, help="Branch/version id to delete.")
    branch_delete_parser.add_argument("--app-id", default="")
    branch_delete_parser.add_argument("--hard-delete", action="store_true", help="Disable Bubble soft-delete flag.")
    branch_delete_parser.add_argument("--execute", action="store_true")
    branch_delete_parser.add_argument("--confirm", action="store_true")
    branch_delete_parser.set_defaults(func=command_branch_delete)

    changelog_parser = subparsers.add_parser("changelog", help="Fetch Bubble editor changelog entries.")
    changelog_subparsers = changelog_parser.add_subparsers(dest="changelog_command", required=True)
    changelog_fetch_parser = changelog_subparsers.add_parser("fetch", help="Fetch Bubble changelog entries.")
    changelog_fetch_parser.add_argument("--profile", required=True)
    changelog_fetch_parser.add_argument("--app-id", default="")
    changelog_fetch_parser.add_argument("--app-version", default="")
    changelog_fetch_parser.add_argument("--start-index", type=int, default=0)
    changelog_fetch_parser.add_argument("--num-fetch", type=int, default=50)
    changelog_fetch_parser.add_argument("--filters", default="", help="JSON object or path to JSON object.")
    changelog_fetch_parser.add_argument("--start-timestamp", type=int, default=None)
    changelog_fetch_parser.add_argument("--end-timestamp", type=int, default=None)
    changelog_fetch_parser.add_argument("--change-type", default="")
    changelog_fetch_parser.add_argument("--root", default="")
    changelog_fetch_parser.add_argument("--change-identifier", default="")
    changelog_fetch_parser.add_argument("--change-path", default="")
    changelog_fetch_parser.add_argument("--user-id", action="append", default=[])
    changelog_fetch_parser.set_defaults(func=command_changelog_fetch)

    extension_parser = subparsers.add_parser("extension", help="Manage local Bubble MCP extension packs.")
    extension_subparsers = extension_parser.add_subparsers(dest="extension_command", required=True)

    extension_list_parser = extension_subparsers.add_parser("list", help="List installed extension packs.")
    extension_list_parser.set_defaults(func=command_extension_list)

    extension_validate_parser = extension_subparsers.add_parser("validate", help="Validate an extension pack directory.")
    extension_validate_parser.add_argument("--path", required=True)
    extension_validate_parser.set_defaults(func=command_extension_validate)

    extension_import_parser = extension_subparsers.add_parser("import", help="Import an extension pack directory.")
    extension_import_parser.add_argument("--path", required=True)
    extension_import_parser.set_defaults(func=command_extension_import)

    extension_enable_parser = extension_subparsers.add_parser("enable", help="Enable an installed extension pack.")
    extension_enable_parser.add_argument("extension_id")
    extension_enable_parser.set_defaults(func=command_extension_enable)

    extension_disable_parser = extension_subparsers.add_parser("disable", help="Disable an installed extension pack.")
    extension_disable_parser.add_argument("extension_id")
    extension_disable_parser.set_defaults(func=command_extension_disable)

    extension_companion_parser = extension_subparsers.add_parser(
        "companion",
        help="Run local services used by the shipped Chrome extension companion.",
    )
    extension_companion_subparsers = extension_companion_parser.add_subparsers(
        dest="extension_companion_command",
        required=True,
    )
    extension_companion_serve_parser = extension_companion_subparsers.add_parser(
        "serve",
        help="Start the local HTTP listener used by chrome-extension/.",
    )
    extension_companion_serve_parser.add_argument("--host", default="127.0.0.1")
    extension_companion_serve_parser.add_argument("--port", type=int, default=3847)
    extension_companion_serve_parser.add_argument(
        "--capture-key",
        default="",
        help="Optional key required from the extension in X-Bubble-MCP-Capture-Key.",
    )
    extension_companion_serve_parser.add_argument(
        "--tool-session-id",
        default="",
        help="Optional tool-authoring session id that receives write captures.",
    )
    extension_companion_serve_parser.set_defaults(func=command_extension_companion_serve)

    skill_parser = subparsers.add_parser("skill", help="Validate declarative Bubble MCP skill contracts.")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)

    skill_validate_parser = skill_subparsers.add_parser("validate", help="Validate a skill contract JSON file.")
    skill_validate_parser.add_argument("--path", required=True)
    skill_validate_parser.set_defaults(func=command_skill_validate)

    skill_describe_parser = skill_subparsers.add_parser("describe", help="Describe a validated skill contract JSON file.")
    skill_describe_parser.add_argument("--path", default="")
    skill_describe_parser.add_argument("--skill-id", default="")
    skill_describe_parser.set_defaults(func=command_skill_describe)

    skill_import_parser = skill_subparsers.add_parser("import", help="Import a skill contract JSON file.")
    skill_import_parser.add_argument("--path", required=True)
    skill_import_parser.set_defaults(func=command_skill_import)

    skill_export_parser = skill_subparsers.add_parser("export", help="Export an installed skill contract.")
    skill_export_parser.add_argument("skill_id")
    skill_export_parser.add_argument("--output", required=True)
    skill_export_parser.set_defaults(func=command_skill_export)

    skill_list_parser = skill_subparsers.add_parser("list", help="List installed and extension-provided skills.")
    skill_list_parser.set_defaults(func=command_skill_list)

    skill_enable_parser = skill_subparsers.add_parser("enable", help="Enable an imported skill.")
    skill_enable_parser.add_argument("skill_id")
    skill_enable_parser.set_defaults(func=command_skill_enable)

    skill_disable_parser = skill_subparsers.add_parser("disable", help="Disable an imported skill.")
    skill_disable_parser.add_argument("skill_id")
    skill_disable_parser.set_defaults(func=command_skill_disable)

    skill_run_parser = skill_subparsers.add_parser("run", help="Preview or execute an approved skill run.")
    skill_run_parser.add_argument("skill_id")
    skill_run_parser.add_argument("--inputs", default="", help="JSON object text or path.")
    skill_run_parser.add_argument("--execute", action="store_true")
    skill_run_parser.add_argument("--approve-execution", action="store_true")
    skill_run_parser.add_argument("--run-id", default="")
    skill_run_parser.set_defaults(func=command_skill_run)

    skill_author_parser = skill_subparsers.add_parser("author", help="Create or update skills interactively.")
    skill_author_subparsers = skill_author_parser.add_subparsers(dest="skill_author_command", required=True)
    skill_author_start_parser = skill_author_subparsers.add_parser("start", help="Start a skill-authoring session.")
    skill_author_start_parser.add_argument("--objective", required=True)
    skill_author_start_parser.add_argument(
        "--risk",
        choices=["read_only", "mutating", "destructive"],
        default="read_only",
    )
    skill_author_start_parser.add_argument("--profile", default="")
    skill_author_start_parser.set_defaults(func=command_skill_author_start)

    skill_author_update_parser = skill_author_subparsers.add_parser("update", help="Add an answer to a skill session.")
    skill_author_update_parser.add_argument("session_id")
    skill_author_update_parser.add_argument("--answer", required=True)
    skill_author_update_parser.add_argument("--field", default="")
    skill_author_update_parser.set_defaults(func=command_skill_author_update)

    skill_author_generate_parser = skill_author_subparsers.add_parser(
        "generate",
        help="Generate a skill contract from a skill session.",
    )
    skill_author_generate_parser.add_argument("session_id")
    skill_author_generate_parser.add_argument("--skill-id", default="")
    skill_author_generate_parser.add_argument("--output-dir", default="")
    skill_author_generate_parser.set_defaults(func=command_skill_author_generate)

    tool_wizard_parser = subparsers.add_parser(
        "tool-wizard",
        help="Manage local tool-authoring sessions from captured Bubble writes.",
    )
    tool_wizard_subparsers = tool_wizard_parser.add_subparsers(dest="tool_wizard_command", required=True)

    tool_wizard_start_parser = tool_wizard_subparsers.add_parser(
        "start",
        help="Start a local tool-authoring session.",
    )
    tool_wizard_start_parser.add_argument("--intent", required=True)
    tool_wizard_start_parser.add_argument("--target", required=True)
    tool_wizard_start_parser.add_argument("--profile", required=True)
    tool_wizard_start_parser.set_defaults(func=command_tool_wizard_start)

    tool_wizard_add_parser = tool_wizard_subparsers.add_parser(
        "add-capture",
        help="Add and classify a captured Bubble editor write JSON file.",
    )
    tool_wizard_add_parser.add_argument("session_id")
    tool_wizard_add_parser.add_argument("--file", required=True)
    tool_wizard_add_parser.set_defaults(func=command_tool_wizard_add_capture)

    tool_wizard_activate_parser = tool_wizard_subparsers.add_parser(
        "activate",
        help="Mark an existing tool-authoring session as the active Chrome extension capture target.",
    )
    tool_wizard_activate_parser.add_argument("session_id")
    tool_wizard_activate_parser.set_defaults(func=command_tool_wizard_activate)

    tool_wizard_describe_parser = tool_wizard_subparsers.add_parser(
        "describe",
        help="Describe a local tool-authoring session and aggregate classification.",
    )
    tool_wizard_describe_parser.add_argument("session_id")
    tool_wizard_describe_parser.set_defaults(func=command_tool_wizard_describe)

    tool_wizard_finalize_parser = tool_wizard_subparsers.add_parser(
        "finalize",
        help="Finalize a tool-authoring capture session and return learned patterns, questions, and test guidance.",
    )
    tool_wizard_finalize_parser.add_argument("session_id")
    tool_wizard_finalize_parser.add_argument("--generate-pack", action="store_true")
    tool_wizard_finalize_parser.add_argument("--extension-id", default="")
    tool_wizard_finalize_parser.add_argument("--tool-name", default="")
    tool_wizard_finalize_parser.add_argument("--output-dir", default="")
    tool_wizard_finalize_parser.set_defaults(func=command_tool_wizard_finalize)

    tool_wizard_generate_parser = tool_wizard_subparsers.add_parser(
        "generate",
        help="Generate a candidate extension pack from a finalized tool-authoring session.",
    )
    tool_wizard_generate_parser.add_argument("session_id")
    tool_wizard_generate_parser.add_argument("--extension-id", default="")
    tool_wizard_generate_parser.add_argument("--tool-name", default="")
    tool_wizard_generate_parser.add_argument("--output-dir", default="")
    tool_wizard_generate_parser.set_defaults(func=command_tool_wizard_generate)

    learning_parser = subparsers.add_parser("learning", help="Manage local consultative learning records.")
    learning_subparsers = learning_parser.add_subparsers(dest="learning_command", required=True)

    learning_record_parser = learning_subparsers.add_parser(
        "record",
        help="Append one scoped consultative learning record.",
    )
    learning_record_parser.add_argument(
        "--scope",
        choices=["global", "profile", "project", "extension"],
        required=True,
    )
    learning_record_parser.add_argument("--key", required=True)
    learning_record_parser.add_argument("--value", required=True, help="JSON object text or a path to a JSON object.")
    learning_record_parser.add_argument("--source", required=True)
    learning_record_parser.add_argument("--confidence", required=True)
    learning_record_parser.add_argument("--profile", default="")
    learning_record_parser.add_argument("--project", default="")
    learning_record_parser.add_argument("--extension-id", default="")
    learning_record_parser.set_defaults(func=command_learning_record)

    learning_list_parser = learning_subparsers.add_parser(
        "list",
        help="List consultative learning records with optional filters.",
    )
    learning_list_parser.add_argument("--scope", choices=["global", "profile", "project", "extension"], default="")
    learning_list_parser.add_argument("--profile", default="")
    learning_list_parser.add_argument("--project", default="")
    learning_list_parser.add_argument("--extension-id", default="")
    learning_list_parser.set_defaults(func=command_learning_list)

    knowledge_parser = subparsers.add_parser("knowledge", help="Manage local cached Bubble manual knowledge.")
    knowledge_subparsers = knowledge_parser.add_subparsers(dest="knowledge_command", required=True)

    knowledge_refresh_parser = knowledge_subparsers.add_parser(
        "refresh-source",
        help="Import normalized knowledge records from a local JSONL file.",
    )
    knowledge_refresh_parser.add_argument("--source", required=True, help="Safe local source id, such as bubble_manual_gitbook.")
    knowledge_refresh_parser.add_argument("--file", required=True, help="Local JSONL file to import.")
    knowledge_refresh_parser.set_defaults(func=command_knowledge_refresh_source)

    knowledge_search_parser = knowledge_subparsers.add_parser(
        "search",
        help="Search the local knowledge cache.",
    )
    knowledge_search_parser.add_argument("query")
    knowledge_search_parser.add_argument("--limit", type=int, default=8)
    knowledge_search_parser.set_defaults(func=command_knowledge_search)

    knowledge_fetch_parser = knowledge_subparsers.add_parser(
        "fetch",
        help="Fetch one local knowledge record by id.",
    )
    knowledge_fetch_parser.add_argument("record_id")
    knowledge_fetch_parser.set_defaults(func=command_knowledge_fetch)

    knowledge_guidance_parser = knowledge_subparsers.add_parser(
        "guidance",
        help="Return Bubble manual guidance from the local cache only.",
    )
    knowledge_guidance_parser.add_argument("query")
    knowledge_guidance_parser.add_argument("--limit", type=int, default=5)
    knowledge_guidance_parser.set_defaults(func=command_knowledge_guidance)

    tools_parser = subparsers.add_parser("tools", help="Discover the MCP tool catalog without opening the full schema.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)

    tools_guide_parser = tools_subparsers.add_parser(
        "guide",
        help="Return compact agent routing guidance for a Bubble task.",
    )
    tools_guide_parser.add_argument("--task", default="", help="Optional natural-language Bubble task to route.")
    tools_guide_parser.set_defaults(func=command_tools_guide)

    tools_search_parser = tools_subparsers.add_parser(
        "search",
        help="Search exposed MCP tools and return compact matching schemas.",
    )
    tools_search_parser.add_argument("--query", required=True, help="Search text such as 'html selector import'.")
    tools_search_parser.add_argument("--limit", type=int, default=8, help="Maximum matches to return, clamped to 1-25.")
    tools_search_parser.set_defaults(func=command_tools_search)

    tools_recipe_parser = tools_subparsers.add_parser(
        "recipe",
        help="Return an ordered MCP tool recipe for a Bubble task.",
    )
    tools_recipe_parser.add_argument("--task", required=True, help="Natural-language Bubble task to route.")
    tools_recipe_parser.add_argument("--recipe", default="", help="Optional recipe id to force.")
    tools_recipe_parser.add_argument("--profile", default="", help="Optional profile value to include in templates.")
    tools_recipe_parser.add_argument("--context", default="", help="Optional context/page value to include in templates.")
    tools_recipe_parser.add_argument("--parent", default="root", help="Optional parent value to include in templates.")
    tools_recipe_parser.add_argument("--execute", action="store_true", help="Mark the generated template as an execution path.")
    tools_recipe_parser.set_defaults(func=command_tools_recipe)

    tools_runbook_parser = tools_subparsers.add_parser(
        "runbook",
        help="Return one compact agent runbook with route, recipe, relevant tools, and optional profile status.",
    )
    tools_runbook_parser.add_argument("--task", required=True)
    tools_runbook_parser.add_argument("--profile", default="")
    tools_runbook_parser.add_argument("--context", default="")
    tools_runbook_parser.add_argument("--parent", default="root")
    tools_runbook_parser.add_argument("--execute", action="store_true")
    tools_runbook_parser.add_argument("--search-limit", type=int, default=6)
    tools_runbook_parser.add_argument("--include-profile-status", action="store_true")
    tools_runbook_parser.set_defaults(func=command_tools_runbook)

    tools_coverage_parser = tools_subparsers.add_parser(
        "coverage",
        help="Report how exposed MCP tools are executed by runtime, compiler, or native handlers.",
    )
    tools_coverage_parser.add_argument(
        "--include-tools",
        action="store_true",
        help="Include per-tool classifications. Omitted by default to keep agent/CI output compact.",
    )
    tools_coverage_parser.set_defaults(func=command_tools_coverage)

    tools_quality_parser = tools_subparsers.add_parser(
        "quality",
        help="Audit MCP catalog usability for agents, including schemas, descriptions, annotations, prompts, resources, and coverage.",
    )
    tools_quality_parser.set_defaults(func=command_tools_quality)

    readiness_parser = subparsers.add_parser(
        "readiness",
        help="Run the recommended MCP readiness sequence: health, coverage quality gate, routing, and optional profile smokes.",
    )
    readiness_parser.add_argument("--profile", default="")
    readiness_parser.add_argument("--context", default="index")
    readiness_parser.add_argument("--parent", default="root")
    readiness_parser.add_argument("--app-id", default="")
    readiness_parser.add_argument("--app-version", default="test")
    readiness_parser.add_argument("--max-age-hours", type=int, default=24)
    readiness_parser.add_argument(
        "--include-family-preview",
        action="store_true",
        help="Also run the broader execute=false family-preview smoke. Requires --profile for useful coverage.",
    )
    readiness_parser.add_argument(
        "--include-details",
        action="store_true",
        help="Include full nested smoke results. Omitted by default to keep output compact.",
    )
    readiness_parser.add_argument("--stop-on-failure", action="store_true")
    readiness_parser.set_defaults(func=command_readiness)

    smoke_parser = subparsers.add_parser("smoke", help="Run safe runtime smoke checks.")
    smoke_subparsers = smoke_parser.add_subparsers(dest="smoke_command", required=True)
    runtime_smoke_parser = smoke_subparsers.add_parser(
        "runtime",
        help="Run MCP runtime smoke checks. Real writes require --suite execute-write --execute.",
    )
    runtime_smoke_parser.add_argument(
        "--suite",
        choices=["coverage", "agent-routing", "visual-repair", "safe-read", "preview-write", "execute-write", "family-preview"],
        default="coverage",
        help="Smoke suite to run. agent-routing validates natural-language tool selection without writes; visual-repair validates visual audit repair planning without writes; family-preview exercises representative tool families without writes; execute-write performs real temporary writes only when --execute is also set.",
    )
    runtime_smoke_parser.add_argument("--profile", default="")
    runtime_smoke_parser.add_argument("--context", default="index")
    runtime_smoke_parser.add_argument("--parent", default="root")
    runtime_smoke_parser.add_argument("--app-id", default="")
    runtime_smoke_parser.add_argument("--app-version", default="test")
    runtime_smoke_parser.add_argument("--limit", type=int, default=0)
    runtime_smoke_parser.add_argument("--html-url", default="")
    runtime_smoke_parser.add_argument("--selector", default="")
    runtime_smoke_parser.add_argument("--report", default="")
    runtime_smoke_parser.add_argument("--include-details", action="store_true")
    runtime_smoke_parser.add_argument("--stop-on-failure", action="store_true")
    runtime_smoke_parser.add_argument(
        "--execute",
        action="store_true",
        help="Required for --suite execute-write. Ignored by read-only and preview suites.",
    )
    runtime_smoke_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="When used with execute-write, delete the temporary smoke page at the end.",
    )
    runtime_smoke_parser.add_argument(
        "--run-id",
        default="",
        help="Optional suffix for temporary smoke objects. Defaults to a timestamp plus random suffix.",
    )
    runtime_smoke_parser.add_argument(
        "--verify-context",
        action="store_true",
        help="After execute-write, refresh Bubble context and verify the temporary objects exist with expected defaults.",
    )
    runtime_smoke_parser.add_argument(
        "--verification-output",
        default="",
        help="Optional context JSON path written by --verify-context.",
    )
    runtime_smoke_parser.set_defaults(func=command_smoke_runtime)

    execute_plan_parser = subparsers.add_parser(
        "execute-plan",
        help="Execute a plan whose steps include args.write_payload.",
    )
    execute_plan_parser.add_argument("--profile", required=True)
    execute_plan_parser.add_argument("--file", required=True)
    execute_plan_parser.add_argument("--app-id", default="")
    execute_plan_parser.add_argument("--app-version", default="test")
    execute_plan_parser.add_argument(
        "--context-file",
        default="",
        help="Optional imported Bubble context JSON used while compiling abstract steps.",
    )
    execute_plan_parser.add_argument(
        "--no-auto-context",
        action="store_true",
        help="Disable automatic project context detection while compiling.",
    )
    execute_plan_parser.add_argument("--compile", action="store_true", help="Compile supported abstract steps before execution.")
    execute_plan_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually post write steps to Bubble. Without this flag the plan is previewed.",
    )
    execute_plan_parser.set_defaults(func=command_execute_plan)

    compile_plan_parser = subparsers.add_parser(
        "compile-plan",
        help="Compile supported abstract plan steps into Bubble write_payload objects.",
    )
    compile_plan_parser.add_argument("--file", required=True)
    compile_plan_parser.add_argument("--app-id", required=True)
    compile_plan_parser.add_argument("--app-version", default="test")
    compile_plan_parser.add_argument(
        "--context-file",
        default="",
        help="Optional imported Bubble context JSON used to resolve internal Bubble paths.",
    )
    compile_plan_parser.add_argument("--output", default="")
    compile_plan_parser.set_defaults(func=command_compile_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
