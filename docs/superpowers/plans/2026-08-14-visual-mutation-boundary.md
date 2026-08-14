# Visual Mutation Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Bubble visual element delete, create, and update orchestration into a typed composed boundary without changing CLI or MCP behavior.

**Architecture:** Add `aria_runtime.visual_mutations` with shared typed target records and operation-specific services. `BubbleCLI` remains the compatibility surface and retains element-specific property building while delegating context/element selection, canonical paths, preview/dispatch, discovery overlay, and alias side effects.

**Tech Stack:** Python 3.11, standard-library `Protocol`/`dataclass`, pytest, coverage.py, Ruff, MyPy.

**Spec:** `docs/superpowers/specs/2026-08-14-visual-mutation-boundary-design.md`

## Global Constraints

- Preserve all public CLI/MCP tool names, schemas, aliases, annotations, dispatch routes, return values, output logs, preview defaults, and confirmation gates.
- Preserve all existing `BubbleCLI` method signatures.
- Keep cache-file persistence in `BubbleCLICacheStore`, alias lifecycle in `ContextAliasRegistry`, and discovery/reference semantics in `ContextReferenceResolver`.
- Do not move HTML import, page/reusable, style/color/font, data/schema, workflow/authentication, or Figma/batch behavior into Family 2.
- Use only the Python standard library in the extracted boundary.
- Apply TDD: every new behavior test must be observed failing before production implementation.
- Reach at least 95% combined branch coverage for each new operation component.
- Raise the global coverage ratchet only with at least 0.1 percentage point of measured headroom.

---

### Task 1: Add typed visual targets and deletion core (Stage 4.4a)

**Files:**
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/__init__.py`
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/protocols.py`
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/targets.py`
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/deletions.py`
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/service.py`
- Create: `tests/unit/test_visual_mutation_deletions.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`

**Interfaces:**
- Produces: `VisualElementTarget`, `VisualMutationTargets.resolve_existing(...)`, `VisualDeletionService.delete(...)`, and `VisualMutationService.deletions`.
- Consumes: existing host discovery, Stage 4.3 reference facades, `PayloadBuilder`, dispatch, and alias registry facades.

- [ ] **Step 1: Write literal target and deletion tests**

```python
def test_delete_nested_element_uses_canonical_index_path_and_updates_each_parent():
    host = DeletionHostFixture.nested_text()
    service = VisualMutationService(host)
    assert service.deletions.delete("Home", "Hero", allowed_types={"text"}, dry_run=False)
    assert host.sent_changes == [
        {"type": "UpdateIndex", "path": ["_index", "id_to_path", "hero-id"], "value": None},
        {"intent": {"name": "RemoveElement"}, "path_array": ["%p3", "pg", "%el", "hero"], "body": None},
        {"type": "UpdateIndex", "path": ["_index", "issues_sub", "root-id"], "value": "[]"},
    ]
    assert host.removed_aliases == [("pg", "page", "hero-id", ["%el", "hero"])]
```

Add separate literal cases for preview/no-dispatch, dispatch failure/no-alias-removal, missing context, missing element, mismatched type, absent type, raw/readable roots, malformed `id_to_path`, multiple parents, and root-parent fallback.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `./.venv/bin/python -m pytest tests/unit/test_visual_mutation_deletions.py -q`

Expected: collection failure because `bubble_mcp.aria_runtime.visual_mutations` does not exist.

- [ ] **Step 3: Implement immutable targets and narrow host protocol**

```python
@dataclass(frozen=True)
class VisualElementTarget:
    context_id: str
    context_type: str
    result: dict[str, Any]
    element_id: str
    element_type: str
    path: list[str]

class VisualMutationHost(Protocol):
    appname: str
    discovery: Any
    def _find_context(self, name: str) -> tuple[str | None, str | None]: ...
    def _find_element_by_ref(self, context_id: str, context_type: str, element_ref: str, ref_kind: str = "auto", match_index: int = 1) -> dict[str, Any] | None: ...
    def _resolve_cached_element_alias(self, context_id: str, context_type: str, element_ref: str) -> dict[str, Any] | None: ...
    def _dispatch_payload(self, payload: PayloadBuilder) -> None: ...
