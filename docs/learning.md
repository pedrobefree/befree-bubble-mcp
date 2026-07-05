# Learning

Learning records are local, append-only hints that can make planning and
documentation more useful without changing the safety model.

## Scope

Learning records use one of four scopes:

- `global`: applies across local Bubble MCP usage.
- `profile`: applies to one local profile and requires `profile`.
- `project`: applies to one Bubble project and requires `project`.
- `extension`: applies to one extension pack and requires `extension_id`.

Records are stored at
`BUBBLE_MCP_CONFIG_DIR/learning/records.jsonl`, or
`~/.config/bubble-mcp/learning/records.jsonl` by default.

## Behavior

Learning records are consultative. They may inform planning, ranking, warnings,
and documentation, but they cannot:

- execute writes;
- bypass extension, semantic, structural, profile, session, or context
  validation;
- change the default `execute=false` behavior for mutating tools;
- auto-confirm destructive actions.

Exporting learning records is not part of the foundation. Any future export must
be an explicit export flow, not an automatic sync or remote upload.

## Commands

```bash
bubble-mcp learning record \
  --scope project \
  --project my-bubble-app \
  --key "privacy-rule-note" \
  --value '{"summary":"Check privacy rules before migration."}' \
  --source "manual-review" \
  --confidence "medium"

bubble-mcp learning list --scope project --project my-bubble-app
```

MCP clients can use `bubble_learning_record` and `bubble_learning_list`.
