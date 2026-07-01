# Befree Bubble MCP

Local-first Bubble automation toolkit for developers who want safer, more accurate agent-assisted Bubble work.

This project is being extracted from Befree/Aria as a standalone open source platform. The current package is already installable and exposes a safe dry-run MCP server:

```bash
pipx install befree-bubble-mcp
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
bubble-mcp profile list
bubble-mcp-server
```

## Current Capabilities

- Bubble-focused CLI.
- MCP server for agent clients.
- Local profile management.
- Compact synthetic context loading and search.
- Deterministic dry-run planner and semantic validator.
- Basic HTML-to-Bubble dry-run converter.
- Eval harness for deterministic routing.
- Local Figma bridge skeleton.

## Planned Capabilities

- Full local session capture providers.
- Context engine from `.bubble` exports and crawler artifacts.
- Richer planner and semantic validator ported from Aria.
- Figma bridge/plugin workflow.
- Mutation execution after dry-run, approval, session, and validation gates are in place.

## Codex MCP Setup

Use the installed stdio server in your MCP config:

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

If the client does not inherit your shell path, point `command` to the absolute `bubble-mcp-server` path.

## Safety Defaults

- No real project data is included in this repository.
- Mutating examples should default to dry-run.
- Session credentials stay local and volatile by default.
- Sensitive values are redacted before logs or reports.

## Status

Early alpha. The MCP server is intentionally read-only/dry-run for Bubble operations.
