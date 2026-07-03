"""Agent-facing MCP catalog metadata.

The execution layer keeps Aria-compatible tool names, but MCP clients select
tools mostly from descriptions and JSON schemas. This module enriches that
catalog with stable intent language, argument guidance, and MCP annotations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


COMMON_PROPERTY_DESCRIPTIONS: dict[str, str] = {
    "profile": "Local Bubble MCP profile to use for settings, context, and authenticated editor sessions.",
    "dry_run": "Preview the operation without writing to Bubble.",
    "settings_path": "Optional settings.json path for non-default profile configuration.",
    "app_id": "Bubble app id/appname. Optional when the selected profile already defines the target app.",
    "app_version": "Bubble editor version to target. Use test/version-test unless the user explicitly asks for live.",
    "context": "Target Bubble page, reusable element, or container context by visible name or known id.",
    "parent": "Parent Bubble element/container where new children should be added. Use root for page-level insertion.",
    "execute": "Set true only when the user asked to apply the change in Bubble. Leave false for preview/planning.",
    "compile": "Compile abstract plan steps into Bubble editor write payloads before execution.",
    "context_file": "Optional compact Bubble context JSON file to resolve pages, elements, and existing project structure.",
    "file": "Local file path to read as input.",
    "output": "Optional local output path for generated context or artifacts.",
    "force": "Refresh or rebuild cached data even when a previous artifact exists.",
    "payload": "Exact Bubble editor write payload to preview or send with the stored session.",
    "write_payload": "Exact Bubble editor write payload produced by a previous validated planning or compiler step.",
    "confirm": "Required true for destructive operations such as deleting or clearing Bubble resources.",
    "plan": "Structured Bubble MCP plan object containing ordered steps and tool arguments.",
    "message": "Natural language instruction to convert into a deterministic Bubble plan.",
    "query": "Search text used to find matching pages, elements, styles, data types, or context entries.",
    "limit": "Maximum number of results to return.",
    "kind": "Input artifact type. Use auto unless the artifact type is known.",
    "bubble_file": "Optional .bubble project export path to use as the primary context source.",
    "consolelog_file": "Optional console.log(app) JSON path to use when a .bubble export is not available.",
    "skip_id_to_path": "Skip generating id-to-path lookup data in the compact context.",
    "dataset": "Evaluation dataset path.",
    "session": "Captured Bubble editor session object containing headers/cookies. Secrets are stored locally.",
    "url": "Source URL to load, hydrate, inspect, and convert into Bubble elements.",
    "html_file": "Local HTML file or URL to convert into Bubble elements.",
    "html": "Raw HTML snippet to convert into Bubble elements.",
    "selector": "CSS selector for the exact source component or section to convert.",
    "rendered_html": "Use a browser-rendered DOM with computed styles when importing HTML from pages or selectors.",
    "translate_to_existing_styles": "Try matching imported visuals to existing Bubble styles in the target app.",
    "style_match_threshold": "Minimum similarity score for matching imported visuals to existing Bubble styles.",
    "placement": "Optional placement instruction for where the generated element tree should be inserted.",
    "strict_validate": "Fail the import when semantic validation finds unsupported or unsafe output.",
    "validation_out_dir": "Optional directory for debug artifacts generated during import validation.",
    "refresh_context": "Refresh Bubble context before resolving targets and compiling the mutation.",
}


NATIVE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "bubble_profile_list": (
        "List configured Bubble MCP profiles, app ids, and editor URLs. Use this first when the user names a profile "
        "or asks what Bubble projects are available. Read-only."
    ),
    "bubble_health_check": (
        "Report server version and capability flags for profiles, session capture, context, planning, mutations, "
        "HTML import, evals, and Figma bridge support. Read-only."
    ),
    "bubble_context_summary": (
        "Summarize a compact Bubble project context file: pages, reusable elements, styles, data types, and indexed "
        "elements. Use before planning changes against a local context artifact. Read-only."
    ),
    "bubble_context_find": (
        "Search a compact Bubble project context file for pages, containers, elements, styles, data types, workflows, "
        "or ids. Use to resolve targets before mutating Bubble. Read-only."
    ),
    "bubble_context_import": (
        "Convert a Bubble project artifact into compact context. Supports .bubble exports, console.log(app) JSON, "
        "and crawler indexes. Writes only local context artifacts."
    ),
    "bubble_context_detect": (
        "Build or refresh the unified Bubble project context for a profile. Prefer .bubble export data, then "
        "consolelog fallback, then editor crawl/cache. Use before planning writes when target pages or elements may "
        "have changed."
    ),
    "bubble_plan": (
        "Turn a short natural language Bubble edit request into a deterministic validated plan without writing to "
        "Bubble. Use for previews and simple supported edits."
    ),
    "bubble_plan_dry_run": (
        "Compatibility alias for bubble_plan. It creates the same deterministic validated Bubble plan without writing "
        "to Bubble; use bubble_plan for new calls unless compatibility with older clients is required."
    ),
    "create_from_html": (
        "Convert, import, copy, or add an HTML component or section from a URL, selector, file, or HTML snippet into "
        "Bubble. Uses the advanced Aria HTML-to-Bubble runtime: browser hydration, rendered DOM extraction, computed "
        "styles, asset handling, Bubble mapping, validation, context resolution, and optional authenticated execution."
    ),
    "bubble_eval_run": "Run deterministic Bubble planning eval datasets. Use for package validation, not user app edits.",
    "bubble_compile_plan": (
        "Compile supported abstract Bubble MCP plan steps into Bubble /appeditor/write payloads. Use after planning "
        "and before execution when the caller needs auditable payloads."
    ),
    "bubble_session_list": "List stored Bubble editor session metadata for local profiles. Secrets are redacted. Read-only.",
    "bubble_session_import": (
        "Import captured Bubble editor headers/cookies into a local profile so future mutating tools can write through "
        "the user's authenticated editor session."
    ),
    "bubble_editor_write": (
        "Preview or send an exact Bubble /appeditor/write payload with a stored local session. Use for advanced writes "
        "when a tool already produced a valid payload; execute=false previews, execute=true mutates Bubble."
    ),
    "bubble_execute_plan": (
        "Preview or execute a structured Bubble MCP plan. Can compile missing write payloads, resolve context, and use "
        "the stored profile session for authenticated execution."
    ),
}


LEGACY_CATEGORY_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    (
        "refresh_profile_cache sync_cache clear_cache inspect_context verify_write resolve_refs scan_types list_data_types list_element_ref_maps list_events sync_event_cache sync_workflow_ref_cache sync_element_ref_cache",
        "Read or refresh Bubble MCP caches, context indexes, reference maps, project metadata, or inspection data.",
    ),
    (
        "create_page delete_page clone_page create_reusable clone_reusable delete_reusable update_reusable",
        "Create, clone, update, or delete Bubble pages and reusable elements.",
    ),
    (
        "create_workflow add_action replace_action delete_action create_event delete_event set_event_ set_condition_ map_workflow_ref",
        "Create or modify Bubble workflows, events, actions, conditions, and workflow references.",
    ),
    (
        "list_styles create_style edit_style add_style_condition rename_style delete_style reorder_style_states create_button_style update_style",
        "Create or modify Bubble styles, style conditions, and reusable design-system definitions.",
    ),
    (
        "create_data_type rename_data_type delete_data_type create_data_field rename_data_field set_data_type_api_exposure",
        "Create or modify Bubble database types, fields, and API exposure settings.",
    ),
    (
        "create_option_set rename_option_set delete_option_set create_option_attribute create_option_value delete_option_value list_option_values",
        "Create or modify Bubble option sets, option attributes, and option values.",
    ),
    (
        "list_colors create_color update_color delete_color reorder_colors clear_custom_colors list_fonts create_font update_font delete_font",
        "Read or modify Bubble app colors and fonts.",
    ),
    (
        "sync_figma_component sync_component sync_figma_style sync_figma_tokens upload_asset",
        "Sync design-system assets from the local bridge into Bubble, including components, styles, tokens, and uploaded assets.",
    ),
    (
        "create_ update_ delete_",
        "Create, update, or delete Bubble visual elements such as groups, text, buttons, inputs, images, icons, links, HTML, maps, and layout containers.",
    ),
)


def enhance_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an MCP tool schema optimized for agent selection."""

    tool = deepcopy(schema)
    name = str(tool.get("name") or "")
    tool["description"] = NATIVE_TOOL_DESCRIPTIONS.get(name) or legacy_description(name)
    tool["annotations"] = tool_annotations(name)
    describe_input_properties(tool)
    return tool


