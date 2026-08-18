"""Repeatable parity checks between the packaged Bubble CLI and MCP catalog."""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from bubble_mcp.catalog_inventory import build_catalog_inventory


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

    records = build_catalog_inventory(
        {"name": str(name), "inputSchema": {}} for name in catalog_names
    )
    direct = [
        {"command": record.legacy_command, "tool": record.mcp_tool}
        for record in records
        if record.relationship == "direct"
        and record.legacy_command is not None
        and record.mcp_tool is not None
    ]
    aliases = [
        {"command": record.legacy_command, "tool": record.canonical_mcp_tool}
        for record in records
        if record.relationship == "alias"
        and record.legacy_command is not None
        and record.canonical_mcp_tool is not None
    ]
    excluded = [
        {"command": record.legacy_command, "reason": record.reason}
        for record in records
        if record.relationship == "excluded"
        and record.legacy_command is not None
        and record.reason is not None
    ]
    missing: list[dict[str, str]] = []
    mcp_only_count = sum(record.relationship == "mcp_only" for record in records)
    mcp_tool_count = len({record.mcp_tool for record in records if record.mcp_tool is not None})

    return {
        "ok": not missing,
        "cli_command_count": sum(record.legacy_command is not None for record in records),
        "direct_match_count": len(direct),
        "alias_count": len(aliases),
        "excluded_count": len(excluded),
        "missing_count": len(missing),
        "mcp_tool_count": mcp_tool_count,
        "mcp_only_count": mcp_only_count,
        "aliases": aliases,
        "excluded": excluded,
        "missing": missing,
    }
