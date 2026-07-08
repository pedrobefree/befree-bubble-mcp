# Dynamic Language Registry V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make framework adapters use Bubble MCP as a dynamic implementation language that can plan, compile, gate, execute, validate, cache, and synchronize evidence with BMAD, Superpowers, SDD, and user-authored tools.

**Architecture:** V2 keeps the v1 low-token registry APIs, then adds a framework program runtime around them. Frameworks submit either compact structured programs or text artifacts; the MCP normalizes them into a typed program, compiles them into preview-safe MCP calls, applies deterministic quality gates, optionally executes the gated sequence, refreshes context, validates outcomes, and writes evidence back to local or external framework artifact layouts.

**Tech Stack:** Python 3.11+, existing `bubble_mcp.language`, `bubble_mcp.frameworks`, MCP server schemas/tools, local JSON/Markdown artifact storage, pytest, ruff, mypy, Node bridge tests.

---

## Scope Coverage

This plan covers the seven requested V2 areas:

1. Execute compiled framework programs directly through a gated sequence runner.
2. Expand the Bubble MCP language of intents across visual, workflow, data, API Connector, style, reusable, migration, performance, and verification families.
3. Resolve multi-step dependencies and placeholders between program steps.
4. Read and update external framework repository layouts in place.
5. Transform framework stories, PRDs, specs, or acceptance text into structured MCP programs.
6. Add incremental registry cache APIs so frameworks do not send or request full catalogs repeatedly.
7. Add deterministic QA policies for branch/profile/app-version, preview-first execution, default visual standards, destructive-risk handling, evidence, refresh, and validation.

## File Structure

- Create `src/bubble_mcp/language/program.py`
  - Defines `FrameworkProgram`, `FrameworkProgramStep`, `CompiledFrameworkCall`, execution metadata, and parsing helpers.
- Create `src/bubble_mcp/language/intents.py`
  - Owns intent aliases, family metadata, argument normalization, and default compile mappings.
- Create `src/bubble_mcp/language/dependencies.py`
  - Resolves placeholders such as `<created_group_id>`, `{{steps.section.output.element_id}}`, and generated output aliases.
- Create `src/bubble_mcp/language/quality.py`
  - Runs deterministic compile-time and pre-execution QA policies.
- Create `src/bubble_mcp/language/cache.py`
  - Stores per-framework registry cache metadata and compact family/tool snapshots.
- Create `src/bubble_mcp/frameworks/program_runner.py`
  - Executes compiled programs with gates, evidence capture, refresh, validation, and dry-run support.
- Create `src/bubble_mcp/frameworks/text_planner.py`
  - Converts framework text artifacts into structured framework programs using deterministic parsing and language queries.
- Create `src/bubble_mcp/frameworks/workspace.py`
  - Imports, detects, and writes framework artifacts in external repository layouts.
- Modify `src/bubble_mcp/language/compiler.py`
  - Delegate aliases and normalization to `language.intents`; return typed compile output with unresolved, missing, dependency, and QA diagnostics.
- Modify `src/bubble_mcp/language/registry.py`
  - Add cache metadata, family digests, intent families, and policy versions.
- Modify `src/bubble_mcp/language/query.py`
  - Add family digest and cache-aware query parameters.
- Modify `src/bubble_mcp/language/__init__.py`
  - Export V2 APIs.
- Modify `src/bubble_mcp/frameworks/artifacts.py`
  - Use workspace adapters for in-place framework sync.
- Modify `src/bubble_mcp/frameworks/__init__.py`
  - Export program runner, planner, and workspace helpers.
- Modify `src/bubble_mcp/server/schema_families.py`
  - Add MCP schemas for V2 language and framework tools.
- Modify `src/bubble_mcp/server/tools.py`
  - Dispatch V2 tools.
- Modify `src/bubble_mcp/cli/main.py`
  - Add diagnostic CLI for program compile, execute, cache, text-plan, and workspace sync.
- Modify `docs/framework-adapters.md`
  - Document the V2 workflow and safety boundaries.
- Test `tests/unit/test_language_program.py`
  - Program parsing, dependency resolution, quality policies, and cache.
- Test `tests/unit/test_framework_program_runner.py`
  - Preview, approval, execution, refresh, validation, evidence, and failure behavior.
- Test `tests/unit/test_framework_text_planner.py`
  - Text artifact to program conversion.
- Test `tests/unit/test_framework_workspace.py`
  - External framework repository import/export behavior.
- Test existing `tests/unit/test_language_registry.py`
  - Registry V2 metadata and cache behavior.
- Test existing `tests/unit/test_mcp_server.py`
  - MCP schema exposure and tool calls.
- Test existing `tests/unit/test_cli_commands.py`
  - CLI command coverage.

---

### Task 1: Typed Framework Program Contract

**Files:**
- Create: `src/bubble_mcp/language/program.py`
- Modify: `src/bubble_mcp/language/__init__.py`
- Test: `tests/unit/test_language_program.py`

- [ ] **Step 1: Write failing tests for program parsing**

Add this test file:

```python
from bubble_mcp.language.program import (
    FrameworkProgram,
    FrameworkProgramStep,
    parse_framework_program,
)


def test_parse_framework_program_normalizes_steps_and_execution_policy() -> None:
    result = parse_framework_program(
        {
            "objective": "Create checkout UI",
            "execution": {"mode": "preview", "approval": "required"},
            "steps": [
                {
                    "id": "section",
                    "intent": "create_container",
                    "context": "checkout",
                    "parent": "root",
                    "label": "Checkout section",
                    "outputs": {"element_id": "checkout_section"},
                },
                {
                    "id": "cta",
                    "intent": "cta_button",
                    "arguments": {
                        "context": "checkout",
                        "parent": "{{steps.section.output.element_id}}",
                        "text": "Start checkout",
                    },
                },
            ],
        }
    )

    assert isinstance(result, FrameworkProgram)
    assert result.objective == "Create checkout UI"
    assert result.execution_mode == "preview"
    assert result.approval == "required"
    assert [step.step_id for step in result.steps] == ["section", "cta"]
    assert result.steps[0].arguments["label"] == "Checkout section"
    assert result.steps[1].arguments["parent"] == "{{steps.section.output.element_id}}"


def test_parse_framework_program_rejects_missing_steps() -> None:
    result = parse_framework_program({"objective": "Empty"})

    assert result.ok is False
    assert result.error == "framework_program_has_no_steps"


def test_framework_program_step_keeps_direct_tool_calls() -> None:
    step = FrameworkProgramStep.from_dict(
        {
            "id": "refresh",
            "tool": "bubble_profile_cache_refresh",
            "arguments": {"force": True},
        },
        index=1,
    )

    assert step.step_id == "refresh"
    assert step.tool == "bubble_profile_cache_refresh"
    assert step.intent == ""
    assert step.arguments == {"force": True}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'bubble_mcp.language.program'`.

