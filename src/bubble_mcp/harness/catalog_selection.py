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


def _schema_required_names(schema: Mapping[str, Any]) -> list[str]:
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, Mapping):
        return []
    required = input_schema.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(name) for name in required)


def _schema_failure(
    *,
    case_id: str,
    failure_type: str,
    expected_tool: str,
    actual_tool: str,
    essential_args: list[str],
    actual_required: list[str],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "query": expected_tool,
        "expected_tool": expected_tool,
        "actual_tool": actual_tool,
        "reordered_actual_tool": actual_tool,
        "essential_args": essential_args,
        "actual_required": actual_required,
        "canonical_ok": False,
        "reordered_ok": False,
        "order_independent": False,
        "failure_type": failure_type,
    }


def catalog_selection_report(
    tool_schemas: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return deterministic exact-selection evidence for every exposed MCP tool."""

    authoritative_schemas = sorted((dict(schema) for schema in list_tool_schemas()), key=_schema_name)
    canonical_schemas = (
        authoritative_schemas
        if tool_schemas is None
        else sorted((dict(schema) for schema in tool_schemas), key=_schema_name)
    )
    records = _canonical_records(build_catalog_inventory(authoritative_schemas))
    inventory_tools = {record.mcp_tool for record in records if record.mcp_tool is not None}
    essential_args_by_tool = {
        record.mcp_tool: list(record.essential_args)
        for record in records
        if record.mcp_tool is not None
    }
    candidate_by_tool: dict[str, Mapping[str, Any]] = {}
    candidate_counts: dict[str, int] = {}
    for schema in canonical_schemas:
        name = _schema_name(schema)
        candidate_by_tool.setdefault(name, schema)
        candidate_counts[name] = candidate_counts.get(name, 0) + 1

    schema_failures: list[dict[str, Any]] = []
    for name in sorted(inventory_tools - candidate_by_tool.keys()):
        schema_failures.append(
            _schema_failure(
                case_id=f"catalog.schema.missing.{name}",
                failure_type="missing_schema",
                expected_tool=name,
                actual_tool="",
                essential_args=essential_args_by_tool[name],
                actual_required=[],
            )
        )
    for name in sorted(candidate_by_tool.keys() - inventory_tools):
        schema_failures.append(
            _schema_failure(
                case_id=f"catalog.schema.extra.{name}",
                failure_type="extra_schema",
                expected_tool="",
                actual_tool=name,
                essential_args=[],
                actual_required=_schema_required_names(candidate_by_tool[name]),
            )
        )
    for name in sorted(inventory_tools & candidate_by_tool.keys()):
        actual_required = _schema_required_names(candidate_by_tool[name])
        if actual_required != essential_args_by_tool[name]:
            schema_failures.append(
                _schema_failure(
                    case_id=f"catalog.schema.contract.{name}",
                    failure_type="contract_mismatch",
                    expected_tool=name,
                    actual_tool=name,
                    essential_args=essential_args_by_tool[name],
                    actual_required=actual_required,
                )
            )
    for name in sorted(name for name, count in candidate_counts.items() if count > 1):
        schema_failures.append(
            _schema_failure(
                case_id=f"catalog.schema.duplicate.{name}",
                failure_type="duplicate_schema",
                expected_tool=name if name in inventory_tools else "",
                actual_tool=name,
                essential_args=essential_args_by_tool.get(name, []),
                actual_required=_schema_required_names(candidate_by_tool[name]),
            )
        )
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
    failures = schema_failures + [
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
    failures.sort(key=lambda result: str(result["case_id"]))
    return {
        "ok": not failures and summary["missing_cases"] == 0 and len(results) == len(inventory_tools),
        "summary": summary,
        "results": results,
        "failures": failures,
    }
