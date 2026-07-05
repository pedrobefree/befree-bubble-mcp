# Knowledge Sources

Knowledge sources provide local, source-attributed Bubble manual context for planning, validation, and tool authoring. The current implementation is cache-only: no CLI or MCP knowledge call reaches out to remote documentation.

## Local Bubble Manual Cache V1

The v1 cache stores normalized JSONL records under:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/knowledge/<source>/records.jsonl
```

Use `bubble_manual_gitbook` as the source id for cached Bubble manual records:

```bash
bubble-mcp knowledge refresh-source \
  --source bubble_manual_gitbook \
  --file ./bubble-manual-records.jsonl
```

Each imported record includes provenance and freshness metadata:

```json
{
  "id": "bubble-manual:api-connector:authentication",
  "source": "bubble_manual_gitbook",
  "source_url": "https://manual.bubble.io/core-resources/api/the-api-connector",
  "title": "API Connector authentication",
  "section_path": ["APIs", "API Connector"],
  "content": "Official cached guidance text.",
  "summary": "Short source-attributed summary.",
  "tags": ["api_connector", "authentication"],
  "retrieved_at": "2026-07-04T00:00:00Z",
  "content_hash": "sha256:...",
  "ttl_seconds": 604800,
  "license_note": "Official Bubble manual excerpt cached for local developer assistance.",
  "confidence": "official_cached"
}
```

Refreshing a source replaces that source cache. Search and fetch dedupe records globally by `id`; if multiple sources contain the same id, the newest cache file wins, with source name as the deterministic tie-breaker.

## CLI Usage

Search the cache:

```bash
bubble-mcp knowledge search "API Connector authentication" --limit 5
```

Fetch a full record:

```bash
bubble-mcp knowledge fetch bubble-manual:api-connector:authentication
```

Return manual guidance shaped for an agent answer:

```bash
bubble-mcp knowledge guidance "privacy rules migration" --limit 5
```

## MCP Tools

- `bubble_knowledge_refresh_source`: imports normalized local JSONL records into a named source cache.
- `bubble_knowledge_search`: searches cached records and returns source-attributed summaries.
- `bubble_knowledge_fetch`: fetches one full record by id.
- `bubble_manual_guidance`: returns cache-only guidance for planning or explanation.
- `bubble_manual_context_for_tool_authoring`: returns cached context for declarative tool authoring decisions.
- `bubble_manual_context_for_validation`: returns cached context for validation and migration risk review.

All of these tools are local and cache-only in this release. Cache misses return `cache_miss_remote_disabled`.

## Sanitizer

The sanitizer exists for future remote documentation lookup. It removes project-sensitive values while preserving the general documentation topic:

- authorization headers and bearer tokens;
- `client_id` and client id values;
- opaque long tokens;
- app/client/customer/project ids embedded in a query.

The sanitizer does not make remote lookup available by itself. It is a required precondition for any future remote fallback.

## Future Remote GitBook Fallback

A future remote GitBook MCP may be added only as an auxiliary fallback after a local cache miss. The intended order is:

1. Search the local cache.
2. Fetch or return guidance from cached records when available.
3. On cache miss, sanitize the query.
4. Call a remote GitBook MCP only if the user or configured policy permits it.
5. Store or display remote results with source attribution, freshness, and license metadata.

Remote documentation must never become the primary source when an adequate local cached record exists, and it must not receive Bubble app ids, credentials, client ids, bearer tokens, or captured project data.
