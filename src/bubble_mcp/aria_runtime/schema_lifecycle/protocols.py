"""Typed host callbacks for schema lifecycle services."""

from __future__ import annotations

from typing import Any, Protocol


class SchemaReferenceHost(Protocol):
    """Detached snapshots and normalization callbacks used by schema reads."""

    def schema_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def schema_reference_revision(self) -> int: ...

    def schema_reference_modules_dir(self) -> str | None: ...

    def schema_reference_profile_key(self) -> str: ...

    def normalize_schema_reference(self, value: Any) -> str: ...

    def slugify_schema_reference(self, value: str) -> str: ...


class SchemaLifecycleHost(SchemaReferenceHost, Protocol):
    """Composition-root boundary for the schema lifecycle service."""

    appname: str
    app_version: str

    def new_schema_lifecycle_payload(self, *, include_app_version: bool = False) -> Any: ...

    def add_schema_lifecycle_change(
        self,
        payload: Any,
        intent_name: str,
        path_array: list[str],
        body: Any,
        *,
        intent_id: int | None = None,
        source_appname: str | None = None,
    ) -> None: ...

    def dispatch_schema_lifecycle_payload(self, payload: Any) -> None: ...

    def preview_schema_lifecycle_payload(self, payload: Any) -> None: ...

    def project_schema_data_type(self, key: str, entry: dict[str, Any] | None) -> str | None: ...

    def project_schema_option_set(self, key: str, entry: dict[str, Any] | None) -> str | None: ...

    def next_schema_option_value_key(self) -> str: ...

    def coerce_schema_option_value(self, value: Any, *, parse_json: bool = False) -> Any: ...

    def log_schema_lifecycle_success(self, message: str) -> None: ...

    def log_schema_lifecycle_error(self, message: str) -> None: ...
