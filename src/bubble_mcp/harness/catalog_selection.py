"""Deterministic selection coverage for the exposed MCP catalog."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from bubble_mcp.catalog_inventory import CatalogInventoryRecord, build_catalog_inventory
from bubble_mcp.server.agent_guide import search_tool_catalog
from bubble_mcp.server.schemas import list_tool_schemas


_RELATIONSHIP_PRECEDENCE = {"direct": 0, "alias": 1, "mcp_only": 2}


def _schema_name(schema: Mapping[str, Any]) -> str:
    return str(schema.get("name") or "")


def _canonical_records(
    records: Iterable[CatalogInventoryRecord],
) -> list[CatalogInventoryRecord]:
    by_tool: dict[str, CatalogInventoryRecord] = {}
    for record in records:
        if record.mcp_tool is None:
            continue
        current = by_tool.get(record.mcp_tool)
        if current is None or _RELATIONSHIP_PRECEDENCE[record.relationship] < _RELATIONSHIP_PRECEDENCE[
            current.relationship
        ]:
            by_tool[record.mcp_tool] = record
    return [by_tool[name] for name in sorted(by_tool)]


def _first_match(search: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = search.get("matches")
    if not isinstance(matches, list) or not matches:
        return {}
    first = matches[0]
    return first if isinstance(first, Mapping) else {}


def _required_names(match: Mapping[str, Any]) -> list[str]:
    required = match.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(name) for name in required)


def catalog_selection_report(
    tool_schemas: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return deterministic exact-selection evidence for every exposed MCP tool."""

    schemas = list_tool_schemas() if tool_schemas is None else tool_schemas
    canonical_schemas = sorted((dict(schema) for schema in schemas), key=_schema_name)
    records = _canonical_records(build_catalog_inventory(canonical_schemas))
    inventory_tools = {record.mcp_tool for record in records if record.mcp_tool is not None}
    results: list[dict[str, Any]] = []

    for record in records:
        expected_tool = record.mcp_tool
        query = record.selection_query
        if expected_tool is None or query is None or record.selection_case_id is None:
            continue
        canonical_match = _first_match(
            search_tool_catalog(query, limit=1, tool_schemas=canonical_schemas)
        )
        reordered_match = _first_match(
            search_tool_catalog(query, limit=1, tool_schemas=list(reversed(canonical_schemas)))
        )
        actual_tool = str(canonical_match.get("name") or "")
        reordered_actual_tool = str(reordered_match.get("name") or "")
        essential_args = list(record.essential_args)
        actual_required = _required_names(canonical_match)
        canonical_ok = actual_tool == expected_tool and actual_required == essential_args
        reordered_ok = reordered_actual_tool == expected_tool
        order_independent = actual_tool == reordered_actual_tool
        results.append(
            {
                "case_id": record.selection_case_id,
                "query": query,
                "expected_tool": expected_tool,
                "actual_tool": actual_tool,
                "reordered_actual_tool": reordered_actual_tool,
                "essential_args": essential_args,
                "actual_required": actual_required,
                "canonical_ok": canonical_ok,
                "reordered_ok": reordered_ok,
                "order_independent": order_independent,
            }
        )

    results.sort(key=lambda result: str(result["expected_tool"]))
    failures = [
        result
        for result in results
        if not (
            result["canonical_ok"]
            and result["reordered_ok"]
            and result["order_independent"]
        )
    ]
    summary = {
        "tool_count": len(inventory_tools),
        "case_count": len(results),
        "canonical_ok": sum(result["canonical_ok"] for result in results),
        "reordered_ok": sum(result["reordered_ok"] for result in results),
        "order_independent": sum(result["order_independent"] for result in results),
        "missing_cases": max(0, len(inventory_tools) - len(results)),
        "failed_cases": len(failures),
    }
    return {
        "ok": not failures and summary["missing_cases"] == 0 and len(results) == len(inventory_tools),
        "summary": summary,
        "results": results,
        "failures": failures,
    }
