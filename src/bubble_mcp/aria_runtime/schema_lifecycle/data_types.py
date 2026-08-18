"""Data type and field lifecycle operations with current-first references."""

from __future__ import annotations

import copy
import random
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


class DataTypeLifecycleService:
    """Build and commit Bubble data-schema mutations through one narrow host."""

    _PRIMITIVE_TYPES = frozenset(
        {
            "text", "number", "date", "boolean", "yes/no", "yes_no", "image", "file",
            "geographic address", "geographic_address", "user", "any", "null",
        }
    )

    def __init__(self, host: SchemaLifecycleHost, references: SchemaReferenceResolver) -> None:
        self._host = host
        self._references = references

    def create_data_type(self, name: str, key: str | None = None, private: bool = False, dry_run: bool = False) -> bool:
        data_type_key = key or self._slugify(name)
        if not data_type_key:
            self._host.log_schema_lifecycle_error("Data type name must produce a non-empty key.")
            return False
        entry: dict[str, Any] = {"%d": name}
        payload = self._payload()
        if private:
            privacy_role, everyone_role, creator_role, creator_rule = self._private_roles()
            entry["privacy_role"] = privacy_role
            self._change(payload, "WriteCustom", ["user_types", data_type_key], entry)
            self._change(payload, "ChangeAppSetting", ["user_types", data_type_key, "privacy_role", "everyone"], everyone_role, intent_id=random.randint(1, 999999), source_appname="")
            self._change(payload, "ChangeAppSetting", ["user_types", data_type_key, "privacy_role", "visible_to_creator_"], creator_role, intent_id=random.randint(1, 999999), source_appname="")
            self._change(payload, "ChangeAppSetting", ["user_types", data_type_key, "privacy_role", "visible_to_creator_", "%c"], creator_rule, intent_id=random.randint(1, 999999), source_appname="")
        else:
            self._change(payload, "WriteCustom", ["user_types", data_type_key], entry)
        return self._commit(payload, dry_run, f"Data type '{name}' created ({data_type_key}).", data_type_key, entry)

    def rename_data_type(self, data_type_key: str, new_name: str, dry_run: bool = False) -> bool:
        resolved = self._resolve_type_for_write(data_type_key)
        if not resolved:
            return False
        entry = self._entry(resolved)
        entry["%d"] = new_name
        payload = self._payload()
        self._change(payload, "WriteCustom", ["user_types", resolved, "%d"], new_name)
        return self._commit(payload, dry_run, f"Data type '{resolved}' renamed to '{new_name}'.", resolved, entry)

    def delete_data_type(self, data_type_key: str, dry_run: bool = False) -> bool:
        resolved = self._resolve_type_for_write(data_type_key)
        if not resolved:
            return False
        entry = self._entry(resolved)
        entry["%del"] = True
        payload = self._payload()
        self._change(payload, "WriteCustom", ["user_types", resolved, "%del"], True)
        return self._commit(payload, dry_run, f"Data type '{resolved}' deleted.", resolved, entry)

    def delete_data_type_permanently(
        self, data_type_key: str, data_type_ref_kind: str = "auto", confirm: bool = False, dry_run: bool = False
    ) -> bool:
        ref_kind = (data_type_ref_kind or "auto").strip().lower()
        if ref_kind not in {"auto", "id", "key"}:
            self._host.log_schema_lifecycle_error("Permanent data type deletion requires the exact internal data type key.")
            return False
        resolved = str(data_type_key or "").strip()
        if resolved.lower().startswith("custom."):
            resolved = resolved.split(".", 1)[1].strip()
        if not resolved:
            self._host.log_schema_lifecycle_error("Permanent data type deletion requires the exact internal data type key.")
            return False
        if not self._is_soft_deleted(resolved, require_fresh_schema=not dry_run):
            self._host.log_schema_lifecycle_error(
                f"Data type '{resolved}' must be soft-deleted with delete_data_type before permanent deletion."
            )
            return False
        if not dry_run and confirm is not True:
            self._host.log_schema_lifecycle_error("Permanent data type deletion requires confirm=true.")
            return False
        payload = self._payload(include_app_version=True)
        self._change(payload, "CleanApp", ["user_types", resolved], None)
        return self._commit(payload, dry_run, f"Data type '{resolved}' permanently deleted.", resolved, None)

    def create_data_field(
        self, data_type_key: str, field_name: str, field_type: str, field_key: str | None = None, dry_run: bool = False
    ) -> bool:
        resolved_type = self._resolve_type_for_write(data_type_key)
        resolved_value_type = self._resolve_field_type(field_type)
        if not resolved_type or not resolved_value_type:
            return False
        field_name_key = self._slugify(field_name)
        resolved_field_key = field_key or f"{field_name_key}_{self._slugify(field_type.replace('.', '_'))}"
        if not field_name_key and not field_key:
            self._host.log_schema_lifecycle_error("Data field name must produce a non-empty key.")
            return False
        if not resolved_field_key:
            self._host.log_schema_lifecycle_error("Data field name must produce a non-empty key.")
            return False
        entry = self._entry(resolved_type)
        fields = self._fields(entry)
        fields[resolved_field_key] = {"%d": field_name, "%v": resolved_value_type}
        entry["%f3"] = fields
        payload = self._payload()
        self._change(payload, "WriteCustomField", ["user_types", resolved_type, "%f3", resolved_field_key], fields[resolved_field_key])
        return self._commit(payload, dry_run, f"Field '{field_name}' created on '{resolved_type}' ({resolved_field_key}).", resolved_type, entry)

    def rename_data_field(self, data_type_key: str, field_key: str, new_name: str, dry_run: bool = False) -> bool:
        resolved_type, resolved_field = self._resolve_field_for_write(data_type_key, field_key)
        if not resolved_type or not resolved_field:
            return False
        entry = self._entry(resolved_type)
        fields = self._fields(entry)
        stored_field = fields.get(resolved_field)
        field = copy.deepcopy(stored_field) if isinstance(stored_field, dict) else {}
        field["%d"] = new_name
        fields[resolved_field] = field
        entry["%f3"] = fields
        payload = self._payload()
        self._change(payload, "WriteCustomField", ["user_types", resolved_type, "%f3", resolved_field, "%d"], new_name)
        return self._commit(payload, dry_run, f"Field '{resolved_field}' on '{resolved_type}' renamed to '{new_name}'.", resolved_type, entry)

    def delete_data_field(self, data_type_key: str, field_key: str, dry_run: bool = False) -> bool:
        resolved_type, resolved_field = self._resolve_field_for_write(data_type_key, field_key)
        if not resolved_type or not resolved_field:
            return False
        entry = self._entry(resolved_type)
        fields = self._fields(entry)
        stored_field = fields.get(resolved_field)
        field = copy.deepcopy(stored_field) if isinstance(stored_field, dict) else {}
        deleted_label = f"{str(field.get('%d') or resolved_field).strip() or resolved_field} - deleted"
        field["%del"] = True
        field["%d"] = deleted_label
        fields[resolved_field] = field
        entry["%f3"] = fields
        payload = self._payload()
        self._change(payload, "WriteCustomField", ["user_types", resolved_type, "%f3", resolved_field, "%del"], True)
        self._change(payload, "WriteCustomField", ["user_types", resolved_type, "%f3", resolved_field, "%d"], deleted_label)
        return self._commit(payload, dry_run, f"Field '{resolved_field}' on '{resolved_type}' deleted.", resolved_type, entry)

    def set_data_type_api_exposure(
        self, data_type_ref: str, enabled: bool, ref_kind: str = "key", dry_run: bool = False
    ) -> bool:
        resolved = self._resolve_type_for_write(data_type_ref, ref_kind=ref_kind)
        if not resolved:
            known = sorted(self._references.user_types(include_cache=False).keys())
            if known:
                self._host.log_schema_lifecycle_error(
                    f"Could not resolve data type '{data_type_ref}' by {ref_kind}. Known keys: {', '.join(known[:12])}"
                    + ("..." if len(known) > 12 else "")
                )
            else:
                self._host.log_schema_lifecycle_error(
                    f"Could not resolve data type '{data_type_ref}': no user_types metadata available. Run scan-types first or use a known key."
                )
            return False
        entry = self._entry(resolved)
        entry["exposed_api"] = bool(enabled)
        payload = self._payload()
        self._change(payload, "WriteCustom", ["user_types", resolved, "exposed_api"], bool(enabled))
        return self._commit(payload, dry_run, f"Data API exposure for data type '{resolved}' set to {bool(enabled)}.", resolved, entry)

    def _resolve_type_for_write(self, value: str, *, ref_kind: str = "auto") -> str | None:
        discovery, _cache = self._host.schema_reference_snapshots()
        current = discovery.get("user_types") if isinstance(discovery, dict) else None
        raw = str(value or "").strip()
        if not isinstance(current, dict) or not current:
            self._host.log_schema_lifecycle_error(
                f"Could not resolve current data type '{value}': no fresh user_types metadata available."
            )
            return None
        resolved = self._references.resolve_data_type(raw, ref_kind=ref_kind, include_cache=False)
        if not resolved or resolved not in current:
            self._host.log_schema_lifecycle_error(f"Could not resolve current data type '{value}'.")
            return None
        return resolved

    def _resolve_field_for_write(self, data_type_ref: str, field_ref: str) -> tuple[str | None, str | None]:
        resolved_type = self._resolve_type_for_write(data_type_ref)
        if not resolved_type:
            return None, None
        resolved_field = self._references.resolve_data_field(resolved_type, field_ref, ref_kind="auto", include_cache=False)
        if not resolved_field:
            self._host.log_schema_lifecycle_error(f"Could not resolve current field '{field_ref}' on data type '{data_type_ref}'.")
            return None, None
        return resolved_type, resolved_field

    def _resolve_field_type(self, value: str) -> str | None:
        raw = str(value or "").strip()
        list_prefix = ""
        if raw.lower().startswith("list."):
            list_prefix, raw = "list.", raw[5:].strip()
        normalized = raw.lower().replace("_", " ")
        if normalized in self._PRIMITIVE_TYPES:
            return f"{list_prefix}{raw}"
        if raw.lower().startswith("custom."):
            key = self._references.resolve_data_type(raw.split(".", 1)[1], ref_kind="auto", include_cache=False)
            if key:
                return f"{list_prefix}{'user' if key == 'user' else f'custom.{self._slugify(key)}'}"
        elif raw.lower().startswith("option."):
            option_ref = raw.split(".", 1)[1]
            if option_ref.lower().startswith("os:"):
                option_ref = option_ref.split(":", 1)[1]
            key = self._references.resolve_option_set(option_ref, ref_kind="auto", include_cache=False)
            if key:
                return f"{list_prefix}option.{key}"
        self._host.log_schema_lifecycle_error(f"Could not resolve current field type '{value}'.")
        return None

    def _entry(self, key: str) -> dict[str, Any]:
        entry = self._references.user_types(include_cache=False).get(key)
        return copy.deepcopy(entry) if isinstance(entry, dict) else {}

    @staticmethod
    def _fields(entry: dict[str, Any]) -> dict[str, Any]:
        fields = entry.get("%f3")
        return copy.deepcopy(fields) if isinstance(fields, dict) else {}

    def _payload(self, *, include_app_version: bool = False) -> PayloadBuilder:
        return cast(PayloadBuilder, self._host.new_schema_lifecycle_payload(include_app_version=include_app_version))

    def _change(self, payload: PayloadBuilder, intent_name: str, path: list[str], body: Any, **kwargs: Any) -> None:
        self._host.add_schema_lifecycle_change(payload, intent_name, path, body, **kwargs)

    def _commit(self, payload: PayloadBuilder, dry_run: bool, message: str, key: str, entry: dict[str, Any] | None) -> bool:
        if dry_run:
            self._host.preview_schema_lifecycle_payload(payload)
            return True
        try:
            self._host.dispatch_schema_lifecycle_payload(payload)
        except Exception as exc:
            self._host.log_schema_lifecycle_error(f"Failed to send: {exc}")
            return False
        warning = self._host.project_schema_data_type(key, entry)
        if warning:
            self._host.log_schema_lifecycle_error(warning)
        self._host.log_schema_lifecycle_success(message)
        return True

    def _slugify(self, value: str) -> str:
        return self._host.slugify_schema_reference(value)

    def _is_soft_deleted(self, key: str, *, require_fresh_schema: bool) -> bool:
        checker = getattr(self._host, "_data_type_is_soft_deleted", None)
        return bool(checker(key, require_fresh_schema=require_fresh_schema)) if callable(checker) else False

    @staticmethod
    def _private_roles() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        everyone = {"%d": "everyone", "permissions": {"view_all": False, "view_attachments": False, "search_for": False, "auto_binding": False}}
        creator_rule = {"%x": "InjectedValue", "%n": {"%x": "Message", "%nm": "Created By", "%n": {"%x": "Message", "%nm": "equals", "%a": {"%x": "CurrentUser"}}}}
        creator = {"%d": "Visible to creator", "permissions": {"view_all": True, "view_attachments": True, "search_for": True, "auto_binding": False}, "%c": creator_rule}
        return {"everyone": everyone, "visible_to_creator_": creator}, everyone, creator, creator_rule
