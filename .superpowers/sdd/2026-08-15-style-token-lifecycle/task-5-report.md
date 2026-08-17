# Task 5 report — Phase 4.5d deterministic Figma token import

Date: 2026-08-15  
Branch: `codex/style-token-lifecycle-4-5d-figma-import`  
Base: `codex/style-token-lifecycle-4-5c-design-tokens`  
Implementation commit: `5ca4a4bbb4209cff335b9b00ef33f03cc2c985ff` — `refactor: extract Figma token import`  
Draft PR: https://github.com/pedrobefree/befree-bubble-mcp/pull/29

## Outcome

Stage 4.5d is implemented and published as a draft stacked PR. The legacy Figma token importer is replaced by `FigmaTokenImportService`, composed through `StyleLifecycleService` and a narrow `StyleDefinitionSink`. The public `BubbleCLI.sync_figma_tokens(...) -> bool` signature remains unchanged. Its structured internal result is stored on the CLI instance for bridge capture, so the public boolean facade and the bridge result do not conflict.

The importer enforces explicit input bounds of 5,000,000 bytes, depth 64, and 100,000 nodes. It rejects unreadable, growing, malformed, non-object, invalid bridge-wrapper, deep, and node-heavy JSON before transformation. Planning snapshots font and color state once, deduplicates deterministically, honors type/base/name and transformer exclusion filters, and produces ordered fonts-then-colors-then-styles work. Stable internal IDs are derived deterministically, and style references use those IDs. A literal regression forbids `var(--color_True_default)`.

Application emits at most one custom-font map and one custom-color map before ordered style operations. Successful remote writes survive cache-warning failures; mutation failures stop later phases and preserve applied counts. Dry runs materialize all font/color payloads and style operations without dispatch, cache mutation, or style side effects.

The existing Figma bridge remains the integration boundary. Token responses add structured counts, the complete plan, enforced `app_version`, and session context while preserving existing top-level result fields. Complete bridge extraction remains out of scope. `sync_figma_tokens(list_options=true)` remains the sole read-only option-discovery path. No tool was added: the contract remains 327 MCP tools and 207 CLI commands.

## RED/GREEN evidence

### Deterministic import service

