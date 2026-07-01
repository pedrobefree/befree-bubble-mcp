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
  --editor-url "https://bubble.io/page?id=my-bubble-app"
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

## `bubble-mcp session import`

Imports local Bubble editor session headers/cookies.

```bash
bubble-mcp session import --profile my-app --file ./bubble-session.json
```

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

Executes a plan whose steps include `args.write_payload`.

```bash
bubble-mcp execute-plan --profile my-app --file ./plan.json --execute
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
- `bubble_eval_run`
- `bubble_session_list`
- `bubble_session_import`
- `bubble_editor_write`
- `bubble_execute_plan`
