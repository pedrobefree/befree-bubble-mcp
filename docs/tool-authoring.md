# Tool Authoring

The guided tool wizard is the local capture and classification layer for turning reviewed Bubble editor writes into future declarative tools. It does not generate, enable, execute, or publish tools by itself.

## Workflow

1. Start a local authoring session with an intent, target, and profile. The new
   session is automatically marked as the active Chrome extension capture target.
2. The dev opens the Bubble editor, enables the Chrome companion, and performs
   the actions that should teach the new tool.
3. When the dev returns and says the capture is finished, finalize the same
   session. Finalization returns what was learned, which questions still need
   answers, and how to test the future extension tool.
4. Generate a candidate declarative extension pack from the same session.
5. Validate the extension pack before import.
6. Import and enable only after preview-oriented tests pass.

## CLI Usage

Start a session:

```bash
bubble-mcp tool-wizard start \
  --intent "Create an API Connector call" \
  --target api_connector \
  --profile client
```

Starting a session also marks it as the active Chrome extension capture target.
The session id returned by `start` is the same id to use when the dev returns
after finishing the browser/editor actions.

To switch an existing session back to active as a recovery action:

```bash
bubble-mcp tool-wizard activate toolwiz_20260704_api_connector_ab12cd34
```

Add a captured write:

```bash
bubble-mcp tool-wizard add-capture \
  toolwiz_20260704_api_connector_ab12cd34 \
  --file ./captures/api-connector-write-capture.json
```

Describe the session:

```bash
bubble-mcp tool-wizard describe toolwiz_20260704_api_connector_ab12cd34
```

Finalize after the dev finishes the editor actions:

```bash
bubble-mcp tool-wizard finalize toolwiz_20260704_api_connector_ab12cd34
```

Finalize and generate the candidate pack in the same command:

```bash
bubble-mcp tool-wizard finalize toolwiz_20260704_api_connector_ab12cd34 --generate-pack
```

Generate the candidate extension pack:

```bash
bubble-mcp tool-wizard generate toolwiz_20260704_api_connector_ab12cd34
```

