# Installation

`befree-bubble-mcp` is packaged as a Python project. The console scripts are:

- `bubble-mcp`: local CLI for settings and Bubble profiles.
- `bubble-mcp-server`: stdio MCP server for MCP clients.

The package also contains a small Node package for bridge integrations, but the
current CLI and MCP server are installed from Python.

## Requirements

- Python 3.11 or newer.
- Node.js 20 or newer only when working on bridge integrations.
- A Bubble account and Bubble app id for profile setup.
- An MCP client that can launch stdio servers, such as Codex, Claude Desktop, or
  another compatible client.

## Local smoke install

Use this when testing the package the same way an end user will run it:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install ".[browser]"
python -m playwright install chromium
bubble-mcp --help
```

## Local editable install

Use this when developing from a checkout or testing the package before
publishing while editing source files. For real Bubble smoke tests, prefer the
normal local smoke install above so the console scripts import the packaged
module exactly as an end user will run it.

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python scripts/install_local.py --extras browser
bubble-mcp --help
```

Install development dependencies when running tests or static checks:

```bash
python scripts/install_local.py --extras browser,dev
```

If a previous editable install was interrupted or `bubble-mcp` cannot import
`bubble_mcp`, repair the virtual environment from the checkout without relying
on the broken console script:

```bash
python scripts/install_local.py --repair --extras browser,dev
```

On macOS, the repair command also clears hidden filesystem flags on the virtual
environment, refreshes local console entrypoints through an external copy/move
step that avoids local execution-policy kills, signs native extension modules
with an ad-hoc local signature, and validates the Playwright browser dependency
when the `browser` extra is installed.

## Optional isolated install with pipx

When the package is available to your Python package index, `pipx` can install
the CLI and server into an isolated environment:

```bash
pipx install befree-bubble-mcp
```

For a local checkout, use:

```bash
pipx install .
```

## Configure a Bubble profile

Initialize settings:

```bash
bubble-mcp init
```

This creates `~/.config/bubble-mcp/settings.json` unless
`BUBBLE_MCP_CONFIG_DIR` is set.

Add a profile:

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
```

Optional metadata:

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url "https://bubble.io/page?id=my-bubble-app"
```

Confirm it was saved:

```bash
bubble-mcp profile list
```

Run a local-only coverage smoke after installation:

```bash
bubble-mcp smoke runtime --suite coverage
```

## Capture a Bubble editor session

Create or reuse a profile, then open a browser-assisted login flow:

```bash
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 180
```

Log in to Bubble in the opened browser and wait until the CLI prints the saved
session JSON. If the command is interrupted after cookies were captured, the CLI
will still save the newest usable session. If it is interrupted before login
completes, rerun the command.

## Start the MCP server

Run:

```bash
bubble-mcp-server
```

The command does not open an HTTP port. It is a stdio server that waits for an
MCP client to send JSON-RPC messages over standard input.

For desktop MCP clients, especially on macOS editable installs, prefer the
equivalent module command:

```bash
python -m bubble_mcp.server.stdio
```

## Current implementation status

The MCP server exposes profile, context, planning, session, eval, and write
tools. Mutating tools require a locally imported Bubble editor session. They
preview requests unless the caller passes `execute=true`.
