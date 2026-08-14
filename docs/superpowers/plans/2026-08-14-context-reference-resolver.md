# Context Reference Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract discovery-backed context and reference resolution from `BubbleCLI` without changing any CLI or MCP contract.

**Architecture:** Introduce a typed-host `ContextReferenceResolver` that consumes the Stage 4.1 cache and Stage 4.2 alias boundaries through existing compatibility methods. Keep persistence and domain mutation logic outside the resolver; retain thin `BubbleCLI` facades.

**Tech Stack:** Python 3.11, standard-library protocols and dataclasses, pytest, coverage.py, timeit.

**Spec:** `docs/superpowers/specs/2026-08-14-context-reference-resolver-design.md`

## Global Constraints

- Preserve all MCP tool names, schemas, aliases, annotations, dispatch routes, outputs, previews, and confirmation gates.
- Preserve existing `BubbleCLI` public and internal compatibility method signatures used by callers.
- Keep cache-file persistence exclusively in `BubbleCLICacheStore` and alias lifecycle exclusively in `ContextAliasRegistry`.
- Support readable and raw discovery aliases together, including `%p3`, `%ed`, `%el`, `%wf`, and `%p`.
- Use only the Python standard library in the extracted resolver.
- Raise the global coverage ratchet only with at least 0.1 percentage point of headroom.

---

### Task 1: Characterize and extract cached materialization and capture parsing

**Files:**
- Create: `src/bubble_mcp/aria_runtime/context_reference_resolver.py`
- Create: `tests/unit/test_context_reference_resolver.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`

**Interfaces:**
- Consumes: host discovery data, path parsing/normalization, cache path, and `ContextAliasRegistry.cache_element`.
- Produces: `materialize_cached_element_stub`, `normalize_capture_path`, `sync_element_ref_cache`, and thin `BubbleCLI` facades.

- [ ] Write failing tests proving cached paths preserve existing siblings, raw/readable roots both materialize, malformed paths return unchanged payloads, and mixed capture rows retain valid mappings.
- [ ] Run `./.venv/bin/python -m pytest tests/unit/test_context_reference_resolver.py -q` and verify failure because the resolver module is absent.
- [ ] Implement the minimal typed host and capture/materialization methods.
- [ ] Delegate the corresponding `BubbleCLI` methods and run focused CLI compatibility tests.
- [ ] Commit as `refactor: extract reference capture boundary`.

### Task 2: Extract discovery traversal and element resolution

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/context_reference_resolver.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `tests/unit/test_context_reference_resolver.py`

**Interfaces:**
- Consumes: discovery lists, raw/index/module readers, alias-registry lookups, and normalization callbacks.
- Produces: `iter_contexts`, `collect_context_elements`, `find_elements_by_ref`, `find_element_by_ref`, and `select_element_match`.

- [ ] Write failing literal-fixture tests for scope filtering, reusable/page ambiguity, source deduplication, cached-only rows, text/name/key/id matching, ranking, and one-based selection.
- [ ] Run focused tests and verify failures name missing resolver behavior.
- [ ] Move traversal and matching logic into the resolver; leave wrappers for legacy callers.
- [ ] Run focused tests plus existing CLI/context suites and verify exact rows and ordering.
- [ ] Commit as `refactor: isolate discovery reference traversal`.

### Task 3: Extract inspection and multi-domain reference orchestration

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/context_reference_resolver.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `tests/unit/test_context_reference_resolver.py`
- Modify: `tests/unit/test_cli_commands.py` only for missing facade contracts.

**Interfaces:**
- Consumes: Tasks 1-2 plus existing workflow/style/data-type/option-set resolvers.
- Produces: `inspect_context` and `resolve_refs` with unchanged JSON, log, truncation, and boolean semantics.

- [ ] Write failing tests for single/list inspection, truncation, styles/workflows, mixed successes/errors, required-context errors, and `match_index` clamping.
- [ ] Run focused tests and verify failures are caused by missing resolver orchestration.
- [ ] Move inspection and resolution orchestration into the resolver and delegate both `BubbleCLI` entry points.
- [ ] Run CLI dispatcher and MCP catalog/routing tests to prove compatibility.
- [ ] Commit as `refactor: delegate context reference resolution`.

### Task 4: Coverage, performance, roadmap, and review

**Files:**
- Modify: `docs/optimization-roadmap.md`
- Modify: `pyproject.toml` only if measured global headroom permits.
- Modify: this plan to mark completed steps.

**Interfaces:**
- Produces: measured Stage 4.3 results and review-ready implementation evidence.

- [ ] Measure pre/post lookup, resolution, and inspection timings with literal synthetic data and no timing assertions in pytest.
- [ ] Run focused branch coverage and raise the resolver to at least 95% combined branch coverage.
- [ ] Run the full Python/Node suites, global sharded coverage, Ruff, MyPy, security/package/setup/catalog/runtime/routing checks, and `git diff --check`.
- [ ] Update the roadmap with moved lines, focused/global coverage, test totals, benchmark, and the next Family 2 boundary.
- [ ] Run independent code review and resolve every Critical/Important finding with regression tests.
- [ ] Commit the final validation documentation; publication remains a separate explicit user request.

## Self-Review

- Spec coverage: capture parsing, cached materialization, discovery traversal, inspection, multi-domain resolution, compatibility, performance, and review each map to a task.
- Placeholder scan: no deferred implementation placeholders remain.
- Type consistency: resolver method names and host dependencies are consistent across tasks.
- Scope: persistence, alias lifecycle, tool schemas, and mutation families remain outside Stage 4.3.
