"""Read-oriented cached element materialization and editor-capture parsing."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

try:
    from .bubble_sdk import logger
    from .context_alias_registry import ContextAliasRegistry
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import logger
    from context_alias_registry import ContextAliasRegistry


class ReferenceResolverHost(Protocol):
    """Existing BubbleCLI callbacks used by the reference resolver."""

    discovery: Any
    _alias_registry: ContextAliasRegistry

    def _normalize_payload_path(self, path_parts: Any) -> list[str]: ...
    def _parse_path_array(self, raw_path: Any) -> list[str]: ...
    def _norm_lookup(self, value: Any) -> str: ...
    def _workflow_prefix(self, context_type: str) -> str: ...
    def _get_value_at_path(self, path_array: list[str]) -> Any: ...
    def _collect_alias_ids_for_element_path(
        self,
        context_id: str,
        context_type: str,
        element_path: list[str],
    ) -> list[str]: ...


class ContextReferenceResolver:
    """Resolve cached element references without owning cache persistence."""

    def __init__(self, host: ReferenceResolverHost) -> None:
        self._host = host

    def materialize_cached_element_stub(
        self,
        context_id: str,
        context_type: str,
        cached_payload: dict[str, Any] | None,
        alias_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Rebuild only the missing discovery chain for one cached alias path."""
        if not isinstance(cached_payload, dict):
            return cached_payload

        normalized_path = self._host._normalize_payload_path(cached_payload.get("path"))
        if not self._is_element_path(normalized_path):
            return cached_payload

        element_id = str(cached_payload.get("id") or cached_payload.get("key") or "").strip()
        element_key = str(cached_payload.get("key") or element_id).strip()
        element_name = str(cached_payload.get("name") or alias_name or element_key or element_id).strip()
        if not element_key:
            return cached_payload

        root = self._host.discovery._get_context_root(context_id, context_type)
        if not isinstance(root, dict):
            root = self._create_context_root(context_id, context_type)
        if not isinstance(root, dict):
            return cached_payload

        node = root
        for index in range(0, len(normalized_path), 2):
            current_key = normalized_path[index + 1]
            children_key = "%el" if "%el" in node or "%x" in node else "elements"
            children = node.get(children_key)
            if not isinstance(children, dict):
                children = {}
                node[children_key] = children

            child = children.get(current_key)
            is_leaf = index + 2 == len(normalized_path)
            if not isinstance(child, dict):
                child = {
                    "id": element_id if is_leaf and element_id else current_key,
                    "type": "Unknown",
                    "default_name": element_name if is_leaf else current_key,
                    "name": element_name if is_leaf else current_key,
                    "elements": {},
                }
                children[current_key] = child
            elif is_leaf:
                if element_id:
                    child["id"] = element_id
                if element_name:
                    child["default_name"] = child.get("default_name") or element_name
                    child["name"] = child.get("name") or element_name
            node = child

        materialized = dict(cached_payload)
        materialized["path"] = normalized_path
        materialized["id"] = element_id or materialized.get("id")
        materialized["key"] = element_key or materialized.get("key")
        materialized["name"] = element_name or materialized.get("name")
        materialized["element"] = node
        return materialized

    @staticmethod
    def _is_element_path(path_parts: list[str]) -> bool:
        return bool(path_parts) and len(path_parts) % 2 == 0 and all(
            path_parts[index] == "%el" and bool(str(path_parts[index + 1]).strip())
            for index in range(0, len(path_parts), 2)
        )

    def _create_context_root(self, context_id: str, context_type: str) -> dict[str, Any] | None:
        data = self._host.discovery.data
        if not isinstance(data, dict):
            return None
        readable_key = "element_definitions" if context_type == "reusable" else "pages"
        raw_key = "%ed" if context_type == "reusable" else "%p3"
        bucket = data.get(readable_key)
        if not isinstance(bucket, dict):
            bucket = data.get(raw_key)
        if not isinstance(bucket, dict):
            bucket = {}
            data[readable_key] = bucket
        root = {"id": context_id, "name": context_id, "elements": {}}
        bucket[context_id] = root
        return root

    def normalize_capture_path(self, raw_path: Any) -> list[str]:
        try:
            parts = self._host._parse_path_array(raw_path)
        except (TypeError, ValueError):
            return []
        return self._host._normalize_payload_path(parts) if parts else []

    @staticmethod
    def _context_type_from_prefix(prefix: str) -> str | None:
        if str(prefix or "") in {"%p3", "pages"}:
            return "page"
        if str(prefix or "") in {"%ed", "element_definitions"}:
            return "reusable"
        return None

    @staticmethod
    def _find_last_element_token(path_parts: list[str]) -> tuple[int | None, str | None]:
        index: int | None = None
        for candidate, token in enumerate(path_parts):
            if token == "%el" and candidate + 1 < len(path_parts):
                index = candidate + 1
        if index is None:
            return None, None
        return index, str(path_parts[index])

    def sync_element_ref_cache(
        self,
        capture_file: str = "page_payloads.json",
        as_json: bool = False,
        dry_run: bool = False,
        quiet: bool = False,
    ) -> bool:
        """Import friendly aliases while skipping malformed capture rows."""
        capture_path = str(capture_file or "").strip() or "page_payloads.json"
        if not os.path.isabs(capture_path):
            capture_path = os.path.abspath(capture_path)
        if not os.path.isfile(capture_path):
            if not quiet:
                logger.error(f"Capture file not found: {capture_path}")
            return False

        try:
            with open(capture_path, "r", encoding="utf-8") as capture:
                raw_capture = json.load(capture)
        except Exception as error:
            if not quiet:
                logger.error(f"Could not read capture file: {error}")
            return False
        if not isinstance(raw_capture, list):
            if not quiet:
                logger.error("Capture file must be a JSON array.")
            return False

        names_by_path: dict[str, dict[str, Any]] = {}

        def register_name(path_parts: list[str], candidate_name: Any) -> None:
            if not isinstance(candidate_name, str):
                return
            name = candidate_name.strip()
            normalized = self._host._normalize_payload_path(path_parts)
            if not name or len(normalized) < 4:
                return
            context_type = self._context_type_from_prefix(normalized[0])
            element_index, element_id = self._find_last_element_token(normalized)
            if not context_type or element_index is None or not element_id:
                return
            context_id = str(normalized[1] or "").strip()
            if not context_id:
                return
            element_path = normalized[: element_index + 1]
            key = ".".join(element_path)
            record = names_by_path.setdefault(
                key,
                {
                    "context_id": context_id,
                    "context_type": context_type,
                    "element_id": element_id,
                    "element_path": element_path,
                    "names": set(),
                },
            )
            record["names"].add(name)

        for row in raw_capture:
            if not isinstance(row, dict):
                continue
            path_parts = self.normalize_capture_path(row.get("path"))
            if not path_parts:
                continue
            intent = row.get("intent")
            intent_name = str(intent.get("name") or "") if isinstance(intent, dict) else str(intent or "")
            body = row.get("body")
            if path_parts[-1] in {"%nm", "%dn"} and isinstance(body, str):
                register_name(path_parts[:-1], body)
            if intent_name == "CreateElement" and isinstance(body, dict):
                register_name(path_parts, body.get("%nm") or body.get("%dn") or body.get("name") or body.get("default_name"))

            element_index, _ = self._find_last_element_token(path_parts)
            if element_index is not None:
                element_path = path_parts[: element_index + 1]
                node = self._host._get_value_at_path(element_path)
                if isinstance(node, dict):
                    register_name(
                        element_path,
                        node.get("%nm") or node.get("%dn") or node.get("name") or node.get("default_name"),
                    )

        mappings: list[dict[str, str]] = []
        for record in names_by_path.values():
            context_id = record["context_id"]
            context_type = record["context_type"]
            element_id = record["element_id"]
            element_path = record["element_path"]
            target_ids = [element_id] + [
                alias_id
                for alias_id in self._host._collect_alias_ids_for_element_path(context_id, context_type, element_path)
                if alias_id != element_id
            ]
            for name in sorted(record["names"], key=self._host._norm_lookup):
                for target_id in target_ids:
                    mappings.append({"context_type": context_type, "context_id": context_id, "name": name, "id": target_id})
                    if not dry_run:
                        self._host._alias_registry.cache_element(
                            context_id,
                            context_type,
                            name,
                            target_id,
                        )

        deduplicated = {
            f"{row['context_type']}:{row['context_id']}:{self._host._norm_lookup(row['name'])}:{row['id']}": row
            for row in mappings
        }
        rows = sorted(
            deduplicated.values(),
            key=lambda row: (row["context_type"], row["context_id"], self._host._norm_lookup(row["name"]), row["id"]),
        )
        if as_json:
            logger.log(json.dumps(rows, indent=2, ensure_ascii=False))
        elif not quiet:
            logger.info(f"{'[DRY RUN] ' if dry_run else ''}Imported {len(rows)} element alias mappings from {capture_path}")
        return True
