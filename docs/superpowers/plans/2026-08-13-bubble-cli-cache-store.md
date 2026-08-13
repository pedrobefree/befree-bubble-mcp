# Bubble CLI Cache Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract crash-safe CLI cache persistence from `BubbleCLI` while preserving every existing MCP, CLI, and runtime contract.

**Architecture:** Add a dependency-light `BubbleCLICacheStore` that owns normalization and filesystem I/O. Keep `BubbleCLI._cli_cache` as the mutable compatibility state and delegate its existing load/save/reload/clear/migration methods to the store, leaving context and reference logic for later stages.

**Tech Stack:** Python 3.11, pathlib, tempfile, json, pytest, coverage.py.

**Spec:** `docs/superpowers/specs/2026-08-13-bubble-cli-cache-store-design.md`

## Global Constraints

- Preserve all MCP tool names, schemas, aliases, annotations, dispatch routes, and result shapes.
- Preserve `BubbleCLI._cli_cache`, `_cache_file`, `_legacy_tmp_cache_file`, and existing cache method signatures.
- Use only the Python standard library in the extracted store.
- Expected serialization and filesystem failures return failure/default state instead of escaping.
- Atomic writes must use a temporary sibling and `os.replace`.
- Canonical data wins conflicts during legacy migration; legacy-only nested data is retained.
- Context aliases and reference-resolution code are out of scope for Stage 4.1.
- The global coverage ratchet may only increase and must retain at least 0.1 percentage point of headroom.

---

### Task 1: Canonical payload and tolerant reads

**Files:**
- Create: `src/bubble_mcp/aria_runtime/cli_cache.py`
- Create: `tests/unit/test_cli_cache_store.py`

**Interfaces:**
- Produces: `default_cache_payload() -> dict[str, Any]`, `merge_cache_payloads(base: Any, incoming: Any) -> Any`, and `BubbleCLICacheStore.load() -> dict[str, Any]`.

- [x] **Step 1: Write failing default, merge, and load tests**

Add literal assertions proving defaults are independent, malformed/non-object JSON returns canonical defaults, unrelated keys survive normalization, invalid canonical buckets are repaired, and canonical incoming values win recursive merge conflicts.

- [x] **Step 2: Run the focused tests and verify RED**

Run: `rtk ./.venv/bin/python -m pytest tests/unit/test_cli_cache_store.py -q`

Expected: collection fails because `bubble_mcp.aria_runtime.cli_cache` does not exist.

- [x] **Step 3: Implement the minimal normalized read boundary**

Implement constants for canonical buckets, fresh default creation, recursive merge, `_normalize_payload`, constructor path storage, warning callback, and `load` using UTF-8 JSON reads.

- [x] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 tests and Ruff on the two new files. Expected: all pass.

- [x] **Step 5: Commit the read boundary**

Commit: `refactor: extract CLI cache read boundary`

### Task 2: Atomic save and idempotent clear

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/cli_cache.py`
- Modify: `tests/unit/test_cli_cache_store.py`

**Interfaces:**
- Produces: `BubbleCLICacheStore.save(payload: Mapping[str, Any]) -> bool` and `clear() -> bool`.

- [x] **Step 1: Write failing filesystem behavior tests**

Use `tmp_path` to assert a normalized round trip, same-directory temporary replacement, failed serialization preserving the previous file, temporary cleanup, and missing/existing clear returning success.

- [x] **Step 2: Run the new tests and verify RED**

Expected: failures because `save` and `clear` are absent.

- [x] **Step 3: Implement atomic persistence**

Serialize to a named temporary sibling, flush and `os.fsync`, replace with `os.replace`, clean the temporary path in `finally`, warn and return `False` on expected errors, and make clear idempotent.

- [x] **Step 4: Run focused tests and verify GREEN**

Run the cache-store tests and `git diff --check`. Expected: all pass.

- [x] **Step 5: Commit atomic persistence**

Commit: `refactor: make CLI cache writes atomic`

### Task 3: Canonical-wins legacy migration

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/cli_cache.py`
- Modify: `tests/unit/test_cli_cache_store.py`

