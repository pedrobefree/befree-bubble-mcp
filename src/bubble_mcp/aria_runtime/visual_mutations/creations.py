"""Shared preparation, payload sequencing, and finalization for visual creation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

try:
    from ..bubble_sdk import BubbleIDGenerator, PayloadBuilder, logger
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import BubbleIDGenerator, PayloadBuilder, logger

from .protocols import VisualCreationTarget, VisualMutationHost


class VisualCreationService:
    """Orchestrate visual creation while element builders stay on the host."""

    def __init__(self, host: VisualMutationHost) -> None:
        self._host = host

    def prepare(
        self,
        context_name: str,
        parent_name: str | None,
    ) -> VisualCreationTarget | None:
        logger.info(f"Searching for context: {context_name}")
        context_id, context_type = self._host._find_context(context_name)
        if not context_id or not context_type:
            logger.error(f"'{context_name}' not found")
            return None
        if parent_name:
            logger.info(f"Searching for parent: '{parent_name}'")
            parent_result = self.resolve_parent(
                context_id,
                context_type,
                context_name,
                parent_name,
            )
            if parent_result is None:
                return None
        else:
            logger.info(f"Adding to root of {context_name}")
            parent_result = {"path": [], "id": context_id}
        parent_path = self._host.discovery.build_path_array(
            context_id,
            list(parent_result.get("path") or []),
            context_type=context_type,
        )
        return VisualCreationTarget(
            context_id=context_id,
            context_type=context_type,
            parent_result=parent_result,
            parent_path=parent_path,
        )

    def resolve_parent(
        self,
        context_id: str,
        context_type: str,
        context_name: str,
        parent_name: str,
    ) -> dict[str, Any] | None:
        parent_ref = str(parent_name or "").strip()
        if not parent_ref:
            logger.error("Parent element is required.")
            return None
        if parent_ref == context_name or parent_ref.lower() == "root":
            return {"path": [], "id": context_id}
        if len(parent_ref) >= 5 and " " not in parent_ref:
            found = self._host.discovery.find_element_by_id(
                context_id,
                parent_ref,
                context_type=context_type,
            )
            if found:
                return found
        found = self._host.discovery.find_element_by_name(
            context_id,
            parent_ref,
            context_type=context_type,
        )
        if found:
            return found
        found = self._host._find_element_by_ref(
            context_id,
            context_type,
            parent_ref,
            ref_kind="auto",
            match_index=1,
        )
        if found:
            return found
        cached = self._host._resolve_cached_element_alias(context_id, context_type, parent_ref)
        if cached:
            return cached
        if self._host._auto_sync_element_ref_aliases():
            cached = self._host._resolve_cached_element_alias(context_id, context_type, parent_ref)
            if cached:
                return cached
        logger.error(f"Parent '{parent_ref}' not found in context {context_id}")
        return None

    def existing_child_ids(
        self,
        context_id: str,
        context_type: str,
        parent_result: dict[str, Any],
    ) -> list[str]:
        parent_node = parent_result.get("element")
        parent_id = parent_result.get("id")
        if not isinstance(parent_node, dict):
            if isinstance(parent_id, str) and parent_id and parent_id != context_id:
                return []
            try:
                parent_node = self._host.discovery._get_context_root(context_id, context_type)
            except Exception:
                parent_node = None
        if not isinstance(parent_node, dict):
            return []
        children = parent_node.get("elements")
        if not isinstance(children, dict):
            children = parent_node.get("%el")
        if not isinstance(children, dict):
            return []
        result: list[str] = []
        for key, child in children.items():
            if key == "length" or not isinstance(child, dict):
                continue
            child_id = child.get("id")
            if isinstance(child_id, str) and child_id:
                result.append(child_id)
        return result

    def queue_create(
        self,
        payload: PayloadBuilder,
        context_id: str,
        context_type: str,
        parent_result: dict[str, Any],
        create_path: list[str],
        create_body: dict[str, Any],
        full_path_str: str,
        name_value: str | None = None,
        text_content: Any = None,
        pending_child_ids_by_parent: dict[str, list[str]] | None = None,
    ) -> None:
        del full_path_str, name_value
        object_id = create_body.get("id")
        if not isinstance(object_id, str) or not object_id:
            raise ValueError("Create element body must include a valid 'id'.")
        props = create_body.get("%p")
        if isinstance(props, dict):
            props = {key: value for key, value in props.items() if value is not None}
            create_body["%p"] = props
            style_ref = create_body.get("%s1") or create_body.get("style") or props.get("%s1") or props.get("style")
            element_type = create_body.get("%x") or create_body.get("type")
            if style_ref and element_type:
                safe_keys = {"%3", "%nm", "%bl"}
                if str(element_type).strip().lower() == "dateinput":
                    safe_keys.update(
                        {
                            "%c1", "initial_content", "input_type", "binding_content_format",
                            "content_format", "date_format", "custom_format", "start_monday",
                            "show_month_year_picker", "time_format", "time_interval", "min_date",
                            "max_date", "min_hour", "max_hour", "%1m", "disabled", "auto_binding",
                            "bind_field",
                        }
                    )
                for key in self._host._style_override_keys_for_element_type(
                    str(element_type),
                    target_style_id=str(style_ref),
                ):
                    if key not in safe_keys:
                        props.pop(str(key), None)

        normalized_path = self._host._normalize_payload_path(create_path)
        normalized_path = self._host._canonicalize_context_prefix_on_path(
            normalized_path,
            context_id,
            context_type,
        )
        _, slot_key = self._host._find_last_element_token(normalized_path)
        if not isinstance(slot_key, str) or not slot_key or slot_key == object_id:
            slot_key = BubbleIDGenerator().element_id()
            element_index = next(
                (index for index in range(len(normalized_path) - 2, -1, -1) if normalized_path[index] == "%el"),
                None,
            )
            if element_index is None or element_index + 1 >= len(normalized_path):
                raise ValueError("Create element path must include a valid slot key after %el.")
            normalized_path[element_index + 1] = slot_key
        create_path[:] = normalized_path

        payload.add_update_index(["_index", "id_to_path", object_id], ".".join(normalized_path))
        payload.add_create_element(normalized_path, create_body)
        payload.add_update_index(["_index", "issues_list", object_id], "[]")

        parent_id = parent_result.get("id")
        if isinstance(parent_id, str) and parent_id:
            if isinstance(pending_child_ids_by_parent, dict) and isinstance(
                pending_child_ids_by_parent.get(parent_id), list
            ):
                child_ids = list(pending_child_ids_by_parent[parent_id])
            else:
                child_ids = self.existing_child_ids(context_id, context_type, parent_result)
            if object_id not in child_ids:
                child_ids.append(object_id)
            if isinstance(pending_child_ids_by_parent, dict):
                pending_child_ids_by_parent[parent_id] = list(child_ids)
            payload.add_update_index(["_index", "issues_sub", parent_id], json.dumps(child_ids))

        if text_content is not None:
            payload.add_set_data(normalized_path + ["%p", "%3"], text_content)
        props = create_body.get("%p") if isinstance(create_body.get("%p"), dict) else {}
        nonant = props.get("nonant_alignment")
        align = props.get("align_to_parent_pos") or nonant
        if nonant:
            payload.add_set_data(normalized_path + ["%p", "nonant_alignment"], nonant)
        if align:
            payload.add_set_data(normalized_path + ["%p", "align_to_parent_pos"], align)
        for key in ("margin_top", "margin_right", "margin_bottom", "margin_left"):
            value = props.get(key)
            if value is not None and value != 0:
                payload.add_set_data(normalized_path + ["%p", key], value)

    def finish(
        self,
        payload: PayloadBuilder,
        *,
        context_id: str,
        context_type: str,
        parent_result: dict[str, Any],
        body: dict[str, Any],
        element_key: str,
        aliases: Iterable[str],
        result_value: str,
        success_message: str,
        dry_run: bool,
        parent_id: str | None = None,
        cache_aliases: bool = True,
        tolerate_injection_error: bool = False,
        error_via_print: bool = False,
        use_parent_result_id: bool = True,
    ) -> str | bool:
        normalized_aliases: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            value = str(alias or "").strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                normalized_aliases.append(value)

        def inject(preview: bool) -> bool:
            try:
                self._host.discovery.inject_element(
                    context_id,
                    context_type,
                    parent_id if parent_id is not None else (
                        parent_result.get("id") if use_parent_result_id else None
                    ),
                    body,
                    element_key=element_key,
                )
                return True
            except Exception as exc:
                if not tolerate_injection_error:
                    raise
                suffix = " (dry-run)" if preview else ""
                logger.warning(f"Injection warning{suffix}: {exc}")
                return False

        if dry_run:
            logger.info("\n DRY RUN - Payload preview:")
            logger.log(payload.to_json())
            inject(True)
            return result_value
        try:
            self._host._dispatch_payload(payload)
            logger.success(success_message)
            inject(False)
            element_id = str(body.get("id") or "").strip()
            if cache_aliases and normalized_aliases and element_id:
                self._host._cache_created_element_aliases(
                    context_id=context_id,
                    context_type=context_type,
                    aliases=normalized_aliases,
                    element_id=element_id,
                    element_key=element_key,
                    parent_path=list(parent_result.get("path") or []),
                )
            return result_value
        except Exception as exc:
            message = f"Failed to send: {exc}"
            if error_via_print:
                print(f"❌ {message}")
            else:
                logger.error(message)
            return False
