"""Compact agent guidance for using the Bubble MCP catalog."""

from __future__ import annotations

from typing import Any


ROUTES: tuple[dict[str, Any], ...] = (
    {
        "intent": "check_server_or_catalog",
        "when": "The user asks whether the MCP is installed, healthy, covered, or ready.",
        "tools": ["bubble_health_check", "bubble_tool_coverage", "bubble_runtime_smoke"],
        "notes": "Use coverage first for catalog integrity; use safe-read or family-preview for runtime confidence.",
    },
    {
        "intent": "find_profile_session_or_context",
        "when": "The user names a project/profile, asks what projects are available, or a target cannot be resolved.",
        "tools": ["bubble_profile_list", "bubble_session_list", "bubble_context_detect", "bubble_context_find"],
        "notes": "Refresh context with bubble_context_detect when pages/elements may have changed in Bubble.",
    },
    {
        "intent": "create_or_update_visual_editor_elements",
        "when": "The user asks to create, update, rename, move, or delete Bubble visual elements.",
        "tools": ["create_group", "create_text", "create_button", "create_input", "update_text", "delete_group"],
        "notes": "Call the specific create_*/update_*/delete_* tool matching the requested element type; pass profile, context, parent, and execute.",
    },
    {
        "intent": "import_html_component",
        "when": "The user asks to convert/import/copy an HTML section, URL, selector, or snippet into Bubble.",
        "tools": ["create_from_html"],
        "notes": "Use create_from_html directly. Pass profile, context, parent, url/html/html_file, selector, rendered_html, refresh_context, and execute.",
    },
    {
        "intent": "manage_styles_tokens_design_system",
        "when": "The user asks to list, create, update, or sync Bubble styles, colors, fonts, or design-system tokens.",
        "tools": ["list_styles", "create_style", "add_style_condition", "list_colors", "create_color", "sync_figma_style", "sync_figma_tokens"],
        "notes": "Prefer list_* before mutation when matching existing design-system assets matters.",
    },
    {
        "intent": "manage_workflows",
        "when": "The user asks to create events, add actions, wire buttons, change conditions, or inspect workflow refs.",
        "tools": ["create_workflow", "create_event", "add_action", "list_events", "resolve_refs", "map_workflow_ref"],
        "notes": "For page load workflows, target element_name='Page'. For element events, resolve the element first when ambiguous.",
    },
    {
        "intent": "manage_data_schema",
        "when": "The user asks to create or change Bubble data types, fields, option sets, or option values.",
        "tools": ["list_data_types", "create_data_type", "create_data_field", "create_option_set", "create_option_value", "list_option_values"],
        "notes": "Use preview mode first for schema changes unless the user explicitly asks to execute.",
    },
    {
        "intent": "branches_or_changelog",
        "when": "The user asks about branches, sub-branches, contributors, history, audit, or changelog.",
        "tools": ["bubble_branch_list", "bubble_branch_create", "bubble_branch_delete", "bubble_branch_contributors", "bubble_changelog_fetch"],
        "notes": "Branch delete requires execute=true and confirm=true. Branch create previews unless execute=true.",
    },
    {
        "intent": "execute_exact_payload_or_plan",
        "when": "A previous step produced a validated Bubble payload or structured plan.",
        "tools": ["bubble_compile_plan", "bubble_execute_plan", "bubble_editor_write"],
        "notes": "Use bubble_execute_plan for structured plans and bubble_editor_write only for exact /appeditor/write payloads.",
    },
)


KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("html", "selector", "url", "convert", "import"), ("import_html_component",)),
    (("branch", "sub-branch", "version", "changelog", "history", "contributors"), ("branches_or_changelog",)),
    (("workflow", "event", "action", "condition", "page load", "click"), ("manage_workflows",)),
    (("style", "color", "font", "token", "figma", "design system"), ("manage_styles_tokens_design_system",)),
    (("data type", "field", "option set", "option value", "schema"), ("manage_data_schema",)),
    (("context", "profile", "session", "cache", "resolve", "find"), ("find_profile_session_or_context",)),
    (("payload", "plan", "execute", "write"), ("execute_exact_payload_or_plan",)),
    (("smoke", "coverage", "health", "ready", "catalog"), ("check_server_or_catalog",)),
    (("create", "update", "delete", "element", "text", "button", "group", "input", "image"), ("create_or_update_visual_editor_elements",)),
)


def agent_guide(task: str = "") -> dict[str, Any]:
    """Return compact tool-routing guidance for MCP clients."""

    normalized = str(task or "").strip().lower()
    matched_intents: list[str] = []
    if normalized:
        for keywords, intents in KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                matched_intents.extend(intents)

    unique_intents = list(dict.fromkeys(matched_intents))
    if not unique_intents:
        unique_intents = [
            "find_profile_session_or_context",
            "create_or_update_visual_editor_elements",
            "import_html_component",
            "execute_exact_payload_or_plan",
        ]

    route_map = {route["intent"]: route for route in ROUTES}
    recommended = [route_map[intent] for intent in unique_intents if intent in route_map]

    return {
        "ok": True,
        "task": task or None,
        "direct_tool_policy": {
            "use_mcp_tools_directly": True,
            "avoid_shell_cli_discovery": True,
            "preview_default": "Leave execute=false unless the user explicitly asked to apply the change in Bubble.",
            "profile_first": "Prefer profile-based calls so the server can use stored session, context, and mutation overlay.",
            "refresh_context_when_stale": "Run bubble_context_detect with force=true when the Bubble editor changed outside this MCP session.",
        },
        "setup_requirements": [
            "Each Bubble project needs a profile.",
            "Mutating calls need a stored editor session for that profile.",
            "Reliable target resolution needs a current context from bubble_context_detect.",
        ],
        "recommended_routes": recommended,
        "all_routes": list(ROUTES),
    }
