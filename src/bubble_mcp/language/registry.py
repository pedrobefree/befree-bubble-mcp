"""Dynamic low-token registry for the Bubble MCP language."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from bubble_mcp.learning.store import list_learning_records
from bubble_mcp.runtime_coverage import catalog_coverage_report, classify_tool
from bubble_mcp.server.agent_catalog import _documentation_family_for_name
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.skills.store import list_skills


RUNTIME_RULES_DIGEST = [
    "Call bubble_task_runbook or bubble_language_query instead of dumping the full catalog.",
    "Use preview-first execution: execute=false before any Bubble mutation.",
    "Use the configured profile app_version unless the user explicitly overrides it.",
    "Resolve targets from real context; do not invent Bubble ids.",
    "Refresh profile cache and verify context after successful writes.",
    "Use bubble_framework_sync_evidence after preview, execution, or validation.",
]

LANGUAGE_ENTRYPOINTS = [
    "bubble_language_index",
    "bubble_language_query",
    "bubble_language_tool_detail",
    "bubble_language_diff",
    "bubble_framework_language_pack",
    "bubble_framework_compile_program",
    "bubble_task_runbook",
    "bubble_tool_search",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _schema_required(tool: dict[str, Any]) -> tuple[str, ...]:
    input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    required = input_schema.get("required") if isinstance(input_schema, dict) else []
    return tuple(str(item) for item in required) if isinstance(required, list) else ()


def _schema_properties(tool: dict[str, Any]) -> tuple[str, ...]:
    input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else {}
    return tuple(sorted(str(key) for key in properties)) if isinstance(properties, dict) else ()


def _risk_from_annotations(tool: dict[str, Any]) -> str:
    raw_annotations = tool.get("annotations")
    annotations: dict[str, Any] = raw_annotations if isinstance(raw_annotations, dict) else {}
    if bool(annotations.get("destructiveHint")):
        return "destructive"
    if bool(annotations.get("readOnlyHint")):
        return "read_only"
    return "mutating"


def _schema_hash(tool: dict[str, Any]) -> str:
    body = json.dumps(tool.get("inputSchema") or {}, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _tool_entry(tool: dict[str, Any], coverage_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    name = str(tool.get("name") or "")
    raw_annotations = tool.get("annotations")
    annotations: dict[str, Any] = raw_annotations if isinstance(raw_annotations, dict) else {}
    coverage: dict[str, Any] = coverage_by_name.get(name) or classify_tool(name)
    source = "extension" if coverage.get("coverage") == "extension_preview" else "native"
    family = _documentation_family_for_name(name)
    return {
        "name": name,
        "family": family,
        "source": source,
        "risk": _risk_from_annotations(tool),
        "read_only": bool(annotations.get("readOnlyHint")),
        "destructive": bool(annotations.get("destructiveHint")),
        "required": list(_schema_required(tool)),
        "properties": list(_schema_properties(tool)),
        "description": str(tool.get("description") or ""),
        "coverage": coverage.get("coverage"),
        "engine": coverage.get("engine"),
        "schema_hash": _schema_hash(tool),
    }


def _registry_version(entries: list[dict[str, Any]], *, skill_count: int, learning_count: int) -> str:
    version_payload = {
        "tools": [
            {
                "name": entry["name"],
                "schema_hash": entry["schema_hash"],
                "family": entry["family"],
                "source": entry["source"],
                "risk": entry["risk"],
            }
            for entry in sorted(entries, key=lambda item: item["name"])
        ],
        "skill_count": skill_count,
        "learning_count": learning_count,
        "rules": RUNTIME_RULES_DIGEST,
    }
    body = json.dumps(version_payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def current_language_entries() -> list[dict[str, Any]]:
    coverage_report = catalog_coverage_report(include_tools=True)
    coverage_by_name = {
        str(item.get("tool") or ""): item
        for item in coverage_report.get("tools", [])
        if isinstance(item, dict)
    }
    return [_tool_entry(tool, coverage_by_name) for tool in list_tool_schemas()]


def build_language_index(*, profile: str | None = None) -> dict[str, Any]:
    entries = current_language_entries()
    skills = list_skills()
    learning = list_learning_records()
    family_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for entry in entries:
        family_counts[str(entry["family"])] = family_counts.get(str(entry["family"]), 0) + 1
        source_counts[str(entry["source"])] = source_counts.get(str(entry["source"]), 0) + 1
        risk_counts[str(entry["risk"])] = risk_counts.get(str(entry["risk"]), 0) + 1
    return {
        "ok": True,
        "language": "bubble-mcp",
        "detail": "index",
        "profile": profile,
        "generated_at": _utc_now_iso(),
        "registry_version": _registry_version(entries, skill_count=len(skills), learning_count=len(learning)),
        "counts": {
            "tools": len(entries),
            "skills": len(skills),
            "learning_records": len(learning),
        },
        "families": family_counts,
        "sources": source_counts,
        "risks": risk_counts,
        "runtime_rules_digest": RUNTIME_RULES_DIGEST,
        "entrypoints": LANGUAGE_ENTRYPOINTS,
    }
