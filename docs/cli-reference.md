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

This command does not mutate Bubble by itself. Use `execute-plan --execute` for
plans whose steps include `args.write_payload`.

## `bubble-mcp import html`

Converts a simple HTML file into a validated Bubble plan.

```bash
bubble-mcp import html --file component.html --context index --parent index
```

Add `--compile --app-id` to convert supported generated steps into
`args.write_payload` objects immediately.

```bash
bubble-mcp import html --file component.html --context index --parent index --compile --app-id my-bubble-app
```

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
browser window.

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

## `bubble-mcp compile-plan`

Compiles supported abstract plan steps into Bubble write payloads.

```bash
bubble-mcp compile-plan --file ./plan.json --app-id my-bubble-app --output ./compiled-plan.json
bubble-mcp compile-plan --file ./plan.json --app-id my-bubble-app --context-file ./my-app-context.json
```

## `bubble-mcp context detect`

Detects and materializes project context. It tries local `.bubble` or
`console.log(app)` artifacts when provided, then falls back to the Bubble editor
crawler using the captured session.

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --force
bubble-mcp context detect --profile my-app --app-id my-bubble-app --bubble-file ./app.bubble
bubble-mcp context detect --profile my-app --app-id my-bubble-app --consolelog-file ./consolelog-app.txt
```

## `bubble-mcp eval run`

Runs a deterministic planning dataset. Use `--compile --app-id` to require
compiler coverage and include write-payload/token metrics in the report.

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --compile --app-id my-bubble-app --report reports/basic-compiled.json
```

## `bubble-mcp validate-plan`

Validates a plan JSON file.

```bash
bubble-mcp validate-plan --file /path/to/plan.json
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

Implemented tools:

- `bubble_health_check`
- `bubble_profile_list`
- `bubble_context_summary`
- `bubble_context_find`
- `bubble_plan`
- `bubble_import_html`
- `bubble_compile_plan`
- `bubble_eval_run`
- `bubble_session_list`
- `bubble_session_import`
- `bubble_editor_write`
- `bubble_execute_plan`
