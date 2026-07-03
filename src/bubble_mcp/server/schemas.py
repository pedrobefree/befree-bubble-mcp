"""MCP tool schemas exposed by the initial server."""

from __future__ import annotations

from typing import Any

from bubble_mcp.server.agent_catalog import enhance_tool_schema
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES, legacy_tool_schema
from bubble_mcp.server.schema_families import native_tool_schemas


def list_tool_schemas() -> list[dict[str, Any]]:
    """Return MCP-compatible tool schema definitions."""

    native_tools = native_tool_schemas()
    native_names = {tool["name"] for tool in native_tools}
    legacy_tools = [
        legacy_tool_schema(name)
        for name in ARIA_BUBBLE_TOOL_NAMES
        if name not in native_names
    ]
    return [enhance_tool_schema(tool) for tool in [*native_tools, *legacy_tools]]
