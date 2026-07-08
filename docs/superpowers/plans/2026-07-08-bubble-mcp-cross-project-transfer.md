# Bubble MCP Cross-Project Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build first-class Bubble project-to-project transfer for pages, reusables, element subtrees, and asset references with dependency inventory, target mapping, preview-first execution, evidence output, and an ID mapping registry.

**Architecture:** Add a focused `bubble_mcp.transfer` package around the existing profile, context, compiler, runtime dispatch, and execution primitives. The transfer flow must resolve two independent profiles, build a source inventory from the source context, map or create target dependencies, compile target Bubble write payloads, and execute only through the existing authenticated target profile session with validation and explicit approval. It must not copy secrets, sessions, private credentials, or API Connector private values.

**Tech Stack:** Python 3.11, dataclasses, JSON config-dir artifacts, existing `bubble_mcp.context`, `bubble_mcp.aria_dispatch`, `bubble_mcp.execution`, stdio MCP server schemas, argparse CLI, pytest, ruff, and real Bubble smoke only after unit coverage passes.

---

## Source Requirements

Primary source spec:

- `/Users/pedroduarte/Documents/Development/Custom/aria/docs/superpowers/specs/2026-07-04-bubble-mcp-extension-kernel-design.md`

Relevant source-spec decisions:

- Cross-project transfer must be a dedicated workflow, not a shallow clone command.
- The tentative module and skill family is `bubble_transfer`.
- The workflow must inventory source pages, reusables, styles, workflows, data types, option sets, API Connector entries, plugin dependencies, and assets.
- The workflow must build a target transfer plan with create-or-map decisions.
- The workflow must preview target changes with a dependency report.
- Execution must happen in dependency order only after validation and confirmation.
- The workflow must produce an evidence bundle and an ID mapping registry.
- API Connector transfer must separate structure from secrets. Secrets and tokens are never copied automatically.
- Database collections are transferred as Bubble schema bundles by default: data types, fields, privacy rules, and related option sets. Live records are a separate high-risk migration mode and default to skipped.
- API Connector calls are transferred as structure-only bundles by default: resource/call names, methods, URLs, parameter/header/body shape, and safe initialization schema. Private keys, OAuth tokens, bearer tokens, cookies, and private headers are never copied.

## Scope

### In Scope For This Plan

- Read-only source inventory for:
  - page;
  - reusable;
  - visual element subtree inside page or reusable;
  - database collection schema bundle: data types, fields, privacy rules, and related option sets;
  - API Connector resource and call definitions, excluding credentials and secret values;
  - referenced visual assets from source nodes;
  - styles, colors, fonts, data types, option sets, workflows, custom states, and plugin/API Connector dependency references that are discoverable from source context.
- Transfer planning with:
  - `source_profile` and `target_profile`;
  - source object selector;
  - target context and parent;
  - target name override;
  - conflict policy;
  - collection/schema policy;
  - API Connector policy;
  - data records policy, defaulting to skip;
  - dependency actions: map existing, create copy, skip with warning, or block.
- Preview-first payload compilation for page, reusable, and element-subtree copies.
- Target-only execution through the target profile session.
- Local transfer plan/evidence storage under `BUBBLE_MCP_CONFIG_DIR/transfers/`.
- MCP tools and CLI commands for inventory, plan, preview, execute, and status.
- Unit tests for models, inventory, mapping, compiler, schemas, CLI, and server dispatch.
- Focused smoke dry-run against a configured profile pair.

### Out Of Scope For This Plan

- Copying Bubble account sessions, cookies, credentials, or secrets.
- Copying private API Connector credentials or OAuth tokens.
- Copying production database records by default.
- Migrating live data records without explicit data-record policy, source export evidence, and target import preview.
- Deploying target branches.
- Remote registry or cloud transfer service.
- Browser-click transfer automation.
- Full semantic migration of arbitrary backend workflows when dependencies cannot be resolved from context.

## User-Facing Tool Contract

Expose these native MCP tools:

1. `bubble_transfer_inventory`
   - Read-only.
   - Inputs: `source_profile`, `source_type`, `source_ref`, optional `source_context`, `include_dependencies`, `include_raw`.
   - Output: normalized inventory, dependency summary, warnings, and unsupported references.

2. `bubble_transfer_plan`
   - Read-only planning operation. It writes only a local plan artifact.
   - Inputs: `source_profile`, `target_profile`, `source_type`, `source_ref`, optional `source_context`, `target_context`, `target_parent`, `target_name`, `conflict_policy`, `asset_policy`, `dependency_policy`, `include_collections`, `collection_policy`, `include_api_connector`, `api_connector_policy`, `data_records_policy`.
   - Output: `transfer_id`, local plan path, dependency report, proposed target writes, blocked items, and next action.

3. `bubble_transfer_preview`
   - Read-only preview of an existing local transfer plan.
   - Inputs: `transfer_id` or `plan_path`, optional `include_payloads`.
   - Output: validation summary, payload count, estimated order, and redacted payload previews.

4. `bubble_transfer_execute`
   - Mutating target app operation.
   - Inputs: `transfer_id` or `plan_path`, `execute`, `confirm`, optional `max_steps`.
   - Requires `execute=true` and `confirm=true`.
   - Output: write results, evidence path, ID mapping path, target context refresh instructions.

5. `bubble_transfer_status`
   - Read-only local status.
   - Inputs: optional `transfer_id`, optional `profile`.
   - Output: list of local transfer plans and executed evidence.

Expose these CLI commands:

```bash
bubble-mcp transfer inventory --source-profile source --source-type reusable --source-ref "Header"
bubble-mcp transfer plan --source-profile source --target-profile target --source-type reusable --source-ref "Header" --target-context index --target-parent root
bubble-mcp transfer preview --transfer-id transfer_20260708_120000_header
bubble-mcp transfer execute --transfer-id transfer_20260708_120000_header --execute --confirm
bubble-mcp transfer status --profile target
```

## File Structure

Create:

- `src/bubble_mcp/transfer/__init__.py`: public transfer APIs.
- `src/bubble_mcp/transfer/models.py`: dataclasses and JSON conversion for inventory, dependency refs, transfer plans, ID mapping, and evidence.
- `src/bubble_mcp/transfer/profiles.py`: source/target profile readiness resolution without exposing session secrets.
- `src/bubble_mcp/transfer/inventory.py`: source object inventory extraction from compact context plus module/raw context metadata where available.
- `src/bubble_mcp/transfer/dependencies.py`: dependency extraction and classification.
- `src/bubble_mcp/transfer/collections.py`: Bubble data type, field, privacy rule, and option set bundle extraction and target planning.
- `src/bubble_mcp/transfer/api_connector.py`: API Connector resource/call structure extraction, secret redaction, and target setup checklist generation.
- `src/bubble_mcp/transfer/mapping.py`: target lookup, conflict policy, ID generation, and create-or-map decisions.
- `src/bubble_mcp/transfer/assets.py`: asset reference classification and optional download staging for target upload.
- `src/bubble_mcp/transfer/compiler.py`: compile transfer plan into ordered target write payloads.
- `src/bubble_mcp/transfer/store.py`: config-dir persistence for plans, previews, mappings, and evidence.
- `src/bubble_mcp/transfer/executor.py`: preview and execute transfer plans through target profile session.
- `tests/unit/test_transfer_models.py`
- `tests/unit/test_transfer_inventory.py`
- `tests/unit/test_transfer_collections.py`
- `tests/unit/test_transfer_api_connector.py`
- `tests/unit/test_transfer_mapping.py`
- `tests/unit/test_transfer_compiler.py`
- `tests/unit/test_transfer_store.py`
- `tests/unit/test_transfer_executor.py`

Modify:

- `src/bubble_mcp/server/schema_families.py`: add transfer tool schemas.
- `src/bubble_mcp/server/tools.py`: dispatch transfer tools.
- `src/bubble_mcp/server/agent_catalog.py`: add descriptions, schemas, annotations, and routing hints.
- `src/bubble_mcp/server/agent_guide.py`: add transfer recipe/runbook route.
- `src/bubble_mcp/runtime_coverage.py`: include transfer native tools in coverage.
- `src/bubble_mcp/cli/main.py`: add `transfer` subcommands.
- `docs/mcp-clients.md`: document agent-facing transfer workflow.
- `docs/cli-reference.md`: document transfer CLI.
- `docs/architecture.md`: mention transfer package and safety gates.
- `tests/unit/test_mcp_server.py`: schema, annotations, routing, and call dispatch tests.
- `tests/unit/test_cli_commands.py`: CLI parser and command dispatch tests.

## Data Model

Create `src/bubble_mcp/transfer/models.py` with these public dataclasses.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


SourceType = Literal["page", "reusable", "element"]
DependencyKind = Literal[
    "page",
    "reusable",
    "element",
    "style",
    "color",
    "font",
    "data_type",
    "data_field",
    "privacy_rule",
    "option_set",
    "api_connector",
    "api_connector_call",
    "plugin",
    "asset",
    "workflow",
    "custom_state",
]
DependencyAction = Literal["map_existing", "create_copy", "skip", "block"]
ConflictPolicy = Literal["fail", "rename", "replace", "reuse_existing"]
AssetPolicy = Literal["reference_url", "stage_and_upload", "skip"]
CollectionPolicy = Literal["skip", "map_existing", "create_missing", "replace_schema"]
ApiConnectorPolicy = Literal["skip", "map_existing", "structure_only"]
DataRecordsPolicy = Literal["skip", "export_manifest_only", "data_api_import_preview"]
TransferStatus = Literal["planned", "previewed", "executed", "failed"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TransferObjectRef:
    profile: str
    app_id: str
    app_version: str
    source_type: SourceType
    ref: str
    context: str | None = None
    bubble_id: str | None = None
    path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "source_type": self.source_type,
            "ref": self.ref,
            "context": self.context,
            "bubble_id": self.bubble_id,
            "path": list(self.path),
        }


