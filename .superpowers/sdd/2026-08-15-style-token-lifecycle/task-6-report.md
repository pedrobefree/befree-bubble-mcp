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
- GitHub push run `31900394019` and pull-request run `31900396582` are infrastructure-blocked: each `test` job completed in roughly two seconds with an empty `steps` array, so no CI test step ran. The local 1,550-test suite is green.

## Fix round 1 — lifecycle boundary findings

All four review findings were verified against the published implementation and addressed with literal behavior regressions before the production fixes:

1. Bulk delete and clear trusted the raw row's `is_default` flag. Production snapshots identify defaults in `settings.client_safe.default_styles`, and a cache alias of that same ID could be represented as a second non-default candidate. Candidate construction now gets the complete default ID set from `StyleReferenceResolver`, merges discovery/cache aliases by ID, and makes default status win every merge. Destructive matching considers all aliases but never emits a default ID.
2. Generic create/update accepted a canonical style ID that existed only in CLI cache and was absent from the current discovery snapshot. Both flows now remove the matching stale alias transactionally before resolution; create proceeds with canonical creation, update returns `False`, and cleanup failure is fail-closed with no dispatch.
3. `StyleDefinitionService` constructed `AddTransition` intents and duplicated transition wire mappings. `StyleBuilder.build_state_transition_intents(...)` now owns automatic transition filtering, wire mapping, deduplication, and order through `StyleBuilder.update_style(..., transitions=...)`. The service delegates and the existing composite-theme path uses the same helper.
4. The prior consumer regression only called the CLI facade. It is replaced by actual HTML style-plan execution and actual `BubbleCLI.sync_figma_tokens(...)` tests. When the definition sink returns `False`, both consumer results remain failed with zero applied styles.

The 18 uncalled `_legacy_*` definition/state orchestration bodies were removed from `BubbleCLI`. A baseline-to-current structural diff contains only those private definitions/decorators; public and helper definition signatures are unchanged. Unrelated resolver and Family 4+ code remains intact.

### RED

Primary literal regressions before the fixes:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_definitions.py::test_bulk_delete_never_emits_settings_backed_default_or_its_cached_alias tests/unit/test_style_lifecycle_definitions.py::test_clear_never_emits_settings_backed_default_or_its_cached_alias tests/unit/test_style_lifecycle_definitions.py::test_create_removes_stale_cache_only_style_before_creating_canonical_style tests/unit/test_style_lifecycle_definitions.py::test_update_rejects_and_removes_stale_cache_only_style tests/unit/test_style_lifecycle_definitions.py::test_state_transitions_follow_builder_mapping_and_preserve_literal_order tests/unit/test_runtime_sdk_style_builder.py::test_state_transition_intents_use_builder_mapping_and_literal_input_order tests/unit/test_style_lifecycle_definition_facades.py::test_html_style_execution_remains_failed_when_definition_sink_returns_false tests/unit/test_style_lifecycle_definition_facades.py::test_figma_sync_remains_failed_when_definition_sink_returns_false
6 failed, 2 passed in 0.35s
```

The failures were literal: both destructive payloads included `Text_default_`; create emitted no cleanup/creation events; update incorrectly returned `True`; the service emitted a `%bas` transition for raw `%bgc`; and the SDK helper did not exist. The two real-consumer characterizations were already green and replaced the inadequate facade-only check without requiring a consumer code change.

Cleanup-failure behavior was then isolated before adding the fail-closed boundary:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_definitions.py::test_definition_mutations_fail_closed_when_stale_cache_cleanup_fails
2 failed in 0.31s
```

Both failures propagated the literal `RuntimeError: literal cache remove failure` instead of returning `False`.

### GREEN

Primary fix round:

```text
8 passed in 0.25s
```

Fail-closed stale cleanup:

```text
2 passed in 0.16s
```

Definitions, SDK builder, facades, HTML runtime, and Figma importer focused integration:

```text
131 passed in 0.33s
```

### Fix-round verification

Exact Stage 4.5e gate:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_render.py tests/unit/test_style_import_runtime.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
265 passed in 7.93s
```

Coverage:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage erase
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_figma_bridge.py -q
88 passed in 0.42s

rtk env PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py' --fail-under=95
definitions.py: 855 statements, 24 missed, 460 branches, 32 partial, 95.1%
```

Syntax/import and signature parity:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m py_compile src/bubble_mcp/aria_runtime/bubble_cli.py src/bubble_mcp/aria_runtime/bubble_sdk.py src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py
(no output; exit 0)

rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_definition_facades.py::test_public_definition_boolean_signatures_are_stable
1 passed in 0.16s
```

The baseline-to-current `bubble_cli.py` definition diff reports only the 18 removed `_legacy_*` methods and two associated `@staticmethod` decorators. The targeted legacy reference search returns no matches.

Catalog and tool counts:

```text
rtk env PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
cli_command_count: 207; direct_match_count: 205; alias_count: 1; missing_count: 0; ok: true

MCP tool_count: 327
```

Exact Ruff remains the deferred static gate:

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_figma_bridge.py
Found 474 errors.
```

All 474 are inherited `bubble_cli.py` findings. Removing dead legacy bodies reduced the inherited count from 485. The lifecycle package and changed tests pass focused Ruff. Whole-file `bubble_sdk.py` retains 98 inherited findings; none land in the changed `StyleBuilder` range.

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle tests/unit/test_runtime_sdk_style_builder.py tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py
All checks passed!
```

Explicit mypy including the changed SDK and all lifecycle modules:

```text
rtk ./.venv/bin/mypy src/bubble_mcp/aria_runtime/bubble_sdk.py src/bubble_mcp/aria_runtime/style_lifecycle/colors.py src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py src/bubble_mcp/aria_runtime/style_lifecycle/fonts.py src/bubble_mcp/aria_runtime/style_lifecycle/assignments.py src/bubble_mcp/aria_runtime/style_lifecycle/__init__.py src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py src/bubble_mcp/aria_runtime/style_lifecycle/references.py src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py src/bubble_mcp/aria_runtime/style_lifecycle/service.py
Success: no issues found in 10 source files
```

The exact directory-form mypy gate remains excluded by repository configuration, as recorded above.

Full suite and diff hygiene:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q
1559 passed in 21.11s

rtk git diff --check
(no output; exit 0)
```

Fix-round implementation commit:

- `10ba3b0986a5d8ba1f27e823e9bb860466fe79d5` — `fix: harden style definition lifecycle boundaries`

### Fix-round self-review

- Default protection is ID-based, is sourced from current resolver/settings discovery, survives cached aliases, and uses default-wins merging before destructive selection.
- Stale canonical cache aliases are removed only when their ID is absent from current discovery; create then continues through normal creation, while update rejects the missing target. Cleanup exceptions remain fail-closed.
- Transition ordering and wire mapping are owned by `StyleBuilder`; the lifecycle service only delegates to the builder-owned helper.
- HTML and Figma regressions execute their real consumer paths and retain failed results when the definition sink returns `False`.
- The baseline-to-current structural diff removes only the 18 uncalled private definition/state legacy bodies and their two decorators. Public signature parity and unrelated command families remain covered by the exact gate, catalog audit, and full suite.

### Fix-round concerns

- The exact Ruff command remains red on 474 inherited `bubble_cli.py` findings; this round intentionally does not address the deferred static-gate minor. Focused changed-code Ruff is green.
- The exact directory-form mypy command remains excluded by repository configuration and returns no input files; explicit changed-module mypy is green.
- No additional code concern was found during the fix-round self-review.
