"""Command line interface for Befree Bubble MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.context.queries import search_context
from bubble_mcp.context.source import load_context
from bubble_mcp.core.config import (
    BubbleMcpSettings,
    BubbleProfile,
    get_config_dir,
    load_settings,
    save_settings,
    with_profile,
)
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.planner.deterministic import plan_message
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
    html = Path(args.file).read_text(encoding="utf-8")
    plan = html_to_plan(html, context=args.context, parent=args.parent)
    payload = plan.to_dict()
    emit_json({"ok": True, "plan": payload, "validation": validate_plan(payload)})
    return 0


def command_eval_run(args: argparse.Namespace) -> int:
    report = run_eval(Path(args.dataset))
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_json({"ok": True, "report": report})
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

    plan_parser = subparsers.add_parser("plan", help="Create a dry-run Bubble plan.")
    plan_parser.add_argument("message")
    plan_parser.add_argument("--context", default="index")
    plan_parser.add_argument("--parent", default="index")
    plan_parser.set_defaults(func=command_plan)

    validate_parser = subparsers.add_parser("validate-plan", help="Validate a plan JSON file.")
    validate_parser.add_argument("--file", required=True)
    validate_parser.set_defaults(func=command_validate_plan)

    import_parser = subparsers.add_parser("import", help="Import external design artifacts.")
    import_subparsers = import_parser.add_subparsers(dest="import_command", required=True)
    html_parser = import_subparsers.add_parser("html", help="Convert HTML to a Bubble dry-run plan.")
    html_parser.add_argument("--file", required=True)
    html_parser.add_argument("--context", default="index")
    html_parser.add_argument("--parent", default="index")
    html_parser.set_defaults(func=command_import_html)

    eval_parser = subparsers.add_parser("eval", help="Run planning evals.")
    eval_subparsers = eval_parser.add_subparsers(dest="eval_command", required=True)
    run_parser = eval_subparsers.add_parser("run", help="Run an eval dataset.")
    run_parser.add_argument("--dataset", required=True)
    run_parser.add_argument("--report", default="")
    run_parser.set_defaults(func=command_eval_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
