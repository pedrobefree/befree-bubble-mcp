# Catalog Precision Round A.3: Data Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 28 targeted data-schema MCP tools publish precise, runtime-consumable argument contracts and fail closed when those contracts drift.

**Architecture:** Add an explicit data-schema precision inventory that joins authoritative MCP schemas to `BubbleCLI` signatures through direct parameters, named aliases, and MCP controls. Correct the public schemas in the existing enrichment layer, validate targeted calls at the execution boundary, and ship a deterministic standalone audit that also runs from a clean installed wheel.

**Tech Stack:** Python 3.11+, dataclasses, `inspect.signature`, JSON Schema dictionaries, pytest, Ruff, MyPy, existing Bubble MCP catalog/runtime/package-smoke infrastructure.

**Spec:** `docs/superpowers/specs/2026-08-20-catalog-precision-round-a3-data-schema-design.md`

## Global Constraints

- Target exactly the 28 tools listed in the spec; prefix discovery must not widen the round.
- Preserve all public MCP tool names and valid compatibility spellings.
- Preserve valid-call preview, confirmation, dispatch, payload, and response behavior.
- Do not add multi-write data-type/field/exposure or option-set/attribute/value convenience behavior.
- Keep current-first reference resolution and permanent-delete prerequisites unchanged.
- Keep `bubble_catalog_quality`'s successful response shape unchanged; the A.3 audit is a separate gate.
- The deterministic audit must use no LLM, network, Bubble profile, authentication, or editor state.
- Run checkout tests with `PYTHONPATH=src:.` so the repository `scripts` package wins over unrelated installed packages.
- Prefix shell commands with `rtk` per the repository instructions.

---

## File Structure

- Create `src/bubble_mcp/catalog_schema_precision.py`: immutable 28-tool policy inventory, schema/signature comparison, argument normalization, and deterministic report.
- Create `scripts/audit_catalog_schema_precision.py`: checkout-runnable JSON command with success/failure exit status.
- Create `tests/unit/test_catalog_schema_precision.py`: inventory, diagnostics, live contract, and argument-boundary tests.
- Modify `src/bubble_mcp/server/agent_catalog.py`: exact family fields, types, enums, conditions, descriptions, and docs-family assignment.
- Modify `src/bubble_mcp/server/tools.py`: normalize and validate targeted arguments before confirmation and runtime dispatch.
- Modify `scripts/package_smoke.py`: execute the A.3 report from the installed wheel.
- Modify `tests/unit/test_mcp_server.py`: literal public-schema regressions.
- Modify `tests/unit/test_aria_dispatch.py`: canonical/alias mapping regressions.
- Modify `tests/unit/test_package_smoke.py`: installed-wheel A.3 gate regression.
- Modify `docs/harness-and-evals.md`, `docs/release-checklist.md`, and `docs/optimization-roadmap.md`: command, policy, and final evidence.

---

### Task 1: Build the explicit precision inventory and comparison engine

**Files:**
- Create: `src/bubble_mcp/catalog_schema_precision.py`
- Create: `tests/unit/test_catalog_schema_precision.py`

**Interfaces:**
- Produces: `ArgumentAlias(public_name: str, runtime_name: str)`.
- Produces: `ToolSchemaPrecisionSpec(handler: str, required: tuple[str, ...], runtime: tuple[str, ...], aliases: tuple[ArgumentAlias, ...], controls: tuple[str, ...], constraints: tuple[PropertyConstraint, ...])`.
- Produces: `DATA_SCHEMA_PRECISION_SPECS: Mapping[str, ToolSchemaPrecisionSpec]` with exactly 28 entries.
- Produces: `catalog_schema_precision_report(*, tool_schemas: Iterable[Mapping[str, Any]] | None = None, runtime_type: type[Any] | None = None, specs: Mapping[str, ToolSchemaPrecisionSpec] = DATA_SCHEMA_PRECISION_SPECS) -> dict[str, Any]`.
- Produces: `normalize_catalog_schema_precision_args(name: str, args: Mapping[str, Any]) -> dict[str, Any]` for Task 5.

- [ ] **Step 1: Write failing model and synthetic-report tests**

Add tests that require immutable records, exact target membership, stable diagnostics, and the three argument roles without depending on the currently drifting live schemas:

