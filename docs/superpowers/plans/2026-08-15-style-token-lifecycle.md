# Stage 4.5 Style and Token Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the complete style, color, font, and design-token lifecycle from `BubbleCLI` into typed, independently tested services without breaking public MCP/CLI contracts.

**Architecture:** A composed `StyleLifecycleService` contains narrow reference, assignment, token, import, and definition services. `BubbleCLI` retains every public signature as a compatibility facade, SDK builders retain wire-format ownership, and each phase is delivered as a stacked branch/PR with an isolated diff.

**Tech Stack:** Python 3.11, pytest, coverage.py branch coverage, Ruff, MyPy, Bubble SDK payload builders, MCP catalog/dispatcher audits, GitHub stacked pull requests.

**Spec:** `docs/superpowers/specs/2026-08-15-style-token-lifecycle-design.md`

## Global Constraints

- Preserve all current public `BubbleCLI` signatures unless the spec explicitly adds an optional field.
- Preserve 327 tool names and 207 CLI operation commands; aliases remain callable.
- Preserve preview, confirmation, payload ordering, dispatch, cache, and result contracts except for defects named in the spec.
- Write and run a failing literal behavior test before each production change.
- New lifecycle components must reach at least 95% combined branch coverage.
- Raise the global 40.5% coverage ratchet only with at least 0.1 percentage point of measured headroom.
- Use `PYTHONPATH=src` for module-driven checks from linked worktrees.

---

### Task 1: Publish the design and executable stack plan

**Files:**
- Modify: `.gitignore`
- Modify: `tests/unit/test_setup_smoke.py`
- Create: `docs/superpowers/specs/2026-08-15-style-token-lifecycle-design.md`
- Create: `docs/superpowers/plans/2026-08-15-style-token-lifecycle.md`

**Interfaces:**
- Consumes: Stage 4.4 `VisualMutationHost` style callbacks and the optimization roadmap.
- Produces: reviewed phase boundaries, stack bases, validation commands, and exit criteria.

- [ ] **Step 1: Verify the linked-worktree setup-smoke regression**

Run: `./.venv/bin/python -m pytest tests/unit/test_setup_smoke.py::test_setup_smoke_environment_prepends_checkout_source -q`

Expected before the test correction: FAIL because the assertion hard-codes `befree-bubble-mcp/src` instead of the active checkout source.

- [ ] **Step 2: Make the assertion checkout-relative**

Derive `expected_source = Path(__file__).resolve().parents[2] / "src"` and compare the first `PYTHONPATH` entry to its full string value.

- [ ] **Step 3: Verify the planning baseline**

Run:

```bash
./.venv/bin/python -m pytest -q
npm test
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_quality.py -q
```

Expected: 1,317 Python and 11 Node tests pass; catalog parity reports zero missing mappings.

- [ ] **Step 4: Commit and publish the planning PR**

```bash
git add .gitignore tests/unit/test_setup_smoke.py docs/superpowers/specs/2026-08-15-style-token-lifecycle-design.md docs/superpowers/plans/2026-08-15-style-token-lifecycle.md
git commit -m "docs: plan Stage 4.5 style lifecycle"
git push -u origin codex/style-token-lifecycle-plan
gh pr create --draft --base main --head codex/style-token-lifecycle-plan
```

### Task 2: Phase 4.5a — extract style reference resolution

**Files:**
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/__init__.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/references.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Create: `tests/unit/test_style_lifecycle_references.py`
- Create: `tests/unit/test_style_lifecycle_reference_facades.py`

**Interfaces:**
- Consumes: discovery `data/list_styles/list_elements`, `_cli_cache`, normalized lookup helpers, and default-style settings.
- Produces: `StyleReferenceResolver.find_style_id(name, element_type=None)`, `resolve(value, element_type=None, strict=False)`, `infer_element_type(style_id)`, and `base_properties(style_id)`.

- [ ] **Step 1: Add RED reference-contract tests**

Cover literal raw/readable snapshots, discovery-over-cache precedence, valid cache-only entries, type filtering, configured/inferred defaults, known/unknown explicit IDs in strict/permissive modes, generic labels, semantic Button labels, and index invalidation after snapshot replacement.

Run: `./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_references.py -q`

Expected: FAIL because `style_lifecycle.references` does not exist.

- [ ] **Step 2: Implement the typed resolver and composition root**

Implement `StyleReferenceHost` with only the snapshot and normalization callbacks used by `StyleReferenceResolver`. Build a normalized index once per current snapshot identity and invalidate it when discovery/cache objects change.

