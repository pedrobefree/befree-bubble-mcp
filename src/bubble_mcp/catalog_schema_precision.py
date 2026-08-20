"""Explicit, deterministic contracts for the data-schema catalog surface."""

from __future__ import annotations

from dataclasses import dataclass
from inspect import Parameter, signature
from typing import Any, Iterable, Literal, Mapping


_UNSET = object()
_SHARED_CONTROLS = (
    "profile",
    "app_id",
    "app_version",
    "context_file",
    "execute",
    "dry_run",
    "settings_path",
    "write_payload",
    "payload",
)
_DESTRUCTIVE_CONTROLS = (*_SHARED_CONTROLS, "confirm")


@dataclass(frozen=True, slots=True)
class ArgumentAlias:
    """A public catalog name that dispatches to a different runtime parameter."""

    public_name: str
    runtime_name: str


@dataclass(frozen=True, slots=True)
class PropertyConstraint:
    """Precision-sensitive JSON Schema attributes for one public property."""

    public_name: str
    type_name: str | tuple[str, ...] | None = None
    enum: tuple[Any, ...] = ()
    default: Any = _UNSET
    min_length: int | None = None
    min_items: int | None = None


@dataclass(frozen=True, slots=True)
class ToolSchemaPrecisionSpec:
    """One checked public schema contract and its BubbleCLI handler."""

    handler: str
    required: tuple[str, ...]
    runtime: tuple[str, ...]
    aliases: tuple[ArgumentAlias, ...] = ()
    controls: tuple[str, ...] = ()
    constraints: tuple[PropertyConstraint, ...] = ()
    any_of_required: tuple[tuple[str, ...], ...] = ()


FailureCode = Literal[
    "any_of_mismatch",
    "duplicate_alias",
    "extra_property",
    "missing_handler",
    "missing_expected_property",
    "missing_required_runtime_parameter",
    "missing_tool",
    "required_list_mismatch",
    "stale_alias",
    "stale_runtime_property",
    "constraint_property_missing",
    "type_mismatch",
    "enum_mismatch",
    "default_mismatch",
    "min_length_mismatch",
    "min_items_mismatch",
]


def _alias(public_name: str, runtime_name: str) -> ArgumentAlias:
    return ArgumentAlias(public_name, runtime_name)


def _constraint(
    public_name: str,
    *,
    type_name: str | tuple[str, ...] | None = "string",
    enum: tuple[Any, ...] = (),
    default: Any = _UNSET,
    min_length: int | None = None,
    min_items: int | None = None,
) -> PropertyConstraint:
    return PropertyConstraint(public_name, type_name, enum, default, min_length, min_items)


def _string(name: str) -> PropertyConstraint:
    return _constraint(name, min_length=1)


def _boolean(name: str, default: Any = _UNSET) -> PropertyConstraint:
    return _constraint(name, type_name="boolean", default=default)


