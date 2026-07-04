# CLI Reference

The Python package installs two console scripts:

- `bubble-mcp`
- `bubble-mcp-server`

Use `bubble-mcp` to manage local settings. Use `bubble-mcp-server` from an MCP
client configuration.

## `bubble-mcp init`

Creates a local config directory and empty `settings.json`.

```bash
bubble-mcp init
```

Default path:

```text
~/.config/bubble-mcp/settings.json
```

Options:

```bash
bubble-mcp init --config-dir /path/to/bubble-mcp-config
```

`--config-dir` affects the init command. For later commands and the server, set
`BUBBLE_MCP_CONFIG_DIR` when you want to use a non-default settings directory.

## `bubble-mcp profile add`

Adds or updates a Bubble profile.

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
```

Arguments and options:

- `name`: local profile name, such as `my-app`.
- `--app-id`: required Bubble app id.
- `--appname`: optional Bubble app name. Defaults to `--app-id`.
- `--editor-url`: optional Bubble editor URL for the app.

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url "https://bubble.io/page?id=my-bubble-app" \
  --app-version test
```

The first profile added becomes `default_profile` in `settings.json`.

## `bubble-mcp profile list`

Lists local profiles.

```bash
bubble-mcp profile list
```

Output is JSON and includes:

- `default_profile`
- `profiles[].name`
- `profiles[].app_id`
- `profiles[].appname`
- `profiles[].editor_url`

## `bubble-mcp context summary`

Summarizes a compact Bubble context JSON file.

```bash
bubble-mcp context summary --file /path/to/context.json
```

The response includes `freshness` with source, timestamp source, age, and stale
status. This helps agents decide whether to call `context detect --force` before
a mutation.

## `bubble-mcp context find`

Searches a compact Bubble context JSON file.

```bash
bubble-mcp context find "button" --file /path/to/context.json --limit 10
```

## `bubble-mcp plan`

Creates and semantically validates a local Bubble plan from a message.

```bash
bubble-mcp plan "add a button to the index page" --context index --parent index
```

This command does not mutate Bubble by itself. The response includes:

- `routing`/`parser`: whether the packaged example corpus or fallback regex matched.
- `validation`: semantic validation.
- `structural_validation`: step graph and payload readiness.
- `operation_snapshot.next_user_action`: the next action an agent should take.

Use `execute-plan --execute` for plans whose steps include `args.write_payload`.

## `bubble-mcp import html`

Converts an HTML file or hydrated URL into Bubble output. Local files use the conservative plan converter by default; `--url` automatically uses the advanced rendered runtime.

```bash
bubble-mcp import html --file component.html --context index --parent index
```

Add `--compile --app-id` to convert supported generated steps into
`args.write_payload` objects immediately.

```bash
bubble-mcp import html --file component.html --context index --parent index --compile --app-id my-bubble-app
```

Use `--runtime` for Aria's advanced `create-from-html` importer:

```bash
bubble-mcp import html \
  --url https://example.com/page.html \
  --profile smoke \
  --app-id my-bubble-app \
  --context index \
  --parent root \
  --selector '.pricing-card' \
  --translate-to-existing-styles
```

Add `--execute` to apply the generated writes to Bubble.

## `bubble-mcp session import`

Imports local Bubble editor session headers/cookies.

```bash
bubble-mcp session import --profile my-app --file ./bubble-session.json
```

## `bubble-mcp session login`

Opens a local Chromium browser through Playwright and captures Bubble cookies.
The browser profile is persisted under the local Bubble MCP config directory so
subsequent login attempts can reuse the same Bubble browser session.

```bash
python -m pip install "befree-bubble-mcp[browser]"
python -m playwright install chromium
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 120
```

`--wait-seconds` is the maximum time the command keeps polling cookies. After
logging in, leave the Bubble editor open for a few seconds before closing the
browser window. If the process is interrupted after Bubble cookies were
observed, the newest usable session is still saved; if it is interrupted before
login completes, rerun the command.

During capture, the command prints human-readable progress to stderr. When it
prints `Session cookies detected. You can close the browser now`, the session
has enough data to be saved. The final JSON result is still printed to stdout.
Use `--quiet` to suppress progress messages in scripts.

## `bubble-mcp session list`

Lists imported session metadata without printing secrets.

```bash
bubble-mcp session list
```

## `bubble-mcp write`

Sends an exact Bubble `/appeditor/write` payload. Without `--execute`, this
prints the normalized request and redacted headers.

```bash
bubble-mcp write --profile my-app --payload ./write-payload.json
bubble-mcp write --profile my-app --payload ./write-payload.json --execute
```