- [ ] **Step 3: Implement typed program models**

Create `src/bubble_mcp/language/program.py`:

```python
"""Typed framework program contracts for the Bubble MCP language."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class FrameworkProgramStep:
    index: int
    step_id: str
    intent: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, index: int) -> "FrameworkProgramStep":
        raw_arguments = _dict(payload.get("arguments"))
        inline_arguments = {
            str(key): value
            for key, value in payload.items()
            if key
            not in {
                "id",
                "step_id",
                "intent",
                "tool",
                "arguments",
                "outputs",
                "requires",
                "description",
            }
        }
        arguments = {**inline_arguments, **raw_arguments}
        step_id = str(payload.get("id") or payload.get("step_id") or f"step_{index}").strip()
        return cls(
            index=index,
            step_id=step_id,
            intent=str(payload.get("intent") or "").strip(),
            tool=str(payload.get("tool") or "").strip(),
            arguments=arguments,
            outputs={str(key): str(value) for key, value in _dict(payload.get("outputs")).items()},
            requires=[str(item) for item in _list(payload.get("requires")) if str(item).strip()],
            description=str(payload.get("description") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.step_id,
            "arguments": dict(self.arguments),
        }
        if self.intent:
            payload["intent"] = self.intent
        if self.tool:
            payload["tool"] = self.tool
        if self.outputs:
            payload["outputs"] = dict(self.outputs)
        if self.requires:
            payload["requires"] = list(self.requires)
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class FrameworkProgram:
    ok: bool
    objective: str
    steps: list[FrameworkProgramStep]
    execution_mode: str = "preview"
    approval: str = "required"
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "objective": self.objective,
            "execution": {"mode": self.execution_mode, "approval": self.approval},
            "metadata": dict(self.metadata),
            "steps": [step.to_dict() for step in self.steps],
            "error": self.error,
        }


@dataclass(frozen=True)
class CompiledFrameworkCall:
    step_id: str
    step_index: int
    tool: str
    arguments: dict[str, Any]
    intent: str = ""
    risk: str = "mutating"
    read_only: bool = False
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "intent": self.intent,
            "risk": self.risk,
            "read_only": self.read_only,
            "requires_approval": self.requires_approval,
        }


def parse_framework_program(program: dict[str, Any]) -> FrameworkProgram:
    if not isinstance(program, dict):
        raise ValueError("framework program must be an object.")
    steps = [
        FrameworkProgramStep.from_dict(step, index=index)
        for index, step in enumerate(_list(program.get("steps")), start=1)
        if isinstance(step, dict)
    ]
    if not steps:
        return FrameworkProgram(
            ok=False,
            objective=str(program.get("objective") or ""),
            steps=[],
            error="framework_program_has_no_steps",
        )
    execution = _dict(program.get("execution"))
    metadata = _dict(program.get("metadata"))
    return FrameworkProgram(
        ok=True,
        objective=str(program.get("objective") or ""),
        steps=steps,
        execution_mode=str(execution.get("mode") or "preview"),
        approval=str(execution.get("approval") or "required"),
        metadata=metadata,
    )
```

Modify `src/bubble_mcp/language/__init__.py`:

```python
from bubble_mcp.language.program import (
    CompiledFrameworkCall,
    FrameworkProgram,
    FrameworkProgramStep,
    parse_framework_program,
)

__all__ = [
    "CompiledFrameworkCall",
    "FrameworkProgram",
    "FrameworkProgramStep",
    "parse_framework_program",
]
```

Preserve existing exports in `__all__` and append these names instead of replacing current exports.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/language/program.py src/bubble_mcp/language/__init__.py tests/unit/test_language_program.py
git commit -m "feat: add framework program contract"
```

---

### Task 2: Dynamic Intent Catalog And Expanded Compile Language

**Files:**
- Create: `src/bubble_mcp/language/intents.py`
- Modify: `src/bubble_mcp/language/compiler.py`
- Modify: `src/bubble_mcp/language/registry.py`
- Test: `tests/unit/test_language_program.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing tests for expanded intent coverage**

Append to `tests/unit/test_language_program.py`:

```python
from bubble_mcp.language.compiler import compile_framework_program
from bubble_mcp.language.intents import INTENT_CATALOG, normalize_intent_arguments


def test_intent_catalog_covers_v2_families() -> None:
    families = {entry.family for entry in INTENT_CATALOG.values()}

    assert {
        "visual",
        "workflow",
        "data",
        "api_connector",
        "style",
        "reusable",
        "migration",
        "performance",
        "verification",
    }.issubset(families)


def test_compile_framework_program_maps_data_workflow_and_verification_intents(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = compile_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Add enrollment data and event",
            "steps": [
                {"intent": "create_data_type", "name": "Enrollment"},
                {"intent": "create_field", "data_type": "Enrollment", "name": "student", "field_type": "User"},
                {"intent": "create_custom_event", "context": "checkout", "name": "Enroll student"},
                {"intent": "refresh_context"},
                {"intent": "verify_context", "query": "Enrollment", "exact": True},
            ],
        },
    )

    assert result["ok"] is True
    assert [call["tool"] for call in result["compiled_calls"]] == [
        "create_data_type",
        "create_data_field",
        "create_event",
        "bubble_profile_cache_refresh",
        "bubble_context_find",
    ]
    assert result["compiled_calls"][0]["arguments"]["profile"] == "cliente2"
    assert result["compiled_calls"][0]["arguments"]["execute"] is False
    assert result["compiled_calls"][4]["arguments"]["exact"] is True


def test_normalize_intent_arguments_maps_api_connector_aliases() -> None:
    args = normalize_intent_arguments(
        "create_api_call",
        {
            "label": "CRM create contact",
            "verb": "POST",
            "endpoint": "https://example.com/contacts",
        },
    )

    assert args["name"] == "CRM create contact"
    assert args["method"] == "POST"
    assert args["url"] == "https://example.com/contacts"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py tests/unit/test_language_registry.py -q
```

Expected: fail because `bubble_mcp.language.intents` does not exist or intent mappings are missing.

- [ ] **Step 3: Implement the intent catalog**

Create `src/bubble_mcp/language/intents.py`:

```python
"""Dynamic intent aliases for the Bubble MCP implementation language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IntentEntry:
    intent: str
    tool: str
    family: str
    description: str
    aliases: tuple[str, ...] = ()


INTENT_ENTRIES = (
    IntentEntry("create_container", "create_group", "visual", "Create a Bubble container/group.", ("create_group", "create_section", "create_card")),
    IntentEntry("create_text", "create_text", "visual", "Create Bubble text.", ("add_text", "headline", "create_heading")),
    IntentEntry("create_button", "create_button", "visual", "Create Bubble button.", ("add_button", "cta_button", "create_cta")),
    IntentEntry("create_input", "create_input", "visual", "Create Bubble input.", ("add_input", "text_input")),
    IntentEntry("create_data_type", "create_data_type", "data", "Create a Bubble data type.", ("add_data_type",)),
    IntentEntry("create_field", "create_data_field", "data", "Create a Bubble data field.", ("create_data_field", "add_field")),
    IntentEntry("create_custom_event", "create_event", "workflow", "Create a Bubble custom event.", ("create_event", "add_custom_event")),
    IntentEntry("add_workflow_action", "add_action", "workflow", "Add an action to a workflow.", ("add_action", "create_action")),
    IntentEntry("create_api_call", "create_api_connector_resource", "api_connector", "Create an API Connector call.", ("create_api_connector_resource", "api_call")),
    IntentEntry("update_style", "update_style", "style", "Update a Bubble style.", ("change_style", "style_update")),
    IntentEntry("create_reusable", "create_reusable", "reusable", "Create a reusable element.", ("add_reusable",)),
    IntentEntry("transfer_bundle", "bubble_transfer_execute", "migration", "Execute a transfer bundle.", ("clone_bundle", "migrate_bundle")),
    IntentEntry("performance_audit", "bubble_performance_audit", "performance", "Run a performance audit.", ("audit_performance",)),
    IntentEntry("verify_context", "bubble_context_find", "verification", "Verify refreshed Bubble context.", ("resolve_context", "find_context")),
    IntentEntry("refresh_context", "bubble_profile_cache_refresh", "verification", "Refresh profile cache.", ("refresh_cache",)),
    IntentEntry("query_language", "bubble_language_query", "verification", "Query the Bubble MCP language registry.", ("find_tool",)),
    IntentEntry("sync_evidence", "bubble_framework_sync_evidence", "verification", "Append framework evidence.", ("record_evidence",)),
)

INTENT_CATALOG: dict[str, IntentEntry] = {}
for entry in INTENT_ENTRIES:
    INTENT_CATALOG[entry.intent] = entry
    for alias in entry.aliases:
        INTENT_CATALOG[alias] = entry


def tool_for_intent(intent: str) -> str:
    entry = INTENT_CATALOG.get(str(intent or "").strip())
    return entry.tool if entry else ""


def _copy_first_available(args: dict[str, Any], target: str, candidates: tuple[str, ...]) -> None:
    if args.get(target) not in (None, ""):
        return
    for candidate in candidates:
        value = args.get(candidate)
        if value not in (None, ""):
            args[target] = value
            return


def normalize_intent_arguments(intent: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    tool = tool_for_intent(intent) or str(intent or "")
    if tool == "create_text":
        _copy_first_available(normalized, "content", ("text", "label", "title", "name"))
    elif tool == "create_button":
        _copy_first_available(normalized, "label", ("text", "content", "title", "name"))
    elif tool in {"create_group", "create_input"}:
        _copy_first_available(normalized, "name", ("label", "title", "text", "content"))
    elif tool == "create_data_field":
        _copy_first_available(normalized, "type", ("field_type", "data_class", "data_type_ref"))
    elif tool == "create_event":
        _copy_first_available(normalized, "name", ("label", "title", "event_name"))
    elif tool == "create_api_connector_resource":
        _copy_first_available(normalized, "name", ("label", "title", "call_name"))
        _copy_first_available(normalized, "method", ("verb", "http_method"))
        _copy_first_available(normalized, "url", ("endpoint", "uri"))
    elif tool == "bubble_context_find":
        _copy_first_available(normalized, "query", ("target", "selector", "description", "name"))
        normalized.setdefault("include_metadata", False)
        normalized.setdefault("limit", 5)
    elif tool == "bubble_language_query":
        _copy_first_available(normalized, "query", ("target", "selector", "description", "name"))
        normalized.setdefault("limit", 8)
    elif tool == "bubble_framework_sync_evidence":
        if "evidence" not in normalized:
            evidence = normalized.get("result") or normalized.get("summary") or normalized.get("description")
            if evidence not in (None, ""):
                normalized["evidence"] = evidence
    return normalized


def language_intent_families() -> dict[str, list[str]]:
    families: dict[str, list[str]] = {}
    for key, entry in sorted(INTENT_CATALOG.items()):
        families.setdefault(entry.family, []).append(key)
    return families
```

- [ ] **Step 4: Refactor compiler to use the intent catalog**

Modify `src/bubble_mcp/language/compiler.py`:

```python
from bubble_mcp.language.intents import normalize_intent_arguments, tool_for_intent
from bubble_mcp.language.program import parse_framework_program
```

Replace the local `INTENT_TOOL_ALIASES`, `_copy_first_available`, and `_normalize_args_for_tool` with calls to `tool_for_intent()` and `normalize_intent_arguments()`.

In `compile_framework_program`, parse the program first:

```python
parsed = parse_framework_program(program)
if not parsed.ok:
    return {
        "ok": False,
        "error": parsed.error,
        "framework": adapter.framework_id,
        "profile": profile,
    }
steps = parsed.steps
```

When a step has an intent:

```python
tool_name = tool_for_intent(step.intent)
if not tool_name:
    unresolved.append(step.intent)
    compiled_calls.append(
        {
            "tool": "bubble_tool_search",
            "arguments": {"query": step.intent or step.description, "limit": 8},
        }
    )
else:
    args = normalize_intent_arguments(step.intent, step.arguments)
    if tool_name == "bubble_framework_sync_evidence":
        args.setdefault("framework", adapter.framework_id)
    compiled_calls.append(
        {
            "step_id": step.step_id,
            "tool": tool_name,
            "arguments": _with_profile_and_preview(tool_name, args, profile, tool_schemas.get(tool_name)),
            "intent": step.intent,
        }
    )
```

- [ ] **Step 5: Add intent family metadata to registry**

Modify `src/bubble_mcp/language/registry.py`:

```python
from bubble_mcp.language.intents import language_intent_families
```

Add to `build_language_index()`:

```python
"intent_families": language_intent_families(),
```

- [ ] **Step 6: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py tests/unit/test_language_registry.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/bubble_mcp/language/intents.py src/bubble_mcp/language/compiler.py src/bubble_mcp/language/registry.py tests/unit/test_language_program.py tests/unit/test_language_registry.py
git commit -m "feat: expand framework intent language"
```

---

### Task 3: Dependency And Placeholder Resolution

**Files:**
- Create: `src/bubble_mcp/language/dependencies.py`
- Modify: `src/bubble_mcp/language/compiler.py`
- Test: `tests/unit/test_language_program.py`

- [ ] **Step 1: Write failing tests for dependency resolution**

Append to `tests/unit/test_language_program.py`:

```python
from bubble_mcp.language.dependencies import DependencyState, resolve_step_arguments, record_step_outputs


def test_resolve_step_arguments_uses_prior_step_outputs() -> None:
    state = DependencyState()
    record_step_outputs(
        state,
        step_id="section",
        declared_outputs={"element_id": "checkout_section"},
        result={"element_id": "group_123"},
    )

    args = resolve_step_arguments(
        {"parent": "{{steps.section.output.element_id}}", "context": "checkout"},
        state,
    )

    assert args == {"parent": "group_123", "context": "checkout"}


