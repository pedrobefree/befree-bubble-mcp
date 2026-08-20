from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from bubble_mcp.catalog_schema_precision import (
    DATA_SCHEMA_PRECISION_SPECS,
    ArgumentAlias,
    PropertyConstraint,
    ToolSchemaPrecisionSpec,
    catalog_schema_precision_report,
    normalize_catalog_schema_precision_args,
)


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


def _sample_schema(*, properties: dict[str, object] | None = None, required: list[str] | None = None) -> dict[str, object]:
    return {
        "name": "sample",
        "inputSchema": {
            "type": "object",
            "required": ["profile", "target_ref", "enabled"] if required is None else required,
            "properties": {
                "profile": {"type": "string"},
                "target_ref": {"type": "string"},
                "enabled": {"type": "boolean"},
                "execute": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            } if properties is None else properties,
        },
    }


def _sample_specs(*, aliases: tuple[ArgumentAlias, ...] = (ArgumentAlias("target_ref", "target"),)) -> dict[str, ToolSchemaPrecisionSpec]:
    return {
        "sample": ToolSchemaPrecisionSpec(
            handler="mutate",
            required=("profile", "target_ref", "enabled"),
            runtime=("enabled",),
            aliases=aliases,
            controls=("profile", "execute", "dry_run"),
            constraints=(PropertyConstraint("enabled", type_name="boolean"),),
        )
    }


class Runtime:
    def mutate(self, target: str, enabled: bool, dry_run: bool = False) -> bool:
        return True


def _report(**kwargs: object) -> dict[str, object]:
    return catalog_schema_precision_report(
        tool_schemas=[_sample_schema()], runtime_type=Runtime, specs=_sample_specs(), **kwargs
    )


def test_precision_inventory_owns_exact_round_a3_target_set() -> None:
    assert set(DATA_SCHEMA_PRECISION_SPECS) == EXPECTED_TARGETS
    assert len(DATA_SCHEMA_PRECISION_SPECS) == 28


def test_precision_records_are_immutable() -> None:
    alias = ArgumentAlias("public", "runtime")
    constraint = PropertyConstraint("public", type_name="string")
    spec = ToolSchemaPrecisionSpec("method", (), ())

    with pytest.raises(FrozenInstanceError):
        alias.public_name = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        constraint.type_name = "boolean"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        spec.handler = "other"  # type: ignore[misc]


def test_precision_report_classifies_direct_alias_and_control_properties() -> None:
    report = _report()

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


@pytest.mark.parametrize(
    ("schemas", "runtime_type", "specs", "code"),
    [
        ([], Runtime, _sample_specs(), "missing_tool"),
        ([_sample_schema()], Runtime, {"sample": ToolSchemaPrecisionSpec("absent", (), ())}, "missing_handler"),
        ([_sample_schema(properties={**_sample_schema()["inputSchema"]["properties"], "stray": {"type": "string"}})], Runtime, _sample_specs(), "extra_property"),  # type: ignore[index]
        ([_sample_schema()], Runtime, _sample_specs(aliases=(ArgumentAlias("target_ref", "absent"),)), "stale_alias"),
        ([_sample_schema(required=["profile", "target_ref"])], Runtime, _sample_specs(), "required_list_mismatch"),
    ],
)
def test_precision_report_emits_stable_failures(
    schemas: list[dict[str, object]],
    runtime_type: type[object],
    specs: dict[str, ToolSchemaPrecisionSpec],
    code: str,
) -> None:
    report = catalog_schema_precision_report(tool_schemas=schemas, runtime_type=runtime_type, specs=specs)

    assert report["ok"] is False
    assert report["failures"] == sorted(report["failures"], key=lambda failure: (failure["tool"], failure["field"], failure["code"]))
    assert any(failure["code"] == code for failure in report["failures"])


def test_precision_report_detects_missing_required_runtime_parameter() -> None:
    class RequiredRuntime:
        def mutate(self, target: str, enabled: bool, missing: str, dry_run: bool = False) -> bool:
            return True

    report = catalog_schema_precision_report(
        tool_schemas=[_sample_schema()], runtime_type=RequiredRuntime, specs=_sample_specs()
    )

    assert {failure["code"] for failure in report["failures"]} == {"missing_required_runtime_parameter"}
    assert report["failures"][0]["field"] == "missing"


@pytest.mark.parametrize(
    ("property_schema", "constraint", "code"),
    [
        ({"type": "string"}, PropertyConstraint("enabled", type_name="boolean"), "type_mismatch"),
        ({"type": "boolean", "enum": [False]}, PropertyConstraint("enabled", enum=(True,)), "enum_mismatch"),
        ({"type": "boolean", "default": True}, PropertyConstraint("enabled", default=False), "default_mismatch"),
    ],
)
def test_precision_report_detects_property_constraint_drift(
    property_schema: dict[str, object], constraint: PropertyConstraint, code: str
) -> None:
    schema = _sample_schema(properties={**_sample_schema()["inputSchema"]["properties"], "enabled": property_schema})  # type: ignore[index]
    specs = _sample_specs()
    specs["sample"] = ToolSchemaPrecisionSpec(
        handler="mutate",
        required=("profile", "target_ref", "enabled"),
        runtime=("enabled",),
        aliases=(ArgumentAlias("target_ref", "target"),),
        controls=("profile", "execute", "dry_run"),
        constraints=(constraint,),
    )

    report = catalog_schema_precision_report(tool_schemas=[schema], runtime_type=Runtime, specs=specs)

    assert any(failure["code"] == code for failure in report["failures"])


def test_precision_report_detects_any_of_and_duplicate_alias_drift() -> None:
    specs = {
        "sample": ToolSchemaPrecisionSpec(
            handler="mutate",
            required=("profile", "target_ref", "enabled"),
            runtime=("enabled",),
            aliases=(ArgumentAlias("target_ref", "target"), ArgumentAlias("target_ref", "target")),
            controls=("profile", "execute", "dry_run"),
            constraints=(PropertyConstraint("enabled", type_name="boolean"),),
            any_of_required=(("enabled", "target_ref"),),
        )
    }

    report = catalog_schema_precision_report(tool_schemas=[_sample_schema()], runtime_type=Runtime, specs=specs)

    assert {failure["code"] for failure in report["failures"]} == {"any_of_mismatch", "duplicate_alias"}


def test_precision_report_never_returns_non_ok_without_actionable_failures() -> None:
    report = _report()

    assert report["ok"] or report["failures"]


def test_normalize_catalog_schema_precision_args_is_a_copying_pass_through() -> None:
    args = {"enabled": True}

    normalized = normalize_catalog_schema_precision_args("sample", args)

    assert normalized == args
    assert normalized is not args