```

The complete protocol must list every callback actually used by `targets.py`, `deletions.py`, `creations.py`, or `updates.py`; no `Any` service object or back-reference to `BubbleCLI` is allowed.

- [ ] **Step 4: Implement target hydration/canonical path and generic deletion**

```python
def delete(
    self,
    context_name: str,
    element_name: str,
    *,
    allowed_types: frozenset[str],
    expected_label: str,
    success_label: str,
    dry_run: bool = False,
    prefer_last: bool = False,
) -> bool:
    target = self._targets.resolve_existing(context_name, element_name, prefer_last=prefer_last)
    if target is None or not self._type_is_allowed(target, allowed_types, expected_label):
        return False
    payload = self._build_remove_payload(target)
    return self._preview_or_dispatch(payload, target, success_label, dry_run=dry_run)
```

The emitted `PayloadBuilder.changes` ordering must remain `id_to_path`, `RemoveElement`, then `issues_sub` updates.

- [ ] **Step 5: Construct the service in `BubbleCLI` and expose compatibility helper facades**

```python
self._visual_mutations = VisualMutationService(self)

def _resolve_element_for_updates(...):
    return self._visual_mutations.targets.resolve_existing_tuple(...)

def _resolve_canonical_existing_element_path(...):
    return self._visual_mutations.targets.canonical_path(...)
```

- [ ] **Step 6: Run focused deletion and existing resolver/cache compatibility tests**

Run: `./.venv/bin/python -m pytest tests/unit/test_visual_mutation_deletions.py tests/unit/test_context_reference_resolver.py tests/unit/test_context_alias_registry.py -q`

Expected: all pass.

- [ ] **Step 7: Commit the deletion core**

```bash
git add src/bubble_mcp/aria_runtime/visual_mutations src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_visual_mutation_deletions.py
git commit -m "refactor: extract visual deletion core"
```

### Task 2: Delegate every concrete visual delete facade

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `tests/unit/test_visual_mutation_deletions.py`
- Modify: relevant existing CLI facade tests only when a literal contract is missing.

**Interfaces:**
- Consumes: `VisualDeletionService.delete(...)` from Task 1.
- Produces: unchanged behavior for the concrete visual deletion catalog.

- [ ] **Step 1: Add a table-driven facade contract test**

Use literal mapping rows for `delete_text`, `delete_group`, `delete_floating_group`, `delete_group_focus`, `delete_repeating_group`, `delete_table`, `delete_button`, `delete_input`, `delete_checkbox`, `delete_multiline_input`, `delete_dropdown`, `delete_datepicker`, `delete_searchbox`, `delete_icon`, `delete_image`, `delete_link`, `delete_shape`, `delete_alert`, `delete_video`, `delete_html`, `delete_map`, `delete_radio`, `delete_slider`, `delete_file_uploader`, `delete_picture_uploader`, and `delete_popup`. Each row must assert accepted wire types and the public success label; `delete_reusable` remains excluded.

- [ ] **Step 2: Run the facade matrix and verify RED**

Run: `./.venv/bin/python -m pytest tests/unit/test_visual_mutation_deletions.py -q`

Expected: fail because the public methods still execute their in-class implementations instead of the service spy.

- [ ] **Step 3: Replace each implementation with a thin, explicit facade**

```python
def delete_text(self, context_name: str, element_name: str, dry_run: bool = False, prefer_last: bool = False) -> bool:
    return self._visual_mutations.deletions.delete(
        context_name,
        element_name,
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
        dry_run=dry_run,
        prefer_last=prefer_last,
    )
```

Every other facade must pass its literal type set; group accepts `group` and `custom_type`. Do not generate methods dynamically because signatures must remain introspectable.

- [ ] **Step 4: Run the full deletion/facade/dispatcher subset and focused coverage**

Run: `./.venv/bin/python -m pytest tests/unit/test_visual_mutation_deletions.py tests/unit/test_cli_commands.py tests/unit/test_execution.py -q`

Run: `./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_visual_mutation_deletions.py -q && ./.venv/bin/python -m coverage report -m src/bubble_mcp/aria_runtime/visual_mutations/deletions.py`

Expected: all pass and deletion component at least 95% combined branch coverage.

- [ ] **Step 5: Commit all delete facades**

```bash
git add src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_visual_mutation_deletions.py
git commit -m "refactor: delegate visual deletions"
```

### Task 3: Validate and publish Stage 4.4a

**Files:**
- Modify: `docs/optimization-roadmap.md`
- Modify: this plan to mark Tasks 1-3 complete.

**Interfaces:**
- Produces: pushed branch and draft PR A against `main`.

- [ ] **Step 1: Run Python/Node, static, catalog, parity, and preview gates**

Run the full Python suite, Node suite, Ruff, MyPy, `tools quality`, CLI/catalog parity, `smoke runtime --suite preview-write`, `smoke runtime --suite family-preview`, and `git diff --check`.

- [ ] **Step 2: Record moved lines, tests, coverage, and contract status in the roadmap**

Document exact measured values and state that no tool/schema/annotation change occurred.

- [ ] **Step 3: Commit validation docs, push, and open draft PR A**

```bash
git add docs/optimization-roadmap.md docs/superpowers/plans/2026-08-14-visual-mutation-boundary.md
git commit -m "docs: record visual deletion extraction"
git push -u origin codex/visual-mutations-4-4a-delete
gh pr create --draft --base main --head codex/visual-mutations-4-4a-delete
```

### Task 4: Extract visual creation preparation and finalization (Stage 4.4b)

**Files:**
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/creations.py`
- Create: `tests/unit/test_visual_mutation_creations.py`
- Modify: `src/bubble_mcp/aria_runtime/visual_mutations/protocols.py`
- Modify: `src/bubble_mcp/aria_runtime/visual_mutations/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`