By default the generated pack is written under:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/tool-authoring/generated-packs/<extension-id>/
```

Use `--extension-id`, `--tool-name`, and `--output-dir` only when a stable pack id,
tool name, or artifact location is needed.

## MCP Usage

Start:

```json
{
  "tool": "bubble_tool_wizard_start",
  "arguments": {
    "intent": "Create an API Connector call",
    "target": "api_connector",
    "profile": "client"
  }
}
```

The response includes the generated `session.id`; the agent should keep that id
and use it directly when finalizing.

Add capture:

```json
{
  "tool": "bubble_tool_wizard_add_capture",
  "arguments": {
    "session_id": "toolwiz_20260704_api_connector_ab12cd34",
    "file": "./captures/api-connector-write-capture.json"
  }
}
```

Describe:

```json
{
  "tool": "bubble_tool_wizard_describe",
  "arguments": {
    "session_id": "toolwiz_20260704_api_connector_ab12cd34"
  }
}
```

Finalize:

```json
{
  "tool": "bubble_tool_wizard_finalize",
  "arguments": {
    "session_id": "toolwiz_20260704_api_connector_ab12cd34"
  }
}
```

`bubble_tool_wizard_finalize` is the normal return point after the dev finishes
the browser/editor capture. By default it returns the learned patterns, pending
questions, and testing guidance for the next step. If the user wants to proceed
immediately, pass `generate_pack=true` to generate the candidate extension pack
in the same MCP call.

Finalize and generate:

```json
{
  "tool": "bubble_tool_wizard_finalize",
  "arguments": {
    "session_id": "toolwiz_20260704_api_connector_ab12cd34",
    "generate_pack": true
  }
}
```

Generate:

```json
{
  "tool": "bubble_tool_wizard_generate",
  "arguments": {
    "session_id": "toolwiz_20260704_api_connector_ab12cd34"
  }
}
```

The response includes `pack_path`, `extension_id`, `tool_name`, validation
results, and `next_mcp_calls` for `bubble_extension_validate`,
`bubble_extension_import`, `bubble_extension_enable`, and preview through
`bubble_extension_call`.

## Capture Input

Capture files must be JSON objects and must contain a Bubble editor write body with a `changes` array. Accepted locations inside the object include:

- `payload`
- `write_payload`
- `body`
- `request.payload`
- `request.body`

Example:

```json
{
  "request": {
    "endpoint": "/appeditor/write",
    "body": {
      "appname": "synthetic-app",
      "app_version": "test",
      "changes": [
        {
          "intent": {"name": "CreateApiConnectorCall"},
          "path_array": ["plugins", "api_connector", "calls", "call_123"],
          "body": {
            "name": "Get Products",
            "method": "GET",
            "url": "https://api.example.invalid/products",
            "authentication": "[REDACTED]"
          }
        }
      ]
    }
  }
}
```

Symlink capture files are rejected. Session ids and copied capture filenames must be safe path segments.

## Classification

Each added capture is classified with the same expert payload classifier used by the eval export path. The wizard reports:

- change count;
- captured app/app version when present;
- intent names and Bubble path families inferred from the write body;
- aggregate classification across all captures in the session.

Classification is evidence for tool design. It is not an executable plan and does not replay the captured write.

## Expected Extension Payload

A reviewed session can inform an extension tool like:

```json
{
  "name": "local.api-pack.create_api_connector_call",
  "description": "Create one reviewed API Connector call template.",
  "risk": "mutating",
  "inputSchema": {
    "type": "object",
    "properties": {
      "profile": {"type": "string"},
      "context": {"type": "string"},
      "call_name": {"type": "string"},
      "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
      "url": {"type": "string"},
      "execute": {"type": "boolean", "default": false}
    },
    "required": ["profile", "context", "call_name", "method", "url"]
  },
  "annotations": {
    "readOnlyHint": false,
    "destructiveHint": false,
    "idempotentHint": false,
    "openWorldHint": true
  },
  "template": {
    "kind": "appeditor_write",
    "family": "api_connector",
    "requiresValidation": true
  }
}
```

Expected preview response shape:

```json
{
  "ok": true,
  "execute": false,
  "validation": {"ok": true},
  "write_payload": {
    "endpoint": "/appeditor/write",
    "body": {"changes": []}
  },
  "next_user_action": "Review preview and rerun with execute=true only if the write is correct."
}
```

Expected executed response shape:

```json
{
  "ok": true,
  "execute": true,
  "operation_snapshot": {
    "phase": "executed",
    "next_user_action": "Refresh context before depending on the new Bubble object."
  }
}
```

## Safe Test Workflow

Use this order for a new candidate tool:

1. Capture a real write only from a profile where the operator intends to inspect the request.
2. Redact credentials, tokens, private URLs, and client data before storing examples.
3. Start a tool wizard session and add captures.
4. Search local manual guidance with `bubble_manual_context_for_tool_authoring` or `bubble-mcp knowledge guidance`.
5. Generate the declarative extension pack with `bubble_tool_wizard_generate`; generated tools keep `execute` defaulting to `false`.
6. Run `bubble-mcp extension validate --path <pack_path>` or call `bubble_extension_validate` with the returned `pack_path`.
7. Import and enable in a temporary `BUBBLE_MCP_CONFIG_DIR`.
8. Confirm the enabled tool appears in `tools/list` or `bubble-mcp tools coverage`.
9. Call the enabled tool once with `execute=false`, directly when the client exposes it or through `bubble_extension_call` when it only appears in the catalog, and confirm v1 returns a preview without writing to Bubble.
10. Confirm `execute=true` returns `extension_tool_execution_not_implemented`.
11. Add execution smoke tests only after a future recipe/template runner exists; real `execute=true` must remain limited to an explicit smoke profile and reviewed validation evidence.

The wizard is intentionally conservative. It helps organize evidence; it does not convert captured writes into trusted automation without review.
