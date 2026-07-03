"""MCP tool schemas exposed by the initial server."""

from __future__ import annotations

from typing import Any

from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES, legacy_tool_schema


def list_tool_schemas() -> list[dict[str, Any]]:
    """Return MCP-compatible tool schema definitions."""

    native_tools = [
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
            "name": "bubble_context_import",
            "description": "Import a Bubble .bubble/consolelog JSON or crawler-index JSON into compact context.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "kind": {"type": "string", "enum": ["auto", "bubble", "crawler"]},
                    "output": {"type": "string"},
                },
                "required": ["file"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_context_detect",
            "description": "Detect and materialize Bubble project context using local artifacts, consolelog fallback, then the editor crawler.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string"},
                    "app_id": {"type": "string"},
                    "app_version": {"type": "string"},
                    "output": {"type": "string"},
                    "bubble_file": {"type": "string"},
                    "consolelog_file": {"type": "string"},
                    "force": {"type": "boolean"},
                    "skip_id_to_path": {"type": "boolean"},
                },
                "required": ["profile"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_plan",
            "description": "Create and validate a deterministic Bubble plan.",
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
            "name": "bubble_plan_dry_run",
            "description": "Compatibility alias for bubble_plan.",
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
            "name": "create_from_html",
            "description": "Use this whenever a user asks to convert, import, copy, or add an HTML component/section from a URL, selector, or HTML snippet into Bubble. This is Aria's advanced HTML-to-Bubble importer: it hydrates the page with a browser, extracts rendered DOM/computed styles, maps the result to Bubble elements, and can execute through the stored profile session. Prefer this over any conservative/raw HTML converter for URL + selector requests.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string"},
                    "app_id": {"type": "string"},
                    "app_version": {"type": "string"},
                    "context": {"type": "string"},
                    "parent": {"type": "string"},
                    "url": {"type": "string"},
                    "html_file": {"type": "string"},
                    "file": {"type": "string"},
                    "html": {"type": "string"},
                    "selector": {"type": "string"},
                    "execute": {"type": "boolean"},
                    "rendered_html": {"type": "boolean"},
                    "translate_to_existing_styles": {"type": "boolean"},
                    "style_match_threshold": {"type": "number"},
                    "placement": {"type": "string"},
                    "strict_validate": {"type": "boolean"},
                    "validation_out_dir": {"type": "string"},
                    "refresh_context": {"type": "boolean"},
                },
                "required": ["profile", "context", "parent"],
                "anyOf": [
                    {"required": ["url"]},
                    {"required": ["html_file"]},
                    {"required": ["file"]},
                    {"required": ["html"]},
                ],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_eval_run",
            "description": "Run a deterministic planning eval dataset.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "compile": {"type": "boolean"},
                    "app_id": {"type": "string"},
                },
                "required": ["dataset"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_compile_plan",
            "description": "Compile supported abstract plan steps into Bubble /appeditor/write payloads.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan": {"type": "object"},
                    "app_id": {"type": "string"},
                    "app_version": {"type": "string"},
                    "context_file": {"type": "string"},
                },
                "required": ["plan", "app_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_session_list",
            "description": "List locally imported Bubble editor session metadata.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_session_import",
            "description": "Import a local Bubble editor session object with headers/cookies for a profile.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string"},
                    "app_id": {"type": "string"},
                    "session": {"type": "object"},
                },
                "required": ["profile", "session"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_editor_write",
            "description": "Send a Bubble /appeditor/write payload using a stored local session. Set execute=true to mutate Bubble; otherwise it previews the request.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string"},
                    "payload": {"type": "object"},
                    "execute": {"type": "boolean"},
                },
                "required": ["profile", "payload"],
                "additionalProperties": False,
            },
        },
        {
            "name": "bubble_execute_plan",
            "description": "Execute a Bubble plan whose steps include args.write_payload. Set execute=true to mutate Bubble; otherwise it previews the plan.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string"},
                    "plan": {"type": "object"},
                    "execute": {"type": "boolean"},
                    "compile": {"type": "boolean"},
                    "app_id": {"type": "string"},
                    "app_version": {"type": "string"},
                    "context_file": {"type": "string"},
                },
                "required": ["profile", "plan"],
                "additionalProperties": False,
            },
        },
    ]
    native_names = {tool["name"] for tool in native_tools}
    legacy_tools = [
        legacy_tool_schema(name)
        for name in ARIA_BUBBLE_TOOL_NAMES
        if name not in native_names
    ]
    return [*native_tools, *legacy_tools]
