# MCP Clients

`bubble-mcp-server` is a stdio MCP server. It is meant to be started by an MCP
client, not kept running as a separate HTTP service.

## Before connecting

Install the Python package and create at least one local Bubble profile:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e .
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
bubble-mcp profile list
```

## Codex or other stdio MCP clients

Use `bubble-mcp-server` as the command:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "bubble-mcp-server",
      "args": [],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

If your MCP client does not inherit the activated virtual environment, use the
absolute path to the installed console script:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/bubble-mcp-server",
      "args": [],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

Keep `BUBBLE_MCP_CONFIG_DIR` consistent with the directory used when you ran
`bubble-mcp init` and `bubble-mcp profile add`.

## Quick manual protocol check

You can verify the server responds before adding it to a client:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' | bubble-mcp-server
```

The response should include server info for `befree-bubble-mcp` and the tools
listed below.

## Available tools

- `bubble_health_check`: reports local server capabilities.
- `bubble_profile_list`: lists configured local Bubble profiles.
- `bubble_context_summary`: summarizes a compact context JSON file.
- `bubble_context_find`: searches a compact context JSON file.
- `bubble_plan`: creates a validated deterministic plan.
- `bubble_plan_dry_run`: compatibility alias for `bubble_plan`.
- `bubble_import_html`: converts HTML text into a validated plan.
- `bubble_import_html_dry_run`: compatibility alias for `bubble_import_html`.
- `bubble_eval_run`: runs a deterministic planning eval dataset.
- `bubble_session_list`: lists locally imported Bubble editor sessions.
- `bubble_session_import`: imports session headers/cookies into local storage.
- `bubble_editor_write`: posts an exact Bubble `/appeditor/write` payload. Set `execute=true` to mutate Bubble.
- `bubble_execute_plan`: executes plan steps that include `args.write_payload`. Set `execute=true` to mutate Bubble.

Mutating calls require a stored local session. Calls without `execute=true`
return a preview instead of posting to Bubble.