@dataclass(frozen=True)
class TransferDependency:
    kind: DependencyKind
    key: str
    label: str
    source_id: str | None = None
    required: bool = True
    secret: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "source_id": self.source_id,
            "required": self.required,
            "secret": self.secret,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TransferInventory:
    source: TransferObjectRef
    root: dict[str, Any]
    nodes: list[dict[str, Any]]
    dependencies: list[TransferDependency]
    warnings: list[str] = field(default_factory=list)
    unsupported: list[TransferDependency] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "root": self.root,
            "nodes": list(self.nodes),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "warnings": list(self.warnings),
            "unsupported": [item.to_dict() for item in self.unsupported],
            "counts": {
                "nodes": len(self.nodes),
                "dependencies": len(self.dependencies),
                "warnings": len(self.warnings),
                "unsupported": len(self.unsupported),
            },
        }


@dataclass(frozen=True)
class TransferMappingDecision:
    dependency: TransferDependency
    action: DependencyAction
    target_id: str | None = None
    target_label: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency": self.dependency.to_dict(),
            "action": self.action,
            "target_id": self.target_id,
            "target_label": self.target_label,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TransferPlan:
    transfer_id: str
    source: TransferObjectRef
    target_profile: str
    target_app_id: str
    target_app_version: str
    target_context: str | None
    target_parent: str | None
    target_name: str | None
    conflict_policy: ConflictPolicy
    asset_policy: AssetPolicy
    collection_policy: CollectionPolicy
    api_connector_policy: ApiConnectorPolicy
    data_records_policy: DataRecordsPolicy
    dependency_decisions: list[TransferMappingDecision]
    write_payloads: list[dict[str, Any]]
    blocked_reasons: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    status: TransferStatus = "planned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "source": self.source.to_dict(),
            "target_profile": self.target_profile,
            "target_app_id": self.target_app_id,
            "target_app_version": self.target_app_version,
            "target_context": self.target_context,
            "target_parent": self.target_parent,
            "target_name": self.target_name,
            "conflict_policy": self.conflict_policy,
            "asset_policy": self.asset_policy,
            "collection_policy": self.collection_policy,
            "api_connector_policy": self.api_connector_policy,
            "data_records_policy": self.data_records_policy,
            "dependency_decisions": [item.to_dict() for item in self.dependency_decisions],
            "write_payloads": list(self.write_payloads),
            "blocked_reasons": list(self.blocked_reasons),
            "created_at": self.created_at,
            "status": self.status,
            "counts": {
                "dependency_decisions": len(self.dependency_decisions),
                "write_payloads": len(self.write_payloads),
                "blocked_reasons": len(self.blocked_reasons),
            },
        }
```

## Collection And API Connector Semantics

### Database Collection Bundles

Bubble collection transfer means schema transfer by default, not data migration.

The transfer inventory must identify:

- data type name;
- field exact Bubble key, including type suffixes such as `_text`, `_number`, or relational table suffixes;
- field display label when available;
- field type and relational target;
- privacy rules for the data type;
- option sets referenced by fields or expressions;
- dependencies from pages, reusables, workflows, and expressions that point to those data types or fields.

The transfer planner must support:

- `collection_policy=skip`: warn about schema dependencies and do not create schema payloads;
- `collection_policy=map_existing`: require matching data types and fields in the target app;
- `collection_policy=create_missing`: create missing data types, fields, option sets, and privacy rules when source context contains enough structure;
- `collection_policy=replace_schema`: blocked by default unless the implementation adds a dedicated destructive confirmation path.

Live records are not copied by the default transfer flow. If `data_records_policy` is anything other than `skip`, the plan must mark the operation as high risk, produce an explicit preview artifact, and require a future implementation backed by Bubble Data API/export evidence. This avoids accidental production data movement.

### API Connector Bundles

API Connector transfer means structure-only transfer by default.

The inventory must identify:

- API Connector resource/plugin id;
- API and call names;
- method;
- URL;
- visible parameters, headers, query params, body shape, and authentication mode metadata;
- safe initialized response shape/sample schema when available;
- references from workflows or elements that call the API.

The transfer planner must support:

- `api_connector_policy=skip`: warn and do not generate API Connector payloads;
- `api_connector_policy=map_existing`: require matching API/call names in the target app;
- `api_connector_policy=structure_only`: create missing API/call structure while redacting private values.

The planner must never copy API keys, OAuth secrets, bearer tokens, cookies, session headers, private headers, or environment-specific credentials. Instead, it must write a target setup checklist listing each value the developer must configure manually before the copied calls can be initialized or used.

## Implementation Tasks

### Task 1: Transfer Models And Store

**Files:**
- Create: `src/bubble_mcp/transfer/__init__.py`
- Create: `src/bubble_mcp/transfer/models.py`
- Create: `src/bubble_mcp/transfer/store.py`
- Test: `tests/unit/test_transfer_models.py`
- Test: `tests/unit/test_transfer_store.py`

- [ ] **Step 1: Write model serialization tests**

Add `tests/unit/test_transfer_models.py`:

```python
from bubble_mcp.transfer.models import (
    TransferDependency,
    TransferInventory,
    TransferMappingDecision,
    TransferObjectRef,
    TransferPlan,
)


def test_transfer_inventory_serializes_counts() -> None:
    source = TransferObjectRef(
        profile="source",
        app_id="source-app",
        app_version="test",
        source_type="reusable",
        ref="Header",
        bubble_id="bSrc1",
    )
    dependency = TransferDependency(kind="style", key="primary_button", label="Primary Button", source_id="st1")

    inventory = TransferInventory(
        source=source,
        root={"id": "bSrc1", "name": "Header"},
        nodes=[{"id": "bSrc1"}, {"id": "bChild"}],
        dependencies=[dependency],
        warnings=["plugin dependency detected"],
    )

    payload = inventory.to_dict()

    assert payload["source"]["profile"] == "source"
    assert payload["counts"] == {"nodes": 2, "dependencies": 1, "warnings": 1, "unsupported": 0}
    assert payload["dependencies"][0]["kind"] == "style"


def test_transfer_plan_serializes_policy_and_blocked_reasons() -> None:
    source = TransferObjectRef(
        profile="source",
        app_id="source-app",
        app_version="test",
        source_type="page",
        ref="index",
    )
    dependency = TransferDependency(kind="api_connector", key="stripe", label="Stripe", secret=True)
    decision = TransferMappingDecision(
        dependency=dependency,
        action="block",
        reason="API Connector secrets cannot be copied automatically.",
    )

    plan = TransferPlan(
        transfer_id="transfer_20260708_header",
        source=source,
        target_profile="target",
        target_app_id="target-app",
        target_app_version="test",
        target_context="index",
        target_parent="root",
        target_name="index_copy",
        conflict_policy="fail",
        asset_policy="reference_url",
        collection_policy="map_existing",
        api_connector_policy="structure_only",
        data_records_policy="skip",
        dependency_decisions=[decision],
        write_payloads=[],
        blocked_reasons=["API Connector secrets cannot be copied automatically."],
    )

    payload = plan.to_dict()

    assert payload["transfer_id"] == "transfer_20260708_header"
    assert payload["counts"]["dependency_decisions"] == 1
    assert payload["counts"]["blocked_reasons"] == 1
    assert payload["dependency_decisions"][0]["action"] == "block"
```

- [ ] **Step 2: Run model tests and verify they fail**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_models.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'bubble_mcp.transfer'
```

- [ ] **Step 3: Add transfer package and models**

Create `src/bubble_mcp/transfer/__init__.py`:

```python
"""Cross-project Bubble transfer planning and execution."""

from bubble_mcp.transfer.models import (
    TransferDependency,
    TransferInventory,
    TransferMappingDecision,
    TransferObjectRef,
    TransferPlan,
)

__all__ = [
    "TransferDependency",
    "TransferInventory",
    "TransferMappingDecision",
    "TransferObjectRef",
    "TransferPlan",
]
```

Add `src/bubble_mcp/transfer/models.py` using the exact dataclass code in the Data Model section.

- [ ] **Step 4: Run model tests and verify they pass**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_models.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Write store tests**

Add `tests/unit/test_transfer_store.py`:

```python
from pathlib import Path

from bubble_mcp.transfer.models import TransferObjectRef, TransferPlan
from bubble_mcp.transfer.store import load_transfer_plan, save_transfer_plan, transfer_plan_path


def test_save_and_load_transfer_plan_under_config_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    source = TransferObjectRef(
        profile="source",
        app_id="source-app",
        app_version="test",
        source_type="page",
        ref="index",
    )
    plan = TransferPlan(
        transfer_id="transfer_20260708_index",
        source=source,
        target_profile="target",
        target_app_id="target-app",
        target_app_version="test",
        target_context="index",
        target_parent="root",
        target_name="index_copy",
        conflict_policy="fail",
        asset_policy="reference_url",
        collection_policy="map_existing",
        api_connector_policy="structure_only",
        data_records_policy="skip",
        dependency_decisions=[],
        write_payloads=[{"v": 1, "appname": "target-app", "changes": []}],
    )

    path = save_transfer_plan(plan)
    loaded = load_transfer_plan("transfer_20260708_index")

    assert path == tmp_path / "transfers" / "transfer_20260708_index" / "plan.json"
    assert loaded["transfer_id"] == "transfer_20260708_index"
    assert loaded["target_profile"] == "target"
    assert transfer_plan_path("transfer_20260708_index") == path
```

- [ ] **Step 6: Implement store helpers**

Create `src/bubble_mcp/transfer/store.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.transfer.models import TransferPlan


def transfer_dir(transfer_id: str) -> Path:
    safe_id = "".join(char for char in transfer_id if char.isalnum() or char in {"_", "-"}).strip()
    if not safe_id:
        raise ValueError("transfer_id is required.")
    return get_config_dir() / "transfers" / safe_id


def transfer_plan_path(transfer_id: str) -> Path:
    return transfer_dir(transfer_id) / "plan.json"


def save_transfer_plan(plan: TransferPlan) -> Path:
    path = transfer_plan_path(plan.transfer_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_transfer_plan(transfer_id: str) -> dict[str, Any]:
    path = transfer_plan_path(transfer_id)
    if not path.exists():
        raise FileNotFoundError(f"Transfer plan not found: {transfer_id}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Transfer plan must be a JSON object: {path}")
    return raw


def load_transfer_plan_file(path: Path) -> dict[str, Any]:
    raw = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Transfer plan must be a JSON object: {path}")
    return raw
```

