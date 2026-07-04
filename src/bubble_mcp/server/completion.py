"""MCP completion helpers for Bubble MCP clients."""

from __future__ import annotations

from typing import Any

from bubble_mcp.core.config import load_settings
from bubble_mcp.server.agent_guide import RECIPES
from bubble_mcp.server.prompts import PROMPTS


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
        if ref_name == "bubble_runtime_smoke" and argument_name == "suite":
            return _completion(RUNTIME_SMOKE_SUITE_SUGGESTIONS, value)
        if ref_name == "bubble_task_recipe" and argument_name == "recipe":
            return _completion(sorted(RECIPES), value)

    return _completion([], value)