**Interfaces:**
- Produces: `VisualCreationTarget`, `VisualCreationService.prepare(...)`, and `VisualCreationService.finish(...)`.
- Consumes: shared targets, existing element-specific bodies/payload builders, discovery injection, and alias registry facades.

- [x] **Step 1: Branch from Stage 4.4a and write failing literal creation lifecycle tests**

```bash
git checkout -b codex/visual-mutations-4-4b-create
```

Test root and nested targets plus preview, execute, failure, injection warning, alias deduplication, and returned element ID/key. Expected payloads and side effects must be literals, not computed with production helpers.

- [x] **Step 2: Run the new tests and verify RED**

Run: `./.venv/bin/python -m pytest tests/unit/test_visual_mutation_creations.py -q`

Expected: import failure because `creations.py` does not exist.

- [x] **Step 3: Implement creation records and lifecycle**

```python
@dataclass(frozen=True)
class VisualCreationTarget:
    context_id: str
    context_type: str
    parent_result: dict[str, Any]
    parent_path: list[str]

def finish(
    self,
    target: VisualCreationTarget,
    payload: PayloadBuilder,
    *,
    body: dict[str, Any],
    element_key: str,
    aliases: Iterable[str],
    result_value: str,
    success_message: str,
    dry_run: bool,
    inject_on_preview: bool = True,
) -> str | bool: ...
```

`finish` must preserve dispatch-before-alias order and must make discovery injection warnings non-fatal exactly where the current facade does.

- [x] **Step 4: Delegate common preparation/finalization from every visual create method**

Cover `create_text`, `create_button`, container methods, inputs/controls, media, HTML/link/alert/map, popup, and reusable instance. Keep `create_from_html`, page/reusable, style, and app-text methods untouched. Element-specific builder/property code remains in place.

- [x] **Step 5: Run creation matrices, existing builder/compiler tests, and focused coverage**

Run creation tests plus `test_cli_commands.py`, compiler tests, visual defaults tests, Bubble SDK builder tests, and relevant HTML regressions. Require at least 95% combined branch coverage for `creations.py`.

- [x] **Step 6: Commit, push, and open draft PR B against Stage 4.4a**

```bash
git add src/bubble_mcp/aria_runtime/visual_mutations src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_visual_mutation_creations.py
git commit -m "refactor: extract visual creation lifecycle"
git push -u origin codex/visual-mutations-4-4b-create
gh pr create --draft --base codex/visual-mutations-4-4a-delete --head codex/visual-mutations-4-4b-create
```

### Task 5: Extract visual update resolution and execution (Stage 4.4c)

**Files:**
- Create: `src/bubble_mcp/aria_runtime/visual_mutations/updates.py`
- Create: `tests/unit/test_visual_mutation_updates.py`
- Modify: `src/bubble_mcp/aria_runtime/visual_mutations/protocols.py`
- Modify: `src/bubble_mcp/aria_runtime/visual_mutations/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`

**Interfaces:**
- Produces: `VisualUpdateService.apply(...)` and shared `VisualMutationTargets.resolve_existing(...)` behavior for all update facades.
- Consumes: literal property maps produced by existing public update methods and host-supplied Family 3 style callbacks.

- [ ] **Step 1: Branch from Stage 4.4b and write failing update lifecycle tests**

```bash
git checkout -b codex/visual-mutations-4-4c-update
```

