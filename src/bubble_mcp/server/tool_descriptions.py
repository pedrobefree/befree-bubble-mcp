"""Per-tool, agent-facing descriptions for catalog tools that used to share one category blurb.

MCP clients pick tools by name + description. When thirteen workflow tools all said
"Create or modify Bubble workflows, events, actions, conditions, and workflow references."
the agent could not tell ``create_workflow`` from ``delete_action``. Every entry here is
one or two sentences that say what the tool does, what it needs, and when NOT to use it.
``agent_catalog._category_for_name`` consults this map before the legacy category table.
"""

from __future__ import annotations

# --- Bubble-native (bubble_*) tools that had no entry in NATIVE_TOOL_DESCRIPTIONS ----------

NATIVE_TOOL_DESCRIPTION_EXTRAS: dict[str, str] = {
    "bubble_transfer_inventory": (
        "Inventory a Bubble page, reusable, or element subtree in a source profile before a cross-project transfer: "
        "elements, styles, workflows, data dependencies, and API Connector structure. Does not write to Bubble."
    ),
    "bubble_transfer_plan": (
        "Plan a cross-project transfer from source_profile to target_profile: resolve the source ref, compute "
        "dependencies, conflicts, asset/collection/API Connector policies, and return a transfer_id for preview/execute."
    ),
    "bubble_transfer_preview": (
        "Preview a planned transfer by transfer_id: ordered steps, skipped dependencies, and optional compiled payloads. "
        "Does not write to Bubble; run before bubble_transfer_execute."
    ),
    "bubble_transfer_execute": (
        "Execute a planned transfer by transfer_id into the target profile (requires confirm=true). Writes pages, "
        "reusables, elements, styles, and allowed dependencies; never copies API Connector secrets."
    ),
    "bubble_transfer_status": "Return the status, executed steps, and follow-ups of a transfer by transfer_id without writing to Bubble.",
    "bubble_schedule_deploy": (
        "Schedule a Bubble deploy from development to live at scheduled_at with a deploy message (requires "
        "confirm=true); can retry and optionally auto-fix issue checklist items. Use bubble_list_scheduled_deploys to review."
    ),
    "bubble_list_scheduled_deploys": "List scheduled Bubble deploys for the profile with ids, times, and state. Read-only.",
    "bubble_cancel_scheduled_deploy": "Cancel one scheduled Bubble deploy by deploy_id before it runs; use bubble_list_scheduled_deploys to find the id first.",
    "bubble_deploy_history": "Fetch recent Bubble deploy history (optionally including cancelled deploys). Read-only.",
    "bubble_branch_merge_start": (
        "Start a Bubble branch merge between ours_version_id and theirs_version_id, creating a savepoint and returning "
        "a merge session with any conflicts. Follow with bubble_branch_merge_conflicts_describe / resolve / confirm / finalize."
    ),
    "bubble_branch_merge_confirm": (
        "Confirm a started branch merge for merge_app_version once conflicts_resolved is true, moving the merge session "
        "to the finalize step."
    ),
    "bubble_extension_import": (
        "Import a validated Bubble MCP extension pack directory (extension.json + tools/) into the local extensions store "
        "in pending state. Follow with bubble_extension_enable to expose its tools in tools/list."
    ),
    "bubble_extension_enable": (
        "Enable an imported extension pack by extension_id so its declarative tools (for example "
        "create_api_connector_call) appear in tools/list after the client refreshes its tool list."
    ),
    "bubble_extension_disable": "Disable an enabled extension pack by extension_id, removing its tools from tools/list.",
    "bubble_extension_companion_start": (
        "Start the local Chrome companion bridge (host/port/capture_key) that captures Bubble editor writes into an "
        "active tool-authoring session for the tool wizard."
    ),
    "bubble_extension_companion_status": "Report whether the Chrome companion bridge is running and which tool-authoring session it feeds. Read-only.",
    "bubble_extension_companion_stop": "Stop the local Chrome companion bridge used for tool-authoring capture.",
    "bubble_framework_plan_from_text": (
        "Turn free text into a framework (for example BMAD) plan/program for Bubble work using the framework language pack. "
        "Read-only planning step before bubble_framework_compile_program/execute_program."
    ),
    "bubble_framework_execute_program": (
        "Execute a compiled framework program for Bubble (mode preview/execute; mutating runs require approved=true) and "
        "write artifacts to artifact_dir."
    ),
    "bubble_framework_workspace_sync": "Sync framework artifacts from artifact_dir into a workspace_dir for the selected framework.",
    "bubble_language_cache_status": "Report the local language registry cache state for a framework (version, freshness, hit counts). Read-only.",
    "bubble_tool_wizard_activate": "Make an existing tool-authoring session (session_id) the active capture target for the Chrome companion.",
}


