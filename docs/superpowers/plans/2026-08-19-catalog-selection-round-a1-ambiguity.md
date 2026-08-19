# Round A.1 Natural-Language Ambiguity Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Round A.1 with a deterministic natural-language selection matrix for closely related MCP tools.

**Architecture:** Add a checked-in ambiguity corpus and a dedicated runner that evaluates catalog search against canonical, reversed, and rotated schema order. Keep exact-name coverage separate, make only declarative scorer changes, and wire the new report into checkout audits and catalog quality.

**Tech Stack:** Python 3.11+, JSON fixtures, pytest, Ruff, MyPy, existing MCP schema registry and catalog search.

**Spec:** `docs/superpowers/specs/2026-08-19-catalog-selection-round-a1-ambiguity-design.md`

## Global Constraints

- Keep all 327 public MCP names and schemas unchanged.
- Keep all 207 packaged legacy CLI operation commands and stage-1 relationships unchanged.
- Do not add the modern nested CLI map; Round A.2 owns it.
- Use no LLM, network, Bubble profile, authentication, or editor state.
- Preserve exact-name fast-path behavior, preview defaults, confirmation gates, dispatch, and result contracts.
- Reject corpus and schema drift explicitly; do not silently skip malformed or missing cases.

---

### Task 1: Add the curated ambiguity corpus and RED runner contract

**Files:**
- Create: `tests/fixtures/evals/catalog-ambiguity.json`
- Create: `tests/unit/test_catalog_ambiguity.py`
- Create: `src/bubble_mcp/harness/catalog_ambiguity.py`

**Interfaces:**
- Consumes: `list_tool_schemas()` and `search_tool_catalog(query, limit, tool_schemas)`.
- Produces: `load_ambiguity_cases(path: Path | None = None) -> list[dict[str, Any]]` and `catalog_ambiguity_report(tool_schemas: Iterable[Mapping[str, Any]] | None = None, cases: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]`.

- [ ] **Step 1: Write exactly 27 fixture cases across eight families**

Use this exact record shape and cover every family from the spec:

```json
{
  "id": "visual.update_text_content",
  "family": "visual_updates",
  "query": "replace the text Old with New in the text element on index",
  "expected_tool": "update_text",
  "contrast_tools": ["update_text_element"]
}
```

Include paired cases for cache refresh, query/data-source building, Figma sync,
text and image updates, reusable definition/instance creation, deletion
lifecycle, workflow/event creation, and HTML element/style import.

- [ ] **Step 2: Write failing validation and report tests**

Assert:

```python
def test_catalog_ambiguity_matrix_passes_all_required_families() -> None:
    report = catalog_ambiguity_report()
    assert report["ok"] is True
    assert report["summary"]["case_count"] == 27
    assert report["summary"]["family_count"] == 8
    assert report["summary"]["failed_cases"] == 0
    assert report["failures"] == []


def test_ambiguity_report_is_identical_for_reversed_schema_input() -> None:
    schemas = list_tool_schemas()
    assert catalog_ambiguity_report(schemas) == catalog_ambiguity_report(reversed(schemas))
```

Also test duplicate IDs, duplicate queries, missing contrast tools, missing
expected tools, expected tools repeated in `contrast_tools`, and malformed
records. Each must raise `ValueError` naming the offending case.