## `bubble-mcp execute-plan`

Executes a plan. If the plan contains abstract `create_text` or `create_group`
steps, pass `--compile` and `--app-id` to compile those steps into
`args.write_payload` before execution. When `--compile` is used and no
`--context-file` is supplied, the CLI detects project context automatically
from the profile/session before compiling.

```bash
bubble-mcp execute-plan --profile my-app --file ./plan.json --execute
bubble-mcp execute-plan --profile my-app --file ./plan.json --app-id my-bubble-app --compile --execute
bubble-mcp execute-plan --profile my-app --file ./plan.json --app-id my-bubble-app --compile --context-file ./my-app-context.json --execute
```

When compiling visual creation steps for a real editor write, pass
`--context-file` or include Bubble internal ids in the step args. The compiler
uses that context to emit the editor index updates Bubble expects:
`_index.id_to_path`, `_index.issues_list`, and `_index.issues_sub`, followed by
the `CreateElement` change at the resolved `%p3.<page-id>.%el.<slot-id>` path.
Bubble can return HTTP 200 for a write that does not appear in the editor when
these index paths target the wrong page or parent.

Use `--no-auto-context` only when deliberately compiling without live project
context.

When a context file is loaded for compile/execute, the runtime also merges the
local mutation overlay for the selected profile/app. This makes pages and
elements created by earlier MCP writes visible even when the cached `.bubble`
export has not been refreshed yet.

## `bubble-mcp branch`

Reads and manages Bubble editor branches through the stored local session.

```bash
bubble-mcp branch list --profile my-app
bubble-mcp branch contributors --profile my-app --app-version test
```

Create a branch from the profile/default version:

```bash
bubble-mcp branch create --profile my-app --name feature-x --description "Feature branch"
```

Add `--execute` to actually create it in Bubble. To create a sub-branch, pass
the parent branch/version id:

```bash
bubble-mcp branch create \
  --profile my-app \
  --name feature-x-child \
  --from-app-version parent-branch-id \
  --execute
```

Delete previews by default. Real deletion requires both `--execute` and
`--confirm`.

```bash
bubble-mcp branch delete --profile my-app --app-version feature-branch-id
bubble-mcp branch delete --profile my-app --app-version feature-branch-id --execute --confirm
```

## `bubble-mcp changelog fetch`

Fetches Bubble editor changelog entries for a profile and branch/version.

```bash
bubble-mcp changelog fetch --profile my-app --app-version test --num-fetch 50
```

Common filters:

```bash
bubble-mcp changelog fetch \
  --profile my-app \
  --app-version test \
  --start-timestamp 1780282800000 \
  --end-timestamp 1783091092976 \
  --change-type Data \
  --change-path user_types.user. \
  --user-id 1234567890x1234567890
```

For advanced Bubble-native filters, pass `--filters` with either a JSON object
or a path to a JSON file.

## `bubble-mcp compile-plan`

Compiles supported abstract plan steps into Bubble write payloads.

```bash
bubble-mcp compile-plan --file ./plan.json --app-id my-bubble-app --output ./compiled-plan.json
bubble-mcp compile-plan --file ./plan.json --app-id my-bubble-app --context-file ./my-app-context.json
```

## `bubble-mcp context detect`

Detects and materializes project context. It tries local `.bubble` or
`console.log(app)` artifacts when provided, then downloads Bubble's authenticated
export endpoint (`/appeditor/export/{version}/{appId}.bubble`) before falling
back to the editor crawler. Successful downloads are cached under
`~/.config/bubble-mcp/contexts/{profile}/` and split into
`bubble_modules/{appId}/` next to the compact context.

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --force
bubble-mcp context detect --profile my-app --app-id my-bubble-app --bubble-file ./app.bubble
bubble-mcp context detect --profile my-app --app-id my-bubble-app --consolelog-file ./consolelog-app.txt
```

## `bubble-mcp eval run`

Runs a deterministic planning dataset. Use `--compile --app-id` to require
compiler coverage and include write-payload/token metrics in the report. The
report includes matched/tool/args/missing/validation/warning metrics plus
`parser_summary` and `fallback_summary` for agent-routing diagnostics.
Use `--filter`, `--failed-from`, `--offset`, and `--limit` for cheap focused
reruns instead of reprocessing a large dataset.

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --compile --app-id my-bubble-app --report reports/basic-compiled.json
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --failed-from reports/basic-compiled.json
```

## `bubble-mcp eval export-expert`

Exports local captured Bubble editor writes into redacted eval cases with family
classification and tool hints. Use it to grow the eval corpus from known-good
examples without committing sessions, cookies, or raw secrets.