def test_resolve_step_arguments_reports_unresolved_placeholders() -> None:
    state = DependencyState()

    args = resolve_step_arguments({"parent": "{{steps.missing.output.element_id}}"}, state)

    assert args == {"parent": "{{steps.missing.output.element_id}}"}
    assert state.unresolved == ["{{steps.missing.output.element_id}}"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py -q
```

Expected: fail because `bubble_mcp.language.dependencies` does not exist.

- [ ] **Step 3: Implement dependency resolver**

Create `src/bubble_mcp/language/dependencies.py`:

```python
"""Dependency and placeholder resolution for framework programs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


PLACEHOLDER_RE = re.compile(r"\{\{steps\.([a-zA-Z0-9_-]+)\.output\.([a-zA-Z0-9_-]+)\}\}")


@dataclass
class DependencyState:
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)


def record_step_outputs(
    state: DependencyState,
    *,
    step_id: str,
    declared_outputs: dict[str, str],
    result: dict[str, Any],
) -> None:
    output_values: dict[str, Any] = {}
    for output_name in declared_outputs:
        if output_name in result:
            output_values[output_name] = result[output_name]
    for key in ("element_id", "id", "call_id", "collection_id", "workflow_id", "field_id"):
        if key in result and key not in output_values:
            output_values[key] = result[key]
    if output_values:
        state.outputs[step_id] = output_values


def _resolve_string(value: str, state: DependencyState) -> str:
    def replace(match: re.Match[str]) -> str:
        step_id, output_name = match.group(1), match.group(2)
        step_outputs = state.outputs.get(step_id, {})
        if output_name not in step_outputs:
            placeholder = match.group(0)
            if placeholder not in state.unresolved:
                state.unresolved.append(placeholder)
            return placeholder
        return str(step_outputs[output_name])

    return PLACEHOLDER_RE.sub(replace, value)


def resolve_step_arguments(args: dict[str, Any], state: DependencyState) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            resolved[key] = _resolve_string(value, state)
        elif isinstance(value, dict):
            resolved[key] = resolve_step_arguments(value, state)
        elif isinstance(value, list):
            resolved[key] = [
                _resolve_string(item, state) if isinstance(item, str) else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved
```

- [ ] **Step 4: Integrate resolver into compiler**

Modify `src/bubble_mcp/language/compiler.py`:

```python
from bubble_mcp.language.dependencies import DependencyState, resolve_step_arguments
```

At the start of `compile_framework_program()`:

```python
dependency_state = DependencyState()
```

Before normalizing step arguments:

```python
step_args = resolve_step_arguments(step.arguments, dependency_state)
```

After compilation, include unresolved placeholders in the response:

```python
"unresolved_dependencies": dependency_state.unresolved,
```

If `dependency_state.unresolved` is non-empty and the affected step is mutating, return:

```python
{
    "ok": False,
    "error": "framework_program_has_unresolved_dependencies",
    "framework": adapter.framework_id,
    "profile": profile,
    "unresolved_dependencies": dependency_state.unresolved,
    "compiled_calls": compiled_calls,
}
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/bubble_mcp/language/dependencies.py src/bubble_mcp/language/compiler.py tests/unit/test_language_program.py
git commit -m "feat: resolve framework program dependencies"
```

---

### Task 4: Deterministic Quality Gates

**Files:**
- Create: `src/bubble_mcp/language/quality.py`
- Modify: `src/bubble_mcp/language/compiler.py`
- Test: `tests/unit/test_language_program.py`

- [ ] **Step 1: Write failing quality policy tests**

Append to `tests/unit/test_language_program.py`:

```python
from bubble_mcp.language.quality import evaluate_compiled_calls


def test_quality_requires_preview_for_mutating_calls() -> None:
    result = evaluate_compiled_calls(
        [
            {
                "tool": "create_button",
                "arguments": {
                    "profile": "cliente2",
                    "context": "index",
                    "parent": "root",
                    "label": "Start",
                    "execute": True,
                },
            }
        ],
        profile="cliente2",
    )

    assert result["ok"] is False
    assert result["violations"][0]["code"] == "mutating_call_must_start_as_preview"


def test_quality_applies_button_defaults_when_missing() -> None:
    result = evaluate_compiled_calls(
        [
            {
                "tool": "create_button",
                "arguments": {
                    "profile": "cliente2",
                    "context": "index",
                    "parent": "root",
                    "label": "Start",
                    "execute": False,
                },
            }
        ],
        profile="cliente2",
    )

    assert result["ok"] is True
    assert result["normalized_calls"][0]["arguments"]["fit_width"] is True
    assert result["normalized_calls"][0]["arguments"]["fit_height"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py -q
```

Expected: fail because `bubble_mcp.language.quality` does not exist.

- [ ] **Step 3: Implement quality policies**

Create `src/bubble_mcp/language/quality.py`:

```python
"""Deterministic quality gates for framework-compiled Bubble MCP programs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


VISUAL_DEFAULTS: dict[str, dict[str, Any]] = {
    "create_button": {"fit_width": True, "fit_height": True},
    "create_text": {"fit_height": True},
    "create_icon": {"width": 20, "height": 20, "fixed_width": True, "fixed_height": True},
    "create_image": {"width": 120, "fixed_width": True, "min_height": 64},
    "create_shape": {"width": 120, "height": 120, "fixed_width": True, "fixed_height": True},
    "create_group": {"layout": "column", "min_height": 40, "fit_height": True, "min_width": 40},
    "create_input": {"height": 44, "fixed_height": True, "min_width": 0, "max_width": 240},
}


def _apply_visual_defaults(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    for key, value in VISUAL_DEFAULTS.get(tool, {}).items():
        normalized.setdefault(key, value)
    if normalized.get("fixed_width") is True and "width" in normalized:
        normalized.setdefault("min_width", normalized["width"])
        normalized.setdefault("max_width", normalized["width"])
    if normalized.get("fixed_height") is True and "height" in normalized:
        normalized.setdefault("min_height", normalized["height"])
        normalized.setdefault("max_height", normalized["height"])
    return normalized


def evaluate_compiled_calls(calls: list[dict[str, Any]], *, profile: str) -> dict[str, Any]:
    normalized_calls = deepcopy(calls)
    violations: list[dict[str, Any]] = []
    for index, call in enumerate(normalized_calls, start=1):
        tool = str(call.get("tool") or "")
        raw_args = call.get("arguments")
        args = raw_args if isinstance(raw_args, dict) else {}
        if args.get("profile") not in (None, "", profile):
            violations.append(
                {
                    "step": index,
                    "tool": tool,
                    "code": "compiled_call_profile_mismatch",
                    "message": "Compiled call profile must match the requested framework profile.",
                }
            )
        if args.get("execute") is True:
            violations.append(
                {
                    "step": index,
                    "tool": tool,
                    "code": "mutating_call_must_start_as_preview",
                    "message": "Mutating calls must compile with execute=false before explicit execution.",
                }
            )
        call["arguments"] = _apply_visual_defaults(tool, args)
    return {
        "ok": not violations,
        "violations": violations,
        "normalized_calls": normalized_calls,
        "policy_version": "framework_quality_v2",
    }
```

- [ ] **Step 4: Integrate quality into compiler**

Modify `src/bubble_mcp/language/compiler.py`:

```python
from bubble_mcp.language.quality import evaluate_compiled_calls
```

Before returning success:

```python
quality = evaluate_compiled_calls(compiled_calls, profile=profile)
if not quality["ok"]:
    return {
        "ok": False,
        "error": "framework_program_quality_gate_failed",
        "framework": adapter.framework_id,
        "profile": profile,
        "quality": quality,
        "compiled_calls": compiled_calls,
    }
compiled_calls = quality["normalized_calls"]
```

Include in success response:

```python
"quality": quality,
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py tests/unit/test_language_registry.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/bubble_mcp/language/quality.py src/bubble_mcp/language/compiler.py tests/unit/test_language_program.py
git commit -m "feat: add framework program quality gates"
```

---

### Task 5: Framework Program Runner

**Files:**
- Create: `src/bubble_mcp/frameworks/program_runner.py`
- Modify: `src/bubble_mcp/frameworks/__init__.py`
- Test: `tests/unit/test_framework_program_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create `tests/unit/test_framework_program_runner.py`:

```python
from bubble_mcp.frameworks.program_runner import execute_framework_program


def test_execute_framework_program_preview_mode_does_not_execute_mutations(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = execute_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Preview CTA",
            "execution": {"mode": "preview", "approval": "required"},
            "steps": [
                {
                    "intent": "create_button",
                    "context": "index",
                    "parent": "root",
                    "text": "Start",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    assert result["executed"] is False
    assert result["compiled"]["compiled_calls"][0]["arguments"]["execute"] is False


def test_execute_framework_program_execute_requires_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = execute_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Execute CTA",
            "execution": {"mode": "execute", "approval": "required"},
            "steps": [
                {
                    "intent": "create_button",
                    "context": "index",
                    "parent": "root",
                    "text": "Start",
                }
            ],
        },
        approved=False,
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_execution_requires_approval"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_program_runner.py -q
```

Expected: fail because `bubble_mcp.frameworks.program_runner` does not exist.

- [ ] **Step 3: Implement preview and approval runner**

Create `src/bubble_mcp/frameworks/program_runner.py`:

```python
"""Gated execution runtime for framework-compiled Bubble MCP programs."""

from __future__ import annotations

from typing import Any

from bubble_mcp.frameworks.artifacts import sync_framework_evidence
from bubble_mcp.language.compiler import compile_framework_program


def _execution_mode(program: dict[str, Any], explicit_mode: str | None) -> str:
    if explicit_mode:
        return explicit_mode
    execution = program.get("execution")
    if isinstance(execution, dict):
        return str(execution.get("mode") or "preview")
    return "preview"


def execute_framework_program(
    *,
    framework: str,
    profile: str,
    program: dict[str, Any],
    mode: str | None = None,
    approved: bool = False,
    artifact_dir: str | None = None,
) -> dict[str, Any]:
    compiled = compile_framework_program(framework=framework, profile=profile, program=program)
    if not compiled.get("ok"):
        return {"ok": False, "error": "framework_program_compile_failed", "compiled": compiled}
    resolved_mode = _execution_mode(program, mode)
    if resolved_mode == "preview":
        evidence = {
            "summary": "Framework program compiled in preview mode.",
            "compiled_calls": compiled.get("compiled_calls", []),
            "approval_required": compiled.get("approval_required", False),
        }
        sync_result = sync_framework_evidence(
            framework=framework,
            profile=profile,
            evidence=evidence,
            artifact_dir=None,
        ) if artifact_dir is None else sync_framework_evidence(
            framework=framework,
            profile=profile,
            evidence=evidence,
            artifact_dir=__import__("pathlib").Path(artifact_dir),
        )
        return {
            "ok": True,
            "mode": "preview",
            "executed": False,
            "compiled": compiled,
            "evidence": sync_result,
        }
    if compiled.get("approval_required") and not approved:
        return {
            "ok": False,
            "error": "framework_program_execution_requires_approval",
            "mode": resolved_mode,
            "compiled": compiled,
        }
    return {
        "ok": False,
        "error": "framework_program_native_execution_dispatch_not_wired",
        "mode": resolved_mode,
        "compiled": compiled,
    }
```

- [ ] **Step 4: Wire actual MCP dispatch execution**

Modify `program_runner.py` to route calls through existing server execution functions:

```python
from bubble_mcp.server.tools import call_tool_by_name
```

If no direct helper exists, add a small internal helper in `src/bubble_mcp/server/tools.py`:

```python
def call_tool_by_name(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return _call_tool(name, arguments)
```

The runner must set `execute=True` only after approval:

```python
def _execution_arguments(args: dict[str, Any]) -> dict[str, Any]:
    execution_args = dict(args)
    if "execute" in execution_args:
        execution_args["execute"] = True
    return execution_args
```

For each call:

```python
result = call_tool_by_name(call["tool"], _execution_arguments(call["arguments"]))
step_results.append({"tool": call["tool"], "result": result})
if not result.get("ok", True):
    break
```

After successful mutating execution, append refresh and evidence:

```python
refresh_result = call_tool_by_name("bubble_profile_cache_refresh", {"profile": profile, "force": True})
evidence = {
    "summary": "Framework program executed through gated MCP runner.",
    "step_results": step_results,
    "refresh_result": refresh_result,
}
```

- [ ] **Step 5: Extend runner tests with mocked dispatch**

Append to `tests/unit/test_framework_program_runner.py`:

```python
def test_execute_framework_program_runs_after_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls = []

    def fake_call_tool_by_name(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "tool": name}

    monkeypatch.setattr(
        "bubble_mcp.frameworks.program_runner.call_tool_by_name",
        fake_call_tool_by_name,
    )

    result = execute_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Execute CTA",
            "execution": {"mode": "execute", "approval": "required"},
            "steps": [
                {
                    "intent": "create_button",
                    "context": "index",
                    "parent": "root",
                    "text": "Start",
                }
            ],
        },
        approved=True,
    )

    assert result["ok"] is True
    assert result["mode"] == "execute"
    assert calls[0][0] == "create_button"
    assert calls[0][1]["execute"] is True
    assert calls[-1][0] == "bubble_profile_cache_refresh"
```

- [ ] **Step 6: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_program_runner.py tests/unit/test_language_program.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/bubble_mcp/frameworks/program_runner.py src/bubble_mcp/frameworks/__init__.py src/bubble_mcp/server/tools.py tests/unit/test_framework_program_runner.py
git commit -m "feat: add gated framework program runner"
```

---

### Task 6: Framework Text To Program Planner

**Files:**
- Create: `src/bubble_mcp/frameworks/text_planner.py`
- Test: `tests/unit/test_framework_text_planner.py`

- [ ] **Step 1: Write failing text planner tests**

Create `tests/unit/test_framework_text_planner.py`:

```python
from bubble_mcp.frameworks.text_planner import plan_framework_text


def test_plan_framework_text_extracts_visual_and_verification_steps() -> None:
    result = plan_framework_text(
        framework="superpowers",
        profile="cliente2",
        text="""
        Objective: Build checkout CTA.
        - Find page checkout.
        - Create a section named Checkout controls inside root.
        - Add button labeled Start checkout inside Checkout controls.
        - Refresh cache and verify Start checkout exists.
        """,
    )

    assert result["ok"] is True
    assert result["program"]["objective"] == "Build checkout CTA."
    assert [step["intent"] for step in result["program"]["steps"]] == [
        "verify_context",
        "create_container",
        "create_button",
        "refresh_context",
        "verify_context",
    ]


def test_plan_framework_text_returns_questions_for_ambiguous_mutation() -> None:
    result = plan_framework_text(
        framework="bmad",
        profile="cliente2",
        text="Create the thing on the page.",
    )

    assert result["ok"] is False
    assert result["error"] == "framework_text_requires_clarification"
    assert result["questions"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_text_planner.py -q
```

Expected: fail because `bubble_mcp.frameworks.text_planner` does not exist.

- [ ] **Step 3: Implement deterministic text planner**

Create `src/bubble_mcp/frameworks/text_planner.py`:

```python
"""Convert framework text artifacts into compact Bubble MCP programs."""

from __future__ import annotations

import re
from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter


def _objective(text: str) -> str:
    match = re.search(r"objective:\s*(.+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else "Framework text program"


def _line_steps(text: str) -> list[str]:
    return [
        line.strip(" -\t")
        for line in text.splitlines()
        if line.strip().startswith(("-", "*"))
    ]


def _quoted_or_after(keyword: str, line: str) -> str:
    quoted = re.search(r"['\"]([^'\"]+)['\"]", line)
    if quoted:
        return quoted.group(1).strip()
    match = re.search(keyword + r"\s+([a-zA-Z0-9 _-]+)", line, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def plan_framework_text(*, framework: str, profile: str, text: str) -> dict[str, Any]:
    adapter = get_adapter(framework)
    content = str(text or "")
    steps: list[dict[str, Any]] = []
    questions: list[str] = []
    for line in _line_steps(content):
        lower = line.lower()
        if "find page" in lower or "verify page" in lower:
            query = line.split("page", 1)[-1].strip(". ")
            steps.append({"intent": "verify_context", "query": query or line, "exact": False})
        elif "create a section" in lower or "create section" in lower:
            name = _quoted_or_after("named", line) or "Generated section"
            steps.append({"intent": "create_container", "context": "index", "parent": "root", "label": name})
        elif "add button" in lower or "create button" in lower:
            label = _quoted_or_after("labeled", line) or _quoted_or_after("label", line)
            if not label:
                questions.append("What should the button label be?")
            steps.append({"intent": "create_button", "context": "index", "parent": "root", "text": label})
        elif "refresh" in lower and "cache" in lower:
            steps.append({"intent": "refresh_context"})
        elif "verify" in lower:
            steps.append({"intent": "verify_context", "query": line, "exact": False})
    if questions or not steps or any(step.get("text") == "" for step in steps):
        return {
            "ok": False,
            "error": "framework_text_requires_clarification",
            "framework": adapter.framework_id,
            "profile": profile,
            "questions": questions or ["Which Bubble target, parent, and operation should be used?"],
        }
    return {
        "ok": True,
        "framework": adapter.framework_id,
        "profile": profile,
        "program": {
            "objective": _objective(content),
            "execution": {"mode": "preview", "approval": "required"},
            "steps": steps,
        },
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_text_planner.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/frameworks/text_planner.py tests/unit/test_framework_text_planner.py
git commit -m "feat: plan framework text into mcp programs"
```

---

### Task 7: External Framework Workspace Sync

**Files:**
- Create: `src/bubble_mcp/frameworks/workspace.py`
- Modify: `src/bubble_mcp/frameworks/artifacts.py`
- Test: `tests/unit/test_framework_workspace.py`

- [ ] **Step 1: Write failing workspace tests**

Create `tests/unit/test_framework_workspace.py`:

```python
from pathlib import Path

from bubble_mcp.frameworks.workspace import detect_framework_workspace, sync_artifacts_to_workspace


def test_detect_framework_workspace_identifies_bmad(tmp_path: Path) -> None:
    (tmp_path / "_bmad-output" / "planning-artifacts").mkdir(parents=True)

    result = detect_framework_workspace(tmp_path)

    assert result["ok"] is True
    assert result["framework"] == "bmad"


def test_sync_artifacts_to_workspace_writes_framework_files(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    (workspace / "_bmad-output" / "planning-artifacts").mkdir(parents=True)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (artifact_dir / "architecture.md").write_text("# Architecture\n", encoding="utf-8")

    result = sync_artifacts_to_workspace(
        framework="bmad",
        artifact_dir=artifact_dir,
        workspace_dir=workspace,
    )

    assert result["ok"] is True
    assert (workspace / "_bmad-output" / "planning-artifacts" / "prd.md").read_text(encoding="utf-8") == "# PRD\n"
    assert (workspace / "_bmad-output" / "planning-artifacts" / "architecture.md").exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_workspace.py -q
```

Expected: fail because `bubble_mcp.frameworks.workspace` does not exist.

- [ ] **Step 3: Implement workspace detection and sync**

Create `src/bubble_mcp/frameworks/workspace.py`:

```python
"""External framework workspace import/export helpers."""

from __future__ import annotations

import shutil
from pathlib import Path


FRAMEWORK_LAYOUTS = {
    "bmad": {
        "marker": "_bmad-output",
        "targets": {
            "project-brief.md": "_bmad-output/planning-artifacts/project-brief.md",
            "prd.md": "_bmad-output/planning-artifacts/prd.md",
            "architecture.md": "_bmad-output/planning-artifacts/architecture.md",
            "epics.md": "_bmad-output/planning-artifacts/epics.md",
            "stories.md": "_bmad-output/implementation-artifacts/stories.md",
            "validation-evidence.md": "_bmad-output/implementation-artifacts/validation-evidence.md",
        },
    },
    "superpowers": {
        "marker": "docs/superpowers",
        "targets": {
            "spec.md": "docs/superpowers/spec.md",
            "implementation-plan.md": "docs/superpowers/implementation-plan.md",
            "execution-gates.md": "docs/superpowers/execution-gates.md",
            "verification-checklist.md": "docs/superpowers/verification-checklist.md",
        },
    },
    "sdd": {
        "marker": "docs/sdd",
        "targets": {
            "specification.md": "docs/sdd/specification.md",
            "fixtures.md": "docs/sdd/fixtures.md",
            "acceptance-tests.md": "docs/sdd/acceptance-tests.md",
            "traceability.md": "docs/sdd/traceability.md",
        },
    },
}


def detect_framework_workspace(workspace_dir: Path) -> dict[str, object]:
    root = workspace_dir.expanduser().resolve(strict=False)
    for framework, layout in FRAMEWORK_LAYOUTS.items():
        if (root / str(layout["marker"])).exists():
            return {"ok": True, "framework": framework, "workspace_dir": str(root)}
    return {"ok": False, "error": "framework_workspace_not_detected", "workspace_dir": str(root)}


def sync_artifacts_to_workspace(*, framework: str, artifact_dir: Path, workspace_dir: Path) -> dict[str, object]:
    normalized = str(framework or "").strip().lower()
    if normalized not in FRAMEWORK_LAYOUTS:
        raise ValueError(f"Unsupported framework workspace: {framework}")
    root = workspace_dir.expanduser().resolve(strict=False)
    source_root = artifact_dir.expanduser().resolve(strict=True)
    copied: list[str] = []
    targets = FRAMEWORK_LAYOUTS[normalized]["targets"]
    assert isinstance(targets, dict)
    for source_name, target_relative in targets.items():
        source = source_root / source_name
        if not source.exists():
            continue
        target = root / str(target_relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(target))
    return {"ok": True, "framework": normalized, "workspace_dir": str(root), "copied": copied}
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_workspace.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/frameworks/workspace.py tests/unit/test_framework_workspace.py
git commit -m "feat: sync framework workspace artifacts"
```

---

### Task 8: Incremental Language Registry Cache

**Files:**
- Create: `src/bubble_mcp/language/cache.py`
- Modify: `src/bubble_mcp/language/registry.py`
- Modify: `src/bubble_mcp/language/query.py`
- Test: `tests/unit/test_language_registry.py`

- [ ] **Step 1: Write failing cache tests**

Append to `tests/unit/test_language_registry.py`:

```python
from bubble_mcp.language.cache import cache_language_index, cached_language_index


def test_language_cache_round_trips_by_framework_and_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    index = {"registry_version": "sha256:abc", "families": {"visual_editor": 10}}

    saved = cache_language_index(framework="bmad", profile="cliente2", index=index)
    loaded = cached_language_index(framework="bmad", profile="cliente2")

    assert saved["ok"] is True
    assert loaded["ok"] is True
    assert loaded["index"]["registry_version"] == "sha256:abc"


def test_language_query_reports_cache_hit_when_version_matches(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    first = language_query(query="create button", profile="cliente2", limit=1)
    cache_language_index(framework="bmad", profile="cliente2", index={"registry_version": first["registry_version"]})
    second = language_query(
        query="create button",
        profile="cliente2",
        limit=1,
        framework="bmad",
        cached_registry_version=first["registry_version"],
    )

    assert second["cache"]["hit"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_registry.py -q
```

Expected: fail because cache APIs and query parameters do not exist.

- [ ] **Step 3: Implement cache APIs**

Create `src/bubble_mcp/language/cache.py`:

```python
"""Low-token language registry cache for framework adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value or "").strip()) or "default"


def _cache_path(framework: str, profile: str) -> Path:
    return get_config_dir() / "language" / "cache" / _safe_segment(framework) / f"{_safe_segment(profile)}.json"


def cache_language_index(*, framework: str, profile: str, index: dict[str, Any]) -> dict[str, Any]:
    path = _cache_path(framework, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(path), "registry_version": index.get("registry_version")}


def cached_language_index(*, framework: str, profile: str) -> dict[str, Any]:
    path = _cache_path(framework, profile)
    if not path.exists():
        return {"ok": False, "error": "language_cache_miss", "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"ok": False, "error": "language_cache_invalid", "path": str(path)}
    return {"ok": True, "path": str(path), "index": payload}
```

- [ ] **Step 4: Add cache metadata to query**

Modify `language_query()` signature in `src/bubble_mcp/language/query.py`:

```python
framework: str | None = None,
cached_registry_version: str | None = None,
```

Add:

```python
cache = {"hit": False, "reason": "not_requested"}
if framework and cached_registry_version:
    cache = {
        "hit": cached_registry_version == index["registry_version"],
        "cached_registry_version": cached_registry_version,
        "current_registry_version": index["registry_version"],
    }
```

Return:

```python
"cache": cache,
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_registry.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/bubble_mcp/language/cache.py src/bubble_mcp/language/query.py tests/unit/test_language_registry.py
git commit -m "feat: cache dynamic language registry"
```

---

### Task 9: MCP And CLI Surface For V2

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/cli/main.py`
- Test: `tests/unit/test_mcp_server.py`
- Test: `tests/unit/test_cli_commands.py`

- [ ] **Step 1: Write failing MCP schema tests**

Append to `tests/unit/test_mcp_server.py` near existing language tests:

```python
def test_framework_v2_tools_are_exposed() -> None:
    tools = {tool["name"]: tool for tool in handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}

    assert "bubble_framework_plan_from_text" in tools
    assert "bubble_framework_execute_program" in tools
    assert "bubble_framework_workspace_sync" in tools
    assert "bubble_language_cache_status" in tools
```

- [ ] **Step 2: Write failing CLI tests**

Append to `tests/unit/test_cli_commands.py`:

```python
def test_language_cache_cli_command(cli_runner, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = cli_runner(["language", "cache-status", "--framework", "bmad", "--profile", "cliente2"])

    assert result.exit_code == 0
    assert "language_cache" in result.output
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py -q
```

Expected: fail because V2 tools and CLI commands are not exposed.

- [ ] **Step 4: Add MCP schemas**

Add schemas to `src/bubble_mcp/server/schema_families.py`:

```python
{
    "name": "bubble_framework_plan_from_text",
    "description": "Convert BMAD, Superpowers, or SDD text into a structured Bubble MCP framework program.",
    "inputSchema": {
        "type": "object",
        "required": ["framework", "profile", "text"],
        "properties": {
            "framework": {"type": "string"},
            "profile": {"type": "string"},
            "text": {"type": "string"},
        },
    },
    "annotations": {"readOnlyHint": True},
}
```

Add equivalent schemas for:

```python
"bubble_framework_execute_program"
"bubble_framework_workspace_sync"
"bubble_language_cache_status"
```

Use `readOnlyHint: False` for execute and workspace sync because they write locally or may execute Bubble mutations.

- [ ] **Step 5: Dispatch MCP tools**

Modify `src/bubble_mcp/server/tools.py`:

```python
from bubble_mcp.frameworks.program_runner import execute_framework_program
from bubble_mcp.frameworks.text_planner import plan_framework_text
from bubble_mcp.frameworks.workspace import detect_framework_workspace, sync_artifacts_to_workspace
from bubble_mcp.language.cache import cached_language_index
```

Add dispatch branches:

```python
if name == "bubble_framework_plan_from_text":
    return plan_framework_text(
        framework=str(arguments.get("framework") or ""),
        profile=str(arguments.get("profile") or ""),
        text=str(arguments.get("text") or ""),
    )
if name == "bubble_framework_execute_program":
    program = arguments.get("program")
    if not isinstance(program, dict):
        raise ValueError("bubble_framework_execute_program requires program object.")
    return execute_framework_program(
        framework=str(arguments.get("framework") or ""),
        profile=str(arguments.get("profile") or ""),
        program=program,
        mode=str(arguments.get("mode") or "") or None,
        approved=bool(arguments.get("approved", False)),
        artifact_dir=str(arguments.get("artifact_dir") or "") or None,
    )
if name == "bubble_language_cache_status":
    return cached_language_index(
        framework=str(arguments.get("framework") or ""),
        profile=str(arguments.get("profile") or ""),
    )
```

- [ ] **Step 6: Add CLI commands**

Modify `src/bubble_mcp/cli/main.py` under the `language` parser:

```python
cache_parser = language_subparsers.add_parser("cache-status", help="Inspect framework language cache status.")
cache_parser.add_argument("--framework", required=True)
cache_parser.add_argument("--profile", required=True)
```

In dispatch:

```python
if args.language_command == "cache-status":
    from bubble_mcp.language.cache import cached_language_index

    print(json.dumps({"language_cache": cached_language_index(framework=args.framework, profile=args.profile)}, indent=2, sort_keys=True))
    return 0
```

- [ ] **Step 7: Run tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/bubble_mcp/server/schema_families.py src/bubble_mcp/server/tools.py src/bubble_mcp/cli/main.py tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py
git commit -m "feat: expose framework language v2 tools"
```

---

### Task 10: Documentation And End-To-End Validation

**Files:**
- Modify: `docs/framework-adapters.md`
- Modify: `docs/cli-reference.md`
- Test: existing validation suites.

- [ ] **Step 1: Update framework documentation**

Add this section to `docs/framework-adapters.md`:

```markdown
## V2 Program Runtime

The V2 flow is:

1. `bubble_framework_plan_from_text` converts framework text artifacts into a structured program when the framework does not already provide one.
2. `bubble_framework_compile_program` validates syntax, resolves intent aliases, applies dependency resolution, injects profile, adds preview flags, and runs deterministic quality gates.
3. `bubble_framework_execute_program` runs the compiled sequence in preview or approved execution mode.
4. The runner refreshes the profile cache after approved mutations and records evidence with `bubble_framework_sync_evidence`.
5. `bubble_framework_workspace_sync` copies generated artifacts into a detected external BMAD, Superpowers, or SDD workspace when requested.
6. `bubble_language_cache_status`, `bubble_language_diff`, and `bubble_language_query` let frameworks refresh only the registry slices they need.

Frameworks must not request `tools/list` as their primary language source. Use `bubble_language_index`, `bubble_language_query`, `bubble_language_tool_detail`, and `bubble_language_diff` instead.
```

- [ ] **Step 2: Update CLI reference**

Add this block to `docs/cli-reference.md` under language/framework commands:

````markdown
```bash
bubble-mcp language cache-status --framework bmad --profile cliente2
```

Returns the current cached registry version for a framework/profile pair.
````

- [ ] **Step 3: Run focused Python tests**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/unit/test_language_program.py \
  tests/unit/test_language_registry.py \
  tests/unit/test_framework_program_runner.py \
  tests/unit/test_framework_text_planner.py \
  tests/unit/test_framework_workspace.py \
  tests/unit/test_mcp_server.py \
  tests/unit/test_cli_commands.py \
  -q
```

Expected: all focused tests pass.

- [ ] **Step 4: Run static checks**

Run:

```bash
./.venv/bin/python -m ruff check src tests scripts
PYTHONPATH=src ./.venv/bin/python -m mypy src
git diff --check
```

Expected:

```text
All checks passed!
Success: no issues found
```

- [ ] **Step 5: Run Node bridge tests**

Run:

```bash
npm test
```

Expected: all Node bridge tests pass.

- [ ] **Step 6: Run full Python suite when unrelated worktree files are stable**

Run:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Expected: all tests pass. If unrelated untracked files from another task are present and failing, run only the focused V2 suite from Step 3 and document the unrelated files by path.

- [ ] **Step 7: Commit**

```bash
git add docs/framework-adapters.md docs/cli-reference.md
git commit -m "docs: document framework language v2"
```

---

## Final Acceptance Criteria

- Frameworks can discover the Bubble MCP language without full catalog dumps.
- Frameworks can submit compact structured programs and receive preview-safe compiled MCP calls.
- Programs with missing required arguments, profile mismatches, unresolved dependencies, or unsafe execution flags fail deterministically before execution.
- Programs can be previewed without Bubble writes.
- Approved programs can execute through MCP dispatch, refresh cache, and record evidence.
- Framework text artifacts can be converted into structured programs or return clarification questions.
- External framework workspaces can receive generated artifacts in place.
- Registry cache allows framework/profile pairs to avoid repeated full language discovery.
- MCP and CLI expose the V2 capabilities.
- Documentation explains the low-token flow and safety gates.

## Validation Matrix

| Area | Test File | Required Command |
| --- | --- | --- |
| Program contract | `tests/unit/test_language_program.py` | `PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py -q` |
| Intent language | `tests/unit/test_language_program.py`, `tests/unit/test_language_registry.py` | `PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_language_program.py tests/unit/test_language_registry.py -q` |
| Program runner | `tests/unit/test_framework_program_runner.py` | `PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_program_runner.py -q` |
| Text planner | `tests/unit/test_framework_text_planner.py` | `PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_text_planner.py -q` |
| Workspace sync | `tests/unit/test_framework_workspace.py` | `PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_framework_workspace.py -q` |
| MCP and CLI | `tests/unit/test_mcp_server.py`, `tests/unit/test_cli_commands.py` | `PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py -q` |
| Static checks | all touched Python | `./.venv/bin/python -m ruff check src tests scripts && PYTHONPATH=src ./.venv/bin/python -m mypy src && git diff --check` |
| Node bridge regression | `test-node/*.test.mjs` | `npm test` |

## Self-Review

- Spec coverage: The seven V2 requirements are mapped to Tasks 2 through 9, with Task 10 covering docs and validation.
- Placeholder scan: This plan avoids unspecified implementation slots and gives concrete files, test code, commands, and expected outputs for each task.
- Type consistency: Program, intent, dependency, quality, runner, text planner, workspace, cache, MCP, and CLI APIs use consistent framework/profile/program naming across tasks.
