# Bubble CLI Cache Store Design

## Context

Stage 4 of the optimization roadmap decomposes the 75,000-line
`aria_runtime/bubble_cli.py` compatibility runtime. The first bounded slice is
cache persistence because it is initialized before the runtime agents and is
used by profiles, context aliases, styles, colors, fonts, schemas, and later
mutation paths.

## Decision

Introduce `aria_runtime/cli_cache.py` with a focused `BubbleCLICacheStore`.
`BubbleCLI` keeps `_cli_cache`, `_cache_file`, `_legacy_tmp_cache_file`, and its
existing cache methods as compatibility facades. No MCP tool name, schema,
dispatch route, CLI command, or result contract changes in Stage 4.1.

The store owns only local JSON persistence:

- creation of a fresh canonical default payload;
- recursive merge of dictionary payloads;
- tolerant reads of missing, malformed, or non-object JSON;
- atomic writes through a temporary sibling followed by `os.replace`;
- reloads that never replace valid in-memory data with a failed read;
- idempotent clear;
- one-way legacy temp-cache migration.

Context reconciliation, element/workflow aliases, `inspect_context`, and
`resolve_refs` remain in `BubbleCLI` for Stage 4.2 and 4.3.

## Public Internal Interface

```python
def default_cache_payload() -> dict[str, Any]: ...

def merge_cache_payloads(base: Any, incoming: Any) -> Any: ...

class BubbleCLICacheStore:
    def __init__(
        self,
        cache_path: str | os.PathLike[str],
        *,
        legacy_path: str | os.PathLike[str] | None = None,
        warn: Callable[[str], None] | None = None,
    ) -> None: ...

    def load(self) -> dict[str, Any]: ...
    def reload(self, current: Mapping[str, Any]) -> dict[str, Any]: ...
    def save(self, payload: Mapping[str, Any]) -> bool: ...
    def clear(self) -> bool: ...
    def migrate_legacy(self) -> bool: ...
```

`load()` always returns a new normalized dictionary. `reload()` preserves the
current in-memory mapping when the disk file is missing or unreadable. `save()`
and `clear()` return success without raising expected filesystem or serialization errors.
The facade retains its current return types, so `_save_cli_cache()` remains
`None`-returning and `clear_cache()` remains boolean.

## Persistence Semantics

Canonical buckets are `colors`, `fonts`, `styles`, `components`, and
`schema.profiles`. Missing or invalid buckets are repaired during load without
discarding unrelated keys.

Writes serialize completely before replacing the destination. A serialization
or filesystem failure must leave the previous canonical file readable and
remove any temporary file created by the failed attempt.

Legacy migration treats the canonical file as authoritative when both files
contain the same scalar or list. Legacy-only nested data is retained. This
prevents stale temp state from overwriting a newer profile cache. The legacy
file is not deleted in this stage, preserving recovery and downgrade safety.
After the canonical payload is saved, a durable sibling marker records that
the one-way migration completed. Clearing the canonical cache preserves this
marker so a later startup cannot resurrect stale legacy-only entries.

## Compatibility and MCP Boundaries

All 327 MCP tools continue calling the same `BubbleCLI` methods. Existing
agent-facing tool descriptions, required fields, aliases, preview defaults,
and mutation gates remain unchanged. The store is an internal runtime boundary,
not a new broad cache-management tool.

## Test Strategy

Unit tests exercise the real filesystem through `tmp_path` and cover:

- independent defaults and schema repair;
- malformed and non-object JSON;
- recursive merge precedence;
- atomic round trips and failed serialization preserving old data;
- idempotent clear;
- canonical-wins legacy migration;
- facade parity through a real `BubbleCLI` initialized with a temporary app
  context and explicit `BUBBLE_CLI_CACHE_PATH`.

The full Python/Node suites, Ruff, MyPy, package/setup smokes, catalog parity,
runtime coverage, and agent-routing smokes remain the final release gate.

## Alternatives Considered

1. A mixin would shorten `bubble_cli.py` but keep storage coupled to mutable CLI
   state and would not produce a reusable test boundary.
2. Extracting cache, contexts, aliases, and reference resolution together would
   reduce more lines at once but create a high-risk PR with circular dependencies.
3. The selected store-first extraction has the smallest dependency surface and
   makes the next context-registry extraction safer.

## Success Criteria

- `BubbleCLI` cache behavior remains compatible at its existing call sites.
- Store branch coverage reaches at least 95%.
- No partial canonical JSON is observable after a failed write.
- The global coverage ratchet only moves upward and retains at least 0.1 point
  of headroom.
- No tool catalog or routing regression is introduced.