```python
EXPECTED_TARGETS = {
    "scan_types", "list_data_types", "create_data_type", "rename_data_type",
    "delete_data_type", "delete_data_type_permanently", "create_data_field",
    "rename_data_field", "delete_data_field", "set_data_type_api_exposure",
    "list_privacy_rules", "create_privacy_rule", "delete_privacy_rule",
    "set_privacy_rule_name", "set_privacy_rule_condition",
    "set_privacy_rule_permission", "set_privacy_rule_field_visibility",
    "set_privacy_rule_auto_binding", "create_option_set", "rename_option_set",
    "delete_option_set", "create_option_attribute", "create_option_value",
    "delete_option_value", "list_option_values", "rename_option_value",
    "set_option_value_attribute", "reorder_option_values",
}

def test_precision_inventory_owns_exact_round_a3_target_set() -> None:
    assert set(DATA_SCHEMA_PRECISION_SPECS) == EXPECTED_TARGETS
    assert len(DATA_SCHEMA_PRECISION_SPECS) == 28

def test_precision_report_classifies_direct_alias_and_control_properties() -> None:
    class Runtime:
        def mutate(self, target: str, enabled: bool, dry_run: bool = False) -> bool:
            return True

    specs = {
        "sample": ToolSchemaPrecisionSpec(
            handler="mutate",
            required=("profile", "target_ref", "enabled"),
            runtime=("enabled",),
            aliases=(ArgumentAlias("target_ref", "target"),),
            controls=("profile", "execute", "dry_run"),
            constraints=(PropertyConstraint("enabled", type_name="boolean"),),
        )
    }
    report = catalog_schema_precision_report(
        tool_schemas=[{
            "name": "sample",
            "inputSchema": {
                "type": "object",
                "required": ["profile", "target_ref", "enabled"],
                "properties": {
                    "profile": {"type": "string"},
                    "target_ref": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "execute": {"type": "boolean"},
                    "dry_run": {"type": "boolean"},
                },
            },
        }],
        runtime_type=Runtime,
        specs=specs,
    )
    assert report["ok"] is True
    assert report["summary"] == {
        "tool_count": 1,
        "property_count": 5,
        "runtime_property_count": 1,
        "alias_property_count": 1,
        "control_property_count": 3,
        "required_parameter_count": 3,
        "failure_count": 0,
    }
```

Also add separate synthetic cases for missing tool, missing handler, extra property, stale alias, missing required runtime parameter, wrong required list, wrong type/enum/default/`anyOf`, duplicate alias, and non-OK-without-failures conversion.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
rtk env PYTHONPATH=src:. pytest -q tests/unit/test_catalog_schema_precision.py
```

Expected: collection fails because `bubble_mcp.catalog_schema_precision` does not exist.

- [ ] **Step 3: Implement immutable records and deterministic comparison**

Create the module with these concrete model boundaries:

```python
from dataclasses import dataclass
from inspect import Parameter, signature
from typing import Any, Iterable, Literal, Mapping

_UNSET = object()

@dataclass(frozen=True, slots=True)
class ArgumentAlias:
    public_name: str
    runtime_name: str

@dataclass(frozen=True, slots=True)
class PropertyConstraint:
    public_name: str
    type_name: str | tuple[str, ...] | None = None
    enum: tuple[Any, ...] = ()
    default: Any = _UNSET
    min_length: int | None = None
    min_items: int | None = None

@dataclass(frozen=True, slots=True)
class ToolSchemaPrecisionSpec:
    handler: str
    required: tuple[str, ...]
    runtime: tuple[str, ...]
    aliases: tuple[ArgumentAlias, ...] = ()
    controls: tuple[str, ...] = ()
    constraints: tuple[PropertyConstraint, ...] = ()
    any_of_required: tuple[tuple[str, ...], ...] = ()
