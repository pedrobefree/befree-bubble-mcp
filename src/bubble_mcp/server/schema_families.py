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
    "text": _prop(
        "string",
        "Framework-authored natural-language text to convert into a compact Bubble MCP program.",
        examples=["Objective: Create checkout CTA\n- Add button labeled Start inside root"],
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
    "tool": _prop(
        "string",
        "Exact MCP tool name to inspect, preview, or call through a stable dispatcher.",
        examples=["local.simple-pack.create_plugin_widget", "bubble_extension_list"],
    ),
    "arguments": _prop(
        "object",
        "Arguments to pass to the target MCP tool. For extension tools, keep execute=false for preview.",
        additional_properties=True,
        examples=[{"profile": "cliente2", "context": "index", "parent": "root", "label": "Test", "execute": False}],
    ),
    "session_id": _prop(
        "string",
        "Local tool-authoring session id.",
        examples=["toolwiz_20260704_api_connector_1a2b3c4d"],
    ),
    "skill_id": _prop(
        "string",
        "Local Bubble MCP skill id.",
        examples=["security-review", "api-connector-security-review"],
    ),
    "objective": _prop(
        "string",
        "Natural-language objective for a new MCP skill.",
        examples=["Review API Connector security and produce a risk summary."],
    ),
    "framework": _prop(
        "string",
        "Framework adapter id.",
        enum=["bmad", "superpowers", "sdd"],
        examples=["bmad", "superpowers", "sdd"],
    ),
    "scope": _prop(
        "string",
        "Optional planning or implementation scope for generated framework artifacts.",
        examples=["checkout page", "API Connector security", "database migration"],
    ),
    "context_summary": _prop(
        "object",
        "Optional compact Bubble context signals to include in generated framework artifacts.",
        additional_properties=True,
        examples=[{"pages": 5, "workflows": 12, "data_types": 7}],
    ),
    "artifact_dir": _prop(
        "string",
        "Local framework artifact directory returned by bubble_framework_generate_artifacts.",
        examples=["/Users/me/.config/bubble-mcp/frameworks/bmad/cliente2/20260707-120000-checkout"],
    ),
    "workspace_dir": _prop(
        "string",
        "Local workspace directory where framework artifacts should be synchronized.",
        examples=["/Users/me/project"],
    ),
    "evidence": _prop(
        "object",
        "Structured implementation or validation evidence to append to framework artifacts. Sensitive values are redacted.",
        additional_properties=True,
        examples=[{"summary": "Preview passed", "run_id": "skillrun_20260707_123456"}],
    ),
    "families": _prop(
        "array",
        "Optional tool-family filters for language registry queries.",
        items={"type": "string"},
        examples=[["visual_editor", "workflow"]],
    ),
    "sources": _prop(
        "array",
        "Optional source filters such as native or extension.",
        items={"type": "string"},
        examples=[["native"], ["extension"]],
    ),
    "risks": _prop(
        "array",
        "Optional risk filters such as read_only, mutating, or destructive.",
        items={"type": "string"},
        examples=[["read_only", "mutating"]],
    ),
    "tools": _prop(
        "array",
        "Exact Bubble MCP tool names for lazy language detail lookup.",
        items={"type": "string"},
        examples=[["create_button", "bubble_context_find"]],
    ),
    "detail": _prop(
        "string",
        "Language registry detail level.",
        enum=["index", "compact", "full"],
        default="compact",
    ),
    "since": _prop(
        "string",
        "Previous language registry version for diff queries.",
        examples=["sha256:old"],
    ),
    "cached_registry_version": _prop(
        "string",
        "Client-held language registry version for cache-hit metadata on language queries.",
        examples=["sha256:abcd1234"],
    ),
    "program": _prop(
        "object",
        "Framework-authored compact Bubble MCP program to compile into preview-safe MCP calls.",
        additional_properties=True,
    ),
    "mode": _prop(
        "string",
        "Framework program run mode. Preview compiles without writes; execute requires explicit approval.",
        enum=["preview", "execute"],
        default="preview",
    ),
    "approved": _prop(
        "boolean",
        "Set true only after reviewing the compiled framework program and approving execute mode.",
        default=False,
    ),
    "risk": _prop(
        "string",
        "Skill risk level.",
        enum=["read_only", "mutating", "destructive"],
        default="read_only",
        examples=["read_only", "mutating"],
    ),
    "answer": _prop(
        "string",
        "Natural-language answer or instruction collected during skill authoring.",
        examples=["The skill should return a plan, risk summary, and execution log."],
    ),
    "field": _prop(
        "string",
        "Optional authoring field label for a collected answer.",
        examples=["outputs", "scope", "tools"],
    ),
    "inputs": _prop(
        "object",
        "Inputs passed to a skill run.",
        additional_properties=True,
        examples=[{"profile": "cliente2", "scope": "privacy"}],
    ),
    "approve_execution": _prop(
        "boolean",
        "Set true only after reviewing a skill preview run and approving its planned execution.",
        default=False,
    ),
    "tool_session_id": _prop(
        "string",
        "Optional local tool-authoring session id that receives captured extension write events.",
        examples=["toolwiz_20260704_api_connector_1a2b3c4d"],
    ),
    "generate_pack": _prop(
        "boolean",
        "When true, finalize the tool-authoring session and immediately generate the candidate extension pack.",
        default=False,
    ),
    "tool_name": _prop(
        "string",
        "Optional exact MCP tool name to generate or expose.",
        examples=["local.api-connector.create_api_call"],
    ),
    "output_dir": _prop(
        "string",
        "Optional local directory for generated artifacts. Omit to use the Bubble MCP config directory.",
        examples=["/Users/me/.config/bubble-mcp/tool-authoring/generated-packs"],
    ),
    "host": _prop(
        "string",
        "Local bind host for an auxiliary HTTP service.",
        default="127.0.0.1",
        examples=["127.0.0.1"],
    ),
    "port": _prop(
        "integer",
        "Local TCP port for an auxiliary HTTP service.",
        default=3847,
        minimum=0,
        maximum=65534,
        examples=[3847],
    ),
    "capture_key": _prop(
        "string",
        "Optional local key required from the Chrome extension in X-Bubble-MCP-Capture-Key.",
        examples=["local-dev-key"],
    ),
    "target": _prop(
        "string",
        "Bubble authoring target or capability family being captured.",
        examples=["api_connector", "workflow_action", "data_schema"],
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
    "intent": _prop(
        "string",
        "Natural-language description of the candidate tool-authoring session intent.",
        examples=["Create an API Connector call", "Create a reusable workflow action"],
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
    "calculate_derived": _prop(
        "boolean",
        "After a successful Bubble editor write, call /appeditor/calculate_derived to refresh derived schema indexes. Use for manual schema writes such as deleting data fields.",
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
    "style_name_prefix": _prop(
        "string",
        "Prefix for style names generated from HTML selectors.",
        default="HTML",
        examples=["HTML", "Marketing", "Imported"],
    ),
    "style_name": _prop(
        "string",
        "Exact Bubble style name to create or update. Identity is style_name plus element_type.",
        examples=["Primary Button", "Card Surface"],
    ),
    "style_prefix": _prop(
        "string",
        "Compatibility alias for style_name_prefix when generating Bubble style names from HTML.",
        examples=["HTML", "Design System"],
    ),
    "element_type": _prop(
        "string",
        "Bubble element type the generated style targets.",
        examples=["Button", "Text", "Group"],
    ),
    "include_states": _prop(
        "boolean",
        "Include supported pseudo-state rules such as hover, focus, disabled, and active/pressed.",
        default=True,
    ),
    "states": _prop(
        "array",
        "Optional subset of pseudo-states to import. Base styles are always included.",
        items={"type": "string", "enum": ["hover", "focus", "disabled", "pressed"]},
        examples=[["hover", "focus"]],
    ),
    "extra_css": _prop(
        "array",
        "Additional CSS strings to merge with style tags found in the HTML source.",
        items={"type": "string"},
        examples=[[".btn:hover { background-color: #004eeb; }"]],
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
    "start": _prop(
        ["string", "integer", "number"],
        "Start date/time for Bubble log, workload, or usage queries. Accepts ISO datetime or epoch milliseconds.",
        examples=["2026-04-11T00:00:00.000Z", 1783000000000],
    ),
    "end": _prop(
        ["string", "integer", "number"],
        "End date/time for Bubble log, workload, or usage queries. Accepts ISO datetime or epoch milliseconds.",
        examples=["2026-05-10T23:59:59.999Z", 1783086400000],
    ),
    "granularity": _prop(
        "string",
        "Bucket size for Bubble workload usage queries.",
        enum=["minute", "hour", "day"],
        default="day",
        examples=["day", "hour"],
    ),
    "platform": _prop(
        "string",
        "Bubble app platform filter for editor metrics endpoints.",
        enum=["web", "mobile", "web_and_mobile"],
        default="web_and_mobile",
    ),
    "tag1": _prop(
        ["string", "null"],
        "Optional first Bubble workload tag filter such as workflow, elasticsearch, or appeditor.",
        examples=["workflow", "elasticsearch", "appeditor"],
    ),
    "tag2": _prop(
        ["string", "null"],
        "Optional second Bubble workload tag filter for a narrower breakdown.",
        examples=["search"],
    ),
    "messages": _prop(
        "array",
        "Optional Jetstream log message tags to request. Omit to use the default workflow, database, HTTP, scheduled task, plugin, and error tags.",
        items={"type": "string"},
        examples=[["running event", "running action", "server_db.modify"]],
    ),
    "ascending": _prop(
        "boolean",
        "Return Bubble logs in ascending time order.",
        default=True,
    ),
    "is_state_ar": _prop(
        "boolean",
        "Bubble Jetstream state flag observed from the editor log calls. Leave true unless the editor contract changes.",
        default=True,
    ),
    "include_raw": _prop(
        "boolean",
        "Include the raw Bubble editor response in addition to compact summaries. Defaults false to keep agent context small.",
        default=False,
    ),
    "refresh": _prop(
        "boolean",
        "Ask Bubble to refresh storage calculation before returning storage usage.",
        default=True,
    ),
    "metric": _prop(
        "string",
        "Bubble time-series metric name.",
        examples=["page_views"],
    ),
    "resolution": _prop(
        "number",
        "Optional Bubble time-series resolution. Omit to auto-derive a compact resolution from the selected time window.",
        minimum=0,
    ),
    "use_observe": _prop(
        "boolean",
        "Use Bubble observe data for read_time_series.",
        default=True,
    ),
    "include_logs": _prop(
        "boolean",
        "Include Jetstream log sampling in performance audit output. Logs default to the live app version unless app_version is provided.",
        default=True,
    ),
    "source_profile": _prop(
        "string",
        "Local Bubble MCP profile used as the transfer source. This profile is only read during project-to-project transfer.",
        examples=["source-app", "template-app"],
    ),
    "target_profile": _prop(
        "string",
        "Local Bubble MCP profile used as the transfer target. Transfer execution writes only through this profile session.",
        examples=["client-app", "target-app"],
    ),
    "source_type": _prop(
        "string",
        "Source object type to transfer from the source project.",
        enum=["page", "reusable", "element"],
        examples=["page", "reusable", "element"],
    ),
    "source_ref": _prop(
        "string",
        "Source object name, Bubble id, or context id to inventory or transfer.",
        examples=["index", "Header", "gp_Hero"],
    ),
    "source_context": _prop(
        "string",
        "Optional source page or reusable context used to disambiguate element transfers.",
        examples=["index", "Header"],
    ),
    "target_context": _prop(
        "string",
        "Target page or reusable context where the transferred object should be placed.",
        examples=["index", "mcp-01"],
    ),
    "target_parent": _prop(
        "string",
        "Target parent element id/name, or root for page/reusable root insertion.",
        default="root",
        examples=["root", "gp_Content"],
    ),
    "target_name": _prop(
        "string",
        "Optional target object name override for the transferred root object.",
        examples=["Header Copy", "gp_Hero_Client"],
    ),
    "transfer_id": _prop(
        "string",
        "Local transfer plan id returned by bubble_transfer_plan.",
        examples=["transfer_20260708_120000_header"],
    ),
    "conflict_policy": _prop(
        "string",
        "How to handle target name conflicts during transfer planning.",
        enum=["fail", "rename", "replace", "reuse_existing"],
        default="fail",
    ),
    "asset_policy": _prop(
        "string",
        "How to handle source asset URLs in transfer planning.",
        enum=["reference_url", "stage_and_upload", "skip"],
        default="reference_url",
    ),
    "dependency_policy": _prop(
        "string",
        "How to handle dependencies not found in the target app.",
        enum=["map_only", "map_or_create", "skip_optional"],
        default="map_or_create",
    ),
    "reuse_policy": _prop(
        "string",
        "How the transfer planner should reuse target resources that are exact or structurally compatible with the source.",
        enum=["prefer_existing", "exact_only", "create_new"],
        default="prefer_existing",
    ),
    "include_collections": _prop(
        "boolean",
        "Include Bubble database collection schema dependencies: data types, fields, privacy rules, and option sets.",
        default=True,
    ),
    "collection_policy": _prop(
        "string",
        "How to transfer Bubble database collection schema.",
        enum=["skip", "map_existing", "create_missing", "replace_schema"],
        default="map_existing",
    ),
    "include_api_connector": _prop(
        "boolean",
        "Include API Connector API/call structure dependencies without copying secrets.",
        default=True,
    ),
    "api_connector_policy": _prop(
        "string",
        "How to transfer API Connector APIs and calls.",
        enum=["skip", "map_existing", "structure_only"],
        default="structure_only",
    ),
    "data_records_policy": _prop(
        "string",
        "How to handle live database records. Default skips record migration.",
        enum=["skip", "export_manifest_only", "data_api_import_preview"],
        default="skip",
    ),
    "include_payloads": _prop(
        "boolean",
        "Include redacted write payloads in transfer preview output.",
        default=False,
    ),
    "max_steps": _prop(
        "integer",
        "Optional maximum number of ordered transfer payloads to execute.",
        minimum=1,
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


def _profile_cache_refresh_tool() -> ToolSchema:
    schema = tool_schema(
        "bubble_profile_cache_refresh",
        "One-call profile cache refresh for routine requests like 'refresh cache do profile cliente2'. It forces context detection by default, updates the local .bubble-backed context/cache artifacts, and returns updated paths/timestamps so agents do not need to inspect directories, CLI help, or runtime internals.",
        [
            "profile",
            "app_id",
            "app_version",
            "output",
            "bubble_file",
            "consolelog_file",
            "force",
            "skip_id_to_path",
            "max_age_hours",
        ],
        required=["profile"],
    )
    schema["inputSchema"]["properties"]["force"] = _prop(
        "boolean",
        "Force cache/context refresh even when a previous context artifact exists. Defaults to true for this high-level refresh tool.",
        default=True,
    )
    return schema


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
        _profile_cache_refresh_tool(),
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
            ["profile", "payload", "execute", "calculate_derived"],
            required=["profile", "payload"],
        ),
        tool_schema(
            "bubble_execute_plan",
            "Execute a Bubble plan whose steps include args.write_payload. Set execute=true to mutate Bubble; otherwise it previews the plan.",
            ["profile", "plan", "execute", "compile", "app_id", "app_version", "context_file"],
            required=["profile", "plan"],
        ),
    ]


def transfer_tools() -> list[ToolSchema]:
    return [
        tool_schema(
            "bubble_transfer_inventory",
            "Inspect a source Bubble page, reusable, or element subtree for project-to-project transfer. This is read-only and returns dependency warnings before planning.",
            ["source_profile", "source_type", "source_ref", "source_context", "include_raw"],
            required=["source_profile", "source_type", "source_ref"],
        ),
        tool_schema(
            "bubble_transfer_plan",
            "Create a local preview-first transfer plan from one Bubble project profile to another. This writes only a local plan artifact, never Bubble.",
            [
                "source_profile",
                "target_profile",
                "source_type",
                "source_ref",
                "source_context",
                "target_context",
                "target_parent",
                "target_name",
                "conflict_policy",
                "asset_policy",
                "dependency_policy",
                "reuse_policy",
                "include_collections",
                "collection_policy",
                "include_api_connector",
                "api_connector_policy",
                "data_records_policy",
            ],
            required=["source_profile", "target_profile", "source_type", "source_ref"],
        ),
        tool_schema(
            "bubble_transfer_preview",
            "Dry-run an existing local Bubble transfer plan against the target profile session before execution.",
            ["transfer_id", "include_payloads"],
            required=["transfer_id"],
        ),
        tool_schema(
            "bubble_transfer_execute",
            "Execute a reviewed Bubble cross-project transfer plan against the target profile. Requires execute=true and confirm=true.",
            ["transfer_id", "execute", "confirm", "max_steps"],
            required=["transfer_id", "execute", "confirm"],
        ),
        tool_schema(
            "bubble_transfer_status",
            "Read a local Bubble transfer plan by id. This does not contact Bubble.",
            ["transfer_id"],
            required=["transfer_id"],
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
        ),
        tool_schema(
            "create_styles_from_html",
            "Create Bubble style definitions from HTML/CSS selectors without creating page elements. Extracts base styles plus hover, focus, disabled, and active/pressed pseudo-state rules, maps supported CSS into Bubble style fields, and returns create_style/add_style_condition/reorder_style_states operations for preview or execution.",
            [
                "profile",
                "url",
                "html_file",
                "file",
                "html",
                "selector",
                "style_name",
                "element_type",
                "execute",
                "rendered_html",
                "include_states",
                "states",
                "extra_css",
            ],
            required=["profile", "style_name", "element_type"],
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


def _metrics_app_version_field() -> JsonSchema:
    return _prop(
        "string",
        "Bubble app version/branch for log sampling. Defaults to live for production performance diagnostics; pass test or a branch id only when explicitly analyzing non-live behavior.",
        default="live",
        examples=["live", "test", "feature-checkout"],
    )


def performance_metrics_tools() -> list[ToolSchema]:
    audit = tool_schema(
            "bubble_performance_audit",
            "Run a compact read-only Bubble performance audit from direct editor metrics endpoints. It fetches workload usage, workload breakdown, workflow runs, plan usage, storage usage, and optional live-version logs, then returns prioritized optimization suggestions.",
            [
                "profile",
                "app_id",
                "app_version",
                "start",
                "end",
                "granularity",
                "platform",
                "include_logs",
                "include_raw",
            ],
            required=["profile"],
    )
    audit["inputSchema"]["properties"]["app_version"] = _metrics_app_version_field()

    logs = tool_schema(
        "bubble_logs_fetch",
        "Fetch Bubble Jetstream logs from the editor for a selected app/profile/time window. Defaults app_version to live for production performance diagnostics unless explicitly overridden. Read-only.",
        [
            "profile",
            "app_id",
            "app_version",
            "start",
            "end",
            "messages",
            "ascending",
            "is_state_ar",
            "limit",
            "include_raw",
        ],
        required=["profile", "start", "end"],
    )
    logs["inputSchema"]["properties"]["app_version"] = _metrics_app_version_field()

    return [
        audit,
        tool_schema(
            "bubble_workload_usage_by_date",
            "Read Bubble workload usage by date directly from the editor metrics endpoint. Use this for workload trend charts and date buckets. Read-only.",
            ["profile", "app_id", "start", "end", "granularity", "include_raw"],
            required=["profile", "start", "end"],
        ),
        tool_schema(
            "bubble_workload_usage_breakdown",
            "Read Bubble workload usage breakdown directly from the editor metrics endpoint. Use tag1/tag2 to drill into workload families. Read-only.",
            ["profile", "app_id", "start", "end", "granularity", "tag1", "tag2", "platform", "limit", "include_raw"],
            required=["profile", "start", "end"],
        ),
        logs,
        tool_schema(
            "bubble_plan_usage_get",
            "Read current Bubble plan usage for the selected profile/app from the editor endpoint. Read-only.",
            ["profile", "app_id", "include_raw"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_workflow_runs_get",
            "Read Bubble workflow run counts for the selected app/platform from the editor endpoint. Read-only.",
            ["profile", "app_id", "platform", "include_raw"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_storage_usage_get",
            "Read Bubble file storage usage and allowance for the selected app from the editor endpoint. Read-only.",
            ["profile", "app_id", "refresh", "include_raw"],
            required=["profile"],
        ),
        tool_schema(
            "bubble_time_series_read",
            "Read a Bubble editor time-series metric such as page_views for a profile/app/time window. Read-only.",
            ["profile", "app_id", "start", "end", "metric", "resolution", "use_observe", "include_raw"],
            required=["profile", "start", "end", "metric"],
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
            "Validate a local Bubble MCP extension pack directory before list/import/enable/disable workflows, without importing or enabling it.",
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
        tool_schema(
            "bubble_extension_call",
            "Preview an enabled declarative extension tool by exact tool name through a stable native MCP dispatcher. Use this when an enabled extension tool appears in the catalog but the client did not expose it as a direct callable function. v1 never writes to Bubble; execute=true returns an explicit unsupported-execution error.",
            ["tool", "arguments"],
            required=["tool", "arguments"],
        ),
        tool_schema(
            "bubble_extension_companion_start",
            "Start the local HTTP listener used by the shipped Chrome extension companion. The listener stays in this MCP server process and receives Bubble editor captures locally.",
            ["host", "port", "capture_key", "tool_session_id"],
        ),
        _empty_tool(
            "bubble_extension_companion_status",
            "Return whether the Chrome extension companion listener is running in this MCP server process.",
        ),
        _empty_tool(
            "bubble_extension_companion_stop",
            "Stop the Chrome extension companion listener running in this MCP server process.",
        ),
        tool_schema(
            "bubble_skill_validate",
            "Validate a declarative Bubble MCP skill contract JSON file. This checks allowed tools, non-executable steps, explicit outputs, and schema shape without executing the skill.",
            ["path"],
            required=["path"],
        ),
        tool_schema(
            "bubble_skill_describe",
            "Describe a Bubble MCP skill contract by local file path or installed skill id. This validates and summarizes the skill without executing steps.",
            ["path", "skill_id"],
        ),
        tool_schema(
            "bubble_skill_import",
            "Import a standalone Bubble MCP skill JSON file or skill directory into local skill storage. Imported skills start pending and must be enabled before running.",
            ["path"],
            required=["path"],
        ),
        tool_schema(
            "bubble_skill_export",
            "Export an installed Bubble MCP skill contract without run history or audit records.",
            ["skill_id", "output"],
            required=["skill_id", "output"],
        ),
        _empty_tool(
            "bubble_skill_list",
            "List local installed skills and skills exposed by enabled extension packs.",
        ),
        tool_schema(
            "bubble_skill_enable",
            "Enable a locally imported skill after validating its contract.",
            ["skill_id"],
            required=["skill_id"],
        ),
        tool_schema(
            "bubble_skill_disable",
            "Disable a locally imported skill without deleting the contract, run history, or exported copies from local storage.",
            ["skill_id"],
            required=["skill_id"],
        ),
        tool_schema(
            "bubble_skill_run",
            "Run a skill in preview mode or execute an approved preview plan. Mutating execution requires run_id, execute=true, and approve_execution=true.",
            ["skill_id", "inputs", "execute", "approve_execution", "run_id"],
            required=["skill_id"],
        ),
        tool_schema(
            "bubble_skill_author_start",
            "Start a friendly natural-language skill-authoring session. The generated contract is structured, but the user should not need to write JSON manually.",
            ["objective", "risk", "profile"],
            required=["objective"],
        ),
        tool_schema(
            "bubble_skill_author_update",
            "Add one natural-language answer or requirement to a skill-authoring session.",
            ["session_id", "answer", "field"],
            required=["session_id", "answer"],
        ),
        tool_schema(
            "bubble_skill_author_generate",
            "Generate and validate a skill contract from a skill-authoring session.",
            ["session_id", "skill_id", "output_dir"],
            required=["session_id"],
        ),
        tool_schema(
            "bubble_language_index",
            "Return a compact versioned Bubble MCP language index. This is the preferred low-token entrypoint instead of dumping the full tools/list catalog.",
            ["profile"],
        ),
        tool_schema(
            "bubble_language_query",
            "Return scoped compact Bubble MCP language entries by query, family, source, and risk filters.",
            ["query", "families", "sources", "risks", "limit", "profile", "framework", "cached_registry_version"],
            required=["query"],
        ),
        tool_schema(
            "bubble_language_tool_detail",
            "Lazy-load compact or full schema details for selected Bubble MCP tools only.",
            ["tools", "detail"],
            required=["tools"],
        ),
        tool_schema(
            "bubble_language_diff",
            "Return added, changed, and removed language entries since a previous registry version.",
            ["since", "profile"],
            required=["since"],
        ),
        tool_schema(
            "bubble_framework_language_pack",
            "Return a framework-shaped low-token Bubble MCP language pack for BMAD, Superpowers, or SDD.",
            ["framework", "profile", "scope", "limit"],
            required=["framework"],
        ),
        tool_schema(
            "bubble_framework_compile_program",
            "Compile a compact framework program into preview-safe Bubble MCP tool calls. This does not execute writes.",
            ["framework", "profile", "program"],
            required=["framework", "profile", "program"],
        ),
        tool_schema(
            "bubble_framework_plan_from_text",
            "Convert framework-authored natural-language text into a compact Bubble MCP program. This does not execute writes.",
            ["framework", "profile", "text"],
            required=["framework", "profile", "text"],
        ),
        tool_schema(
            "bubble_framework_execute_program",
            "Compile and preview or execute a compact framework program. Execute mode requires explicit approval.",
            ["framework", "profile", "program", "mode", "approved", "artifact_dir"],
            required=["framework", "profile", "program"],
        ),
        tool_schema(
            "bubble_framework_workspace_sync",
            "Copy generated framework artifacts into an external framework workspace layout.",
            ["framework", "artifact_dir", "workspace_dir"],
            required=["framework", "artifact_dir", "workspace_dir"],
        ),
        tool_schema(
            "bubble_language_cache_status",
            "Return the cached framework/profile language index status without rebuilding the registry.",
            ["framework", "profile"],
            required=["framework", "profile"],
        ),
        _empty_tool(
            "bubble_framework_list",
            "List supported AI development framework adapters such as BMAD, Superpowers, and SDD. Read-only.",
        ),
        tool_schema(
            "bubble_framework_generate_artifacts",
            "Generate local framework artifacts from Bubble MCP context for BMAD, Superpowers, or SDD. This does not execute Bubble writes.",
            ["framework", "profile", "objective", "scope", "context_summary", "output_dir"],
            required=["framework", "profile", "objective"],
        ),
        tool_schema(
            "bubble_framework_sync_evidence",
            "Append redacted implementation or validation evidence to a generated framework artifact directory.",
            ["framework", "profile", "evidence", "artifact_dir", "output_dir"],
            required=["framework", "profile", "evidence"],
        ),
        tool_schema(
            "bubble_framework_status",
            "Inspect local generated framework artifacts and evidence counts.",
            ["framework", "profile", "output_dir"],
        ),
        tool_schema(
            "bubble_tool_wizard_start",
            "Start a local tool-authoring session for captured Bubble editor writes and mark it as the active Chrome extension capture target. After this, the user should perform the actions in the Bubble editor and return so the agent can call bubble_tool_wizard_finalize.",
            ["intent", "target", "profile"],
            required=["intent", "target", "profile"],
        ),
        tool_schema(
            "bubble_tool_wizard_add_capture",
            "Add a captured Bubble editor write JSON file to a local tool-authoring session and classify it with the expert payload classifier. This does not replay writes.",
            ["session_id", "file"],
            required=["session_id", "file"],
        ),
        tool_schema(
            "bubble_tool_wizard_activate",
            "Mark an existing local tool-authoring session as the active capture target for Chrome extension write events.",
            ["session_id"],
            required=["session_id"],
        ),
        tool_schema(
            "bubble_tool_wizard_describe",
            "Describe a local tool-authoring session and its aggregate captured-write classification. Read-only and does not generate or activate tools.",
            ["session_id"],
            required=["session_id"],
        ),
        tool_schema(
            "bubble_tool_wizard_finalize",
            "Finalize a local tool-authoring session after the user finishes the Bubble editor actions. By default it returns what the MCP learned, questions, and test guidance. Pass generate_pack=true to immediately generate the candidate extension pack in the same MCP call.",
            ["session_id", "generate_pack", "extension_id", "tool_name", "output_dir"],
            required=["session_id"],
        ),
        tool_schema(
            "bubble_tool_wizard_generate",
            "Generate a candidate declarative extension pack from a finalized tool-authoring session. The generated pack is local, preview-first, and validated; it does not import, enable, or execute the tool.",
            ["session_id", "extension_id", "tool_name", "output_dir"],
            required=["session_id"],
        ),
        {
            "name": "bubble_learning_record",
            "description": (
                "Append one local consultative learning record. Records are stored as append-only JSONL and are not "
                "used for writes directly; extension-scoped write examples can be folded into generated extension "
                "runner patches during tool authoring."
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
                "Read-only; extension-scoped records may inform generated extension packs."
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
        *transfer_tools(),
        *html_import_tools(),
        *branch_changelog_tools(),
        *performance_metrics_tools(),
        *extension_kernel_tools(),
    ]
