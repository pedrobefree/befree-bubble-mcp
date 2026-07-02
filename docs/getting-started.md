# Getting Started

`befree-bubble-mcp` is a local-first Python package. It gives Bubble developers
a CLI for profile/session setup and a stdio MCP server that MCP clients can
launch.

The server supports real Bubble editor writes through `/appeditor/write` when a
valid local session is imported and the caller explicitly sets `execute=true`.
Without execution opt-in, write commands preview the normalized request.

## 1. Install locally

From a local checkout of this repository:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install ".[browser]"
python -m playwright install chromium
```

If you want test and development dependencies too:

```bash
python -m pip install ".[dev,browser]"
```

Use `python -m pip install -e ".[dev,browser]"` only when you are actively
editing the source checkout and want imports to point at local files.

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

## 5. Import a Bubble editor session

Create a JSON file with the session headers/cookies captured from an authenticated
Bubble editor request:

```json
{
  "appId": "my-bubble-app",
  "url": "https://bubble.io/page?id=my-bubble-app",
  "headers": {
    "Cookie": "..."
  },
  "appVersion": "test"
}
```

Import it locally:

```bash
bubble-mcp session import --profile my-app --file ./bubble-session.json
bubble-mcp session list
```

Session files are stored under `~/.config/bubble-mcp/sessions/` and are never
committed by this repository.

## 6. Connect an MCP client

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
- `bubble_session_list`
- `bubble_session_import`
- `bubble_editor_write`
- `bubble_execute_plan`
