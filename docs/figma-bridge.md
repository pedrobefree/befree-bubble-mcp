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

`BUBBLE_MCP_CONFIG_DIR` is optional. When it is not set, the bridge reads the
default `~/.config/bubble-mcp/settings.json`, matching the Python CLI/MCP
server. The value supports `~` expansion. Use a real path for your machine, for
example `~/.config/bubble-mcp`; `/Users/me/...` is only placeholder text.

`GET /profiles` returns the profile names, default profile, raw profile details,
and the resolved `config_dir` / `settings_path` used by the bridge. If the Figma
plugin reports no profiles, check these two fields in the response or plugin log
first; they should point to the same settings file used by `bubble-mcp profile
list`.

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
