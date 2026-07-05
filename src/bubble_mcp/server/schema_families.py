"""Reusable schema builders for agent-facing MCP tools."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


JsonSchema = dict[str, Any]
ToolSchema = dict[str, Any]


_MISSING = object()


def _prop(
    schema_type: str | list[str],
    description: str,
    *,
    enum: list[str] | None = None,
    default: Any = _MISSING,
    examples: list[Any] | None = None,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
    fmt: str | None = None,
    items: JsonSchema | None = None,
    additional_properties: bool | JsonSchema | None = None,
    properties: dict[str, JsonSchema] | None = None,
    required: list[str] | None = None,
    any_of: list[JsonSchema] | None = None,
) -> JsonSchema:
    schema: JsonSchema = {"type": schema_type, "description": description}
    if enum is not None:
        schema["enum"] = enum
    if default is not _MISSING:
        schema["default"] = default
    if examples is not None:
        schema["examples"] = examples
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    if fmt is not None:
        schema["format"] = fmt
    if items is not None:
        schema["items"] = items
    if additional_properties is not None:
        schema["additionalProperties"] = additional_properties
    if properties is not None:
        schema["properties"] = properties
    if required is not None:
        schema["required"] = required
    if any_of is not None:
        schema["anyOf"] = any_of
    return schema


FIELD_LIBRARY: dict[str, JsonSchema] = {
    "profile": _prop(
        "string",
        "Local Bubble MCP profile to use. This resolves the app id, default branch/version, local context, and stored editor session.",
        examples=["smoke", "dev", "my-client-app"],
    ),
    "app_id": _prop(
        "string",
        "Bubble app id/appname. Omit when the selected profile already targets the correct Bubble app.",
        examples=["my-bubble-app"],
    ),
    "appname": _prop(
        "string",
        "Optional Bubble appname override. Defaults to app_id when omitted.",
        examples=["my-bubble-app"],
    ),
    "editor_url": _prop(
        "string",
        "Optional Bubble editor/page URL associated with the profile.",
        fmt="uri",
        examples=["https://bubble.io/page?id=my-bubble-app"],
    ),
    "app_version": _prop(
        "string",
        "Bubble branch/version id. Use test/version-test by default; pass a specific branch id when operating outside test.",
        default="test",
        examples=["test", "version-test", "feature-checkout"],
    ),
    "app_json_path": _prop(
        "string",
        "Optional local .bubble export path associated with the profile for context detection.",
        examples=["/Users/me/Downloads/app.bubble"],
    ),
    "consolelog_json_path": _prop(
        "string",
        "Optional local console.log(app) JSON/text capture path associated with the profile for context fallback.",
        examples=["/tmp/bubble-console-app.json"],
    ),
    "file": _prop(
        "string",
        "Local file path for the input artifact.",
        examples=["/Users/me/project/app.bubble", "/tmp/bubble-context.json"],
    ),
    "path": _prop(
        "string",
        "Local filesystem path.",
        examples=["/Users/me/project/extension-pack"],
    ),
    "extension_id": _prop(
        "string",
        "Installed Bubble MCP extension id.",
        examples=["local.simple-pack"],
    ),
    "output": _prop(
        "string",
        "Optional local output path for generated context or diagnostic artifacts.",
        examples=["/tmp/bubble-context.json"],
    ),
    "source": _prop(
        "string",
        "URL, local HTML file path, or raw HTML source to capture into a structured visual snapshot.",
        examples=["https://example.com/page.html", "/tmp/component.html", "<section id='hero'>...</section>"],
    ),
    "input": _prop(
        "string",
        "Local input artifact path.",
        examples=["/tmp/captured-editor-writes.json"],
    ),
    "query": _prop(
        "string",
        "Search query for pages, reusable elements, styles, data types, element names, ids, or visible labels.",
        examples=["checkout button", "mcp-01", "primary button style"],
    ),
    "exact": _prop(
        "boolean",
        "When true, match only exact node ids, labels, Bubble ids, or context refs. Use for verification and absence checks.",
        default=False,
    ),
    "include_metadata": _prop(
        "boolean",
        "When false, omit full node metadata for compact search results. Prefer false for simple existence or absence checks.",
        default=True,
    ),
    "limit": _prop(
        "integer",
        "Maximum number of search results or eval cases to return.",
        minimum=1,
    ),
    "filter": _prop(
        "string",
        "Comma-separated eval case ids to run.",
        examples=["create_text_hello,create_button_primary"],
    ),
    "failed_from": _prop(
        "string",
        "Path to a prior eval JSON report; only failed case ids are rerun.",
        examples=["reports/basic-compiled.json"],
    ),
    "reference": _prop(
        "string",
        "Local visual reference snapshot JSON path for structured visual/perceptual comparison.",
        examples=["tests/fixtures/visual-snapshots/reference.json"],
    ),
    "actual": _prop(
        "string",
        "Local actual visual snapshot JSON path to compare against the reference snapshot.",
        examples=["/tmp/bubble-actual-snapshot.json"],
    ),
    "reference_source": _prop(
        "string",
        "URL, local HTML file path, or raw HTML source to capture as the visual reference snapshot before audit.",
        examples=["https://example.com/page.html", "/tmp/reference.html", "<section id='hero'>...</section>"],
    ),
    "actual_source": _prop(
        "string",
        "URL, local HTML file path, or raw HTML source to capture as the visual actual snapshot before audit.",
        examples=["https://example.com/actual.html", "/tmp/actual.html"],
    ),
    "reference_selector": _prop(
        "string",
        "CSS selector override for reference capture. Omit to use selector.",
        examples=["#home-area", ".hero"],
    ),
    "actual_selector": _prop(
        "string",
        "CSS selector override for actual capture. Omit to use selector.",
        examples=["#gp_home_area", ".hero"],
    ),
    "actual_profile": _prop(
        "string",
        "Optional Bubble MCP profile used only for capturing the actual rendered Bubble output.",
        examples=["smoke", "cliente2"],
    ),
    "actual_app_id": _prop(
        "string",
        "Optional Bubble app id used only for capturing the actual rendered Bubble output.",
        examples=["my-bubble-app"],
    ),
    "actual_app_version": _prop(
        "string",
        "Optional Bubble branch/version used only for actual rendered Bubble capture.",
        default="test",
        examples=["test", "version-test"],
    ),
    "actual_page": _prop(
        "string",
        "Optional Bubble page path used only for actual rendered Bubble capture.",
        examples=["index", "mcp-01"],
    ),
    "actual_url": _prop(
        "string",
        "Explicit actual rendered URL override for visual audit capture.",
        fmt="uri",
        examples=["https://my-app.bubbleapps.io/version-test/mcp-01"],
    ),
    "actual_public_base_url": _prop(
        "string",
        "Optional public base URL override used only for actual Bubble capture.",
        fmt="uri",
        examples=["https://my-app.bubbleapps.io"],
    ),
    "reference_screenshot": _prop(
        "string",
        "Local reference screenshot path. The tool returns an LLM-ready multimodal comparison payload for screenshots.",
        examples=["/tmp/reference.png"],
    ),
    "reference_snapshot": _prop(
        "object",
        "Inline structured reference visual snapshot object. Use when the caller already captured a snapshot and does not need a local file path.",
        additional_properties=True,
    ),
    "actual_snapshot": _prop(
        "object",
        "Inline structured actual visual snapshot object. Use when the caller already captured a snapshot and does not need a local file path.",
        additional_properties=True,
    ),
    "actual_screenshot": _prop(
        "string",
        "Local actual screenshot path. The tool returns an LLM-ready multimodal comparison payload for screenshots.",
        examples=["/tmp/actual.png"],
    ),
    "screenshot_task": _prop(
        "string",
        "Optional instruction to include in the screenshot comparison prompt for the LLM client.",
        examples=["Focus on image size, gradient direction, typography, and max-width."],
    ),
    "tolerance_px": _prop(
        "number",
        "Absolute pixel tolerance for visual snapshot geometry comparisons.",
        default=4,
        minimum=0,
    ),
    "tolerance_ratio": _prop(
        "number",
        "Relative tolerance for visual snapshot geometry comparisons. A value of 0.08 allows an 8 percent drift.",
        default=0.08,
        minimum=0,
        maximum=1,
    ),
    "require_text": _prop(
        "boolean",
        "Require every text string in the reference snapshot to appear in the actual snapshot.",
        default=True,
    ),
    "require_images": _prop(
        "boolean",
        "Require image nodes and image dimensions from the reference snapshot to be present in the actual snapshot.",
        default=False,
    ),
    "offset": _prop(
        "integer",
        "Number of eval cases to skip after filtering.",
        default=0,
        minimum=0,
    ),
    "kind": _prop(
        "string",
        "Input artifact type. Use auto unless the caller already knows the source format.",
        enum=["auto", "bubble", "crawler"],
        default="auto",
    ),
    "force": _prop(
        "boolean",
        "Refresh or rebuild cached context even when a previous artifact exists.",
        default=False,
    ),
    "detect_context": _prop(
        "boolean",
        "Run project context detection during setup when the profile is available.",
        default=False,
    ),
    "force_context": _prop(
        "boolean",
        "Force context detection when detect_context is true.",
        default=False,
    ),
    "wait_seconds": _prop(
        "integer",
        "Maximum time to keep the local browser login flow open while polling for Bubble session cookies.",
        default=180,
        minimum=1,
    ),
    "headless": _prop(
        "boolean",
        "Run the browser in headless mode. Leave false for normal user-driven Bubble login.",
        default=False,
    ),
    "bubble_file": _prop(
        "string",
        "Optional .bubble export path. This is the preferred source when available because it contains the real project structure.",
        examples=["/Users/me/Downloads/app.bubble"],
    ),
    "consolelog_file": _prop(
        "string",
        "Optional console.log(app) JSON path used as fallback when a .bubble export is unavailable.",
        examples=["/tmp/bubble-console-app.json"],
    ),
    "skip_id_to_path": _prop(
        "boolean",
        "Skip id-to-path lookup generation in the compact context. Leave false for normal agent workflows.",
        default=False,
    ),
    "message": _prop(
        "string",
        "Natural language Bubble edit request to turn into a deterministic plan.",
        examples=["Create a text element saying Hello on the index page."],
    ),
    "task": _prop(
        "string",
        "Optional user request or task summary used to recommend the most relevant Bubble MCP tools.",
        examples=[
            "Convert #home-area from a URL into page mcp-01",
            "Create a page and add a text element",
            "Fetch changelog entries for the current branch",
        ],
    ),
    "recipe": _prop(
        "string",
        "Optional recipe id to force. Omit this so the MCP infers the recipe from the task.",
        enum=[
            "setup_or_refresh_context",
            "html_import",
            "visual_quality_gate",
            "visual_edit",
            "page_or_reusable",
            "workflow",
            "data_schema",
            "style_or_tokens",
            "branch_or_changelog",
            "quality_gate",
        ],
    ),
    "parent": _prop(
        "string",
        "Target parent element/container. Use root for page-level insertion or a known Bubble element id/name for nested insertion.",
        default="root",
        examples=["root", "main container", "bX123"],
    ),
    "context": _prop(
        "string",
        "Target Bubble page, reusable element, or container context by visible name or known id.",
        examples=["index", "mcp-01", "Reusable Header"],
    ),
    "dataset": _prop(
        "string",
        "Local eval dataset JSON path.",
        examples=["tests/fixtures/eval/basic.json"],
    ),
    "compile": _prop(
        "boolean",
        "Compile abstract plan steps into Bubble editor write payloads before returning or executing.",
        default=False,
    ),
    "plan": _prop(
        "object",
        "Structured Bubble MCP plan object containing ordered steps and tool arguments.",
        additional_properties=True,
    ),
    "context_file": _prop(
        "string",
        "Optional compact Bubble context JSON path used to resolve page, reusable, and element references.",
        examples=["/tmp/bubble-context.json"],
    ),
    "session": _prop(
        "object",
        "Captured Bubble editor session object. Secrets are stored locally and redacted from responses.",
        properties={
            "headers": _prop("object", "Captured editor request headers.", additional_properties=True),
            "cookies": _prop("string", "Captured editor cookies string."),
            "url": _prop("string", "Bubble editor/page URL associated with the session.", fmt="uri"),
            "appId": _prop("string", "Bubble app id captured with the session."),
            "appVersion": _prop("string", "Bubble branch/version captured with the session."),
            "method": _prop("string", "HTTP method from the captured editor request."),
        },
        additional_properties=True,
    ),
    "payload": _prop(
        "object",
        "Exact Bubble editor payload produced by a validated compiler/runtime step.",
        additional_properties=True,
    ),
    "execute": _prop(
        "boolean",
        "Set true only when the user asked to apply the change in Bubble. Leave false to preview the authenticated request.",
        default=False,
    ),
    "cleanup": _prop(
        "boolean",
        "For execute-write smoke only: delete the temporary smoke page after the suite finishes.",
        default=False,
    ),
    "run_id": _prop(
        "string",
        "Optional short identifier used to name temporary smoke pages/elements. Leave empty to auto-generate a unique id.",
        examples=["manual_20260703"],
    ),
    "verify_context": _prop(
        "boolean",
        "For execute-write smoke only: refresh Bubble context after writes and verify the temporary page/elements materialized with required defaults.",
        default=False,
    ),
    "include_family_preview": _prop(
        "boolean",
        "For readiness checks only: also run the broader family-preview smoke when a profile is available. This remains execute=false.",
        default=False,
    ),
    "max_age_hours": _prop(
        "integer",
        "Maximum accepted context age before the profile status reports the context as stale.",
        default=24,
        minimum=1,
    ),
    "verification_output": _prop(
        "string",
        "Optional local context JSON output path used by verify_context.",
        examples=["./runtime-smoke-context.json"],
    ),
    "url": _prop(
        "string",
        "Source URL for an HTML page/component import.",
        fmt="uri",
        examples=["https://example.com/page.html"],
    ),
    "public_base_url": _prop(
        "string",
        "Optional Bubble app public base URL override. Use for custom domains or non-standard app hosts.",
        fmt="uri",
        examples=["https://my-app.bubbleapps.io", "https://app.example.com"],
    ),
    "page": _prop(
        "string",
        "Bubble page path to capture from the public/preview app. Use index for the app root.",
        default="index",
        examples=["index", "mcp-01", "pricing"],
    ),
    "url_query": _prop(
        "object",
        "Optional URL query parameters to append when capturing a Bubble app page.",
        additional_properties={"type": "string"},
        examples=[{"debug": "true"}],
    ),
    "html_file": _prop(
        "string",
        "Local HTML file path or URL to convert into Bubble elements.",
        examples=["/tmp/component.html", "https://example.com/page.html"],
    ),
    "html": _prop(
        "string",
        "Raw HTML snippet to convert into Bubble elements.",
        examples=["<section id='hero'>...</section>"],
    ),
    "selector": _prop(
        "string",
        "CSS selector for the exact source component or section to convert. Prefer this for URL imports.",
        examples=["#home-area", ".pricing-card"],
    ),
    "rendered_html": _prop(
        "boolean",
        "Use browser-rendered DOM/computed styles instead of raw HTML when importing from a URL.",
        default=True,
    ),
    "viewport_width": _prop(
        "integer",
        "Browser viewport width in pixels for rendered visual capture.",
        default=1365,
        minimum=1,
    ),
    "viewport_height": _prop(
        "integer",
        "Browser viewport height in pixels for rendered visual capture.",
        default=768,
        minimum=1,
    ),
    "wait_ms": _prop(
        "integer",
        "Optional milliseconds to wait after page load before capturing the visual snapshot.",
        default=0,
        minimum=0,
    ),
    "selector_timeout_ms": _prop(
        "integer",
        "Milliseconds to wait for the requested selector before capturing rendered output.",
        default=5000,
        minimum=0,
    ),
    "max_nodes": _prop(
        "integer",
        "Maximum DOM nodes to include in the captured visual snapshot.",
        default=250,
        minimum=1,
    ),
    "allow_raw_fallback": _prop(
        "boolean",
        "When rendered capture is unavailable, fall back to raw HTML extraction instead of failing.",
        default=True,
    ),
    "translate_to_existing_styles": _prop(
        "boolean",
        "Try matching imported visual properties to existing Bubble styles in the target app.",
        default=False,
    ),
    "style_match_threshold": _prop(
        "number",
        "Minimum similarity score for matching imported visuals to existing Bubble styles.",
        default=0.82,
        minimum=0,
        maximum=1,
    ),
    "placement": _prop(
        "string",
        "Optional placement instruction for where the generated element tree should be inserted.",
        examples=["append", "prepend", "replace children"],
    ),
    "strict_validate": _prop(
        "boolean",
        "Fail the import when semantic validation finds unsupported or unsafe output.",
        default=False,
    ),
    "validation_out_dir": _prop(
        "string",
        "Optional directory for HTML import validation/debug artifacts.",
        examples=["/tmp/bubble-html-validation"],
    ),
    "refresh_context": _prop(
        "boolean",
        "Refresh Bubble context before resolving targets and compiling the import mutation.",
        default=False,
    ),
    "start_index": _prop(
        "integer",
        "Zero-based pagination offset for Bubble changelog entries.",
        default=0,
        minimum=0,
    ),
    "num_fetch": _prop(
        "integer",
        "Number of changelog entries to fetch. The implementation caps this at 200.",
        default=50,
        minimum=1,
        maximum=200,
    ),
    "filters": _prop(
        "object",
        "Raw Bubble changelog filters object. Use only when advanced filters already match Bubble's editor payload shape.",
        additional_properties=True,
    ),
    "start_timestamp": _prop(
        "integer",
        "Start timestamp in milliseconds for changelog filtering.",
        examples=[1783000000000],
    ),
    "end_timestamp": _prop(
        "integer",
        "End timestamp in milliseconds for changelog filtering.",
        examples=[1783090000000],
    ),
    "change_type": _prop(
        "string",
        "Bubble changelog category/type filter. Common values include Element, Workflow, Data, Style, Page, AppText, and Settings.",
        examples=["Element", "Workflow", "Data", "Style", "Page"],
    ),
    "root": _prop(
        ["string", "null"],
        "Bubble root id for deeper changelog filtering, usually a page or reusable element id.",
    ),
    "change_identifier": _prop(
        ["string", "null"],
        "Specific Bubble change identifier for an element, workflow, data type, style, or resource.",
    ),
    "change_path": _prop(
        ["string", "array", "null"],
        "Bubble changelog path filter. Pass the exact string or string array observed in Bubble change paths.",
        items={"type": "string"},
    ),
    "user_id": _prop(
        ["string", "array"],
        "Bubble collaborator user id or list of ids used to filter changelog entries.",
        items={"type": "string"},
    ),
    "name": _prop(
        "string",
        "Display name or Bubble entity name to create.",
        examples=["feature-checkout", "mcp-02"],
    ),
    "from_app_version": _prop(
        "string",
        "Source Bubble branch/version to branch from. Pass an existing branch id to create a sub-branch.",
        default="test",
        examples=["test", "feature-parent"],
    ),
    "description": _prop(
        "string",
        "Optional Bubble branch description.",
        default="",
    ),
    "version_control_api_version": _prop(
        "integer",
        "Bubble version-control API version for branch operations. Keep the default unless Bubble changes the editor contract.",
        default=7,
        minimum=1,
    ),
    "soft_delete": _prop(
        "boolean",
        "Use Bubble's soft-delete behavior for branch deletion. Leave true unless explicitly asked for hard delete behavior.",
        default=True,
    ),
    "confirm": _prop(
        "boolean",
        "Required true for destructive operations when execute=true.",
        default=False,
    ),
    "suite": _prop(
        "string",
        "Runtime smoke suite to run. coverage checks catalog execution coverage and agent-facing catalog quality; agent-routing validates natural-language tool routing without writes; visual-repair validates visual audit repair planning without writes; safe-read runs read-only profile calls; preview-write compiles representative mutations with execute=false; family-preview exercises representative visual/container/input/schema/workflow/style/html/branch/changelog paths without writes; execute-write creates temporary Bubble objects and requires execute=true.",
        enum=["coverage", "agent-routing", "visual-repair", "safe-read", "preview-write", "family-preview", "execute-write"],
        default="coverage",
    ),
    "include_details": _prop(
        "boolean",
        "Include redacted raw tool results in smoke output. Leave false for compact agent-friendly summaries.",
        default=False,
    ),
    "include_profile_status": _prop(
        "boolean",
        "Include compact profile/session/context readiness in the task runbook. Leave false when the profile was already checked.",
        default=False,
    ),
    "search_limit": _prop(
        "integer",
        "Maximum number of relevant tool matches to include in a one-call task runbook.",
        minimum=1,
        default=6,
    ),
    "stop_on_failure": _prop(
        "boolean",
        "Stop the smoke suite after the first failed case.",
        default=False,
    ),
    "html_url": _prop(
        "string",
        "Optional HTML URL used by the preview-write smoke suite to include create_from_html.",
        fmt="uri",
        examples=["https://example.com/component.html"],
    ),
}


def field(name: str) -> JsonSchema:
    """Return a defensive copy of a shared field schema."""

    return deepcopy(FIELD_LIBRARY[name])


def object_schema(
    properties: dict[str, JsonSchema] | list[str],
    *,
    required: list[str] | None = None,
    any_of: list[JsonSchema] | None = None,
    additional_properties: bool = False,
) -> JsonSchema:
    if isinstance(properties, list):
        resolved_properties = {name: field(name) for name in properties}
    else:
        resolved_properties = properties
    schema: JsonSchema = {
        "type": "object",
        "properties": resolved_properties,
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    if any_of:
        schema["anyOf"] = any_of
    return schema


def tool_schema(
    name: str,
    description: str,
    fields: list[str],
    *,
    required: list[str] | None = None,
    any_of: list[JsonSchema] | None = None,
    additional_properties: bool = False,
) -> ToolSchema:
    return {
        "name": name,
        "description": description,
        "inputSchema": object_schema(
            fields,
            required=required,
            any_of=any_of,
            additional_properties=additional_properties,
        ),
    }


def _empty_tool(name: str, description: str) -> ToolSchema:
    return {
        "name": name,
        "description": description,
        "inputSchema": object_schema({}),
    }


def profile_session_context_tools() -> list[ToolSchema]:
    return [
        tool_schema(
            "bubble_project_bootstrap",
            "One-call MCP setup entrypoint for a Bubble project profile. It can create or update the local profile, report readiness, and optionally run context detection so agents do not need to discover setup command sequences.",
            [
                "profile",
                "app_id",
                "appname",
                "editor_url",
                "app_version",
                "app_json_path",
                "consolelog_json_path",
                "detect_context",
                "force_context",
                "max_age_hours",
            ],
            required=["profile"],
        ),
        tool_schema(
            "bubble_profile_add",
            "Add or update a local Bubble MCP profile. This writes only local MCP settings; it does not contact or mutate Bubble. After adding a profile, run session login/import and context detect before app mutations.",
            [
                "name",
                "app_id",
                "appname",
                "editor_url",
                "app_version",
                "app_json_path",
                "consolelog_json_path",
            ],
            required=["name", "app_id"],
        ),
        _empty_tool("bubble_profile_list", "List local Bubble MCP profiles. This is read-only."),
        tool_schema(
            "bubble_profile_status",
            "Return a read-only readiness snapshot for one local Bubble MCP profile: mapping, session metadata, context freshness/loadability, and next actions.",
            ["profile", "max_age_hours"],
        ),
        _empty_tool(
            "bubble_health_check",
            "Return local Bubble MCP server health and capability metadata.",
        ),
        tool_schema(
            "bubble_session_inspect",
            "Inspect redacted stored Bubble session data and computed editor write headers for one profile. Use this to debug whether a captured/imported session contains the headers needed for authenticated writes. Read-only.",
            ["profile", "app_id"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_session_login",
            "Open a local Playwright browser, let the user log in to Bubble, capture editor cookies and request headers, and save the redacted session for a profile. This is interactive and writes only local MCP session storage.",
            ["profile", "app_id", "editor_url", "app_version", "wait_seconds", "headless"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_readiness_check",
            "Run the recommended Bubble MCP readiness sequence in one call: server health, compact catalog coverage/quality gate, agent-routing smoke, profile-status readiness when a profile is provided, and optional profile safe-read/family-preview checks. Read-only.",
            [
                "profile",
                "context",
                "parent",
                "app_id",
                "app_version",
                "max_age_hours",
                "include_family_preview",
                "include_details",
                "stop_on_failure",
            ],
        ),
        tool_schema(
            "bubble_agent_guide",
            "Return compact agent-facing routing guidance for the Bubble MCP catalog. Call this when a client needs to choose the correct tool family without inspecting CLI help or repository code.",
            ["task"],
        ),
        tool_schema(
            "bubble_tool_search",
            "Search the exposed Bubble MCP tool catalog and return compact matching tool metadata. Use this instead of reading the full tools/list response when the task only needs a small set of relevant tools.",
            ["query", "limit"],
            required=["query"],
        ),
        tool_schema(
            "bubble_task_recipe",
            "Return a compact operational recipe for a Bubble task: preflight checks, ordered MCP tool calls, arguments to fill, safeguards, and verification guidance. Use this after bubble_agent_guide or bubble_tool_search when the agent needs the execution sequence, not just candidate tools.",
            ["task", "recipe", "profile", "context", "parent", "execute"],
            required=["task"],
        ),
        tool_schema(
            "bubble_task_runbook",
            "Return a one-call compact runbook for a Bubble task: route intents, ordered recipe steps, safeguards, compact relevant tool matches, and optional profile readiness. Use this first when an agent needs to act without inspecting CLI help, repository code, or the full tools/list response.",
            ["task", "profile", "context", "parent", "execute", "search_limit", "include_profile_status"],
            required=["task"],
        ),
        tool_schema(
            "bubble_tool_coverage",
            "Report runtime coverage for every exposed Bubble MCP tool, including native, Aria-runtime, alias, custom, compiler fallback, and uncovered categories. Read-only.",
            ["include_details"],
        ),
        _empty_tool(
            "bubble_catalog_quality",
            "Audit the exposed MCP catalog for agent usability: unique tool/resource/prompt ids, clear descriptions, documented input fields, complete annotations, resource metadata, prompt arguments, and runtime coverage. Read-only.",
        ),
        tool_schema(
            "bubble_runtime_smoke",
            "Run an operational smoke suite for the MCP runtime. coverage is local-only and validates catalog execution coverage plus agent-facing catalog quality; agent-routing validates natural-language tool selection without writes; visual-repair validates visual audit repair planning without writes; safe-read performs read-only calls; preview-write compiles representative Bubble mutations with execute=false; and execute-write creates temporary Bubble objects only when execute=true.",
            [
                "suite",
                "profile",
                "context",
                "parent",
                "app_id",
                "app_version",
                "limit",
                "html_url",
                "selector",
                "include_details",
                "stop_on_failure",
                "execute",
                "cleanup",
                "run_id",
                "verify_context",
                "verification_output",
            ],
        ),
        tool_schema(
            "bubble_context_summary",
            "Summarize a compact Bubble context JSON file.",
            ["file"],
            required=["file"],
        ),
        tool_schema(
            "bubble_context_find",
            "Search a compact Bubble context by profile or local JSON file.",
            ["profile", "file", "query", "limit", "exact", "include_metadata"],
            required=["query"],
        ),
        tool_schema(
            "bubble_context_import",
            "Import a Bubble .bubble/consolelog JSON or crawler-index JSON into compact context.",
            ["file", "kind", "output"],
            required=["file"],
        ),
        tool_schema(
            "bubble_context_detect",
            "Detect and materialize Bubble project context using .bubble export, consolelog fallback, and editor crawler/cache.",
            [
                "profile",
                "app_id",
                "app_version",
                "output",
                "bubble_file",
                "consolelog_file",
                "force",
                "skip_id_to_path",
            ],
            required=["profile"],
        ),
        tool_schema(
            "bubble_session_list",
            "List locally imported Bubble editor session metadata.",
            [],
        ),
        tool_schema(
            "bubble_session_import",
            "Import a local Bubble editor session object with headers/cookies for a profile.",
            ["profile", "app_id", "session"],
            required=["profile", "session"],
        ),
    ]


def planning_execution_tools() -> list[ToolSchema]:
    return [
        tool_schema(
            "bubble_plan",
            "Create and validate a deterministic Bubble plan.",
            ["message", "context", "parent"],
            required=["message"],
        ),
        tool_schema(
            "bubble_plan_dry_run",
            "Compatibility alias for bubble_plan.",
            ["message", "context", "parent"],
            required=["message"],
        ),
        tool_schema(
            "bubble_eval_run",
            "Run a deterministic planning eval dataset with optional filters for cheap focused reruns.",
            ["dataset", "compile", "app_id", "filter", "failed_from", "offset", "limit"],
            required=["dataset"],
        ),
        tool_schema(
            "bubble_eval_export_expert",
            "Export redacted captured Bubble editor write artifacts into eval cases with family classification and tool hints. This is read-only and does not contact Bubble.",
            ["input", "output", "limit"],
            required=["input", "output"],
        ),
        tool_schema(
            "bubble_visual_compare",
            "Compare two structured visual snapshots and report layout, text, image, typography, max-width, and gradient drift. Use this as the lightweight perceptual harness before screenshot automation is available.",
            ["reference", "actual", "tolerance_px", "tolerance_ratio", "require_text", "require_images"],
            required=["reference", "actual"],
        ),
        tool_schema(
            "bubble_visual_audit",
            "Audit visual drift, return actionable issues, generate a Bubble repair plan, and optionally execute supported repairs when execute=true. Accepts snapshot files, source URLs/HTML captures, rendered Bubble actual captures, and optional screenshots for LLM-based comparison review.",
            [
                "reference",
                "actual",
                "reference_source",
                "actual_source",
                "reference_snapshot",
                "actual_snapshot",
                "actual_profile",
                "actual_app_id",
                "actual_app_version",
                "actual_page",
                "actual_url",
                "actual_public_base_url",
                "selector",
                "reference_selector",
                "actual_selector",
                "profile",
                "context",
                "parent",
                "app_id",
                "app_version",
                "execute",
                "tolerance_px",
                "tolerance_ratio",
                "require_text",
                "require_images",
                "reference_screenshot",
                "actual_screenshot",
                "screenshot_task",
                "rendered_html",
                "viewport_width",
                "viewport_height",
                "wait_ms",
                "selector_timeout_ms",
                "max_nodes",
                "allow_raw_fallback",
            ],
            any_of=[
                {"required": ["reference", "actual"]},
                {"required": ["reference_snapshot", "actual_snapshot"]},
                {"required": ["reference_source", "actual_source"]},
                {"required": ["reference_source", "actual_profile"]},
                {"required": ["reference_screenshot", "actual_screenshot"]},
            ],
        ),
        tool_schema(
            "bubble_visual_capture",
            "Capture a structured visual snapshot from a URL, local HTML file, or raw HTML. Use this before bubble_visual_compare when the agent needs a reference/actual snapshot from source material instead of hand-authored JSON.",
            [
                "source",
                "selector",
                "output",
                "rendered_html",
                "viewport_width",
                "viewport_height",
                "wait_ms",
                "selector_timeout_ms",
                "max_nodes",
                "allow_raw_fallback",
            ],
            required=["source"],
        ),
        tool_schema(
            "bubble_visual_capture_actual",
            "Capture the actual rendered Bubble app/preview output for a configured profile, app, page, or explicit Bubble URL. Use this after a write/import to compare the Bubble result against a source/reference snapshot.",
            [
                "profile",
                "app_id",
                "app_version",
                "page",
                "context",
                "selector",
                "public_base_url",
                "url",
                "url_query",
                "output",
                "viewport_width",
                "viewport_height",
                "wait_ms",
                "selector_timeout_ms",
                "max_nodes",
            ],
        ),
        tool_schema(
            "bubble_compile_plan",
            "Compile supported abstract plan steps into Bubble /appeditor/write payloads.",
            ["plan", "app_id", "app_version", "context_file"],
            required=["plan", "app_id"],
        ),
        tool_schema(
            "bubble_editor_write",
            "Send a Bubble /appeditor/write payload using a stored local session. Set execute=true to mutate Bubble; otherwise it previews the request.",
            ["profile", "payload", "execute"],
            required=["profile", "payload"],
        ),
        tool_schema(
            "bubble_execute_plan",
            "Execute a Bubble plan whose steps include args.write_payload. Set execute=true to mutate Bubble; otherwise it previews the plan.",
            ["profile", "plan", "execute", "compile", "app_id", "app_version", "context_file"],
            required=["profile", "plan"],
        ),
    ]


def html_import_tools() -> list[ToolSchema]:
    return [
        tool_schema(
            "create_from_html",
            "Use this whenever a user asks to convert, import, copy, or add an HTML component/section from a URL, selector, or HTML snippet into Bubble. This is Aria's advanced HTML-to-Bubble importer: it hydrates the page with a browser, extracts rendered DOM/computed styles, maps the result to Bubble elements, and can execute through the stored profile session. Prefer this over any conservative/raw HTML converter for URL + selector requests.",
            [
                "profile",
                "app_id",
                "app_version",
                "context",
                "parent",
                "url",
                "html_file",
                "file",
                "html",
                "selector",
                "execute",
                "rendered_html",
                "translate_to_existing_styles",
                "style_match_threshold",
                "placement",
                "strict_validate",
                "validation_out_dir",
                "refresh_context",
            ],
            required=["profile", "context", "parent"],
            any_of=[
                {"required": ["url"]},
                {"required": ["html_file"]},
                {"required": ["file"]},
                {"required": ["html"]},
            ],
        )
    ]


def branch_changelog_tools() -> list[ToolSchema]:
    return [
        tool_schema(
            "bubble_branch_list",
            "List Bubble editor branches/versions for a profile by calling the authenticated editor get_versions endpoint.",
            ["profile", "app_id"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_branch_contributors",
            "List Bubble collaborators who contributed to the selected branch/version using the stored editor session.",
            ["profile", "app_id", "app_version"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_changelog_fetch",
            "Fetch recent Bubble editor changelog entries with optional filters for date, user, category, root, identifier, and change path.",
            [
                "profile",
                "app_id",
                "app_version",
                "start_index",
                "num_fetch",
                "filters",
                "start_timestamp",
                "end_timestamp",
                "change_type",
                "root",
                "change_identifier",
                "change_path",
                "user_id",
            ],
            required=["profile"],
        ),
        tool_schema(
            "bubble_branch_create",
            "Create a new Bubble development branch or sub-branch from an existing app version. Pass from_app_version to choose the parent branch/version. Without execute=true it only previews the authenticated request.",
            [
                "profile",
                "app_id",
                "name",
                "from_app_version",
                "description",
                "execute",
                "version_control_api_version",
            ],
            required=["profile", "name"],
        ),
        tool_schema(
            "bubble_branch_delete",
            "Soft-delete a Bubble branch/version. Requires execute=true and confirm=true to mutate Bubble; otherwise it previews the request.",
            ["profile", "app_id", "app_version", "soft_delete", "execute", "confirm"],
            required=["profile", "app_version"],
        ),
    ]


def extension_kernel_tools() -> list[ToolSchema]:
    return [
        _empty_tool(
            "bubble_extension_list",
            "List local Bubble MCP extension packs and their enabled state.",
        ),
        tool_schema(
            "bubble_extension_validate",
            "Validate a local Bubble MCP extension pack directory without importing it.",
            ["path"],
            required=["path"],
        ),
        tool_schema(
            "bubble_extension_import",
            "Import a local Bubble MCP extension pack directory into local extension storage. The import is idempotent for the same extension id.",
            ["path"],
            required=["path"],
        ),
        tool_schema(
            "bubble_extension_enable",
            "Enable an installed Bubble MCP extension pack by extension id. Re-enabling an enabled extension is idempotent.",
            ["extension_id"],
            required=["extension_id"],
        ),
        tool_schema(
            "bubble_extension_disable",
            "Disable an installed Bubble MCP extension pack by extension id. Re-disabling a disabled extension is idempotent.",
            ["extension_id"],
            required=["extension_id"],
        ),
        {
            "name": "bubble_learning_record",
            "description": (
                "Append one local consultative learning record. Records are stored as append-only JSONL and are not "
                "used by planner behavior in this release."
            ),
            "inputSchema": object_schema(
                {
                    "scope": _prop(
                        "string",
                        "Learning scope for this record.",
                        enum=["global", "profile", "project", "extension"],
                    ),
                    "key": _prop(
                        "string",
                        "Stable learning key such as naming.page_language or workflow.preview_required.",
                        examples=["naming.page_language", "workflow.preview_required"],
                    ),
                    "value": _prop(
                        "object",
                        "JSON object containing the consultative learning value.",
                        additional_properties=True,
                        default={},
                        examples=[{"language": "pt-BR"}],
                    ),
                    "source": _prop(
                        "string",
                        "Provenance for the learning record.",
                        examples=["user_declared", "operator_reviewed"],
                    ),
                    "confidence": _prop(
                        "string",
                        "Confidence label for the learning record.",
                        examples=["confirmed", "tentative"],
                    ),
                    "profile": field("profile"),
                    "project": _prop(
                        "string",
                        "Optional Bubble app/project identifier used when scope is project.",
                        examples=["client-app"],
                    ),
                    "extension_id": field("extension_id"),
                },
                required=["scope", "key", "source", "confidence"],
            ),
        },
        {
            "name": "bubble_learning_list",
            "description": (
                "List local consultative learning records with optional scope/profile/project/extension filters. "
                "Read-only and does not affect planner behavior."
            ),
            "inputSchema": object_schema(
                {
                    "scope": _prop(
                        "string",
                        "Optional learning scope filter.",
                        enum=["global", "profile", "project", "extension"],
                    ),
                    "profile": field("profile"),
                    "project": _prop(
                        "string",
                        "Optional Bubble app/project identifier filter.",
                        examples=["client-app"],
                    ),
                    "extension_id": field("extension_id"),
                }
            ),
        },
        {
            "name": "bubble_knowledge_refresh_source",
            "description": (
                "Import normalized Bubble manual records from a local JSONL file into the local knowledge cache. "
                "This never calls remote documentation services and only mutates local MCP cache storage."
            ),
            "inputSchema": object_schema(
                {
                    "source": _prop(
                        "string",
                        "Safe local knowledge source id. Use bubble_manual_gitbook for cached Bubble manual records.",
                        examples=["bubble_manual_gitbook"],
                    ),
                    "file": _prop(
                        "string",
                        "Local JSONL file containing normalized knowledge records to append to the cache.",
                        examples=["tests/fixtures/knowledge/bubble-manual-records.jsonl"],
                    ),
                },
                required=["source", "file"],
            ),
        },
        {
            "name": "bubble_knowledge_search",
            "description": (
                "Search the local normalized knowledge cache. Results are source-attributed and cache-only; remote "
                "GitBook or manual lookups are disabled in this release."
            ),
            "inputSchema": object_schema(
                {
                    "query": _prop(
                        "string",
                        "Documentation topic to search in the local cache.",
                        examples=["API Connector authentication", "privacy rules migration"],
                    ),
                    "limit": field("limit"),
                },
                required=["query"],
            ),
        },
        {
            "name": "bubble_knowledge_fetch",
            "description": "Fetch one local knowledge record by id with full provenance and license metadata.",
            "inputSchema": object_schema(
                {
                    "record_id": _prop(
                        "string",
                        "Knowledge record id returned by bubble_knowledge_search.",
                        examples=["bubble-manual:data-types:privacy"],
                    ),
                },
                required=["record_id"],
            ),
        },
        {
            "name": "bubble_manual_guidance",
            "description": (
                "Return source-attributed Bubble manual guidance from the local cache only. Use for consultative "
                "manual context; it does not call remote docs or automatically influence execution."
            ),
            "inputSchema": object_schema(
                {
                    "query": _prop(
                        "string",
                        "Bubble manual topic or question to answer from cached records.",
                        examples=["How should API Connector authentication be handled?"],
                    ),
                    "limit": field("limit"),
                },
                required=["query"],
            ),
        },
        {
            "name": "bubble_manual_context_for_tool_authoring",
            "description": (
                "Return local cached Bubble manual context shaped for declarative tool authoring decisions. "
                "Consultative only and cache-only."
            ),
            "inputSchema": object_schema(
                {
                    "query": _prop(
                        "string",
                        "Tool-authoring topic to search in cached Bubble manual records.",
                        examples=["API Connector authentication reusable calls"],
                    ),
                    "limit": field("limit"),
                },
                required=["query"],
            ),
        },
        {
            "name": "bubble_manual_context_for_validation",
            "description": (
                "Return local cached Bubble manual context shaped for validation and migration risk review. "
                "Consultative only and cache-only."
            ),
            "inputSchema": object_schema(
                {
                    "query": _prop(
                        "string",
                        "Validation topic to search in cached Bubble manual records.",
                        examples=["privacy rules migration risk"],
                    ),
                    "limit": field("limit"),
                },
                required=["query"],
            ),
        },
    ]


def native_tool_schemas() -> list[ToolSchema]:
    """Return native tool schemas grouped by capability family."""

    return [
        *profile_session_context_tools(),
        *planning_execution_tools(),
        *html_import_tools(),
        *branch_changelog_tools(),
        *extension_kernel_tools(),
    ]
