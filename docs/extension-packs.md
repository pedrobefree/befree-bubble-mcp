# Extension Packs

Extension packs let the standalone Bubble MCP package load local, declarative
capability descriptions without adding runtime code to the package.

## V1 Boundary

- Packs are declarative JSON files.
- Packs are imported into `pending` state.
- Enabling a pack requires local validation, and enabled schemas are revalidated
  before exposure through the MCP tool catalog.
- No arbitrary Python, Node, shell, or bundled extension code is executed in v1.
- Mutating extension tools must default to `execute=false` and require explicit
  `execute=true` before any Bubble write.
- Tool name collisions with built-in/native tools are rejected.
- Duplicate tool names inside one pack are rejected.
- Likely secrets are rejected during validation.
- Pack files cannot use symlinks or escape the pack directory.
- All pack state is stored under `BUBBLE_MCP_CONFIG_DIR/extensions/packs`, or
  `~/.config/bubble-mcp/extensions/packs` when the environment variable is not
  set.

## Pack Shape

Each pack has an `extension.json` manifest. The manifest identifies the pack and
declares exported assets:

```json
{
  "id": "local.example-pack",
  "name": "Example Pack",
  "version": "0.1.0",
  "bubbleMcpVersion": "0.1.0",
  "capabilities": ["visual"],
  "risk": "mutating",
  "author": "local",
  "exports": {
    "tools": ["tools/create-example.tool.json"],
    "recipes": [],
    "skills": [],
    "evals": []
  }
}
```

The v1 runtime loads declarative tool schemas from enabled packs. Recipes,
skills, and eval exports are reserved contract slots for follow-up work.

## Commands

```bash
bubble-mcp extension validate --path ./my-pack
bubble-mcp extension import --path ./my-pack
bubble-mcp extension list
bubble-mcp extension enable local.example-pack
bubble-mcp extension disable local.example-pack
```

MCP clients can use the equivalent tools:

- `bubble_extension_validate`
- `bubble_extension_import`
- `bubble_extension_list`
- `bubble_extension_enable`
- `bubble_extension_disable`

## Chrome Companion Boundary

The Chrome extension companion is separate from this MCP repository/package. It
must remain local-only, must not use Aria email/password auth, and must not use
an Aria remote relay or auth server.

Its UI should be limited to:

- local service status;
- local event summary;
- local enable/disable key.
