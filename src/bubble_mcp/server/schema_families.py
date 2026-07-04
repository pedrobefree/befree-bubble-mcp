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
    "app_version": _prop(
        "string",
        "Bubble branch/version id. Use test/version-test by default; pass a specific branch id when operating outside test.",
        default="test",
        examples=["test", "version-test", "feature-checkout"],
    ),
    "file": _prop(
        "string",
        "Local file path for the input artifact.",
        examples=["/Users/me/project/app.bubble", "/tmp/bubble-context.json"],
    ),
    "output": _prop(
        "string",
        "Optional local output path for generated context or diagnostic artifacts.",
        examples=["/tmp/bubble-context.json"],
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
        "Runtime smoke suite to run. coverage checks catalog coverage only; safe-read runs read-only profile calls; preview-write compiles representative mutations with execute=false; family-preview exercises representative visual/container/input/schema/workflow/style/html/branch/changelog paths without writes; execute-write creates temporary Bubble objects and requires execute=true.",
        enum=["coverage", "safe-read", "preview-write", "family-preview", "execute-write"],
        default="coverage",
    ),
    "include_details": _prop(
        "boolean",
        "Include redacted raw tool results in smoke output. Leave false for compact agent-friendly summaries.",
        default=False,
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
        _empty_tool("bubble_profile_list", "List local Bubble MCP profiles. This is read-only."),
        _empty_tool(
            "bubble_health_check",
            "Return local Bubble MCP server health and capability metadata.",
        ),
        tool_schema(
            "bubble_agent_guide",
            "Return compact agent-facing routing guidance for the Bubble MCP catalog. Call this when a client needs to choose the correct tool family without inspecting CLI help or repository code.",
            ["task"],
        ),
        _empty_tool(
            "bubble_tool_coverage",
            "Report runtime coverage for every exposed Bubble MCP tool, including native, Aria-runtime, alias, custom, compiler fallback, and uncovered categories. Read-only.",
        ),
        tool_schema(
            "bubble_runtime_smoke",
            "Run an operational smoke suite for the MCP runtime. coverage is local-only, safe-read performs read-only calls, preview-write compiles representative Bubble mutations with execute=false, and execute-write creates temporary Bubble objects only when execute=true.",
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
            "Search a compact Bubble context JSON file.",
            ["file", "query", "limit"],
            required=["file", "query"],
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


def native_tool_schemas() -> list[ToolSchema]:
    """Return native tool schemas grouped by capability family."""

    return [
        *profile_session_context_tools(),
        *planning_execution_tools(),
        *html_import_tools(),
        *branch_changelog_tools(),
    ]
