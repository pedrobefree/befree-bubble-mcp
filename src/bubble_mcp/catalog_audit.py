"""Repeatable parity checks between the packaged Bubble CLI and MCP catalog."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Iterable


# CLI-only housekeeping must not become a remotely callable MCP capability.
LEGACY_CLI_EXCLUSIONS: dict[str, str] = {
    "reset-tmp": "Local developer housekeeping; it does not operate on a Bubble project.",
}

# Compatibility spellings intentionally converge on one canonical MCP capability.
LEGACY_CLI_ALIASES: dict[str, str] = {
    "create-reusable-type": "create_reusable",
}


def _runtime_cli_source() -> Path:
    return Path(__file__).resolve().parent / "aria_runtime" / "bubble_cli.py"


def _literal_add_parser_names(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    names = {
        str(node.args[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_parser"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    return tuple(sorted(names))


@lru_cache(maxsize=1)
def legacy_cli_commands() -> tuple[str, ...]:
    """Return literal top-level commands exposed by the packaged Aria CLI."""

    return _literal_add_parser_names(_runtime_cli_source().read_text(encoding="utf-8"))


def cli_catalog_parity_report(catalog_names: Iterable[str]) -> dict[str, object]:
    """Compare Bubble-operation CLI commands with canonical or aliased MCP tools."""

    catalog = {str(name) for name in catalog_names}
    direct: list[dict[str, str]] = []
    aliases: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    for command in legacy_cli_commands():
        normalized = command.replace("-", "_")
        if normalized in catalog:
            direct.append({"command": command, "tool": normalized})
            continue
        alias_target = LEGACY_CLI_ALIASES.get(command)
        if alias_target and alias_target in catalog:
            aliases.append({"command": command, "tool": alias_target})
            continue
        reason = LEGACY_CLI_EXCLUSIONS.get(command)
        if reason:
            excluded.append({"command": command, "reason": reason})
            continue
        missing.append({"command": command, "candidate_tool": normalized})

    return {
        "ok": not missing,
        "cli_command_count": len(legacy_cli_commands()),
        "direct_match_count": len(direct),
        "alias_count": len(aliases),
        "excluded_count": len(excluded),
        "missing_count": len(missing),
        "aliases": aliases,
        "excluded": excluded,
        "missing": missing,
    }
