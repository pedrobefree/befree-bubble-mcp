# Befree Bubble MCP

Local-first Bubble automation toolkit for developers who want safer, more accurate agent-assisted Bubble work.

This project is being extracted from Befree/Aria as a standalone open source platform. The package is installable and exposes a stdio MCP server with local profiles, context tools, planning tools, and authenticated Bubble editor write execution:

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
- Full Aria Bubble MCP tool catalog exposed over MCP.
- Local profile management.
- Compact context loading, search, and import from `.bubble`/consolelog or crawler-index JSON.
- Deterministic planner and semantic validator.
- HTML-to-Bubble import: conservative plan converter plus Aria's advanced `create-from-html` runtime.
- Local session import/listing for Bubble editor credentials.
- Authenticated `/appeditor/write` execution through CLI and MCP.
- Compiler for basic `create_text` and `create_group` plans into executable Bubble write payloads.
- Browser-assisted session login through optional Playwright support.
- Eval harness for deterministic routing.
- Local Figma bridge for the Befree Figma plugin. Figma-side integration code is intentionally outside this repository.

## Planned Capabilities

- Context engine from `.bubble` exports and crawler artifacts.
- Richer planner and semantic validator ported from Aria.
- Richer Bubble payload compilation for generated visual/schema/workflow plans.

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

## Figma Bridge

Start the local bridge from the repository clone when using the Befree Figma plugin:

```bash
BUBBLE_MCP_CONFIG_DIR=/Users/me/.config/bubble-mcp npm run figma:bridge
```

The bridge listens on `http://localhost:3333`, exposes `/health`, `/profiles`,
and `/sync`, saves incoming plugin payloads under `tmp/bridge_data`, and runs
the Aria-derived Figma-to-Bubble runtime through the local Bubble session before
returning success.

## Safety Defaults

- No real project data is included in this repository.
- Mutating commands require a local session and explicit `execute=true`/`--execute`.
- Without execution opt-in, write commands preview the normalized request.
- Session credentials stay local.
- Sensitive values are redacted before logs or reports.

## Status

Early alpha. Real Bubble editor writes are supported when you provide a valid local session and an exact Bubble `/appeditor/write` payload. Generated plans that do not yet contain a `write_payload` are previewable but not automatically applied.
