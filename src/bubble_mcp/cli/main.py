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
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.html_runtime import create_from_html_runtime
from bubble_mcp.planner.deterministic import plan_message
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
    emit_json({"ok": True, "summary": context.summary()})
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
    emit_json({"ok": True, "plan": payload, "validation": validate_plan(payload)})
    return 0


def command_validate_plan(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    emit_json({"ok": True, "validation": validate_plan(payload)})
    return 0


def command_import_html(args: argparse.Namespace) -> int:
    html_source = str(getattr(args, "url", "") or args.file or "").strip()
    if args.runtime:
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
    report = run_eval(Path(args.dataset), app_id=args.app_id or None, compile_plans=args.compile)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json({"ok": True, "report": report})
    return 0


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
    context = load_context(Path(args.context_file)) if args.context_file else None
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
    context = load_context(Path(args.context_file)) if args.context_file else None
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
    session = capture_session_with_playwright(
        app_id=args.app_id,
        editor_url=args.editor_url or None,
        headless=args.headless,
        wait_seconds=args.wait_seconds,
        user_data_dir=browser_profile_dir,
        app_version=app_version or "test",
    )
    target = save_session(args.profile, session)
    emit_json({"ok": True, "profile": args.profile, "path": str(target), "session": session.to_dict(redact=True)})
    return 0


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
    run_parser.set_defaults(func=command_eval_run)

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
