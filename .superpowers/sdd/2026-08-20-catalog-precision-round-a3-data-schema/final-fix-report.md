# Round A.3 final-review fix report

Date: 2026-08-20  
Worktree: `/Users/pedroduarte/Documents/Development/Custom/aria/.external/befree-bubble-mcp/.worktrees/catalog-precision-a3-data-schema`  
Remote actions: none (no push, PR update, fetch, or other remote mutation)  
Authenticated Bubble Editor execution: not performed

## Final status

All six final-review findings are closed. Every production behavior used strict
test-first RED/GREEN evidence. The documentation-only historical correction did
not receive a source-text test because the testing guidance explicitly rejects
tests that grep human prose; it was verified through the documentation search
and diff-hygiene gates instead.

The complete Task 7 matrix was rerun from the beginning after the functional
fix commit. All canonical gates exited 0. The final A.3 audit is base-catalog
only, owns exactly 28 tools, and reports 0 failures.

## Finding-to-RED-to-fix-to-GREEN ledger

### 1. Critical: read-only discovery exposed write channels

Mutation captured: reintroducing `execute`, `write_payload`, `payload`, or the
unconsumed `settings_path` field in `scan_types`/`list_data_types`, or accepting
those arguments during targeted normalization.

RED command:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py::test_read_only_data_type_discovery_rejects_write_and_unused_controls \
  tests/unit/test_mcp_server.py::test_read_only_data_type_discovery_schemas_publish_no_write_channels \
  tests/unit/test_mcp_server.py::test_data_schema_schemas_do_not_publish_unconsumed_settings_path
```

RED result: `6 failed in 0.74s`. The four normalizer cases did not raise, the
read-only schemas still published write channels, and all A.3 schemas still
published `settings_path`.

Fix:

- removed `execute`, `write_payload`, and `payload` from the two read-only
  discovery schemas and precision specs;
- removed `settings_path` from every targeted A.3 schema/spec because neither
  `server/tools.py` nor the dispatch boundary consumes it;
- made normalization intersect declared controls with an independent boundary
  consumer contract, so stale controls fail closed.

GREEN result: the same command passed `6 passed in 0.36s`.

### 2. Important: mutable/shrinkable exact inventory and weak wheel assertion

Mutation captured: mutating a precision spec at runtime, removing one target
from the module inventory while calling the default report, or allowing the
installed-wheel check to accept a non-28/failed report.

RED command:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py::test_precision_inventory_mapping_rejects_runtime_mutation \
  tests/unit/test_catalog_schema_precision.py::test_default_precision_report_fails_when_inventory_target_is_removed
```

RED result: both inventory assertions failed in the recorded three-case RED
run (`3 failed in 0.11s` overall). The mapping accepted assignment and the
default report retained the old 28-entry default object after the module
inventory was reduced.

The installed-wheel behavior was then exercised by running the executable
check against reports mutated to `27 tools / 0 failures` and
`28 tools / 1 failure`:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_package_smoke.py::test_package_smoke_rejects_non_exact_installed_precision_report
```

With the exact assertions removed, RED was `2 failed in 15.17s`: both invalid
reports printed successfully instead of raising. This behavioral test replaced
the provisional text-presence assertion.

Fix:

- wrapped `DATA_SCHEMA_PRECISION_SPECS` in `MappingProxyType` while retaining
  frozen/slotted records;
- added an independent immutable
  `EXPECTED_DATA_SCHEMA_PRECISION_TARGETS` frozenset;
- changed the report default to resolve the live module inventory and emit
  deterministic `target_set_mismatch` failures for missing/unexpected targets;
- made the installed-wheel check assert `tool_count == 28` and
  `failure_count == 0` in addition to `ok is True`.

GREEN result: the two inventory tests, the two executable wheel mutations, and
the installed-quality check passed together: `5 passed in 13.14s`.

### 3. Important: audit trusted declared aliases and controls

Mutation captured: deleting the real `value -> enabled` operation alias from
`OPERATION_ARG_ALIASES`, or deleting `execute` from the actual server-boundary
control-consumer table while leaving the precision specs unchanged.

RED command:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py::test_live_precision_report_validates_aliases_against_dispatch_tables \
  tests/unit/test_catalog_schema_precision.py::test_live_precision_report_validates_controls_against_boundary_consumers
```

