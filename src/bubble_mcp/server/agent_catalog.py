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
    "from_app_version": "Source Bubble branch/version to branch from. Defaults to the profile or session app version, usually test.",
    "start_index": "Zero-based pagination offset for Bubble editor changelog entries.",
    "num_fetch": "Number of changelog entries to fetch. The implementation caps this to avoid oversized responses.",
    "filters": "Raw Bubble changelog filters object. Use when advanced filters already match Bubble's editor payload shape.",
    "start_timestamp": "Start timestamp in milliseconds for changelog filtering.",
    "end_timestamp": "End timestamp in milliseconds for changelog filtering.",
    "change_type": "Bubble changelog category/type filter, such as Element, Workflow, Data, Style, or Page.",
    "root": "Bubble root id for deeper changelog filtering. This is usually a page or reusable element id.",
    "change_identifier": "Bubble changelog change identifier filter for a specific element, workflow, data type, or resource.",
    "change_path": "Bubble changelog path filter. Pass the exact string or string array observed in Bubble change paths.",
    "user_id": "Bubble collaborator user id or ids used to filter changelog entries.",
    "soft_delete": "When deleting a branch, keep Bubble's soft-delete behavior enabled unless explicitly instructed otherwise.",
    "version_control_api_version": "Bubble version-control API version for branch operations. Defaults to the current observed value.",
    "context": "Target Bubble page, reusable element, or container context by visible name or known id.",
    "parent": "Parent Bubble element/container where new children should be added. Use root for page-level insertion.",
    "execute": "Set true only when the user asked to apply the change in Bubble. Leave false for preview/planning.",
    "compile": "Compile abstract plan steps into Bubble editor write payloads before execution.",
    "context_file": "Optional compact Bubble context JSON file to resolve pages, elements, and existing project structure.",
    "file": "Local file path to read as input.",
    "output": "Optional local output path for generated context or artifacts.",
    "input": "Local input artifact path.",
    "force": "Refresh or rebuild cached data even when a previous artifact exists.",
    "payload": "Exact Bubble editor write payload to preview or send with the stored session.",
    "write_payload": "Exact Bubble editor write payload produced by a previous validated planning or compiler step.",
    "confirm": "Required true for destructive operations such as deleting or clearing Bubble resources.",
    "plan": "Structured Bubble MCP plan object containing ordered steps and tool arguments.",
    "message": "Natural language instruction to convert into a deterministic Bubble plan.",
    "task": "Optional user request or task summary used to recommend the most relevant Bubble MCP tools.",
    "recipe": "Optional operational recipe id to force. Omit it so the MCP infers the right recipe from the task.",
    "query": "Search text used to find matching pages, elements, styles, data types, or context entries.",
    "limit": "Maximum number of results or eval cases to return.",
    "kind": "Input artifact type. Use auto unless the artifact type is known.",
    "bubble_file": "Optional .bubble project export path to use as the primary context source.",
    "consolelog_file": "Optional console.log(app) JSON path to use when a .bubble export is not available.",
    "skip_id_to_path": "Skip generating id-to-path lookup data in the compact context.",
    "dataset": "Evaluation dataset path.",
    "filter": "Comma-separated eval case ids to run.",
    "failed_from": "Path to a prior eval JSON report; only failed case ids are rerun.",
    "offset": "Number of eval cases to skip after filtering.",
    "session": "Captured Bubble editor session object containing headers/cookies. Secrets are stored locally.",
    "url": "URL used by the tool, such as source page, link target, video URL, or HTML import source.",
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
    "name": "Display name or Bubble entity name to create, update, clone, or resolve.",
    "title": "Human-readable title for a page, branch, action, test, or entity.",
    "source": "Source page, reusable, workflow, action, element, asset, or existing entity to copy/clone.",
    "layout": "Bubble responsive layout mode, such as column, row, align-to-parent, or fixed.",
    "default_builder_width": "Default Bubble builder canvas width for a page.",
    "row_gap": "Vertical spacing between children in Bubble responsive layout.",
    "column_gap": "Horizontal spacing between children in Bubble responsive layout.",
    "horiz_alignment": "Horizontal alignment for children or content.",
    "vert_alignment": "Vertical alignment for children or content.",
    "container_alignment": "Container alignment behavior used by Bubble responsive layout.",
    "padding": "Uniform padding value applied to all sides.",
    "padding_top": "Top padding value.",
    "padding_bottom": "Bottom padding value.",
    "padding_left": "Left padding value.",
    "padding_right": "Right padding value.",
    "margin_top": "Top margin value.",
    "margin_bottom": "Bottom margin value.",
    "margin_left": "Left margin value.",
    "margin_right": "Right margin value.",
    "min_width": "Minimum responsive width value.",
    "max_width": "Maximum responsive width value.",
    "fixed_width": "Set whether width is fixed instead of responsive.",
    "fit_width": "Set whether width fits content.",
    "min_height": "Minimum responsive height value.",
    "max_height": "Maximum responsive height value.",
    "fixed_height": "Set whether height is fixed instead of responsive.",
    "fit_height": "Set whether height fits content.",
    "style": "Bubble reusable style name or id to apply.",
    "element_type": "Bubble element type, such as Group, Text, Button, Input, Popup, or Map.",
    "type": "Bubble type, entity type, element type, or workflow parameter type depending on the tool.",
    "content": "Text content to display in a Bubble Text element.",
    "label": "Visible label for a Bubble control, button, uploader, checkbox, or test item.",
    "placeholder": "Placeholder text shown in an input-like Bubble element.",
    "choices": "Static choices for dropdowns, radios, or option values.",
    "dynamic_type": "Bubble data type used for dynamic option sources.",
    "option_caption_field": "Field used as the visible caption for dynamic dropdown options.",
    "checked": "Initial checked state for checkbox-like controls.",
    "required": "Whether the Bubble input/control is required.",
    "selected": "Initial selected value.",
    "min": "Minimum numeric value.",
    "max": "Maximum numeric value.",
    "val": "Initial numeric value.",
    "step": "Numeric increment step.",
    "show_time": "Show time selection in date/time inputs.",
    "group_name": "Radio button group name.",
    "source_appname": "Source Bubble app id for cross-app copy operations.",
    "source_context": "Source Bubble page/reusable/context for copy operations.",
    "element_name": "Existing Bubble element name to update, delete, bind, or inspect.",
    "search_text": "Text to search for when updating a Text element.",
    "new_text": "Replacement text for a Text element.",
    "new_name": "Replacement name for an existing Bubble entity or element.",
    "new_placeholder": "Replacement placeholder text.",
    "new_style": "Replacement Bubble style name or id.",
    "from_style": "Source Bubble style to replace.",
    "to_style": "Target Bubble style to apply.",
    "new_source": "Replacement image, video, icon, or asset source.",
    "new_icon": "Replacement Bubble icon identifier.",
    "property": "Bubble layout/property name to update.",
    "value": "Value to assign to a Bubble property.",
    "content_format": "Bubble input content format, such as text, email, integer, decimal, or date.",
    "icon": "Bubble icon identifier or icon source.",
    "video_id": "Video provider id for Bubble Video elements.",
    "origin": "Video origin/provider, such as YouTube or Vimeo.",
    "autoplay": "Whether the video should autoplay.",
    "color": "Color value, token name, or Bubble color reference.",
    "bg_style": "Background style, such as color, image, gradient, or none.",
    "bg_color": "Background color value or Bubble color token.",
    "bg_image": "Background image URL or asset reference.",
    "gradient_color1": "First gradient color.",
    "gradient_color2": "Second gradient color.",
    "gradient_mid": "Gradient midpoint value.",
    "gradient_angle": "Gradient angle in degrees.",
    "border_color": "Border color value or Bubble color token.",
    "border_width": "Border width value.",
    "border_style": "Border style value.",
    "border_radius": "Border radius value.",
    "shadow": "Bubble shadow or CSS-like shadow value.",
    "rotation_angle": "Rotation angle in degrees.",
    "opacity": "Element opacity value.",
    "data_class": "Bubble data type/class for a group or repeating group.",
    "data_type": "Bubble data type name or id.",
    "data_source": "Bubble data source expression or reference.",
    "query_json": "Raw Bubble query JSON expression.",
    "query_result_type": "Expected Bubble query result type.",
    "query_source_type": "Bubble query source type.",
    "query_result_from_field": "Field used to derive query result values.",
    "query_constraints_json": "Raw Bubble query constraints JSON.",
    "query_sort_field": "Field used for query sorting.",
    "query_sort_desc": "Set true to sort query results descending.",
    "query_ignore_empty_constraints": "Ignore empty query constraints when building the Bubble query.",
    "data_source_json": "Raw Bubble data source JSON expression.",
    "source_type": "Alias for query source type in data-source builder tools.",
    "result_type": "Alias for query result type in data-source builder tools.",
    "result_from_field": "Alias for query result-from-field in data-source builder tools.",
    "constraints_json": "Alias for query constraints JSON in data-source builder tools.",
    "sort_field": "Alias for query sort field.",
    "sort_desc": "Alias for query descending sort.",
    "ignore_empty_constraints": "Alias for ignoring empty query constraints.",
    "rows": "Number of visible repeating group rows.",
    "default": "Set the created style as the default style for its element type.",
    "map_type": "Bubble map type/style category.",
    "map_style": "Built-in Bubble map style identifier.",
    "custom_style": "Custom JSON/style payload for a Bubble style.",
    "condition": "Bubble style or workflow condition expression.",
    "order": "Desired style condition/state order, as CSV or natural phrase.",
    "event_type": "Bubble workflow event type, such as PageLoaded, CustomEvent, APIEvent, or ConditionTrue.",
    "event_ref": "Existing Bubble workflow event reference, id, key, alias, or name.",
    "event_ref_kind": "How to interpret event_ref, such as id, key, alias, name, or auto.",
    "element_ref": "Existing Bubble element reference, id, alias, or name.",
    "element_ref_kind": "How to interpret element_ref, such as id, alias, name, text, or auto.",
    "ref_kind": "How to interpret a reference argument.",
    "action_type": "Bubble workflow action type to create or replace.",
    "action_ref": "Existing workflow action reference, id, key, index, or alias.",
    "action_ref_kind": "How to interpret action_ref.",
    "event": "Workflow event name or shorthand used by older CLI commands.",
    "param": "Generic action parameter value.",
    "fields": "Action field assignments as JSON or friendly DSL such as key=value; another=true.",
    "thing": "Bubble Thing expression, direct reference, element reference, or search shortcut.",
    "to_email": "Email recipient address for email-related actions.",
    "to": "Email recipient alias for to_email.",
    "subject": "Email/message subject.",
    "body": "Email/message body.",
    "pause_ms": "Pause duration in milliseconds.",
    "hide_status_bar": "Whether to hide Bubble status bar UI for navigation actions.",
    "open_in_new_tab": "Whether navigation opens in a new browser tab.",
    "same_tab": "Whether navigation stays in the same browser tab.",
    "keep_current_page_params": "Whether navigation preserves current page URL parameters.",
    "add_parameters": "Whether to add URL parameters to the navigation action.",
    "url_parameters_json": "Raw Bubble URL parameters JSON.",
    "data_to_send_json": "Raw Bubble data-to-send JSON for navigation actions.",
    "page_ref": "Target page reference, id, name, key, or alias.",
    "action_index": "Numeric workflow action index.",
    "action_id": "Workflow action id.",
    "bind_name": "Alias name to store for a resolved reference.",
    "custom_event_name": "Custom event display/name value.",
    "run_when": "Run-when condition expression.",
    "only_when_json": "Raw Bubble only-when condition JSON.",
    "interval_seconds": "Interval in seconds for DoInterval events.",
    "event_key": "Explicit workflow event map key.",
    "event_id": "Explicit workflow event id.",
    "id_counter": "Optional Bubble id counter override used by advanced payload generation.",
    "alias_name": "Local alias name to map to a Bubble reference.",
    "property_path": "Bubble object path to set or verify.",
    "value_type": "How to encode the supplied value, such as string, number, boolean, json, or expression.",
    "current_event_type": "Current event type used to disambiguate an event update.",
    "element": "Element name/ref used by event mutation helpers.",
    "parameters_json": "Raw custom event parameters JSON.",
    "param_name": "Custom event parameter name.",
    "btype_id": "Bubble type id for workflow parameter or return type.",
    "is_list": "Whether the Bubble type is a list.",
    "optional": "Whether the Bubble workflow parameter or return type is optional.",
    "param_id": "Explicit custom event parameter id.",
    "return_types_json": "Raw custom event return types JSON.",
    "return_name": "Custom event return type name.",
    "return_id": "Explicit custom event return type id.",
    "state_name": "Custom state name.",
    "state_type": "Bubble custom state type.",
    "default_value": "Default scalar custom-state value.",
    "default_value_json": "Default custom-state value as raw JSON.",
    "element_id": "Exact Bubble element id.",
    "capture_file": "Captured traffic or reference-map artifact path.",
    "clear": "Clear existing cached values before rebuilding.",
    "json": "Return machine-readable JSON output when supported.",
    "scope": "Inspection scope, such as elements, workflows, styles, schema, or all.",
    "include_elements": "Include element details in inspection output.",
    "include_workflows": "Include workflow details in inspection output.",
    "include_styles": "Include style details in inspection output.",
    "parent_ref": "Parent element reference to resolve.",
    "parent_match_index": "Match index when parent resolution returns multiple candidates.",
    "match_index": "Match index when reference resolution returns multiple candidates.",
    "style_ref": "Style name/id/ref to resolve.",
    "style_element_type": "Element type scope for style resolution.",
    "data_type_ref": "Bubble data type reference to resolve.",
    "data_type_ref_kind": "How to interpret data_type_ref.",
    "option_set_ref": "Bubble option set reference to resolve.",
    "option_set_ref_kind": "How to interpret option_set_ref.",
    "option_value_ref": "Bubble option value reference to resolve.",
    "path": "Workspace path, Bubble object path, or target owner path depending on the tool.",
    "entity": "Entity kind to inspect or verify.",
    "expected": "Expected value for verification.",
    "skip_clear_cache": "Skip cache clearing during profile refresh.",
    "skip_split": "Skip splitting the downloaded .bubble export during profile refresh.",
    "skip_sync_events": "Skip workflow/event cache sync during profile refresh.",
    "skip_scan_types": "Skip Bubble type/schema scanning during profile refresh.",
    "skip_sync_element_refs": "Skip element reference cache sync during profile refresh.",
    "mode": "Cache sync preset mode.",
    "type_of_content": "Bubble type of content for a page or reusable container.",
    "url_backup_field": "Bubble field used for URL backup behavior.",
    "meta_title": "SEO meta title.",
    "meta_description": "SEO meta description.",
    "html_header": "Custom HTML header content.",
    "float_v_relative": "Floating group vertical reference behavior.",
    "float_h_relative": "Floating group horizontal reference behavior.",
    "float_zindex": "Floating group z-index.",
    "parallax": "Floating/parallax behavior setting.",
    "limit_image_size_before_upload": "Whether Bubble should limit image size before upload.",
    "prefer_last": "When multiple matches exist, prefer the last matching element.",
    "language": "Language code for app text or translation operations.",
    "commands": "Batch command list or command text to execute through a higher-level Bubble MCP command.",
    "ref": "Reference id, alias, key, or name used by inspection or verification tools.",
    "values": "Option-set values, static choices, or bulk values depending on the tool.",
    "attributes": "Option-set attributes or structured metadata depending on the tool.",
    "names": "Comma-separated or array-like list of Bubble entity names.",
    "pattern": "Name-matching pattern for bulk cleanup or selection operations.",
    "token_id": "Bubble API token id or key.",
    "private_key": "Private API token value. Never log or commit real secrets.",
    "exposed_api": "Whether the Bubble data type should be exposed through Bubble's Data API.",
    "include_cache": "Include local cache data in the read-only response.",
}