- [ ] **Step 3: Add RED facade-parity tests**

Instantiate a real `BubbleCLI` fixture and compare literal results for `find_style_id`, `find_style_id_by_name`, `_resolve_style_reference`, `_infer_element_type_from_style_id`, normalization/default helpers, and `_get_base_style_props` against the pre-extraction fixtures.

Expected: FAIL until the facades delegate to `self._style_lifecycle.references`.

- [ ] **Step 4: Replace legacy bodies with compatibility facades**

Construct `StyleLifecycleService(self)` beside the existing resolver/mutation services. Retain signatures and direct-execution import fallbacks.

- [ ] **Step 5: Verify 4.5a**

```bash
./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_references.py tests/unit/test_style_lifecycle_reference_facades.py tests/unit/test_create_defaults_golden.py tests/unit/test_visual_mutation_updates.py -q
./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_style_lifecycle_references.py tests/unit/test_style_lifecycle_reference_facades.py
./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
PYTHONPATH=src ./.venv/bin/python -m coverage erase
PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_references.py tests/unit/test_style_lifecycle_reference_facades.py tests/unit/test_create_defaults_golden.py tests/unit/test_visual_mutation_updates.py -q
PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/references.py' --fail-under=95
git diff --check
```

Expected: all checks pass and the new reference component reaches at least 95% combined branch coverage.

- [ ] **Step 6: Commit and publish the 4.5a PR**

Create `codex/style-token-lifecycle-4-5a-references` from the planning branch, commit as `refactor: extract style reference resolution`, push, and open a draft PR based on `codex/style-token-lifecycle-plan`.

### Task 3: Phase 4.5b — extract assignment and override policy

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/assignments.py`
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Create: `tests/unit/test_style_lifecycle_assignments.py`
- Create: `tests/unit/test_style_lifecycle_assignment_facades.py`
- Modify: `tests/unit/test_mcp_server.py`

**Interfaces:**
- Consumes: `StyleReferenceResolver`, `PayloadBuilder`, SDK style intents, raw/base style properties, and element-type policy.
- Produces: `StyleOverridePolicy.override_keys/prune` and `StyleAssignmentService.assign/clear`, while retaining all Family 2 callbacks.

- [ ] **Step 1: Add RED literal assignment goldens**

Cover Text, Button, Group, Table, RepeatingGroup, Popup, and DateInput; alias-equivalent values; protected structural properties; marker cleanup; explicit differences; removal; `include_set_data=False`; shared intent IDs; and exact intent order.

Run: `./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_assignments.py -q`

Expected: FAIL because the assignment service does not exist.

- [ ] **Step 2: Implement override policy and assignment service**

Move override-key calculation, marker clearing, both pruning implementations, and assignment intent construction. Keep target resolution and dispatch in the visual/update callers.

- [ ] **Step 3: Add RED facade and failure regressions**

Prove real `BubbleCLI` callbacks delegate, unresolved styles emit no write, failed dispatch does not mutate cache, and all Family 2 update/create goldens remain literal.

- [ ] **Step 4: Add the missing `by_contains` MCP field**

Expose optional boolean `by_contains` on `update_style_all` and add a schema-to-dispatch regression that reaches the unchanged runtime signature.

- [ ] **Step 5: Verify 4.5b**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_assignments.py tests/unit/test_style_lifecycle_assignment_facades.py tests/unit/test_visual_mutation_creations.py tests/unit/test_visual_mutation_updates.py tests/unit/test_visual_mutation_deletions.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py src/bubble_mcp/server/agent_catalog.py tests/unit/test_style_lifecycle_assignments.py tests/unit/test_style_lifecycle_assignment_facades.py tests/unit/test_mcp_server.py
./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
PYTHONPATH=src ./.venv/bin/python -m coverage erase
PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_assignments.py tests/unit/test_style_lifecycle_assignment_facades.py tests/unit/test_visual_mutation_creations.py tests/unit/test_visual_mutation_updates.py tests/unit/test_visual_mutation_deletions.py -q
PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/assignments.py' --fail-under=95
git diff --check
```

- [ ] **Step 6: Commit and publish the 4.5b PR**

Create `codex/style-token-lifecycle-4-5b-assignments` from 4.5a, commit as `refactor: extract style assignment policy`, push, and open a draft PR based on the 4.5a branch.

