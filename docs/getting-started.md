# Getting Started

`befree-bubble-mcp` is a local-first Python package. It gives Bubble developers
a CLI for project setup and a stdio MCP server that MCP clients can launch.

The server can write to Bubble's editor only when a local profile has a captured
Bubble session, a detected project context, and the caller explicitly sets
`execute=true`. Without execution opt-in, mutation tools preview the normalized
request.

## 1. Install

For a local checkout:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python scripts/install_local.py --extras browser,dev
python -m playwright install chromium
```

If an editable install is interrupted or a console script stops importing
`bubble_mcp`, repair the checkout:

```bash
python scripts/install_local.py --repair --extras browser,dev
```

For a packaged install:

```bash
python -m pip install "befree-bubble-mcp[browser]"
python -m playwright install chromium
```

Confirm the CLI is available:

```bash
bubble-mcp --help
```

## 2. Initialize Local Settings

```bash
bubble-mcp init
```

By default this writes local settings under:

```text
~/.config/bubble-mcp
```

Use `BUBBLE_MCP_CONFIG_DIR` when you need a different config directory. Use the
same config directory for the CLI and the MCP server.

## 3. Add A Bubble Project Profile

Use the Bubble app id from your Bubble editor URL. For example, if the editor URL
contains `id=my-bubble-app`, use `my-bubble-app`:

```bash
bubble-mcp profile add my-app --app-id my-bubble-app --app-version test
bubble-mcp profile list
```

You can also store the editor URL:

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url "https://bubble.io/page?id=my-bubble-app" \
  --app-version test
```

## 4. Capture The Bubble Session

```bash
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 180
```

The command opens a local Chromium window. Log in to Bubble and keep the editor
tab open until the terminal prints:

```text
[bubble-mcp session] Session cookies detected. You can close the browser now; the CLI will save the newest captured session.
```

After that message appears, it is safe to close the browser. The final output is
a redacted JSON result.

Inspect the saved session without printing cookies:

```bash
bubble-mcp session list
bubble-mcp session inspect --profile my-app
```

Manual session import remains available for advanced workflows:

```bash
bubble-mcp session import --profile my-app --file ./bubble-session.json
```

## 5. Detect Project Context

Context detection is required before reliable page, reusable, style, workflow,
data type, or element resolution.

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --force
```

If your app uses a specific Bubble branch/version:

```bash
bubble-mcp context detect \
  --profile my-app \
  --app-id my-bubble-app \
  --app-version test \
  --force
```

Detected artifacts stay local under:

```text
~/.config/bubble-mcp/contexts/{profile}/
```

Refresh context after creating or changing app structure outside this MCP, or
when an agent cannot resolve a visible Bubble name.

## 6. Verify Readiness

Check profile, session, and context readiness:

```bash
bubble-mcp profile status --profile my-app
```

Run the compact MCP readiness gate:

```bash
bubble-mcp readiness --profile my-app --context index --parent root
```

The profile is ready when `profile status` reports `ready: true` and readiness
checks pass. If setup is incomplete, the JSON output includes `next_actions`.

## 7. Connect An MCP Client

For Codex or another MCP client, prefer launching the stdio server through the
virtualenv Python:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/python",
      "args": ["-m", "bubble_mcp.server.stdio"],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

The console script form is also supported:

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

After connecting, ask naturally and reference the profile name:

```text
Using befree-bubble-mcp with profile my-app, create a page called mcp-01.
```

Agents should call `bubble_profile_status` and `bubble_task_runbook` instead of
asking users to memorize internal tool names.
