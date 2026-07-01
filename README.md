# Befree Bubble MCP

Local-first Bubble automation toolkit for developers who want safer, more accurate agent-assisted Bubble work.

This project is being extracted from Befree/Aria as a standalone open source platform. The first target is a practical developer workflow:

```bash
pipx install befree-bubble-mcp
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
bubble-mcp profile list
bubble-mcp-server
```

## What This Will Include

- Bubble-focused CLI.
- MCP server for agent clients.
- Local-only session capture interfaces.
- Context engine from `.bubble` exports and crawler artifacts.
- Planner and semantic validator.
- HTML-to-Bubble converter.
- Figma bridge/plugin workflow.
- Harness and eval tools for improving routing accuracy and reducing token usage.

## Safety Defaults

- No real project data is included in this repository.
- Mutating examples should default to dry-run.
- Session credentials stay local and volatile by default.
- Sensitive values are redacted before logs or reports.

## Status

Early bootstrap. APIs and commands are expected to change before the first alpha.
