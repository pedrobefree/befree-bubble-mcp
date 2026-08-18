# Round A.1 Deterministic Catalog Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, stable MCP-to-legacy-CLI inventory and deterministic exact-name selection eval for every public MCP tool.

**Architecture:** Add a typed read-only inventory derived from `list_tool_schemas()` and the packaged legacy parser source, then make the existing parity audit consume it. Reuse the production `bubble_tool_search` ranker with an injectable catalog to evaluate every tool against canonical and reversed catalog order, and expose the resulting coverage report through a script and catalog-quality gate.

**Tech Stack:** Python 3.11, dataclasses, pytest, existing MCP schema registry, legacy CLI AST discovery, existing catalog search ranker, Ruff, MyPy.

**Spec:** `docs/superpowers/specs/2026-08-18-catalog-selection-round-a1-design.md`

## Global Constraints

- Cover all 327 public MCP tools and all 207 packaged legacy CLI operation commands.
- Preserve 205 direct mappings, `create-reusable-type` to `create_reusable`, and the intentional `reset-tmp` exclusion.
- Derive catalog and command names from authoritative registries; do not add a second handwritten name list.
- Produce stable ordering and byte-stable JSON independent of registry or parser iteration order.
- Every MCP tool must have one deterministic selection case; missing coverage fails closed.
- Selection must be local and independent of catalog enumeration order, network access, profiles, LLMs, and application state.
- Preserve public MCP names, schemas, dispatch, preview defaults, confirmation gates, payloads, and result contracts.
- Do not model the modern nested `bubble-mcp` CLI; it belongs to Round A.2.
- Do not implement the richer natural-language ambiguity matrix; it is the second stage of Round A.1.

---

### Task 1: Shared MCP and legacy CLI inventory

**Files:**
- Create: `src/bubble_mcp/catalog_inventory.py`
- Create: `tests/unit/test_catalog_inventory.py`
- Modify: `src/bubble_mcp/catalog_audit.py`
- Modify: `tests/unit/test_catalog_audit.py`

**Interfaces:**
- Consumes: `list_tool_schemas() -> list[dict[str, Any]]`, `legacy_cli_commands() -> tuple[str, ...]`, `LEGACY_CLI_ALIASES`, and `LEGACY_CLI_EXCLUSIONS`.
- Produces: `CatalogInventoryRecord`, `build_catalog_inventory(tool_schemas, *, cli_commands=None) -> tuple[CatalogInventoryRecord, ...]`, `serialize_catalog_inventory(records) -> str`, and a parity report derived from those records.

- [ ] **Step 1: Write the failing inventory tests**

Create `tests/unit/test_catalog_inventory.py` with these contracts:

```python
import json

from bubble_mcp.catalog_inventory import (
    build_catalog_inventory,
    serialize_catalog_inventory,
)
from bubble_mcp.server.schemas import list_tool_schemas


def test_current_catalog_inventory_is_complete_and_explicit() -> None:
    records = build_catalog_inventory(list_tool_schemas())
    mcp_records = [record for record in records if record.mcp_tool is not None]

    assert len(mcp_records) == 327
    assert len({record.mcp_tool for record in mcp_records}) == 327
    assert sum(record.relationship == "direct" for record in records) == 205
    assert sum(record.relationship == "alias" for record in records) == 1
    assert sum(record.relationship == "excluded" for record in records) == 1
    assert sum(record.relationship == "mcp_only" for record in records) == 121
    assert next(record for record in records if record.legacy_command == "create-reusable-type").mcp_tool == "create_reusable"
    assert next(record for record in records if record.legacy_command == "reset-tmp").mcp_tool is None
    assert all(record.selection_case_id for record in mcp_records)
    assert all(record.selection_query for record in mcp_records)


def test_inventory_order_and_serialization_ignore_input_order() -> None:
    schemas = list_tool_schemas()
    forward = build_catalog_inventory(schemas)
    reversed_input = build_catalog_inventory(list(reversed(schemas)), cli_commands=reversed(tuple(record.legacy_command for record in forward if record.legacy_command)))

    assert forward == reversed_input
    assert serialize_catalog_inventory(forward) == serialize_catalog_inventory(reversed_input)
    assert json.loads(serialize_catalog_inventory(forward))[0]["relationship"] in {"alias", "direct", "excluded", "mcp_only"}
```