### Task 4: Phase 4.5c — extract color and font lifecycle

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/colors.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/fonts.py`
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Create: `tests/unit/test_style_lifecycle_colors.py`
- Create: `tests/unit/test_style_lifecycle_fonts.py`
- Create: `tests/unit/test_style_lifecycle_token_facades.py`
- Modify: `tests/unit/test_mcp_server.py`

**Interfaces:**
- Consumes: immutable discovery/cache snapshots, `ColorBuilder`, `FontBuilder`, payload dispatch, and post-success cache mutation.
- Produces: internal token IDs and stable public boolean facades; canonical color resolution shared by styles and elements.

- [ ] **Step 1: Add RED color lifecycle tests**

Cover raw/default/custom wrappers, discovery/cache precedence, cache-only entries, canonical custom variables, literal hex/RGBA, targeted default update, custom-map preservation, real ID creation, soft/hard deletion, regex failure, and reorder tombstone preservation.

- [ ] **Step 2: Implement `ColorTokenService` and color facades**

Use one normalized snapshot and one grouped custom-map payload per operation. Apply cache deltas only after successful dispatch; dry-run returns the complete plan without side effects.

- [ ] **Step 3: Add RED font lifecycle tests**

Cover app/custom lookup, case-insensitive names, deleted entries, real ID creation, update/delete cache coherence, App Font protection, and dry-run/failure behavior.

- [ ] **Step 4: Implement `FontTokenService` and font facades**

Use `FontBuilder` for wire entries, preserve public booleans, and return IDs only through the internal service result.

- [ ] **Step 5: Correct MCP schemas and destructive confirmation**

Add literal schema-to-dispatch-to-signature tests for create/update/delete/list colors and fonts, bulk color delete, and reorder. Require `confirm=true` only for executing destructive calls; preview remains non-dispatching.

- [ ] **Step 6: Verify and publish 4.5c**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_colors.py tests/unit/test_style_lifecycle_fonts.py tests/unit/test_style_lifecycle_token_facades.py tests/unit/test_runtime_token_transformer.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/tools.py tests/unit/test_style_lifecycle_colors.py tests/unit/test_style_lifecycle_fonts.py tests/unit/test_style_lifecycle_token_facades.py tests/unit/test_mcp_server.py
./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
PYTHONPATH=src ./.venv/bin/python -m coverage erase
PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_colors.py tests/unit/test_style_lifecycle_fonts.py tests/unit/test_style_lifecycle_token_facades.py tests/unit/test_runtime_token_transformer.py -q
PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/colors.py' --fail-under=95
PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/fonts.py' --fail-under=95
git diff --check
```

Create `codex/style-token-lifecycle-4-5c-design-tokens`, commit `refactor: extract design token lifecycle`, push, and open a draft PR based on 4.5b.

### Task 5: Phase 4.5d — extract deterministic Figma token import

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py`
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/figma_bridge.py`
- Create: `tests/unit/test_style_lifecycle_figma_import.py`
- Modify: `tests/unit/test_runtime_token_transformer.py`
- Modify: `tests/unit/test_figma_bridge.py`
- Modify: `tests/unit/test_mcp_server.py`

**Interfaces:**
- Consumes: `ColorTokenService`, `FontTokenService`, `StyleDefinitionSink`, and `TokenTransformer`.
- Produces: deterministic `FigmaTokenPlan` and structured sync result while keeping the public `sync_figma_tokens` boolean facade.

- [ ] **Step 1: Add RED plan and regression tests**

Cover bounded/malformed/deep JSON, font-color-style order, deduplication, default one-to-many mappings, filters, idempotence, complete dry-run payloads, partial failure, and a literal regression forbidding `var(--color_True_default)`.

- [ ] **Step 2: Implement bounded loading and deterministic planning**

Remove CWD `sys.path` mutation. Validate size/depth/shape before transformation. Build grouped font/color payloads and ordered style operations without dispatch.

- [ ] **Step 3: Implement application and bridge capture**

Apply at most one custom-font and one custom-color map, then style operations. Ensure bridge write capture records dry-run plans, `app_version`, session context, and structured counts.

- [ ] **Step 4: Correct MCP import schemas without adding a tool**

Expose the full `sync_figma_tokens` signature while retaining the 327-tool
contract. Keep option discovery solely on the existing
`sync_figma_tokens(list_options=true)` path, and add literal
schema-to-dispatch-to-runtime-signature tests for both import and option
discovery in `tests/unit/test_mcp_server.py`.

