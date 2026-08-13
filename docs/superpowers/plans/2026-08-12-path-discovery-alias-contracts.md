# Path Discovery Alias Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PathDiscovery` preserve and synchronize readable and Bubble wire aliases across context lookup, element traversal, workflow injection, property access, and disk-cache reloads.

**Architecture:** Keep normalization local to `PathDiscovery` through three focused helpers: a non-mutating union for record buckets, a non-empty fallback for property buckets, and a write synchronizer that installs one shared mapping under both aliases. Existing public signatures and canonical path tokens remain unchanged.

**Tech Stack:** Python 3.11+, pytest, coverage.py, Ruff, Git, GitHub CLI

**Spec:** `docs/superpowers/specs/2026-08-12-path-discovery-alias-contracts-design.md`

## Global Constraints

- Do not redesign the context-composition pipeline.
- Do not rewrite the legacy `bubble_sdk.py` module or change public method signatures.
- Do not change source priority between `.bubble`, console, crawler, and mutation overlay.
- Do not merge conflicting property keys across two non-empty property dictionaries.
- Preserve readable-alias precedence on record-key collisions.
- Preserve canonical Bubble wire tokens in normalized API paths.
- Work on `codex/path-discovery-contracts-round-3-stage-4`, the existing branch for PR #17.

---

### Task 1: Add deterministic alias readers

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_sdk.py:6598-6651`
- Test: `tests/unit/test_runtime_sdk_path_discovery.py:20-49`

**Interfaces:**
- Consumes: arbitrary discovery objects and alias names such as `elements/%el`.
- Produces: `PathDiscovery._read_alias_mapping(obj: Any, preferred_key: str, alternate_key: str) -> Dict[str, Any]` and `PathDiscovery._read_nonempty_alias_mapping(obj: Any, preferred_key: str, alternate_key: str) -> Dict[str, Any]`.

- [ ] **Step 1: Write the failing precedence test**

```python
def test_alias_mapping_readers_resolve_precedence() -> None:
    discovery = PathDiscovery()
    target = {
        "elements": {"same": {"id": "readable"}},
        "%el": {"same": {"id": "wire"}, "wire": {"id": "wire"}},
    }

    resolved = discovery._read_alias_mapping(target, "elements", "%el")

    assert resolved == {
        "same": {"id": "readable"},
        "wire": {"id": "wire"},
    }
```

- [ ] **Step 2: Run the test to verify the missing helper fails**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py::test_alias_mapping_readers_resolve_precedence`

Expected: FAIL because `_read_alias_mapping` or `_sync_alias_mapping` is absent.

- [ ] **Step 3: Implement the two read helpers**

```python
@staticmethod
def _read_alias_mapping(obj: Any, preferred_key: str, alternate_key: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    preferred = obj.get(preferred_key)
    alternate = obj.get(alternate_key)
    preferred_mapping = preferred if isinstance(preferred, dict) else None
    alternate_mapping = alternate if isinstance(alternate, dict) else None
    if preferred_mapping is None:
        return alternate_mapping if alternate_mapping is not None else {}
    if alternate_mapping is None or preferred_mapping is alternate_mapping:
        return preferred_mapping
    return {**alternate_mapping, **preferred_mapping}

@staticmethod
def _read_nonempty_alias_mapping(obj: Any, preferred_key: str, alternate_key: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    preferred = obj.get(preferred_key)
    alternate = obj.get(alternate_key)
    if isinstance(preferred, dict) and preferred:
        return preferred
    if isinstance(alternate, dict):
        return alternate
    return preferred if isinstance(preferred, dict) else {}
```

- [ ] **Step 4: Run the helper test**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py::test_alias_mapping_readers_resolve_precedence`

Expected: PASS.

### Task 2: Synchronize aliases on mutation

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_sdk.py:6652-6665,7425-7610`
- Test: `tests/unit/test_runtime_sdk_path_discovery.py:430-710`

**Interfaces:**
- Consumes: `_read_alias_mapping` from Task 1.
- Produces: `PathDiscovery._sync_alias_mapping(obj: Dict[str, Any], preferred_key: str, alternate_key: str) -> Dict[str, Any]`; `inject_element` and `inject_workflow` leave both alias keys pointing at the same dictionary.

- [ ] **Step 1: Write the failing hybrid workflow test**

