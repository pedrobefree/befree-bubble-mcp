# Stage 4.3 — Task 1 report

## Scope delivered

- Added `ContextReferenceResolver` as the typed host boundary for cached stub
  materialization, capture-path normalization, and capture alias import.
- Kept `BubbleCLI` as the compatibility surface. Its existing
  `_materialize_cached_element_stub`, `_normalize_capture_path`, and
  `sync_element_ref_cache` signatures now delegate without changing CLI or MCP
  call sites.
- Kept durable cache ownership in Stage 4.1 and alias persistence ownership in
  Stage 4.2: the resolver only calls `ContextAliasRegistry.cache_element` for
  discovered aliases and never opens or writes the CLI cache file.

## TDD evidence

1. Added the resolver behavioral tests before creating the production module.
2. Ran:

   ```sh
   ./.venv/bin/python -m pytest tests/unit/test_context_reference_resolver.py -q
   ```

   RED result: collection failed with the expected
   `ModuleNotFoundError: No module named 'bubble_mcp.aria_runtime.context_reference_resolver'`.
3. Implemented the minimal resolver and BubbleCLI facades.
4. The focused suite then passed.

## Behavioral coverage

- Cached canonical `%el` paths build only missing ancestors and preserve
  existing siblings.
- Page and reusable contexts materialize from either readable roots or raw
  `%p3` / `%ed` roots.
- Non-list, incomplete, and non-canonical cached paths return the original
  payload unchanged.
- Mixed editor-capture rows skip malformed entries without preventing valid
  name and `CreateElement` aliases from reaching the registry.
- A real `BubbleCLI` test verifies cached materialization and capture-path
  normalization continue through the compatibility facades.

## Validation

Passed:

```sh
./.venv/bin/python -m pytest tests/unit/test_context_reference_resolver.py tests/unit/test_context_alias_registry.py tests/unit/test_runtime_sdk_path_discovery.py -q
# 92 passed

./.venv/bin/ruff check src/bubble_mcp/aria_runtime/context_reference_resolver.py tests/unit/test_context_reference_resolver.py
# All checks passed

./.venv/bin/mypy src/bubble_mcp/aria_runtime/context_reference_resolver.py
# Success: no issues found in 1 source file

git diff --check
# clean
```

The focused resolver test suite is 11 passed. A broad Ruff run against
`bubble_cli.py` reports 508 pre-existing violations, including the established
post-`sys.path` import pattern; none are introduced by this task. The
resolver-only branch coverage snapshot is 72.7%. The design's 95% target is
for the completed resolver after the remaining ownership families and their
tests are extracted, not this Task 1 subset.