```

Build `DATA_SCHEMA_PRECISION_SPECS` explicitly. Each record's `runtime` tuple
must list every public property that maps to a same-named handler parameter;
the complete accepted public surface is `runtime`, alias public names, and
controls. Use the shared control tuple
`("profile", "app_id", "app_version", "context_file", "execute", "dry_run", "settings_path", "write_payload", "payload")`; add `confirm` only to the six destructive targets in this round. Record these aliases exactly:

| Tools | Public property | Runtime parameter |
|---|---|---|
| `scan_types`, `list_data_types`, `list_option_values` | `json` | `as_json` |
| type/field/privacy tools whose handler uses a key | `data_type_ref` | `data_type_key` |
| `create_data_field` | `name` | `field_name` |
| `create_data_field` | `type` | `field_type` |
| `rename_data_field`, `delete_data_field` | `name` | `field_key` |
| option tools whose handler uses a set key | `option_set_ref` | `option_set_key` |
| `create_option_attribute` | `type` | `value_type` |
| `create_option_value` | `name` | `label` |
| option-value mutation tools | `option_value_ref` | `value_ref` |
| `rename_option_value` | `new_name` | `new_label` |
| `set_option_value_attribute` | `name` | `attribute_key` |
| `reorder_option_values` | `order` | `assignments` |
| `set_data_type_api_exposure` | `value` | `enabled` |

The report must sort specs, properties, and failures. Treat `dry_run` as a
control even though the runtime also accepts it. Count runtime-required
parameters as signature parameters without defaults after excluding `self` and
parameters satisfied by controls.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
rtk env PYTHONPATH=src:. pytest -q tests/unit/test_catalog_schema_precision.py
```

Expected: synthetic inventory/report tests pass. Do not assert the live 28-tool report is green yet.

- [ ] **Step 5: Commit the inventory engine**

```bash
rtk git add src/bubble_mcp/catalog_schema_precision.py tests/unit/test_catalog_schema_precision.py
rtk git diff --cached --check
rtk git commit -m "test: define data schema precision contracts"
```

---

### Task 2: Correct data-type, field, and API-exposure schemas

**Files:**
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `tests/unit/test_mcp_server.py`
- Modify: `tests/unit/test_catalog_schema_precision.py`
- Modify: `tests/unit/test_aria_dispatch.py`

**Interfaces:**
- Consumes: `catalog_schema_precision_report(..., specs=...)` from Task 1.
- Produces: precise public schemas for the first ten target tools.
- Produces: canonical `enabled: bool` plus compatibility `value -> enabled` dispatch.

- [ ] **Step 1: Write failing literal schema tests**

Add one table-driven test asserting these exact contracts:

```python
expected = {
    "create_data_type": (["profile", "name"], {"key", "private"}, {"fields", "exposed_api", "confirm"}),
    "rename_data_type": (["profile", "data_type_ref", "new_name"], set(), {"data_type_ref_kind"}),
    "delete_data_type": (["profile", "data_type_ref"], {"confirm"}, {"data_type_ref_kind"}),
    "create_data_field": (["profile", "data_type_ref", "name", "type"], {"field_key"}, {"is_list", "optional"}),
    "rename_data_field": (["profile", "data_type_ref", "name", "new_name"], set(), set()),
    "delete_data_field": (["profile", "data_type_ref", "name"], {"confirm"}, set()),
    "set_data_type_api_exposure": (["profile", "data_type_ref", "enabled"], {"ref_kind", "value"}, {"confirm"}),
}
```

For each tuple, assert the required list, presence set, and absence set. Also assert:

```python
assert properties["private"]["type"] == "boolean"
assert properties["enabled"]["type"] == "boolean"
assert properties["field_key"]["type"] == "string"
assert properties["field_key"]["minLength"] == 1
assert properties["value"]["deprecated"] is True
```

Add a filtered live-report assertion for these ten tools and a dispatch test that maps both `enabled=True` and legacy `value=True` to runtime parameter `enabled`.

- [ ] **Step 2: Run tests and verify RED with the measured drift**

```bash
rtk env PYTHONPATH=src:. pytest -q \
  tests/unit/test_mcp_server.py -k 'data_type or data_field or api_exposure' \
  tests/unit/test_catalog_schema_precision.py \
  tests/unit/test_aria_dispatch.py -k 'data_type or data_field'
```

Expected: failures name the currently missing `key`, `private`, `field_key`, and `enabled`, plus the unsupported published fields.

- [ ] **Step 3: Implement the exact family fields and metadata**

Change `_data_schema_fields` so the seven mutation schemas match the table above. Add `key`, `private`, `field_key`, and `enabled` to `FIELD_TYPES`; give key-like fields `minLength: 1`. In `apply_legacy_specific_schema`, mark `value` on `set_data_type_api_exposure` as a deprecated compatibility alias:

```python
if name == "set_data_type_api_exposure":
    properties["value"] = {
        "type": "boolean",
        "deprecated": True,
        "description": "Compatibility alias for enabled; new calls must use enabled.",
    }
```

Add `set_data_type_api_exposure` to the `data_schema` branch of
`_documentation_family_for_name`. Do not change `BubbleCLI` signatures or
schema-lifecycle payload builders.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command again. Expected: all selected tests pass and the ten-tool filtered report is OK.

- [ ] **Step 5: Commit the type/field schema corrections**

```bash
rtk git add src/bubble_mcp/server/agent_catalog.py tests/unit/test_mcp_server.py tests/unit/test_catalog_schema_precision.py tests/unit/test_aria_dispatch.py
rtk git diff --cached --check
rtk git commit -m "fix: align data type MCP schemas with runtime"
```

---

### Task 3: Tighten privacy schema conditions without changing payloads

**Files:**
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `tests/unit/test_mcp_server.py`
- Modify: `tests/unit/test_catalog_schema_precision.py`

**Interfaces:**
- Consumes: the Task 1 precision report.
- Produces: precise schemas for all eight privacy targets.
- Preserves: existing `BubbleCLI` privacy facade signatures and lifecycle payloads.

- [ ] **Step 1: Write failing privacy precision tests**

Extend the existing privacy schema test with these exact assertions:

```python
assert "json" not in tools["list_privacy_rules"]["inputSchema"]["properties"]
visibility = tools["set_privacy_rule_field_visibility"]["inputSchema"]
assert visibility["anyOf"] == [
    {"required": ["view_all"]},
    {"required": ["view_fields"]},
]
assert visibility["properties"]["view_fields"]["type"] == ["string", "array", "object", "null"]
assert tools["set_privacy_rule_permission"]["inputSchema"]["properties"]["value"]["type"] == "boolean"
assert tools["delete_privacy_rule"]["inputSchema"]["properties"]["confirm"]["default"] is False
```

Add a filtered precision-report assertion for the eight privacy tools and a
negative synthetic case proving a changed `anyOf` is reported as
`conditional_contract_mismatch`.

- [ ] **Step 2: Run privacy tests and verify RED**

```bash
rtk env PYTHONPATH=src:. pytest -q \
  tests/unit/test_mcp_server.py -k privacy \
  tests/unit/test_catalog_schema_precision.py -k 'privacy or any_of'
```

Expected: `list_privacy_rules.json` and the missing visibility `anyOf` fail.

- [ ] **Step 3: Apply the minimal privacy schema corrections**

Remove `json` only from `list_privacy_rules`. Add the exact visibility `anyOf`
in `apply_legacy_specific_schema`. Keep `create_privacy_rule` defaults,
destructive `confirm`, field-key guidance, current-first resolution, and all
runtime methods unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command again. Expected: all privacy tests pass and the filtered report is OK.

- [ ] **Step 5: Commit the privacy contract**

```bash
rtk git add src/bubble_mcp/server/agent_catalog.py tests/unit/test_mcp_server.py tests/unit/test_catalog_schema_precision.py
rtk git diff --cached --check
rtk git commit -m "fix: encode precise privacy tool schemas"
```

---

### Task 4: Correct option-set and option-value schemas

**Files:**
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `tests/unit/test_mcp_server.py`
- Modify: `tests/unit/test_catalog_schema_precision.py`
- Modify: `tests/unit/test_aria_dispatch.py`

**Interfaces:**
- Consumes: the Task 1 alias inventory and report.
- Produces: precise schemas for ten option targets.
- Preserves: focused attribute/value tools and existing option lifecycle payloads.

- [ ] **Step 1: Write failing option precision tests**

Assert the following exact changes:

