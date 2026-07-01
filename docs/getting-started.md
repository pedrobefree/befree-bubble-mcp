# Getting Started

`befree-bubble-mcp` is currently a local-first Python package. It gives Bubble
developers a small CLI for profile setup and a stdio MCP server that MCP clients
can launch.

The current server is read-only. It exposes profile listing and health metadata;
Bubble mutation tools are not implemented yet.

## 1. Install locally

From a local checkout of this repository:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e .
```

If you want test and development dependencies too:

```bash
pip install -e ".[dev]"
```

Confirm the console scripts are available:

```bash
bubble-mcp --help
bubble-mcp-server
```

Stop `bubble-mcp-server` with `Ctrl+C` after confirming it starts. It is a
stdio server, so it waits for JSON-RPC messages on standard input.

## 2. Initialize local settings

Create the local config directory and settings file:

```bash
bubble-mcp init
```

By default this writes `~/.config/bubble-mcp/settings.json`. To keep settings in
a different location, set `BUBBLE_MCP_CONFIG_DIR` when running both the CLI and
the MCP server.

## 3. Add a Bubble app profile

Use the Bubble app id from your Bubble editor URL. For example, if the editor URL
contains `id=my-bubble-app`, use `my-bubble-app`:

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
bubble-mcp profile list
```

You can also store the app name and editor URL for easier inspection:

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url "https://bubble.io/page?id=my-bubble-app"
```

The first profile you add becomes the default profile in `settings.json`.

## 4. Run the MCP server

```bash
bubble-mcp-server
```

The server speaks newline-delimited JSON-RPC over stdio. In normal use, your MCP
client starts this command for you.

## 5. Connect an MCP client

For Codex or another MCP client, add a stdio server entry that runs
`bubble-mcp-server`:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "bubble-mcp-server",
      "args": []
    }
  }
}
```

If you installed the package in a virtual environment and the client cannot find
`bubble-mcp-server`, point the command at the virtualenv script:

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

After connecting, the available tools should be:

- `bubble_health_check`
- `bubble_profile_list`

No Bubble editor mutations are currently exposed.
