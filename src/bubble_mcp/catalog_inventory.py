"""Deterministic inventory of public MCP tools and legacy CLI commands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import json
from typing import Any, Literal


Relationship = Literal["direct", "alias", "excluded", "mcp_only"]


@dataclass(frozen=True, slots=True)
class CatalogInventoryRecord:
    mcp_tool: str | None
    legacy_command: str | None
    relationship: Relationship
    canonical_mcp_tool: str | None
    selection_case_id: str | None
    selection_query: str | None
    essential_args: tuple[str, ...]
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["essential_args"] = list(self.essential_args)
        return payload


def _required_args(schema: Mapping[str, Any]) -> tuple[str, ...]:
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, Mapping):
        return ()
    required = input_schema.get("required", ())
    if not isinstance(required, Iterable) or isinstance(required, (bytes, str)):
        return ()
    return tuple(sorted(str(argument) for argument in required))


def _sort_key(record: CatalogInventoryRecord) -> tuple[str, str]:
    return (record.mcp_tool or "~", record.legacy_command or "")


def build_catalog_inventory(
    tool_schemas: Iterable[Mapping[str, Any]],
    *,
    cli_commands: Iterable[str] | None = None,
    strict: bool = True,
) -> tuple[CatalogInventoryRecord, ...]:
    """Build a stable mapping of MCP tools and legacy CLI commands.

    Strict construction fails closed when a legacy command cannot be mapped.
    Diagnostic callers may opt out to retain records for the mapped surface.
    """

    from bubble_mcp.catalog_audit import (
        LEGACY_CLI_ALIASES,
        LEGACY_CLI_EXCLUSIONS,
        legacy_cli_commands,
    )

    tools: dict[str, Mapping[str, Any]] = {}
    for schema in tool_schemas:
        name = schema.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("MCP tool name must be non-empty")
        if name in tools:
            raise ValueError(f"duplicate MCP tool: {name}")
        tools[name] = schema

    commands = tuple(legacy_cli_commands() if cli_commands is None else cli_commands)
    seen_commands: set[str] = set()
    for command in commands:
        if command in seen_commands:
            raise ValueError(f"duplicate legacy CLI command: {command}")
        seen_commands.add(command)

    records: list[CatalogInventoryRecord] = []
    mapped_tools: set[str] = set()
    for command in commands:
        normalized = command.replace("-", "_")
        if normalized in tools:
            mapped_tools.add(normalized)
            records.append(
                CatalogInventoryRecord(
                    mcp_tool=normalized,
                    legacy_command=command,
                    relationship="direct",
                    canonical_mcp_tool=None,
                    selection_case_id=f"catalog.exact.{normalized}",
                    selection_query=normalized,
                    essential_args=_required_args(tools[normalized]),
                )
            )
            continue

        alias_target = LEGACY_CLI_ALIASES.get(command)
        if alias_target is not None:
            if alias_target not in tools:
                if strict:
                    raise ValueError(
                        f"legacy CLI alias target is absent: {command} -> {alias_target}"
                    )
                continue
            mapped_tools.add(alias_target)
            records.append(
                CatalogInventoryRecord(
                    mcp_tool=alias_target,
                    legacy_command=command,
                    relationship="alias",
                    canonical_mcp_tool=alias_target,
                    selection_case_id=f"catalog.exact.{alias_target}",
                    selection_query=alias_target,
                    essential_args=_required_args(tools[alias_target]),
                )
            )
            continue

        reason = LEGACY_CLI_EXCLUSIONS.get(command)
        if reason is not None:
            records.append(
                CatalogInventoryRecord(
                    mcp_tool=None,
                    legacy_command=command,
                    relationship="excluded",
                    canonical_mcp_tool=None,
                    selection_case_id=None,
                    selection_query=None,
                    essential_args=(),
                    reason=reason,
                )
            )
            continue

        if strict:
            raise ValueError(f"unmapped legacy CLI command: {command}")

    for name, schema in tools.items():
        if name not in mapped_tools:
            records.append(
                CatalogInventoryRecord(
                    mcp_tool=name,
                    legacy_command=None,
                    relationship="mcp_only",
                    canonical_mcp_tool=None,
                    selection_case_id=f"catalog.exact.{name}",
                    selection_query=name,
                    essential_args=_required_args(schema),
                )
            )

    return tuple(sorted(records, key=_sort_key))


def serialize_catalog_inventory(records: Iterable[CatalogInventoryRecord]) -> str:
    ordered = sorted(records, key=lambda record: (record.mcp_tool or "", record.legacy_command or ""))
    return json.dumps([record.to_dict() for record in ordered], indent=2, sort_keys=True) + "\n"
