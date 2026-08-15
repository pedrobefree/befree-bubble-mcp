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
    def _lookup_cached_context_object_id(self, context_type: str, context_id: str) -> str: ...
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
    def _dispatch_payload(self, payload: PayloadBuilder) -> None: ...
    def _remove_cached_element_aliases(
        self,
        *,
        context_id: str,
        context_type: str,
        element_id: str | None = None,
        element_path: list[str] | None = None,
    ) -> None: ...
