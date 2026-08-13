# Context Alias Registry Design

## Context

Stage 4.1 extracted durable JSON persistence from `BubbleCLI`. Stage 4.2 now
extracts the profile-scoped registry stored inside that cache: context aliases,
element aliases, workflow aliases, and their lifecycle operations.

## Decision

Add `aria_runtime/context_alias_registry.py` with `ContextAliasRegistry`.
The registry receives callbacks for the current cache mapping, disk reload,
atomic save, transactional mutation, lookup normalization, and path
normalization. Callbacks keep the registry independent from `BubbleCLI` while
ensuring it sees cache dictionaries replaced after another MCP/CLI subprocess
writes to disk. Production mutations run through a cache-store transaction that
holds an inter-process sidecar lock across reload, mutation, and atomic save.

`BubbleCLI` retains every existing method as a compatibility facade. Public MCP
tool names, schemas, annotations, aliases, routing, outputs, preview defaults,
and confirmation gates remain unchanged.

## Responsibilities

The registry owns:

- canonical profile-cache creation and repair;
- typed access to `option_sets`, `user_types`, `app_texts`, `events`,
  `workflow_refs`, `element_refs`, `components`, and `contexts` buckets;
- context aliases keyed by normalized name, context key, and object ID;
- element aliases scoped by `<context_type>:<context_id>` with path/key
  enrichment and cross-process reload-before-write behavior;
- workflow aliases using the same scope and deterministic millisecond clock;
- removal by context/name/object ID, element ID/key/path, workflow ID/key/name,
  and complete context scope.

The registry does not resolve Bubble objects, traverse discovery data,
materialize cached element stubs, parse traffic capture files, or implement
`inspect_context`/`resolve_refs`. Those stay in `BubbleCLI` until Stage 4.3.

## Interface

```python
class ContextAliasRegistry:
    def __init__(
        self,
        *,
        cache: Callable[[], MutableMapping[str, Any]],
        profile_key: Callable[[], str],
        normalize: Callable[[Any], str],
        normalize_path: Callable[[Any], list[str]],
        reload: Callable[[], None],
        save: Callable[[], None],
        transaction: Callable[[Callable[[], bool]], bool] | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None: ...

    def profile_cache(self) -> dict[str, Any]: ...
    def bucket(self, name: str) -> dict[str, Any]: ...
    def cache_context(...) -> bool: ...
    def lookup_context(token: str) -> tuple[str | None, str | None]: ...
    def cache_element(...) -> bool: ...
    def cache_created_elements(...) -> int: ...
    def lookup_element_id(...) -> str | None: ...
    def lookup_element_payload(...) -> dict[str, Any] | None: ...
    def cache_workflow(...) -> bool: ...
    def lookup_workflow(...) -> dict[str, Any] | None: ...
    def remove_context_aliases(...) -> int: ...
    def remove_element_aliases(...) -> int: ...
    def remove_workflow_aliases(...) -> int: ...
    def remove_context_scope(...) -> bool: ...
```

Mutation methods return whether/how many records changed so the facade can
avoid unnecessary disk writes. Lookups return defensive copies so callers
cannot mutate persisted registry state without an explicit registry operation.

## Compatibility Semantics

- Context lookup checks reusable aliases before page aliases, preserving the
  current ambiguity rule.
- Empty aliases and identifiers are rejected without saving.
- Re-caching an element preserves an existing key/path when the new call omits
  them.
- Element ID lookup continues accepting legacy string payloads.
- Context, element, and workflow writes and removals execute as locked
  read-modify-write transactions to prevent lost updates across subprocesses.
- Context-scope removal handles both modern scoped dictionaries and historical
  flat workflow/event keys.
- Aliases remain profile-isolated under `schema.profiles.<profile>`.

## Testing

Filesystem-free unit tests use real dictionaries and literal expectations for
normalization, profile repair, ambiguity precedence, enrichment, defensive
copies, cross-process replacement, legacy payloads, timestamp injection, and
all removal selectors. Integration tests instantiate a real `BubbleCLI` with a
temporary cache file and verify existing alias tools/facades across independent
instances. Barrier-controlled spawned processes verify that concurrent writes
and removal-versus-write interleavings preserve both operations.

Target focused combined branch coverage is at least 95%. The final gate remains
the complete Python/Node suites, sharded global coverage, Ruff, MyPy, package
and setup smokes, catalog parity/quality, runtime coverage, agent routing, and
independent review.

## Alternatives

1. A mixin would move lines but retain implicit mutable state and poor unit
   boundaries.
2. Extracting discovery resolution with storage would introduce circular
   dependencies and make alias persistence impossible to test independently.
3. The selected callback-backed registry isolates persistence semantics now and
   supplies a clean dependency for Stage 4.3 resolution services.

## Success Criteria

- Existing alias and context behavior is unchanged at every `BubbleCLI` facade.
- Registry focused coverage is at least 95%.
- Concurrent CLI/MCP instances do not overwrite newly written element or
  workflow aliases from another process.
- Tool/catalog counts and routing evaluations remain unchanged.
- The global coverage ratchet only increases with at least 0.1 point headroom.
