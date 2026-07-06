# Consultative Learning

Consultative learning records are local, append-only notes that capture user-confirmed preferences, project observations, or extension-specific guidance. They are meant to inform future planning and review, not to silently change runtime behavior.

## Storage

Records are stored as JSONL under the local Bubble MCP config directory:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/learning/records.jsonl
```

Each call appends one record. Existing records are not rewritten during normal use.

## Record Shape

A record contains:

```json
{
  "id": "generated-uuid",
  "scope": "project",
  "key": "naming.page_language",
  "value": {"language": "pt-BR"},
  "source": "user_declared",
  "confidence": "confirmed",
  "created_at": "2026-07-04T00:00:00Z",
  "project": "client-app"
}
```

Required fields:

- `scope`: one of `global`, `profile`, `project`, or `extension`.
- `key`: stable dotted identifier such as `naming.page_language` or `workflow.preview_required`.
- `value`: JSON object with the consultative payload.
- `source`: provenance such as `user_declared`, `operator_reviewed`, or `capture_review`.
- `confidence`: label such as `confirmed` or `tentative`.

Scope-specific fields:

- `profile` scope requires `profile`.
- `project` scope requires `project`.
- `extension` scope requires `extension_id`.

## CLI Usage

Append or import a reviewed record:

```bash
bubble-mcp learning record \
  --scope project \
  --project client-app \
  --key naming.page_language \
  --value '{"language":"pt-BR"}' \
  --source user_declared \
  --confidence confirmed
```

List all records:

```bash
bubble-mcp learning list
```

Filter by scope:

```bash
bubble-mcp learning list --scope project --project client-app
bubble-mcp learning list --scope profile --profile smoke
bubble-mcp learning list --scope extension --extension-id local.simple-pack
```

The `--value` argument accepts either JSON object text or a path to a JSON object file.

### Export And Import Boundary

This branch implements append and list operations, not a bulk sync protocol. Practical export is a read-only JSON response from `bubble-mcp learning list`, or a direct copy of the local `learning/records.jsonl` file when the operator controls the config directory. Practical import is explicit replay through `bubble-mcp learning record` for each reviewed record.

Do not auto-sync learning records to a remote service. Any future bulk export/import command must be explicit, preserve scopes, and keep sensitive project details out of shared artifacts.

## MCP Usage

Append or import a reviewed record:

```json
{
  "tool": "bubble_learning_record",
  "arguments": {
    "scope": "project",
    "project": "client-app",
    "key": "naming.page_language",
    "value": {"language": "pt-BR"},
    "source": "user_declared",
    "confidence": "confirmed"
  }
}
```

List records:

```json
{
  "tool": "bubble_learning_list",
  "arguments": {
    "scope": "project",
    "project": "client-app"
  }
}
```

MCP clients should treat `bubble_learning_list` as the current export surface and `bubble_learning_record` as the current import/append surface. There is no automatic background import or export.

## Safety Boundaries

Learning is consultative in this release:

- Recording a preference does not alter planner decisions automatically.
- Listing records is read-only.
- Records do not grant permission to execute Bubble writes.
- Mutations still require normal profile readiness, preview, validation, and explicit `execute=true`.
- Sensitive values should not be placed in `value`, `key`, `source`, or `confidence`.
- Cross-project transfer must treat records as advice. Agents must separate confirmed record content from inferred guidance when using it in docs, plans, or reviews.