DATA_SCHEMA_PRECISION_SPECS: Mapping[str, ToolSchemaPrecisionSpec] = {
    "scan_types": ToolSchemaPrecisionSpec(
        "list_data_types", ("profile",), (), (_alias("json", "as_json"),), _SHARED_CONTROLS,
        (_boolean("json", False),),
    ),
    "list_data_types": ToolSchemaPrecisionSpec(
        "list_data_types", ("profile",), (), (_alias("json", "as_json"),), _SHARED_CONTROLS,
        (_boolean("json", False),),
    ),
    "create_data_type": ToolSchemaPrecisionSpec(
        "create_data_type", ("profile", "name"), ("name", "key", "private"), (), _SHARED_CONTROLS,
        (_string("name"), _string("key"), _boolean("private", False)),
    ),
    "rename_data_type": ToolSchemaPrecisionSpec(
        "rename_data_type", ("profile", "data_type_ref", "new_name"), ("new_name",),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("new_name")),
    ),
    "delete_data_type": ToolSchemaPrecisionSpec(
        "delete_data_type", ("profile", "data_type_ref"), (),
        (_alias("data_type_ref", "data_type_key"),), _DESTRUCTIVE_CONTROLS,
        (_string("data_type_ref"),),
    ),
    "delete_data_type_permanently": ToolSchemaPrecisionSpec(
        "delete_data_type_permanently", ("profile", "data_type_ref"), (),
        (_alias("data_type_ref", "data_type_key"),), _DESTRUCTIVE_CONTROLS,
        (_string("data_type_ref"),),
    ),
    "create_data_field": ToolSchemaPrecisionSpec(
        "create_data_field", ("profile", "data_type_ref", "name", "type"), ("field_key",),
        (_alias("data_type_ref", "data_type_key"), _alias("name", "field_name"), _alias("type", "field_type")),
        _SHARED_CONTROLS, (_string("data_type_ref"), _string("name"), _string("type"), _string("field_key")),
    ),
    "rename_data_field": ToolSchemaPrecisionSpec(
        "rename_data_field", ("profile", "data_type_ref", "name", "new_name"), ("new_name",),
        (_alias("data_type_ref", "data_type_key"), _alias("name", "field_key")), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("name"), _string("new_name")),
    ),
    "delete_data_field": ToolSchemaPrecisionSpec(
        "delete_data_field", ("profile", "data_type_ref", "name"), (),
        (_alias("data_type_ref", "data_type_key"), _alias("name", "field_key")), _DESTRUCTIVE_CONTROLS,
        (_string("data_type_ref"), _string("name")),
    ),
    "set_data_type_api_exposure": ToolSchemaPrecisionSpec(
        "set_data_type_api_exposure", ("profile", "data_type_ref", "enabled"), ("data_type_ref", "enabled"),
        (_alias("value", "enabled"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _boolean("enabled")),
    ),
    "list_privacy_rules": ToolSchemaPrecisionSpec(
        "list_privacy_rules", ("profile", "data_type_ref"), (),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS, (_string("data_type_ref"),),
    ),
    "create_privacy_rule": ToolSchemaPrecisionSpec(
        "create_privacy_rule", ("profile", "data_type_ref"),
        ("rule_name", "rule_key", "view_all", "view_attachments", "search_for", "auto_binding", "view_fields", "binding_fields", "condition_json", "include_everyone_default", "id_counter"),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("rule_name"), _string("rule_key"), _boolean("view_all", True), _boolean("view_attachments", True), _boolean("search_for", True), _boolean("auto_binding", False), _boolean("include_everyone_default", True), _constraint("id_counter", type_name="integer")),
    ),
    "delete_privacy_rule": ToolSchemaPrecisionSpec(
        "delete_privacy_rule", ("profile", "data_type_ref", "rule_key"), ("rule_key",),
        (_alias("data_type_ref", "data_type_key"),), _DESTRUCTIVE_CONTROLS,
        (_string("data_type_ref"), _string("rule_key")),
    ),
    "set_privacy_rule_name": ToolSchemaPrecisionSpec(
        "set_privacy_rule_name", ("profile", "data_type_ref", "rule_key", "new_name"), ("rule_key", "new_name"),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("rule_key"), _string("new_name")),
    ),
    "set_privacy_rule_condition": ToolSchemaPrecisionSpec(
        "set_privacy_rule_condition", ("profile", "data_type_ref", "rule_key", "condition_json"), ("rule_key", "condition_json"),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("rule_key")),
    ),
    "set_privacy_rule_permission": ToolSchemaPrecisionSpec(
        "set_privacy_rule_permission", ("profile", "data_type_ref", "rule_key", "permission", "value"), ("rule_key", "permission", "value"),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("rule_key"), _constraint("permission", enum=("view_all", "view_attachments", "search_for", "auto_binding")), _boolean("value")),
    ),
    "set_privacy_rule_field_visibility": ToolSchemaPrecisionSpec(
        "set_privacy_rule_field_visibility", ("profile", "data_type_ref", "rule_key"), ("rule_key", "view_all", "view_fields"),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("rule_key"), _boolean("view_all")), (("view_all",), ("view_fields",)),
    ),
    "set_privacy_rule_auto_binding": ToolSchemaPrecisionSpec(
        "set_privacy_rule_auto_binding", ("profile", "data_type_ref", "rule_key", "auto_binding"), ("rule_key", "auto_binding", "binding_fields"),
        (_alias("data_type_ref", "data_type_key"),), _SHARED_CONTROLS,
        (_string("data_type_ref"), _string("rule_key"), _boolean("auto_binding")),
    ),
    "create_option_set": ToolSchemaPrecisionSpec(
        "create_option_set", ("profile", "name"), ("name", "key"), (), _SHARED_CONTROLS,
        (_string("name"), _string("key")),
    ),
    "rename_option_set": ToolSchemaPrecisionSpec(
        "rename_option_set", ("profile", "option_set_ref", "new_name"), ("new_name",),
        (_alias("option_set_ref", "option_set_key"),), _SHARED_CONTROLS,
        (_string("option_set_ref"), _string("new_name")),
    ),
    "delete_option_set": ToolSchemaPrecisionSpec(
        "delete_option_set", ("profile", "option_set_ref"), (),
        (_alias("option_set_ref", "option_set_key"),), _DESTRUCTIVE_CONTROLS, (_string("option_set_ref"),),
    ),
    "create_option_attribute": ToolSchemaPrecisionSpec(
        "create_option_attribute", ("profile", "option_set_ref", "name", "type"), ("name", "attribute_key"),
        (_alias("option_set_ref", "option_set_key"), _alias("type", "value_type")), _SHARED_CONTROLS,
        (_string("option_set_ref"), _string("name"), _string("type"), _string("attribute_key")),
    ),
    "create_option_value": ToolSchemaPrecisionSpec(
        "create_option_value", ("profile", "option_set_ref", "name"), ("value_key", "db_value", "sort_factor", "id_counter"),
        (_alias("option_set_ref", "option_set_key"), _alias("name", "label")), _SHARED_CONTROLS,
        (_string("option_set_ref"), _string("name"), _string("value_key"), _string("db_value"), _constraint("sort_factor", type_name="integer"), _constraint("id_counter", type_name="integer")),
    ),
    "delete_option_value": ToolSchemaPrecisionSpec(
        "delete_option_value", ("profile", "option_set_ref", "option_value_ref"), ("ref_kind",),
        (_alias("option_set_ref", "option_set_key"), _alias("option_value_ref", "value_ref")), _DESTRUCTIVE_CONTROLS,
        (_string("option_set_ref"), _string("option_value_ref"), _constraint("ref_kind", enum=("key", "db_value", "db-value", "label"), default="key")),
    ),
    "list_option_values": ToolSchemaPrecisionSpec(
        "list_option_values", ("profile", "option_set_ref"), (),
        (_alias("option_set_ref", "option_set_key"), _alias("json", "as_json")), _SHARED_CONTROLS,
        (_string("option_set_ref"), _boolean("json", False)),
    ),
    "rename_option_value": ToolSchemaPrecisionSpec(
        "rename_option_value", ("profile", "option_set_ref", "option_value_ref", "new_name"), ("ref_kind",),
        (_alias("option_set_ref", "option_set_key"), _alias("option_value_ref", "value_ref"), _alias("new_name", "new_label")), _SHARED_CONTROLS,
        (_string("option_set_ref"), _string("option_value_ref"), _string("new_name"), _constraint("ref_kind", enum=("key", "db_value", "db-value", "label"), default="key")),
    ),
    "set_option_value_attribute": ToolSchemaPrecisionSpec(
        "set_option_value_attribute", ("profile", "option_set_ref", "option_value_ref", "name", "value"), ("value", "ref_kind", "parse_json"),
        (_alias("option_set_ref", "option_set_key"), _alias("option_value_ref", "value_ref"), _alias("name", "attribute_key")), _SHARED_CONTROLS,
        (_string("option_set_ref"), _string("option_value_ref"), _string("name"), _constraint("ref_kind", enum=("key", "db_value", "db-value", "label"), default="key"), _boolean("parse_json", False)),
    ),
    "reorder_option_values": ToolSchemaPrecisionSpec(
        "reorder_option_values", ("profile", "option_set_ref", "order"), ("ref_kind",),
        (_alias("option_set_ref", "option_set_key"), _alias("order", "assignments")), _SHARED_CONTROLS,
        (_string("option_set_ref"), _constraint("order", type_name="array", min_items=1), _constraint("ref_kind", enum=("key", "db_value", "db-value", "label"), default="key")),
    ),
}


