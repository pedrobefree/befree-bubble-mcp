"""Privacy-rule lifecycle operations with fresh schema binding resolution."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:
    from ..bubble_sdk import PayloadBuilder
else:
    try:
        from ..bubble_sdk import PayloadBuilder
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import PayloadBuilder

from .protocols import SchemaLifecycleHost
from .references import SchemaReferenceResolver


class _CurrentFieldResolutionError(ValueError):
    """A fresh-schema field lookup failed before a payload may be built."""


class PrivacyLifecycleService:
    """Build, dispatch, and atomically project Bubble privacy-rule mutations."""

    _SYSTEM_FIELDS = ("Created Date", "Modified Date", "Slug", "Created By")
    _PERMISSIONS = frozenset({"view_all", "view_attachments", "search_for", "auto_binding"})

    def __init__(self, host: SchemaLifecycleHost, references: SchemaReferenceResolver) -> None:
        self._host = host
        self._references = references

    def list_privacy_rules(self, data_type_key: str, dry_run: bool = False) -> list[dict[str, Any]]:
        rules = self._rules(data_type_key, include_cache=True)
        rows: list[dict[str, Any]] = []
        for rule_key, rule_payload in sorted(rules.items()):
            payload = rule_payload if isinstance(rule_payload, dict) else {}
            permissions = payload.get("permissions") if isinstance(payload.get("permissions"), dict) else {}
            rows.append({"data_type_key": data_type_key, "rule_key": rule_key, "name": payload.get("%d") or rule_key, "has_condition": "%c" in payload, "permissions": permissions})
        if dry_run:
            print(json.dumps({"ok": True, "data_type_key": data_type_key, "privacy_rules": rows}, indent=2))
        return rows

    def create_privacy_rule(
        self, data_type_key: str, rule_name: str = "New rule", rule_key: Optional[str] = None,
        view_all: bool = True, view_attachments: bool = True, search_for: bool = True, auto_binding: bool = False,
        view_fields: Optional[Any] = None, binding_fields: Optional[Any] = None, condition_json: Optional[Any] = None,
        include_everyone_default: bool = True, id_counter: Optional[int] = None, dry_run: bool = False,
    ) -> bool:
        parsed_id_counter = int(id_counter) if id_counter is not None else None
        parsed_auto_binding = self._parse_bool(auto_binding, "auto_binding")
        permissions: dict[str, Any] = {
            "view_all": self._parse_bool(view_all, "view_all"),
            "view_attachments": self._parse_bool(view_attachments, "view_attachments"),
            "search_for": self._parse_bool(search_for, "search_for"),
            "auto_binding": parsed_auto_binding,
        }
        resolved_type: str | None = None
        if view_fields is not None or binding_fields is not None:
            resolved_type = self._resolve_type_for_fields(data_type_key)
            if not resolved_type:
                return False
        try:
            if view_fields is not None:
                permissions["view_fields"] = self._field_list_payload(resolved_type or data_type_key, view_fields)
            if parsed_auto_binding:
                permissions["binding_fields"] = self._field_list_payload(resolved_type or data_type_key, binding_fields or [])
            elif binding_fields is not None:
                permissions["binding_fields"] = self._field_list_payload(resolved_type or data_type_key, binding_fields)
        except _CurrentFieldResolutionError:
            return False
        rule_payload: dict[str, Any] = {"%d": rule_name, "permissions": permissions}
        if condition_json is not None:
            rule_payload["%c"] = self._parse_json_value(condition_json, "condition_json")
        resolved_rule_key = rule_key or self._next_rule_key(data_type_key)
        add_default = self._parse_bool(include_everyone_default, "include_everyone_default") and not self._rules(data_type_key, include_cache=True)
        payload = self._payload()
        if add_default:
            self._change(payload, ["user_types", data_type_key, "privacy_role", "everyone"], self._default_everyone_rule(data_type_key))
        self._change(payload, ["user_types", data_type_key, "privacy_role", resolved_rule_key], rule_payload)
        if parsed_id_counter is not None:
            payload.add_change_raw({"type": "id_counter", "value": parsed_id_counter})
        return self._commit(payload, dry_run, f"Privacy rule '{resolved_rule_key}' created on '{data_type_key}'.", data_type_key, resolved_rule_key, rule_payload)

    def delete_privacy_rule(self, data_type_key: str, rule_key: str, dry_run: bool = False) -> bool:
        payload = self._payload()
        self._change(payload, ["user_types", data_type_key, "privacy_role", rule_key], None)
        return self._commit(payload, dry_run, f"Privacy rule '{rule_key}' deleted from '{data_type_key}'.", data_type_key, rule_key, None)

    def set_privacy_rule_name(self, data_type_key: str, rule_key: str, new_name: str, dry_run: bool = False) -> bool:
        return self._set_path(data_type_key, rule_key, ["%d"], new_name, dry_run, f"Privacy rule '{rule_key}' renamed to '{new_name}'.")

    def set_privacy_rule_condition(self, data_type_key: str, rule_key: str, condition_json: Any, dry_run: bool = False) -> bool:
        return self._set_path(data_type_key, rule_key, ["%c"], self._parse_json_value(condition_json, "condition_json"), dry_run, f"Privacy rule '{rule_key}' condition updated.")

    def set_privacy_rule_permission(self, data_type_key: str, rule_key: str, permission: str, value: bool, dry_run: bool = False) -> bool:
        if permission not in self._PERMISSIONS:
            print(f"❌ Unsupported privacy permission '{permission}'. Expected one of: {', '.join(sorted(self._PERMISSIONS))}")
            return False
        parsed = self._parse_bool(value, "value")
        return self._set_path(data_type_key, rule_key, ["permissions", permission], parsed, dry_run, f"Privacy rule '{rule_key}' permission '{permission}' set to {parsed}.")

    def set_privacy_rule_field_visibility(
        self, data_type_key: str, rule_key: str, view_all: Optional[bool] = None, view_fields: Optional[Any] = None, dry_run: bool = False,
    ) -> bool:
        if view_all is None and view_fields is None:
            print("❌ Missing privacy field visibility change: pass view_all and/or view_fields.")
            return False
        parsed_view_all = self._parse_bool(view_all, "view_all") if view_all is not None else None
        resolved_type = self._resolve_type_for_fields(data_type_key)
        if not resolved_type:
            return False
        try:
            parsed_fields = self._field_list_payload(resolved_type, view_fields) if view_fields is not None else None
        except _CurrentFieldResolutionError:
            return False
        payload = self._payload()
        if parsed_view_all is not None:
            self._change(payload, ["user_types", resolved_type, "privacy_role", rule_key, "permissions", "view_all"], parsed_view_all)
        if parsed_fields is not None:
            self._change(payload, ["user_types", resolved_type, "privacy_role", rule_key, "permissions", "view_fields"], parsed_fields)
        return self._commit_paths(payload, dry_run, f"Privacy rule '{rule_key}' field visibility updated.", resolved_type, rule_key, [(["permissions", "view_all"], parsed_view_all)] * (parsed_view_all is not None) + [(["permissions", "view_fields"], parsed_fields)] * (parsed_fields is not None))

    def set_privacy_rule_auto_binding(
        self, data_type_key: str, rule_key: str, auto_binding: bool, binding_fields: Optional[Any] = None, dry_run: bool = False,
    ) -> bool:
        parsed_auto_binding = self._parse_bool(auto_binding, "auto_binding")
        resolved_type = self._resolve_type_for_fields(data_type_key)
        if not resolved_type:
            return False
        try:
            binding_body = self._field_list_payload(resolved_type, binding_fields or []) if parsed_auto_binding else None
        except _CurrentFieldResolutionError:
            return False
        payload = self._payload()
        self._change(payload, ["user_types", resolved_type, "privacy_role", rule_key, "permissions", "auto_binding"], parsed_auto_binding)
        self._change(payload, ["user_types", resolved_type, "privacy_role", rule_key, "permissions", "binding_fields"], binding_body)
        return self._commit_paths(payload, dry_run, f"Privacy rule '{rule_key}' auto-binding updated.", resolved_type, rule_key, [(["permissions", "auto_binding"], parsed_auto_binding), (["permissions", "binding_fields"], binding_body)])

    def _set_path(self, data_type_key: str, rule_key: str, suffix: list[str], body: Any, dry_run: bool, message: str) -> bool:
        payload = self._payload()
        self._change(payload, ["user_types", data_type_key, "privacy_role", rule_key, *suffix], body)
        return self._commit_paths(payload, dry_run, message, data_type_key, rule_key, [(suffix, body)])

    def _payload(self) -> PayloadBuilder:
        return cast(PayloadBuilder, self._host.new_schema_lifecycle_payload())

    def _change(self, payload: PayloadBuilder, path: list[str], body: Any) -> None:
        self._host.add_schema_lifecycle_change(payload, "ChangeAppSetting", path, body)

    def _commit(self, payload: PayloadBuilder, dry_run: bool, message: str, data_type_key: str, rule_key: str, rule_payload: dict[str, Any] | None) -> bool:
        return self._commit_paths(payload, dry_run, message, data_type_key, rule_key, [(None, rule_payload)])

    def _commit_paths(self, payload: PayloadBuilder, dry_run: bool, message: str, data_type_key: str, rule_key: str, updates: list[tuple[list[str] | None, Any]]) -> bool:
        if dry_run:
            self._host.preview_schema_lifecycle_payload(payload)
            return True
        try:
            self._host.dispatch_schema_lifecycle_payload(payload)
        except Exception as exc:
            self._host.log_schema_lifecycle_error(f"Failed to send: {exc}")
            return False
        entry = self._current_entry(data_type_key)
        raw_rules = entry.get("privacy_role")
        rules: dict[str, Any] = copy.deepcopy(raw_rules) if isinstance(raw_rules, dict) else {}
        for suffix, body in updates:
            if suffix is None:
                if body is None:
                    rules.pop(rule_key, None)
                else:
                    rules[rule_key] = copy.deepcopy(body)
                continue
            current_rule = rules.get(rule_key)
            rule: dict[str, Any] = copy.deepcopy(current_rule) if isinstance(current_rule, dict) else {}
            cursor = rule
            for token in suffix[:-1]:
                nested = cursor.get(token)
                if not isinstance(nested, dict):
                    nested = {}
                    cursor[token] = nested
                cursor = nested
            cursor[suffix[-1]] = copy.deepcopy(body)
            rules[rule_key] = rule
        entry["privacy_role"] = rules
        warning = self._host.project_schema_data_type(data_type_key, entry)
        if warning:
            self._host.log_schema_lifecycle_error(warning)
        self._host.log_schema_lifecycle_success(message)
        return True

    def _resolve_type_for_fields(self, data_type_key: str) -> str | None:
        discovery, _cache = self._host.schema_reference_snapshots()
        current = discovery.get("user_types") if isinstance(discovery, dict) else None
        if not isinstance(current, dict) or not current:
            self._host.log_schema_lifecycle_error(f"Could not resolve current data type '{data_type_key}': no fresh user_types metadata available.")
            return None
        resolved = self._references.resolve_data_type(data_type_key, ref_kind="auto", include_cache=False)
        if not resolved or resolved not in current:
            self._host.log_schema_lifecycle_error(f"Could not resolve current data type '{data_type_key}'.")
            return None
        return resolved

    def _field_list_payload(self, data_type_key: str, fields: Any) -> dict[str, str] | None:
        values = self._parse_field_values(fields)
        resolved: list[str] = []
        for value in values:
            if value in self._SYSTEM_FIELDS:
                resolved.append(value)
                continue
            field_key = self._references.resolve_data_field(data_type_key, value, ref_kind="auto", include_cache=False)
            if not field_key:
                self._host.log_schema_lifecycle_error(f"Could not resolve current field '{value}' on data type '{data_type_key}'.")
                raise _CurrentFieldResolutionError(f"Could not resolve current field '{value}' on data type '{data_type_key}'.")
            resolved.append(field_key)
        return {str(index): value for index, value in enumerate(resolved)}

    def _current_entry(self, data_type_key: str) -> dict[str, Any]:
        entries = self._references.user_types(include_cache=False)
        entry = entries.get(data_type_key)
        return copy.deepcopy(entry) if isinstance(entry, dict) else {}

    def _rules(self, data_type_key: str, *, include_cache: bool) -> dict[str, Any]:
        entry = self._references.user_types(include_cache=include_cache).get(data_type_key)
        raw_rules = entry.get("privacy_role") if isinstance(entry, dict) else None
        return copy.deepcopy(raw_rules) if isinstance(raw_rules, dict) else {}

    def _next_rule_key(self, data_type_key: str) -> str:
        rules = self._rules(data_type_key, include_cache=True)
        if "new_rule_" not in rules:
            return "new_rule_"
        index = 1
        while f"new_rule_{index}" in rules:
            index += 1
        return f"new_rule_{index}"

    def _default_everyone_rule(self, data_type_key: str) -> dict[str, Any]:
        entry = self._references.user_types(include_cache=True).get(data_type_key)
        raw_fields = entry.get("%f3") if isinstance(entry, dict) else None
        fields: dict[str, Any] = raw_fields if isinstance(raw_fields, dict) else {}
        field_keys = [str(key) for key in fields]
        field_keys.extend(field for field in self._SYSTEM_FIELDS if field not in field_keys)
        return {"%d": "everyone", "permissions": {"view_all": False, "view_attachments": False, "search_for": False, "auto_binding": False, "non_filterable_fields": {field: True for field in field_keys}}}

    @staticmethod
    def _parse_field_values(fields: Any) -> list[str]:
        if fields is None:
            return []
        if isinstance(fields, str):
            stripped = fields.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError("fields JSON must be an array.")
                return [str(item) for item in parsed]
            return [part.strip() for part in stripped.split(",") if part.strip()]
        if isinstance(fields, dict):
            return [str(fields[key]) for key in sorted(fields, key=lambda item: (0, int(str(item))) if str(item).isdigit() else (1, str(item)))]
        if isinstance(fields, list):
            return [str(item) for item in fields]
        raise ValueError("fields must be a comma-separated string, JSON array, or object.")

    @staticmethod
    def _parse_bool(value: Any, label: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value)
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "enable", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disable", "disabled"}:
            return False
        raise ValueError(f"Invalid boolean value for {label}: {value!r}")

    @staticmethod
    def _parse_json_value(value: Any, label: str) -> Any:
        if not isinstance(value, str):
            return value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid {label}.") from exc
        if parsed is None:
            raise ValueError(f"Invalid {label}.")
        return parsed
