# Context Alias Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract profile-scoped context, element, and workflow alias lifecycle logic from `BubbleCLI` without changing any MCP or CLI contract.

**Architecture:** Introduce a callback-backed `ContextAliasRegistry` over the Stage 4.1 cache store. Keep discovery traversal and public resolution in `BubbleCLI`; replace registry-related methods with thin compatibility facades.

**Tech Stack:** Python 3.11, mutable mappings, pytest, coverage.py.

**Spec:** `docs/superpowers/specs/2026-08-13-context-alias-registry-design.md`

## Global Constraints

- Preserve all MCP tool names, schemas, aliases, annotations, dispatch routes, outputs, previews, and confirmation gates.
- Preserve every existing `BubbleCLI` registry method signature.
- Use only the Python standard library in the extracted registry.
- Reload immediately before cross-process-sensitive alias writes.
- Return defensive copies from payload lookups.
- Preserve legacy string element alias payload compatibility.
- Keep discovery traversal, stub materialization, capture parsing, `inspect_context`, and `resolve_refs` out of Stage 4.2.
- Raise the global coverage ratchet only with at least 0.1 percentage point of headroom.

---

### Task 1: Profile buckets and context aliases

**Files:**
- Create: `src/bubble_mcp/aria_runtime/context_alias_registry.py`
- Create: `tests/unit/test_context_alias_registry.py`

**Interfaces:**
- Produces: `ContextAliasRegistry.profile_cache`, `bucket`, `context_key`, `cache_context`, and `lookup_context`.

- [ ] Write failing tests for profile isolation, invalid bucket repair, context alias fan-out, empty rejection, and reusable-before-page lookup.
- [ ] Run the focused file and verify collection fails because the registry module is absent.
- [ ] Implement the minimal callback-backed profile and context boundary.
- [ ] Run focused tests and Ruff; verify all pass.
- [ ] Commit as `refactor: extract context alias registry`.

### Task 2: Element alias lifecycle

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/context_alias_registry.py`
- Modify: `tests/unit/test_context_alias_registry.py`

**Interfaces:**
- Produces: `cache_element`, `cache_created_elements`, `lookup_element_id`, `lookup_element_payload`, and `remove_element_aliases`.

- [ ] Write failing tests for scope, reload-before-write, path/key enrichment, deduplication, defensive copies, legacy strings, and removal by ID/key/path.
- [ ] Run tests and verify failures because element operations are absent.
- [ ] Implement the minimal element lifecycle and save only on changes.
- [ ] Run focused tests and verify all pass.
- [ ] Commit as `refactor: isolate element alias lifecycle`.

### Task 3: Workflow and context-scope lifecycle

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/context_alias_registry.py`
- Modify: `tests/unit/test_context_alias_registry.py`

**Interfaces:**
- Produces: `cache_workflow`, `lookup_workflow`, `remove_context_aliases`, `remove_workflow_aliases`, and `remove_context_scope`.

- [ ] Write failing tests for deterministic timestamps, reload-before-write, invalid payloads, all removal selectors, and modern/legacy scoped cleanup.
- [ ] Run tests and verify workflow/lifecycle methods are absent.
- [ ] Implement workflow/context cleanup with defensive lookups.
- [ ] Run focused branch coverage and require at least 95%.
- [ ] Commit as `refactor: isolate workflow alias lifecycle`.

### Task 4: BubbleCLI compatibility facades

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `tests/unit/test_context_alias_registry.py`
- Modify: focused existing CLI/runtime tests only when a behavior lacks coverage.

**Interfaces:**
- Consumes: `ContextAliasRegistry` Tasks 1-3.
- Preserves: schema bucket methods and all context/element/workflow cache and removal method signatures.

- [ ] Write failing real-`BubbleCLI` tests for independent-process element/workflow visibility, context lookup precedence, enrichment, and removals.
- [ ] Run integration tests and confirm failures caused by direct legacy registry logic.
- [ ] Construct the registry after cache initialization and delegate existing methods without changing their return types.
- [ ] Run CLI, MCP server, stdio, catalog and routing compatibility suites.
- [ ] Commit as `refactor: delegate BubbleCLI alias registry`.

### Task 5: Validation, roadmap, review, and draft PR

**Files:**
- Modify: `docs/optimization-roadmap.md`
- Modify: `pyproject.toml` only if measured global headroom permits.
- Modify: this plan to mark completed steps.

**Interfaces:**
- Produces: measured Stage 4.2 results and a review-clean draft PR.

- [ ] Benchmark 1,000 registry lookups and 100 alias mutations without timing assertions in pytest.
- [ ] Run full Python/Node, sharded coverage, Ruff, MyPy, security/package/setup/catalog/runtime/routing checks, and `git diff --check`.
- [ ] Update the roadmap with extracted lines, focused/global coverage, test totals, benchmark, and stable ratchet.
- [ ] Run independent code review and resolve every Critical/Important finding with regression tests.
- [ ] Commit final documentation, push the branch, and open a draft PR against `main`.

## Self-Review

- Spec coverage: profile repair, three alias families, cross-process safety, cleanup, compatibility, coverage, review, and publication all map to tasks.
- Placeholder scan: no deferred implementation placeholders remain.
- Type consistency: callback and registry method names match the design and facade task.
- Scope: public resolution/discovery stays explicitly deferred to Stage 4.3.
