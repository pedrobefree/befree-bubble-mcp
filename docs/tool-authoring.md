# Tool Authoring

The tool-authoring foundation groups captured Bubble editor writes so future
flows can turn repeated operations into declarative tools. In v1 it is a local
classification workflow only.

## What Sessions Do

Tool-authoring sessions:

- store an intent, target, profile, and list of capture files;
- copy captured write JSON files into the local config directory;
- reject unsafe session ids, symlink captures, malformed JSON, and captures
  without Bubble editor write changes;
- classify captured write payloads with the existing expert-capture classifier;
- aggregate classifications across captures in a session.

Session data stays under
`BUBBLE_MCP_CONFIG_DIR/tool-authoring/sessions`, or
`~/.config/bubble-mcp/tool-authoring/sessions` by default.

## What Sessions Do Not Do

The foundation does not:

- generate tool schemas;
- activate extension packs;
- replay captured writes;
- execute Bubble writes;
- upload captures;
- export learning records or tool candidates automatically.

Future generation, export, activation, or replay flows must be explicit user
actions and must pass through extension-pack validation, normal preview-first
mutation behavior, and existing profile/session/context gates.

## Commands

```bash
bubble-mcp tool-wizard start \
  --intent "Create an API Connector call" \
  --target api-connector \
  --profile my-app

bubble-mcp tool-wizard add-capture toolwiz_20260704_api_connector_abcd1234 \
  --file ./api-connector-write-capture.json

bubble-mcp tool-wizard describe toolwiz_20260704_api_connector_abcd1234
```

MCP clients can use:

- `bubble_tool_wizard_start`
- `bubble_tool_wizard_add_capture`
- `bubble_tool_wizard_describe`
- `bubble_manual_context_for_tool_authoring`
