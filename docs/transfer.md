# Project Transfer

Bubble MCP can plan, preview, and execute transfers from one Bubble project
profile to another. The transfer flow is preview-first and stores local plan
artifacts before any Bubble write.

Use it for:

- Copying a page, reusable, or element subtree between projects.
- Inspecting dependencies before transfer.
- Preparing collection schema and API Connector transfer decisions.

Do not use it for live database record migration yet. Record migration defaults
to `skip`.

## Requirements

Both source and target projects need local profiles and detected context.

```bash
bubble-mcp profile add source-app --app-id source-bubble-app --app-version test
bubble-mcp profile add target-app --app-id target-bubble-app --app-version test

bubble-mcp session login --profile target-app --app-id target-bubble-app --wait-seconds 180

bubble-mcp context detect --profile source-app --app-id source-bubble-app --app-version test --force
bubble-mcp context detect --profile target-app --app-id target-bubble-app --app-version test --force
```

The source profile is read-only during transfer. The target profile needs a
captured session only when previewing or executing writes.

## CLI Flow

Inspect the source object:

```bash
bubble-mcp transfer inventory \
  --source-profile source-app \
  --source-type reusable \
  --source-ref Header
```

Create a local transfer plan:

```bash
bubble-mcp transfer plan \
  --source-profile source-app \
  --target-profile target-app \
  --source-type reusable \
  --source-ref Header \
  --target-context index \
  --target-parent root \
  --target-name Header_copy
```

Preview the plan before writing:

```bash
bubble-mcp transfer preview --transfer-id TRANSFER_ID --include-payloads
```

Execute only after review:

```bash
bubble-mcp transfer execute --transfer-id TRANSFER_ID --execute --confirm
```

Check the stored plan:

```bash
bubble-mcp transfer status --transfer-id TRANSFER_ID
```

Refresh target context after execution:

```bash
bubble-mcp context detect --profile target-app --force
```

## MCP Tools

The same flow is exposed to MCP clients:

- `bubble_transfer_inventory`: read-only source subtree inspection.
- `bubble_transfer_plan`: local transfer plan creation.
- `bubble_transfer_preview`: target-session dry run for an existing plan.
- `bubble_transfer_execute`: real execution; requires `execute=true` and
  `confirm=true`.
- `bubble_transfer_status`: local plan lookup.

Agents should call `bubble_transfer_inventory` before `bubble_transfer_plan`
when the request is broad or the source object may have dependencies.

## Policies

`bubble_transfer_plan` supports these policy fields:

- `conflict_policy`: `fail`, `rename`, `replace`, or `reuse_existing`.
- `asset_policy`: `reference_url`, `stage_and_upload`, or `skip`.
- `dependency_policy`: `map_only`, `map_or_create`, or `skip_optional`.
- `collection_policy`: `skip`, `map_existing`, `create_missing`, or
  `replace_schema`.
- `api_connector_policy`: `skip`, `map_existing`, or `structure_only`.
- `data_records_policy`: `skip`, `export_manifest_only`, or
  `data_api_import_preview`.

API Connector transfer never copies secrets. Shared headers, call definitions,
and parameter structure can be mapped or recreated, but credentials must be
reviewed and re-entered by the project owner.

## Current Limits

- Element subtree payloads are supported for transfer execution.
- Collection schema and API Connector structures are inventoried and mapped in
  the local plan, with conservative execution defaults.
- Live database record migration is not executed by default.
- Successful Bubble write responses must still be verified with refreshed
  context or the Bubble editor.