- [ ] **Step 5: Verify and publish 4.5d**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py src/bubble_mcp/figma_bridge.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/tools.py tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py
./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
PYTHONPATH=src ./.venv/bin/python -m coverage erase
PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_figma_import.py tests/unit/test_runtime_token_transformer.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py -q
PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/figma_import.py' --fail-under=95
git diff --check
```

Create `codex/style-token-lifecycle-4-5d-figma-import`, commit `refactor: extract Figma token import`, push, and open a draft PR based on 4.5c.

### Task 6: Phase 4.5e — extract style definitions and states

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/protocols.py`
- Create: `src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py`
- Modify: `src/bubble_mcp/aria_runtime/style_lifecycle/service.py`
- Modify: `src/bubble_mcp/aria_runtime/bubble_cli.py`
- Create: `tests/unit/test_style_lifecycle_definitions.py`
- Create: `tests/unit/test_style_lifecycle_definition_facades.py`

**Interfaces:**
- Consumes: `StyleReferenceResolver`, color resolution, `StyleBuilder`, dispatch/cache callbacks, and the `StyleDefinitionSink` used by Figma import.
- Produces: create/update/rename/delete/default/state operations and unchanged public `BubbleCLI` facades.

- [ ] **Step 1: Add RED definition lifecycle goldens**

Cover normalization, create/update/rename, default assignment, conditional states, transition intents, order parsing, dry-run discovery hydration, dispatch failure, delete/bulk/clear cache cleanup, and literal payload order.

- [ ] **Step 2: Implement `StyleDefinitionService`**

Move lifecycle orchestration while keeping `StyleBuilder` wire construction. Cache mutation follows successful dispatch; dry-run hydration is isolated and explicit.

- [ ] **Step 3: Add RED facade/import regressions**

Prove all existing public methods delegate, HTML style import and Figma `StyleDefinitionSink` retain results, and style definition failures cannot report success.

- [ ] **Step 4: Verify and publish 4.5e**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_render.py tests/unit/test_style_import_runtime.py tests/unit/test_figma_bridge.py tests/unit/test_mcp_server.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
./.venv/bin/ruff check src/bubble_mcp/aria_runtime/style_lifecycle src/bubble_mcp/aria_runtime/bubble_cli.py tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_figma_bridge.py
./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
PYTHONPATH=src ./.venv/bin/python -m coverage erase
PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest tests/unit/test_style_lifecycle_definitions.py tests/unit/test_style_lifecycle_definition_facades.py tests/unit/test_style_import_html.py tests/unit/test_figma_bridge.py -q
PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/definitions.py' --fail-under=95
git diff --check
```

Create `codex/style-token-lifecycle-4-5e-definitions`, commit `refactor: extract style definition lifecycle`, push, and open a draft PR based on 4.5d.

### Task 7: Phase 4.5f — final evidence and independent review

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/optimization-roadmap.md`
- Create: `docs/superpowers/reviews/2026-08-15-style-token-lifecycle-review.md`
- Create or modify: focused regression tests required by review findings.

**Interfaces:**
- Consumes: the complete 4.5a–4.5e stack.
- Produces: reproducible coverage/benchmark evidence, an honest ratchet, and a review-ready final stack.

- [ ] **Step 1: Run the final validation matrix**

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
npm test
PYTHONPATH=src ./.venv/bin/python -m coverage erase
PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest -q
PYTHONPATH=src ./.venv/bin/python -m coverage report
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_package_smoke.py tests/unit/test_setup_smoke.py tests/unit/test_sensitive_audit.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
PYTHONPATH=src ./.venv/bin/python scripts/audit_sensitive_paths.py .
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite coverage
PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite agent-routing
PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite visual-repair
./.venv/bin/ruff check src tests scripts
./.venv/bin/mypy src
git diff --check
```

With a configured local Bubble profile, additionally run the profile-dependent
safe-read, preview-write, and family-preview suites using that profile and
context; these commands are intentionally excluded from the no-profile matrix
above because they require authenticated project state.

- [ ] **Step 2: Record before/after benchmarks**

Measure seven-run medians for 500/5,000-style resolution, assignment payloads, color/font CRUD, 25/250/100-token import, and definition operations. Record elapsed time, absolute delta, percent delta, JSON bytes, build count, and write count.

- [ ] **Step 3: Raise the ratchet only with measured headroom**

Set `fail_under` no higher than the measured global combined coverage minus 0.1 percentage point. Leave it unchanged if that headroom is unavailable.

- [ ] **Step 4: Request independent review for each PR**

Review each phase against its base SHA and the spec. Fix every Critical/Important finding with a failing literal regression, rerun the affected phase and final matrix, and document the outcome.

- [ ] **Step 5: Publish the closing PR**

Create `codex/style-token-lifecycle-4-5f-final-evidence` from 4.5e, commit `docs: close Stage 4.5 style lifecycle`, push, and open a draft PR based on 4.5e.
