# Context Reference Resolver Design

## Context

Stage 4.1 extracted durable cache persistence and Stage 4.2 extracted the
profile-scoped context, element, and workflow alias registry. The remaining
Family 1 logic in `BubbleCLI` still mixes discovery traversal, cached-element
materialization, editor-capture parsing, reference resolution, and output
formatting with unrelated mutation families.

## Decision

Add `aria_runtime/context_reference_resolver.py` with a
`ContextReferenceResolver`. The resolver receives the current `BubbleCLI` as a
typed host and consumes its discovery boundary and `ContextAliasRegistry`.
It owns read-oriented context/reference behavior but never reads or writes the
cache file directly. Alias mutations discovered while parsing a capture are
performed through the registry exposed by the host.

`BubbleCLI` constructs one resolver after cache and alias initialization and
retains its existing method signatures as compatibility facades. Public MCP
tool names, schemas, aliases, annotations, dispatch routes, preview defaults,
confirmation gates, result shapes, CLI output, and exit semantics remain
unchanged.

## Responsibilities

The resolver owns:

- cached element stub materialization from canonical alias paths;
- capture-path normalization and editor-capture alias extraction;
- page/reusable context enumeration across readable, raw, module, index, and
  alias-cache sources;
- element enumeration, matching, ranking, deduplication, and selection;
- structured context inspection and reference resolution orchestration;
- compatibility rendering for `inspect_context`, `resolve_refs`, and capture
  synchronization.

The resolver does not own:

- cache-file loading, migration, locking, transactions, or atomic writes;
- alias storage, cleanup, or cross-process reconciliation;
- Bubble mutations, payload dispatch, confirmation gates, or tool schemas;
- style, workflow, data-type, or option-set domain rules. It calls their
  existing `BubbleCLI` compatibility methods when `resolve_refs` needs them.

## Interface

```python
class ContextReferenceResolver:
    def __init__(self, host: ReferenceResolverHost) -> None: ...

    def materialize_cached_element_stub(
        self,
        context_id: str,
        context_type: str,
        cached_payload: dict[str, Any] | None,
        alias_name: str | None = None,
    ) -> dict[str, Any] | None: ...

    def normalize_capture_path(self, raw_path: Any) -> list[str]: ...
    def sync_element_ref_cache(...) -> bool: ...
    def iter_contexts(self, scope: str = "all") -> list[dict[str, str]]: ...
    def collect_context_elements(...) -> list[dict[str, Any]]: ...
    def find_elements_by_ref(...) -> list[dict[str, Any]]: ...
    def find_element_by_ref(...) -> dict[str, Any] | None: ...
    def inspect_context(...) -> bool: ...
    def resolve_refs(...) -> bool: ...
```

The host protocol documents every compatibility callback the resolver may use.
Keeping a single typed host avoids a large constructor of loosely related
callbacks while still making coupling visible to static analysis and tests.

## Data Flow

1. A CLI command or MCP dispatcher calls an existing `BubbleCLI` method.
2. The facade delegates to the resolver without rewriting arguments.
3. The resolver reads discovery, module, index, and registry-backed sources.
4. Results are normalized, deduplicated, ranked, and rendered with the existing
   JSON/log contract.
5. Capture synchronization sends alias writes through
   `ContextAliasRegistry.cache_element`; the resolver never persists directly.

## Compatibility and Failure Semantics

- Reusable aliases continue to win over page aliases when names are ambiguous.
- Readable discovery roots and raw `%p3`/`%ed` roots remain equivalent inputs;
  non-mapping preferred roots fall back to valid raw mappings.
- Missing, malformed, or deeply nested capture rows are skipped without
  aborting valid sibling mappings.
- A cached path materializes only its ancestor chain and does not replace an
  existing context or sibling element.
- `match_index` stays one-based and clamps values below one to the first match.
- JSON mode preserves the exact current keys and returns success when a payload
  can be emitted, including a payload containing resolution errors.
- Human-readable mode preserves current log levels and boolean success rules.
- No resolver read is allowed to mutate registry state by reference.

## Testing and Performance

Focused unit tests use real dictionaries and a minimal typed host to cover raw
and readable roots, context ambiguity, malformed buckets, cached-only elements,
capture shapes, duplicate names, exact match ranking, one-based selection,
inspection truncation, mixed successful/failed references, and defensive
payload behavior. Real-`BubbleCLI` tests prove facade and output compatibility.

Record a pre-extraction baseline and a post-extraction `timeit` benchmark for
1,000 context lookups, 1,000 element resolutions, and 100 context inspections.
The extraction must not cause a material regression beyond normal measurement
noise. Focused combined branch coverage for the new module must be at least
95%; the global coverage ratchet may rise only with at least 0.1 percentage
point of headroom.

## Alternatives

1. Utility functions would reduce a few lines but leave ownership and mutable
   dependencies implicit.
2. A fully pure resolver returning new result models would be cleaner in
   isolation but would force broad CLI/MCP output changes during a compatibility
   refactor.
3. The selected typed-host resolver moves ownership now, preserves behavior,
   and leaves result-model cleanup available as a later internal change.

## Success Criteria

- Family 1 discovery/reference behavior is owned by the new resolver.
- Existing `BubbleCLI`, CLI, and MCP contracts remain byte-for-byte compatible
  for deterministic JSON outputs.
- The resolver has at least 95% focused combined branch coverage.
- Full Python and Node suites, catalog parity/quality, runtime coverage, agent
  routing, package/setup checks, Ruff, MyPy, and `git diff --check` pass.
- Benchmarks show no material regression.

