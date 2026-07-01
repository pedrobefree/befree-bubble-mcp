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

## Local editable install

Use this when developing from a checkout or testing the package before
publishing:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e .
bubble-mcp --help
```

Install development dependencies when running tests or static checks:

```bash
pip install -e ".[dev]"
```

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

## Start the MCP server

Run:

```bash
bubble-mcp-server
```

The command does not open an HTTP port. It is a stdio server that waits for an
MCP client to send JSON-RPC messages over standard input.

## Current implementation status

The MCP server exposes profile, context, planning, session, eval, and write
tools. Mutating tools require a locally imported Bubble editor session. They
preview requests unless the caller passes `execute=true`.