```python
create_set = tools["create_option_set"]["inputSchema"]
assert create_set["required"] == ["profile", "name"]
assert "key" in create_set["properties"]
assert {"values", "attributes", "ref_kind", "confirm"}.isdisjoint(create_set["properties"])

create_attribute = tools["create_option_attribute"]["inputSchema"]
assert create_attribute["required"] == ["profile", "option_set_ref", "name", "type"]
assert "attribute_key" in create_attribute["properties"]
assert {"ref_kind", "confirm"}.isdisjoint(create_attribute["properties"])

for name in ["delete_option_value", "rename_option_value", "set_option_value_attribute", "reorder_option_values"]:
    assert tools[name]["inputSchema"]["properties"]["ref_kind"]["enum"] == [
        "auto", "key", "label", "db_value"
    ]

order = tools["reorder_option_values"]["inputSchema"]["properties"]["order"]
assert order == {
    "type": "array",
    "items": {"type": "string", "minLength": 3},
    "minItems": 1,
    "description": "Complete value_key:sort_factor assignments; each active value must appear exactly once.",
}
```

Also assert `sort_factor` and `id_counter` are integers, `parse_json` is boolean,
only destructive option tools expose `confirm`, and the filtered ten-tool
precision report is OK.

- [ ] **Step 2: Run option tests and verify RED**

```bash
rtk env PYTHONPATH=src:. pytest -q \
  tests/unit/test_mcp_server.py -k option \
  tests/unit/test_catalog_schema_precision.py -k option \
  tests/unit/test_aria_dispatch.py -k option
```

Expected: failures expose inline `values`/`attributes`, generic reference enums, and the string-shaped reorder contract.

- [ ] **Step 3: Implement exact option schema overrides**

Update `_option_schema_fields` to publish only handler-backed properties plus
MCP controls. Add `attribute_key`, `value_key`, `db_value`, `sort_factor`,
`parse_json`, and `order` types to `FIELD_TYPES`. In
`apply_legacy_specific_schema`, override option-value `ref_kind` with
`["auto", "key", "label", "db_value"]` and install the exact `order` schema
above. Keep `confirm` on `delete_option_set` and `delete_option_value`; remove it
from non-destructive option tools.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command again. Expected: all option tests pass and the filtered report is OK.

- [ ] **Step 5: Commit the option contract**

```bash
rtk git add src/bubble_mcp/server/agent_catalog.py tests/unit/test_mcp_server.py tests/unit/test_catalog_schema_precision.py tests/unit/test_aria_dispatch.py
rtk git diff --cached --check
rtk git commit -m "fix: align option MCP schemas with runtime"
```

---

### Task 5: Reject silently ignored targeted arguments and close the live audit

**Files:**
- Modify: `src/bubble_mcp/catalog_schema_precision.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `tests/unit/test_catalog_schema_precision.py`
- Modify: `tests/unit/test_mcp_server.py`

**Interfaces:**
- Consumes: all 28 corrected schemas from Tasks 2-4.
- Produces: `normalize_catalog_schema_precision_args` used before confirmation and runtime dispatch.
- Produces: a live `catalog_schema_precision_report()` with `ok=True` and `tool_count=28`.

- [ ] **Step 1: Write failing boundary and live-report tests**

Add these tests:

```python
def test_live_data_schema_precision_report_is_complete_and_green() -> None:
    report = catalog_schema_precision_report()
    assert report["ok"] is True
    assert report["summary"]["tool_count"] == 28
    assert report["summary"]["failure_count"] == 0
    assert report["failures"] == []

def test_targeted_argument_normalization_rejects_unknown_operational_fields() -> None:
    with pytest.raises(ValueError, match="create_data_type does not accept operational argument: fields"):
        normalize_catalog_schema_precision_args("create_data_type", {"profile": "smoke", "name": "Order", "fields": []})

def test_api_exposure_legacy_value_alias_normalizes_to_enabled() -> None:
    normalized = normalize_catalog_schema_precision_args(
        "set_data_type_api_exposure",
        {"profile": "smoke", "data_type_ref": "order", "value": True},
    )
    assert normalized["enabled"] is True
    assert normalized["value"] is True
```

At the MCP boundary, call `create_data_type` with removed `fields` and assert the
same field-specific error. Call `set_data_type_api_exposure` with `value=True`
and assert dispatch still receives `enabled=True`.

- [ ] **Step 2: Run boundary tests and verify RED**

```bash
rtk env PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py \
  tests/unit/test_mcp_server.py -k 'unsupported_operational or api_exposure'