- [ ] **Step 7: Run store tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_models.py tests/unit/test_transfer_store.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add src/bubble_mcp/transfer/__init__.py src/bubble_mcp/transfer/models.py src/bubble_mcp/transfer/store.py tests/unit/test_transfer_models.py tests/unit/test_transfer_store.py
git commit -m "feat: add transfer plan models and storage"
```

### Task 2: Source And Target Profile Resolution

**Files:**
- Create: `src/bubble_mcp/transfer/profiles.py`
- Test: `tests/unit/test_transfer_profiles.py`

- [ ] **Step 1: Write profile resolution tests**

Add `tests/unit/test_transfer_profiles.py`:

```python
from pathlib import Path

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.sessions.store import BubbleSessionData, save_session
from bubble_mcp.transfer.profiles import resolve_transfer_profiles


def test_resolve_transfer_profiles_requires_two_distinct_profiles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="source",
            profiles={
                "source": BubbleProfile(name="source", app_id="source-app", appname="source-app"),
            },
        )
    )

    with pytest.raises(ValueError, match="target_profile"):
        resolve_transfer_profiles("source", "missing")

    with pytest.raises(ValueError, match="must be different"):
        resolve_transfer_profiles("source", "source")


def test_resolve_transfer_profiles_reports_context_and_target_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    source_context = tmp_path / "contexts" / "source" / "source-app-context.json"
    target_context = tmp_path / "contexts" / "target" / "target-app-context.json"
    source_context.parent.mkdir(parents=True)
    target_context.parent.mkdir(parents=True)
    source_context.write_text("{}", encoding="utf-8")
    target_context.write_text("{}", encoding="utf-8")
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="source",
            profiles={
                "source": BubbleProfile(
                    name="source",
                    app_id="source-app",
                    appname="source-app",
                    app_version="test",
                    app_json_path=str(source_context),
                ),
                "target": BubbleProfile(
                    name="target",
                    app_id="target-app",
                    appname="target-app",
                    app_version="test",
                    app_json_path=str(target_context),
                ),
            },
        )
    )
    save_session(
        BubbleSessionData(
            profile="target",
            app_id="target-app",
            app_version="test",
            cookies=[],
            headers={"user-agent": "test"},
            captured_at="2026-07-08T00:00:00+00:00",
            source="test",
            url="https://bubble.io/page?id=target-app",
            method="POST",
        )
    )

    resolved = resolve_transfer_profiles("source", "target")

    assert resolved.source.name == "source"
    assert resolved.target.name == "target"
    assert resolved.source_context_path == Path(source_context)
    assert resolved.target_context_path == Path(target_context)
    assert resolved.target_has_session is True
```

- [ ] **Step 2: Implement profile resolution**

Create `src/bubble_mcp/transfer/profiles.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bubble_mcp.context.detector import default_context_path
from bubble_mcp.core.config import BubbleProfile, load_settings, resolve_profile
from bubble_mcp.sessions.store import load_session


@dataclass(frozen=True)
class ResolvedTransferProfiles:
    source: BubbleProfile
    target: BubbleProfile
    source_context_path: Path | None
    target_context_path: Path | None
    target_has_session: bool


def _profile_context_path(profile: BubbleProfile) -> Path | None:
    if profile.app_json_path:
        path = Path(profile.app_json_path).expanduser()
        if path.exists() and path.name.endswith("-context.json"):
            return path
    candidate = default_context_path(profile.name, profile.app_id)
    return candidate if candidate.exists() else None


def resolve_transfer_profiles(source_profile: str, target_profile: str) -> ResolvedTransferProfiles:
    if not source_profile:
        raise ValueError("source_profile is required.")
    if not target_profile:
        raise ValueError("target_profile is required.")
    if source_profile == target_profile:
        raise ValueError("source_profile and target_profile must be different for cross-project transfer.")

    settings = load_settings()
    source = resolve_profile(settings, source_profile)
    target = resolve_profile(settings, target_profile)
    if source is None:
        raise ValueError(f"source_profile not configured: {source_profile}")
    if target is None:
        raise ValueError(f"target_profile not configured: {target_profile}")

    target_session = load_session(target.name)
    return ResolvedTransferProfiles(
        source=source,
        target=target,
        source_context_path=_profile_context_path(source),
        target_context_path=_profile_context_path(target),
        target_has_session=target_session is not None and target_session.app_id == target.app_id,
    )
```

- [ ] **Step 3: Run profile tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_profiles.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 4: Commit Task 2**

Run:

```bash
git add src/bubble_mcp/transfer/profiles.py tests/unit/test_transfer_profiles.py
git commit -m "feat: resolve transfer source and target profiles"
```

### Task 3: Source Inventory And Dependency Extraction

**Files:**
- Create: `src/bubble_mcp/transfer/inventory.py`
- Create: `src/bubble_mcp/transfer/dependencies.py`
- Test: `tests/unit/test_transfer_inventory.py`

- [ ] **Step 1: Write inventory tests**

Add `tests/unit/test_transfer_inventory.py`:

```python
from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.inventory import inventory_source_object


def _context() -> BubbleProjectContext:
    return BubbleProjectContext(
        app_id="source-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="page:index",
                label="index",
                type="page",
                metadata={"bubble_id": "bPage", "path": ["%p3", "bPage"]},
            ),
            BubbleContextNode(
                id="element:bHero",
                label="gp_Hero",
                type="element",
                metadata={
                    "bubble_id": "bHero",
                    "path": ["%p3", "bPage", "%el", "bHero"],
                    "style": "Primary Card",
                    "image_url": "https://example.com/hero.png",
                    "data_type": "User",
                },
            ),
            BubbleContextNode(
                id="element:bButton",
                label="bt_CTA",
                type="element",
                metadata={
                    "bubble_id": "bButton",
                    "path": ["%p3", "bPage", "%el", "bHero", "%el", "bButton"],
                    "style": "Primary Button",
                },
            ),
        ],
        edges=[
            BubbleContextEdge(source="page:index", target="element:bHero", type="contains"),
            BubbleContextEdge(source="element:bHero", target="element:bButton", type="contains"),
        ],
    )


def test_inventory_source_page_collects_subtree_and_dependencies() -> None:
    inventory = inventory_source_object(
        context=_context(),
        profile="source",
        app_version="test",
        source_type="page",
        source_ref="index",
    )

    payload = inventory.to_dict()

    assert payload["source"]["bubble_id"] == "bPage"
    assert payload["counts"]["nodes"] == 3
    kinds = {item["kind"] for item in payload["dependencies"]}
    assert {"style", "asset", "data_type"} <= kinds


def test_inventory_source_element_requires_context_match() -> None:
    inventory = inventory_source_object(
        context=_context(),
        profile="source",
        app_version="test",
        source_type="element",
        source_ref="gp_Hero",
        source_context="index",
    )

    assert inventory.source.source_type == "element"
    assert inventory.source.context == "index"
    assert len(inventory.nodes) == 2
```

- [ ] **Step 2: Implement dependency extraction**

Create `src/bubble_mcp/transfer/dependencies.py`:

```python
from __future__ import annotations

from typing import Any

from bubble_mcp.transfer.models import TransferDependency


ASSET_KEYS = ("image_url", "source", "asset_url", "background_image", "bg_image")
STYLE_KEYS = ("style", "style_name", "button_style", "text_style")
DATA_KEYS = ("data_type", "type_of_content", "data_class")


def dependencies_from_node(node: dict[str, Any]) -> list[TransferDependency]:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    label = str(node.get("label") or node.get("id") or "")
    out: list[TransferDependency] = []

    for key in STYLE_KEYS:
        value = metadata.get(key)
        if value:
            out.append(TransferDependency(kind="style", key=str(value), label=str(value), metadata={"from": label}))

    for key in DATA_KEYS:
        value = metadata.get(key)
        if value:
            out.append(TransferDependency(kind="data_type", key=str(value), label=str(value), metadata={"from": label}))

    for key in ASSET_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            out.append(
                TransferDependency(
                    kind="asset",
                    key=value,
                    label=value.rsplit("/", 1)[-1] or value,
                    required=False,
                    metadata={"from": label, "field": key},
                )
            )

    plugin = metadata.get("plugin_id") or metadata.get("plugin")
    if plugin:
        out.append(
            TransferDependency(
                kind="plugin",
                key=str(plugin),
                label=str(plugin),
                required=True,
                metadata={"from": label},
            )
        )

    return out


def dedupe_dependencies(items: list[TransferDependency]) -> list[TransferDependency]:
    seen: set[tuple[str, str]] = set()
    out: list[TransferDependency] = []
    for item in items:
        marker = (item.kind, item.key)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out
```

- [ ] **Step 3: Implement source inventory**

Create `src/bubble_mcp/transfer/inventory.py`:

```python
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.transfer.dependencies import dedupe_dependencies, dependencies_from_node
from bubble_mcp.transfer.models import TransferInventory, TransferObjectRef


def _node_to_dict(node: Any) -> dict[str, Any]:
    return {
        "id": node.id,
        "label": node.label,
        "type": node.type,
        "metadata": dict(node.metadata),
    }


def _matches_source(node: Any, source_type: str, source_ref: str, source_context: str | None) -> bool:
    ref = source_ref.strip().lower()
    if node.type != source_type:
        return False
    if source_context and str(node.metadata.get("context") or "").strip().lower() != source_context.strip().lower():
        if source_type == "element":
            path_text = ".".join(str(part) for part in node.metadata.get("path", []))
            if source_context.strip().lower() not in path_text.lower():
                return False
    return ref in {node.id.lower(), node.label.lower(), str(node.metadata.get("bubble_id") or "").lower()}


def _children_by_source(context: BubbleProjectContext) -> dict[str, list[str]]:
    children: dict[str, list[str]] = defaultdict(list)
    for edge in context.edges:
        if edge.type in {"contains", "child", "parent_child"}:
            children[edge.source].append(edge.target)
    return children