def _failure(tool: str, field: str, code: FailureCode, message: str) -> dict[str, str]:
    return {"tool": tool, "field": field, "code": code, "message": message}


def _schema_properties(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, Mapping):
        return {}
    properties = input_schema.get("properties")
    return properties if isinstance(properties, Mapping) else {}


def _schema_required(schema: Mapping[str, Any]) -> tuple[str, ...]:
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, Mapping):
        return ()
    required = input_schema.get("required", ())
    if not isinstance(required, Iterable) or isinstance(required, (str, bytes)):
        return ()
    return tuple(sorted(str(name) for name in required))


def _schema_any_of_required(schema: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    input_schema = schema.get("inputSchema")
    if not isinstance(input_schema, Mapping):
        return ()
    any_of = input_schema.get("anyOf", ())
    if not isinstance(any_of, Iterable) or isinstance(any_of, (str, bytes, Mapping)):
        return ()
    groups: list[tuple[str, ...]] = []
    for item in any_of:
        if not isinstance(item, Mapping):
            continue
        required = item.get("required")
        if isinstance(required, Iterable) and not isinstance(required, (str, bytes, Mapping)):
            groups.append(tuple(sorted(str(name) for name in required)))
    return tuple(sorted(groups))


def _runtime_parameters(handler: Any) -> dict[str, Parameter]:
    return {
        name: parameter
        for name, parameter in signature(handler).parameters.items()
        if name != "self" and parameter.kind not in {Parameter.VAR_KEYWORD, Parameter.VAR_POSITIONAL}
    }


def _constraint_failures(
    tool_name: str, properties: Mapping[str, Any], constraints: tuple[PropertyConstraint, ...]
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for constraint in constraints:
        property_schema = properties.get(constraint.public_name)
        if not isinstance(property_schema, Mapping):
            failures.append(_failure(tool_name, constraint.public_name, "constraint_property_missing", "Constrained property is absent from the schema."))
            continue
        if constraint.type_name is not None:
            actual_type = property_schema.get("type")
            expected_type: Any = list(constraint.type_name) if isinstance(constraint.type_name, tuple) else constraint.type_name
            if actual_type != expected_type:
                failures.append(_failure(tool_name, constraint.public_name, "type_mismatch", f"Expected type {expected_type!r}, found {actual_type!r}."))
        if constraint.enum and tuple(property_schema.get("enum", ())) != constraint.enum:
            failures.append(_failure(tool_name, constraint.public_name, "enum_mismatch", f"Expected enum {list(constraint.enum)!r}, found {property_schema.get('enum')!r}."))
        if constraint.default is not _UNSET and property_schema.get("default", _UNSET) != constraint.default:
            failures.append(_failure(tool_name, constraint.public_name, "default_mismatch", f"Expected default {constraint.default!r}, found {property_schema.get('default', _UNSET)!r}."))
        if constraint.min_length is not None and property_schema.get("minLength") != constraint.min_length:
            failures.append(_failure(tool_name, constraint.public_name, "min_length_mismatch", f"Expected minLength {constraint.min_length}, found {property_schema.get('minLength')!r}."))
        if constraint.min_items is not None and property_schema.get("minItems") != constraint.min_items:
            failures.append(_failure(tool_name, constraint.public_name, "min_items_mismatch", f"Expected minItems {constraint.min_items}, found {property_schema.get('minItems')!r}."))
    return failures


def catalog_schema_precision_report(
    *,
    tool_schemas: Iterable[Mapping[str, Any]] | None = None,
    runtime_type: type[Any] | None = None,
    specs: Mapping[str, ToolSchemaPrecisionSpec] = DATA_SCHEMA_PRECISION_SPECS,
) -> dict[str, Any]:
    """Compare target MCP schemas with their explicit public-runtime contracts."""

    if tool_schemas is None:
        from bubble_mcp.server.schemas import list_tool_schemas

        tool_schemas = list_tool_schemas()
    if runtime_type is None:
        from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

        runtime_type = BubbleCLI

    schemas_by_name: dict[str, Mapping[str, Any]] = {}
    for schema in tool_schemas:
        name = schema.get("name")
        if isinstance(name, str) and name:
            schemas_by_name[name] = schema

    failures: list[dict[str, str]] = []
    runtime_property_count = alias_property_count = control_property_count = property_count = 0
    required_parameter_count = sum(len(spec.required) for spec in specs.values())

    for tool_name in sorted(specs):
        spec = specs[tool_name]
        schema = schemas_by_name.get(tool_name)
        if schema is None:
            failures.append(_failure(tool_name, "tool", "missing_tool", "Target tool is absent from the catalog."))
            continue
        handler = getattr(runtime_type, spec.handler, None)
        if handler is None or not callable(handler):
            failures.append(_failure(tool_name, "handler", "missing_handler", f"Runtime handler '{spec.handler}' is absent."))
            continue

        properties = _schema_properties(schema)
        property_count += len(properties)
        parameters = _runtime_parameters(handler)
        alias_by_public: dict[str, str] = {}
        for alias in spec.aliases:
            if alias.public_name in alias_by_public:
                failures.append(_failure(tool_name, alias.public_name, "duplicate_alias", "Public alias is declared more than once."))
            alias_by_public[alias.public_name] = alias.runtime_name
            if alias.runtime_name not in parameters:
                failures.append(_failure(tool_name, alias.public_name, "stale_alias", f"Alias runtime parameter '{alias.runtime_name}' is absent."))

        for runtime_name in spec.runtime:
            if runtime_name not in parameters:
                failures.append(_failure(tool_name, runtime_name, "stale_runtime_property", "Direct runtime parameter is absent."))

        for property_name in sorted(properties):
            if property_name in spec.runtime:
                runtime_property_count += 1
            elif property_name in alias_by_public:
                alias_property_count += 1
            elif property_name in spec.controls:
                control_property_count += 1
            else:
                failures.append(_failure(tool_name, property_name, "extra_property", "Published property has no runtime, alias, or control consumer."))

        expected_properties = set(spec.runtime) | set(alias_by_public) | set(spec.controls)
        for property_name in sorted(expected_properties - set(properties)):
            failures.append(_failure(tool_name, property_name, "missing_expected_property", "Expected public runtime, alias, or control property is absent from the schema."))

        expected_required = tuple(sorted(spec.required))
        actual_required = _schema_required(schema)
        if actual_required != expected_required:
            failures.append(_failure(tool_name, "required", "required_list_mismatch", f"Expected required {list(expected_required)!r}, found {list(actual_required)!r}."))

        expected_any_of = tuple(sorted(tuple(sorted(group)) for group in spec.any_of_required))
        actual_any_of = _schema_any_of_required(schema)
        if actual_any_of != expected_any_of:
            failures.append(_failure(tool_name, "anyOf", "any_of_mismatch", f"Expected anyOf required groups {list(expected_any_of)!r}, found {list(actual_any_of)!r}."))

        public_runtime_names = set(spec.runtime) | set(alias_by_public.values()) | set(spec.controls)
        for parameter_name, parameter in parameters.items():
            if parameter.default is not Parameter.empty or parameter_name in spec.controls:
                continue
            if parameter_name not in public_runtime_names:
                failures.append(_failure(tool_name, parameter_name, "missing_required_runtime_parameter", "Required runtime parameter has no public schema path."))

        failures.extend(_constraint_failures(tool_name, properties, spec.constraints))

    ordered_failures = sorted(failures, key=lambda failure: (failure["tool"], failure["field"], failure["code"]))
    return {
        "ok": not ordered_failures,
        "summary": {
            "tool_count": len(specs),
            "property_count": property_count,
            "runtime_property_count": runtime_property_count,
            "alias_property_count": alias_property_count,
            "control_property_count": control_property_count,
            "required_parameter_count": required_parameter_count,
            "failure_count": len(ordered_failures),
        },
        "failures": ordered_failures,
    }


def normalize_catalog_schema_precision_args(name: str, args: Mapping[str, Any]) -> dict[str, Any]:
    """Return an isolated copy; Task 5 adds A.3 alias and unknown-field checks."""

    del name
    return dict(args)
