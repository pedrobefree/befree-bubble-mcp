# Extension Packs

Extension packs are the local declarative packaging layer for reusable Bubble MCP capabilities. They let a developer install and enable additive tool schemas without editing the core package.

## Install Layout

Imported packs are copied into the Bubble MCP config directory:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/extensions/packs/<extension-id>/
  extension.json
  state.json
  tools/
    *.tool.json
```

The default state after import is `pending`. Enabling or disabling a pack updates `state.json` to `enabled` or `disabled`.

Only enabled packs are exposed through the MCP tool list. Pending and disabled packs remain installed locally but do not add callable tool schemas.

## Manifest

Every pack must include `extension.json` at its root:

```json
{
  "id": "local.simple-pack",
  "name": "Local Simple Pack",
  "version": "0.1.0",
  "bubbleMcpVersion": ">=0.1.0",
  "capabilities": ["tools", "recipes", "skills", "evals"],
  "risk": "mutating",
  "author": "local-user",
  "exports": {
    "tools": ["tools/create-plugin-widget.tool.json"],
    "skills": [],
    "evals": []
  }
}
```

Important fields:

- `id` must be a safe path segment. It cannot be empty, `.`, `..`, or contain `/` or `\`.
- `risk` must be one of `read_only`, `mutating`, or `destructive`.
- `exports.tools` lists JSON files inside the pack. Export paths cannot escape the pack root.
- `capabilities`, `exports.recipes`, `exports.skills`, and `exports.evals` reserve the broader kernel shape even though this release exposes only declarative tool schemas from enabled packs.

## Tool Schema

Exported tools use MCP-compatible JSON schema plus Bubble MCP metadata:

```json
{
  "name": "local.simple-pack.create_plugin_widget",
  "description": "Create a plugin widget through a captured Bubble editor write template.",
  "risk": "mutating",
  "inputSchema": {
    "type": "object",
    "properties": {
      "profile": {
        "type": "string",
        "description": "Local Bubble MCP profile."
      },
      "context": {
        "type": "string",
        "description": "Target page or reusable context."
      },
      "parent": {
        "type": "string",
        "description": "Target parent element id."
      },
      "label": {
        "type": "string",
        "description": "Visible widget label."
      },
      "execute": {
        "type": "boolean",
        "description": "Execute the write after preview and validation.",
        "default": false
      }
    },
    "required": ["profile", "context", "parent", "label"]
  },
  "annotations": {
    "readOnlyHint": false,
    "destructiveHint": false,
    "idempotentHint": false,
    "openWorldHint": true
  },
  "template": {
    "kind": "appeditor_write",
    "family": "plugin_widget",
    "requiresValidation": true
  }
}
```

Tool names must not collide with native Bubble MCP tools or the Aria-compatible catalog. Duplicate enabled extension tool names are filtered to one schema.

## Validation

Validate a pack before import:

```bash
bubble-mcp extension validate --path ./my-extension-pack
```

MCP clients can call:

```json
{
  "tool": "bubble_extension_validate",
  "arguments": {"path": "./my-extension-pack"}
}
```

Validation checks:

- pack root and files are not symlinks;
- exported paths stay under the pack root;
- manifest id and risk are valid;
- exported tool files exist and parse as objects;
- tool names are present, unique inside the pack, and do not collide with existing native/catalog tools;
- exported tool content does not contain obvious secrets such as bearer tokens, API keys, passwords, or secret assignments.

## Import And Enable

CLI flow:

```bash
bubble-mcp extension import --path ./my-extension-pack
bubble-mcp extension list
bubble-mcp extension enable local.simple-pack
bubble-mcp extension disable local.simple-pack
```

MCP tools:

- `bubble_extension_import`
- `bubble_extension_list`
- `bubble_extension_enable`
- `bubble_extension_disable`

Import is idempotent for the same extension id: the local copy is replaced and returned to `pending`. Enable validates the installed pack before changing state; invalid packs remain pending or disabled and return validation errors.

## Preview And Execute Boundary

Extension packs can add validated schemas to the tool catalog, but v1 does not execute those declarative tools yet. If an enabled extension tool is called, the MCP returns an explicit `extension_tool_execution_not_implemented` result instead of treating it as an unknown tool.

Future declarative execution must not bypass the Bubble MCP execution model. Mutating operations must keep an explicit `execute` input with `false` as the safe default. A tool proposal should preview the normalized write first, then require explicit `execute=true` only after semantic and structural validation.

Extension pack validation does not execute Bubble writes. Enabling a pack only exposes schemas; it does not replay captured writes, create elements, or modify a Bubble app.

## Companion Boundary

The Chrome extension companion is shipped in `chrome-extension/` as a browser integration surface for this MCP project. It is separate from declarative extension packs: it is not imported, enabled, validated, or exposed through the extension-pack kernel.

The companion must not use Aria email/password authentication. Browser-side companion auth should be designed independently from Aria application login and should keep Bubble sessions, MCP profile state, and any local tokens under their own explicit security model.
