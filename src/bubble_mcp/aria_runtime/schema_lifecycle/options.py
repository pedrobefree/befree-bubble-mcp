"""Option set and value lifecycle operations with current-first references."""

from __future__ import annotations

import copy
import json
import re
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ..bubble_sdk import PayloadBuilder
else:
    try:
        from ..bubble_sdk import PayloadBuilder
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import PayloadBuilder

from .protocols import SchemaLifecycleHost
from .references import SchemaReferenceResolver


class OptionLifecycleService:
    """Build, dispatch, and atomically project option-schema mutations."""

    def __init__(self, host: SchemaLifecycleHost, references: SchemaReferenceResolver) -> None:
        self._host = host
        self._references = references

    def create_option_set(self, name: str, key: str | None = None, dry_run: bool = False) -> bool:
        normalized_name = name[3:] if str(name).startswith("OS:") else name
        option_set_key = key or f"os_{self._slugify(normalized_name)}"
        display_name = f"OS:{self._slugify(normalized_name)}"
        entry = {"%d": display_name, "creation_source": "editor", "attributes": {}, "values": {}}
        payload = self._payload()
        self._change(payload, "WriteOptionSet", ["option_sets", option_set_key], {"%d": display_name, "creation_source": "editor"})
        return self._commit(payload, dry_run, f"Option set '{display_name}' created ({option_set_key}).", option_set_key, entry)

    def rename_option_set(self, option_set_ref: str, new_name: str, dry_run: bool = False) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        normalized_name = new_name[3:] if str(new_name).startswith("OS:") else new_name
        display_name = f"OS:{self._slugify(normalized_name)}"
        entry["%d"] = display_name
        payload = self._payload()
        self._change(payload, "WriteOptionSet", ["option_sets", option_key, "%d"], display_name)
        return self._commit(payload, dry_run, f"Option set '{option_key}' renamed to '{display_name}'.", option_key, entry)

    def delete_option_set(self, option_set_ref: str, dry_run: bool = False) -> bool:
        option_key, _entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        payload = self._payload()
        self._change(payload, "WriteOptionSet", ["option_sets", option_key, "%del"], True)
        return self._commit(payload, dry_run, f"Option set '{option_key}' deleted.", option_key, None)

    def create_option_attribute(
        self, option_set_ref: str, name: str, value_type: str, attribute_key: str | None = None, dry_run: bool = False
    ) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        resolved_attribute_key = attribute_key or self._slugify(name)
        attributes = self._attributes(entry)
        attribute = {"%d": name, "%v": value_type, "creation_source": "editor"}
        attributes[resolved_attribute_key] = attribute
        entry["attributes"] = attributes
        entry.setdefault("values", {})
        payload = self._payload()
        self._change(payload, "WriteOptionAttribute", ["option_sets", option_key, "attributes", resolved_attribute_key], attribute)
        return self._commit(payload, dry_run, f"Attribute '{name}' created on option set '{option_key}' ({resolved_attribute_key}).", option_key, entry)

    def create_option_value(
        self,
        option_set_ref: str,
        label: str,
        value_key: str | None = None,
        db_value: str | None = None,
        sort_factor: int | None = None,
        id_counter: int | None = None,
        dry_run: bool = False,
    ) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        resolved_value_key = value_key or self._host.next_schema_option_value_key()
        values = self._values(entry)
        existing_entry = values.get(resolved_value_key)
        existing = copy.deepcopy(existing_entry) if isinstance(existing_entry, dict) else None
        existing_db_value = existing.get("db_value") if existing else None
        existing_sort_factor = existing.get("sort_factor") if existing else None
        resolved_db_value = db_value if db_value is not None else (existing_db_value if existing_db_value is not None else self._slugify(label))
        resolved_sort_factor = sort_factor if sort_factor is not None else (existing_sort_factor if isinstance(existing_sort_factor, int) else 1)
        safe_patch_existing = value_key is not None and existing is None
        projected = copy.deepcopy(existing) if existing else {}
        projected["%d"] = label
        if not safe_patch_existing or db_value is not None:
            projected["db_value"] = resolved_db_value
        if not safe_patch_existing or sort_factor is not None:
            projected["sort_factor"] = resolved_sort_factor
        values[resolved_value_key] = projected
        entry["values"] = values
        entry.setdefault("attributes", {})

        payload = self._payload()
        if safe_patch_existing:
            self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", resolved_value_key, "%d"], label)
            if db_value is not None:
                self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", resolved_value_key, "db_value"], resolved_db_value)
            if sort_factor is not None:
                self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", resolved_value_key, "sort_factor"], resolved_sort_factor)
        else:
            self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", resolved_value_key], projected)
        if id_counter is not None:
            payload.add_change_raw({"type": "id_counter", "value": int(id_counter)})
        ok = self._commit(payload, dry_run, f"Option '{label}' created in '{option_key}' ({resolved_value_key}).", option_key, entry)
        if ok and not dry_run:
            self._host.log_schema_lifecycle_success(f"Option key: {resolved_value_key}")
        return ok

    def delete_option_value(self, option_set_ref: str, value_ref: str, ref_kind: str = "key", dry_run: bool = False) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        value_key = self._resolve_value_for_write(option_key, value_ref, ref_kind)
        if not value_key:
            return False
        values = self._values(entry)
        values.pop(value_key, None)
        entry["values"] = values
        payload = self._payload()
        self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", value_key, "%del"], True)
        return self._commit(payload, dry_run, f"Option '{value_key}' deleted from '{option_key}'.", option_key, entry)

    def rename_option_value(
        self, option_set_ref: str, value_ref: str, new_label: str, ref_kind: str = "key", dry_run: bool = False
    ) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        value_key = self._resolve_value_for_write(option_key, value_ref, ref_kind)
        if not value_key:
            return False
        values = self._values(entry)
        existing_value = values.get(value_key)
        value: dict[str, Any] = copy.deepcopy(existing_value) if isinstance(existing_value, dict) else {}
        value["%d"] = new_label
        values[value_key] = value
        entry["values"] = values
        payload = self._payload()
        self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", value_key, "%d"], new_label)
        return self._commit(payload, dry_run, f"Option '{value_key}' in '{option_key}' renamed to '{new_label}'.", option_key, entry)

    def set_option_value_attribute(
        self, option_set_ref: str, value_ref: str, attribute_key: str, value: Any, ref_kind: str = "key",
        parse_json: bool = False, dry_run: bool = False,
    ) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        value_key = self._resolve_value_for_write(option_key, value_ref, ref_kind)
        if not value_key:
            return False
        coerced_value = self._host.coerce_schema_option_value(value, parse_json=parse_json)
        values = self._values(entry)
        existing_value = values.get(value_key)
        option_value: dict[str, Any] = copy.deepcopy(existing_value) if isinstance(existing_value, dict) else {}
        option_value[attribute_key] = coerced_value
        values[value_key] = option_value
        entry["values"] = values
        payload = self._payload()
        self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", value_key, attribute_key], coerced_value)
        return self._commit(payload, dry_run, f"Attribute '{attribute_key}' updated for option '{value_key}' in '{option_key}'.", option_key, entry)

    def reorder_option_values(self, option_set_ref: str, assignments: list[str], ref_kind: str = "key", dry_run: bool = False) -> bool:
        option_key, entry = self._option_set_for_write(option_set_ref)
        if not option_key:
            return False
        if not assignments:
            self._host.log_schema_lifecycle_error("No assignments provided. Use value_key:sort_factor pairs.")
            return False
        values = self._values(entry)
        expected_keys = {key for key, value in values.items() if isinstance(value, dict) and value.get("%del") is not True}
        resolved: list[tuple[str, int]] = []
        for raw in assignments:
            token = str(raw).strip()
            if ":" in token:
                value_ref, sort_raw = token.rsplit(":", 1)
            elif "=" in token:
                value_ref, sort_raw = token.rsplit("=", 1)
            else:
                self._host.log_schema_lifecycle_error(f"Invalid assignment '{token}'. Expected value_key:sort_factor.")
                return False
            if not value_ref.strip() or not re.fullmatch(r"-?\d+", sort_raw.strip()):
                self._host.log_schema_lifecycle_error(f"Invalid assignment '{token}'.")
                return False
            value_key = self._resolve_value_for_write(option_key, value_ref.strip(), ref_kind)
            if not value_key:
                return False
            resolved.append((value_key, int(sort_raw.strip())))
        resolved_keys = [key for key, _factor in resolved]
        factors = [factor for _key, factor in resolved]
        if len(resolved_keys) != len(set(resolved_keys)):
            self._host.log_schema_lifecycle_error("Option value reorder assignments must not repeat a value.")
            return False
        if set(resolved_keys) != expected_keys or len(resolved_keys) != len(expected_keys):
            self._host.log_schema_lifecycle_error("Option value reorder assignments must include every current value exactly once.")
            return False
        if set(factors) != set(range(1, len(expected_keys) + 1)) or len(factors) != len(set(factors)):
            self._host.log_schema_lifecycle_error("Option value reorder sort factors must be a complete unique permutation starting at 1.")
            return False
        projected = copy.deepcopy(entry)
        projected_values = self._values(projected)
        for value_key, factor in resolved:
            existing_value = projected_values.get(value_key)
            value: dict[str, Any] = copy.deepcopy(existing_value) if isinstance(existing_value, dict) else {}
            value["sort_factor"] = factor
            projected_values[value_key] = value
        projected["values"] = projected_values
        payload = self._payload()
        for value_key, factor in resolved:
            self._change(payload, "WriteOptionValue", ["option_sets", option_key, "values", value_key, "sort_factor"], factor)
        return self._commit(payload, dry_run, f"Option values reordered in '{option_key}'.", option_key, projected)

    def list_option_values(self, option_set_ref: str, as_json: bool = False) -> bool:
        option_key = self._references.resolve_option_set(option_set_ref, ref_kind="auto", include_cache=True)
        values = self._references.option_values(option_key or "", include_cache=True) if option_key else None
        if values is None:
            self._host.log_schema_lifecycle_error(f"Option set '{option_set_ref}' not found in discovery data or schema cache.")
            return False
        rows = [
            {"key": key, "label": data.get("%d", data.get("display", "")), "db_value": data.get("db_value", ""), "sort_factor": data.get("sort_factor", "")}
            for key, data in values.items() if isinstance(data, dict)
        ]
        rows.sort(key=lambda row: (self._sort_weight(row["sort_factor"]), str(row["label"]).lower()))
        if as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return True
        if not rows:
            self._host.log_schema_lifecycle_success(f"No values found for option set '{option_set_ref}'.")
            return True
        print(f"✅ Option values for '{option_set_ref}':")
        print(f"{'KEY':<10} | {'SORT':<5} | {'DB VALUE':<24} | LABEL")
        print("-" * 90)
        for row in rows:
            print(f"{str(row['key']):<10} | {str(row['sort_factor']):<5} | {str(row['db_value']):<24} | {str(row['label'])}")
        return True

    def _option_set_for_write(self, value: str) -> tuple[str | None, dict[str, Any]]:
        discovery, _cache = self._host.schema_reference_snapshots()
        current = discovery.get("option_sets") if isinstance(discovery, dict) else None
        if not isinstance(current, dict) or not current:
            self._host.log_schema_lifecycle_error(f"Could not resolve current option set '{value}': no fresh option_sets metadata available.")
            return None, {}
        key = self._references.resolve_option_set(value, ref_kind="auto", include_cache=False)
        entry = current.get(key) if key else None
        if not key or not isinstance(entry, dict) or entry.get("%del") is True:
            self._host.log_schema_lifecycle_error(f"Could not resolve current option set '{value}'.")
            return None, {}
        return key, copy.deepcopy(entry)

    def _resolve_value_for_write(self, option_key: str, value: str, ref_kind: str) -> str | None:
        key = self._references.resolve_option_value(option_key, value, ref_kind=ref_kind, include_cache=False)
        if key:
            return key
        self._host.log_schema_lifecycle_error(
            f"Could not resolve option value '{value}' in '{option_key}' by {ref_kind}. Try --ref-kind db_value or --ref-kind label."
        )
        return None

    def _commit(self, payload: PayloadBuilder, dry_run: bool, message: str, key: str, entry: dict[str, Any] | None) -> bool:
        if dry_run:
            # PayloadBuilder sessions are intentionally random for real editor writes;
            # preview bytes must instead be stable for a fixed lifecycle plan.
            for change in payload.changes:
                if isinstance(change, dict):
                    change["session_id"] = "schema-lifecycle-preview"
            self._host.preview_schema_lifecycle_payload(payload)
            return True
        try:
            self._host.dispatch_schema_lifecycle_payload(payload)
        except Exception as exc:
            self._host.log_schema_lifecycle_error(f"Failed to send: {exc}")
            return False
        warning = self._host.project_schema_option_set(key, entry)
        if warning:
            self._host.log_schema_lifecycle_error(warning)
        self._host.log_schema_lifecycle_success(message)
        return True

    def _payload(self) -> PayloadBuilder:
        return cast(PayloadBuilder, self._host.new_schema_lifecycle_payload())

    def _change(self, payload: PayloadBuilder, intent_name: str, path: list[str], body: Any) -> None:
        self._host.add_schema_lifecycle_change(payload, intent_name, path, body)

    def _slugify(self, value: str) -> str:
        return self._host.slugify_schema_reference(value)

    @staticmethod
    def _attributes(entry: dict[str, Any]) -> dict[str, Any]:
        value = entry.get("attributes")
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    @staticmethod
    def _values(entry: dict[str, Any]) -> dict[str, Any]:
        value = entry.get("values")
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    @staticmethod
    def _sort_weight(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            return int(value.strip())
        return 10**9
