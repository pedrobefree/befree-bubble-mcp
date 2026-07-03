# Tool Schema Development

The MCP catalog is optimized for agent selection. A tool schema should tell the
agent what capability to call, which arguments are required, which arguments are
safe defaults, and when an operation mutates Bubble.

## Where Schemas Live

- Native standalone tools are built in `src/bubble_mcp/server/schema_families.py`.
- Legacy Aria-compatible tools are enriched in `src/bubble_mcp/server/agent_catalog.py`.
- `src/bubble_mcp/server/schemas.py` combines native and legacy schemas, then applies descriptions and annotations.
- `src/bubble_mcp/aria_dispatch.py` routes compatible catalog calls to the
  packaged Aria runtime so tool behavior stays aligned with mature Bubble
  payload builders.

## Schema Family Rules

Use schema families instead of hand-writing large inline dictionaries in
`schemas.py`.

For each tool family:

- define shared fields once in `FIELD_LIBRARY`;
- set `required` only for arguments the agent must provide;
- add `default`, `minimum`, `maximum`, `format`, and `examples` when they help the agent choose correctly;
- keep `additionalProperties: false` for native tools;
- keep `execute` explicit and defaulted to `false` for Bubble mutations;
- require or validate `confirm` for destructive operations;
- avoid enums when Bubble can return unknown or changing values.

## Current Native Families

- `profile_session_context_tools`: profiles, session import/list, tool coverage, context summary/search/import/detect.
- `planning_execution_tools`: plan, eval, compile, direct editor write, execute plan.
- `bubble_eval_export_expert`: local redacted expert-capture export for eval growth.
- `html_import_tools`: advanced HTML-to-Bubble runtime import.
- `branch_changelog_tools`: branch list/create/delete, contributors, changelog fetch.

## Required Tests

When adding or refining a family, update tests in
`tests/unit/test_mcp_server.py` to verify:

- every property has a useful description;
- mutating tools expose `execute` with default `false`;
- destructive tools expose `confirm`;
- source-selection fields use `anyOf` when there are alternative input sources;
- numeric fields include realistic min/max bounds;
- `tools/list` still exposes the full catalog.
- `bubble_tool_coverage` reports zero uncovered tools for the Aria catalog.

## Agent Efficiency Rules

Schemas should reduce discovery loops:

- descriptions must say when to use the tool by user intent, not only what API it wraps;
- descriptions should make profile-based execution clear when a tool can use
  stored context/session state;
- read-only tools must set `readOnlyHint`;
- mutating tools must expose `execute` and default it to `false`;
- destructive tools must expose `confirm` and set `destructiveHint`;
- context-producing tools should explain freshness and artifact priority;
- eval tools should support focused reruns (`filter`, `failed_from`, `offset`, `limit`) so agents avoid rerunning the full suite.

## Runtime Compatibility Rules

When a catalog capability already exists in the packaged Aria runtime, prefer
dispatching to that runtime over rebuilding payload logic in the standalone
compiler. The standalone compiler should remain the deterministic fallback for
small abstract plans, exact `write_payload` execution, and tool families that do
not yet have a runtime method.

Every runtime-routed mutation must preserve the same safety contract:

- `execute=false` compiles through the runtime and returns the captured Bubble
  write payload without posting it;
- `execute=true` posts through the local Bubble session;
- successful writes are recorded into the local mutation overlay so subsequent
  context resolution can see changes before the next `.bubble` download;
- returned data must identify `engine`, `profile`, `app_id`, `app_version`,
  `executed`, and `write_count` so agents can reason from the response without
  re-inspecting the repository.

When a catalog name differs from the packaged runtime method name, add an
explicit alias in `src/bubble_mcp/aria_dispatch.py` and keep
`bubble_tool_coverage` green. Do not rely on agents discovering CLI subcommand
spellings at runtime.