def _subtree(context: BubbleProjectContext, root_id: str) -> list[dict[str, Any]]:
    nodes = {node.id: node for node in context.nodes}
    children = _children_by_source(context)
    ordered: list[dict[str, Any]] = []
    queue: deque[str] = deque([root_id])
    seen: set[str] = set()
    while queue:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = nodes.get(node_id)
        if node is None:
            continue
        ordered.append(_node_to_dict(node))
        queue.extend(children.get(node_id, []))
    return ordered


def inventory_source_object(
    *,
    context: BubbleProjectContext,
    profile: str,
    app_version: str,
    source_type: str,
    source_ref: str,
    source_context: str | None = None,
) -> TransferInventory:
    root = next(
        (
            node
            for node in context.nodes
            if _matches_source(node, source_type=source_type, source_ref=source_ref, source_context=source_context)
        ),
        None,
    )
    if root is None:
        raise ValueError(f"Source {source_type} not found: {source_ref}")

    nodes = _subtree(context, root.id)
    dependencies = dedupe_dependencies(
        [dependency for node in nodes for dependency in dependencies_from_node(node)]
    )
    unsupported = [dependency for dependency in dependencies if dependency.kind in {"plugin", "api_connector"}]
    warnings = [
        f"{dependency.kind} dependency requires target-side setup: {dependency.label}"
        for dependency in unsupported
    ]

    return TransferInventory(
        source=TransferObjectRef(
            profile=profile,
            app_id=context.app_id,
            app_version=app_version,
            source_type=source_type,  # type: ignore[arg-type]
            ref=source_ref,
            context=source_context,
            bubble_id=str(root.metadata.get("bubble_id") or root.id),
            path=[str(part) for part in root.metadata.get("path", [])],
        ),
        root=_node_to_dict(root),
        nodes=nodes,
        dependencies=dependencies,
        warnings=warnings,
        unsupported=unsupported,
    )
```

- [ ] **Step 4: Run inventory tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_inventory.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add src/bubble_mcp/transfer/inventory.py src/bubble_mcp/transfer/dependencies.py tests/unit/test_transfer_inventory.py
git commit -m "feat: inventory Bubble transfer source objects"
```

### Task 4: Target Mapping And Conflict Policies

**Files:**
- Create: `src/bubble_mcp/transfer/mapping.py`
- Test: `tests/unit/test_transfer_mapping.py`

- [ ] **Step 1: Write mapping tests**

Add `tests/unit/test_transfer_mapping.py`:

```python
from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.mapping import build_dependency_decisions
from bubble_mcp.transfer.models import TransferDependency


def test_mapping_reuses_existing_style_by_label() -> None:
    target = BubbleProjectContext(
        app_id="target-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="style:primary_button",
                label="Primary Button",
                type="style",
                metadata={"bubble_id": "stTarget"},
            )
        ],
        edges=[],
    )
    dependency = TransferDependency(kind="style", key="Primary Button", label="Primary Button", source_id="stSource")

    decisions = build_dependency_decisions([dependency], target, dependency_policy="map_or_create")

    assert decisions[0].action == "map_existing"
    assert decisions[0].target_id == "stTarget"


def test_mapping_blocks_secret_api_connector_dependency() -> None:
    target = BubbleProjectContext(app_id="target-app", source="test", nodes=[], edges=[])
    dependency = TransferDependency(kind="api_connector", key="stripe", label="Stripe", secret=True)

    decisions = build_dependency_decisions([dependency], target, dependency_policy="map_or_create")

    assert decisions[0].action == "block"
    assert "secret" in decisions[0].reason.lower()
```

- [ ] **Step 2: Implement mapping**

Create `src/bubble_mcp/transfer/mapping.py`:

```python
from __future__ import annotations

from typing import Literal

from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.transfer.models import TransferDependency, TransferMappingDecision


DependencyPolicy = Literal["map_only", "map_or_create", "skip_optional"]


def _target_lookup(context: BubbleProjectContext) -> dict[tuple[str, str], tuple[str, str]]:
    lookup: dict[tuple[str, str], tuple[str, str]] = {}
    for node in context.nodes:
        key = (node.type, node.label.strip().lower())
        target_id = str(node.metadata.get("bubble_id") or node.id)
        lookup[key] = (target_id, node.label)
    return lookup


def build_dependency_decisions(
    dependencies: list[TransferDependency],
    target_context: BubbleProjectContext,
    *,
    dependency_policy: DependencyPolicy = "map_or_create",
) -> list[TransferMappingDecision]:
    lookup = _target_lookup(target_context)
    decisions: list[TransferMappingDecision] = []

    for dependency in dependencies:
        if dependency.secret:
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="block",
                    reason="Secret-bearing dependencies must be configured manually in the target app.",
                )
            )
            continue

        existing = lookup.get((dependency.kind, dependency.label.strip().lower()))
        if existing is not None:
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="map_existing",
                    target_id=existing[0],
                    target_label=existing[1],
                    reason="Matched target object by kind and label.",
                )
            )
            continue

        if dependency.kind in {"plugin", "api_connector"}:
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="block" if dependency.required else "skip",
                    reason=f"{dependency.kind} dependency requires manual target setup.",
                )
            )
            continue

        if dependency_policy == "map_only":
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="block" if dependency.required else "skip",
                    reason="Dependency was not found in target and dependency_policy=map_only.",
                )
            )
            continue

        if dependency_policy == "skip_optional" and not dependency.required:
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="skip",
                    reason="Optional dependency skipped by policy.",
                )
            )
            continue

        decisions.append(
            TransferMappingDecision(
                dependency=dependency,
                action="create_copy",
                reason="Dependency not found in target and can be copied or recreated.",
            )
        )

    return decisions
```

- [ ] **Step 3: Run mapping tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_mapping.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 4: Commit Task 4**

Run:

```bash
git add src/bubble_mcp/transfer/mapping.py tests/unit/test_transfer_mapping.py
git commit -m "feat: map Bubble transfer dependencies"
```

### Task 5A: Collection And API Connector Bundles

**Files:**
- Create: `src/bubble_mcp/transfer/collections.py`
- Create: `src/bubble_mcp/transfer/api_connector.py`
- Modify: `src/bubble_mcp/transfer/dependencies.py`
- Modify: `src/bubble_mcp/transfer/models.py`
- Test: `tests/unit/test_transfer_collections.py`
- Test: `tests/unit/test_transfer_api_connector.py`

- [ ] **Step 1: Write collection bundle tests**

Add `tests/unit/test_transfer_collections.py` covering:

- exact Bubble field keys are preserved, including suffixes like `_text`, `_number`, and relational target suffixes;
- data type dependencies include fields, privacy rules, and related option sets;
- `collection_policy=map_existing` blocks when the target does not contain a required data type or field;
- `collection_policy=create_missing` produces deterministic schema write payload descriptors;
- `data_records_policy=skip` is the default and emits no record migration payloads;
- any non-skip data record policy is marked high risk and requires explicit preview evidence.

- [ ] **Step 2: Write API Connector bundle tests**

Add `tests/unit/test_transfer_api_connector.py` covering:

- API Connector APIs and calls are extracted as structure-only bundles;
- method, URL, parameter/header/body shape, and safe response schema are preserved;
- private headers, bearer tokens, cookies, OAuth secrets, API keys, and sample secret values are redacted;
- `api_connector_policy=map_existing` blocks when the target API/call is missing;
- `api_connector_policy=structure_only` produces target setup checklist items for private values;
- dependency inventory can point workflows/elements to the API Connector call they require.

- [ ] **Step 3: Implement collection extraction**

Create `src/bubble_mcp/transfer/collections.py` with focused helpers:

```python
def extract_collection_bundle(source_context: BubbleProjectContext, data_type: str) -> CollectionBundle:
    ...


def plan_collection_bundle(bundle: CollectionBundle, target_context: BubbleProjectContext, policy: str) -> CollectionPlan:
    ...
```

Implementation requirements:

- rely on parsed `.bubble`/module context and unified context metadata first;
- preserve exact field keys used by Bubble writes;
- include privacy roles/rules when available;
- include option sets referenced by fields or expressions;
- avoid data record movement unless future data-record migration support is explicitly implemented.

- [ ] **Step 4: Implement API Connector extraction**

Create `src/bubble_mcp/transfer/api_connector.py` with focused helpers:

```python
def extract_api_connector_bundle(source_context: BubbleProjectContext, api_ref: str) -> ApiConnectorBundle:
    ...


def redact_api_connector_bundle(bundle: ApiConnectorBundle) -> ApiConnectorBundle:
    ...


def plan_api_connector_bundle(bundle: ApiConnectorBundle, target_context: BubbleProjectContext, policy: str) -> ApiConnectorPlan:
    ...
```

Implementation requirements:

- preserve API/call structure;
- redact secret-bearing values before local artifact storage;
- produce a target setup checklist for every redacted value;
- block execution when a copied workflow requires an API call that is neither mapped nor planned for structure-only creation.

- [ ] **Step 5: Wire bundles into dependency extraction**

Update `src/bubble_mcp/transfer/dependencies.py` so inventory can emit:

- `data_type`;
- `data_field`;
- `privacy_rule`;
- `option_set`;
- `api_connector`;
- `api_connector_call`.

Each dependency should include enough metadata for target mapping without embedding secrets.