Add focused parity assertions to `tests/unit/test_catalog_audit.py`:

```python
def test_parity_report_is_derived_from_complete_inventory() -> None:
    report = cli_catalog_parity_report(tool["name"] for tool in list_tool_schemas())

    assert report["mcp_tool_count"] == 327
    assert report["direct_match_count"] == 205
    assert report["alias_count"] == 1
    assert report["excluded_count"] == 1
    assert report["mcp_only_count"] == 121
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_inventory.py tests/unit/test_catalog_audit.py -q
```

Expected: collection fails because `bubble_mcp.catalog_inventory` does not exist.

- [ ] **Step 3: Implement the typed inventory**

Create `src/bubble_mcp/catalog_inventory.py` with this public shape:

```python
from dataclasses import asdict, dataclass
import json
from collections.abc import Iterable, Mapping
from typing import Any, Literal


Relationship = Literal["direct", "alias", "excluded", "mcp_only"]


@dataclass(frozen=True, slots=True)
class CatalogInventoryRecord:
    mcp_tool: str | None
    legacy_command: str | None
    relationship: Relationship
    canonical_mcp_tool: str | None
    selection_case_id: str | None
    selection_query: str | None
    essential_args: tuple[str, ...]
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["essential_args"] = list(self.essential_args)
        return payload


def serialize_catalog_inventory(records: Iterable[CatalogInventoryRecord]) -> str:
    ordered = sorted(records, key=lambda record: (record.mcp_tool or "", record.legacy_command or ""))
    return json.dumps([record.to_dict() for record in ordered], indent=2, sort_keys=True) + "\n"
```

Implementation rules:

- validate non-empty unique MCP names;
- derive required argument names from `inputSchema.required`, sorted into `essential_args`;
- assign `selection_case_id=f"catalog.exact.{mcp_tool}"` and `selection_query=mcp_tool` to every MCP record;
- normalize direct CLI names with `command.replace("-", "_")`;
- apply only `LEGACY_CLI_ALIASES` and `LEGACY_CLI_EXCLUSIONS` for exceptions;
- raise `ValueError` naming duplicate tools, duplicate commands, aliases whose target is absent, and unmapped commands;
- return records sorted by `(mcp_tool or "~", legacy_command or "")`, so the CLI-only exclusion follows MCP records.

Refactor `cli_catalog_parity_report()` to call `build_catalog_inventory()` and derive its direct, alias, excluded, missing, MCP-only, and total counts from records. Retain the existing output keys and add `mcp_tool_count` and `mcp_only_count`; no caller-facing key may be removed.

- [ ] **Step 4: Run focused tests and static checks**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_inventory.py tests/unit/test_catalog_audit.py -q
./.venv/bin/ruff check src/bubble_mcp/catalog_inventory.py src/bubble_mcp/catalog_audit.py tests/unit/test_catalog_inventory.py tests/unit/test_catalog_audit.py
./.venv/bin/mypy src/bubble_mcp/catalog_inventory.py src/bubble_mcp/catalog_audit.py
```

Expected: all tests and static checks pass.

- [ ] **Step 5: Commit the inventory boundary**

```bash
git add src/bubble_mcp/catalog_inventory.py src/bubble_mcp/catalog_audit.py tests/unit/test_catalog_inventory.py tests/unit/test_catalog_audit.py
git commit -m "feat: add deterministic catalog inventory"
```

---

### Task 2: Complete deterministic selection evaluation

**Files:**
- Create: `src/bubble_mcp/harness/catalog_selection.py`
- Create: `tests/unit/test_catalog_selection.py`
- Modify: `src/bubble_mcp/server/agent_guide.py`
- Modify: `tests/unit/test_mcp_server.py`

**Interfaces:**
- Consumes: `build_catalog_inventory()`, `list_tool_schemas()`, and the production catalog ranking rules in `search_tool_catalog()`.
- Produces: optional `tool_schemas` injection on `search_tool_catalog()`, plus `catalog_selection_report(tool_schemas=None) -> dict[str, Any]` with per-case diagnostics and aggregate coverage.

- [ ] **Step 1: Write failing selection and order-independence tests**

Create `tests/unit/test_catalog_selection.py`:

```python
from bubble_mcp.harness.catalog_selection import catalog_selection_report
from bubble_mcp.server.schemas import list_tool_schemas