```python
def test_sync_alias_mapping_unifies_divergent_buckets() -> None:
    discovery = PathDiscovery()
    target = {
        "elements": {"readable": {"id": "readable"}},
        "%el": {"wire": {"id": "wire"}},
    }

    synchronized = discovery._sync_alias_mapping(target, "elements", "%el")

    assert target["elements"] is synchronized
    assert target["%el"] is synchronized

def test_inject_workflow_synchronizes_hybrid_aliases(monkeypatch) -> None:
    discovery = discovery_with({
        "element_definitions": {
            "hybrid": {"%x": "Group", "workflows": {"existing": {"id": "existing"}}}
        }
    })
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: True)

    discovery.inject_workflow("hybrid", "button", "click", "workflow", "reusable")
    root = discovery.data["element_definitions"]["hybrid"]

    assert root["workflows"] is root["%wf"]
    assert discovery.find_workflow_for_element("hybrid", "button")["id"] == "workflow"
```

- [ ] **Step 2: Run the hybrid workflow test**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py::test_sync_alias_mapping_unifies_divergent_buckets tests/unit/test_runtime_sdk_path_discovery.py::test_inject_workflow_synchronizes_hybrid_aliases`

Expected: FAIL because the old implementation creates `%wf` separately and lookup keeps reading `workflows`.

- [ ] **Step 3: Implement write synchronization and migrate injections**

```python
@classmethod
def _sync_alias_mapping(cls, obj: Dict[str, Any], preferred_key: str, alternate_key: str) -> Dict[str, Any]:
    resolved = cls._read_alias_mapping(obj, preferred_key, alternate_key)
    obj[preferred_key] = resolved
    obj[alternate_key] = resolved
    return resolved
```

Use `_sync_alias_mapping(root, "elements", "%el")` for root children,
`_sync_alias_mapping(parent_node, "elements", "%el")` for nested children, and
`_sync_alias_mapping(root, "workflows", "%wf")` for workflow injection.

- [ ] **Step 4: Run element and workflow injection tests**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py -k 'inject or workflow'`

Expected: PASS.

### Task 3: Migrate discovery reads and raw matching

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_sdk.py:7030-7645`
- Test: `tests/unit/test_runtime_sdk_path_discovery.py:275-710`

**Interfaces:**
- Consumes: both read helpers from Task 1.
- Produces: raw contexts can be found by name; divergent element and workflow buckets are traversed; empty property aliases fall back to populated data.

- [ ] **Step 1: Add failing mixed-shape assertions**

```python
assert discovery.find_reusable("raw reusable") == "raw-reuse"
assert discovery.find_page("raw page") == "raw-page"
assert [item["id"] for item in discovery.list_elements("hybrid")] == [
    "wire", "standard", "nested-wire", "nested-standard"
]
assert discovery.get_element_properties(
    {"properties": {}, "%p": {"%dn": "wire"}}
) == {"%dn": "wire"}
```

- [ ] **Step 2: Run the mixed-shape tests**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py -k 'context_and_name or element_lookup or list_and_inject or accessors'`

Expected: FAIL on the pre-change branch because truthiness selection drops the alternate mappings.

- [ ] **Step 3: Replace local truthiness selection**

Use `_read_alias_mapping` in `find_reusable`, `find_page`, all recursive element searches,
`find_workflow_for_element`, and `list_elements`. Use `_read_nonempty_alias_mapping` for workflow
event properties, `_element_match_candidates`, and `get_element_properties`. Include `%nm`, `%dn`,
and `%3` in raw element-name/text candidates.

- [ ] **Step 4: Run all PathDiscovery contracts**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py tests/unit/test_runtime_sdk_core_contracts.py`

Expected: PASS.

### Task 4: Prove disk-cache readback

**Files:**
- Test: `tests/unit/test_runtime_discovery.py:150-190`

**Interfaces:**
- Consumes: `PathDiscovery.inject_workflow` and `DiscoveryDataBoundary.persist_disk_cache`.
- Produces: an integration-level regression proving a fresh instance observes the injected workflow and shared aliases.

- [ ] **Step 1: Write the round-trip test**

```python
def test_path_discovery_persists_injected_workflow_across_instances(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"element_definitions": {"reuse": {"elements": {}}}})
    discovery = PathDiscovery(str(app_path))
    _ = discovery.data

    discovery.inject_workflow("reuse", "button", "click", "workflow", "reusable")

    reloaded = PathDiscovery(str(app_path))
    result = reloaded.find_workflow_for_element("reuse", "button", "click")
    assert result is not None
    assert result["id"] == "workflow"
    root = reloaded.data["element_definitions"]["reuse"]
    assert root["workflows"] is root["%wf"]
```

- [ ] **Step 2: Run the round-trip test**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_discovery.py::test_path_discovery_persists_injected_workflow_across_instances`

Expected: PASS only when injection persists the synchronized mapping.

- [ ] **Step 3: Run the focused discovery suite**

Run: `./.venv/bin/python -m pytest -q tests/unit/test_runtime_sdk_path_discovery.py tests/unit/test_runtime_discovery.py tests/unit/test_runtime_sdk_core_contracts.py`

