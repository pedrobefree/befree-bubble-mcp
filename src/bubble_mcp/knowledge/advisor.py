"""Selective knowledge advisor for agent and harness flows."""

from __future__ import annotations

import os
import re
from typing import Any

from bubble_mcp.knowledge.cache import knowledge_search, store_knowledge_records
from bubble_mcp.knowledge.models import KnowledgeRecord
from bubble_mcp.knowledge.remote import fetch_remote_records
from bubble_mcp.knowledge.sanitize import sanitize_remote_docs_query


FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
REMOTE_ENV = "BUBBLE_MCP_KNOWLEDGE_REMOTE"

STRUCTURAL_TERMS = (
    "field",
    "campo",
    "data type",
    "datatype",
    "schema",
    "privacy",
    "privacidade",
    "workflow",
    "branch",
    "changelog",
)
AMBIGUITY_TERMS = (
    "api connector",
    "privacy rule",
    "privacy rules",
    "data source",
    "datasource",
    "workflow",
    "permission",
    "permissions",
    "responsive",
    "condition",
    "conditional",
    "param",
    "parameter",
    "field",
    "tipo",
)
BEST_PRACTICE_TERMS = (
    "best practice",
    "melhor prática",
    "melhores práticas",
    "right way",
    "jeito certo",
    "documented",
    "documentado",
    "safe",
    "seguro",
    "should i",
    "devo",
    "como devo",
)
TOOL_AUTHORING_TERMS = ("tool wizard", "payload", "runner", "extension", "contract", "capture")
FAILURE_TERMS = ("error", "erro", "failed", "falhou", "blocked", "401", "not created", "não criou")


def remote_knowledge_enabled() -> bool:
    value = os.environ.get(REMOTE_ENV)
    if value is None:
        return True
    return value.strip().lower() not in FALSE_VALUES


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def detect_knowledge_triggers(
    *,
    task: str = "",
    tool_name: str = "",
    family: str = "",
    arguments: dict[str, Any] | None = None,
    error: str | None = None,
    validation_result: dict[str, Any] | None = None,
) -> list[str]:
    """Detect whether a task deserves knowledge lookup."""

    args_text = " ".join(str(key) for key in (arguments or {}).keys())
    validation_text = str(validation_result or "")
    haystack = _normalize(" ".join([task, tool_name, family, args_text, str(error or ""), validation_text]))
    triggers: list[str] = []
    if not haystack:
        return triggers
    if error or _contains_any(haystack, FAILURE_TERMS):
        triggers.append("execution_or_validation_failure")
    if _contains_any(haystack, BEST_PRACTICE_TERMS):
        triggers.append("best_practice_question")
    if _contains_any(haystack, TOOL_AUTHORING_TERMS):
        triggers.append("tool_authoring")
    if _contains_any(haystack, STRUCTURAL_TERMS):
        triggers.append("structural_action")
    if _contains_any(haystack, AMBIGUITY_TERMS):
        triggers.append("schema_or_parameter_ambiguity")
    if family in {"unknown", "ambiguous"}:
        triggers.append("low_routing_confidence")
    return list(dict.fromkeys(triggers))


def _queries(task: str, tool_name: str, family: str, triggers: list[str]) -> list[str]:
    base = sanitize_remote_docs_query(" ".join(part for part in (task, tool_name, family) if part))
    candidates: list[str] = []
    if base:
        candidates.append(base)
    if "structural_action" in triggers:
        candidates.append("Bubble schema data type field privacy workflow editor write validation")
    if "schema_or_parameter_ambiguity" in triggers:
        candidates.append("Bubble API Connector privacy rules data sources workflow parameters")
    if "execution_or_validation_failure" in triggers:
        candidates.append("Bubble editor write failed materialization validation refresh")
    if "best_practice_question" in triggers:
        candidates.append("Bubble best practices documented behavior")
    return list(dict.fromkeys(query for query in candidates if query))[:3]


def _trust_level(record: dict[str, Any] | KnowledgeRecord) -> str:
    source = record.source if isinstance(record, KnowledgeRecord) else str(record.get("source") or "")
    confidence = record.confidence if isinstance(record, KnowledgeRecord) else str(record.get("confidence") or "")
    if "forum" in source or "community" in confidence:
        return "community"
    return "official"


def _source_mix(records: list[dict[str, Any]]) -> list[str]:
    mix: list[str] = []
    for record in records:
        trust = _trust_level(record)
        value = "community_forum" if trust == "community" else "official_docs"
        if value not in mix:
            mix.append(value)
    return mix


def _guidance_from_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    guidance: list[dict[str, Any]] = []
    for result in results[:8]:
        trust = _trust_level(result)
        guidance.append(
            {
                "id": result.get("id"),
                "title": result.get("title"),
                "summary": result.get("summary"),
                "source_id": result.get("source"),
                "source_url": result.get("source_url"),
                "trust_level": trust,
                "retrieved_at": result.get("retrieved_at"),
                "confidence": result.get("confidence"),
            }
        )
    return guidance


