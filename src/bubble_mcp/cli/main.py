"""Command line interface for Befree Bubble MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.context.queries import search_context
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.core.config import (
    BubbleMcpSettings,
    BubbleProfile,
    get_config_dir,
    load_settings,
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
from bubble_mcp.harness.expert import export_expert_eval_cases
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.html_runtime import create_from_html_runtime
from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.runtime_smoke import run_runtime_smoke
from bubble_mcp.server.agent_guide import agent_guide, search_tool_catalog, task_recipe
from bubble_mcp.server.tools import call_tool
from bubble_mcp.sessions.browser import capture_session_with_playwright
from bubble_mcp.sessions.store import list_sessions, load_session, save_session, session_from_payload
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


def command_context_summary(args: argparse.Namespace) -> int:
    context = load_context(Path(args.file))
    emit_json({"ok": True, "summary": context.summary(), "freshness": context_freshness(context, path=Path(args.file))})
    return 0


def command_context_find(args: argparse.Namespace) -> int:
    context = load_context(Path(args.file))
    emit_json({"ok": True, "results": search_context(context, args.query, args.limit)})
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

    context_parser = subparsers.add_parser("context", help="Inspect compact Bubble context.")
    context_subparsers = context_parser.add_subparsers(dest="context_command", required=True)

    summary_parser = context_subparsers.add_parser("summary", help="Summarize a context file.")
    summary_parser.add_argument("--file", required=True, help="Path to compact context JSON.")
    summary_parser.set_defaults(func=command_context_summary)

    find_parser = context_subparsers.add_parser("find", help="Search a context file.")
    find_parser.add_argument("query")
    find_parser.add_argument("--file", required=True, help="Path to compact context JSON.")
    find_parser.add_argument("--limit", type=int, default=10)
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

    smoke_parser = subparsers.add_parser("smoke", help="Run safe runtime smoke checks.")
    smoke_subparsers = smoke_parser.add_subparsers(dest="smoke_command", required=True)
    runtime_smoke_parser = smoke_subparsers.add_parser(
        "runtime",
        help="Run MCP runtime smoke checks. Real writes require --suite execute-write --execute.",
    )
    runtime_smoke_parser.add_argument(
        "--suite",
        choices=["coverage", "safe-read", "preview-write", "execute-write", "family-preview"],
        default="coverage",
        help="Smoke suite to run. family-preview exercises representative tool families without writes; execute-write performs real temporary writes only when --execute is also set.",
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