Add literal cases for exact-name, button-label, reference, alias-cache, path hydration, secondary hydration, canonical index path, plain SetData, style lookup, override clearing, AssignStyle ordering, no-op, preview, dispatch failure, and resolved-target reuse.

- [ ] **Step 2: Run tests and verify RED**

Run: `./.venv/bin/python -m pytest tests/unit/test_visual_mutation_updates.py -q`

Expected: import failure because `updates.py` does not exist.

- [ ] **Step 3: Implement update execution without absorbing Family 3**

```python
def apply(
    self,
    context_name: str,
    element_name: str,
    *,
    prop_updates: dict[str, Any],
    style: str | None = None,
    clear_style_override_keys: list[str] | None = None,
    style_assign_props: dict[str, Any] | None = None,
    force_style_assign: bool = False,
    style_assign_with_set_data: bool = True,
    resolved_target: VisualElementTarget | None = None,
    dry_run: bool = False,
    prefer_last: bool = False,
    success_label: str = "element",
) -> bool: ...
```

Style resolution, style-key discovery, and AssignStyle change construction remain host callbacks with literal ordering tests.

- [ ] **Step 4: Delegate `_resolve_element_for_updates`, `_apply_element_updates`, `update_text`, and `update_layout_property`**

Keep all public update signatures and element-specific property collection unchanged. The two special methods must use the same target/path/preview/dispatch boundary instead of maintaining parallel orchestration.

- [ ] **Step 5: Run update/control/container/media/style compatibility tests and focused coverage**

Require all existing update suites to pass and `updates.py` plus `targets.py` to reach at least 95% combined branch coverage.

- [ ] **Step 6: Commit the update extraction**

```bash
git add src/bubble_mcp/aria_runtime/visual_mutations src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_visual_mutation_updates.py
git commit -m "refactor: extract visual update lifecycle"
```

### Task 6: Final Family 2 validation, roadmap, review, and publication

**Files:**
- Modify: `docs/optimization-roadmap.md`
- Modify: `pyproject.toml` only if global headroom permits.
- Modify: this plan to mark all tasks complete and record evidence.

**Interfaces:**
- Produces: final measured Family 2 stack, pushed PR C, and three review-ready PRs.

- [ ] **Step 1: Run full validation from the Stage 4.4c head**

Run all Python and Node tests, focused combined branch coverage for the entire package, sharded global coverage, Ruff, MyPy, sensitive-path audit, package/setup smokes, catalog quality, CLI/catalog parity, runtime coverage/agent-routing/visual-repair/preview-write/family-preview smokes, and `git diff --check`.

- [ ] **Step 2: Benchmark representative create/update/delete preview payloads**

Measure the same literal fixtures before/after service delegation with `timeit`; record medians and absolute per-operation overhead. Do not add timing assertions to pytest.

- [ ] **Step 3: Update roadmap, ratchet, and plan evidence**

Record physical/executable lines moved, facade lines retained, test totals, focused/global coverage, benchmark, catalog parity, and Stage 4 Family 3 as the next boundary.

- [ ] **Step 4: Run one independent final review across the complete stack and fix every Critical/Important finding with RED/GREEN regression tests**

Review base `origin/main` through the Stage 4.4c head. Re-run affected focused and full gates after fixes.

- [ ] **Step 5: Commit, push, and open draft PR C against Stage 4.4b**

```bash
git add docs/optimization-roadmap.md docs/superpowers/plans/2026-08-14-visual-mutation-boundary.md pyproject.toml
git commit -m "docs: complete visual mutation boundary"
git push -u origin codex/visual-mutations-4-4c-update
gh pr create --draft --base codex/visual-mutations-4-4b-create --head codex/visual-mutations-4-4c-update
```

- [ ] **Step 6: Update all PR bodies and mark the stack ready**

Verify branch heads, mergeability, PR bases, and exact validation evidence. Mark A, B, and C ready only after the final review is clean. Document merge order A → B → C and the known GitHub zero-step infrastructure status separately from code results.

## Self-Review

- Spec coverage: shared target selection, delete/create/update orchestration, safety, compatibility, coverage, performance, stacked delivery, and final review each map to a task.
- Placeholder scan: no deferred implementation placeholders remain.
- Type consistency: `VisualElementTarget`, `VisualCreationTarget`, `VisualMutationHost`, and service method names are defined before downstream use.
- Scope: HTML import, page/reusable, Family 3 style ownership, Family 4 data/schema, Family 5 workflows/authentication, and Family 6 bridges remain excluded.