def _results_from_records(records: list[KnowledgeRecord]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for record in records:
        results.append(
            {
                "id": record.id,
                "source": record.source,
                "source_url": record.source_url,
                "title": record.title,
                "section_path": list(record.section_path),
                "summary": record.summary,
                "tags": list(record.tags),
                "score": 1,
                "retrieved_at": record.retrieved_at,
                "content_hash": record.content_hash,
                "confidence": record.confidence,
            }
        )
    return results


def _decision_effect(triggers: list[str], results: list[dict[str, Any]]) -> str:
    if not results:
        return "none"
    if "execution_or_validation_failure" in triggers:
        return "validation_requirement"
    if "structural_action" in triggers:
        return "validation_requirement"
    if "best_practice_question" in triggers:
        return "answer_support"
    if "schema_or_parameter_ambiguity" in triggers:
        return "schema_hint"
    if any(_trust_level(record) == "community" for record in results):
        return "recommendation_adjustment"
    return "answer_support"


def _confidence(results: list[dict[str, Any]]) -> str:
    has_official = any(_trust_level(record) == "official" for record in results)
    has_community = any(_trust_level(record) == "community" for record in results)
    if has_official and has_community:
        return "mixed"
    if has_official:
        return "official_cached"
    if has_community:
        return "community_observed"
    return "none"


def _warnings(results: list[dict[str, Any]], effect: str) -> list[str]:
    warnings: list[str] = []
    if any(_trust_level(record) == "community" for record in results):
        warnings.append(
            "Community knowledge adjusted recommendations only; keep preview and validation gates before real writes."
        )
    text = " ".join(str(record.get("summary") or "") for record in results).lower()
    if "calculate_derived" in text or "derived" in text:
        warnings.append("Knowledge indicates this flow may require derived-state refresh or context verification after write.")
    if effect == "validation_requirement":
        warnings.append("Run additional validation before considering this task complete.")
    return list(dict.fromkeys(warnings))


def _recommended_next_steps(effect: str) -> list[str]:
    if effect == "validation_requirement":
        return [
            "Preview first unless the user explicitly requested execution.",
            "Refresh context after execute=true.",
            "Verify materialization with context/changelog/smoke evidence.",
        ]
    if effect == "schema_hint":
        return ["Use knowledge guidance as a parameter hint, then validate against current project context."]
    if effect == "recommendation_adjustment":
        return ["Treat community guidance as advisory and verify locally before changing execution contracts."]
    if effect == "answer_support":
        return ["Answer with source attribution and confidence."]
    return []


def _local_results(queries: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        payload = knowledge_search(query, limit=5)
        if not payload.get("ok"):
            continue
        for result in payload.get("results", []):
            record_id = str(result.get("id") or "")
            if record_id and record_id not in seen:
                results.append(result)
                seen.add(record_id)
    return results


def knowledge_advice(
    *,
    task: str = "",
    tool_name: str = "",
    family: str = "",
    profile: str = "",
    context: str = "",
    arguments: dict[str, Any] | None = None,
    error: str | None = None,
    validation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return compact source-attributed knowledge advice for agent flows."""

    del profile, context
    triggers = detect_knowledge_triggers(
        task=task,
        tool_name=tool_name,
        family=family,
        arguments=arguments,
        error=error,
        validation_result=validation_result,
    )
    remote_enabled = remote_knowledge_enabled()
    if not triggers:
        return {
            "used": False,
            "reason": "no_trigger",
            "remote_enabled": remote_enabled,
            "triggers": [],
            "suggested_queries": [],
            "missing_knowledge_topics": [],
        }

    queries = _queries(task, tool_name, family, triggers)
    local_results = _local_results(queries)
    remote_used = False
    results = local_results
    if not results and remote_enabled:
        try:
            remote_records = fetch_remote_records(queries=queries, max_records=8)
        except Exception as exc:  # pragma: no cover - network variability is handled as degraded advice
            return {
                "used": False,
                "reason": "remote_knowledge_error",
                "remote_enabled": remote_enabled,
                "remote_used": True,
                "error": str(exc),
                "triggers": triggers,
                "suggested_queries": queries,
                "missing_knowledge_topics": queries,
            }
        if remote_records:
            store_knowledge_records(remote_records)
            results = _results_from_records(remote_records)
            remote_used = True

    if not results:
        return {
            "used": False,
            "reason": "local_and_remote_knowledge_missing" if remote_enabled else "local_knowledge_missing",
            "remote_enabled": remote_enabled,
            "remote_used": remote_used,
            "triggers": triggers,
            "suggested_queries": queries,
            "missing_knowledge_topics": queries,
        }

    effect = _decision_effect(triggers, results)
    return {
        "used": True,
        "remote_used": remote_used,
        "remote_enabled": remote_enabled,
        "triggers": triggers,
        "queries": queries,
        "source_mix": _source_mix(results),
        "confidence": _confidence(results),
        "decision_effect": effect,
        "guidance": _guidance_from_results(results),
        "warnings": _warnings(results, effect),
        "recommended_next_steps": _recommended_next_steps(effect),
        "missing_knowledge_topics": [],
        "execute_authorized": False,
    }
