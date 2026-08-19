"""Deterministic natural-language ambiguity coverage for the MCP catalog."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

from bubble_mcp.server.agent_guide import search_tool_catalog
from bubble_mcp.server.schemas import list_tool_schemas


DEFAULT_AMBIGUITY_RESOURCE = files("bubble_mcp.harness").joinpath(
    "data/catalog_ambiguity.json"
)
EXPECTED_AMBIGUITY_CASE_COUNT = 27

AMBIGUITY_FAMILIES = frozenset(
    {
        "cache_routing",
        "source_builders",
        "figma_sync",
        "visual_updates",
        "reusable",
        "deletion",
        "workflow",
        "html_import",
    }
)


def _schema_name(schema: Mapping[str, Any]) -> str:
    return str(schema.get("name") or "").strip()


def _required_names(schema: Mapping[str, Any]) -> list[str]:
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, Mapping):
        return []
    required = input_schema.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(name) for name in required)


def _required_from_match(match: Mapping[str, Any]) -> list[str]:
    required = match.get("required")
    if not isinstance(required, list):
        return []
    return sorted(str(name) for name in required)


def _normalize_cases(payload: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_queries: set[str] = set()
    for index, raw_case in enumerate(payload):
        if not isinstance(raw_case, Mapping):
            raise ValueError(f"case at index {index} must be an object")
        case_id = str(raw_case.get("id") or "").strip()
        family = str(raw_case.get("family") or "").strip()
        query = str(raw_case.get("query") or "").strip()
        expected_tool = str(raw_case.get("expected_tool") or "").strip()
        raw_contrasts = raw_case.get("contrast_tools")
        if not case_id:
            raise ValueError(f"case at index {index} must have a non-empty id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        if family not in AMBIGUITY_FAMILIES:
            raise ValueError(f"{case_id}: unknown family {family}")
        if not query:
            raise ValueError(f"{case_id}: query must be non-empty")
        normalized_query = " ".join(query.casefold().split())
        if normalized_query in seen_queries:
            raise ValueError(f"duplicate query in case {case_id}")
        if not expected_tool:
            raise ValueError(f"{case_id}: expected_tool must be non-empty")
        if not isinstance(raw_contrasts, list) or not raw_contrasts:
            raise ValueError(f"{case_id}: contrast_tools must be a non-empty list")
        contrasts = [str(name).strip() for name in raw_contrasts]
        if any(not name for name in contrasts):
            raise ValueError(f"{case_id}: contrast_tools cannot contain empty names")
        if len(contrasts) != len(set(contrasts)):
            raise ValueError(f"{case_id}: contrast_tools cannot contain duplicates")
        if expected_tool in contrasts:
            raise ValueError(f"{case_id}: expected tool cannot be a contrast tool")
        seen_ids.add(case_id)
        seen_queries.add(normalized_query)
        cases.append(
            {
                "id": case_id,
                "family": family,
                "query": query,
                "expected_tool": expected_tool,
                "contrast_tools": sorted(contrasts),
            }
        )
    return sorted(cases, key=lambda case: str(case["id"]))


def _validate_corpus_coverage(cases: list[dict[str, Any]]) -> None:
    if len(cases) != EXPECTED_AMBIGUITY_CASE_COUNT:
        raise ValueError(
            "ambiguity corpus must contain exactly "
            f"{EXPECTED_AMBIGUITY_CASE_COUNT} cases; got {len(cases)}"
        )
    actual_families = {str(case["family"]) for case in cases}
    if actual_families != AMBIGUITY_FAMILIES:
        missing = sorted(AMBIGUITY_FAMILIES - actual_families)
        extra = sorted(actual_families - AMBIGUITY_FAMILIES)
        raise ValueError(
            "ambiguity corpus family coverage mismatch: "
            f"missing={missing}, extra={extra}"
        )


def load_ambiguity_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Load and validate the checked-in natural-language ambiguity corpus."""

    raw_payload = (
        DEFAULT_AMBIGUITY_RESOURCE.read_text(encoding="utf-8")
        if path is None
        else path.read_text(encoding="utf-8")
    )
    payload = json.loads(raw_payload)
    if not isinstance(payload, list):
        raise ValueError("ambiguity dataset must be a JSON array")
    mappings: list[Mapping[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            raise ValueError(f"case at index {index} must be an object")
        mappings.append(item)
    cases = _normalize_cases(mappings)
    _validate_corpus_coverage(cases)
    return cases


def _match_evidence(search: Mapping[str, Any]) -> list[dict[str, Any]]:
    matches = search.get("matches")
    if not isinstance(matches, list):
        return []
    evidence: list[dict[str, Any]] = []
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        evidence.append(
            {
                "name": str(match.get("name") or ""),
                "score": int(match.get("score") or 0),
                "required": _required_from_match(match),
            }
        )
    return evidence


def _first_match(evidence: list[dict[str, Any]]) -> Mapping[str, Any]:
    return evidence[0] if evidence else {}


def catalog_ambiguity_report(
    tool_schemas: Iterable[Mapping[str, Any]] | None = None,
    cases: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate natural-language family selection across stable catalog orders."""

    authoritative_schemas = sorted((dict(schema) for schema in list_tool_schemas()), key=_schema_name)
    authoritative_by_name = {_schema_name(schema): schema for schema in authoritative_schemas}
    normalized_cases = load_ambiguity_cases() if cases is None else _normalize_cases(cases)
    _validate_corpus_coverage(normalized_cases)
    for case in normalized_cases:
        case_id = str(case["id"])
        expected_tool = str(case["expected_tool"])
        if expected_tool not in authoritative_by_name:
            raise ValueError(f"{case_id}: unknown expected tool {expected_tool}")
        unknown_contrasts = sorted(
            set(str(name) for name in case["contrast_tools"]) - authoritative_by_name.keys()
        )
        if unknown_contrasts:
            raise ValueError(
                f"{case_id}: unknown contrast tools {', '.join(unknown_contrasts)}"
            )

    canonical_schemas = (
        authoritative_schemas
        if tool_schemas is None
        else sorted((dict(schema) for schema in tool_schemas), key=_schema_name)
    )
    candidate_names = [_schema_name(schema) for schema in canonical_schemas]
    duplicate_names = sorted({name for name in candidate_names if candidate_names.count(name) > 1})
    if duplicate_names:
        raise ValueError(f"duplicate candidate schemas: {', '.join(duplicate_names)}")
    candidate_name_set = set(candidate_names)
    reversed_schemas = list(reversed(canonical_schemas))
    rotated_schemas = canonical_schemas[1:] + canonical_schemas[:1]
    results: list[dict[str, Any]] = []

    for case in normalized_cases:
        case_id = str(case["id"])
        family = str(case["family"])
        query = str(case["query"])
        expected_tool = str(case["expected_tool"])
        contrasts = [str(name) for name in case["contrast_tools"]]
        essential_args = _required_names(authoritative_by_name[expected_tool])
        missing_contrasts = sorted(set(contrasts) - candidate_name_set)
        if expected_tool not in candidate_name_set or missing_contrasts:
            schema_failure_type = (
                "missing_schema" if expected_tool not in candidate_name_set else "missing_contrast_schema"
            )
            results.append(
                {
                    "case_id": case_id,
                    "family": family,
                    "query": query,
                    "expected_tool": expected_tool,
                    "actual_tool": "",
                    "contrast_tools": contrasts,
                    "missing_contrast_tools": missing_contrasts,
                    "essential_args": essential_args,
                    "actual_required": [],
                    "canonical_matches": [],
                    "reversed_matches": [],
                    "rotated_matches": [],
                    "canonical_ok": False,
                    "reversed_ok": False,
                    "rotated_ok": False,
                    "order_independent": False,
                    "failure_type": schema_failure_type,
                }
            )
            continue

        canonical_matches = _match_evidence(
            search_tool_catalog(query, limit=5, tool_schemas=canonical_schemas)
        )
        reversed_matches = _match_evidence(
            search_tool_catalog(query, limit=5, tool_schemas=reversed_schemas)
        )
        rotated_matches = _match_evidence(
            search_tool_catalog(query, limit=5, tool_schemas=rotated_schemas)
        )
        canonical_first = _first_match(canonical_matches)
        reversed_first = _first_match(reversed_matches)
        rotated_first = _first_match(rotated_matches)
        actual_tool = str(canonical_first.get("name") or "")
        actual_required = _required_from_match(canonical_first)
        canonical_ok = actual_tool == expected_tool and actual_required == essential_args
        reversed_ok = (
            str(reversed_first.get("name") or "") == expected_tool
            and _required_from_match(reversed_first) == essential_args
        )
        rotated_ok = (
            str(rotated_first.get("name") or "") == expected_tool
            and _required_from_match(rotated_first) == essential_args
        )
        order_independent = canonical_matches == reversed_matches == rotated_matches
        failure_type: str | None = None
        if actual_tool != expected_tool:
            failure_type = "selection_mismatch"
        elif actual_required != essential_args:
            failure_type = "contract_mismatch"
        elif not reversed_ok or not rotated_ok or not order_independent:
            failure_type = "order_dependent"
        result = {
            "case_id": case_id,
            "family": family,
            "query": query,
            "expected_tool": expected_tool,
            "actual_tool": actual_tool,
            "contrast_tools": contrasts,
            "missing_contrast_tools": [],
            "essential_args": essential_args,
            "actual_required": actual_required,
            "canonical_matches": canonical_matches,
            "reversed_matches": reversed_matches,
            "rotated_matches": rotated_matches,
            "canonical_ok": canonical_ok,
            "reversed_ok": reversed_ok,
            "rotated_ok": rotated_ok,
            "order_independent": order_independent,
        }
        if failure_type is not None:
            result["failure_type"] = failure_type
        results.append(result)

    results.sort(key=lambda result: str(result["case_id"]))
    failures = [
        result
        for result in results
        if not (
            result["canonical_ok"]
            and result["reversed_ok"]
            and result["rotated_ok"]
            and result["order_independent"]
        )
    ]
    summary = {
        "case_count": len(results),
        "family_count": len({str(result["family"]) for result in results}),
        "canonical_ok": sum(bool(result["canonical_ok"]) for result in results),
        "reversed_ok": sum(bool(result["reversed_ok"]) for result in results),
        "rotated_ok": sum(bool(result["rotated_ok"]) for result in results),
        "order_independent": sum(bool(result["order_independent"]) for result in results),
        "failed_cases": len(failures),
    }
    return {
        "ok": not failures and len(results) == len(normalized_cases),
        "summary": summary,
        "results": results,
        "failures": failures,
    }
