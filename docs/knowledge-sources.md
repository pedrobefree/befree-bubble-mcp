# Knowledge Sources

Knowledge sources provide source-attributed Bubble documentation and community context for planning, validation, tool authoring, and best-practice answers. Explicit `search` and `fetch` calls read the local cache only. Agent-facing guidance uses a selective `KnowledgeAdvisor`: it searches local cache first and, when a risk/ambiguity/best-practice trigger is present, may fetch a small number of remote official/forum records and store them locally.

## Local Knowledge Cache V1

The v1 cache stores normalized JSONL records under:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/knowledge/<source>/records.jsonl
```

Use `bubble_manual_gitbook` or `bubble_manual` as the source id for cached Bubble manual records:

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

Refreshing a source replaces that source cache. Advisor-fetched remote records are merged into their source cache. Search and fetch dedupe records globally by `id`; if multiple sources contain the same id, the newest cache file wins, with source name as the deterministic tie-breaker.

## Automatic KnowledgeAdvisor

The `KnowledgeAdvisor` is used by agent runbooks, recipes, guidance calls, and manual guidance wrappers. It is automatic only when at least one trigger is detected:

- low routing confidence;
- schema or parameter ambiguity;
- destructive or structural action;
- tool generation/evolution;
- user asks for best practices or documented behavior;
- execution, validation, visual, or materialization failure.

Simple confident tasks do not trigger remote lookup.

When triggered, the advisor:

1. Sanitizes the topic.
2. Searches local cache.
3. If local cache is insufficient and remote lookup is enabled, fetches only likely official documentation pages and Bubble Forum topics.
4. Stores fetched records locally with source, URL, confidence, TTL, content hash, and retrieval time.
5. Returns compact `knowledge_advice` with guidance, warnings, confidence, source mix, and recommended validation steps.

Remote lookup is enabled by default and can be disabled with:

```bash
BUBBLE_MCP_KNOWLEDGE_REMOTE=0
```

No remote lookup runs at startup.

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

`knowledge guidance` uses the advisor. It reads local cache first and may perform selective remote fetch unless `BUBBLE_MCP_KNOWLEDGE_REMOTE=0`.

## MCP Tools

- `bubble_knowledge_refresh_source`: imports normalized local JSONL records into a named source cache.
- `bubble_knowledge_search`: searches cached records and returns source-attributed summaries.
- `bubble_knowledge_fetch`: fetches one full record by id.
- `bubble_manual_guidance`: returns advisor-backed guidance for planning or explanation.
- `bubble_manual_context_for_tool_authoring`: returns advisor-backed context for declarative tool authoring decisions.
- `bubble_manual_context_for_validation`: returns advisor-backed context for validation and migration risk review.

`bubble_knowledge_search` and `bubble_knowledge_fetch` are local cache-only. The `bubble_manual_*` tools may use selective remote fetch when local cache misses and the remote policy allows it.

## Source Policy

Default sources:

- `bubble_manual`: official Bubble Manual pages, discovered through the public sitemap and fetched selectively.
- `bubble_forum`: Bubble Forum topics, queried through Discourse-compatible search/topic endpoints.

Official docs have higher authority for documented behavior. Forum/community records can adjust warnings, recommendations, and validation requirements, especially for undocumented editor behavior, bugs, edge cases, and workarounds. Forum records never silently override official documentation or authorize execution.

## Sanitizer

The sanitizer removes project-sensitive values while preserving the general documentation topic before any remote lookup:

- authorization headers and bearer tokens;
- `client_id` and client id values;
- opaque long tokens;
- app/client/customer/project ids embedded in a query.

Remote documentation must never receive Bubble app ids, credentials, client ids, bearer tokens, session cookies, raw editor payloads, customer data, or captured project data.
