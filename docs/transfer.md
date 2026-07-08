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
- `reuse_policy`: `prefer_existing`, `exact_only`, or `create_new`.
- `collection_policy`: `skip`, `map_existing`, `create_missing`, or
  `replace_schema`.
- `api_connector_policy`: `skip`, `map_existing`, or `structure_only`.
- `data_records_policy`: `skip`, `export_manifest_only`, or
  `data_api_import_preview`.

`reuse_policy=prefer_existing` is the default. It first maps exact target
resources, then reuses structurally compatible target resources when the source
and target context contain enough non-secret metadata to compare them. This is
intended for styles, option sets, API Connector calls, colors, fonts, assets,
and plugins, so a transfer can reuse an equivalent target resource instead of
duplicating it. Use `exact_only` when only same-key/same-label mappings should
be accepted, or `create_new` when the migration must create a fresh copy even if
the target already has a compatible resource.

API Connector transfer never copies secrets. Shared headers, call definitions,
and parameter structure can be mapped or recreated, but credentials must be
reviewed and re-entered by the project owner.

`conflict_policy` is applied before payload compilation:

- `fail` blocks the plan when the target page/reusable shell or target root
  element name already exists.
- `rename` creates a non-conflicting name by adding `_copy`, `_copy_2`, and so
  on.
- `reuse_existing` can reuse an existing target page or reusable shell as the
  destination context. Updating an existing element subtree in place is not
  implemented yet, so element-name conflicts still block with a clear reason.
- `replace` remains blocked for existing targets until a dedicated destructive
  confirmation path exists.

## Current Limits

- Element subtree payloads are supported for transfer execution. Page and
  reusable transfers create a target shell automatically when `target_context`
  is omitted.
- Collection schema can generate data type, field, option set/value, and
  privacy rule target payloads when `collection_policy=create_missing`.
- API Connector structures can generate target payloads for collections and
  calls, but credentials/secrets are never copied and must be re-entered by the
  project owner.
- Live database record migration is not executed by default.
- Successful Bubble write responses must still be verified with refreshed
  context or the Bubble editor.

## Technical Evolution Plan

The transfer module should evolve toward deterministic project-to-project
copies without changing the current safety limits: API Connector secrets are
not copied, and live database records are not migrated by default.

Implementation order:

1. Deep-remap copied element payloads.
   - Use `dependency_decisions` as the only authority for cross-project
     replacement.
   - Replace source dependency keys, labels, and Bubble ids with the mapped or
     reused target references.
   - Replace source element ids inside copied properties with the newly created
     target element ids.
   - Leave unresolved values unchanged when the plan intentionally skips or
     creates later resources.
2. Enforce conflict policies consistently.
   - `fail` blocks conflicting target resources.
   - `rename` creates non-conflicting target names.
   - `reuse_existing` maps compatible existing resources.
   - `replace` remains explicit and must not silently delete or overwrite
     destructive structures.
3. Add first-class dependency compilers where they are safe.
   - Create missing styles, colors, fonts, option sets, data schema resources,
     and API Connector structure when the selected policy allows it.
   - Keep plugin installation and API credentials as manual review items unless
     Bubble exposes safe, non-secret editor operations for them.
4. Add asset staging only after there is a reliable upload path.
   - Until then, `reference_url` and `skip` remain the safe asset policies.
   - `stage_and_upload` should either perform a real upload or block with a
     clear reason; it must not pretend assets were copied.
5. Add post-execute verification.
   - Refresh target context after execution.
   - Verify created shells, element counts, schema resources, API Connector
     structures, and remapped dependency references.
   - Return missing artifacts as actionable warnings, not as a generic success.
6. Add cross-project smoke coverage.
   - Run source-to-target transfer with two real profiles.
   - Verify through refreshed context and editor-visible artifacts.
   - Keep synthetic unit fixtures for deterministic regression coverage.