- [ ] **Step 6: Run focused checks**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_collections.py tests/unit/test_transfer_api_connector.py tests/unit/test_transfer_inventory.py tests/unit/test_transfer_mapping.py -q
PYTHONPATH=src python -m ruff check src/bubble_mcp/transfer tests/unit/test_transfer_collections.py tests/unit/test_transfer_api_connector.py
```

Expected:

```text
pytest passes
All checks passed!
```

- [ ] **Step 7: Commit Task 5A**

Run:

```bash
git add src/bubble_mcp/transfer/collections.py src/bubble_mcp/transfer/api_connector.py src/bubble_mcp/transfer/dependencies.py src/bubble_mcp/transfer/models.py tests/unit/test_transfer_collections.py tests/unit/test_transfer_api_connector.py tests/unit/test_transfer_inventory.py tests/unit/test_transfer_mapping.py
git commit -m "feat: add Bubble transfer collection and API connector bundles"
```

### Task 5: Transfer Planning And Compilation

**Files:**
- Create: `src/bubble_mcp/transfer/compiler.py`
- Create: `src/bubble_mcp/transfer/planner.py`
- Test: `tests/unit/test_transfer_compiler.py`

- [ ] **Step 1: Write compiler tests**

Add `tests/unit/test_transfer_compiler.py`:

```python
from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.compiler import compile_inventory_to_target_payloads
from bubble_mcp.transfer.models import TransferObjectRef, TransferInventory


def test_compile_element_inventory_targets_target_app_and_parent_path() -> None:
    inventory = TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="element",
            ref="gp_Hero",
            context="index",
            bubble_id="bHero",
            path=["%p3", "bSourcePage", "%el", "bHero"],
        ),
        root={
            "id": "element:bHero",
            "label": "gp_Hero",
            "type": "element",
            "metadata": {"bubble_id": "bHero", "path": ["%p3", "bSourcePage", "%el", "bHero"]},
        },
        nodes=[
            {
                "id": "element:bHero",
                "label": "gp_Hero",
                "type": "element",
                "metadata": {"bubble_id": "bHero", "properties": {"%x": "Group", "%p": {"%nm": "gp_Hero"}}},
            }
        ],
        dependencies=[],
    )
    target_context = BubbleProjectContext(
        app_id="target-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="page:index",
                label="index",
                type="page",
                metadata={"bubble_id": "bTargetPage", "path": ["%p3", "bTargetPage"]},
            )
        ],
        edges=[],
    )

    payloads = compile_inventory_to_target_payloads(
        inventory=inventory,
        target_context=target_context,
        target_app_id="target-app",
        target_app_version="test",
        target_context_ref="index",
        target_parent_ref="root",
        target_name="gp_Hero_Copy",
    )

    assert len(payloads) == 1
    assert payloads[0]["appname"] == "target-app"
    assert payloads[0]["app_version"] == "test"
    change = payloads[0]["changes"][0]
    assert change["intent"]["name"] == "CreateElement"
    assert change["path_array"][:2] == ["%p3", "bTargetPage"]
    assert change["body"]["%p"]["%nm"] == "gp_Hero_Copy"
```

- [ ] **Step 2: Implement compiler v1**

Create `src/bubble_mcp/transfer/compiler.py`:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any

from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.transfer.models import TransferInventory


def _find_target_path(context: BubbleProjectContext, context_ref: str, parent_ref: str | None) -> list[str]:
    normalized_context = context_ref.strip().lower()
    root = next(
        (
            node
            for node in context.nodes
            if node.type in {"page", "reusable"}
            and normalized_context in {node.id.lower(), node.label.lower(), str(node.metadata.get("bubble_id") or "").lower()}
        ),
        None,
    )
    if root is None:
        raise ValueError(f"Target context not found: {context_ref}")
    root_path = [str(part) for part in root.metadata.get("path", [])] or ["%p3", str(root.metadata.get("bubble_id") or root.id)]
    if not parent_ref or parent_ref == "root":
        return root_path
    normalized_parent = parent_ref.strip().lower()
    parent = next(
        (
            node
            for node in context.nodes
            if node.type == "element"
            and normalized_parent in {node.id.lower(), node.label.lower(), str(node.metadata.get("bubble_id") or "").lower()}
        ),
        None,
    )
    if parent is None:
        raise ValueError(f"Target parent not found: {parent_ref}")
    return [str(part) for part in parent.metadata.get("path", [])]


def _body_from_inventory_node(node: dict[str, Any], target_name: str | None) -> dict[str, Any]:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    raw = metadata.get("properties")
    body = deepcopy(raw) if isinstance(raw, dict) else {"%x": "Group", "%p": {}}
    props = body.setdefault("%p", {})
    if isinstance(props, dict):
        props["%nm"] = target_name or str(node.get("label") or "gp_transferred")
    return body


def compile_inventory_to_target_payloads(
    *,
    inventory: TransferInventory,
    target_context: BubbleProjectContext,
    target_app_id: str,
    target_app_version: str,
    target_context_ref: str,
    target_parent_ref: str | None,
    target_name: str | None,
) -> list[dict[str, Any]]:
    if not inventory.nodes:
        raise ValueError("Cannot compile transfer with an empty inventory.")
    target_path = _find_target_path(target_context, target_context_ref, target_parent_ref)
    root_node = inventory.nodes[0]
    body = _body_from_inventory_node(root_node, target_name)
    slot_id = str(body.get("id") or inventory.source.bubble_id or "bTransfer")
    body["id"] = slot_id
    return [
        {
            "v": 1,
            "appname": target_app_id,
            "app_version": target_app_version,
            "changes": [
                {
                    "body": body,
                    "path_array": [*target_path, "%el", slot_id],
                    "intent": {"name": "CreateElement", "source_appname": ""},
                    "version_control_api_version": 4,
                    "changelog_data": [],
                }
            ],
        }
    ]
```

- [ ] **Step 3: Implement planner orchestration**

Create `src/bubble_mcp/transfer/planner.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from bubble_mcp.context.freshness import load_context_with_overlay
from bubble_mcp.transfer.compiler import compile_inventory_to_target_payloads
from bubble_mcp.transfer.inventory import inventory_source_object
from bubble_mcp.transfer.mapping import build_dependency_decisions
from bubble_mcp.transfer.models import TransferPlan
from bubble_mcp.transfer.profiles import resolve_transfer_profiles
from bubble_mcp.transfer.store import save_transfer_plan


def _transfer_id(source_ref: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = "".join(char.lower() if char.isalnum() else "_" for char in source_ref).strip("_") or "object"
    return f"transfer_{stamp}_{slug}"


def create_transfer_plan(
    *,
    source_profile: str,
    target_profile: str,
    source_type: str,
    source_ref: str,
    source_context: str | None = None,
    target_context: str | None = None,
    target_parent: str | None = "root",
    target_name: str | None = None,
    conflict_policy: str = "fail",
    asset_policy: str = "reference_url",
    dependency_policy: str = "map_or_create",
    collection_policy: str = "map_existing",
    api_connector_policy: str = "structure_only",
    data_records_policy: str = "skip",
) -> dict:
    resolved = resolve_transfer_profiles(source_profile, target_profile)
    if resolved.source_context_path is None:
        raise ValueError(f"Source context is missing for profile '{source_profile}'. Run bubble-mcp context detect.")
    if resolved.target_context_path is None:
        raise ValueError(f"Target context is missing for profile '{target_profile}'. Run bubble-mcp context detect.")

    source = load_context_with_overlay(
        resolved.source_context_path,
        profile=source_profile,
        app_id=resolved.source.app_id,
    )
    target = load_context_with_overlay(
        resolved.target_context_path,
        profile=target_profile,
        app_id=resolved.target.app_id,
    )
    inventory = inventory_source_object(
        context=source,
        profile=source_profile,
        app_version=resolved.source.app_version or "test",
        source_type=source_type,
        source_ref=source_ref,
        source_context=source_context,
    )
    decisions = build_dependency_decisions(
        inventory.dependencies,
        target,
        dependency_policy=dependency_policy,  # type: ignore[arg-type]
    )
    blocked = [decision.reason for decision in decisions if decision.action == "block"]
    payloads = [] if blocked else compile_inventory_to_target_payloads(
        inventory=inventory,
        target_context=target,
        target_app_id=resolved.target.app_id,
        target_app_version=resolved.target.app_version or "test",
        target_context_ref=target_context or "index",
        target_parent_ref=target_parent,
        target_name=target_name,
    )
    plan = TransferPlan(
        transfer_id=_transfer_id(source_ref),
        source=inventory.source,
        target_profile=target_profile,
        target_app_id=resolved.target.app_id,
        target_app_version=resolved.target.app_version or "test",
        target_context=target_context,
        target_parent=target_parent,
        target_name=target_name,
        conflict_policy=conflict_policy,  # type: ignore[arg-type]
        asset_policy=asset_policy,  # type: ignore[arg-type]
        collection_policy=collection_policy,  # type: ignore[arg-type]
        api_connector_policy=api_connector_policy,  # type: ignore[arg-type]
        data_records_policy=data_records_policy,  # type: ignore[arg-type]
        dependency_decisions=decisions,
        write_payloads=payloads,
        blocked_reasons=blocked,
    )
    path = save_transfer_plan(plan)
    payload = plan.to_dict()
    payload["ok"] = not blocked
    payload["plan_path"] = str(path)
    payload["inventory"] = inventory.to_dict()
    payload["next_action"] = "Run bubble_transfer_preview before execution."
    return payload
```

- [ ] **Step 4: Run compiler tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_compiler.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit Task 5**

Run:

```bash
git add src/bubble_mcp/transfer/compiler.py src/bubble_mcp/transfer/planner.py tests/unit/test_transfer_compiler.py
git commit -m "feat: compile transfer plans for target Bubble apps"
```

### Task 6: Preview And Execute Transfer Plans

**Files:**
- Create: `src/bubble_mcp/transfer/executor.py`
- Test: `tests/unit/test_transfer_executor.py`

- [ ] **Step 1: Write executor tests**

Add `tests/unit/test_transfer_executor.py`:

```python
import pytest

from bubble_mcp.sessions.store import BubbleSessionData, save_session
from bubble_mcp.transfer.executor import execute_transfer_plan, preview_transfer_plan
from bubble_mcp.transfer.models import TransferObjectRef, TransferPlan
from bubble_mcp.transfer.store import save_transfer_plan


def _plan() -> TransferPlan:
    source = TransferObjectRef(
        profile="source",
        app_id="source-app",
        app_version="test",
        source_type="element",
        ref="gp_Hero",
    )
    return TransferPlan(
        transfer_id="transfer_test",
        source=source,
        target_profile="target",
        target_app_id="target-app",
        target_app_version="test",
        target_context="index",
        target_parent="root",
        target_name="gp_Hero_Copy",
        conflict_policy="fail",
        asset_policy="reference_url",
        collection_policy="map_existing",
        api_connector_policy="structure_only",
        data_records_policy="skip",
        dependency_decisions=[],
        write_payloads=[{"v": 1, "appname": "target-app", "app_version": "test", "changes": []}],
    )


def test_preview_transfer_plan_returns_payload_count(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan())

    result = preview_transfer_plan("transfer_test")

    assert result["ok"] is True
    assert result["payload_count"] == 1
    assert result["executed"] is False


def test_execute_transfer_requires_execute_and_confirm(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan())

    with pytest.raises(ValueError, match="execute=true"):
        execute_transfer_plan("transfer_test", execute=False, confirm=True)

    with pytest.raises(ValueError, match="confirm=true"):
        execute_transfer_plan("transfer_test", execute=True, confirm=False)


def test_execute_transfer_uses_target_profile_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan())
    save_session(
        BubbleSessionData(
            profile="target",
            app_id="target-app",
            app_version="test",
            cookies=[],
            headers={"user-agent": "test"},
            captured_at="2026-07-08T00:00:00+00:00",
            source="test",
            url="https://bubble.io/page?id=target-app",
            method="POST",
        )
    )
    calls = []

    class FakeClient:
        def write(self, payload, session, dry_run=False, calculate_derived=False):
            calls.append({"payload": payload, "session": session, "dry_run": dry_run})
            return {"ok": True, "request": {"payload": payload}, "response": {"last_change": "1"}}

    result = execute_transfer_plan("transfer_test", execute=True, confirm=True, client=FakeClient())

    assert result["ok"] is True
    assert result["executed"] is True
    assert calls[0]["session"].profile == "target"
    assert calls[0]["dry_run"] is False
```

- [ ] **Step 2: Implement executor**

Create `src/bubble_mcp/transfer/executor.py`:

```python
from __future__ import annotations

from typing import Any

from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.sessions.store import load_session
from bubble_mcp.transfer.store import load_transfer_plan


def preview_transfer_plan(transfer_id: str) -> dict[str, Any]:
    plan = load_transfer_plan(transfer_id)
    payloads = plan.get("write_payloads")
    if not isinstance(payloads, list):
        raise ValueError("Transfer plan is missing write_payloads.")
    return {
        "ok": not bool(plan.get("blocked_reasons")),
        "transfer_id": transfer_id,
        "executed": False,
        "payload_count": len(payloads),
        "blocked_reasons": plan.get("blocked_reasons", []),
        "dependency_decisions": plan.get("dependency_decisions", []),
        "payloads": payloads,
    }


def execute_transfer_plan(
    transfer_id: str,
    *,
    execute: bool,
    confirm: bool,
    client: BubbleEditorClient | None = None,
    max_steps: int | None = None,
) -> dict[str, Any]:
    if not execute:
        raise ValueError("bubble_transfer_execute requires execute=true.")
    if not confirm:
        raise ValueError("bubble_transfer_execute requires confirm=true.")
    plan = load_transfer_plan(transfer_id)
    blocked = plan.get("blocked_reasons")
    if isinstance(blocked, list) and blocked:
        return {"ok": False, "executed": False, "transfer_id": transfer_id, "blocked_reasons": blocked}

    target_profile = str(plan.get("target_profile") or "")
    session = load_session(target_profile)
    if session is None:
        raise ValueError(f"No Bubble session stored for target profile '{target_profile}'.")
    payloads = plan.get("write_payloads")
    if not isinstance(payloads, list):
        raise ValueError("Transfer plan is missing write_payloads.")
    limited = payloads[:max_steps] if max_steps else payloads
    editor_client = client or BubbleEditorClient()
    results = []
    for payload in limited:
        if not isinstance(payload, dict):
            results.append({"ok": False, "error": "payload_not_object"})
            break
        result = editor_client.write(payload, session, dry_run=False)
        if result.get("ok"):
            record_mutation_overlay(
                profile=target_profile,
                app_id=str(payload.get("appname") or session.app_id),
                payload=result.get("request", {}).get("payload") or payload,
                source="bubble_transfer_execute",
                response=result.get("response"),
            )
        results.append({"ok": bool(result.get("ok")), "result": result})
        if not result.get("ok"):
            break
    return {
        "ok": all(item.get("ok") for item in results),
        "executed": True,
        "transfer_id": transfer_id,
        "target_profile": target_profile,
        "result_count": len(results),
        "results": results,
    }
```

- [ ] **Step 3: Run executor tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_executor.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 4: Commit Task 6**

Run:

```bash
git add src/bubble_mcp/transfer/executor.py tests/unit/test_transfer_executor.py
git commit -m "feat: preview and execute Bubble transfers"
```

### Task 7: MCP Tool Schemas And Dispatch

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/runtime_coverage.py`
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Write MCP schema tests**

Append to `tests/unit/test_mcp_server.py`:

```python
def test_transfer_tools_are_exposed_with_specific_schemas() -> None:
    response = handle_request({"jsonrpc": "2.0", "id": 801, "method": "tools/list"})

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    for name in [
        "bubble_transfer_inventory",
        "bubble_transfer_plan",
        "bubble_transfer_preview",
        "bubble_transfer_execute",
        "bubble_transfer_status",
    ]:
        assert name in tools
        assert tools[name]["inputSchema"]["type"] == "object"

    assert tools["bubble_transfer_inventory"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_transfer_plan"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_transfer_preview"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_transfer_status"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_transfer_execute"]["annotations"]["readOnlyHint"] is False
    assert tools["bubble_transfer_execute"]["annotations"]["destructiveHint"] is True
    assert tools["bubble_transfer_inventory"]["inputSchema"]["required"] == [
        "source_profile",
        "source_type",
        "source_ref",
    ]
    assert tools["bubble_transfer_plan"]["inputSchema"]["required"] == [
        "source_profile",
        "target_profile",
        "source_type",
        "source_ref",
    ]
    assert tools["bubble_transfer_execute"]["inputSchema"]["required"] == ["transfer_id", "execute", "confirm"]
```

- [ ] **Step 2: Add schema family**

In `src/bubble_mcp/server/schema_families.py`, add transfer field definitions to `FIELD_LIBRARY`:

```python
    "source_profile": _prop("string", "Local Bubble MCP profile used as the transfer source.", examples=["source-app"]),
    "target_profile": _prop("string", "Local Bubble MCP profile used as the transfer target.", examples=["target-app"]),
    "source_type": _prop("string", "Source object type to transfer.", enum=["page", "reusable", "element"], examples=["page", "reusable", "element"]),
    "source_ref": _prop("string", "Source object name, Bubble id, or context id.", examples=["index", "Header", "gp_Hero"]),
    "source_context": _prop("string", "Optional page or reusable context used to disambiguate element refs.", examples=["index"]),
    "target_context": _prop("string", "Target page or reusable context where the transferred object should be placed.", examples=["index"]),
    "target_parent": _prop("string", "Target parent element id/name, or root for page/reusable root.", default="root", examples=["root", "gp_Content"]),
    "target_name": _prop("string", "Optional target object name override.", examples=["Header Copy"]),
    "transfer_id": _prop("string", "Local transfer plan id.", examples=["transfer_20260708_120000_header"]),
    "conflict_policy": _prop("string", "How to handle target name conflicts.", enum=["fail", "rename", "replace", "reuse_existing"], default="fail"),
    "asset_policy": _prop("string", "How to handle source asset URLs.", enum=["reference_url", "stage_and_upload", "skip"], default="reference_url"),
    "dependency_policy": _prop("string", "How to handle dependencies not found in the target app.", enum=["map_only", "map_or_create", "skip_optional"], default="map_or_create"),
    "include_collections": _prop("boolean", "Include Bubble database collection schema dependencies: data types, fields, privacy rules, and option sets.", default=True),
    "collection_policy": _prop("string", "How to transfer Bubble database collection schema.", enum=["skip", "map_existing", "create_missing", "replace_schema"], default="map_existing"),
    "include_api_connector": _prop("boolean", "Include API Connector API/call structure dependencies without copying secrets.", default=True),
    "api_connector_policy": _prop("string", "How to transfer API Connector APIs and calls.", enum=["skip", "map_existing", "structure_only"], default="structure_only"),
    "data_records_policy": _prop("string", "How to handle live database records. Default skips record migration.", enum=["skip", "export_manifest_only", "data_api_import_preview"], default="skip"),
```

Add:

```python
def transfer_tools() -> list[ToolSchema]:
    return [
        {
            "name": "bubble_transfer_inventory",
            "description": "Inspect a source Bubble page, reusable, or element subtree for project-to-project transfer. Read-only.",
            "inputSchema": object_schema(
                {
                    "source_profile": field("source_profile"),
                    "source_type": field("source_type"),
                    "source_ref": field("source_ref"),
                    "source_context": field("source_context"),
                    "include_dependencies": _prop("boolean", "Include dependency extraction in the inventory.", default=True),
                    "include_raw": field("include_raw"),
                },
                required=["source_profile", "source_type", "source_ref"],
            ),
        },
        {
            "name": "bubble_transfer_plan",
            "description": "Create a local preview-first transfer plan from one Bubble project profile to another.",
            "inputSchema": object_schema(
                {
                    "source_profile": field("source_profile"),
                    "target_profile": field("target_profile"),
                    "source_type": field("source_type"),
                    "source_ref": field("source_ref"),
                    "source_context": field("source_context"),
                    "target_context": field("target_context"),
                    "target_parent": field("target_parent"),
                    "target_name": field("target_name"),
                    "conflict_policy": field("conflict_policy"),
                    "asset_policy": field("asset_policy"),
                    "dependency_policy": field("dependency_policy"),
                    "include_collections": field("include_collections"),
                    "collection_policy": field("collection_policy"),
                    "include_api_connector": field("include_api_connector"),
                    "api_connector_policy": field("api_connector_policy"),
                    "data_records_policy": field("data_records_policy"),
                },
                required=["source_profile", "target_profile", "source_type", "source_ref"],
            ),
        },
        {
            "name": "bubble_transfer_preview",
            "description": "Preview a local Bubble cross-project transfer plan before execution.",
            "inputSchema": object_schema(
                {
                    "transfer_id": field("transfer_id"),
                    "include_payloads": _prop("boolean", "Include redacted write payloads in the preview.", default=False),
                },
                required=["transfer_id"],
            ),
        },
        {
            "name": "bubble_transfer_execute",
            "description": "Execute a reviewed Bubble cross-project transfer plan against the target profile. Requires execute=true and confirm=true.",
            "inputSchema": object_schema(
                {
                    "transfer_id": field("transfer_id"),
                    "execute": field("execute"),
                    "confirm": field("confirm"),
                    "max_steps": _prop("integer", "Optional maximum number of ordered payloads to execute.", minimum=1),
                },
                required=["transfer_id", "execute", "confirm"],
            ),
        },
        {
            "name": "bubble_transfer_status",
            "description": "List local Bubble transfer plans and evidence records. Read-only.",
            "inputSchema": object_schema(
                {
                    "transfer_id": field("transfer_id"),
                    "profile": field("profile"),
                }
            ),
        },
    ]