def test_every_mcp_tool_has_passing_deterministic_selection_evidence() -> None:
    report = catalog_selection_report()

    assert report["ok"] is True
    assert report["summary"] == {
        "tool_count": 327,
        "case_count": 327,
        "canonical_ok": 327,
        "reordered_ok": 327,
        "order_independent": 327,
        "missing_cases": 0,
        "failed_cases": 0,
    }
    assert report["failures"] == []
    assert all(result["case_id"].startswith("catalog.exact.") for result in report["results"])


def test_selection_report_is_identical_for_reversed_schema_input() -> None:
    schemas = list_tool_schemas()

    assert catalog_selection_report(schemas) == catalog_selection_report(list(reversed(schemas)))


def test_selection_failure_names_case_expected_and_actual_tool(monkeypatch) -> None:
    import bubble_mcp.harness.catalog_selection as selection

    real_search = selection.search_tool_catalog

    def wrong_create_text(query, **kwargs):
        if query == "create_text":
            return {"matches": [{"name": "create_button", "required": []}]}
        return real_search(query, **kwargs)

    monkeypatch.setattr(selection, "search_tool_catalog", wrong_create_text)

    report = catalog_selection_report()

    assert report["ok"] is False
    assert any({"case_id", "expected_tool", "actual_tool", "essential_args"} <= failure.keys() for failure in report["failures"])
```

Add a production-ranker injection regression to `tests/unit/test_mcp_server.py`:

```python
def test_tool_search_exact_name_is_independent_of_catalog_order() -> None:
    schemas = list_tool_schemas()

    forward = search_tool_catalog("create_text", limit=1, tool_schemas=schemas)
    reverse = search_tool_catalog("create_text", limit=1, tool_schemas=list(reversed(schemas)))

    assert forward["matches"] == reverse["matches"]
    assert forward["matches"][0]["name"] == "create_text"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_selection.py tests/unit/test_mcp_server.py::test_tool_search_exact_name_is_independent_of_catalog_order -q
