# Figma Bridge

This repository includes only the local bridge service. It does not include
Figma-side integration code.

Bridge endpoints:

```text
GET /health
GET /profiles
POST /sync
```

By default the bridge listens on `http://localhost:3333`, matching the
existing Befree Figma plugin. Override with
`BUBBLE_MCP_BRIDGE_HOST` and `BUBBLE_MCP_BRIDGE_PORT` when the Figma-side
integration expects a different local endpoint.

The bridge responds to CORS preflight requests so browser-based plugin UIs can
fetch these local endpoints from Figma's iframe environment.

Start it with the same config directory used by the CLI/MCP server:

```bash
BUBBLE_MCP_CONFIG_DIR=/Users/me/.config/bubble-mcp npm run figma:bridge
```

`POST /sync` saves the incoming plugin payload under `tmp/bridge_data` and then
executes the Aria-derived Figma-to-Bubble runtime against the local Bubble MCP
session. The endpoint returns success only after the Bubble writes complete. If
Bubble rejects a write or the session/profile cannot be resolved, the bridge
returns an error to the plugin instead of reporting a false positive.

For component payloads, the bridge uses the exported `.bubble` context and the
ported Aria component sync logic to create or update Bubble reusable definitions,
styles, groups, text, buttons, layout, spacing, shadows, and responsive metadata.
The transport is local: editor writes go through the stored Bubble session, not
through the legacy Aria webhook.
