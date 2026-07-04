"""Read-only MCP resources for Bubble MCP clients."""

from __future__ import annotations

import json
from typing import Any

from bubble_mcp import __version__
from bubble_mcp.profile_status import profile_status
from bubble_mcp.server.agent_guide import RECIPES, ROUTES
from bubble_mcp.server.schemas import list_tool_schemas


RESOURCE_MIME_MARKDOWN = "text/markdown"
RESOURCE_MIME_JSON = "application/json"


def _tool_count() -> int:
    return len(list_tool_schemas())


def _agent_runtime_markdown() -> str:
    return "\n".join(
        [
            "# Befree Bubble MCP Agent Runtime",
            "",
            "Use MCP tools directly for Bubble work. Do not inspect repository code or CLI help unless a required",
            "capability is missing from `tools/list`.",
            "",
            "Recommended discovery order:",
            "",
            "1. `bubble_agent_guide` when the user request is broad and the agent needs the right family.",
            "2. `bubble_task_recipe` when the agent knows the task but needs preflight, sequence, safeguards, and verification.",
            "3. `bubble_tool_search` when the agent needs a compact subset of tool schemas.",
            "4. The specific Bubble mutation/read tool with `profile`, `context`, and `execute` filled intentionally.",
            "",
            "Mutation policy:",
            "",
            "- Preview first unless the user explicitly asked to apply the change.",
            "- Use profile-based calls so the server can use stored session, context, and mutation overlay.",
            "- Refresh context with `bubble_context_detect` when targets may be stale.",
            "- Destructive operations require explicit confirmation arguments.",
            "- After real writes, verify with context refresh, changelog, or a smoke suite when materialization matters.",
            "",
            "Operational checks:",
            "",
            "- `bubble_readiness_check` runs the recommended health, coverage, catalog-quality, routing, and profile-status sequence.",
            "- `bubble_tool_coverage` verifies catalog handling.",
            "- `bubble_catalog_quality` verifies schema, description, annotation, resource, prompt, and coverage quality.",
            "- `bubble_runtime_smoke` with `coverage` runs local catalog coverage and quality checks.",
            "- `bubble_runtime_smoke` with `agent-routing` validates natural-language tool selection without writes.",
            "- `bubble_runtime_smoke` with `family-preview` exercises major families without real writes.",
        ]
    )


def _agent_quickstart_markdown() -> str:
    return "\n".join(
        [
            "# Bubble MCP Agent Quickstart",
            "",
            "When the user asks for Bubble work through this MCP, use the MCP catalog directly.",
            "Do not inspect repository code, CLI help, or shell commands unless the required capability is missing",
            "from `tools/list`.",
            "",
            "Default call sequence:",
            "",
            "1. If the target profile is unclear, call `bubble_profile_list`.",
            "2. Call `bubble_profile_status` for the target profile to check session/context readiness.",
            "3. Call `bubble_agent_guide` with the user's natural-language task.",
            "4. Call `bubble_task_recipe` with `task`, `profile`, `context`, `parent`, and `execute`.",
            "5. Execute the recipe's MCP tools in order. Use `execute=false` for preview unless the user",
            "   explicitly asked to apply the change.",
            "6. After real writes, verify with `bubble_context_detect`, changelog tools, or `bubble_runtime_smoke`.",
            "",
            "Setup assumptions:",
            "",
            "- Every Bubble app needs a local profile.",
            "- Mutating calls need a captured session for that profile.",
            "- Reliable page/reusable/element resolution needs current context from `bubble_context_detect`.",
            "",
            "User interaction policy:",
            "",
            "- Do not ask the user to memorize or provide internal tool names.",
            "- Infer the capability from the request and use the visible Bubble names the user provided.",
            "- Ask the user only for missing business inputs such as profile, page/reusable name, target element,",
            "  selector, URL, or permission to execute a real write.",
        ]
    )


def _catalog_summary() -> dict[str, Any]:
    tools = list_tool_schemas()
    native = [
        "bubble_health_check",
        "bubble_profile_status",
        "bubble_readiness_check",
        "bubble_agent_guide",
        "bubble_task_recipe",
        "bubble_tool_search",
        "bubble_tool_coverage",
        "bubble_catalog_quality",
        "bubble_runtime_smoke",
    ]
    return {
        "ok": True,
        "version": __version__,
        "tool_count": len(tools),
        "native_agent_tools": native,
        "route_count": len(ROUTES),
        "recipe_count": len(RECIPES),
        "recommended_entrypoints": [
            "bubble_agent_guide",
            "bubble_profile_status",
            "bubble_task_recipe",
            "bubble_tool_search",
            "bubble_readiness_check",
            "bubble_catalog_quality",
            "bubble_runtime_smoke",
        ],
    }