def legacy_description(name: str) -> str:
    category = _category_for_name(name)
    return (
        f"{category} This is an Aria-compatible Bubble MCP tool. Use it when the user's intent matches this "
        "capability by outcome, not because the user named the tool. Prefer profile/context arguments for normal "
        "operation; pass an exact write_payload only when another step already produced a validated Bubble payload."
    )


def tool_annotations(name: str) -> dict[str, bool]:
    read_only = _is_read_only(name)
    destructive = name.startswith(("delete_", "clear_", "regenerate_"))
    return {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": read_only or name in {"bubble_health_check", "bubble_profile_list"},
        "openWorldHint": name
        in {
            "bubble_context_detect",
            "create_from_html",
            "bubble_editor_write",
            "bubble_execute_plan",
            "upload_asset",
        },
    }


def describe_input_properties(tool: dict[str, Any]) -> None:
    input_schema = tool.get("inputSchema")
    if not isinstance(input_schema, dict):
        return
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        return
    for property_name, property_schema in properties.items():
        if not isinstance(property_schema, dict):
            continue
        property_schema.setdefault(
            "description",
            COMMON_PROPERTY_DESCRIPTIONS.get(
                str(property_name),
                f"Argument '{property_name}' for the Bubble MCP tool '{tool.get('name')}'.",
            ),
        )


