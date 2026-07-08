"""Scoped lookup APIs for the Bubble MCP language registry."""

from __future__ import annotations

from typing import Any

from bubble_mcp.language.registry import build_language_index, current_language_entries
from bubble_mcp.server.schemas import list_tool_schemas


def _score_entry(entry: dict[str, Any], query: str) -> int:
    haystack = " ".join(
        [
            str(entry.get("name") or ""),
            str(entry.get("family") or ""),
            str(entry.get("description") or ""),
            " ".join(str(item) for item in entry.get("required", [])),
            " ".join(str(item) for item in entry.get("properties", [])),
        ]
    ).lower()
    terms = [term for term in query.lower().replace("_", " ").split() if term]
    return sum(3 if term in str(entry.get("name") or "").lower() else 1 for term in terms if term in haystack)


def _compact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        key: entry[key]
        for key in (
            "name",
            "family",
            "source",
            "risk",
            "read_only",
            "destructive",
            "required",
            "properties",
            "description",
            "coverage",
            "schema_hash",
        )
        if key in entry
    }


def language_query(
    *,
    query: str,
    families: list[str] | None = None,
    sources: list[str] | None = None,
    risks: list[str] | None = None,
    limit: int = 12,
    profile: str | None = None,
) -> dict[str, Any]:
    entries = current_language_entries()
    if families:
        family_set = {str(item) for item in families}
        entries = [entry for entry in entries if entry.get("family") in family_set]
    if sources:
        source_set = {str(item) for item in sources}
        entries = [entry for entry in entries if entry.get("source") in source_set]
    if risks:
        risk_set = {str(item) for item in risks}
        entries = [entry for entry in entries if entry.get("risk") in risk_set]
    scored = [(entry, _score_entry(entry, query)) for entry in entries]
    matches = [entry for entry, score in sorted(scored, key=lambda item: (-item[1], item[0]["name"])) if score > 0]
    if not matches and not query.strip():
        matches = sorted(entries, key=lambda item: item["name"])
    index = build_language_index(profile=profile)
    return {
        "ok": True,
        "language": "bubble-mcp",
        "detail": "compact",
        "registry_version": index["registry_version"],
        "query": query,
        "families": families or [],
        "sources": sources or [],
        "risks": risks or [],
        "limit": limit,
        "matches": [_compact_entry(entry) for entry in matches[: max(1, min(limit, 50))]],
    }


def language_tool_detail(tool_names: list[str], *, detail: str = "compact") -> dict[str, Any]:
    requested = [str(name) for name in tool_names if str(name).strip()]
    schemas = {str(tool.get("name") or ""): tool for tool in list_tool_schemas()}
    entries = {str(entry.get("name") or ""): entry for entry in current_language_entries()}
    tools: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in requested:
        schema = schemas.get(name)
        entry = entries.get(name)
        if schema is None or entry is None:
            missing.append(name)
            continue
        if detail == "full":
            tools.append({**schema, "language": {key: value for key, value in entry.items() if key != "description"}})
        else:
            tools.append(_compact_entry(entry))
    return {"ok": not missing, "detail": detail, "tools": tools, "missing": missing}