```

Expected: targeted calls still discard unknown fields and legacy `value` is not normalized before dispatch.

- [ ] **Step 3: Implement normalization at the existing server boundary**

In `normalize_catalog_schema_precision_args`, return untouched arguments for
non-target tools. For target tools, compute the accepted set from the spec's
explicit runtime properties, alias public names, and controls. Raise one sorted,
field-specific `ValueError` for the first unknown key. Normalize only the
existing API-exposure compatibility alias:

```python
normalized = dict(args)
if name == "set_data_type_api_exposure" and "enabled" not in normalized and "value" in normalized:
    normalized["enabled"] = normalized["value"]
return normalized
```

In `call_legacy_catalog_tool`, invoke the normalizer immediately after the
`sync_figma_tokens` special case and before computing `executing` or checking
confirmation. Do not add a second dispatch path.

- [ ] **Step 4: Run focused and live audit tests and verify GREEN**

Run the Step 2 command again, then:

```bash
rtk env PYTHONPATH=src:. pytest -q tests/unit/test_aria_dispatch.py tests/unit/test_schema_lifecycle_data_types.py tests/unit/test_schema_lifecycle_privacy.py tests/unit/test_schema_lifecycle_options.py
```

Expected: all tests pass; the live report covers 28 tools with zero failures.

- [ ] **Step 5: Commit boundary enforcement**

```bash
rtk git add src/bubble_mcp/catalog_schema_precision.py src/bubble_mcp/server/tools.py tests/unit/test_catalog_schema_precision.py tests/unit/test_mcp_server.py
rtk git diff --cached --check
rtk git commit -m "fix: reject ignored data schema arguments"
```

---

### Task 6: Ship the standalone and installed-wheel audit gates

**Files:**
- Create: `scripts/audit_catalog_schema_precision.py`
- Modify: `scripts/package_smoke.py`
- Modify: `tests/unit/test_catalog_schema_precision.py`
- Modify: `tests/unit/test_package_smoke.py`
- Modify: `docs/harness-and-evals.md`
- Modify: `docs/release-checklist.md`

**Interfaces:**
- Consumes: `catalog_schema_precision_report()` from Task 1.
- Produces: checkout command `PYTHONPATH=src python scripts/audit_catalog_schema_precision.py`.
- Produces: installed-wheel result keys `schema_precision_ok` and `schema_precision_tool_count`.

- [ ] **Step 1: Write failing script and package-smoke tests**

Add a subprocess test matching the A.2 audit pattern:

```python
result = subprocess.run(
    [sys.executable, "scripts/audit_catalog_schema_precision.py"],
    cwd=REPOSITORY_ROOT,
    text=True,
    capture_output=True,
    check=False,
)
assert result.returncode == 0
report = json.loads(result.stdout)
assert report["ok"] is True
assert report["summary"]["tool_count"] == 28
```

Extend `test_package_smoke_checks_catalog_quality_from_installed_wheel`:

```python
assert "catalog_schema_precision_report" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
assert "schema_precision_ok" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
assert "schema_precision_tool_count" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
rtk env PYTHONPATH=src:. pytest -q tests/unit/test_catalog_schema_precision.py tests/unit/test_package_smoke.py
```

Expected: the audit script and installed-wheel imports are absent.

- [ ] **Step 3: Add the script and installed-wheel check**

Implement the script exactly like the existing leaf-map wrapper: prepend
`src`, call `catalog_schema_precision_report`, print sorted indented JSON, and
exit `0` only when `report["ok"]` is true.

Extend `INSTALLED_CATALOG_QUALITY_CHECK` to import and execute the A.3 report,
assert it is green, and print:

```python
{
    "schema_precision_ok": precision["ok"],
    "schema_precision_tool_count": precision["summary"]["tool_count"],
}
```

Document the checkout command, deterministic/no-network behavior, exact
28-tool target, and field-role policy in `docs/harness-and-evals.md`. Add the
command and expected `ok: true`, `tool_count: 28`, `failure_count: 0` to the
release checklist.

- [ ] **Step 4: Run focused, script, and clean-wheel verification**

```bash
rtk env PYTHONPATH=src:. pytest -q tests/unit/test_catalog_schema_precision.py tests/unit/test_package_smoke.py
rtk env PYTHONPATH=src python scripts/audit_catalog_schema_precision.py
rtk python scripts/package_smoke.py --python python3.11
```

Expected: focused tests pass; audit reports 28/28 with zero failures; wheel smoke reports both schema-precision keys successfully from the installed package.

- [ ] **Step 5: Commit release integration**

```bash
rtk git add scripts/audit_catalog_schema_precision.py scripts/package_smoke.py tests/unit/test_catalog_schema_precision.py tests/unit/test_package_smoke.py docs/harness-and-evals.md docs/release-checklist.md
rtk git diff --cached --check
rtk git commit -m "test: gate data schema precision in releases"
```

---

### Task 7: Run complete validation and record closing evidence

**Files:**
- Modify: `docs/optimization-roadmap.md`
- Test: complete repository and installed-wheel gates.

**Interfaces:**
- Consumes: all implementation and audit outputs from Tasks 1-6.
- Produces: fresh A.3 closing evidence without claiming authenticated Bubble execution.

- [ ] **Step 1: Run focused contract suites**

```bash
rtk env PYTHONPATH=src:. pytest -q \
  tests/unit/test_catalog_schema_precision.py \
  tests/unit/test_mcp_server.py \
  tests/unit/test_aria_dispatch.py \
  tests/unit/test_schema_lifecycle_data_types.py \
  tests/unit/test_schema_lifecycle_privacy.py \
  tests/unit/test_schema_lifecycle_options.py \
  tests/unit/test_package_smoke.py
