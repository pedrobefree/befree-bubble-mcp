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
