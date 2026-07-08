"""Framework-shaped low-token language packs."""

from __future__ import annotations

from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter
from bubble_mcp.language.query import language_query
from bubble_mcp.language.registry import RUNTIME_RULES_DIGEST, build_language_index
from bubble_mcp.server.agent_guide import task_runbook


FRAMEWORK_FOCUS: dict[str, list[str]] = {
    "bmad": ["visual_editor", "workflow", "data_schema", "api_connector", "observability"],
    "superpowers": ["visual_editor", "workflow", "data_schema", "extension_authoring", "observability"],
    "sdd": ["visual_editor", "workflow", "data_schema", "observability"],
}


def framework_language_pack(
    *,
    framework: str,
    profile: str | None = None,
    scope: str = "",
    max_tools: int = 12,
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    families = FRAMEWORK_FOCUS.get(adapter.framework_id, [])
    index = build_language_index(profile=profile)
    matches = language_query(query=scope, families=families, limit=max_tools, profile=profile)
    runbook = task_runbook(scope or f"{adapter.name} Bubble implementation", profile=profile or "", execute=False)
    return {
        "ok": True,
        "language": "bubble-mcp",
        "framework": adapter.framework_id,
        "profile": profile,
        "scope": scope,
        "registry_version": index["registry_version"],
        "language_index": index,
        "runtime_rules": RUNTIME_RULES_DIGEST,
        "framework_guidance": {
            "name": adapter.name,
            "modes": list(adapter.modes),
            "artifact_types": list(adapter.artifacts),
            "execution_boundary": (
                "Frameworks plan and structure; Bubble MCP validates, previews, executes, and syncs evidence."
            ),
        },
        "tool_matches": matches["matches"],
        "recipes": runbook.get("recipes", []),
        "next_actions": [
            "Call bubble_language_query for more scoped tools when needed.",
            "Call bubble_language_tool_detail only for selected tools before compilation.",
            "Call bubble_framework_compile_program to compile framework work into preview-safe MCP calls.",
        ],
    }
