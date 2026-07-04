"""MCP completion helpers for Bubble MCP clients."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from bubble_mcp.core.config import load_settings
from bubble_mcp.server.agent_guide import RECIPES
from bubble_mcp.server.prompts import PROMPTS
from bubble_mcp.server.schemas import list_tool_schemas


DEFAULT_CONTEXT_SUGGESTIONS = ["index", "root"]
DEFAULT_PARENT_SUGGESTIONS = ["root"]
BOOLEAN_SUGGESTIONS = ["false", "true"]
BOOLEAN_ARGUMENT_NAMES = {
    "cleanup",
    "confirm",
    "dry_run",
    "exact",
    "execute",
    "force",
    "include_details",
    "include_family_preview",
    "include_metadata",
    "include_profile_status",
    "refresh_context",
    "rendered_html",
    "skip_id_to_path",
    "stop_on_failure",
    "strict_validate",
    "verify_context",
}
APP_VERSION_ARGUMENT_NAMES = {"app_version", "from_app_version"}
APP_VERSION_SUGGESTIONS = ["test", "version-test"]
RUNTIME_SMOKE_SUITE_SUGGESTIONS = [
    "coverage",
    "agent-routing",
    "safe-read",
    "preview-write",
    "family-preview",
    "execute-write",
]


def _completion(values: list[str], prefix: str) -> dict[str, Any]:
    normalized_prefix = str(prefix or "").strip().lower()
    filtered = [
        value
        for value in values
        if not normalized_prefix or value.lower().startswith(normalized_prefix)
    ]
    return {
        "completion": {
            "values": filtered[:100],
            "total": len(filtered),
            "hasMore": len(filtered) > 100,
        }
    }


def _profile_names() -> list[str]:
    try:
        settings = load_settings()
    except Exception:
        return []
    return sorted(settings.profiles)


@lru_cache(maxsize=1)
def _tool_schema_by_name() -> dict[str, dict[str, Any]]:
    return {str(tool.get("name") or ""): tool for tool in list_tool_schemas()}


def _tool_names() -> list[str]:
    return sorted(_tool_schema_by_name())


def _schema_property(tool_name: str, argument_name: str) -> dict[str, Any]:
    schema = _tool_schema_by_name().get(tool_name, {})
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, dict):
        return {}
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    prop = properties.get(argument_name)
    return prop if isinstance(prop, dict) else {}


def _schema_suggestions(tool_name: str, argument_name: str) -> list[str]:
    prop = _schema_property(tool_name, argument_name)
    if not prop:
        if argument_name in APP_VERSION_ARGUMENT_NAMES:
            return APP_VERSION_SUGGESTIONS
        return []

    raw_type = prop.get("type")
    property_types = raw_type if isinstance(raw_type, list) else [raw_type]
    if "boolean" in property_types:
        return BOOLEAN_SUGGESTIONS

    values: list[str] = []
    for key in ("enum", "examples"):
        raw_values = prop.get(key)
        if isinstance(raw_values, list):
            values.extend(str(item) for item in raw_values if item is not None and str(item).strip())

    if not values and prop.get("default") is not None:
        values.append(str(prop["default"]))

    if not values and argument_name in APP_VERSION_ARGUMENT_NAMES:
        values.extend(APP_VERSION_SUGGESTIONS)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _completion_ref(params: dict[str, Any]) -> dict[str, Any]:
    raw_ref = params.get("ref")
    return raw_ref if isinstance(raw_ref, dict) else {}


def _completion_argument(params: dict[str, Any]) -> dict[str, Any]:
    raw_argument = params.get("argument")
    return raw_argument if isinstance(raw_argument, dict) else {}


def complete(params: dict[str, Any]) -> dict[str, Any]:
    """Return MCP completion suggestions for resources and prompts."""

    ref = _completion_ref(params)
    argument = _completion_argument(params)
    argument_name = str(argument.get("name") or "")
    value = str(argument.get("value") or "")
    ref_type = str(ref.get("type") or "")
    ref_name = str(ref.get("name") or "")
    ref_uri = str(ref.get("uri") or ref.get("uriTemplate") or "")

    if ref_type.endswith("resource") and argument_name == "recipe_id":
        if ref_uri in {"bubble://recipes/{recipe_id}", "bubble://recipes/"} or ref_uri.startswith("bubble://recipes/"):
            return _completion(sorted(RECIPES), value)
    if ref_type.endswith("resource") and argument_name == "profile":
        if ref_uri in {"bubble://profiles/{profile}/status", "bubble://profiles/"} or ref_uri.startswith("bubble://profiles/"):
            return _completion(_profile_names(), value)
    if ref_type.endswith("resource") and argument_name == "tool_name":
        if ref_uri in {"bubble://tools/{tool_name}", "bubble://tools/"} or ref_uri.startswith("bubble://tools/"):
            return _completion(_tool_names(), value)

    if ref_type.endswith("prompt") and ref_name in PROMPTS:
        if argument_name == "profile":
            return _completion(_profile_names(), value)
        if argument_name == "context":
            return _completion(DEFAULT_CONTEXT_SUGGESTIONS, value)
        if argument_name == "parent":
            return _completion(DEFAULT_PARENT_SUGGESTIONS, value)
        if argument_name in BOOLEAN_ARGUMENT_NAMES:
            return _completion(BOOLEAN_SUGGESTIONS, value)

    if ref_type.endswith("tool"):
        if argument_name == "profile":
            return _completion(_profile_names(), value)
        if argument_name == "context":
            return _completion(DEFAULT_CONTEXT_SUGGESTIONS, value)
        if argument_name == "parent":
            return _completion(DEFAULT_PARENT_SUGGESTIONS, value)
        if argument_name in BOOLEAN_ARGUMENT_NAMES:
            return _completion(BOOLEAN_SUGGESTIONS, value)

        schema_suggestions = _schema_suggestions(ref_name, argument_name)
        if schema_suggestions:
            return _completion(schema_suggestions, value)
        if ref_name == "bubble_runtime_smoke" and argument_name == "suite":
            return _completion(RUNTIME_SMOKE_SUITE_SUGGESTIONS, value)
        if ref_name == "bubble_task_recipe" and argument_name == "recipe":
            return _completion(sorted(RECIPES), value)

    return _completion([], value)