- [ ] **Step 3: Run RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/test_catalog_ambiguity.py -q
```

Expected: failure because the runner does not exist or because current lexical
ranking selects the wrong tool for multiple cases.

- [ ] **Step 4: Implement the loader and evidence report without ranking changes**

The report top-level shape is:

```python
{
    "ok": bool,
    "summary": {
        "case_count": int,
        "family_count": int,
        "canonical_ok": int,
        "reversed_ok": int,
        "rotated_ok": int,
        "order_independent": int,
        "failed_cases": int,
    },
    "results": list[dict[str, Any]],
    "failures": list[dict[str, Any]],
}
```

Derive required arguments from each expected schema, evaluate `limit=5`, sort
results by case ID, and compare full `(name, score, required)` tuples across all
three orderings. Reject duplicate candidate schema names.

- [ ] **Step 5: Run the runner tests and record the real RED mismatches**

Run the Task 1 command again. Confirm failures name the wrong winners and are
not fixture-loader errors.

- [ ] **Step 6: Commit the RED boundary**

```bash
git add tests/fixtures/evals/catalog-ambiguity.json tests/unit/test_catalog_ambiguity.py src/bubble_mcp/harness/catalog_ambiguity.py
git commit -m "test: add Round A.1 ambiguity matrix"
```

---

### Task 2: Make natural-language ranking deterministic across ambiguity families

**Files:**
- Modify: `src/bubble_mcp/server/agent_guide.py`
- Modify: `tests/unit/test_mcp_server.py`
- Modify: `tests/unit/test_catalog_ambiguity.py`

**Interfaces:**
- Consumes: normalized query terms, schema name, description, properties, and docs enrichment inside `_score_tool_catalog_match()`.
- Produces: declarative semantic bonuses that preserve the existing `(score, compact_schema)` return contract.

- [ ] **Step 1: Add focused scorer regressions for every exposed defect class**

Add parameterized tests shaped as:

```python
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("build source query json with query_source_type and constraints", "build_source_query_json"),
        ("sync figma style from the local bridge", "sync_figma_style"),
        ("soft delete a recoverable data type", "delete_data_type"),
        ("create visual elements from an html section", "create_from_html"),
    ],
)
def test_tool_search_disambiguates_related_capabilities(query: str, expected: str) -> None:
    assert search_tool_catalog(query, limit=1)["matches"][0]["name"] == expected
```

- [ ] **Step 2: Implement minimal declarative semantic signals**

Add a focused helper such as:

```python
def _semantic_tool_bonus(name: str, normalized_query: str, terms: set[str]) -> int:
    ...
```

Use composable term/phrase signals for contract distinctions (`soft` versus
`permanently`, `instance`, `tokens`, `style`, `source query`, `data source`,
`replace source/content`, general layout/property changes, and HTML import
outcomes). Do not match full fixture strings. Apply the bonus inside the normal
scoring path and retain final alphabetical tie-breaking.

- [ ] **Step 3: Run GREEN focused tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/test_catalog_ambiguity.py tests/unit/test_mcp_server.py -q
```

Expected: all pass, with every corpus case green across canonical, reversed,
and rotated schema orders.

- [ ] **Step 4: Run exact-name and eval compatibility tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/test_catalog_selection.py tests/unit/test_eval_runner.py tests/unit/test_runtime_smoke.py -q
```

Expected: all pass with 327/327 exact-name coverage unchanged.

- [ ] **Step 5: Run static checks and commit ranking**

```bash
../../.venv/bin/ruff check src/bubble_mcp/server/agent_guide.py src/bubble_mcp/harness/catalog_ambiguity.py tests/unit/test_catalog_ambiguity.py tests/unit/test_mcp_server.py
../../.venv/bin/mypy src/bubble_mcp/server/agent_guide.py src/bubble_mcp/harness/catalog_ambiguity.py
git diff --check
git add src/bubble_mcp/server/agent_guide.py tests/unit/test_mcp_server.py tests/unit/test_catalog_ambiguity.py
git commit -m "fix: disambiguate natural-language catalog selection"
```

---

### Task 3: Add executable audit, catalog-quality gate, and A.1 documentation

**Files:**
- Create: `scripts/audit_catalog_ambiguity.py`
- Modify: `src/bubble_mcp/catalog_quality.py`
- Modify: `tests/unit/test_catalog_quality.py`
- Modify: `tests/unit/test_catalog_ambiguity.py`
- Modify: `docs/harness-and-evals.md`
- Modify: `docs/optimization-roadmap.md`

**Interfaces:**
- Consumes: `catalog_ambiguity_report()`.
- Produces: checkout-runnable JSON audit and catalog-quality check `deterministic_ambiguity_matrix`.

- [ ] **Step 1: Write failing audit and quality tests**

Assert the script runs from the checkout after removing `PYTHONPATH`, returns
exit code 0, and emits a passing JSON report. Assert catalog quality includes:

```python
{
    "name": "deterministic_ambiguity_matrix",
    "ok": True,
    "issue_count": 0,
    "case_count": 27,
    "family_count": 8,
}
```

Monkeypatch a wrong-tool failure and a non-OK report without failures; verify
both become issues naming the matrix and case.

- [ ] **Step 2: Run RED audit tests**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/test_catalog_ambiguity.py tests/unit/test_catalog_quality.py -q
```

Expected: failures because the script and quality check do not exist.

