"""MCP tool schemas exposed by the initial server."""

from __future__ import annotations

from typing import Any


def list_tool_schemas() -> list[dict[str, Any]]:
    """Return MCP-compatible tool schema definitions."""

    return [
        {
            "name": "bubble_profile_list",
            "description": "List local Bubble MCP profiles. This is read-only.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_health_check",
            "description": "Return local Bubble MCP server health and capability metadata.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    ]