RED result: `2 failed in 0.22s`; both mutated runtime contracts still produced
an incorrectly green report.

Fix:

- introduced `public_aliases_for_runtime_parameter()` and made `_method_kwargs`
  use it directly;
- moved the existing rename/delete field-reference special case into the real
  operation alias table, preserving `name` and `field_name` compatibility;
- made the audit compare every declared target alias with that real dispatch
  resolver and emit `dispatch_alias_mismatch`;
- added the independent `SERVER_BOUNDARY_CONTROL_CONSUMERS` contract, used by
  normalization and checked by the audit with `unconsumed_control` diagnostics;
- retained generic server-consumed controls where legitimate, while excluding
  read-only write channels and unsupported `settings_path`.

GREEN result: the same command passed `2 passed in 0.31s`.

### 4. Important: empty permanent-delete payload mapping escaped

Mutation captured: replacing the key-presence guard with truthiness selection,
so an explicitly supplied empty `write_payload` or `payload` can disappear
before permanent-delete validation.

RED command:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_mcp_server.py::test_permanent_data_type_delete_rejects_explicit_empty_payload_mappings
```

RED result: `1 failed, 1 passed in 0.51s`; `write_payload={}` escaped to runtime
dispatch, while the compatibility `payload={}` spelling happened to reach the
old guard because of operand order.

Fix: added the permanent-delete exclusion immediately after normalization and
before execution/confirmation/dispatch, checking `argument in args` for both
payload spellings. Non-mapping values retain the existing field-specific
normalization error; all mapping values receive the permanent-delete safety
message.

GREEN result: the same command passed `2 passed in 0.33s`.

### 5. Minor: default audit traversed configured extension packs

Mutation captured: making `enabled_extension_tool_schemas()` raise if the
default A.3 report touches local extension configuration.

RED command:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py::test_default_precision_report_does_not_load_local_extension_packs
```

RED result: `1 failed in 0.12s` with
`AssertionError: default precision audit traversed extension packs`.

Fix: added `list_tool_schemas(include_extensions=False)` and made the default
precision report use it. The public catalog loader retains its existing
`include_extensions=True` default for compatibility.

GREEN result: the same command passed `1 passed in 0.21s`.

### 6. Minor: roadmap described a corrected command as currently stale

Mutation addressed: wording that conflated the initial Task 7 brief/attempt
with the subsequently corrected canonical plan and regenerated brief.

Fix: the roadmap now states that the initial brief and initial validation used
the no-argument form, that the canonical plan and regenerated brief were later
corrected, and that the fresh closing run used
`python scripts/audit_sensitive_paths.py .` successfully.

Verification: documentation `rg` found the corrected history and current A.3
evidence; `git diff --check` exited 0. No automated prose test was added.

## Commits

- `f124943` — `fix: close A.3 catalog precision review gaps`
- `9ff1bdb` — `docs: refresh A.3 final review evidence`
- this report is committed as the final local evidence artifact after the two
  implementation/evidence commits above.

No commit was pushed and no PR or remote state was changed.

## Complete Task 7 validation matrix

### Focused contracts

Command:

```bash
PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py \
  tests/unit/test_mcp_server.py \
  tests/unit/test_aria_dispatch.py \
  tests/unit/test_schema_lifecycle_data_types.py \
  tests/unit/test_schema_lifecycle_privacy.py \
  tests/unit/test_schema_lifecycle_options.py \
  tests/unit/test_package_smoke.py
```

Result: `356 passed in 35.23s`.

### Static and deterministic gates