- [ ] **Step 3: Implement the script and quality integration**

Follow the bootstrap pattern in `scripts/audit_catalog_selection.py`. Convert
each runner failure to a catalog-quality issue with check
`deterministic_ambiguity_matrix`, scope `tool`, field `selection`, and a message
containing case ID, expected tool, and actual tool. Add the check policy text to
the report.

- [ ] **Step 4: Document operation and the A.1/A.2 boundary**

Document both A.1 audits in `docs/harness-and-evals.md`. Update the roadmap to
mark stage 2 complete, list the matrix families and actual counts, state that no
network/profile was used, and leave the modern nested CLI explicitly in A.2.

- [ ] **Step 5: Run focused gates and commit**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/test_catalog_ambiguity.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_selection.py tests/unit/test_mcp_server.py -q
PYTHONPATH=src ../../.venv/bin/python scripts/audit_catalog_selection.py
PYTHONPATH=src ../../.venv/bin/python scripts/audit_catalog_ambiguity.py
../../.venv/bin/ruff check scripts/audit_catalog_ambiguity.py src/bubble_mcp/catalog_quality.py src/bubble_mcp/harness/catalog_ambiguity.py tests/unit/test_catalog_ambiguity.py tests/unit/test_catalog_quality.py
../../.venv/bin/mypy src/bubble_mcp/catalog_quality.py src/bubble_mcp/harness/catalog_ambiguity.py
git diff --check
git add scripts/audit_catalog_ambiguity.py src/bubble_mcp/catalog_quality.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_ambiguity.py docs/harness-and-evals.md docs/optimization-roadmap.md
git commit -m "chore: gate Round A.1 ambiguity coverage"
```

---

### Task 4: Complete verification, independent review, and closeout evidence

**Files:**
- Modify: `docs/optimization-roadmap.md`

**Interfaces:**
- Consumes: both A.1 reports, complete test/static output, runtime audit output, and branch diff.
- Produces: fresh reproducible closeout evidence for Round A.1.

- [ ] **Step 1: Run the complete local matrix**

```bash
PYTHONPATH=src ../../.venv/bin/python -m pytest -q
npm test
../../.venv/bin/ruff check .
../../.venv/bin/mypy src
PYTHONPATH=src ../../.venv/bin/python scripts/audit_sensitive_paths.py .
PYTHONPATH=src ../../.venv/bin/python scripts/audit_cli_catalog.py
PYTHONPATH=src ../../.venv/bin/python scripts/audit_catalog_selection.py
PYTHONPATH=src ../../.venv/bin/python scripts/audit_catalog_ambiguity.py
PYTHONPATH=src ../../.venv/bin/python scripts/run_runtime_smoke.py --suite coverage
PYTHONPATH=src ../../.venv/bin/python scripts/run_runtime_smoke.py --suite agent-routing
git diff --check
```

Expected: all tests and static checks pass; CLI parity remains 205 direct, 1
alias, 1 exclusion, 122 MCP-only, and 0 missing; exact selection remains
327/327; every ambiguity case passes all three orderings; both runtime suites
report zero failures.

- [ ] **Step 2: Request independent review**

Provide the reviewer with the stage-2 spec, this plan, `origin/main` as base,
branch HEAD, the complete diff, and fresh verification evidence. Resolve every
Critical or Important finding and rerun affected gates.

- [ ] **Step 3: Record actual evidence**

Replace roadmap stage-2 planned wording with the exact Python and Node test
counts, matrix case/family totals, static results, audit totals, smoke run IDs,
and any infrastructure-only limitation. Do not copy old counts or claim an
unexecuted gate passed.

- [ ] **Step 4: Commit evidence and verify branch scope**

```bash
git add docs/optimization-roadmap.md
git commit -m "docs: close Round A.1 selection evidence"
git status --short
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Expected: only the approved stage-2 spec, plan, corpus, runner, scorer, audit,
quality integration, tests, and documentation are present; the worktree is
clean.

## Self-Review

- Spec coverage: all eight ambiguity families, deterministic orders, schema
  contracts, failure diagnostics, audit, quality gate, compatibility, full
  verification, and A.2 boundary map to Tasks 1-4.
- Placeholder scan: no provisional or undefined implementation step remains.
- Type consistency: the loader/report signatures and report keys are identical
  across tasks; quality consumes the same report defined in Task 1.
