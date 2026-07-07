# Executable Skills V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Bubble MCP skills from validation-only JSON contracts into user-authored, importable/exportable, runnable MCP workflows with preview-first approved execution.

**Architecture:** Extend the existing `bubble_mcp.skills` package with executable contract validation, local skill storage, authoring sessions, run/audit storage, and a runner that executes read/preview steps before requiring `run_id + approve_execution` for writes. MCP tools dispatch into those focused modules, while extension packs can expose skills through the existing `exports.skills` field.

**Tech Stack:** Python 3.11, existing Bubble MCP stdio tool dispatcher, JSON file storage under `BUBBLE_MCP_CONFIG_DIR`, pytest, ruff, mypy.

---

### Task 1: Executable Skill Contract Validation

**Files:**
- Modify: `src/bubble_mcp/skills/models.py`
- Modify: `src/bubble_mcp/skills/validator.py`
- Modify: `tests/unit/test_skill_contracts.py`
- Create: `tests/fixtures/skills/executable-security-review.skill.json`

- [x] Add an executable skill fixture with `risk`, object `inputs`, tool-mode steps, approval gates, and outputs.
- [x] Add failing tests for valid executable contracts, mutating contracts without approval, steps outside `allowedTools`, and legacy contracts returning `executable=false`.
- [x] Extend models without breaking the legacy `SkillDefinition.to_dict()` shape.
- [x] Extend validator to accept both legacy validation-only contracts and executable v1 contracts.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_skill_contracts.py -q`.
- [x] Commit with `feat: validate executable skill contracts`.

### Task 2: Skill Store, Import, Export, List, Enable, Disable

**Files:**
- Create: `src/bubble_mcp/skills/store.py`
- Modify: `src/bubble_mcp/extensions/validator.py`
- Modify: `tests/unit/test_skill_contracts.py`
- Modify: `tests/fixtures/extensions/simple-pack/extension.json`
- Create: `tests/fixtures/extensions/simple-pack/skills/security-review.skill.json`

- [x] Add local storage under `skills/installed/<skill_id>/skill.json` and `state.json`.
- [x] Add `import_skill`, `export_skill`, `list_skills`, `enable_skill`, and `disable_skill`.
- [x] Include enabled extension-pack skills from `exports.skills` in `list_skills`.
- [x] Validate extension-pack skill paths stay inside the pack and parse as valid skill contracts.
- [x] Add tests for import/list/enable/disable/export and extension-pack skills.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_skill_contracts.py tests/unit/test_extensions.py -q`.
- [x] Commit with `feat: add skill import export store`.

### Task 3: Skill Authoring Sessions

**Files:**
- Create: `src/bubble_mcp/skills/authoring.py`
- Modify: `tests/unit/test_skill_contracts.py`

- [x] Add `create_skill_authoring_session(objective, risk, profile=None)`.
- [x] Add `update_skill_authoring_session(session_id, answer, field=None)` to collect conversational answers.
- [x] Add `generate_skill_from_authoring_session(session_id, skill_id=None, output_dir=None)` that writes `.skill.json`, validates it, and returns next MCP calls.
- [x] Generate a conservative executable contract from answers using existing tools only.
- [x] Add tests for start, update, generate, and generated contract validation.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_skill_contracts.py -q`.
- [x] Commit with `feat: add skill authoring sessions`.

### Task 4: Skill Runner And Audit

**Files:**
- Create: `src/bubble_mcp/skills/runner.py`
- Create: `src/bubble_mcp/skills/audit.py`
- Modify: `tests/unit/test_skill_contracts.py`

- [x] Add preview run support with `run_skill(skill_id, inputs, execute=False)`.
- [x] Resolve `{{inputs.name}}` templates inside step args.
- [x] Execute read steps through the MCP dispatcher in preview.
- [x] Execute write steps only as preview during `execute=false`.
- [x] Save `skillrun_*.json` records with redacted internal details.
- [x] Add approved execution support requiring `execute=true`, `approve_execution=true`, and `run_id`.
- [x] Block execution when skill id, plan hash, or approved step list changed.
- [x] Return user-facing summaries without raw payloads.
- [x] Add tests for preview, approved execution, missing approval, missing run id, and no raw payloads in responses.
- [x] Run `./.venv/bin/python -m pytest tests/unit/test_skill_contracts.py -q`.
- [x] Commit with `feat: run approved executable skills`.

### Task 5: MCP And CLI Integration

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/runtime_coverage.py`
- Modify: `src/bubble_mcp/cli/main.py`
- Modify: `tests/unit/test_skill_contracts.py`
- Modify: `tests/unit/test_cli_commands.py`
- Modify: `tests/unit/test_mcp_server.py`

- [x] Add MCP schemas for `bubble_skill_author_start`, `bubble_skill_author_update`, `bubble_skill_author_generate`, `bubble_skill_import`, `bubble_skill_export`, `bubble_skill_list`, `bubble_skill_enable`, `bubble_skill_disable`, and `bubble_skill_run`.
- [x] Dispatch all new MCP tools through `call_tool`.
- [x] Add CLI subcommands under `bubble-mcp skill`.
- [x] Update runtime coverage and agent catalog.
- [x] Add MCP and CLI tests for the new commands.
- [x] Run focused skill, CLI, and MCP tests.
- [x] Commit with `feat: expose executable skill mcp tools`.

### Task 6: Documentation And Full Validation

**Files:**
- Modify: `docs/extension-packs.md`
- Modify: `docs/cli-reference.md`
- Create: `docs/skills.md`
- Modify: `README.md`

- [x] Document executable skill contract v1.
- [x] Document friendly authoring flow.
- [x] Document import/export/list/enable/disable/run.
- [x] Document preview/approve execution and the no-raw-payload user response rule.
- [x] Run full validation:
  - `./.venv/bin/python -m pytest -q`
  - `./.venv/bin/python -m ruff check src tests scripts`
  - `./.venv/bin/python -m mypy src`
  - `npm test`
  - `git diff --check`
- [x] Commit with `docs: document executable skills`.
- [x] Push `main`.

Validation evidence:

- `./.venv/bin/python -m pytest -q`: 393 passed.
- `./.venv/bin/python -m ruff check src tests scripts`: passed.
- `./.venv/bin/python -m mypy src`: success, 90 source files.
- `npm test`: 9 passed.
- `git diff --check`: passed.

## Self-Review

- Spec coverage: The plan covers authoring, validation, storage/import/export, extension-pack skills, preview and approved execution, friendly responses, audit, MCP tools, CLI, docs, and tests.
- Placeholder scan: No task contains TBD/TODO placeholders.
- Type consistency: The plan consistently uses `skill_id`, `run_id`, `execute`, and `approve_execution` as public API fields.
