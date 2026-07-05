# Knowledge Sources

The Bubble manual knowledge cache is local-first. It gives agents concise
official-docs guidance while keeping project state and sensitive values local.

## V1 Cache

`bubble_knowledge_refresh_source` imports normalized local JSONL records into a
named source cache. The CLI equivalent is:

```bash
bubble-mcp knowledge refresh-source \
  --source bubble_manual_gitbook \
  --file ./bubble-manual-records.jsonl
```

Records are stored under
`BUBBLE_MCP_CONFIG_DIR/knowledge/<source>/records.jsonl`, or the same path under
`~/.config/bubble-mcp` by default.

Search, fetch, and guidance calls read the local cache only:

```bash
bubble-mcp knowledge search "API Connector authentication"
bubble-mcp knowledge fetch "bubble-manual:data-types:privacy"
bubble-mcp knowledge guidance "privacy rules migration"
```

MCP clients can use:

- `bubble_knowledge_refresh_source`
- `bubble_knowledge_search`
- `bubble_knowledge_fetch`
- `bubble_knowledge_guidance`
- `bubble_manual_context_for_tool_authoring`

## Remote Fallback

A remote GitBook MCP fallback is planned behind the same knowledge interface.
That fallback is not enabled in v1. Before it is enabled, remote queries must be
sanitized so app ids, client ids, authorization headers, bearer tokens, and
opaque project-sensitive values are removed.

## Authority Boundary

Official Bubble docs guidance is advisory. It can explain Bubble platform
concepts, constraints, and recommended usage, but it never proves the current
project state.

Use local profile status, captured session metadata, detected context, mutation
overlays, and fresh Bubble reads to confirm the actual app structure before
planning or executing project-specific changes.
