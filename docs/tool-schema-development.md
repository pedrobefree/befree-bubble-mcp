# Tool Schema Development

The MCP catalog is optimized for agent selection. A tool schema should tell the
agent what capability to call, which arguments are required, which arguments are
safe defaults, and when an operation mutates Bubble.

## Where Schemas Live

- Native standalone tools are built in `src/bubble_mcp/server/schema_families.py`.
- Legacy Aria-compatible tools are enriched in `src/bubble_mcp/server/agent_catalog.py`.
- `src/bubble_mcp/server/schemas.py` combines native and legacy schemas, then applies descriptions and annotations.

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

- `profile_session_context_tools`: profiles, session import/list, context summary/search/import/detect.
- `planning_execution_tools`: plan, eval, compile, direct editor write, execute plan.
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
