"""Command line interface for Befree Bubble MCP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bubble_mcp.core.config import (
    BubbleMcpSettings,
    BubbleProfile,
    get_config_dir,
    load_settings,
    save_settings,
    with_profile,
)


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
