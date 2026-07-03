# Buildprint MCP Parity Notes

This note tracks the public Buildprint MCP/CLI patterns that should guide
`befree-bubble-mcp` quality. It is intentionally token-free and does not store
project-specific MCP endpoint URLs.

## Observed MCP Catalog Pattern

Buildprint exposes a compact, agent-readable catalog. The observed MCP server
reported 43 tools grouped by outcome:

- Agent runs: `deploy_agent`, `send_agent_follow_up`, `get_agent_status`,
  `archive_agent`.
- Documentation and feedback: `search_buildprint_docs`, `submit_feedback`.
- Project inventory: `list_apps`, `list_bubble_branches`.
- Bubble runtime data: `search_data`, `fetch_data`, `aggregate_data`,
  `create_thing`, `update_thing`, `delete_thing`.
- Logs and usage: `get_simple_logs`, `get_advanced_logs`,
  `get_workload_usage`.
- Monitors: `list_monitors`, `create_monitor`, `update_monitor`,
  `delete_monitor`.
- Tests: `list_tests`, `get_test`, `create_test`, `update_test`,
  `delete_test`, `list_test_groups`, `get_test_group`, `create_test_group`,
  `update_test_group`, `delete_test_group`, `list_test_users`,
  `get_test_user`, `create_test_user`, `update_test_user`,
  `delete_test_user`, `start_test_run`, `get_test_run`,
  `start_test_group_run`, `get_test_group_run`.
- Automations: `list_automations`, `run_automation`.
- Reviews: `complete_review`.

Their schemas follow a consistent structure:

- Tool names are outcome-specific: `list_*`, `get_*`, `create_*`, `update_*`,
  `delete_*`, `start_*`, `run_*`, `deploy_*`, `send_*`, `archive_*`.
- Every tool has a specific JSON Schema with required fields, property
  descriptions, enums, min/max constraints, and array/object item schemas where
  useful.
- Tool descriptions include operational preconditions, safety notes, backend
  semantics, defaults, and examples of valid values.
- Annotations are meaningful: read-only reads use `readOnlyHint=true`, delete
  or irreversible actions use `destructiveHint=true`, and tools that call
  external services or long-running hosted systems use `openWorldHint=true`.
- Mutating data tools require a human-readable `description` field shown to the
  user before the write runs.
- The MCP surface is not a generic command runner. It exposes typed capabilities
  and pushes broad editing workflows into the CLI/workspace model.

## CLI Pattern To Match

Buildprint's CLI is organized around an editable local workspace:

1. `project clone` creates a deterministic filesystem projection of one Bubble
   app branch.
2. `sync` refreshes the Bubble snapshot.
3. Users or agents edit canonical files or use helper commands like `new` and
   `copy`.
4. `check` validates pending changes and records a freshness fingerprint.
5. `apply` sends the validated diff back to Bubble.

Relevant CLI surfaces for future parity:

- `summary`, `tree`, `context`, and `schema` for project exploration.
- `docs` and `guidelines` for agent-facing help.
- `new`, `copy`, and `utils generate-ids` for canonical local edits.
- `check`, `apply`, `savepoint`, `branch`, `merge`, and `audit` for safety and
  release discipline.

## Translation To Befree Bubble MCP Syntax

The current Befree package keeps Aria-compatible tool names and execution
semantics, but the agent-facing catalog should emulate Buildprint's specificity:

- Keep `profile` as the local workspace/session selector.
- Use `app_id`, `app_version`, and `context_file` as the standalone compiler
  bridge for mutating tools.
- Use `execute=false` for preview and `execute=true` only when the user asks to
  apply a change.
- Keep `write_payload`/`payload` as an advanced escape hatch only after another
  step produced a validated Bubble payload.
- Add family-specific required fields and optional fields instead of presenting
  every Aria tool as `{ profile, context, payload }`.
- Keep `additionalProperties=true` during migration so legacy Aria arguments
  still work, then tighten individual tools once execution coverage is verified.

Implemented catalog families:

- Context/session/profile native tools.
- Advanced HTML import native tool.
- Page/reusable/custom-state basics.
- Visual element create/update/delete families.
- Style and style-condition tools.
- Workflow/event/action tools.
- Data type and option-set families.
- Colors, fonts, app/project settings, API tokens, redirects, app text, and
  Figma bridge families at schema-metadata level.

## Coverage Gaps Versus Buildprint

These Buildprint capabilities do not yet have equivalent standalone coverage:

- Hosted agent lifecycle: deploy, follow-up, status, archive.
- First-class docs/guidelines search resources exposed through MCP.
- Bubble database runtime reads and writes: search, fetch, aggregate, create,
  update, delete records.
- Logs, advanced log search, and workload usage.
- Log monitor CRUD.
- Project tests as first-class entities: tests, groups, users, runs, and run
  status.
- Manual/API automations.
- Code review completion workflows.
- App inventory and branch listing as first-class MCP tools.
- Savepoints, branch creation, branch merge, audit, and `sync -> check -> apply`
  local workspace workflow.
- Feedback submission tool for agents to report exact tool/schema/runtime
  friction.

## Developer Extensibility Radar

Do not implement this yet, but future contributors should not need to hand-edit
large Python dictionaries to add tools. A high-quality path would be:

- Declarative tool registry files grouped by family.
- Schema/code generation for MCP schemas, CLI docs, tests, and examples.
- Golden tests that verify `tools/list` descriptions, required fields,
  annotations, and example calls.
- A contribution guide for adding a tool: catalog entry, execution mapping,
  semantic validation, smoke fixture, and docs.
- Optional extension hooks so project-specific tools can live outside the core
  package without forking it.