```

Expected: collection fails because `bubble_mcp.harness.catalog_selection` does not exist and `search_tool_catalog` does not accept `tool_schemas`.

- [ ] **Step 3: Make the production ranker testable without changing its default behavior**

Change the signature in `src/bubble_mcp/server/agent_guide.py` to:

```python
def search_tool_catalog(
    query: str,
    *,
    limit: int = 8,
    tool_schemas: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
```

Use `list_tool_schemas()` only when `tool_schemas is None`; otherwise copy the supplied mappings into plain dictionaries. Preserve the existing scoring, alphabetical tie-break, compact result shape, `limit` clamping, and public caller behavior.

- [ ] **Step 4: Implement the deterministic coverage report**

Create `src/bubble_mcp/harness/catalog_selection.py` with the interface from this task and return this exact top-level shape:

```python
{
    "ok": not failures,
    "summary": summary,
    "results": results,
    "failures": failures,
}
```

For each MCP inventory record:

- run `search_tool_catalog(record.selection_query, limit=1, tool_schemas=canonical_schemas)`;
- repeat with `list(reversed(canonical_schemas))`;
- compare the first match name with `record.mcp_tool`;
- compare the sorted returned `required` names with `record.essential_args`;
- record `case_id`, `query`, `expected_tool`, `actual_tool`, `reordered_actual_tool`, `essential_args`, `actual_required`, `canonical_ok`, `reordered_ok`, and `order_independent`;
- add every failing result to `failures` without reducing it to aggregate counts;
- sort input schemas and final results by tool name so reports are identical for forward and reversed caller input;
- set `ok` only when every inventory MCP tool has exactly one case and every canonical, reordered, argument, and order-independence check passes.

- [ ] **Step 5: Run focused tests and static checks**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_selection.py tests/unit/test_mcp_server.py::test_tool_search_exact_name_is_independent_of_catalog_order tests/unit/test_eval_runner.py -q
./.venv/bin/ruff check src/bubble_mcp/harness/catalog_selection.py src/bubble_mcp/server/agent_guide.py tests/unit/test_catalog_selection.py tests/unit/test_mcp_server.py
./.venv/bin/mypy src/bubble_mcp/harness/catalog_selection.py src/bubble_mcp/server/agent_guide.py
```

Expected: all tests and static checks pass, with 327 passing selection cases.

- [ ] **Step 6: Commit deterministic selection coverage**

```bash
git add src/bubble_mcp/harness/catalog_selection.py src/bubble_mcp/server/agent_guide.py tests/unit/test_catalog_selection.py tests/unit/test_mcp_server.py
git commit -m "test: cover deterministic selection for every MCP tool"
```

---

### Task 3: Executable audit, catalog-quality gate, and A.1 documentation

**Files:**
- Create: `scripts/audit_catalog_selection.py`
- Modify: `src/bubble_mcp/catalog_quality.py`
- Modify: `tests/unit/test_catalog_quality.py`
- Modify: `docs/harness-and-evals.md`
- Modify: `docs/optimization-roadmap.md`

**Interfaces:**
- Consumes: `catalog_selection_report()` and the shared parity report from Task 1.
- Produces: checkout-runnable JSON audit, catalog-quality check named `deterministic_selection_coverage`, and documented stage boundary between A.1 deterministic coverage, A.1 ambiguity evals, and A.2 modern CLI mapping.

- [ ] **Step 1: Write failing executable and quality-gate tests**

Add to `tests/unit/test_catalog_quality.py`:

```python
def test_catalog_quality_includes_complete_deterministic_selection_coverage() -> None:
    report = catalog_quality_report()
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["deterministic_selection_coverage"] == {
        "name": "deterministic_selection_coverage",
        "ok": True,
        "issue_count": 0,
    }
    assert report["summary"]["tool_count"] == 327
```

Add a subprocess test to `tests/unit/test_catalog_selection.py`:

```python
def test_selection_audit_runs_from_checkout_without_pythonpath() -> None:
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "scripts/audit_catalog_selection.py"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["summary"]["case_count"] == 327
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_selection.py::test_selection_audit_runs_from_checkout_without_pythonpath tests/unit/test_catalog_quality.py::test_catalog_quality_includes_complete_deterministic_selection_coverage -q
```

Expected: the script is absent and the catalog-quality check is missing.

- [ ] **Step 3: Add the executable audit and quality check**

Create `scripts/audit_catalog_selection.py` using the same checkout bootstrap pattern as `scripts/audit_cli_catalog.py`, call `catalog_selection_report()`, print `json.dumps(report, indent=2, sort_keys=True)`, and return exit code 0 only when `report["ok"]` is true.

In `src/bubble_mcp/catalog_quality.py`, add a `_deterministic_selection_check()` that converts each failed case into an issue with:

```python
{
    "check": "deterministic_selection_coverage",
    "scope": "tool",
    "name": failure["expected_tool"],
    "field": "selection",
    "message": f"{failure['case_id']}: expected {failure['expected_tool']}, got {failure['actual_tool']}",
}
```

Append the check after `cli_catalog_parity`, include it in the policy section, and preserve every existing quality check and issue shape.

- [ ] **Step 4: Document the commands and stage boundaries**

Add a `Deterministic Catalog Selection` section to `docs/harness-and-evals.md` containing:

```bash
PYTHONPATH=src python scripts/audit_catalog_selection.py
```

Document that the report covers exact-name deterministic selection for every MCP tool, verifies required-argument metadata and reversed-order stability, uses no network or Bubble profile, and is a structural baseline rather than the natural-language ambiguity matrix.

Add a Round A.1 entry to `docs/optimization-roadmap.md` recording:

- stage 1 owns the 327 MCP tools and 207 legacy CLI commands;
- stage 2 will add ambiguous natural-language family evals after stage 1 closes;
- Round A.2 owns the modern nested CLI leaf-command map;
- no consolidation or alias migration occurs in stage 1.

- [ ] **Step 5: Run the full stage validation matrix**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_catalog_inventory.py tests/unit/test_catalog_audit.py tests/unit/test_catalog_selection.py tests/unit/test_eval_runner.py tests/unit/test_catalog_quality.py tests/unit/test_mcp_server.py -q
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
PYTHONPATH=src ./.venv/bin/python scripts/audit_catalog_selection.py
./.venv/bin/ruff check src/bubble_mcp/catalog_inventory.py src/bubble_mcp/catalog_audit.py src/bubble_mcp/harness/catalog_selection.py src/bubble_mcp/catalog_quality.py src/bubble_mcp/server/agent_guide.py scripts/audit_catalog_selection.py tests/unit/test_catalog_inventory.py tests/unit/test_catalog_audit.py tests/unit/test_catalog_selection.py tests/unit/test_catalog_quality.py tests/unit/test_mcp_server.py
./.venv/bin/mypy src/bubble_mcp/catalog_inventory.py src/bubble_mcp/catalog_audit.py src/bubble_mcp/harness/catalog_selection.py src/bubble_mcp/catalog_quality.py src/bubble_mcp/server/agent_guide.py
rtk git diff --check
```

Expected: all tests and static checks pass; CLI audit reports 327 MCP tools, 207 CLI commands, 205 direct mappings, one alias, one exclusion, 121 MCP-only tools, and zero missing mappings; selection audit reports 327/327 canonical and reordered cases passing.

- [ ] **Step 6: Commit the executable gate and documentation**

```bash
git add scripts/audit_catalog_selection.py src/bubble_mcp/catalog_quality.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_selection.py docs/harness-and-evals.md docs/optimization-roadmap.md
git commit -m "chore: gate complete deterministic catalog selection"
```

---

### Task 4: Final compatibility validation and evidence

**Files:**
- Modify: `docs/optimization-roadmap.md`

**Interfaces:**
- Consumes: the completed inventory, selection report, parity audit, focused validation results, and current branch diff.
- Produces: recorded executable evidence for closing stage 1 and a clean review surface for stage 2 planning.

- [ ] **Step 1: Run repository-wide compatibility gates**

Because Task 2 changes shared catalog-search behavior and Task 3 changes catalog quality, run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
npm test
./.venv/bin/ruff check src tests scripts
./.venv/bin/mypy src
PYTHONPATH=src ./.venv/bin/python scripts/audit_sensitive_paths.py .
PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
PYTHONPATH=src ./.venv/bin/python scripts/audit_catalog_selection.py
PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite coverage
PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite agent-routing
rtk git diff --check
```

Expected: all Python and Node tests pass; Ruff and MyPy pass; sensitive-path, catalog parity, deterministic selection, runtime coverage, and existing agent-routing gates report `ok: true`.

- [ ] **Step 2: Record exact fresh evidence**

Update the Round A.1 section in `docs/optimization-roadmap.md` with the actual fresh Python and Node test counts, inventory counts, selection totals, static-check results, and runtime smoke results. Record any infrastructure-only limitation separately from executable local evidence; do not claim an unexecuted gate passed.

- [ ] **Step 3: Verify the complete branch diff**

Run:

```bash
git status --short
git diff main...HEAD --stat
git diff main...HEAD --check
git log --oneline main..HEAD
```

Expected: only the approved Round A.1 specification, plan, inventory, selection harness, audit integration, tests, and documentation are present; the worktree is clean after the evidence commit.

- [ ] **Step 4: Commit final evidence**

```bash
git add docs/optimization-roadmap.md
git commit -m "docs: record Round A.1 deterministic selection evidence"
```