```

Append `*transfer_tools()` to `native_tool_schemas()`.

- [ ] **Step 3: Add MCP dispatch**

In `src/bubble_mcp/server/tools.py`, import:

```python
from bubble_mcp.transfer.executor import execute_transfer_plan, preview_transfer_plan
from bubble_mcp.transfer.planner import create_transfer_plan
from bubble_mcp.transfer.store import load_transfer_plan
```

Add handlers in `call_tool`:

```python
    if name == "bubble_transfer_plan":
        args = arguments or {}
        return create_transfer_plan(
            source_profile=_required_string_arg(args, "source_profile", name),
            target_profile=_required_string_arg(args, "target_profile", name),
            source_type=_required_string_arg(args, "source_type", name),
            source_ref=_required_string_arg(args, "source_ref", name),
            source_context=str(args.get("source_context") or "") or None,
            target_context=str(args.get("target_context") or "") or None,
            target_parent=str(args.get("target_parent") or "root"),
            target_name=str(args.get("target_name") or "") or None,
            conflict_policy=str(args.get("conflict_policy") or "fail"),
            asset_policy=str(args.get("asset_policy") or "reference_url"),
            dependency_policy=str(args.get("dependency_policy") or "map_or_create"),
            collection_policy=str(args.get("collection_policy") or "map_existing"),
            api_connector_policy=str(args.get("api_connector_policy") or "structure_only"),
            data_records_policy=str(args.get("data_records_policy") or "skip"),
        )
    if name == "bubble_transfer_preview":
        args = arguments or {}
        return preview_transfer_plan(_required_string_arg(args, "transfer_id", name))
    if name == "bubble_transfer_execute":
        args = arguments or {}
        return execute_transfer_plan(
            _required_string_arg(args, "transfer_id", name),
            execute=bool(args.get("execute")),
            confirm=bool(args.get("confirm")),
            max_steps=int(args["max_steps"]) if args.get("max_steps") else None,
        )
    if name == "bubble_transfer_status":
        args = arguments or {}
        transfer_id = str(args.get("transfer_id") or "").strip()
        if transfer_id:
            return {"ok": True, "transfer": load_transfer_plan(transfer_id)}
        return {"ok": True, "message": "Use transfer_id for detailed status in this implementation slice."}
```

Add `bubble_transfer_inventory` after Task 8 connects inventory loading from profile context.

- [ ] **Step 4: Add annotations**

In `src/bubble_mcp/server/agent_catalog.py`, update `tool_annotations`:

```python
    agent_read_only = {
        ...,
        "bubble_transfer_inventory",
        "bubble_transfer_plan",
        "bubble_transfer_preview",
        "bubble_transfer_status",
    }
    destructive = name.startswith(("delete_", "clear_", "regenerate_")) or name in {"bubble_branch_delete", "bubble_transfer_execute"}
```

- [ ] **Step 5: Run MCP schema tests**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_mcp_server.py::test_transfer_tools_are_exposed_with_specific_schemas -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit Task 7**

Run:

```bash
git add src/bubble_mcp/server/schema_families.py src/bubble_mcp/server/tools.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/runtime_coverage.py tests/unit/test_mcp_server.py
git commit -m "feat: expose Bubble transfer MCP tools"
```

### Task 8: Transfer Inventory Tool And CLI Commands

**Files:**
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/cli/main.py`
- Test: `tests/unit/test_cli_commands.py`
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Add transfer inventory runtime helper**

Create helper in `src/bubble_mcp/transfer/planner.py`:

```python
from bubble_mcp.core.config import load_settings, resolve_profile


def inspect_transfer_inventory(
    *,
    source_profile: str,
    source_type: str,
    source_ref: str,
    source_context: str | None = None,
) -> dict:
    settings = load_settings()
    profile = resolve_profile(settings, source_profile)
    if profile is None:
        raise ValueError(f"source_profile not configured: {source_profile}")
    context_path = _profile_context_path(profile)
    if context_path is None:
        raise ValueError(f"Source context is missing for profile '{source_profile}'. Run bubble-mcp context detect.")
    context = load_context_with_overlay(context_path, profile=profile.name, app_id=profile.app_id)
    inventory = inventory_source_object(
        context=context,
        profile=profile.name,
        app_version=profile.app_version or "test",
        source_type=source_type,
        source_ref=source_ref,
        source_context=source_context,
    )
    payload = inventory.to_dict()
    payload["ok"] = True
    return payload
```

- [ ] **Step 2: Dispatch inventory tool**

In `src/bubble_mcp/server/tools.py`, import `inspect_transfer_inventory` and add:

```python
    if name == "bubble_transfer_inventory":
        args = arguments or {}
        return inspect_transfer_inventory(
            source_profile=_required_string_arg(args, "source_profile", name),
            source_type=_required_string_arg(args, "source_type", name),
            source_ref=_required_string_arg(args, "source_ref", name),
            source_context=str(args.get("source_context") or "") or None,
        )
```

- [ ] **Step 3: Add CLI command functions**

In `src/bubble_mcp/cli/main.py`, import transfer functions:

```python
from bubble_mcp.transfer.executor import execute_transfer_plan, preview_transfer_plan
from bubble_mcp.transfer.planner import create_transfer_plan, inspect_transfer_inventory
```

Add command handlers:

```python
def command_transfer_inventory(args: argparse.Namespace) -> int:
    _print_json(
        inspect_transfer_inventory(
            source_profile=args.source_profile,
            source_type=args.source_type,
            source_ref=args.source_ref,
            source_context=args.source_context or None,
        )
    )
    return 0


def command_transfer_plan(args: argparse.Namespace) -> int:
    _print_json(
        create_transfer_plan(
            source_profile=args.source_profile,
            target_profile=args.target_profile,
            source_type=args.source_type,
            source_ref=args.source_ref,
            source_context=args.source_context or None,
            target_context=args.target_context or None,
            target_parent=args.target_parent,
            target_name=args.target_name or None,
            conflict_policy=args.conflict_policy,
            asset_policy=args.asset_policy,
            dependency_policy=args.dependency_policy,
            collection_policy=args.collection_policy,
            api_connector_policy=args.api_connector_policy,
            data_records_policy=args.data_records_policy,
        )
    )
    return 0


def command_transfer_preview(args: argparse.Namespace) -> int:
    _print_json(preview_transfer_plan(args.transfer_id))
    return 0


def command_transfer_execute(args: argparse.Namespace) -> int:
    _print_json(
        execute_transfer_plan(
            args.transfer_id,
            execute=bool(args.execute),
            confirm=bool(args.confirm),
            max_steps=args.max_steps,
        )
    )
    return 0
```

- [ ] **Step 4: Add argparse subcommands**

In `main()`, add after metrics or before extension commands:

```python
    transfer_parser = subparsers.add_parser("transfer", help="Plan and execute Bubble project-to-project transfers.")
    transfer_subparsers = transfer_parser.add_subparsers(dest="transfer_command", required=True)

    transfer_inventory_parser = transfer_subparsers.add_parser("inventory", help="Inspect a source object for transfer.")
    transfer_inventory_parser.add_argument("--source-profile", required=True)
    transfer_inventory_parser.add_argument("--source-type", choices=["page", "reusable", "element"], required=True)
    transfer_inventory_parser.add_argument("--source-ref", required=True)
    transfer_inventory_parser.add_argument("--source-context", default="")
    transfer_inventory_parser.set_defaults(func=command_transfer_inventory)

    transfer_plan_parser = transfer_subparsers.add_parser("plan", help="Create a local transfer plan.")
    transfer_plan_parser.add_argument("--source-profile", required=True)
    transfer_plan_parser.add_argument("--target-profile", required=True)
    transfer_plan_parser.add_argument("--source-type", choices=["page", "reusable", "element"], required=True)
    transfer_plan_parser.add_argument("--source-ref", required=True)
    transfer_plan_parser.add_argument("--source-context", default="")
    transfer_plan_parser.add_argument("--target-context", default="")
    transfer_plan_parser.add_argument("--target-parent", default="root")
    transfer_plan_parser.add_argument("--target-name", default="")
    transfer_plan_parser.add_argument("--conflict-policy", choices=["fail", "rename", "replace", "reuse_existing"], default="fail")
    transfer_plan_parser.add_argument("--asset-policy", choices=["reference_url", "stage_and_upload", "skip"], default="reference_url")
    transfer_plan_parser.add_argument("--dependency-policy", choices=["map_only", "map_or_create", "skip_optional"], default="map_or_create")
    transfer_plan_parser.add_argument("--collection-policy", choices=["skip", "map_existing", "create_missing", "replace_schema"], default="map_existing")
    transfer_plan_parser.add_argument("--api-connector-policy", choices=["skip", "map_existing", "structure_only"], default="structure_only")
    transfer_plan_parser.add_argument("--data-records-policy", choices=["skip", "export_manifest_only", "data_api_import_preview"], default="skip")
    transfer_plan_parser.set_defaults(func=command_transfer_plan)

    transfer_preview_parser = transfer_subparsers.add_parser("preview", help="Preview a transfer plan.")
    transfer_preview_parser.add_argument("--transfer-id", required=True)
    transfer_preview_parser.set_defaults(func=command_transfer_preview)

    transfer_execute_parser = transfer_subparsers.add_parser("execute", help="Execute a reviewed transfer plan.")
    transfer_execute_parser.add_argument("--transfer-id", required=True)
    transfer_execute_parser.add_argument("--execute", action="store_true")
    transfer_execute_parser.add_argument("--confirm", action="store_true")
    transfer_execute_parser.add_argument("--max-steps", type=int, default=None)
    transfer_execute_parser.set_defaults(func=command_transfer_execute)
```