```bash
bubble-mcp eval export-expert \
  --input /tmp/captured-writes.json \
  --output /tmp/bubble-expert-evals.json
```

## `bubble-mcp validate-plan`

Validates a plan JSON file.

```bash
bubble-mcp validate-plan --file /path/to/plan.json
bubble-mcp validate-plan --file /path/to/plan.json --execute
```

Pass `--execute` to require executable write payloads and destructive-operation
confirmation checks.

## `bubble-mcp tools guide`

Returns compact routing guidance for agents or humans that need to choose the
right MCP tool family without reading the full catalog.

```bash
bubble-mcp tools guide --task "convert an HTML selector from a URL into a Bubble page"
```

Use this when the request is natural language and the caller needs the likely
route, setup requirements, execution policy, and next tool families.

## `bubble-mcp tools search`

Searches the exposed MCP catalog and returns compact matching tool metadata.

```bash
bubble-mcp tools search --query "html selector import" --limit 5
bubble-mcp tools search --query "workflow page load action"
```

Use this instead of dumping `tools/list` when an agent only needs a small,
relevant subset of names, required fields, properties, and annotations.

## `bubble-mcp tools recipe`

Returns an ordered MCP execution recipe for a natural-language Bubble task.

```bash
bubble-mcp tools recipe --task "convert an HTML selector from a URL into a Bubble page" --profile my-app --context index
bubble-mcp tools recipe --task "create a page-load workflow action" --recipe workflow
```

Use this when the caller already understands the user intent but needs the
right preflight checks, tool sequence, arguments to fill, safeguards, and
verification path. It is read-only and does not mutate Bubble.

## `bubble-mcp smoke runtime`

Runs safe runtime smoke suites through the same tool handlers used by MCP
clients.

```bash
bubble-mcp smoke runtime --suite coverage
bubble-mcp smoke runtime --suite safe-read --profile my-app
bubble-mcp smoke runtime --suite preview-write --profile my-app --context index --parent root
bubble-mcp smoke runtime --suite family-preview --profile my-app --context index --parent root
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --verify-context
```

Suites:

- `coverage`: local-only catalog coverage check.
- `safe-read`: read-only profile/session/project checks.
- `preview-write`: representative create/import mutations compiled with
  `execute=false`; this does not post changes to Bubble.
- `family-preview`: representative visual, container, input, schema, workflow,
  style, HTML import, branch, and changelog paths with `execute=false` or
  read-only editor calls.
- `execute-write`: authenticated real-write smoke that creates a temporary
  page and representative elements. This suite requires `--execute`.
  Add `--verify-context` to refresh the `.bubble` context after the writes and
  assert that the temporary page, group, text, button, and input materialized
  with required defaults.

Optional report file:

```bash
bubble-mcp smoke runtime --suite preview-write --profile my-app --report ./runtime-smoke.json
```

Optional real-write cleanup:

```bash
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --cleanup
```

## `bubble-mcp-server`

Starts the stdio MCP server.

```bash
bubble-mcp-server
```

This command waits for newline-delimited JSON-RPC messages on standard input and
writes JSON-RPC responses to standard output. MCP clients usually launch it for
you.

Implemented MCP methods:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/templates/list`
- `resources/read`
- `prompts/list`
- `prompts/get`
- `completion/complete`

`tools/call` responses include JSON text content and matching
`structuredContent` for clients that can consume structured tool results. Tool
execution failures return `isError: true` tool results instead of JSON-RPC
errors.

Implemented resources:

- `bubble://docs/agent-runtime`
- `bubble://catalog/summary`
- `bubble://recipes/summary`
- `bubble://recipes/{recipe_id}`

Implemented prompts:

- `bubble-task-runbook`
- `bubble-html-import`
- `bubble-quality-gate`

Implemented completions:

- `bubble://recipes/{recipe_id}`: recipe ids such as `html_import`.
- Prompt arguments: `profile`, `context`, `parent`, and `execute` where
  applicable.

Implemented tools:

- `bubble_health_check`
- `bubble_agent_guide`
- `bubble_tool_search`
- `bubble_task_recipe`
- `bubble_tool_coverage`
- `bubble_runtime_smoke`
- `bubble_profile_list`
- `bubble_context_summary`
- `bubble_context_find`
- `bubble_plan`
- `create_from_html`
- `bubble_compile_plan`
- `bubble_eval_run`
- `bubble_eval_export_expert`
- `bubble_session_list`
- `bubble_session_import`
- `bubble_editor_write`
- `bubble_execute_plan`
