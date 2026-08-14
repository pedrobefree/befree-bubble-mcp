"""Typed records and host callbacks shared by visual mutation services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

try:
    from ..bubble_sdk import PayloadBuilder
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import PayloadBuilder


@dataclass(frozen=True)
class VisualElementTarget:
    """Fully resolved existing element ready for a canonical editor write."""

    context_id: str
    context_type: str
    result: dict[str, Any]
    element_id: str
    element_type: str
    path: list[str]


@dataclass(frozen=True)
class VisualCreationTarget:
    """Resolved context and parent for a new visual element."""

    context_id: str
    context_type: str
    parent_result: dict[str, Any]
    parent_path: list[str]


class VisualMutationHost(Protocol):
    """Narrow BubbleCLI callbacks required by the mutation boundary."""

    appname: str
    discovery: Any

    def _find_context(self, name: str) -> tuple[str | None, str | None]: ...
    def _find_button_by_label(
        self,
        context_id: str,
        context_type: str,
        label: str,
    ) -> dict[str, Any] | None: ...
    def _find_element_by_ref(
        self,
        context_id: str,
        context_type: str,
        element_ref: str,
        *,
        ref_kind: str,
        match_index: int,
    ) -> dict[str, Any] | None: ...
    def _resolve_cached_element_alias(
        self,
        context_id: str,
        context_type: str,
        element_ref: str,
    ) -> dict[str, Any] | None: ...
    def _auto_sync_element_ref_aliases(self) -> bool: ...
    def _get_value_at_path(self, path: list[str]) -> Any: ...
    def _normalize_payload_path(self, path: Any) -> list[str]: ...
    def _normalize_capture_path(self, path: Any) -> list[str]: ...
    def _workflow_prefix(self, context_type: str) -> str: ...
    def _resolve_context_write_root_token(self, context_id: str, context_type: str) -> str: ...
    def _canonicalize_context_prefix_on_path(
        self,
        path: list[str],
        context_id: str,
        context_type: str,
    ) -> list[str]: ...
    def _find_last_element_token(
        self,
        path: list[str],
    ) -> tuple[int | None, str | None]: ...
    def _style_override_keys_for_element_type(
        self,
        element_type: str | None,
        *,
        target_style_id: str | None = None,
    ) -> list[str]: ...
    def _dispatch_payload(self, payload: PayloadBuilder) -> None: ...
    def _remove_cached_element_aliases(
        self,
        *,
        context_id: str,
        context_type: str,
        element_id: str | None = None,
        element_path: list[str] | None = None,
    ) -> None: ...
    def _cache_created_element_aliases(
        self,
        *,
        context_id: str,
        context_type: str,
        aliases: list[str],
        element_id: str,
        element_key: str | None = None,
        parent_path: list[str] | None = None,
        element_type: str | None = None,
    ) -> None: ...