# --- Aria-compatible catalog tools ---------------------------------------------------------

LEGACY_TOOL_DESCRIPTIONS: dict[str, str] = {
    # Workflows / events / actions
    "create_workflow": (
        "Create a new Bubble workflow (event shell) for a page or element: element_name='Page' for page-load workflows, "
        "or an element name/ref for element events. Returns the event ref to use with add_action. Does not add actions."
    ),
    "add_action": (
        "Add one action (action_type such as create_thing, make_changes, navigate, show/hide, send_email, set_state, "
        "schedule_api_workflow, custom_event) to an existing workflow. Target it by element_name+event for "
        "click/change/load, or by event_ref (workflow key/id/name/alias, or shorthand like 'ButtonClicked my-button') "
        "for any workflow, including ConditionTrue, CustomEvent, and DoEvery. Reuses the workflow; does not create a "
        "new one when the event already exists. Prefer event_ref over manual bubble_editor_write payloads; for action types this tool does not support (especially expression-heavy ones), capture the real editor write with bubble_tool_wizard_start instead of composing bodies from the export. To change an action that already exists, use bubble_node_edit rather than adding a replacement."
    ),
    "replace_action": "Replace an existing action in a workflow (by event/element and action_type) with new parameters, keeping its position.",
    "delete_action": "Delete one action (action_ref) from a workflow after explicit confirm=true. Does not delete the event.",
    "create_event": (
        "Create a workflow event of a given event_type (ButtonClicked, PageLoaded, CustomEvent, DoEvery, condition-true, etc.) "
        "bound to an element_ref, with optional run_when/only_when conditions. Use create_workflow for the simple page/element case."
    ),
    "delete_event": "Delete a workflow event (event_ref) and all its actions after explicit confirm=true.",
    "set_event_type": "Change the trigger type (event_type) of an existing workflow event, optionally rebinding it to another element.",
    "set_event_element": "Bind or rebind a workflow event (event_ref) to a visual element (element_ref), for example a button that triggers it.",
    "map_workflow_ref": "Create an alias_name for a workflow event ref so later calls can target it by a stable name.",
    "set_event_property": "Set one raw property (property_path/value) on a workflow event, including query/data-source JSON for dynamic values.",
    "set_event_interval": "Set interval_seconds of a 'Do every X seconds' workflow event.",
    "set_condition_run_when": "Set the 'Run when' (run_when) trigger condition expression of a workflow event.",
    "set_condition_only_when": "Set the 'Only when' (only_when_json) condition of a workflow event or action.",
    "create_empty_event": "Create an empty workflow event shell with an explicit event_key/event_id (low-level; prefer create_workflow/create_event).",
    "cleanup_empty_actions": "Remove empty/placeholder actions from a workflow (element_name/event/event_ref) so it stays valid.",
    "add_event_go_to_page": "Add a 'Go to page' navigation action to a workflow event (event_ref) targeting page_ref, with URL/data parameters and tab options.",
    "set_custom_event_name": "Rename a custom workflow event (event_ref) to name.",
    "set_custom_event_parameters": "Replace the parameter list of a custom event (event_ref) with parameters_json.",
    "add_custom_event_parameter": "Add one parameter (param_name, btype_id, is_list, optional) to a custom workflow event.",
    "set_custom_event_return_types": "Replace the return types of a custom event (event_ref) with return_types_json.",
    "add_custom_event_return_type": "Add one return value (return_name, btype_id, is_list, optional) to a custom workflow event.",
    # Built-in user actions
    "log_the_user_in": "Add a 'Log the user in' action to a workflow (event_ref) using email/password input refs.",
    "log_the_user_out": "Add a 'Log the user out' action to a workflow (event_ref).",
    "sign_the_user_up": "Add a 'Sign the user up' action to a workflow with email/password inputs, optional confirmation fields and extra user fields.",
    "signup_login_with_a_social_network": "Add a 'Signup/login with a social network' action (oauth_provider, scopes, app credentials) to a workflow.",
    "send_confirmation_email": "Add a 'Send confirmation email' action to a workflow, optionally just_make_token and a confirmation_page_ref.",
    "make_changes_to_current_user": "Add a 'Make changes to current user' action with a fields map to a workflow (event_ref).",
    "update_user_credentials": "Add an 'Update the user's credentials' action (change email/password with input refs and confirmation) to a workflow.",
    # Data schema / privacy
    "create_data_type": "Create a new Bubble data type (thing) named name with optional initial fields and exposed_api flag.",
    "rename_data_type": "Rename an existing data type (data_type_ref) to new_name.",
    "delete_data_type": "Delete a data type (data_type_ref) and its fields after explicit confirm=true.",
    "create_data_field": "Add a field (name, type, is_list, optional) to an existing data type (data_type_ref).",
    "rename_data_field": "Rename a field (name to new_name) on a data type (data_type_ref).",
    "delete_data_field": "Delete a field (name) from a data type (data_type_ref) after explicit confirm=true.",
    "list_privacy_rules": "List privacy rules of a data type (data_type_ref) with their conditions and permissions. Read-only.",
    "create_privacy_rule": "Create a privacy rule (rule_key/rule_name, condition_json, view/search/autobinding permissions, visible fields) on a data type.",
    "delete_privacy_rule": "Delete a privacy rule (rule_key) from a data type after explicit confirm=true.",
    "set_privacy_rule_name": "Rename a privacy rule (rule_key) of a data type to new_name.",
    "set_privacy_rule_condition": "Set the condition_json of a privacy rule (rule_key) on a data type.",
    "set_privacy_rule_permission": "Set one permission flag (permission=view_all|search_for|view_attachments|..., value) of a privacy rule.",
    "set_privacy_rule_field_visibility": "Set which fields a privacy rule exposes (view_all or an explicit view_fields list).",
    "set_privacy_rule_auto_binding": "Set auto_binding and the binding_fields list of a privacy rule.",
    "set_data_type_api_exposure": "Toggle Data API exposure (value true/false) of a data type (data_type_ref); requires confirm=true.",
    # Option sets
    "create_option_set": "Create an option set named name with optional attributes and initial values.",
    "rename_option_set": "Rename an option set (option_set_ref) to new_name.",
    "delete_option_set": "Delete an option set (name) and its values after explicit confirm=true.",
    "create_option_attribute": "Add an attribute (name, type) to an option set (option_set_ref).",
    "create_option_value": "Add an option value (name, optional attribute values) to an option set (option_set_ref).",
    "delete_option_value": "Delete one option value (name) from an option set after explicit confirm=true.",
    "list_option_values": "List values of an option set (with optional query filter). Read-only.",
    "rename_option_value": "Rename an option value (option_value_ref/value) of an option set to new_name.",
    "set_option_value_attribute": "Set an attribute (name/type) value on one option value of an option set.",
    "reorder_option_values": "Reorder the values of an option set (option_set_ref) to the given order.",
    # Caches / context / inspection
    "refresh_profile_cache": "Rebuild the local profile cache (clear, split, sync events/types/element refs) from the latest .bubble export or capture_file.",
    "sync_cache": "Run the cache sync pipeline (mode full|incremental) for the profile: split app export, sync events, scan types, sync element refs.",
    "clear_cache": "Clear a named local cache (name) for the profile after confirm=true.",
    "list_events": "List workflow events in a context (page/reusable) with optional query filter and limit. Read-only.",
    "sync_event_cache": "Rebuild the workflow event cache for a context (optionally clear first).",
    "sync_workflow_ref_cache": "Rebuild workflow ref aliases for a context/parent (confirm=true to overwrite).",
    "sync_element_ref_cache": "Rebuild the element ref cache from the app export or a capture_file.",
    "list_element_ref_maps": "List element ref aliases (alias_name to element) for a context. Read-only.",
    "map_element_ref": "Create an alias_name for a visual element ref (element_ref, ref_kind, match_index) so later calls can target it by name.",
    "resolve_refs": "Resolve element/event/style/data-type/option-set refs in a context to concrete Bubble ids without mutating anything. Read-only.",
    "inspect_context": "Inspect a context (page/reusable): elements, workflows, styles, scoped by include_* flags and limit. Read-only.",
    "verify_write": "Verify that a previous write landed: compare a property_path of an entity/ref in context against an expected value. Read-only.",
    "scan_types": "Scan the app export and rebuild the data-type/field index used for ref resolution.",
    "list_data_types": "List Bubble data types and their fields (optionally from cache). Read-only.",
    # Pages / reusables
    "create_page": "Create a new page named name with title, layout, size, style, type_of_content, SEO meta fields, and background options.",
    "delete_page": "Delete a page (name) after explicit confirm=true.",
    "clone_page": "Clone an existing page (source) into a new page (name, optional title).",
    "create_reusable": "Create a reusable element (name, type/element_type, layout, size, style, data_class/data_source) for use across pages.",
    "update_reusable": "Update properties of an existing reusable element definition in context.",
    "update_reusable_type": "Change the content type (type) of a reusable element (name).",
    "clone_reusable": "Clone an existing reusable element (source) into a new one (name).",
    "delete_reusable": "Delete a reusable element (name) after explicit confirm=true.",
    # Styles
    "create_style": "Create a named style (name, element_type) with layout, padding/margin, background, border, shadow, and opacity properties.",
    "edit_style": "Edit properties of an existing style (name, element_type) such as background, border, padding, size, or opacity.",
    "update_style": "Apply an existing style (new_style) to one element (element_name) in context; keep_overrides keeps element-level overrides.",
    "update_style_all": "Re-point every element of element_type using from_style to to_style across the context.",
    "add_style_condition": "Add a conditional state (condition such as hovered/pressed/focused) with its property overrides to a style (name).",
    "reorder_style_states": "Reorder the conditional states of a style (name) to the given order.",
    "create_button_style": "Create a button style preset in context.",
    "rename_style": "Rename an existing style.",
    "delete_style": "Delete one style (name) after explicit confirm=true.",
    "delete_styles": "Delete several styles matching name/pattern after explicit confirm=true.",
    "clear_custom_styles": "Remove all custom (non-default) styles after explicit confirm=true.",
    # Colors / fonts
    "create_color": "Create an app color token (name, color/value).",
    "update_color": "Update the value of an app color token (name) to color/value.",
    "delete_color": "Delete one app color token (name) after explicit confirm=true.",
    "delete_colors": "Delete several app color tokens matching name/pattern after explicit confirm=true.",
    "clear_custom_colors": "Remove all custom color tokens after explicit confirm=true.",
    "reorder_colors": "Reorder app color tokens (names/pattern/order).",
    "create_font": "Add an app font (name, value/source).",
    "update_font": "Update an app font (name) to value.",
    "delete_font": "Delete an app font (name) after explicit confirm=true.",
    # App text / translations
    "list_app_texts": "List app texts (translation keys) with optional query filter. Read-only.",
    "list_text_matches": "List visual text occurrences matching query across a context, to find candidates for app-text conversion. Read-only.",
    "create_app_text": "Create an app text entry (name, value, language).",
    "set_app_text_translation": "Set the translation value of an app text (name) for a language.",
    "convert_text_to_app_text": "Convert the static text of an element (element_name/path/search_text) into an app text entry (name, language) and bind it.",
    "convert_text_parts_to_app_text": "Convert matching parts (search_text) of an element's text into app text entries and bind them.",
    "convert_text_path_to_app_text": "Convert the text at a specific property path of an element into an app text entry and bind it.",
    "propagate_app_text": "Propagate an app text value (name, value, language) to every element bound to it in context.",
    # Design-system sync / assets
    "sync_figma_component": "Sync one Figma component definition (file) from the local bridge into Bubble under parent in context.",
    "sync_component": "Sync a local component export (file) from the bridge into Bubble under parent in context.",
    "sync_figma_style": "Sync one Figma style (file) from the local bridge into Bubble styles.",
    "sync_figma_tokens": "Sync Figma design tokens (file: colors, fonts) from the local bridge into Bubble app tokens.",
    "upload_asset": "Upload a local file (image/asset) to Bubble and return its URL for use in elements.",
    # API tokens (Data API) — NOT the API Connector plugin
    "create_api_token": (
        "Create a Bubble Data API / Workflow API token in Settings > API (name, optional token_id/private_key). "
        "This is NOT the API Connector plugin: to create an external API call use create_api_connector_call."
    ),
    "rename_api_token": "Rename an existing Data API token (Settings > API). Not related to API Connector calls.",
    "regenerate_api_token": "Regenerate the private key of a Data API token (name) after confirm=true. Not related to API Connector calls.",
    "delete_api_token": "Delete a Data API token (name) after confirm=true. Not related to API Connector calls (use the API Connector tools for those).",
    # Settings / redirects
    "set_app_setting": "Set one Bubble app setting (name, value) in Settings.",
    "set_project_setting": "Set one local bubble-mcp project/profile setting (name, value).",
    "list_project_settings": "List local bubble-mcp project/profile settings (optional query). Read-only.",
    "list_301_redirects": "List configured 301 redirects of the app. Read-only.",
    "create_301_redirect": "Create a 301 redirect rule in app settings.",
    "delete_301_redirect": "Delete a 301 redirect rule (name) after explicit confirm=true.",
    # Misc visual helpers
    "update_name": "Rename a visual element (element_name to new_name) in context without changing other properties.",
    "update_placeholder": "Change the placeholder text (new_placeholder) of an input-like element (element_name).",
    "update_layout": "Set one layout property (property/value such as layout type, gap, alignment, size) on an element (element_name).",
    "create_custom_state": "Add a custom state (state_name, state_type, default_value) to an element (element_name/element_id) in context.",
    "list_global_expressions": "List app-level global expressions with their id, return type, parameters, and whether a body expression is set.",
    "create_global_expression": "Create an app-level global expression (name, expression_type, is_list); its body starts empty and is set separately.",
    "set_global_expression_parameter": "Add or retype a parameter (parameter_name, parameter_type, is_list) on an existing global expression.",
    "set_global_expression_expression": "Point a global expression body at one of its own parameters, optionally chaining one field such as email.",
    "delete_global_expression": "Remove a global expression (expression, by id or name) along with the index entries its creation registered.",
    "list_global_expression_folders": "List global expression folders with their id, name, and the expressions each one holds.",
    "create_global_expression_folder": "Create a folder (name) for grouping global expressions; folders are an app setting, not a node.",
    "rename_global_expression_folder": "Rename a global expression folder (folder, by id or current name) to name.",
    "delete_global_expression_folder": "Delete a global expression folder (folder) and clear the folder_id of every expression it held.",
    "set_global_expression_folder": "Move a global expression into a folder, or out of every folder when folder is omitted.",
    "update_text": "Find-and-replace the content of a text element: locate by search_text in context and set new_text.",
    "update_text_element": "Update a text element by element_name: content, name, style, and size/layout properties.",
    "update_image": "Replace the source of an image element (element_name) with new_source (prefer_last picks the last match).",
    "update_image_element": "Update an image element by element_name: source, name, style, and size/layout properties.",
    "update_icon": "Replace the icon glyph of an icon element (element_name) with new_icon.",
    "update_icon_element": "Update an icon element by element_name: icon, color, style, and size/layout properties.",
    "build_source_query_json": "Build a Bubble 'Do a search for' query JSON (source type, constraints, sort) for use in data_source arguments. Read-only helper.",
    "build_data_source_json": "Build a data_source JSON (search/query/parent/state source) for visual elements and repeating groups. Read-only helper.",
}