NATIVE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "bubble_project_bootstrap": (
        "One-call setup entrypoint for a Bubble project profile. Use it when the user provides or implies a profile "
        "and Bubble app id: it can create or update the local profile, report readiness, and optionally run context "
        "detection. This reduces setup trial-and-error before session capture and project mutations."
    ),
    "bubble_profile_add": (
        "Add or update a local Bubble MCP profile in settings.json. This is a local setup mutation only; it does not "
        "contact Bubble or edit the app. Use it when the user asks to configure a project profile before session "
        "capture and context detection."
    ),
    "bubble_profile_list": (
        "List configured Bubble MCP profiles, app ids, and editor URLs. Use this first when the user names a profile "
        "or asks what Bubble projects are available. Read-only."
    ),
    "bubble_profile_status": (
        "Return a read-only readiness snapshot for one local Bubble MCP profile: profile mapping, stored session "
        "metadata, context artifact loadability/freshness, and concrete next actions when setup is incomplete. Use "
        "this before mutations when the agent needs to know whether a profile is ready without calling profile, "
        "session, and context tools separately."
    ),
    "bubble_health_check": (
        "Report server version and capability flags for profiles, session capture, context, planning, mutations, "
        "HTML import, evals, and Figma bridge support. Read-only."
    ),
    "bubble_readiness_check": (
        "Run the recommended Bubble MCP readiness sequence in one compact call: server health, catalog coverage and "
        "quality gate, agent-routing smoke, profile-status readiness when a profile is provided, and optional "
        "profile safe-read or family-preview checks. Use this before broad Bubble work or after installation to avoid "
        "trial-and-error discovery. Output is compact by default; pass include_details=true only when debugging. "
        "Read-only."
    ),
    "bubble_agent_guide": (
        "Return compact routing guidance for MCP clients and agents. Use this when deciding which Bubble MCP tool "
        "family matches a user request, especially to avoid shelling out to CLI help or inspecting repository code. "
        "Read-only."
    ),
    "bubble_tool_search": (
        "Search the exposed Bubble MCP catalog and return compact tool metadata for a query. Use this when the agent "
        "needs to choose between related Bubble tool families without loading or reasoning over the full tools/list "
        "response. Read-only."
    ),
    "bubble_task_recipe": (
        "Return a compact operational recipe for a Bubble task, including preflight checks, ordered tool calls, "
        "arguments to fill, safeguards, and verification guidance. Use this when a client knows the user intent but "
        "needs the correct execution sequence without trial-and-error. Read-only."
    ),
    "bubble_task_runbook": (
        "Return a one-call compact runbook for a Bubble task: route intents, ordered recipe steps, safeguards, "
        "compact matching tool metadata, and optional profile readiness. Use this as the first planning call when an "
        "agent needs to act without inspecting CLI help, repository code, or the full tools/list response. Read-only."
    ),
    "bubble_tool_coverage": (
        "Report execution coverage for every exposed MCP tool. Use this to audit whether tools are handled by "
        "standalone native code, direct Aria-runtime methods, Aria-runtime aliases, custom runtime adapters, compiler "
        "fallback, or are uncovered. The default response is compact; pass include_details=true only when per-tool "
        "classifications are needed. Read-only."
    ),
    "bubble_catalog_quality": (
        "Audit the exposed MCP catalog for agent usability. Checks tool/resource/prompt identifiers, descriptions, "
        "input schemas, property descriptions, annotations, resource metadata, prompt arguments, and runtime coverage "
        "so clients can detect catalog regressions before agents waste tokens on discovery. Read-only."
    ),
    "bubble_runtime_smoke": (
        "Run an operational runtime smoke suite. Use coverage for local catalog execution coverage plus "
        "agent-facing catalog quality, agent-routing to validate natural-language tool selection without writes, "
        "safe-read for read-only profile/session/context checks, preview-write to compile representative Bubble mutations with execute=false, "
        "family-preview to exercise representative visual/container/input/schema/workflow/style/html/branch/changelog "
        "paths without writes, and execute-write with execute=true only when the user explicitly wants real temporary "
        "Bubble writes. Add verify_context=true to refresh the Bubble context and confirm the temporary objects "
        "materialized."
    ),
    "bubble_context_summary": (
        "Summarize a compact Bubble project context file: pages, reusable elements, styles, data types, and indexed "
        "elements. Use before planning changes against a local context artifact. Read-only."
    ),
    "bubble_context_find": (
        "Search a compact Bubble project context file for pages, containers, elements, styles, data types, workflows, "
        "or ids. Use exact=true and include_metadata=false for compact validation checks that must not accept fuzzy "
        "matches; inspect count/truncated and match_field to distinguish direct node matches from context references. "
        "Read-only."
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
    "bubble_eval_export_expert": (
        "Export local captured Bubble editor writes into redacted eval cases with operation-family classification and "
        "tool hints. Use this for harness growth from known-good examples; it is local and read-only."
    ),
    "bubble_visual_compare": (
        "Compare two structured visual snapshots for layout, text, image, typography, max-width, and gradient drift. "
        "Use this lightweight perceptual harness to validate HTML/Figma/Bubble conversion quality from saved "
        "snapshots without reading project code or performing Bubble writes. Read-only."
    ),
    "bubble_visual_capture": (
        "Capture a structured visual snapshot from a URL, local HTML file, or raw HTML source. Use this before "
        "bubble_visual_compare when the agent needs a reference or actual snapshot from source material without "
        "hand-authoring JSON. Read-only."
    ),
    "bubble_compile_plan": (
        "Compile supported abstract Bubble MCP plan steps into Bubble /appeditor/write payloads. Use after planning "
        "and before execution when the caller needs auditable payloads."
    ),
    "bubble_session_list": "List stored Bubble editor session metadata for local profiles. Secrets are redacted. Read-only.",
    "bubble_session_inspect": (
        "Inspect a stored Bubble editor session for one profile, returning redacted session metadata, captured header "
        "keys, cookie presence, and computed /appeditor/write headers. Use this to debug authentication/session "
        "capture without exposing secrets. Read-only."
    ),
    "bubble_session_login": (
        "Start an interactive local Playwright browser login for one Bubble profile, capture editor cookies and "
        "request headers, and save the redacted session locally. Use when the profile lacks an authenticated Bubble "
        "editor session and the user can complete login in the opened browser."
    ),
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
    "bubble_branch_list": (
        "List Bubble editor branches and versions for a profile using the authenticated editor session. Use when the "
        "user asks which branches exist, needs branch ids, or wants to choose a target version before an operation."
    ),
    "bubble_branch_contributors": (
        "List collaborators who have contributed to a Bubble branch/version. Use for changelog filtering, audit "
        "questions, or when the user asks who edited the current branch. Read-only."
    ),
    "bubble_changelog_fetch": (
        "Fetch Bubble editor changelog entries for a profile and branch/version. Supports pagination plus filters for "
        "date range, collaborator user ids, category/type, root page/reusable, change identifier, and change path."
    ),
    "bubble_branch_create": (
        "Create a Bubble development branch or sub-branch from an existing version using the stored editor session. "
        "Use when the user asks to create a branch or child branch; pass from_app_version for the source/parent "
        "branch; execute=false previews the request, execute=true performs it."
    ),
    "bubble_branch_delete": (
        "Soft-delete a Bubble branch/version using the stored editor session. Use only when the user asks to remove a "
        "branch; execute=true also requires confirm=true because this is destructive."
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


DIMENSION_FIELDS = (
    "min_width",
    "max_width",
    "fixed_width",
    "fit_width",
    "min_height",
    "max_height",
    "fixed_height",
    "fit_height",
)
SPACING_FIELDS = (
    "row_gap",
    "column_gap",
    "horiz_alignment",
    "vert_alignment",
    "container_alignment",
    "padding",
    "padding_top",
    "padding_bottom",
    "padding_left",
    "padding_right",
    "margin_top",
    "margin_bottom",
    "margin_left",
    "margin_right",
)
BACKGROUND_FIELDS = (
    "bg_style",
    "bg_color",
    "bg_image",
    "gradient_color1",
    "gradient_color2",
    "gradient_mid",
    "gradient_angle",
)
BORDER_SHADOW_FIELDS = ("border_color", "border_width", "border_style", "border_radius", "shadow")
VISUAL_STYLE_FIELDS = ("style", *DIMENSION_FIELDS, *SPACING_FIELDS, *BACKGROUND_FIELDS, *BORDER_SHADOW_FIELDS, "rotation_angle", "opacity")
QUERY_FIELDS = (
    "query_json",
    "query_result_type",
    "query_source_type",
    "query_result_from_field",
    "query_constraints_json",
    "query_sort_field",
    "query_sort_desc",
    "query_ignore_empty_constraints",
)


EXACT_TOOL_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "refresh_profile_cache": (("profile",), ("dry_run", "settings_path", "skip_clear_cache", "skip_split", "skip_sync_events", "skip_scan_types", "skip_sync_element_refs", "capture_file")),
    "sync_cache": (("profile",), ("dry_run", "settings_path", "mode", "skip_clear_cache", "skip_split", "skip_sync_events", "skip_scan_types", "skip_sync_element_refs", "capture_file")),
    "sync_event_cache": (("profile",), ("dry_run", "settings_path", "context", "clear", "json")),
    "inspect_context": (("profile",), ("dry_run", "settings_path", "context", "scope", "include_elements", "include_workflows", "include_styles", "limit", "json")),
    "resolve_refs": (("profile",), ("dry_run", "settings_path", "context", "parent_ref", "parent_match_index", "element_ref", "element_ref_kind", "match_index", "event_ref", "event_ref_kind", "style_ref", "style_element_type", "data_type_ref", "data_type_ref_kind", "option_set_ref", "option_set_ref_kind", "option_value_ref", "json")),
    "verify_write": (("profile",), ("dry_run", "settings_path", "path", "context", "entity", "ref", "property_path", "ref_kind", "element_ref_kind", "match_index", "expected", "value_type", "json")),
    "sync_element_ref_cache": (("profile", "capture_file"), ("dry_run", "settings_path", "json")),
    "scan_types": (("profile",), ("dry_run", "settings_path", "json")),
    "list_data_types": (("profile",), ("dry_run", "settings_path", "include_cache", "json")),
    "create_page": (("profile", "name"), ("dry_run", "settings_path", "title", "layout", "default_builder_width", "min_width", "min_height", "row_gap", "column_gap", "container_alignment", "style", "keep_overrides", "type_of_content", "url_backup_field", "meta_title", "meta_description", "html_header", *BACKGROUND_FIELDS)),
    "delete_page": (("profile", "name"), ("dry_run", "settings_path", "confirm")),
    "clone_page": (("profile", "source", "name"), ("dry_run", "settings_path", "title")),
    "create_reusable": (("profile", "name"), ("dry_run", "settings_path", "type", "element_type", "layout", *VISUAL_STYLE_FIELDS, "float_v_relative", "float_h_relative", "float_zindex", "parallax", "data_class", "data_source", "properties")),
    "update_reusable_type": (("profile", "name", "type"), ("dry_run", "settings_path")),
    "clone_reusable": (("profile", "source", "name"), ("dry_run", "settings_path")),
    "delete_reusable": (("profile", "name"), ("dry_run", "settings_path", "confirm")),
    "create_custom_state": (("profile", "state_name"), ("dry_run", "settings_path", "element_id", "context", "element_name", "state_type", "default_value", "default_value_json")),
    "create_repeating_group": (("profile", "context", "parent", "name", "data_type"), ("dry_run", "layout", "rows", *QUERY_FIELDS, *VISUAL_STYLE_FIELDS)),
    "update_repeating_group": (("profile", "context", "element_name"), ("dry_run", "settings_path", "layout", "rows", *QUERY_FIELDS, *VISUAL_STYLE_FIELDS)),
    "build_source_query_json": (("profile", "query_source_type"), ("dry_run", "context", "query_result_type", "query_result_from_field", "query_constraints_json", "query_sort_field", "query_sort_desc", "query_ignore_empty_constraints")),
    "build_data_source_json": (("profile",), ("dry_run", "context", "data_source", "query_json", "data_source_json", "query_source_type", "source_type", "query_result_type", "result_type", "query_result_from_field", "result_from_field", "query_constraints_json", "constraints_json", "query_sort_field", "sort_field", "query_sort_desc", "sort_desc", "query_ignore_empty_constraints", "ignore_empty_constraints")),
    "update_text": (("profile", "context", "search_text", "new_text"), ("dry_run", "settings_path")),
    "update_name": (("profile", "context", "element_name", "new_name"), ("dry_run", "settings_path")),
    "update_placeholder": (("profile", "context", "element_name", "new_placeholder"), ("dry_run", "settings_path")),
    "update_style": (("profile", "context", "element_name", "new_style"), ("dry_run", "settings_path", "keep_overrides")),
    "update_style_all": (("profile", "context", "from_style", "to_style"), ("dry_run", "settings_path", "element_type", "keep_overrides")),
    "update_image": (("profile", "context", "element_name", "new_source"), ("dry_run", "settings_path", "prefer_last")),
    "update_icon": (("profile", "context", "element_name", "new_icon"), ("dry_run", "settings_path", "prefer_last")),
    "update_layout": (("profile", "context", "element_name", "property", "value"), ("dry_run", "settings_path")),
    "create_style": (("profile", "name", "element_type"), ("dry_run", "settings_path", "default", "map_type", "map_style", "custom_style", *VISUAL_STYLE_FIELDS)),
    "edit_style": (("profile", "name", "element_type"), ("dry_run", "settings_path", "map_type", "map_style", "custom_style", *VISUAL_STYLE_FIELDS)),
    "add_style_condition": (("profile", "name", "condition"), ("dry_run", "settings_path", *VISUAL_STYLE_FIELDS)),
    "reorder_style_states": (("profile", "name", "order"), ("dry_run", "settings_path")),
    "create_workflow": (("profile", "context", "element_name"), ("dry_run", "settings_path", "event")),
    "create_event": (("profile", "context", "event_type"), ("dry_run", "settings_path", "element_ref", "element_ref_kind", "match_index", "bind_name", "custom_event_name", "run_when", "only_when_json", "interval_seconds", "event_key", "event_id", "id_counter")),
    "create_empty_event": (("profile", "context"), ("dry_run", "settings_path", "event_key", "event_id", "id_counter")),
    "delete_event": (("profile", "context", "event_ref"), ("dry_run", "settings_path", "ref_kind", "confirm")),
    "set_event_type": (("profile", "context", "event_type"), ("dry_run", "settings_path", "event_ref", "ref_kind", "current_event_type", "element", "element_ref_kind", "match_index")),
    "set_event_element": (("profile", "context", "event_ref", "element_ref"), ("dry_run", "settings_path", "event_ref_kind", "element_ref_kind", "match_index", "bind_name")),
    "map_element_ref": (("profile", "context", "alias_name", "element_ref"), ("dry_run", "settings_path", "ref_kind", "match_index")),
    "map_workflow_ref": (("profile", "context", "alias_name", "event_ref"), ("dry_run", "settings_path", "ref_kind", "match_index")),
    "set_event_property": (("profile", "context", "event_ref", "property_path"), ("dry_run", "settings_path", "value", "ref_kind", "value_type", *QUERY_FIELDS)),
    "add_event_go_to_page": (("profile", "context", "event_ref", "page_ref"), ("dry_run", "settings_path", "ref_kind", "action_index", "action_id", "open_in_new_tab", "same_tab", "keep_current_page_params", "add_parameters", "url_parameters_json", "data_to_send_json", "id_counter")),
    "set_event_interval": (("profile", "context", "event_ref", "interval_seconds"), ("dry_run", "settings_path", "ref_kind")),
    "set_condition_run_when": (("profile", "context", "event_ref", "run_when"), ("dry_run", "settings_path", "ref_kind")),
    "set_condition_only_when": (("profile", "context", "event_ref", "only_when_json"), ("dry_run", "settings_path", "ref_kind")),
    "set_custom_event_name": (("profile", "context", "event_ref", "name"), ("dry_run", "settings_path", "ref_kind")),
    "set_custom_event_parameters": (("profile", "context", "event_ref", "parameters_json"), ("dry_run", "settings_path", "ref_kind", "id_counter")),
    "add_custom_event_parameter": (("profile", "context", "event_ref", "param_name", "btype_id"), ("dry_run", "settings_path", "is_list", "optional", "param_id", "ref_kind", "id_counter")),
    "set_custom_event_return_types": (("profile", "context", "event_ref", "return_types_json"), ("dry_run", "settings_path", "ref_kind", "id_counter")),
    "add_custom_event_return_type": (("profile", "context", "event_ref", "return_name", "btype_id"), ("dry_run", "settings_path", "is_list", "optional", "return_id", "ref_kind", "id_counter")),
    "add_action": (("profile", "context", "action_type"), ("dry_run", "settings_path", "element_name", "event_ref", "event", "event_type", "ref_kind", "param", "data_type", "fields", "thing", *QUERY_FIELDS, "to_email", "to", "subject", "body", "message", "title", "pause_ms", "hide_status_bar", "open_in_new_tab")),
    "replace_action": (("profile", "context", "element_name", "action_type", "param"), ("dry_run", "settings_path", "event")),
    "delete_action": (("profile", "context", "action_ref"), ("dry_run", "settings_path", "element_name", "event", "event_ref", "event_type", "ref_kind", "action_ref_kind", "confirm")),
    "cleanup_empty_actions": (("profile", "context"), ("dry_run", "settings_path", "element_name", "event", "event_ref", "event_type", "ref_kind")),
}


FIELD_TYPES: dict[str, dict[str, Any]] = {
    "dry_run": {"type": "boolean", "default": True},
    "execute": {"type": "boolean", "default": False},
    "confirm": {"type": "boolean", "default": False},
    "force": {"type": "boolean"},
    "compile": {"type": "boolean"},
    "clear": {"type": "boolean"},
    "json": {"type": "boolean"},
    "include_elements": {"type": "boolean"},
    "include_workflows": {"type": "boolean"},
    "include_styles": {"type": "boolean"},
    "checked": {"type": "boolean"},
    "required": {"type": "boolean"},
    "fixed_width": {"type": "boolean"},
    "fit_width": {"type": "boolean"},
    "fixed_height": {"type": "boolean"},
    "fit_height": {"type": "boolean"},
    "keep_overrides": {"type": "boolean"},
    "default": {"type": "boolean"},
    "query_sort_desc": {"type": "boolean"},
    "query_ignore_empty_constraints": {"type": "boolean"},
    "sort_desc": {"type": "boolean"},
    "ignore_empty_constraints": {"type": "boolean"},
    "show_time": {"type": "boolean"},
    "autoplay": {"type": "boolean"},
    "open_in_new_tab": {"type": "boolean"},
    "same_tab": {"type": "boolean"},
    "keep_current_page_params": {"type": "boolean"},
    "add_parameters": {"type": "boolean"},
    "is_list": {"type": "boolean"},
    "optional": {"type": "boolean"},
    "hide_status_bar": {"type": "boolean"},
    "limit_image_size_before_upload": {"type": "boolean"},
    "prefer_last": {"type": "boolean"},
    "include_cache": {"type": "boolean"},
    "rows": {"type": "integer"},
    "limit": {"type": "integer"},
    "match_index": {"type": "integer"},
    "parent_match_index": {"type": "integer"},
    "action_index": {"type": "integer"},
    "pause_ms": {"type": "integer"},
    "interval_seconds": {"type": "number"},
    "min": {"type": "number"},
    "max": {"type": "number"},
    "val": {"type": "number"},
    "step": {"type": "number"},
    "gradient_mid": {"type": "number"},
    "gradient_angle": {"type": "number"},
    "rotation_angle": {"type": "number"},
    "opacity": {"type": "number"},
    "payload": {"type": "object"},
    "write_payload": {"type": "object"},
    "properties": {"type": "object"},
    "query_json": {"type": "object"},
    "data_source_json": {"type": "object"},
    "query_constraints_json": {"type": "array", "items": {"type": "object"}},
    "constraints_json": {"type": "array", "items": {"type": "object"}},
    "only_when_json": {"type": "object"},
    "url_parameters_json": {"type": "object"},
    "data_to_send_json": {"type": "object"},
    "parameters_json": {"type": "array", "items": {"type": "object"}},
    "return_types_json": {"type": "array", "items": {"type": "object"}},
    "fields": {"type": ["string", "object"]},
    "choices": {"type": ["string", "array"], "items": {"type": "string"}},
    "layout": {"type": "string", "enum": ["column", "row", "align_to_parent", "fixed"]},
    "container_alignment": {"type": "string", "enum": ["left", "center", "right", "stretch"]},
    "horiz_alignment": {"type": "string", "enum": ["flex-start", "center", "flex-end", "space-between", "stretch"]},
    "vert_alignment": {"type": "string", "enum": ["flex-start", "center", "flex-end", "space-between", "stretch"]},
    "float_v_relative": {"type": "string", "enum": ["top", "bottom", "both"]},
    "float_h_relative": {"type": "string", "enum": ["left", "right", "both"]},
    "float_zindex": {"type": "string", "enum": ["front", "back"]},
    "content_format": {"type": "string", "enum": ["text", "email", "password", "integer", "decimal", "date"]},
    "origin": {"type": "string", "enum": ["youtube", "vimeo", "html5", "external"]},
    "bg_style": {"type": "string", "enum": ["none", "color", "image", "gradient"]},
    "border_style": {"type": "string", "enum": ["none", "solid", "dashed", "dotted"]},
    "element_type": {
        "type": "string",
        "enum": [
            "Group",
            "Text",
            "Button",
            "Input",
            "Image",
            "Icon",
            "HTML",
            "Popup",
            "RepeatingGroup",
            "ReusableElement",
        ],
    },
    "value_type": {"type": "string", "enum": ["string", "number", "boolean", "json", "expression"]},
    "ref_kind": {"type": "string", "enum": ["auto", "id", "key", "alias", "name", "text"]},
    "element_ref_kind": {"type": "string", "enum": ["auto", "id", "alias", "name", "text"]},
    "event_ref_kind": {"type": "string", "enum": ["auto", "id", "key", "alias", "name"]},
    "action_ref_kind": {"type": "string", "enum": ["auto", "id", "key", "index", "alias"]},
    "data_type_ref_kind": {"type": "string", "enum": ["auto", "id", "name"]},
    "option_set_ref_kind": {"type": "string", "enum": ["auto", "id", "name"]},
    "option_value_ref_kind": {"type": "string", "enum": ["auto", "id", "name", "display"]},
    "scope": {"type": "string", "enum": ["elements", "workflows", "styles", "schema", "all"]},
    "mode": {"type": "string", "enum": ["full", "fast", "events", "types", "elements"]},
    "placement": {"type": "string", "enum": ["top", "bottom", "append", "prepend", "replace children"]},
    "change_path": {"type": ["string", "array"], "items": {"type": "string"}},
    "user_id": {"type": ["string", "array"], "items": {"type": "string"}},
    "reference": {"type": "string"},
    "actual": {"type": "string"},
    "tolerance_px": {"type": "number", "minimum": 0, "default": 4},
    "tolerance_ratio": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.08},
    "require_text": {"type": "boolean", "default": True},
    "require_images": {"type": "boolean", "default": False},
}