- [ ] **Step 5: Run CLI smoke help**

Run:

```bash
PYTHONPATH=src python -m bubble_mcp.cli.main transfer --help
PYTHONPATH=src python -m bubble_mcp.cli.main transfer plan --help
```

Expected:

```text
usage: bubble-mcp transfer ...
usage: bubble-mcp transfer plan ...
```

- [ ] **Step 6: Commit Task 8**

Run:

```bash
git add src/bubble_mcp/transfer/planner.py src/bubble_mcp/server/tools.py src/bubble_mcp/cli/main.py tests/unit/test_cli_commands.py tests/unit/test_mcp_server.py
git commit -m "feat: add Bubble transfer CLI commands"
```

### Task 9: Documentation, Runbook Routing, And Quality Gates

**Files:**
- Modify: `src/bubble_mcp/server/agent_guide.py`
- Modify: `docs/mcp-clients.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/architecture.md`
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Add agent guide route**

In `src/bubble_mcp/server/agent_guide.py`, add a route named `cross_project_transfer`:

```python
{
    "id": "cross_project_transfer",
    "when": "The user asks to copy or transfer a Bubble page, reusable, element, asset, database collection schema, or API Connector call from one project/profile/app to another.",
    "tools": [
        "bubble_profile_status",
        "bubble_transfer_inventory",
        "bubble_transfer_plan",
        "bubble_transfer_preview",
        "bubble_transfer_execute",
        "bubble_profile_cache_refresh",
    ],
    "notes": "Always require explicit source_profile and target_profile. Start with inventory and plan. Never execute without transfer preview, execute=true, and confirm=true. Do not copy secrets, sessions, API credentials, or live database records by default.",
}
```

Add a recipe that orders:

1. Check both profiles.
2. Refresh stale source and target contexts.
3. Inventory source object.
4. Create transfer plan.
5. Preview plan and dependency report.
6. Execute only when user approved execution.
7. Refresh target context.
8. Verify target object exists.

- [ ] **Step 2: Add documentation**

Add this section to `docs/mcp-clients.md`:

```markdown
### Cross-Project Transfer

Use transfer tools when the user asks to copy a Bubble page, reusable, element, database collection schema, or API Connector call from one configured profile/app to another. The user should not need to name the exact tool. Agents should infer this route from words like copy, transfer, move, duplicate into another app, source project, or target project.

Required flow:

1. `bubble_profile_status` for source and target profiles.
2. `bubble_transfer_inventory`.
3. `bubble_transfer_plan`.
4. `bubble_transfer_preview`.
5. `bubble_transfer_execute` only after explicit approval with `execute=true` and `confirm=true`.
6. `bubble_profile_cache_refresh` for the target profile.
7. `bubble_context_find` to verify the transferred target object.

Never copy sessions, cookies, tokens, private API Connector credentials, private plugin secrets, or live database records by default. Collection transfer means schema by default. API Connector transfer means structure-only by default and must return a target setup checklist for missing private values.
```

Add this section to `docs/cli-reference.md`:

```markdown
## `bubble-mcp transfer`

Plans and executes Bubble project-to-project transfer through local profiles.

```bash
bubble-mcp transfer inventory --source-profile source --source-type reusable --source-ref Header
bubble-mcp transfer plan --source-profile source --target-profile target --source-type reusable --source-ref Header --target-context index --target-parent root
bubble-mcp transfer preview --transfer-id transfer_20260708_120000_header
bubble-mcp transfer execute --transfer-id transfer_20260708_120000_header --execute --confirm
```

Transfer execution writes only to the target profile. It never copies Bubble sessions, cookies, tokens, private API Connector credentials, private plugin secrets, or live database records by default.
```

- [ ] **Step 3: Run quality checks**

Run:

```bash
PYTHONPATH=src python -m pytest tests/unit/test_transfer_models.py tests/unit/test_transfer_store.py tests/unit/test_transfer_profiles.py tests/unit/test_transfer_inventory.py tests/unit/test_transfer_collections.py tests/unit/test_transfer_api_connector.py tests/unit/test_transfer_mapping.py tests/unit/test_transfer_compiler.py tests/unit/test_transfer_executor.py tests/unit/test_mcp_server.py -q
PYTHONPATH=src python -m ruff check src/bubble_mcp/transfer src/bubble_mcp/server/schema_families.py src/bubble_mcp/server/tools.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/agent_guide.py src/bubble_mcp/cli/main.py tests/unit/test_transfer_models.py tests/unit/test_transfer_store.py tests/unit/test_transfer_profiles.py tests/unit/test_transfer_inventory.py tests/unit/test_transfer_collections.py tests/unit/test_transfer_api_connector.py tests/unit/test_transfer_mapping.py tests/unit/test_transfer_compiler.py tests/unit/test_transfer_executor.py tests/unit/test_mcp_server.py
PYTHONPATH=src python -m bubble_mcp.cli.main tools quality
PYTHONPATH=src python -m bubble_mcp.cli.main tools coverage
```

Expected:

```text
pytest passes
All checks passed!
tools quality returns ok=true and issue_count=0
tools coverage returns ok=true and uncovered_count=0
```

- [ ] **Step 4: Commit Task 9**

Run:

```bash
git add src/bubble_mcp/server/agent_guide.py docs/mcp-clients.md docs/cli-reference.md docs/architecture.md tests/unit/test_mcp_server.py
git commit -m "docs: document Bubble cross-project transfer workflow"
```

### Task 10: Real Smoke Plan

**Files:**
- Create: `.local/transfer-smoke-checklist.md`

- [ ] **Step 1: Create smoke checklist**

Create `.local/transfer-smoke-checklist.md`:

```markdown
# Bubble Transfer Smoke Checklist

## Preconditions

- Source profile has `profile status` ready.
- Target profile has `profile status` ready.
- Both profiles have fresh context.
- Target profile session has edit permission.
- Use a safe target test app or branch.

## Smoke 1: Inventory Only

```bash
bubble-mcp transfer inventory \
  --source-profile SOURCE \
  --source-type reusable \
  --source-ref "REUSABLE_NAME"
```

Expected:

- `ok=true`
- `counts.nodes > 0`
- dependency report contains no secrets

## Smoke 2: Plan And Preview

```bash
bubble-mcp transfer plan \
  --source-profile SOURCE \
  --target-profile TARGET \
  --source-type reusable \
  --source-ref "REUSABLE_NAME" \
  --target-context index \
  --target-parent root

bubble-mcp transfer preview --transfer-id TRANSFER_ID
```

Expected:

- plan stores under `BUBBLE_MCP_CONFIG_DIR/transfers/TRANSFER_ID/plan.json`
- preview reports payload count
- blocked dependencies are explicit

## Smoke 3: Execute On Safe Target

```bash
bubble-mcp transfer execute --transfer-id TRANSFER_ID --execute --confirm
bubble-mcp profile refresh-cache --profile TARGET
bubble-mcp context find "REUSABLE_NAME" --profile TARGET --exact --no-include-metadata
```

Expected:

- write result `ok=true`
- target context refresh succeeds
- transferred object appears in target context

## Smoke 4: Collection Schema Preview

```bash
bubble-mcp transfer plan \
  --source-profile SOURCE \
  --target-profile TARGET \
  --source-type reusable \
  --source-ref "REUSABLE_WITH_DATA_DEPENDENCY" \
  --collection-policy map_existing \
  --data-records-policy skip

bubble-mcp transfer preview --transfer-id TRANSFER_ID
```

Expected:

- data type and field dependencies preserve exact Bubble field keys
- privacy-rule dependencies are reported when available
- no live record payload is generated
- missing target schema blocks execution or appears as a required mapping action

## Smoke 5: API Connector Structure Preview

```bash
bubble-mcp transfer plan \
  --source-profile SOURCE \
  --target-profile TARGET \
  --source-type reusable \
  --source-ref "REUSABLE_WITH_API_CONNECTOR_DEPENDENCY" \
  --api-connector-policy structure_only

bubble-mcp transfer preview --transfer-id TRANSFER_ID
```

Expected:

- API and API Call structure is listed
- secret values are redacted in every artifact
- target setup checklist lists each private credential/header/token required
- execution is blocked if a required API Call cannot be mapped or planned safely
```

- [ ] **Step 2: Run smoke against local safe profiles**

Run the checklist with known safe profiles. If a safe source/target pair is not available, stop after unit validation and record:

```text
Real Bubble smoke skipped because no safe source/target profile pair was configured.
```

- [ ] **Step 3: Commit Task 10**

Run:

```bash
git add .local/transfer-smoke-checklist.md
git commit -m "test: add Bubble transfer smoke checklist"
```

## Self-Review

- Spec coverage: The plan covers source inventory, target mapping, dependency report, preview, explicit execution, evidence-ready local storage, ID mapping foundation, CLI, MCP tools, docs, and tests.
- Safety coverage: Execution writes only through the target profile session. Secrets, sessions, cookies, and private API Connector credentials are excluded or blocked.
- Current limitation: The first implementation slice compiles element-root payloads from compact context metadata. A follow-up enhancement should deepen raw `.bubble` module extraction so full nested page/reusable clones preserve every property with the same fidelity as the Aria same-app clone runtime.
- Validation coverage: Unit tests cover deterministic behavior. Real smoke requires two safe configured profiles and should run only after unit, ruff, catalog quality, and coverage checks pass.
