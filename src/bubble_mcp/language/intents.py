"""Dynamic intent catalog for compact Bubble MCP language programs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class IntentEntry:
    intent: str
    tool: str
    family: str
    description: str
    aliases: tuple[str, ...] = ()


INTENT_ENTRIES = (
    IntentEntry(
        "create_container",
        "create_group",
        "visual",
        "Create a visual container/group.",
        aliases=("create_group", "create_section", "create_card"),
    ),
    IntentEntry(
        "create_text",
        "create_text",
        "visual",
        "Create a text element.",
        aliases=("add_text", "headline", "create_heading"),
    ),
    IntentEntry(
        "create_button",
        "create_button",
        "visual",
        "Create a button element.",
        aliases=("add_button", "cta_button", "create_cta"),
    ),
    IntentEntry(
        "create_input",
        "create_input",
        "visual",
        "Create an input element.",
        aliases=("add_input", "text_input"),
    ),
    IntentEntry("create_data_type", "create_data_type", "data", "Create a Bubble data type."),
    IntentEntry(
        "create_field",
        "create_data_field",
        "data",
        "Create a field on a Bubble data type.",
        aliases=("create_data_field", "add_field"),
    ),
    IntentEntry(
        "create_custom_event",
        "create_event",
        "workflow",
        "Create a Bubble custom workflow event.",
        aliases=("create_event", "add_custom_event"),
    ),
    IntentEntry("add_workflow_action", "add_action", "workflow", "Add a workflow action."),
    IntentEntry(
        "create_api_call",
        "create_api_connector_resource",
        "api_connector",
        "Create an API Connector resource call.",
        aliases=("create_api_connector_resource", "api_call"),
    ),
    IntentEntry("update_style", "update_style", "style", "Update an existing Bubble style."),
    IntentEntry("create_reusable", "create_reusable", "reusable", "Create a reusable element."),
    IntentEntry(
        "transfer_bundle",
        "bubble_transfer_execute",
        "migration",
        "Execute a prepared transfer bundle.",
    ),
    IntentEntry(
        "performance_audit",
        "bubble_performance_audit",
        "performance",
        "Run a Bubble performance audit.",
    ),
    IntentEntry(
        "verify_context",
        "bubble_context_find",
        "verification",
        "Find or verify entries in the Bubble context.",
        aliases=("resolve_context", "find_context"),
    ),
    IntentEntry(
        "refresh_context",
        "bubble_profile_cache_refresh",
        "verification",
        "Refresh the cached Bubble profile context.",
    ),
    IntentEntry(
        "query_language",
        "bubble_language_query",
        "verification",
        "Query the Bubble MCP language registry.",
        aliases=("find_tool",),
    ),
    IntentEntry(
        "sync_evidence",
        "bubble_framework_sync_evidence",
        "verification",
        "Sync framework execution or validation evidence.",
    ),
)


def _catalog() -> dict[str, IntentEntry]:
    catalog: dict[str, IntentEntry] = {}
    for entry in INTENT_ENTRIES:
        catalog[entry.intent] = entry
        for alias in entry.aliases:
            catalog[alias] = replace(entry, intent=alias)
    return catalog


INTENT_CATALOG = _catalog()


def tool_for_intent(intent: str) -> str:
    entry = INTENT_CATALOG.get(str(intent or "").strip())
    return entry.tool if entry else ""


def _copy_first_available(args: dict[str, Any], target: str, candidates: tuple[str, ...]) -> None:
    if args.get(target) not in (None, ""):
        return
    for candidate in candidates:
        value = args.get(candidate)
        if value not in (None, ""):
            args[target] = value
            return


def normalize_intent_arguments(intent: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    tool_name = tool_for_intent(intent) or str(intent or "").strip()
    if tool_name == "create_text":
        _copy_first_available(normalized, "content", ("text", "label", "title", "name"))
    elif tool_name == "create_button":
        _copy_first_available(normalized, "label", ("text", "content", "title", "name"))
    elif tool_name in {"create_group", "create_input"}:
        _copy_first_available(normalized, "name", ("label", "title", "text", "content"))
    elif tool_name == "create_data_field":
        _copy_first_available(normalized, "data_type_ref", ("data_type", "data_type_name"))
        _copy_first_available(normalized, "type", ("field_type", "data_class", "data_type_ref"))
    elif tool_name == "create_event":
        _copy_first_available(normalized, "name", ("label", "title", "event_name"))
        _copy_first_available(normalized, "custom_event_name", ("name", "label", "title", "event_name"))
        if "event_type" not in normalized:
            normalized["event_type"] = "CustomEvent"
    elif tool_name == "create_api_connector_resource":
        _copy_first_available(normalized, "name", ("label", "title", "call_name"))
        _copy_first_available(normalized, "method", ("verb", "http_method"))
        _copy_first_available(normalized, "url", ("endpoint", "uri"))
    elif tool_name == "bubble_context_find":
        _copy_first_available(normalized, "query", ("target", "selector", "description", "name"))
        if "include_metadata" not in normalized:
            normalized["include_metadata"] = False
        if "limit" not in normalized:
            normalized["limit"] = 5
    elif tool_name == "bubble_profile_cache_refresh":
        if "force" not in normalized:
            normalized["force"] = True
    elif tool_name == "bubble_language_query":
        _copy_first_available(normalized, "query", ("target", "selector", "description", "name"))
        if "limit" not in normalized:
            normalized["limit"] = 8
    elif tool_name == "bubble_framework_sync_evidence" and "evidence" not in normalized:
        evidence = normalized.get("result") or normalized.get("summary") or normalized.get("description")
        if evidence not in (None, ""):
            normalized["evidence"] = evidence
    return normalized


def language_intent_families() -> dict[str, list[str]]:
    families: dict[str, list[str]] = {}
    for entry in INTENT_ENTRIES:
        families.setdefault(entry.family, []).append(entry.intent)
    return {family: sorted(intents) for family, intents in sorted(families.items())}
