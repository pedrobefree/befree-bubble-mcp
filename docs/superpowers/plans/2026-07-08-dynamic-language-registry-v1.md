# Dynamic Language Registry V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Bubble MCP consumable by BMAD, Superpowers, SDD, and future framework adapters as a dynamic, low-token, versioned implementation language instead of a static full catalog dump.

**Architecture:** Add a `bubble_mcp.language` package that builds compact runtime registry indexes from native tools, enabled extension tools, installed skills, recipes, runtime rules, and local learning records. Expose low-token MCP tools for index, scoped query, lazy tool detail, diff, framework language pack, and framework program compilation; the framework layer consumes these APIs instead of embedding static tool documentation.

**Tech Stack:** Python 3.11, existing Bubble MCP stdio tool dispatcher, existing catalog/search/runbook/extension/skill/learning stores, local JSON snapshot storage under `BUBBLE_MCP_CONFIG_DIR`, pytest, ruff, mypy.

---

## File Structure

- `src/bubble_mcp/language/__init__.py`
  - Public exports for language registry, query, diff, framework packs, and compile-program functions.
- `src/bubble_mcp/language/models.py`
  - Typed dataclasses/constants for detail levels, registry entries, registry snapshots, framework packs, program steps, and compile results.
- `src/bubble_mcp/language/registry.py`
  - Builds the dynamic language index and registry version from `list_tool_schemas()`, `enabled_extension_tool_schemas()`, `list_skills()`, `list_learning_records()`, `catalog_coverage_report()`, and `task_runbook()` route/recipe data.
- `src/bubble_mcp/language/query.py`
  - Provides scoped search and lazy detail expansion over the current registry without returning the full catalog by default.
- `src/bubble_mcp/language/diff.py`
  - Stores compact registry snapshots and returns added/changed/removed entries between registry versions.
- `src/bubble_mcp/language/framework_pack.py`
  - Produces BMAD/Superpowers/SDD-shaped language packs using index + scoped query + runtime rules + recipes.
- `src/bubble_mcp/language/compiler.py`
  - Compiles a compact framework "program" into preview-safe MCP tool calls and validation steps; does not execute writes.
- `src/bubble_mcp/server/schema_families.py`
  - Adds schemas for `bubble_language_index`, `bubble_language_query`, `bubble_language_tool_detail`, `bubble_language_diff`, `bubble_framework_language_pack`, and `bubble_framework_compile_program`.
- `src/bubble_mcp/server/tools.py`
  - Dispatches new MCP language tools.
- `src/bubble_mcp/server/agent_catalog.py`
  - Adds concise descriptions and annotations so agents find these APIs before dumping `tools/list`.
- `src/bubble_mcp/runtime_coverage.py`
  - Adds new language tools to native coverage.
- `src/bubble_mcp/cli/main.py`
  - Adds optional diagnostic CLI equivalents under `bubble-mcp language`.
- `docs/framework-adapters.md`
  - Updates framework docs to describe dynamic language consumption and token strategy.
- `docs/cli-reference.md`
  - Documents language commands and MCP tool names.
- `tests/unit/test_language_registry.py`
  - Unit tests for index/version/query/detail/diff/framework packs/compiler.
- `tests/unit/test_mcp_server.py`
  - MCP schema/dispatch tests.
- `tests/unit/test_cli_commands.py`
  - CLI smoke tests for diagnostics.

---

### Task 1: Dynamic Language Models And Compact Index

**Files:**
- Create: `src/bubble_mcp/language/__init__.py`
- Create: `src/bubble_mcp/language/models.py`
- Create: `src/bubble_mcp/language/registry.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing model/index tests**

Add this test to `tests/unit/test_language_registry.py`:

```python
from bubble_mcp.language.registry import build_language_index


def test_language_index_is_compact_versioned_and_counts_dynamic_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = build_language_index(profile="cliente2")

    assert result["ok"] is True
    assert result["language"] == "bubble-mcp"
    assert result["detail"] == "index"
    assert result["registry_version"].startswith("sha256:")
    assert result["counts"]["tools"] > 250
    assert "visual_editor" in result["families"]
    assert result["runtime_rules_digest"]
    assert "bubble_language_query" in result["entrypoints"]
    assert "tools" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_language_index_is_compact_versioned_and_counts_dynamic_sources -q
```

Expected: failure because `bubble_mcp.language.registry` does not exist.

- [ ] **Step 3: Create model primitives**

Create `src/bubble_mcp/language/models.py`:

```python
"""Typed models for the dynamic Bubble MCP language registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


DetailLevel = Literal["index", "compact", "full"]
ToolSource = Literal["native", "extension"]
RiskLevel = Literal["read_only", "mutating", "destructive"]


@dataclass(frozen=True)
class LanguageToolEntry:
    name: str
    family: str
    source: ToolSource
    description: str
    risk: RiskLevel
    read_only: bool
    destructive: bool
    required: tuple[str, ...]
    properties: tuple[str, ...]
    coverage: str | None = None
    extension_id: str | None = None
    schema_hash: str | None = None

    def to_index(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "family": self.family,
            "source": self.source,
            "risk": self.risk,
            "read_only": self.read_only,
            "destructive": self.destructive,
        }
        if self.coverage:
            payload["coverage"] = self.coverage
        if self.extension_id:
            payload["extension_id"] = self.extension_id
        return payload

    def to_compact(self) -> dict[str, Any]:
        return {
            **self.to_index(),
            "description": self.description,
            "required": list(self.required),
            "properties": list(self.properties),
            "schema_hash": self.schema_hash,
        }
```

- [ ] **Step 4: Implement compact registry index**

Create `src/bubble_mcp/language/registry.py`:

```python
"""Dynamic low-token registry for the Bubble MCP language."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from bubble_mcp.learning.store import list_learning_records
from bubble_mcp.runtime_coverage import catalog_coverage_report, classify_tool
from bubble_mcp.server.agent_catalog import _documentation_family_for_name
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.skills.store import list_skills


