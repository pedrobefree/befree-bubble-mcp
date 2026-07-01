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
        {
            "name": "bubble_context_summary",
            "description": "Summarize a compact Bubble context JSON file.",
            "inputSchema": {
                "type": "object",
                "properties": {"file": {"type": "string"}},
                "required": ["file"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_context_find",
            "description": "Search a compact Bubble context JSON file.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["file", "query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_plan_dry_run",
            "description": "Create and validate a deterministic dry-run Bubble plan.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "context": {"type": "string"},
                    "parent": {"type": "string"},
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_import_html_dry_run",
            "description": "Convert HTML text into a validated Bubble dry-run plan.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "html": {"type": "string"},
                    "context": {"type": "string"},
                    "parent": {"type": "string"},
                },
                "required": ["html"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_eval_run",
            "description": "Run a deterministic planning eval dataset.",
            "inputSchema": {
                "type": "object",
                "properties": {"dataset": {"type": "string"}},
                "required": ["dataset"],
                "additionalProperties": False,
            },
        },
    ]