def _category_for_name(name: str) -> str:
    visual_family = _visual_element_family(name)
    if visual_family:
        return visual_family
    if name == "list_styles":
        return "List Bubble styles for lookup, validation, style matching, and design-system inspection."
    if name == "list_colors":
        return "List Bubble app color tokens for lookup, validation, and design-system inspection."
    if name == "list_fonts":
        return "List Bubble app fonts for lookup, validation, and design-system inspection."
    for prefixes, description in LEGACY_CATEGORY_DESCRIPTIONS:
        if any(name.startswith(prefix) for prefix in prefixes.split()):
            return description
    if name in {"batch", "natural"}:
        return "Run a higher-level Bubble MCP command that may dispatch multiple validated operations."
    if name.startswith(("build_source_query_json", "build_data_source_json")):
        return "Build Bubble data source/query JSON for visual elements, repeating groups, and dynamic expressions."
    if name.startswith(("set_app_setting", "set_project_setting", "list_project_settings")):
        return "Read or modify Bubble app and project settings."
    if "app_text" in name or "text_match" in name:
        return "Read or modify Bubble app text, translations, and app-text propagation."
    return "Operate on Bubble editor metadata or project structure."


def _visual_element_family(name: str) -> str | None:
    element_names = (
        "text",
        "button",
        "input",
        "multiline_input",
        "dropdown",
        "searchbox",
        "checkbox",
        "datepicker",
        "radio",
        "slider",
        "file_uploader",
        "picture_uploader",
        "shape",
        "video",
        "image",
        "icon",
        "html",
        "link",
        "alert",
        "map",
        "group",
        "floating_group",
        "group_focus",
        "table",
        "popup",
        "repeating_group",
        "reusable_instance",
    )
    for element in element_names:
        if name == f"create_{element}":
            return f"Create a Bubble {element.replace('_', ' ')} visual element with layout, styling, and parent placement arguments."
        if name == f"update_{element}" or name == f"update_{element}_element":
            return f"Update an existing Bubble {element.replace('_', ' ')} visual element by reference, name, or context."
        if name == f"delete_{element}":
            return f"Delete an existing Bubble {element.replace('_', ' ')} visual element after explicit confirmation."
    return None


def _is_read_only(name: str) -> bool:
    return name.startswith(("list_", "inspect_", "scan_", "resolve_", "verify_", "build_")) or name in {
        "bubble_profile_list",
        "bubble_health_check",
        "bubble_context_summary",
        "bubble_context_find",
        "bubble_eval_run",
        "bubble_plan",
        "bubble_plan_dry_run",
        "bubble_compile_plan",
        "refresh_profile_cache",
        "sync_cache",
        "sync_event_cache",
        "sync_workflow_ref_cache",
        "sync_element_ref_cache",
    }


def _is_mutating(name: str) -> bool:
    if _is_read_only(name):
        return False
    return name.startswith(
        (
            "create_",
            "update_",
            "delete_",
            "clone_",
            "rename_",
            "set_",
            "add_",
            "replace_",
            "reorder_",
            "convert_",
            "propagate_",
            "sync_",
            "upload_",
            "clear_",
            "regenerate_",
        )
    ) or name in {"bubble_editor_write", "bubble_execute_plan", "batch", "natural"}