| Command | Literal result |
|---|---|
| `PYTHONPATH=src:. ruff check src tests scripts` | `All checks passed!` |
| `PYTHONPATH=src:. mypy src` | `Success: no issues found in 148 source files` |
| `PYTHONPATH=src python scripts/audit_catalog_selection.py` | `ok: true`; 327 tools/cases; canonical 327; reordered 327; order-independent 327; missing 0; failed 0 |
| `PYTHONPATH=src python scripts/audit_catalog_ambiguity.py` | `ok: true`; 27/27 cases; 8 families; canonical/reversed/rotated/order-independent 27; failed 0 |
| `PYTHONPATH=src python scripts/audit_cli_catalog.py` | `ok: true`; 207 commands; 205 direct; 1 alias; 1 explained exclusion; 327 MCP tools; 122 MCP-only; missing 0 |
| `PYTHONPATH=src python scripts/audit_cli_leaf_map.py` | `ok: true`; 105/105 classified; 99 direct; 1 composed; 4 administration-only; 1 local-housekeeping; catalog gaps 0; issues 0 |
| `PYTHONPATH=src python scripts/audit_catalog_schema_precision.py` | `ok: true`; 28 tools; 301 properties; 52 runtime; 39 aliases; 210 controls; 83 required; failures 0 |
| `python scripts/audit_sensitive_paths.py .` | `Sensitive public-source audit passed.` |
| `git diff --check` | exit 0; no output |

### Full suites

- `PYTHONPATH=src:. pytest -q` — `1958 passed in 136.52s (0:02:16)`.
- `npm test` — 11 tests, 11 passed, 0 failed, 0 cancelled, 0 skipped,
  0 todo; `duration_ms 159.634`.

### Installed wheel and runtime smokes

- `python scripts/package_smoke.py --python python3.11` — `ok: true`;
  clean wheel `befree_bubble_mcp-0.1.2-py3-none-any.whl`;
  `quality_ok: true`, `ambiguity_ok: true`, `case_count: 27`,
  `cli_leaf_map_ok: true`, `leaf_count: 105`,
  `schema_precision_ok: true`, `schema_precision_tool_count: 28`, and server
  initialization included instructions.
- `PYTHONPATH=src python -m bubble_mcp.cli.main smoke runtime --suite coverage`
  — run `20260821020323_276940`; `ok: true`; 2 cases, 2 passed, 0 failed,
  0 skipped; `profile: null`, `execute: false`.
- `PYTHONPATH=src python -m bubble_mcp.cli.main smoke runtime --suite agent-routing`
  — run `20260821020323_147ac6`; `ok: true`; 9 cases, 9 passed, 0 failed,
  0 skipped; `profile: null`, `execute: false`.

### Documentation and hygiene

- `rg` found the refreshed Round A.3 metrics, exact 28-tool language,
  authenticated-execution disclaimer, and corrected initial-brief history in
  `docs/optimization-roadmap.md`, `docs/harness-and-evals.md`, and
  `docs/release-checklist.md`.
- `git diff --check` exited 0 after the documentation update.

## Files changed in the final-fix cycle

- `src/bubble_mcp/catalog_schema_precision.py`
- `src/bubble_mcp/aria_dispatch.py`
- `src/bubble_mcp/server/agent_catalog.py`
- `src/bubble_mcp/server/schemas.py`
- `src/bubble_mcp/server/tools.py`
- `scripts/package_smoke.py`
- `tests/unit/test_catalog_schema_precision.py`
- `tests/unit/test_mcp_server.py`
- `tests/unit/test_package_smoke.py`
- `docs/optimization-roadmap.md`
- `.superpowers/sdd/2026-08-20-catalog-precision-round-a3-data-schema/final-fix-report.md`

## Concerns and residual scope

- No unresolved correctness, safety, typing, lint, packaging, or deterministic
  audit concern remains from the six findings.
- A diagnostic-only summary helper (not a Task 7 gate) initially assumed every
  audit report had a `summary` key and raised `KeyError` for CLI parity; it was
  corrected and used only to extract the already-passing canonical gate
  summaries. No production or test behavior was affected.
- No authenticated Bubble Editor execution was performed. This remains correct
  for Round A.3 because the changes cover discovery, argument-boundary safety,
  dispatch mapping, and deterministic audit contracts; runtime smokes were
  profile-independent with `execute: false`.
- No remote publication action was authorized or performed.
