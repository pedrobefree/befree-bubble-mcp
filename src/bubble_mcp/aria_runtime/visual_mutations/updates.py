"""Shared target, payload, style, preview, and dispatch flow for visual updates."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

try:
    from ..bubble_sdk import PayloadBuilder, logger
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import PayloadBuilder, logger

from .protocols import VisualElementTarget, VisualMutationHost
from .targets import VisualMutationTargets


class VisualUpdateService:
    """Apply prepared visual updates without owning element-specific semantics."""

    def __init__(self, host: VisualMutationHost, targets: VisualMutationTargets) -> None:
        self._host = host
        self._targets = targets

    def apply(
        self,
        context_name: str,
        element_name: str,
        *,
        prop_updates: dict[str, Any],
        style: str | None = None,
        clear_style_override_keys: list[str] | None = None,
        style_assign_props: dict[str, Any] | None = None,
        force_style_assign: bool = False,
        style_assign_with_set_data: bool = True,
        direct_updates: Iterable[tuple[list[str], Any]] | None = None,
        resolved_target: VisualElementTarget | None = None,
        dry_run: bool = False,
        prefer_last: bool = False,
        success_label: str = "element",
        success_message: str | None = None,
    ) -> bool:
        target = resolved_target or self._targets.resolve_existing(
            context_name,
            element_name,
            prefer_last=prefer_last,
        )
        if target is None:
            return False

        path = target.path
        payload = PayloadBuilder(appname=self._host.appname)
        element_obj = target.result.get("element", {})
        if not isinstance(element_obj, dict):
            element_obj = {}
        element_type = str(element_obj.get("%x") or element_obj.get("type") or "").strip() or None

        if style is not None:
            raw_style = str(style).strip()
            if self._host._looks_like_style_id(raw_style, element_type=element_type):
                resolved_style = raw_style
            else:
                resolved_style = self._host._resolve_style_reference(
                    raw_style,
                    element_type=element_type,
                    strict=False,
                )
            if resolved_style is None:
                return False

            if not element_type:
                element_type = self._host._infer_element_type_from_style_id(resolved_style)

            effective_clear_keys = clear_style_override_keys
            if effective_clear_keys is None and style_assign_props is None:
                effective_clear_keys = self._host._style_override_keys_for_element_type(
                    element_type,
                    target_style_id=resolved_style,
                )
            if effective_clear_keys:
                for key in effective_clear_keys:
                    key_str = str(key)
                    if key_str not in prop_updates:
                        payload.add_set_data(path + ["%p", key_str], None)
            self._host._queue_clear_style_marker_props(
                payload,
                path,
                prop_updates=prop_updates,
            )

            if force_style_assign or style_assign_props is not None:
                self._host._queue_style_assignment_changes(
                    payload,
                    path,
                    resolved_style,
                    style_props=style_assign_props,
                    include_set_data=style_assign_with_set_data,
                )
            else:
                payload.add_set_data(path + ["%s1"], resolved_style)

        for suffix, value in direct_updates or ():
            payload.add_set_data(path + list(suffix), value)
        for key, value in prop_updates.items():
            if value is not None:
                payload.add_set_data(path + ["%p", key], value)

        if not payload.changes:
            logger.warning("No update fields were provided.")
            return True
        if dry_run:
            logger.info("\n DRY RUN - Payload preview:")
            logger.log(payload.to_json())
            return True

        try:
            self._host._dispatch_payload(payload)
            logger.success(
                success_message
                or f"Successfully updated {success_label}: '{element_name}'"
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to send: {exc}")
            return False
