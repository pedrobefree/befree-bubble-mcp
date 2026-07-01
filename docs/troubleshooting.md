# Troubleshooting

## `bubble-mcp` command not found

Install the package or activate the virtual environment where it is installed:

```bash
. .venv/bin/activate
pip install -e .
bubble-mcp --help
```

For `pipx`, install from the local checkout with `pipx install .` or from the
published package with `pipx install befree-bubble-mcp`.

## MCP client cannot find `bubble-mcp-server`

Many desktop MCP clients do not inherit your shell's activated virtual
environment. Use the absolute path to the console script in the client config:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/bubble-mcp-server",
      "args": []
    }
  }
}
```

You can find the path from an activated virtual environment:

```bash
command -v bubble-mcp-server
```

## No profiles returned

Run:

```bash
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
```

If you used a custom config directory, pass the same environment variable to the
CLI and MCP server:

```bash
export BUBBLE_MCP_CONFIG_DIR=/path/to/bubble-mcp-config
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
bubble-mcp profile list
```

Use the same `BUBBLE_MCP_CONFIG_DIR` in your MCP client config.

## Server appears to hang when run manually

This is expected. `bubble-mcp-server` is a stdio MCP server and waits for
newline-delimited JSON-RPC input.

To verify it responds:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' | bubble-mcp-server
```

## MCP server starts but writes do not execute

Check these items:

- `bubble_health_check` should report `mutations: true`.
- `bubble_session_list` should show a session for the target profile.
- `bubble_editor_write` and `bubble_execute_plan` preview requests unless
  `execute=true` is passed.
- The payload must contain Bubble's `changes` array.

## `Unknown Bubble MCP tool`

The client requested a tool that the server does not implement. Run `tools/list`
from the client or use the manual protocol check above to confirm the available
tool names.