```

Expected: all focused tests pass.

- [ ] **Step 2: Run static and deterministic gates**

```bash
rtk env PYTHONPATH=src:. ruff check src tests scripts
rtk env PYTHONPATH=src:. mypy src
rtk env PYTHONPATH=src python scripts/audit_catalog_selection.py
rtk env PYTHONPATH=src python scripts/audit_catalog_ambiguity.py
rtk env PYTHONPATH=src python scripts/audit_cli_catalog.py
rtk env PYTHONPATH=src python scripts/audit_cli_leaf_map.py
rtk env PYTHONPATH=src python scripts/audit_catalog_schema_precision.py
rtk python scripts/audit_sensitive_paths.py .
rtk git diff --check
```

Expected: every command exits zero; A.1 remains 327/327 and 27/27, legacy CLI has zero missing mappings, A.2 has zero catalog gaps, and A.3 reports 28 tools with zero failures.

- [ ] **Step 3: Run full Python and Node suites**

```bash
rtk env PYTHONPATH=src:. pytest -q
rtk npm test
```

Expected: all Python tests and all 11 Node tests pass. Record the fresh Python count and duration.

- [ ] **Step 4: Run package and runtime smokes**

```bash
rtk python scripts/package_smoke.py --python python3.11
rtk env PYTHONPATH=src python -m bubble_mcp.cli.main smoke runtime --suite coverage
rtk env PYTHONPATH=src python -m bubble_mcp.cli.main smoke runtime --suite agent-routing
```

Expected: installed-wheel smoke is OK with A.3 evidence; coverage passes 2/2 and agent-routing passes 9/9 with `profile: null` and `execute: false`.

- [ ] **Step 5: Update the roadmap with literal evidence**

Add a `Round A.3: Data-schema precision` section to
`docs/optimization-roadmap.md`. Record the 28-tool scope, direct/alias/control
counts from the final report, removed unsupported fields, retained aliases,
exact test/static/audit/wheel/smoke results, and the explicit statement that no
authenticated Bubble-editor execution was performed.

- [ ] **Step 6: Re-run documentation and diff hygiene checks**

```bash
rtk rg -n "Round A.3|28 tools|schema precision|authenticated" docs/optimization-roadmap.md docs/harness-and-evals.md docs/release-checklist.md
rtk git diff --check
rtk git status --short
```

Expected: documentation contains the final evidence, no whitespace errors exist, and only intended files are modified.

- [ ] **Step 7: Commit closing evidence**

```bash
rtk git add docs/optimization-roadmap.md
rtk git diff --cached --check
rtk git commit -m "docs: close Round A.3 data schema precision"
```

- [ ] **Step 8: Inspect final branch state before publication**

```bash
rtk git status --short --branch
rtk git log --oneline origin/main..HEAD
rtk git diff --stat origin/main...HEAD
rtk git diff --check origin/main...HEAD
```

Expected: clean worktree, only A.3 commits ahead of `origin/main`, expected file list, and clean diff hygiene. Push/PR publication requires the user's explicit authorization at execution time.