Initial RED, before production implementation:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_figma_import.py -q
ERROR collecting tests/unit/test_style_lifecycle_figma_import.py
ModuleNotFoundError: No module named 'bubble_mcp.aria_runtime.style_lifecycle.figma_import'
```

The first GREEN established bounded loading, deterministic planning, grouped writes, complete dry runs, partial failure reporting, filtering, deduplication, one-to-many default mappings, idempotence, and the literal boolean-ID regression:

```text
21 passed
```

Self-review expanded boundary coverage for missing/growing files, explicit node limits, bridge-wrapper extraction, planning failures, post-write cache warnings, style false/exception failures, custom-color updates, duplicate mapping targets, color-base selection, invalid types, style normalization, and result copying. Final focused service result:

```text
16 passed
```

### Facade, bridge, and schema integration

Integration tests were written before wiring and failed on five missing contracts: legacy facade delegation, structured bridge capture, full schema fields, and read-only `list_options=true` dispatch for both execution flag combinations.

```text
5 failed
```

After composition, facade, bridge, catalog, and dispatcher changes:

```text
5 passed
```

The final exact Stage 4.5d test gate, including all expanded regressions, is green with 186 tests.

## Required verification gates

Exact Stage 4.5d pytest gate:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q --tb=short
186 passed in 7.67s
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

MCP tool-count probe:

```text
rtk env PYTHONPATH=src ./.venv/bin/python - <<'PY'
from bubble_mcp.server.stdio import handle_request
response = handle_request({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
print('tool_count', len(response['result']['tools']))
PY
tool_count 327
```

Public signature probe:

```text
rtk env PYTHONPATH=src ./.venv/bin/python - <<'PY'
import inspect
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
print(inspect.signature(BubbleCLI.sync_figma_tokens))
print('return_annotation', inspect.signature(BubbleCLI.sync_figma_tokens).return_annotation)
PY
(self, tokens_path: str, config_path: str = 'figma_bridge/token_config.json', dry_run: bool = False, types: str = None, color_bases: str = None, all_tokens: bool = False, list_options: bool = False, filter: str = None) -> bool
return_annotation <class 'bool'>
```

Coverage:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage erase
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py -q
181 passed in 15.91s

rtk env PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py' --fail-under=95
figma_import.py: 402 statements, 2 missed, 136 branches, 5 partial, 98.7%
```

Exact Ruff gate:

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py src/bubble_mcp/aria_runtime/figma_bridge.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/tools.py tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py
Found 486 errors.
```

Of these, 485 are inherited violations in the legacy `bubble_cli.py`; the final error is `E902` because the brief names nonexistent `src/bubble_mcp/aria_runtime/figma_bridge.py` instead of the actual `src/bubble_mcp/figma_bridge.py`. The changed CLI ranges have no Ruff findings. The corrected focused gate over all new or independently lintable touched lifecycle, transformer, bridge, server, and test files passes:

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py src/bubble_mcp/aria_runtime/style_lifecycle/service.py src/bubble_mcp/aria_runtime/style_lifecycle/__init__.py src/bubble_mcp/aria_runtime/figma_bridge/transform_tokens.py src/bubble_mcp/figma_bridge.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/tools.py tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py
All checks passed!
```

The exact directory-form mypy gate is neutralized by the repository exclusion configuration:

```text
rtk ./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
There are no .py[i] files in directory 'src/bubble_mcp/aria_runtime/style_lifecycle'
```

The explicit eight-file lifecycle equivalent passes:

```text
rtk ./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle/__init__.py src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py src/bubble_mcp/aria_runtime/style_lifecycle/service.py src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py src/bubble_mcp/aria_runtime/style_lifecycle/colors.py src/bubble_mcp/aria_runtime/style_lifecycle/fonts.py src/bubble_mcp/aria_runtime/style_lifecycle/assignments.py src/bubble_mcp/aria_runtime/style_lifecycle/references.py
Success: no issues found in 8 source files
```

Full repository suite:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q --tb=short --disable-warnings
1478 passed in 19.02s
```

Diff and forbidden-literal hygiene:

```text
rtk git diff --check
(no output; exit 0)

rtk rg -n 'sys\.path\.(append|insert)\(os\.getcwd\(\)\)|mock_id|var\(--color_True_default\)' src tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py
tests/unit/test_style_lifecycle_figma_import.py:353: assertion literal only
```

## Self-review

- Confirmed the service snapshots fonts and colors once per plan and never performs incremental discovery during planning or application.
- Confirmed dry-run returns materialized token payloads and ordered style operations while producing zero host events and leaving discovery/cache byte-equivalent.
- Confirmed execution groups one custom font map and one custom color map, applies fonts then colors then styles, and stops later phases after a failure.
- Confirmed structured results are additive to the bridge contract and do not replace the public boolean facade.
- Confirmed bridge-captured and planned write payloads carry the requested bridge `app_version`.
- Confirmed `list_options=true` forces a read-only preview before legacy dispatch even when callers provide `execute=true`.
- Confirmed full runtime signature/schema/dispatcher alignment, exactly 327 tools, exactly 207 CLI commands, and no new tool registration.
- Confirmed CWD-based `sys.path` mutation and the legacy `mock_id` path are absent.

## Commits and publication

- `5ca4a4bbb4209cff335b9b00ef33f03cc2c985ff` — `refactor: extract Figma token import`
- Draft PR: https://github.com/pedrobefree/befree-bubble-mcp/pull/29
- Verified PR base: `codex/style-token-lifecycle-4-5c-design-tokens`
- Verified PR head: `codex/style-token-lifecycle-4-5d-figma-import`

## Concerns

- The exact Ruff command remains red on 485 inherited `bubble_cli.py` findings plus the brief's one nonexistent path; the corrected focused gate is green and no finding lands in the changed CLI ranges.
- The directory-form mypy command does not inspect `aria_runtime` under the current repository exclusion; the explicit eight-file equivalent is green.
- Full Figma bridge extraction remains intentionally out of scope for 4.5d; this phase adds only the structured capture required by the existing bridge.
- GitHub push and pull-request CI runs `31897805977` and `31897825272` are infrastructure-blocked: each `test` job completed after roughly three seconds with an empty `steps` array. No CI test step ran; the local 1,478-test suite is green.

## Fix round 1 — Important findings

Four review findings were verified against repository behavior and addressed with failing regressions before production changes:

1. The second size check used `Path.read_bytes()` after `stat`, so a file that grew could cause an unbounded read. The loader now rejects non-regular inputs and reads exactly `max_json_bytes + 1` bytes before rejecting surplus input.
2. The Figma bridge omitted the resolved `app_version` when constructing `BubbleCLI`, so execute-mode structured plans could retain the constructor default `test`. The resolved bridge version is now passed at construction.
3. Direct MCP previews returned before any payload-builder capture, leaving the existing `compiled=false`, `write_count=0`, and empty `results`. The dispatcher now adds `figma_import.result` and `figma_import.plan` without changing those existing fields. The safe `figma_import` container name ensures the real MCP response is not replaced by generic secret-key redaction for keys containing `token`.
4. Applied color progress counted payload changes, where one grouped custom-color map represents multiple logical mutations. It now counts default-color updates plus custom cache updates, so a later style failure reports every successful color mutation.

### RED

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_figma_import.py::test_bounded_loader_rejects_missing_growing_and_node_heavy_documents tests/unit/test_style_lifecycle_figma_import.py::test_bounded_loader_rejects_non_regular_inputs tests/unit/test_style_lifecycle_figma_import.py::test_later_style_failure_reports_each_applied_custom_color_mutation tests/unit/test_figma_bridge.py::test_figma_bridge_execute_uses_requested_version_in_structured_token_plan tests/unit/test_mcp_server.py::test_sync_figma_tokens_tools_call_preview_exposes_structured_plan_additively
5 failed in 0.62s
```

The failures were literal: the stream observed `read(-1)` instead of capped `read(33)`; a directory reached the JSON error path; three applied custom colors were reported as one; the execute bridge plan contained `test` instead of `version-stage`; and the real `tools/call` preview had no additive structured import result.

### GREEN

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_figma_import.py::test_bounded_loader_rejects_missing_growing_and_node_heavy_documents tests/unit/test_style_lifecycle_figma_import.py::test_bounded_loader_rejects_non_regular_inputs tests/unit/test_style_lifecycle_figma_import.py::test_later_style_failure_reports_each_applied_custom_color_mutation tests/unit/test_figma_bridge.py::test_figma_bridge_execute_uses_requested_version_in_structured_token_plan tests/unit/test_mcp_server.py::test_sync_figma_tokens_tools_call_preview_exposes_structured_plan_additively
5 passed in 0.44s
```

### Fix-round verification

Exact Stage 4.5d gate:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q --tb=short
190 passed in 7.68s
```

Coverage:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage erase
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py -q
185 passed in 15.81s

rtk env PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py' --fail-under=95
figma_import.py: 408 statements, 2 missed, 140 branches, 5 partial, 98.7%
```

Focused Ruff:

```text
rtk ./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py src/bubble_mcp/figma_bridge.py src/bubble_mcp/aria_dispatch.py tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py
All checks passed!
```

Explicit mypy:

```text
rtk ./.venv/bin/mypy src/bubble_mcp/aria_dispatch.py src/bubble_mcp/aria_runtime/style_lifecycle/__init__.py src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py src/bubble_mcp/aria_runtime/style_lifecycle/service.py src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py src/bubble_mcp/aria_runtime/style_lifecycle/colors.py src/bubble_mcp/aria_runtime/style_lifecycle/fonts.py src/bubble_mcp/aria_runtime/style_lifecycle/assignments.py src/bubble_mcp/aria_runtime/style_lifecycle/references.py
Success: no issues found in 9 source files
```

Catalog and tool contracts:

```text
rtk env PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
cli_command_count: 207; alias_count: 1; missing_count: 0; ok: true

MCP tool-count probe: 327
```

Full suite and diff hygiene:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q --tb=short --disable-warnings
1482 passed in 19.82s

rtk git diff --check
(no output; exit 0)
```