**Interfaces:**
- Produces: `BubbleCLICacheStore.migrate_legacy() -> bool`.

- [ ] **Step 1: Write failing migration tests**

Cover absent/same legacy paths, malformed legacy JSON, legacy-only data retention, canonical scalar conflict precedence, nested dictionary merge, and save failure propagation.

- [ ] **Step 2: Run migration tests and verify RED**

Expected: failures because `migrate_legacy` is absent.

- [ ] **Step 3: Implement migration**

Load both raw object payloads, merge legacy as the base and canonical as incoming, normalize once, and persist atomically. Return `False` for no migration or any invalid/failing path.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run cache-store tests with branch coverage. Expected: at least 95% combined coverage for `cli_cache.py`.

- [ ] **Step 5: Commit migration**

Commit: `refactor: isolate legacy cache migration`

### Task 4: Preserve the BubbleCLI facade

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `tests/unit/test_cli_commands.py`
- Test: `tests/unit/test_cli_cache_store.py`

**Interfaces:**
- Consumes: `BubbleCLICacheStore` from Tasks 1-3.
- Preserves: `_load_cli_cache`, `_merge_cache_payloads`, `_migrate_legacy_tmp_cache`, `_save_cli_cache`, `_reload_cli_cache_from_disk`, and `clear_cache` signatures.

- [ ] **Step 1: Write failing facade integration tests**

Initialize a real `BubbleCLI` with a temporary app JSON and `BUBBLE_CLI_CACHE_PATH`. Assert store construction, persisted add/remove round trips, malformed recovery, clear defaults, and that reload preserves current in-memory state when a disk read fails.

- [ ] **Step 2: Run facade tests and verify RED**

Expected: the store-construction assertion fails because `BubbleCLI` still performs cache I/O directly.

- [ ] **Step 3: Delegate existing facade methods**

Construct the store before cache initialization, delegate each facade method, retain logger messages and return contracts, and remove direct JSON persistence from `bubble_cli.py`.

- [ ] **Step 4: Run focused compatibility suites**

Run cache-store tests, CLI command tests, MCP server tests, stdio tests, catalog quality, and runtime coverage smoke. Expected: all pass with unchanged tool counts.

- [ ] **Step 5: Commit the facade integration**

Commit: `refactor: delegate BubbleCLI cache persistence`

### Task 5: Coverage, performance, documentation, and review

**Files:**
- Modify: `docs/optimization-roadmap.md`
- Modify: `pyproject.toml` only if the measured stable ratchet can increase.
- Modify: this plan to mark completed steps.

**Interfaces:**
- Produces: measured Stage 4.1 results and a review-ready branch.

- [ ] **Step 1: Measure focused coverage and cache performance**

Run branch coverage for `cli_cache.py` and a deterministic temporary-directory loop of 100 normalized load/save cycles. Record coverage and elapsed time without asserting timing in pytest.

- [ ] **Step 2: Run the full validation matrix**

Run full Python and Node suites, full sharded branch coverage, Ruff, MyPy, package/setup smokes, sensitive-path audit, CLI parity, catalog quality, runtime coverage, agent routing, and `git diff --check`.

- [ ] **Step 3: Update roadmap and ratchet**

Record extracted lines, focused/global coverage, test totals, and benchmark. Raise `fail_under` only to the highest stable tenth with at least 0.1 point headroom.

- [ ] **Step 4: Request independent code review**

Review `origin/main...HEAD` against the spec and plan. Fix every Critical and Important finding with focused regression tests and separate commits.

- [ ] **Step 5: Commit final documentation**

Commit: `docs: record CLI cache extraction results`

## Self-Review

- Spec coverage: every persistence, compatibility, testing, coverage, and failure requirement maps to a task.
- Placeholder scan: no deferred implementation placeholders are present.
- Type consistency: store methods and facade signatures match the design; later tasks consume only interfaces introduced earlier.
- Scope: context reconciliation and reference resolution remain explicitly deferred to Stage 4.2/4.3.