def _recipes_summary() -> dict[str, Any]:
    return {
        "ok": True,
        "recipes": [
            {
                "id": recipe_id,
                "when": recipe["when"],
                "tools": recipe["tools"],
                "step_count": len(recipe["steps"]),
            }
            for recipe_id, recipe in RECIPES.items()
        ],
    }


def _recipe_detail(recipe_id: str) -> dict[str, Any]:
    recipe = RECIPES.get(recipe_id)
    if not recipe:
        raise ValueError(f"Unknown Bubble MCP recipe: {recipe_id}")
    return {
        "ok": True,
        "id": recipe_id,
        "when": recipe["when"],
        "tools": recipe["tools"],
        "steps": recipe["steps"],
    }


RESOURCES: dict[str, dict[str, Any]] = {
    "bubble://docs/agent-quickstart": {
        "name": "bubble_agent_quickstart",
        "title": "Bubble Agent Quickstart",
        "description": "Shortest operating sequence for agents using this Bubble MCP server.",
        "mimeType": RESOURCE_MIME_MARKDOWN,
    },
    "bubble://docs/agent-runtime": {
        "name": "bubble_agent_runtime",
        "title": "Bubble Agent Runtime Guide",
        "description": "Compact read-only operating rules for agents using this Bubble MCP server.",
        "mimeType": RESOURCE_MIME_MARKDOWN,
    },
    "bubble://catalog/summary": {
        "name": "bubble_catalog_summary",
        "title": "Bubble MCP Catalog Summary",
        "description": "Compact JSON summary of the exposed Bubble MCP catalog and agent entrypoints.",
        "mimeType": RESOURCE_MIME_JSON,
    },
    "bubble://recipes/summary": {
        "name": "bubble_recipe_summary",
        "title": "Bubble Task Recipe Summary",
        "description": "Compact JSON summary of available task recipes and their tool families.",
        "mimeType": RESOURCE_MIME_JSON,
    },
}


RESOURCE_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "bubble_recipe",
        "uriTemplate": "bubble://recipes/{recipe_id}",
        "title": "Bubble Task Recipe",
        "description": "Read the complete operational recipe for one Bubble task family.",
        "mimeType": RESOURCE_MIME_JSON,
    },
    {
        "name": "bubble_profile_status",
        "uriTemplate": "bubble://profiles/{profile}/status",
        "title": "Bubble Profile Status",
        "description": "Read setup/readiness status for one local Bubble MCP profile.",
        "mimeType": RESOURCE_MIME_JSON,
    }
]


def list_resources() -> list[dict[str, Any]]:
    """Return MCP resource descriptors."""

    return [{"uri": uri, **metadata} for uri, metadata in RESOURCES.items()]


def list_resource_templates() -> list[dict[str, Any]]:
    """Return MCP resource template descriptors."""

    return RESOURCE_TEMPLATES.copy()


def read_resource(uri: str) -> dict[str, Any]:
    """Read one MCP resource by URI."""

    mime_type = RESOURCE_MIME_JSON
    if uri.startswith("bubble://recipes/") and uri != "bubble://recipes/summary":
        recipe_id = uri.removeprefix("bubble://recipes/").strip()
        text = json.dumps(_recipe_detail(recipe_id), indent=2, sort_keys=True)
    elif uri.startswith("bubble://profiles/") and uri.endswith("/status"):
        profile = uri.removeprefix("bubble://profiles/").removesuffix("/status").strip()
        text = json.dumps(profile_status(profile), indent=2, sort_keys=True)
    elif uri not in RESOURCES:
        raise ValueError(f"Unknown Bubble MCP resource: {uri}")
    elif uri == "bubble://docs/agent-quickstart":
        mime_type = RESOURCE_MIME_MARKDOWN
        text = _agent_quickstart_markdown()
    elif uri == "bubble://docs/agent-runtime":
        mime_type = RESOURCE_MIME_MARKDOWN
        text = _agent_runtime_markdown()
    elif uri == "bubble://catalog/summary":
        text = json.dumps(_catalog_summary(), indent=2, sort_keys=True)
    elif uri == "bubble://recipes/summary":
        text = json.dumps(_recipes_summary(), indent=2, sort_keys=True)
    else:
        raise ValueError(f"Unknown Bubble MCP resource: {uri}")
    return {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]}