Expected: PASS.

### Task 5: Validate and publish PR #17

**Files:**
- Verify: all files changed against `origin/main`

**Interfaces:**
- Consumes: all implementation and tests from Tasks 1-4.
- Produces: the implementation commit plus the previously published plan commit on `origin/codex/path-discovery-contracts-round-3-stage-4`, and an updated PR #17 comment.

- [ ] **Step 1: Run the full test suite and coverage gate**

Run: `./.venv/bin/python -m coverage run -m pytest -q tests && ./.venv/bin/python -m coverage report`

Expected: all tests pass and total coverage is at least `35.0%`.

- [ ] **Step 2: Run focused quality gates**

Run: `./.venv/bin/python -m ruff check tests/unit/test_runtime_sdk_path_discovery.py tests/unit/test_runtime_discovery.py tests/unit/test_runtime_sdk_core_contracts.py`

Run: `./.venv/bin/python scripts/runtime_coverage_smoke.py`

Run: `./.venv/bin/python scripts/agent_routing_smoke.py`

Run: `git diff --check`

Expected: Ruff passes, runtime coverage reports `2/2`, agent routing reports `9/9`, and the uncommitted implementation diff is clean.

- [ ] **Step 3: Commit the implementation intentionally**

```bash
git add src/bubble_mcp/aria_runtime/bubble_sdk.py \
  tests/unit/test_runtime_sdk_path_discovery.py \
  tests/unit/test_runtime_discovery.py
git diff --cached --check
git diff --cached --stat
git commit -m "fix: reconcile path discovery aliases"
```

- [ ] **Step 4: Push and update the existing PR**

```bash
git push origin codex/path-discovery-contracts-round-3-stage-4
gh pr comment 17 --body "Structural alias resolution is implemented and validated: readable/wire buckets now reconcile deterministically, mutable aliases stay synchronized, mixed contexts remain discoverable, and workflow cache persistence is proven across instances."
gh pr view 17 --json headRefOid,statusCheckRollup,url
git diff --check origin/main...HEAD
```

Expected: PR #17 points at both the plan and implementation commits, contains the structural-update comment, and the committed branch diff is clean; remote CI may remain infrastructure-blocked by the existing billing lock.

### Task 6: Close remaining in-scope alias and workflow counterexamples

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/bubble_sdk.py`
- Test: `tests/unit/test_runtime_sdk_path_discovery.py`
- Test: `tests/unit/test_runtime_discovery.py`

**Interfaces:**
- Consumes: the alias readers/synchronizer and cache persistence introduced by Tasks 1-4.
- Produces: canonical nested writes, stable preferred ordering, consistent newest-first workflow lookup, and payload isolation between callers and the persisted discovery cache.

- [ ] **Step 1: Reproduce all four review findings in RED**

Add behavioral regressions proving:

1. When an ancestor slot exists as distinct objects in `elements` and `%el`, nested injection synchronizes the ancestor before mutation and the returned canonical `%el` path resolves to the injected child after a fresh-instance cache readback.
2. Same-ID collisions retain both the preferred value and the preferred mapping's insertion order; alternate-only IDs remain present.
3. Root and nested workflow searches both choose the newest matching preferred workflow, while retaining raw-only workflows as fallback.
4. Mutating nested `%p` or `actions` in the caller's `workflow_obj` after injection cannot mutate the live cache or create a difference from a freshly loaded instance.

Run the new tests against `020f0b1` and record the expected four failures before production edits.

- [ ] **Step 2: Implement the minimum structural fixes**

- Build read unions from alternate-only records followed by the entire preferred mapping.
- Use a write-aware recursive element traversal that synchronizes `elements/%el` at every ancestor before descending.
- Apply newest-first iteration consistently to nested workflow buckets.
- Deep-copy a custom workflow payload before defaults, insertion, and persistence.
- Do not alter unrelated BubbleAppMapper behavior, public method signatures, or non-discovery runtime code.

- [ ] **Step 3: Verify focused and clean full-suite behavior**

Run the new regressions, then the three focused discovery files. Because the primary checkout contains unrelated untracked duplicate test files, run the clean full Python suite from a temporary detached worktree at the committed HEAD, using the existing venv interpreter with `PYTHONPATH=<temp-worktree>/src`.

Also run Ruff on changed tracked files, MyPy on `src`, the runtime coverage and agent-routing smokes, and `git diff --check`.

- [ ] **Step 4: Commit, review, push, and update PR #17**

Stage only the plan, `bubble_sdk.py`, and the two intended tracked test files. Inspect the staged diff, commit intentionally, obtain independent spec/quality review, push the existing branch, update PR #17, and verify the remote head. Keep the PR Draft.
