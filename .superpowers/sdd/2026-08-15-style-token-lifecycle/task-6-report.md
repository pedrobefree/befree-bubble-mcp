# Task 6 report — Phase 4.5e style definitions and states

Date: 2026-08-15
Branch: `codex/style-token-lifecycle-4-5e-definitions`
Base: `codex/style-token-lifecycle-4-5d-figma-import`
Implementation commit: `3ccedc2d6e75ba0072b11efaa123597f00df30d4` — `refactor: extract style definition lifecycle`
Draft PR: https://github.com/pedrobefree/befree-bubble-mcp/pull/30

## Outcome

Stage 4.5e is implemented and published as a draft stacked PR. `StyleDefinitionService` now owns definition/state lifecycle orchestration for normalization, create, update, rename, default assignment, button themes, conditional states, transitions, state lookup/order, delete, bulk delete, and clear. SDK `StyleBuilder` wire construction remains unchanged.

`StyleLifecycleService` composes the new service from the stable reference, color, dispatch, cache, and hydration boundaries. `BubbleCLI` keeps the existing public signatures and boolean results as direct delegating facades. HTML import and Figma import remain integration consumers; the Figma importer receives `StyleDefinitionService` through the existing `StyleDefinitionSink` interface.

Mutation ordering is explicit. Cache writes and cleanup happen only after successful dispatch. Multi-stage state mutations dispatch transitions, state creation, and properties in literal order and do not update cache after an earlier failure. Create and update dry runs hydrate discovery explicitly and never persist the CLI cache. Definition failures remain `False` through CLI, HTML, and Figma callers.

## RED/GREEN evidence

### Definition lifecycle service

The initial service test was written before the module existed:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definitions.py -q
ERROR collecting tests/unit/test_style_lifecycle_definitions.py
ModuleNotFoundError: No module named 'bubble_mcp.aria_runtime.style_lifecycle.definitions'
1 failed
```

After adding only normalization, the first minimal GREEN was:

```text
1 passed
```

The expanded lifecycle goldens then failed before orchestration existed:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definitions.py -q
10 failed, 1 passed
```

The first complete service GREEN covered normalization, create/update/rename/default, state transition order, reorder, dispatch failures, dry-run hydration, and delete/bulk/clear cache cleanup:

```text
11 passed
```

Behavior-bearing edge and failure regressions were added during self-review for malformed state trees, each staged dispatch boundary, cache failures, legacy/direct IDs, property matching, popup/uploader defaults, recursive conditions, cache-only button aliases, invalid bulk regex, and dry-run behavior. Final focused result:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definitions.py -q
63 passed in 0.20s
```

### Facades and import consumers

Facade/import regressions were written before `BubbleCLI` and composition wiring:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definition_facades.py -q
3 failed, 2 passed
```

After wiring all definition/state facades and installing the service as the Figma definition sink:

```text
16 passed
```

The regressions prove signature/result parity, helper delegation, unchanged Figma sink identity, HTML/Figma success results, and literal failure propagation.

## Required verification gates

Exact Stage 4.5e lifecycle/import/catalog pytest gate:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_render.py tests/unit/test_style_import_runtime.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
257 passed in 8.15s
```

Catalog audit:

```text
rtk env PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
cli_command_count: 207
direct_match_count: 205
alias_count: 1
missing_count: 0
ok: true
```

Coverage:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage erase
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_figma_bridge.py -q
80 passed in 0.44s

rtk env PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py' --fail-under=95
definitions.py: 825 statements, 20 missed, 442 branches, 29 partial, 95.5%
```

Exact Ruff gate:

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_figma_bridge.py
Found 485 errors.
```

All 485 findings are inherited violations in the legacy `bubble_cli.py`. The extracted lifecycle package and new tests pass their focused gate:

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py
All checks passed!
```

The exact directory-form mypy gate remains neutralized by the repository exclusion configuration:

```text
rtk ./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
There are no .py[i] files in directory 'src/bubble_mcp/aria_runtime/style_lifecycle'
```

The explicit nine-file lifecycle equivalent passes:

```text
rtk ./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle/colors.py src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py src/bubble_mcp/aria_runtime/style_lifecycle/fonts.py src/bubble_mcp/aria_runtime/style_lifecycle/assignments.py src/bubble_mcp/aria_runtime/style_lifecycle/__init__.py src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py src/bubble_mcp/aria_runtime/style_lifecycle/references.py src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py src/bubble_mcp/aria_runtime/style_lifecycle/service.py
Success: no issues found in 9 source files
```

Full repository suite and diff hygiene:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q
1550 passed in 20.16s

rtk git diff --check
(no output; exit 0)
```

Baseline before implementation was `1482 passed in 19.76s`.

## Self-review

- Confirmed `StyleBuilder` remains the only Bubble style wire constructor; the extraction coordinates its returned payloads and intents.
- Confirmed every existing public definition/state `BubbleCLI` signature and return annotation is unchanged and delegates without result translation.
- Confirmed HTML import and Figma import are integration consumers, not moved into the extraction.
- Confirmed the Figma importer consumes `StyleDefinitionService` through the stable `StyleDefinitionSink` contract.
- Confirmed create payload order remains index, create, ID-path fixer, optional default, and ID counter; conditional-state order remains transitions, state creation, then properties.
- Confirmed create/update dry runs hydrate discovery but do not dispatch or mutate cache.
- Confirmed cache writes/removals happen only after successful dispatch and that each dispatch/cache failure returns `False`.
- Confirmed default styles are excluded from bulk deletion and clearing.
- Confirmed property matching preserves the legacy missing `boxshadow_enable=True` exception without treating arbitrary missing booleans as equal.
- Removed two unreachable cache branches: button fallback duplicated `StyleReferenceResolver` cache indexing, and property-match cache candidates could never satisfy both raw-style membership and absence from the ID set derived from those same raw styles.

## Commits and publication

- `3ccedc2d6e75ba0072b11efaa123597f00df30d4` — `refactor: extract style definition lifecycle`
- Draft PR: https://github.com/pedrobefree/befree-bubble-mcp/pull/30
- Verified PR base: `codex/style-token-lifecycle-4-5d-figma-import`
- Verified PR head: `codex/style-token-lifecycle-4-5e-definitions`

## Concerns

- The exact Ruff command remains red on 485 inherited `bubble_cli.py` findings; the extracted package and new tests are clean.
- The directory-form mypy command does not inspect `aria_runtime` under the current repository exclusion; the explicit nine-file equivalent is green.
- Legacy implementations remain under `_legacy_*` names inside `BubbleCLI` for compatibility/reference during the staged decomposition. Public execution goes exclusively through `StyleDefinitionService`; physical removal of those dead bodies is outside this stage's requested orchestration-only boundary.
