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
- `bubble_plan_dry_run`: creates a validated deterministic dry-run plan.
- `bubble_import_html_dry_run`: converts HTML text into a validated dry-run plan.
- `bubble_eval_run`: runs a deterministic planning eval dataset.

Direct mutating Bubble execution is not implemented in the current server and is not exposed to MCP clients.