def enhance_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an MCP tool schema optimized for agent selection."""

    tool = deepcopy(schema)
    name = str(tool.get("name") or "")
    tool["description"] = NATIVE_TOOL_DESCRIPTIONS.get(name) or legacy_description(name)
    tool["annotations"] = tool_annotations(name)
    input_schema = tool.setdefault("inputSchema", {"type": "object"})
    if isinstance(input_schema, dict):
        input_schema.setdefault("$schema", "http://json-schema.org/draft-07/schema#")
    apply_legacy_specific_schema(tool)
    describe_input_properties(tool)
    return tool


def apply_legacy_specific_schema(tool: dict[str, Any]) -> None:
    name = str(tool.get("name") or "")
    fields = _legacy_fields_for_name(name)
    if fields is None:
        return
    required, optional = fields
    input_schema = tool.setdefault("inputSchema", {"type": "object"})
    properties: dict[str, Any] = {}
    input_schema["properties"] = properties
    input_schema["required"] = list(dict.fromkeys(required))
    bridge_fields: tuple[str, ...] = ()
    if _is_mutating(name):
        bridge_fields = ("app_id", "app_version", "context_file", "execute", "write_payload", "payload")
    if tool_annotations(name)["destructiveHint"]:
        bridge_fields = (*bridge_fields, "confirm")
    for field in dict.fromkeys((*required, *optional, *bridge_fields)):
        properties.setdefault(field, _property_schema(field))


def _legacy_fields_for_name(name: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    if name in EXACT_TOOL_FIELDS:
        return EXACT_TOOL_FIELDS[name]
    visual_fields = _visual_fields_for_name(name)
    if visual_fields is not None:
        return visual_fields
    if name.startswith(("delete_", "clear_", "regenerate_")):
        return (("profile",), ("dry_run", "settings_path", "name", "confirm"))
    if name.startswith(("list_", "inspect_", "scan_", "resolve_", "verify_")):
        return (("profile",), ("dry_run", "settings_path", "context", "query", "limit", "json"))
    if name.startswith(("create_data_type", "rename_data_type", "delete_data_type", "create_data_field", "rename_data_field", "set_data_type_api_exposure")):
        return _data_schema_fields(name)
    if name.startswith(("create_option_", "rename_option_", "delete_option_", "list_option_", "set_option_", "reorder_option_")):
        return _option_schema_fields(name)
    if name.startswith(("create_color", "update_color", "delete_color", "delete_colors", "clear_custom_colors", "reorder_colors")):
        return _color_schema_fields(name)
    if name.startswith(("create_font", "update_font", "delete_font")) or name == "list_fonts":
        return (("profile",), ("dry_run", "settings_path", "name", "value", "confirm", "json"))
    if name.startswith(("set_app_setting", "set_project_setting", "list_project_settings")):
        return (("profile",), ("dry_run", "settings_path", "name", "value", "json"))
    if name.startswith(("create_api_token", "rename_api_token", "regenerate_api_token", "delete_api_token")):
        return (("profile",), ("dry_run", "settings_path", "name", "token_id", "private_key", "confirm"))
    if "app_text" in name or "text_match" in name:
        return _app_text_fields(name)
    if name.startswith(("sync_figma_", "sync_component", "upload_asset")):
        return (("profile",), ("dry_run", "settings_path", "context", "parent", "name", "file", "payload", "execute", "json"))
    if name in {"batch", "natural"}:
        return (("profile",), ("dry_run", "settings_path", "message", "commands", "execute", "json"))
    return None


def _property_schema(field: str) -> dict[str, Any]:
    schema = deepcopy(FIELD_TYPES.get(field, {"type": "string"}))
    schema.setdefault("description", COMMON_PROPERTY_DESCRIPTIONS.get(field, f"Argument '{field}' for this Bubble MCP tool."))
    return schema


def _visual_fields_for_name(name: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    create_fields: dict[str, tuple[str, ...]] = {
        "group": ("name", "layout", *VISUAL_STYLE_FIELDS, "data_class", "data_source", *QUERY_FIELDS),
        "floating_group": ("name", "layout", *VISUAL_STYLE_FIELDS, "float_v_relative", "float_h_relative", "float_zindex", "parallax"),
        "group_focus": ("name", "layout", *VISUAL_STYLE_FIELDS),
        "table": ("name", "data_type", "rows", *QUERY_FIELDS, *VISUAL_STYLE_FIELDS),
        "popup": ("name", "layout", *VISUAL_STYLE_FIELDS, "data_class", "data_source"),
        "text": ("content", "name", "style", *VISUAL_STYLE_FIELDS),
        "button": ("label", "name", "style", "icon", *VISUAL_STYLE_FIELDS),
        "input": ("name", "placeholder", "content_format", "style", *VISUAL_STYLE_FIELDS),
        "multiline_input": ("name", "placeholder", "style", *VISUAL_STYLE_FIELDS),
        "dropdown": ("name", "placeholder", "choices", "dynamic_type", "option_caption_field", "style", *QUERY_FIELDS, *VISUAL_STYLE_FIELDS),
        "searchbox": ("name", "placeholder", "data_type", "style", *QUERY_FIELDS, *VISUAL_STYLE_FIELDS),
        "checkbox": ("name", "label", "checked", "required", "style", *VISUAL_STYLE_FIELDS),
        "datepicker": ("name", "placeholder", "show_time", "style", *VISUAL_STYLE_FIELDS),
        "radio": ("name", "label", "group_name", "choices", "selected", "style", *VISUAL_STYLE_FIELDS),
        "slider": ("name", "min", "max", "val", "step", "style", *VISUAL_STYLE_FIELDS),
        "file_uploader": ("name", "label", "style", *VISUAL_STYLE_FIELDS),
        "picture_uploader": ("name", "label", "style", "limit_image_size_before_upload", *VISUAL_STYLE_FIELDS),
        "shape": ("name", "style", "color", *VISUAL_STYLE_FIELDS),
        "video": ("name", "url", "video_id", "origin", "autoplay", "style", *VISUAL_STYLE_FIELDS),
        "image": ("name", "source", "style", *VISUAL_STYLE_FIELDS),
        "icon": ("name", "icon", "style", "color", *VISUAL_STYLE_FIELDS),
        "html": ("name", "html", "style", *VISUAL_STYLE_FIELDS),
        "link": ("name", "label", "url", "style", *VISUAL_STYLE_FIELDS),
        "alert": ("name", "content", "style", *VISUAL_STYLE_FIELDS),
        "map": ("name", "data_source", "style", *VISUAL_STYLE_FIELDS),
        "reusable_instance": ("name", "source", "source_context", *VISUAL_STYLE_FIELDS),
    }
    for element, fields in create_fields.items():
        if name == f"create_{element}":
            return (("profile", "context", "parent", *fields[:1]), ("dry_run", "settings_path", *fields[1:]))
        if name == f"update_{element}" or name == f"update_{element}_element":
            return (("profile", "context", "element_name"), ("dry_run", "settings_path", *fields, "prefer_last"))
        if name == f"delete_{element}":
            return (("profile", "context", "element_name"), ("dry_run", "settings_path", "prefer_last", "confirm"))
    return None


def _data_schema_fields(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if name == "create_data_type":
        return (("profile", "name"), ("dry_run", "settings_path", "fields", "exposed_api", "confirm"))
    if name == "rename_data_type":
        return (("profile", "data_type_ref", "new_name"), ("dry_run", "settings_path", "data_type_ref_kind"))
    if name == "delete_data_type":
        return (("profile", "data_type_ref"), ("dry_run", "settings_path", "data_type_ref_kind", "confirm"))
    if name == "create_data_field":
        return (("profile", "data_type_ref", "name", "type"), ("dry_run", "settings_path", "is_list", "optional"))
    if name == "rename_data_field":
        return (("profile", "data_type_ref", "name", "new_name"), ("dry_run", "settings_path"))
    return (("profile", "data_type_ref"), ("dry_run", "settings_path", "value", "confirm"))


def _option_schema_fields(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if name in {"create_option_set", "rename_option_set", "delete_option_set"}:
        required = ("profile", "name") if name == "create_option_set" else ("profile", "option_set_ref")
        return (required, ("dry_run", "settings_path", "new_name", "confirm", "values", "attributes"))
    if name in {"create_option_attribute", "create_option_value", "rename_option_value", "delete_option_value", "set_option_value_attribute"}:
        return (("profile", "option_set_ref", "name"), ("dry_run", "settings_path", "type", "value", "new_name", "option_value_ref", "confirm"))
    return (("profile", "option_set_ref"), ("dry_run", "settings_path", "order", "json"))


def _color_schema_fields(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if name == "list_colors":
        return (("profile",), ("dry_run", "settings_path", "json"))
    if name in {"delete_colors", "clear_custom_colors", "reorder_colors"}:
        return (("profile",), ("dry_run", "settings_path", "names", "pattern", "order", "confirm"))
    return (("profile", "name"), ("dry_run", "settings_path", "color", "value", "confirm"))


def _app_text_fields(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if name in {"list_app_texts", "list_text_matches"}:
        return (("profile",), ("dry_run", "settings_path", "query", "context", "limit", "json"))
    if name == "set_app_text_translation":
        return (("profile", "name", "language", "value"), ("dry_run", "settings_path"))
    if name.startswith("convert_"):
        return (("profile", "context"), ("dry_run", "settings_path", "element_name", "path", "search_text", "name", "language"))
    return (("profile", "name"), ("dry_run", "settings_path", "value", "language", "context"))


def legacy_description(name: str) -> str:
    category = _category_for_name(name)
    return (
        f"{category} This is an Aria-compatible Bubble MCP tool. Use it when the user's intent matches this "
        "capability by outcome, not because the user named the tool. Prefer profile/context arguments for normal "
        "operation; pass an exact write_payload only when another step already produced a validated Bubble payload."
    )


def tool_annotations(name: str) -> dict[str, bool]:
    agent_read_only = {
        "bubble_agent_guide",
        "bubble_profile_status",
        "bubble_tool_search",
        "bubble_task_recipe",
        "bubble_task_runbook",
        "bubble_catalog_quality",
        "bubble_readiness_check",
    }
    read_only = _is_read_only(name) or name in agent_read_only
    destructive = name.startswith(("delete_", "clear_", "regenerate_")) or name in {"bubble_branch_delete"}
    return {
        "readOnlyHint": read_only,
        "destructiveHint": destructive,
        "idempotentHint": read_only
        or name
        in {"bubble_health_check", "bubble_project_bootstrap", "bubble_profile_add", "bubble_profile_list", *agent_read_only},
        "openWorldHint": name
        in {
            "bubble_project_bootstrap",
            "bubble_session_login",
            "bubble_context_detect",
            "create_from_html",
            "bubble_editor_write",
            "bubble_execute_plan",
            "bubble_visual_capture",
            "bubble_branch_list",
            "bubble_branch_contributors",
            "bubble_changelog_fetch",
            "bubble_branch_create",
            "bubble_branch_delete",
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
        "bubble_tool_coverage",
        "bubble_runtime_smoke",
        "bubble_context_summary",
        "bubble_context_find",
        "bubble_session_list",
        "bubble_session_inspect",
        "bubble_eval_run",
        "bubble_eval_export_expert",
        "bubble_visual_compare",
        "bubble_visual_capture",
        "bubble_plan",
        "bubble_plan_dry_run",
        "bubble_compile_plan",
        "bubble_branch_list",
        "bubble_branch_contributors",
        "bubble_changelog_fetch",
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
