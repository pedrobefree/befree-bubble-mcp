# Framework Adapters V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class framework adapter layer so BMAD, Superpowers, and SDD can generate portable project artifacts and receive implementation evidence from real Bubble MCP context.

**Architecture:** Implement adapters as read-only artifact generators under `bubble_mcp.frameworks`, keeping BMAD/Superpowers/SDD outside the MCP core execution path. Expose a small MCP surface for listing frameworks, generating artifacts, syncing evidence, and reading framework status; generated artifacts are local Markdown/JSON files under the Bubble MCP config directory or a caller-provided output directory.

**Tech Stack:** Python 3.11, existing Bubble MCP stdio tool dispatcher, local JSON/Markdown file storage, pytest, ruff, mypy.

---

### Task 1: Framework Adapter Models And Artifact Generation

**Files:**
- Create: `src/bubble_mcp/frameworks/__init__.py`
- Create: `src/bubble_mcp/frameworks/models.py`
- Create: `src/bubble_mcp/frameworks/adapters.py`
- Create: `src/bubble_mcp/frameworks/artifacts.py`
- Test: `tests/unit/test_framework_adapters.py`

- [x] Add supported framework ids: `bmad`, `superpowers`, and `sdd`.
- [x] Add framework modes and artifact names for each adapter.
- [x] Add deterministic artifact rendering from `profile`, `objective`, optional `scope`, optional `context_summary`, and optional `output_dir`.
- [x] Add tests for adapter listing and artifact generation for all supported frameworks.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_framework_adapters.py -q`.

### Task 2: Evidence Sync And Status

**Files:**
- Modify: `src/bubble_mcp/frameworks/artifacts.py`
- Test: `tests/unit/test_framework_adapters.py`

- [x] Add `sync_framework_evidence` to append a normalized evidence record to the framework artifact directory.
- [x] Add `framework_status` to inspect generated artifacts and evidence count.
- [x] Redact sensitive values before evidence persistence.
- [x] Add tests for evidence append, redaction, and status.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_framework_adapters.py -q`.

### Task 3: MCP Tool Exposure

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/runtime_coverage.py`
- Test: `tests/unit/test_mcp_server.py`

- [x] Add schemas for `bubble_framework_list`, `bubble_framework_generate_artifacts`, `bubble_framework_sync_evidence`, and `bubble_framework_status`.
- [x] Dispatch each tool through `call_tool`.
- [x] Add agent catalog descriptions that make clear these tools generate framework artifacts and do not execute Bubble writes.
- [x] Add runtime coverage entries.
- [x] Add MCP tests for tool listing and dispatch.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_mcp_server.py tests/unit/test_framework_adapters.py -q`.

### Task 4: CLI And Documentation

**Files:**
- Modify: `src/bubble_mcp/cli/main.py`
- Create: `docs/framework-adapters.md`
- Modify: `docs/cli-reference.md`
- Modify: `README.md`
- Test: `tests/unit/test_cli_commands.py`

- [x] Add `bubble-mcp framework list`.
- [x] Add `bubble-mcp framework generate`.
- [x] Add `bubble-mcp framework status`.
- [x] Add concise docs explaining BMAD, Superpowers, and SDD adapter boundaries.
- [x] Add CLI tests for list/generate/status.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_cli_commands.py tests/unit/test_framework_adapters.py -q`.

### Task 5: Full Validation

**Files:**
- All changed files.

- [x] Run `./.venv/bin/python -m pytest -q`.
- [x] Run `./.venv/bin/python -m ruff check src tests scripts`.
- [x] Run `./.venv/bin/python -m mypy src`.
- [x] Run `npm test`.
- [x] Run `git diff --check`.
- [x] Review `git diff --stat` and summarize changed surfaces.

Validation evidence:

- `./.venv/bin/python -m pytest -q`: 455 passed.
- `./.venv/bin/python -m ruff check src tests scripts`: passed.
- `./.venv/bin/python -m mypy src`: success, 97 source files.
- `npm test`: 9 passed.
- `git diff --check`: passed.

## Self-Review

- Spec coverage: This v1 covers the missing framework adapter layer, artifact generation, evidence sync, MCP exposure, CLI access, documentation, and validation. It intentionally does not execute framework stories automatically; execution remains mediated by existing skills/tools.
- Placeholder scan: No TODO/TBD placeholders remain in task steps.
- Type consistency: Public names consistently use `framework`, `profile`, `objective`, `scope`, `output_dir`, `artifacts`, and `evidence`.
