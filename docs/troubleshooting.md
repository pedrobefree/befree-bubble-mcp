# Troubleshooting

## `bubble-mcp` command not found

Install the package or activate the virtual environment where it is installed:

```bash
. .venv/bin/activate
python -m pip install -e .
bubble-mcp --help
```

For `pipx`, install from the local checkout with `pipx install .` or from the
published package with `pipx install befree-bubble-mcp`.

## `bubble-mcp` or `bubble-mcp-server` exits with `killed` on macOS

Local editable installs can occasionally be blocked by macOS execution policy
for generated console scripts. First repair the editable install, which rewrites
the local entrypoints through a macOS-safe replacement path:

```bash
python scripts/install_local.py --repair --extras browser,dev
bubble-mcp --help
```

If a specific MCP client still blocks generated scripts, the Python modules are
the stable fallback:

```bash
python -m bubble_mcp.cli.main --help
printf '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}\n' | python -m bubble_mcp.server.stdio
```

For MCP client configuration, use the virtualenv Python command with
`args: ["-m", "bubble_mcp.server.stdio"]` instead of launching the generated
`bubble-mcp-server` script directly.

## `No module named playwright` after installing browser extras

Your shell may be using a global or Conda `pip` instead of the virtual
environment's `pip`. Install through the active Python interpreter:

```bash
. .venv/bin/activate
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

## MCP client cannot find or run `bubble-mcp-server`

Many desktop MCP clients do not inherit your shell's activated virtual
environment. Local macOS execution policy can also block generated console
scripts in editable installs. Prefer running the server module with the
virtualenv Python:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/python",
      "args": ["-m", "bubble_mcp.server.stdio"]
    }
  }
}
```

You can find the Python path from an activated virtual environment:

```bash
command -v python
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
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' | python -m bubble_mcp.server.stdio
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
