"""Generic visual element deletion orchestration."""

from __future__ import annotations

import json
import random
from typing import Any

try:
    from ..bubble_sdk import PayloadBuilder, logger
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import PayloadBuilder, logger

from .protocols import VisualElementTarget, VisualMutationHost
from .targets import VisualMutationTargets


class VisualDeletionService:
    """Build and execute editor-consistent RemoveElement transactions."""

    def __init__(self, host: VisualMutationHost, targets: VisualMutationTargets) -> None:
        self._host = host
        self._targets = targets

    def delete(
        self,
        context_name: str,
        element_name: str,
        *,
        allowed_types: frozenset[str],
        expected_label: str,
        success_label: str,
        dry_run: bool = False,
        prefer_last: bool = False,
        issues_list_bodies: tuple[str | None, ...] = (),
        cascade_descendants: bool = False,
    ) -> bool:
        target = self._targets.resolve_existing(
            context_name,
            element_name,
            prefer_last=prefer_last,
        )
        if target is None:
            return False
        if allowed_types and target.element_type and target.element_type not in allowed_types:
            expected_display = " or ".join(
                f"'{token}'" for token in expected_label.split(" or ")
            )
            logger.error(
                f"Element '{element_name}' is type '{target.element_type}', "
                f"expected {expected_display}."
            )
            return False

        payload = self._build_remove_payload(
            target,
            issues_list_bodies=issues_list_bodies,
            cascade_descendants=cascade_descendants,
        )
        if dry_run:
            logger.info("\n DRY RUN - Payload preview:")
            logger.log(payload.to_json())
            return True

        try:
            self._host._dispatch_payload(payload)
            relative_path = target.result.get("path")
            self._host._remove_cached_element_aliases(
                context_id=target.context_id,
                context_type=target.context_type,
                element_id=target.element_id,
                element_path=relative_path if isinstance(relative_path, list) else None,
            )
            logger.success(f"Successfully deleted {success_label}: '{element_name}'")
            return True
        except Exception as exc:
            logger.error(f"Failed to send: {exc}")
            return False

    def _build_remove_payload(
        self,
        target: VisualElementTarget,
        *,
        issues_list_bodies: tuple[str | None, ...] = (),
        cascade_descendants: bool = False,
    ) -> PayloadBuilder:
        payload = PayloadBuilder(appname=self._host.appname)
        delete_entries = (
            self._collect_descendant_removals(target)
            if cascade_descendants
            else [(target.element_id, target.path, None, True)]
        )
        for element_id, path, parent_id, is_root in delete_entries:
            payload.add_update_index(["_index", "id_to_path", element_id], None)
            if is_root:
                intent_details = {
                    "user_action": "Keyboard Press Delete",
                    "selected_element": target.element_id,
                }
            else:
                intent_details = {
                    "user_action": "Deleted by parent element",
                    "parent_user_action": "Deleted by parent element",
                }
                if parent_id:
                    intent_details["parent_id"] = parent_id
            payload.changes.append(
                {
                    "intent": {
                        "name": "RemoveElement",
                        "id": random.randint(1, 999999),
                        "intent_details": intent_details,
                        "source_appname": "",
                    },
                    "path_array": path,
                    "body": None,
                    "version_control_api_version": 4,
                    "changelog_data": [],
                    "session_id": payload.session_id,
                }
            )
        for body in issues_list_bodies:
            payload.add_update_index(
                ["_index", "issues_list", target.element_id],
                body,
            )
        parent_updates = self._find_parent_updates(target)
        for parent_id, children in parent_updates:
            remaining = [child_id for child_id in children if child_id != target.element_id]
            payload.add_update_index(
                ["_index", "issues_sub", parent_id],
                json.dumps(remaining),
            )
        return payload

    def _collect_descendant_removals(
        self,
        target: VisualElementTarget,
    ) -> list[tuple[str, list[str], str | None, bool]]:
        target_node = self._host._get_value_at_path(target.path)
        if not isinstance(target_node, dict):
            element = target.result.get("element")
            target_node = element if isinstance(element, dict) else {}

        entries: list[tuple[str, list[str], str | None, bool]] = []

        def collect(node: dict[str, Any], path: list[str], parent_id: str | None) -> None:
            children = node.get("%el") if isinstance(node.get("%el"), dict) else {}
            current_key = str(path[-1] if path else "").strip()
            element_id = str(node.get("id") or current_key).strip()
            if not element_id:
                return
            for child_key, child in children.items():
                if child_key == "length" or not isinstance(child, dict):
                    continue
                collect(child, [*path, "%el", str(child_key)], element_id)
            entries.append((element_id, list(path), parent_id, element_id == target.element_id))

        collect(target_node, target.path, None)
        return entries or [(target.element_id, target.path, None, True)]

    def _find_parent_updates(self, target: VisualElementTarget) -> list[tuple[str, list[str]]]:
        data = self._host.discovery.data if isinstance(self._host.discovery.data, dict) else {}
        index = data.get("_index", {}) if isinstance(data.get("_index"), dict) else {}
        issues_sub = index.get("issues_sub", {}) if isinstance(index.get("issues_sub"), dict) else {}
        matches: list[tuple[str, list[str]]] = []
        for parent_id, raw_children in issues_sub.items():
            children = self._parse_children(raw_children)
            if target.element_id in children:
                matches.append((str(parent_id), children))
        if matches:
            return matches

        parent_id = ""
        children: list[str] = []
        if len(target.path) >= 2:
            parent_node = self._host._get_value_at_path(target.path[:-2])
            if isinstance(parent_node, dict):
                parent_id = str(parent_node.get("id") or "").strip()
                children = self._child_ids(parent_node)
        if not parent_id:
            parent_id = self._context_object_id(
                target.context_id,
                target.context_type,
            ) or self._host._lookup_cached_context_object_id(
                target.context_type,
                target.context_id,
            )
            if parent_id:
                try:
                    root = self._host.discovery._get_context_root(
                        target.context_id,
                        target.context_type,
                    )
                except Exception:
                    root = None
                children = self._child_ids(root)
                if not children:
                    children = self._root_children_from_index(
                        target.context_id,
                        target.context_type,
                    )
        return [(parent_id, children)] if parent_id else []

    @staticmethod
    def _parse_children(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if not isinstance(value, str) or not value.strip():
            return []
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return [str(item) for item in decoded if str(item).strip()] if isinstance(decoded, list) else []

    @staticmethod
    def _child_ids(node: Any) -> list[str]:
        if not isinstance(node, dict):
            return []
        children = node.get("%el") if isinstance(node.get("%el"), dict) else node.get("elements")
        if not isinstance(children, dict):
            return []
        result: list[str] = []
        for key, child in children.items():
            if key == "length" or not isinstance(child, dict):
                continue
            child_id = str(child.get("id") or key).strip()
            if child_id:
                result.append(child_id)
        return result

    def _context_object_id(self, context_id: str, context_type: str) -> str:
        data = self._host.discovery.data if isinstance(self._host.discovery.data, dict) else {}
        index = data.get("_index", {}) if isinstance(data.get("_index"), dict) else {}
        id_to_path = index.get("id_to_path", {}) if isinstance(index.get("id_to_path"), dict) else {}
        prefix = self._host._workflow_prefix(context_type)
        root_token = self._host._resolve_context_write_root_token(context_id, context_type)
        for object_id, raw_path in id_to_path.items():
            normalized = self._host._normalize_capture_path(raw_path)
            if normalized == [prefix, root_token]:
                return str(object_id or "").strip()
        return ""

    def _root_children_from_index(self, context_id: str, context_type: str) -> list[str]:
        data = self._host.discovery.data if isinstance(self._host.discovery.data, dict) else {}
        index = data.get("_index", {}) if isinstance(data.get("_index"), dict) else {}
        id_to_path = index.get("id_to_path", {}) if isinstance(index.get("id_to_path"), dict) else {}
        prefix = self._host._workflow_prefix(context_type)
        root_token = self._host._resolve_context_write_root_token(context_id, context_type)
        result: list[str] = []
        for object_id, raw_path in id_to_path.items():
            normalized = self._host._normalize_capture_path(raw_path)
            if len(normalized) == 4 and normalized[:2] == [prefix, root_token] and normalized[2] == "%el":
                child_id = str(object_id or "").strip()
                if child_id:
                    result.append(child_id)
        return result