RUNTIME_RULES_DIGEST = [
    "Call bubble_task_runbook or bubble_language_query instead of dumping the full catalog.",
    "Use preview-first execution: execute=false before any Bubble mutation.",
    "Use the configured profile app_version unless the user explicitly overrides it.",
    "Resolve targets from real context; do not invent Bubble ids.",
    "Refresh profile cache and verify context after successful writes.",
    "Use bubble_framework_sync_evidence after preview, execution, or validation.",
]

LANGUAGE_ENTRYPOINTS = [
    "bubble_language_index",
    "bubble_language_query",
    "bubble_language_tool_detail",
    "bubble_language_diff",
    "bubble_framework_language_pack",
    "bubble_framework_compile_program",
    "bubble_task_runbook",
    "bubble_tool_search",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _schema_required(tool: dict[str, Any]) -> tuple[str, ...]:
    input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    required = input_schema.get("required") if isinstance(input_schema, dict) else []
    return tuple(str(item) for item in required) if isinstance(required, list) else ()


def _schema_properties(tool: dict[str, Any]) -> tuple[str, ...]:
    input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else {}
    return tuple(sorted(str(key) for key in properties)) if isinstance(properties, dict) else ()


def _risk_from_annotations(tool: dict[str, Any]) -> str:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    if bool(annotations.get("destructiveHint")):
        return "destructive"
    if bool(annotations.get("readOnlyHint")):
        return "read_only"
    return "mutating"


def _schema_hash(tool: dict[str, Any]) -> str:
    body = json.dumps(tool.get("inputSchema") or {}, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _tool_entry(tool: dict[str, Any], coverage_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    name = str(tool.get("name") or "")
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    coverage = coverage_by_name.get(name) or classify_tool(name)
    source = "extension" if coverage.get("coverage") == "extension_preview" else "native"
    family = _documentation_family_for_name(name)
    return {
        "name": name,
        "family": family,
        "source": source,
        "risk": _risk_from_annotations(tool),
        "read_only": bool(annotations.get("readOnlyHint")),
        "destructive": bool(annotations.get("destructiveHint")),
        "required": list(_schema_required(tool)),
        "properties": list(_schema_properties(tool)),
        "description": str(tool.get("description") or ""),
        "coverage": coverage.get("coverage"),
        "engine": coverage.get("engine"),
        "schema_hash": _schema_hash(tool),
    }


def _registry_version(entries: list[dict[str, Any]], *, skill_count: int, learning_count: int) -> str:
    version_payload = {
        "tools": [
            {
                "name": entry["name"],
                "schema_hash": entry["schema_hash"],
                "family": entry["family"],
                "source": entry["source"],
                "risk": entry["risk"],
            }
            for entry in sorted(entries, key=lambda item: item["name"])
        ],
        "skill_count": skill_count,
        "learning_count": learning_count,
        "rules": RUNTIME_RULES_DIGEST,
    }
    body = json.dumps(version_payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def current_language_entries() -> list[dict[str, Any]]:
    coverage_report = catalog_coverage_report(include_tools=True)
    coverage_by_name = {
        str(item.get("tool") or ""): item
        for item in coverage_report.get("tools", [])
        if isinstance(item, dict)
    }
    return [_tool_entry(tool, coverage_by_name) for tool in list_tool_schemas()]


def build_language_index(*, profile: str | None = None) -> dict[str, Any]:
    entries = current_language_entries()
    skills = list_skills()
    learning = list_learning_records()
    family_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for entry in entries:
        family_counts[str(entry["family"])] = family_counts.get(str(entry["family"]), 0) + 1
        source_counts[str(entry["source"])] = source_counts.get(str(entry["source"]), 0) + 1
        risk_counts[str(entry["risk"])] = risk_counts.get(str(entry["risk"]), 0) + 1
    return {
        "ok": True,
        "language": "bubble-mcp",
        "detail": "index",
        "profile": profile,
        "generated_at": _utc_now_iso(),
        "registry_version": _registry_version(entries, skill_count=len(skills), learning_count=len(learning)),
        "counts": {
            "tools": len(entries),
            "skills": len(skills),
            "learning_records": len(learning),
        },
        "families": family_counts,
        "sources": source_counts,
        "risks": risk_counts,
        "runtime_rules_digest": RUNTIME_RULES_DIGEST,
        "entrypoints": LANGUAGE_ENTRYPOINTS,
    }
```

Create `src/bubble_mcp/language/__init__.py`:

```python
"""Dynamic Bubble MCP language registry."""

from bubble_mcp.language.registry import build_language_index, current_language_entries

__all__ = ["build_language_index", "current_language_entries"]
```

- [ ] **Step 5: Run focused test**

Run:

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_language_index_is_compact_versioned_and_counts_dynamic_sources -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/bubble_mcp/language tests/unit/test_language_registry.py
git commit -m "feat: add dynamic language registry index"
```

---

### Task 2: Scoped Query And Lazy Tool Detail

**Files:**
- Modify: `src/bubble_mcp/language/query.py`
- Modify: `src/bubble_mcp/language/__init__.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing query/detail tests**

Append:

```python
from bubble_mcp.language.query import language_query, language_tool_detail


def test_language_query_returns_scoped_compact_matches_without_full_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = language_query(query="create checkout button", families=["visual_editor"], limit=8)

    assert result["ok"] is True
    assert result["detail"] == "compact"
    assert result["matches"]
    assert len(result["matches"]) <= 8
    assert any(match["name"] == "create_button" for match in result["matches"])
    assert all(match["family"] == "visual_editor" for match in result["matches"])
    assert all("inputSchema" not in match for match in result["matches"])


def test_language_tool_detail_lazy_loads_selected_schemas_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = language_tool_detail(["create_button", "bubble_context_find"], detail="full")

    assert result["ok"] is True
    assert [tool["name"] for tool in result["tools"]] == ["create_button", "bubble_context_find"]
    assert all("inputSchema" in tool for tool in result["tools"])
```

- [ ] **Step 2: Run tests to verify failure**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_language_query_returns_scoped_compact_matches_without_full_schema tests/unit/test_language_registry.py::test_language_tool_detail_lazy_loads_selected_schemas_only -q
```

Expected: fail because `language.query` does not exist.

- [ ] **Step 3: Implement query/detail module**

Create `src/bubble_mcp/language/query.py`:

```python
"""Scoped lookup APIs for the Bubble MCP language registry."""

from __future__ import annotations

from typing import Any

from bubble_mcp.language.registry import build_language_index, current_language_entries
from bubble_mcp.server.schemas import list_tool_schemas


def _score_entry(entry: dict[str, Any], query: str) -> int:
    haystack = " ".join(
        [
            str(entry.get("name") or ""),
            str(entry.get("family") or ""),
            str(entry.get("description") or ""),
            " ".join(str(item) for item in entry.get("required", [])),
            " ".join(str(item) for item in entry.get("properties", [])),
        ]
    ).lower()
    terms = [term for term in query.lower().replace("_", " ").split() if term]
    return sum(3 if term in str(entry.get("name") or "").lower() else 1 for term in terms if term in haystack)


def language_query(
    *,
    query: str,
    families: list[str] | None = None,
    sources: list[str] | None = None,
    risks: list[str] | None = None,
    limit: int = 12,
    profile: str | None = None,
) -> dict[str, Any]:
    entries = current_language_entries()
    if families:
        family_set = {str(item) for item in families}
        entries = [entry for entry in entries if entry.get("family") in family_set]
    if sources:
        source_set = {str(item) for item in sources}
        entries = [entry for entry in entries if entry.get("source") in source_set]
    if risks:
        risk_set = {str(item) for item in risks}
        entries = [entry for entry in entries if entry.get("risk") in risk_set]
    scored = [(entry, _score_entry(entry, query)) for entry in entries]
    matches = [entry for entry, score in sorted(scored, key=lambda item: (-item[1], item[0]["name"])) if score > 0]
    if not matches and not query.strip():
        matches = sorted(entries, key=lambda item: item["name"])
    index = build_language_index(profile=profile)
    return {
        "ok": True,
        "language": "bubble-mcp",
        "detail": "compact",
        "registry_version": index["registry_version"],
        "query": query,
        "families": families or [],
        "sources": sources or [],
        "risks": risks or [],
        "limit": limit,
        "matches": [
            {
                key: entry[key]
                for key in (
                    "name",
                    "family",
                    "source",
                    "risk",
                    "read_only",
                    "destructive",
                    "required",
                    "properties",
                    "description",
                    "coverage",
                    "schema_hash",
                )
                if key in entry
            }
            for entry in matches[: max(1, min(limit, 50))]
        ],
    }


def language_tool_detail(tool_names: list[str], *, detail: str = "compact") -> dict[str, Any]:
    requested = [str(name) for name in tool_names if str(name).strip()]
    schemas = {str(tool.get("name") or ""): tool for tool in list_tool_schemas()}
    entries = {str(entry.get("name") or ""): entry for entry in current_language_entries()}
    tools: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in requested:
        schema = schemas.get(name)
        entry = entries.get(name)
        if schema is None or entry is None:
            missing.append(name)
            continue
        if detail == "full":
            tools.append({**schema, "language": {key: value for key, value in entry.items() if key != "description"}})
        else:
            tools.append(
                {
                    key: entry[key]
                    for key in (
                        "name",
                        "family",
                        "source",
                        "risk",
                        "read_only",
                        "destructive",
                        "required",
                        "properties",
                        "description",
                        "coverage",
                        "schema_hash",
                    )
                    if key in entry
                }
            )
    return {"ok": not missing, "detail": detail, "tools": tools, "missing": missing}
```

Update `src/bubble_mcp/language/__init__.py`:

```python
from bubble_mcp.language.query import language_query, language_tool_detail

__all__ = [
    "build_language_index",
    "current_language_entries",
    "language_query",
    "language_tool_detail",
]
```

- [ ] **Step 4: Run focused tests**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_language_query_returns_scoped_compact_matches_without_full_schema tests/unit/test_language_registry.py::test_language_tool_detail_lazy_loads_selected_schemas_only -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/language tests/unit/test_language_registry.py
git commit -m "feat: add scoped language query APIs"
```

---

### Task 3: Registry Snapshot Storage And Diff

**Files:**
- Create: `src/bubble_mcp/language/diff.py`
- Modify: `src/bubble_mcp/language/__init__.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing diff test**

Append:

```python
from bubble_mcp.language.diff import language_diff, save_language_snapshot


def test_language_diff_reports_added_changed_removed_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    old = {
        "registry_version": "sha256:old",
        "entries": [
            {"name": "create_button", "schema_hash": "a", "family": "visual_editor"},
            {"name": "removed_tool", "schema_hash": "r", "family": "custom"},
        ],
    }
    new = {
        "registry_version": "sha256:new",
        "entries": [
            {"name": "create_button", "schema_hash": "b", "family": "visual_editor"},
            {"name": "new_tool", "schema_hash": "n", "family": "extension"},
        ],
    }

    save_language_snapshot(old)
    save_language_snapshot(new)
    result = language_diff(since="sha256:old", current="sha256:new")

    assert result["ok"] is True
    assert result["added"] == ["new_tool"]
    assert result["changed"] == ["create_button"]
    assert result["removed"] == ["removed_tool"]
```

- [ ] **Step 2: Run test to verify failure**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_language_diff_reports_added_changed_removed_entries -q
```

Expected: fail because `language.diff` does not exist.

- [ ] **Step 3: Implement diff module**

Create `src/bubble_mcp/language/diff.py`:

```python
"""Registry snapshot and diff support."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.language.registry import build_language_index, current_language_entries


def _safe_version(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)


def _snapshot_dir() -> Path:
    return get_config_dir() / "language" / "registry-snapshots"


def _snapshot_path(version: str) -> Path:
    return _snapshot_dir() / f"{_safe_version(version)}.json"


def current_language_snapshot(*, profile: str | None = None) -> dict[str, Any]:
    index = build_language_index(profile=profile)
    return {
        "registry_version": index["registry_version"],
        "generated_at": index["generated_at"],
        "entries": [
            {
                "name": entry["name"],
                "schema_hash": entry["schema_hash"],
                "family": entry["family"],
                "source": entry["source"],
                "risk": entry["risk"],
            }
            for entry in current_language_entries()
        ],
    }


def save_language_snapshot(snapshot: dict[str, Any] | None = None, *, profile: str | None = None) -> dict[str, Any]:
    payload = snapshot or current_language_snapshot(profile=profile)
    version = str(payload.get("registry_version") or "")
    if not version:
        raise ValueError("language snapshot requires registry_version.")
    _snapshot_dir().mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(version)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "registry_version": version, "path": str(path)}


def _load_snapshot(version: str) -> dict[str, Any]:
    path = _snapshot_path(version)
    if not path.exists():
        raise ValueError(f"Unknown language registry snapshot: {version}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected language registry snapshot object in {path}")
    return payload


def _entry_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = snapshot.get("entries")
    if not isinstance(entries, list):
        return {}
    return {
        str(entry.get("name") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("name") or "")
    }


def language_diff(*, since: str, current: str | None = None, profile: str | None = None) -> dict[str, Any]:
    current_snapshot = current_language_snapshot(profile=profile) if current is None else _load_snapshot(current)
    if current is None:
        save_language_snapshot(current_snapshot, profile=profile)
    old_snapshot = _load_snapshot(since)
    old_entries = _entry_map(old_snapshot)
    new_entries = _entry_map(current_snapshot)
    added = sorted(name for name in new_entries if name not in old_entries)
    removed = sorted(name for name in old_entries if name not in new_entries)
    changed = sorted(
        name
        for name in new_entries.keys() & old_entries.keys()
        if new_entries[name].get("schema_hash") != old_entries[name].get("schema_hash")
        or new_entries[name].get("family") != old_entries[name].get("family")
        or new_entries[name].get("risk") != old_entries[name].get("risk")
    )
    return {
        "ok": True,
        "since": str(old_snapshot.get("registry_version") or since),
        "current": str(current_snapshot.get("registry_version") or current),
        "added": added,
        "changed": changed,
        "removed": removed,
        "counts": {"added": len(added), "changed": len(changed), "removed": len(removed)},
    }
```

Update `src/bubble_mcp/language/__init__.py` exports:

```python
from bubble_mcp.language.diff import current_language_snapshot, language_diff, save_language_snapshot
```

- [ ] **Step 4: Run focused test**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_language_diff_reports_added_changed_removed_entries -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/language tests/unit/test_language_registry.py
git commit -m "feat: add language registry diffs"
```

---

### Task 4: Framework Language Pack

**Files:**
- Create: `src/bubble_mcp/language/framework_pack.py`
- Modify: `src/bubble_mcp/language/__init__.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing framework-pack tests**

Append:

```python
from bubble_mcp.language.framework_pack import framework_language_pack


def test_framework_language_pack_filters_context_for_framework_and_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = framework_language_pack(
        framework="bmad",
        profile="cliente2",
        scope="create checkout page with button and workflow",
        max_tools=10,
    )

    assert result["ok"] is True
    assert result["framework"] == "bmad"
    assert result["registry_version"].startswith("sha256:")
    assert result["language_index"]["counts"]["tools"] > 250
    assert result["runtime_rules"]
    assert result["tool_matches"]
    assert len(result["tool_matches"]) <= 10
    assert "full_catalog" not in result
```

- [ ] **Step 2: Run test to verify failure**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_framework_language_pack_filters_context_for_framework_and_scope -q
```

Expected: fail because `framework_pack` does not exist.

- [ ] **Step 3: Implement framework pack**

Create `src/bubble_mcp/language/framework_pack.py`:

```python
"""Framework-shaped low-token language packs."""

from __future__ import annotations

from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter
from bubble_mcp.language.query import language_query
from bubble_mcp.language.registry import RUNTIME_RULES_DIGEST, build_language_index
from bubble_mcp.server.agent_guide import task_runbook


FRAMEWORK_FOCUS: dict[str, list[str]] = {
    "bmad": ["visual_editor", "workflow", "data_schema", "api_connector", "observability"],
    "superpowers": ["visual_editor", "workflow", "data_schema", "extension_authoring", "observability"],
    "sdd": ["visual_editor", "workflow", "data_schema", "observability"],
}


def framework_language_pack(
    *,
    framework: str,
    profile: str | None = None,
    scope: str = "",
    max_tools: int = 12,
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    families = FRAMEWORK_FOCUS.get(adapter.framework_id, [])
    index = build_language_index(profile=profile)
    matches = language_query(query=scope, families=families, limit=max_tools, profile=profile)
    runbook = task_runbook(scope or f"{adapter.name} Bubble implementation", profile=profile or "", execute=False)
    return {
        "ok": True,
        "language": "bubble-mcp",
        "framework": adapter.framework_id,
        "profile": profile,
        "scope": scope,
        "registry_version": index["registry_version"],
        "language_index": index,
        "runtime_rules": RUNTIME_RULES_DIGEST,
        "framework_guidance": {
            "name": adapter.name,
            "modes": list(adapter.modes),
            "artifact_types": list(adapter.artifacts),
            "execution_boundary": "Frameworks plan and structure; Bubble MCP validates, previews, executes, and syncs evidence.",
        },
        "tool_matches": matches["matches"],
        "recipes": runbook.get("recipes", []),
        "next_actions": [
            "Call bubble_language_query for more scoped tools when needed.",
            "Call bubble_language_tool_detail only for selected tools before compilation.",
            "Call bubble_framework_compile_program to compile framework work into preview-safe MCP calls.",
        ],
    }
```

Update `src/bubble_mcp/language/__init__.py`:

```python
from bubble_mcp.language.framework_pack import framework_language_pack
```

- [ ] **Step 4: Run focused test**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_framework_language_pack_filters_context_for_framework_and_scope -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/language tests/unit/test_language_registry.py
git commit -m "feat: add framework language packs"
```

---

### Task 5: Compile Framework Programs To Preview-Safe MCP Calls

**Files:**
- Create: `src/bubble_mcp/language/compiler.py`
- Modify: `src/bubble_mcp/language/__init__.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing compiler tests**

Append:

```python
from bubble_mcp.language.compiler import compile_framework_program


def test_compile_framework_program_outputs_preview_safe_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="superpowers",
        profile="cliente2",
        program={
            "objective": "Create checkout CTA",
            "steps": [
                {"intent": "resolve_context", "query": "page checkout"},
                {"tool": "create_group", "arguments": {"context": "checkout", "parent": "root"}},
                {"tool": "create_button", "arguments": {"context": "checkout", "parent": "<created_group_id>", "label": "Start checkout"}},
            ],
        },
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    assert result["approval_required"] is True
    assert [call["tool"] for call in result["compiled_calls"]] == [
        "bubble_context_find",
        "create_group",
        "create_button",
    ]
    assert result["compiled_calls"][1]["arguments"]["execute"] is False
    assert result["compiled_calls"][2]["arguments"]["profile"] == "cliente2"
    assert result["validation_plan"]


def test_compile_framework_program_rejects_unknown_tool(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={"objective": "Bad", "steps": [{"tool": "missing_tool", "arguments": {}}]},
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_has_unavailable_tools"
    assert result["unavailable_tools"] == ["missing_tool"]
```

- [ ] **Step 2: Run tests to verify failure**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_compile_framework_program_outputs_preview_safe_calls tests/unit/test_language_registry.py::test_compile_framework_program_rejects_unknown_tool -q
```

Expected: fail because `compiler` does not exist.

- [ ] **Step 3: Implement compiler**

Create `src/bubble_mcp/language/compiler.py`:

```python
"""Compile compact framework programs into preview-safe MCP calls."""

from __future__ import annotations

from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter
from bubble_mcp.language.query import language_tool_detail
from bubble_mcp.server.schemas import list_tool_schemas


READ_ONLY_TOOLS = {
    "bubble_context_find",
    "bubble_context_summary",
    "bubble_profile_status",
    "bubble_tool_search",
    "bubble_task_runbook",
}


def _available_tool_names() -> set[str]:
    return {str(tool.get("name") or "") for tool in list_tool_schemas()}


def _with_profile_and_preview(tool_name: str, args: dict[str, Any], profile: str) -> dict[str, Any]:
    compiled = dict(args)
    if profile and "profile" not in compiled:
        compiled["profile"] = profile
    if tool_name not in READ_ONLY_TOOLS:
        compiled["execute"] = False
    return compiled


def _compile_intent_step(step: dict[str, Any], profile: str) -> dict[str, Any]:
    intent = str(step.get("intent") or "")
    if intent == "resolve_context":
        return {
            "tool": "bubble_context_find",
            "arguments": {
                "profile": profile,
                "query": str(step.get("query") or step.get("target") or ""),
                "limit": int(step.get("limit") or 5),
                "include_metadata": False,
            },
        }
    if intent == "refresh_context":
        return {"tool": "bubble_profile_cache_refresh", "arguments": {"profile": profile, "force": True}}
    return {
        "tool": "bubble_tool_search",
        "arguments": {"query": intent or str(step.get("description") or ""), "limit": 8},
        "unresolved_intent": intent,
    }


def compile_framework_program(
    *,
    framework: str,
    profile: str,
    program: dict[str, Any],
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    if not isinstance(program, dict):
        raise ValueError("framework program must be an object.")
    raw_steps = program.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    available = _available_tool_names()
    compiled_calls: list[dict[str, Any]] = []
    unavailable: list[str] = []
    unresolved: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("tool"):
            tool_name = str(step.get("tool") or "")
            if tool_name not in available:
                unavailable.append(tool_name)
                continue
            raw_args = step.get("arguments")
            args = raw_args if isinstance(raw_args, dict) else {}
            compiled_calls.append({"tool": tool_name, "arguments": _with_profile_and_preview(tool_name, args, profile)})
        else:
            compiled = _compile_intent_step(step, profile)
            if compiled.get("unresolved_intent"):
                unresolved.append(str(compiled["unresolved_intent"]))
                compiled.pop("unresolved_intent", None)
            compiled_calls.append(compiled)
    if unavailable:
        return {
            "ok": False,
            "error": "framework_program_has_unavailable_tools",
            "framework": adapter.framework_id,
            "profile": profile,
            "unavailable_tools": sorted(unavailable),
        }
    detail = language_tool_detail([call["tool"] for call in compiled_calls], detail="compact")
    mutating = [
        tool
        for tool in detail.get("tools", [])
        if isinstance(tool, dict) and not bool(tool.get("read_only"))
    ]
    return {
        "ok": True,
        "framework": adapter.framework_id,
        "profile": profile,
        "objective": str(program.get("objective") or ""),
        "mode": "preview",
        "compiled_calls": compiled_calls,
        "unresolved_intents": unresolved,
        "approval_required": bool(mutating),
        "validation_plan": [
            "Review compiled calls before execution.",
            "Execute mutating calls only after user approval.",
            "Refresh profile cache after successful writes.",
            "Verify the requested outcome from refreshed Bubble context.",
            "Call bubble_framework_sync_evidence with preview, execution, and validation evidence.",
        ],
        "next_action": "Preview or execute the compiled calls through MCP tools; do not bypass MCP safety gates.",
    }
```

Update `src/bubble_mcp/language/__init__.py`:

```python
from bubble_mcp.language.compiler import compile_framework_program
```

- [ ] **Step 4: Run focused tests**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py::test_compile_framework_program_outputs_preview_safe_calls tests/unit/test_language_registry.py::test_compile_framework_program_rejects_unknown_tool -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/language tests/unit/test_language_registry.py
git commit -m "feat: compile framework programs to mcp calls"
```

---

### Task 6: MCP Tool Exposure

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/runtime_coverage.py`
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Write failing MCP schema/dispatch tests**

Add to `tests/unit/test_mcp_server.py`:

```python
def test_language_tools_are_listed_with_annotations() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 201, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name in (
        "bubble_language_index",
        "bubble_language_query",
        "bubble_language_tool_detail",
        "bubble_language_diff",
        "bubble_framework_language_pack",
        "bubble_framework_compile_program",
    ):
        assert name in tools
    assert tools["bubble_language_index"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_language_query"]["inputSchema"]["required"] == ["query"]
    assert tools["bubble_language_tool_detail"]["inputSchema"]["required"] == ["tools"]
    assert tools["bubble_framework_language_pack"]["inputSchema"]["required"] == ["framework"]
    assert tools["bubble_framework_compile_program"]["inputSchema"]["required"] == ["framework", "profile", "program"]


def test_language_tools_dispatch_index_query_pack_and_compile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    index_response = handle_request({"jsonrpc": "2.0", "id": 202, "method": "tools/call", "params": {"name": "bubble_language_index", "arguments": {"profile": "cliente2"}}})
    assert index_response is not None
    index_payload = json.loads(index_response["result"]["content"][0]["text"])
    assert index_payload["registry_version"].startswith("sha256:")

    query_response = handle_request({"jsonrpc": "2.0", "id": 203, "method": "tools/call", "params": {"name": "bubble_language_query", "arguments": {"query": "create button", "families": ["visual_editor"], "limit": 5}}})
    assert query_response is not None
    query_payload = json.loads(query_response["result"]["content"][0]["text"])
    assert query_payload["matches"]

    pack_response = handle_request({"jsonrpc": "2.0", "id": 204, "method": "tools/call", "params": {"name": "bubble_framework_language_pack", "arguments": {"framework": "bmad", "profile": "cliente2", "scope": "create checkout button"}}})
    assert pack_response is not None
    pack_payload = json.loads(pack_response["result"]["content"][0]["text"])
    assert pack_payload["framework"] == "bmad"

    compile_response = handle_request({"jsonrpc": "2.0", "id": 205, "method": "tools/call", "params": {"name": "bubble_framework_compile_program", "arguments": {"framework": "bmad", "profile": "cliente2", "program": {"objective": "Create CTA", "steps": [{"tool": "create_button", "arguments": {"context": "index", "parent": "root", "label": "Start"}}]}}}})
    assert compile_response is not None
    compile_payload = json.loads(compile_response["result"]["content"][0]["text"])
    assert compile_payload["ok"] is True
    assert compile_payload["compiled_calls"][0]["arguments"]["execute"] is False
```

- [ ] **Step 2: Run tests to verify failure**

```bash
./.venv/bin/python -m pytest tests/unit/test_mcp_server.py::test_language_tools_are_listed_with_annotations tests/unit/test_mcp_server.py::test_language_tools_dispatch_index_query_pack_and_compile -q
```

Expected: fail because MCP tools are not exposed.

- [ ] **Step 3: Add schema fields and tools**

Modify `src/bubble_mcp/server/schema_families.py`:

```python
"families": _prop(
    "array",
    "Optional tool-family filters for language registry queries.",
    items={"type": "string"},
    examples=[["visual_editor", "workflow"]],
),
"sources": _prop(
    "array",
    "Optional source filters such as native or extension.",
    items={"type": "string"},
    examples=[["native"], ["extension"]],
),
"risks": _prop(
    "array",
    "Optional risk filters such as read_only, mutating, or destructive.",
    items={"type": "string"},
    examples=[["read_only", "mutating"]],
),
"tools": _prop(
    "array",
    "Exact Bubble MCP tool names for lazy language detail lookup.",
    items={"type": "string"},
    examples=[["create_button", "bubble_context_find"]],
),
"detail": _prop(
    "string",
    "Language registry detail level.",
    enum=["index", "compact", "full"],
    default="compact",
),
"since": _prop(
    "string",
    "Previous language registry version for diff queries.",
    examples=["sha256:old"],
),
"program": _prop(
    "object",
    "Framework-authored compact Bubble MCP program to compile into preview-safe MCP calls.",
    additional_properties=True,
),
```

Add tool schemas:

```python
tool_schema(
    "bubble_language_index",
    "Return a compact versioned Bubble MCP language index. This is the preferred low-token entrypoint instead of dumping the full tools/list catalog.",
    ["profile"],
),
tool_schema(
    "bubble_language_query",
    "Return scoped compact Bubble MCP language entries by query, family, source, and risk filters.",
    ["query", "families", "sources", "risks", "limit", "profile"],
    required=["query"],
),
tool_schema(
    "bubble_language_tool_detail",
    "Lazy-load compact or full schema details for selected Bubble MCP tools only.",
    ["tools", "detail"],
    required=["tools"],
),
tool_schema(
    "bubble_language_diff",
    "Return added, changed, and removed language entries since a previous registry version.",
    ["since", "profile"],
    required=["since"],
),
tool_schema(
    "bubble_framework_language_pack",
    "Return a framework-shaped low-token Bubble MCP language pack for BMAD, Superpowers, or SDD.",
    ["framework", "profile", "scope", "limit"],
    required=["framework"],
),
tool_schema(
    "bubble_framework_compile_program",
    "Compile a compact framework program into preview-safe Bubble MCP tool calls. This does not execute writes.",
    ["framework", "profile", "program"],
    required=["framework", "profile", "program"],
),
```

- [ ] **Step 4: Add dispatcher handlers**

Modify `src/bubble_mcp/server/tools.py` imports:

```python
from bubble_mcp.language import (
    build_language_index,
    compile_framework_program,
    framework_language_pack,
    language_diff,
    language_query,
    language_tool_detail,
)
```

Add handlers before `bubble_framework_list`:

```python
if name == "bubble_language_index":
    args = arguments or {}
    return build_language_index(profile=str(args.get("profile") or "") or None)
if name == "bubble_language_query":
    args = arguments or {}
    return language_query(
        query=_required_string_arg(args, "query", name),
        families=args.get("families") if isinstance(args.get("families"), list) else None,
        sources=args.get("sources") if isinstance(args.get("sources"), list) else None,
        risks=args.get("risks") if isinstance(args.get("risks"), list) else None,
        limit=int(args.get("limit") or 12),
        profile=str(args.get("profile") or "") or None,
    )
if name == "bubble_language_tool_detail":
    args = arguments or {}
    raw_tools = args.get("tools")
    if not isinstance(raw_tools, list):
        raise ValueError("bubble_language_tool_detail requires tools to be an array.")
    return language_tool_detail([str(tool) for tool in raw_tools], detail=str(args.get("detail") or "compact"))
if name == "bubble_language_diff":
    args = arguments or {}
    return language_diff(since=_required_string_arg(args, "since", name), profile=str(args.get("profile") or "") or None)
if name == "bubble_framework_language_pack":
    args = arguments or {}
    return framework_language_pack(
        framework=_required_string_arg(args, "framework", name),
        profile=str(args.get("profile") or "") or None,
        scope=str(args.get("scope") or ""),
        max_tools=int(args.get("limit") or args.get("max_tools") or 12),
    )
if name == "bubble_framework_compile_program":
    args = arguments or {}
    raw_program = args.get("program")
    if not isinstance(raw_program, dict):
        raise ValueError("bubble_framework_compile_program requires program to be an object.")
    return compile_framework_program(
        framework=_required_string_arg(args, "framework", name),
        profile=_required_string_arg(args, "profile", name),
        program=raw_program,
    )
```

- [ ] **Step 5: Update catalog and runtime coverage**

Add all six new tool names to `src/bubble_mcp/runtime_coverage.py` `NATIVE_SPECIAL_TOOLS`.

Add descriptions in `src/bubble_mcp/server/agent_catalog.py`:

```python
"bubble_language_index": "Return compact dynamic language metadata, registry version, family counts, source counts, and runtime rules. Use this before framework planning instead of dumping tools/list.",
"bubble_language_query": "Return scoped language entries for a task or family without full schemas.",
"bubble_language_tool_detail": "Lazy-load schema details only for selected tools.",
"bubble_language_diff": "Report language registry changes since a previous version so frameworks can refresh cached context cheaply.",
"bubble_framework_language_pack": "Return BMAD/Superpowers/SDD-shaped low-token language context.",
"bubble_framework_compile_program": "Compile framework-authored compact programs into preview-safe MCP tool calls without execution.",
```

Mark read-only in `_is_read_only`:

```python
"bubble_language_index",
"bubble_language_query",
"bubble_language_tool_detail",
"bubble_language_diff",
"bubble_framework_language_pack",
"bubble_framework_compile_program",
```

- [ ] **Step 6: Run MCP tests**

```bash
./.venv/bin/python -m pytest tests/unit/test_mcp_server.py::test_language_tools_are_listed_with_annotations tests/unit/test_mcp_server.py::test_language_tools_dispatch_index_query_pack_and_compile -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/bubble_mcp/server src/bubble_mcp/runtime_coverage.py tests/unit/test_mcp_server.py
git commit -m "feat: expose dynamic language mcp tools"
```

---

### Task 7: CLI Diagnostics And Documentation

**Files:**
- Modify: `src/bubble_mcp/cli/main.py`
- Modify: `docs/framework-adapters.md`
- Modify: `docs/cli-reference.md`
- Test: `tests/unit/test_cli_commands.py`

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/unit/test_cli_commands.py`:

```python
def test_cli_language_index_query_detail_and_pack(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert main(["language", "index", "--profile", "cliente2"]) == 0
    index = json.loads(capsys.readouterr().out)
    assert index["registry_version"].startswith("sha256:")

    assert main(["language", "query", "create button", "--family", "visual_editor", "--limit", "5"]) == 0
    query = json.loads(capsys.readouterr().out)
    assert query["matches"]

    assert main(["language", "detail", "create_button", "--detail", "full"]) == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["tools"][0]["name"] == "create_button"
    assert "inputSchema" in detail["tools"][0]

    assert main(["language", "framework-pack", "--framework", "bmad", "--profile", "cliente2", "--scope", "create checkout button"]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["framework"] == "bmad"
```

- [ ] **Step 2: Run test to verify failure**

```bash
./.venv/bin/python -m pytest tests/unit/test_cli_commands.py::test_cli_language_index_query_detail_and_pack -q
```

Expected: fail because `language` parser does not exist.

- [ ] **Step 3: Add CLI command functions**

Modify imports:

```python
from bubble_mcp.language import (
    build_language_index,
    framework_language_pack,
    language_query,
    language_tool_detail,
)
```

Add command functions near framework commands:

```python
def command_language_index(args: argparse.Namespace) -> int:
    emit_json(build_language_index(profile=args.profile or None))
    return 0


def command_language_query(args: argparse.Namespace) -> int:
    emit_json(
        language_query(
            query=args.query,
            families=args.family or None,
            sources=args.source or None,
            risks=args.risk or None,
            limit=args.limit,
            profile=args.profile or None,
        )
    )
    return 0


def command_language_detail(args: argparse.Namespace) -> int:
    emit_json(language_tool_detail(args.tools, detail=args.detail))
    return 0


def command_language_framework_pack(args: argparse.Namespace) -> int:
    emit_json(
        framework_language_pack(
            framework=args.framework,
            profile=args.profile or None,
            scope=args.scope or "",
            max_tools=args.limit,
        )
    )
    return 0
```

- [ ] **Step 4: Add CLI parser**

Add before `framework_parser`:

```python
language_parser = subparsers.add_parser("language", help="Inspect the dynamic Bubble MCP language registry.")
language_subparsers = language_parser.add_subparsers(dest="language_command", required=True)

language_index_parser = language_subparsers.add_parser("index", help="Return compact registry index.")
language_index_parser.add_argument("--profile", default="")
language_index_parser.set_defaults(func=command_language_index)

language_query_parser = language_subparsers.add_parser("query", help="Query compact language entries.")
language_query_parser.add_argument("query")
language_query_parser.add_argument("--family", action="append", default=[])
language_query_parser.add_argument("--source", action="append", default=[])
language_query_parser.add_argument("--risk", action="append", default=[])
language_query_parser.add_argument("--limit", type=int, default=12)
language_query_parser.add_argument("--profile", default="")
language_query_parser.set_defaults(func=command_language_query)

language_detail_parser = language_subparsers.add_parser("detail", help="Lazy-load selected tool detail.")
language_detail_parser.add_argument("tools", nargs="+")
language_detail_parser.add_argument("--detail", choices=["compact", "full"], default="compact")
language_detail_parser.set_defaults(func=command_language_detail)

language_pack_parser = language_subparsers.add_parser("framework-pack", help="Return framework-shaped language pack.")
language_pack_parser.add_argument("--framework", choices=["bmad", "superpowers", "sdd"], required=True)
language_pack_parser.add_argument("--profile", default="")
language_pack_parser.add_argument("--scope", default="")
language_pack_parser.add_argument("--limit", type=int, default=12)
language_pack_parser.set_defaults(func=command_language_framework_pack)
```

- [ ] **Step 5: Update docs**

Append to `docs/framework-adapters.md`:

```markdown
## Dynamic Language Registry

Framework adapters should not request the full MCP catalog by default. Use:

1. `bubble_language_index` for registry version, counts, families, source counts, and runtime rules.
2. `bubble_language_query` for scoped tools and recipes relevant to the current objective.
3. `bubble_language_tool_detail` only for selected tools before compilation.
4. `bubble_language_diff` when a framework has a cached registry version.
5. `bubble_framework_language_pack` when a framework wants a single low-token contextual package.
6. `bubble_framework_compile_program` to turn framework-authored programs into preview-safe MCP calls.
```

Add to `docs/cli-reference.md`:

```markdown
## `bubble-mcp language`

Diagnostic commands for the dynamic Bubble MCP language registry:

```bash
bubble-mcp language index --profile my-app
bubble-mcp language query "create checkout button" --family visual_editor --limit 8
bubble-mcp language detail create_button bubble_context_find --detail full
bubble-mcp language framework-pack --framework bmad --profile my-app --scope "checkout flow"
```
```

- [ ] **Step 6: Run CLI test**

```bash
./.venv/bin/python -m pytest tests/unit/test_cli_commands.py::test_cli_language_index_query_detail_and_pack -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/bubble_mcp/cli/main.py docs/framework-adapters.md docs/cli-reference.md tests/unit/test_cli_commands.py
git commit -m "docs: document dynamic language registry"
```

---

### Task 8: Full Validation

**Files:**
- All changed files.

- [ ] **Step 1: Run focused language/MCP/CLI tests**

```bash
./.venv/bin/python -m pytest tests/unit/test_language_registry.py tests/unit/test_mcp_server.py::test_language_tools_are_listed_with_annotations tests/unit/test_mcp_server.py::test_language_tools_dispatch_index_query_pack_and_compile tests/unit/test_cli_commands.py::test_cli_language_index_query_detail_and_pack -q
```

Expected: all pass.

- [ ] **Step 2: Run full Python test suite**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run ruff**

```bash
./.venv/bin/python -m ruff check src tests scripts
```

Expected: `All checks passed!`

- [ ] **Step 4: Run mypy**

```bash
./.venv/bin/python -m mypy src
```

Expected: `Success: no issues found`.

- [ ] **Step 5: Run Node bridge tests**

```bash
npm test
```

Expected: all Node tests pass.

- [ ] **Step 6: Run whitespace check**

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 7: Review diff stat**

```bash
git diff --stat
```

Expected: changes are limited to `src/bubble_mcp/language`, MCP schema/dispatcher/catalog coverage, CLI, docs, and tests.

- [ ] **Step 8: Final commit if needed**

If any validation/doc cleanup changed files after prior commits:

```bash
git add .
git commit -m "test: validate dynamic language registry"
```

---

## Self-Review

- Spec coverage: The plan covers dynamic documentation, current native tools, enabled extension tools, installed skills, learning records, runtime coverage, low-token index, scoped query, lazy schema detail, registry versioning, diff, framework-shaped packs, and program compilation into preview-safe MCP calls.
- Performance/token strategy: The default path returns index-level data only; tool schemas are loaded lazily; framework packs are scoped by framework and objective; diffs avoid re-sending unchanged registry data.
- Execution safety: The compiler never executes writes. It forces `execute=false` for mutating calls, returns approval and validation plans, and keeps actual execution in existing MCP tools/skills.
- Placeholder scan: No task uses TBD/TODO placeholders.
- Type consistency: Public fields consistently use `registry_version`, `detail`, `families`, `sources`, `risks`, `tools`, `framework`, `profile`, `scope`, `program`, `compiled_calls`, and `validation_plan`.
