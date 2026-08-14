"""Read-oriented cached element materialization and editor-capture parsing."""

from __future__ import annotations

import json
import os
import re
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
    def _list_raw_context_elements(self, context_id: str, context_type: str) -> list[dict[str, Any]]: ...
    def _list_index_context_elements(self, context_id: str, context_type: str) -> list[dict[str, Any]]: ...
    def _list_module_context_elements(self, context_id: str, context_type: str) -> list[dict[str, Any]]: ...
    def _list_cached_context_elements(self, context_id: str, context_type: str) -> list[dict[str, Any]]: ...
    def _load_modules_index(self, context_type: str) -> dict[str, str]: ...
    def _schema_contexts_cache(self) -> dict[str, Any]: ...
    def _extract_plain_text_value(self, raw_value: Any) -> str: ...
    def _find_context(self, name: str) -> tuple[str | None, str | None]: ...


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

    def iter_contexts(self, scope: str = "all") -> list[dict[str, str]]:
        """Enumerate page/reusable contexts from discovery data and module indexes."""
        normalized_scope = (scope or "all").strip().lower()
        include_pages = normalized_scope in {"all", "pages", "page"}
        include_reusables = normalized_scope in {"all", "reusables", "reusable"}
        contexts: dict[tuple[str, str], dict[str, str]] = {}
        data = self._host.discovery.data if isinstance(self._host.discovery.data, dict) else {}

        def collect_data_contexts(
            context_type: str,
            readable_key: str,
            raw_key: str,
            skip_raw: bool = False,
        ) -> None:
            readable = data.get(readable_key)
            if isinstance(readable, dict):
                for context_id, payload in readable.items():
                    if not isinstance(payload, dict):
                        continue
                    name = payload.get("name") or payload.get("%nm") or str(context_id)
                    contexts[(context_type, str(context_id))] = {
                        "id": str(context_id), "type": context_type, "name": str(name)
                    }
            raw = data.get(raw_key)
            if isinstance(raw, dict):
                for context_id, payload in raw.items():
                    if not isinstance(payload, dict):
                        continue
                    if skip_raw and str(payload.get("%x", "")).lower() == "reusableelement":
                        continue
                    key = (context_type, str(context_id))
                    if key in contexts:
                        continue
                    name = payload.get("%nm") or payload.get("name") or str(context_id)
                    contexts[key] = {"id": str(context_id), "type": context_type, "name": str(name)}
            for context_id, display_name in self._host._load_modules_index(context_type).items():
                key = (context_type, str(context_id))
                if key not in contexts:
                    contexts[key] = {
                        "id": str(context_id), "type": context_type, "name": str(display_name or context_id)
                    }

        if include_pages:
            collect_data_contexts("page", "pages", "%p3", skip_raw=True)
        if include_reusables:
            collect_data_contexts("reusable", "element_definitions", "%ed")

        cached_contexts = self._host._schema_contexts_cache()
        for context_type, included in (("page", include_pages), ("reusable", include_reusables)):
            if not included:
                continue
            cache_bucket = cached_contexts.get(context_type, {}) if isinstance(cached_contexts, dict) else {}
            if not isinstance(cache_bucket, dict):
                continue
            for payload in cache_bucket.values():
                if not isinstance(payload, dict):
                    continue
                context_id = str(payload.get("context_id") or "").strip()
                if not context_id or (context_type, context_id) in contexts:
                    continue
                contexts[(context_type, context_id)] = {
                    "id": context_id,
                    "type": context_type,
                    "name": str(payload.get("name") or context_id),
                }

        rows = list(contexts.values())
        rows.sort(key=lambda item: (item.get("type", ""), self._host._norm_lookup(item.get("name")), item.get("id", "")))
        return rows

    @staticmethod
    def _extract_element_text_payload(element: dict[str, Any]) -> Any:
        if not isinstance(element, dict):
            return None
        props = element.get("%p")
        if isinstance(props, dict) and "%3" in props:
            return props.get("%3")
        props = element.get("properties")
        if isinstance(props, dict):
            return props.get("text") if "text" in props else props.get("%3")
        return None

    def _match_raw_element(
        self, element: dict[str, Any], element_ref: str, ref_kind: str, element_key: str | None = None
    ) -> bool:
        return self._score_raw_element_match(element, element_ref, ref_kind, element_key) >= 0

    def _score_raw_element_match(
        self, element: dict[str, Any], element_ref: str, ref_kind: str, element_key: str | None = None
    ) -> int:
        kind = (ref_kind or "name").strip().lower()
        if not isinstance(element, dict):
            return -1
        raw_ref = str(element_ref or "")
        needle = self._host._norm_lookup(element_ref)
        element_id = str(element.get("id") or "")
        element_key_value = str(element_key or "")
        names = [
            self._host._norm_lookup(value)
            for value in (element.get("%dn"), element.get("%nm"), element.get("name"), element.get("default_name"))
            if isinstance(value, str) and value.strip()
        ]
        text = self._host._norm_lookup(
            self._host._extract_plain_text_value(self._extract_element_text_payload(element))
        )
        if kind == "id":
            return 400 if element_id == raw_ref or element_key_value == raw_ref else -1
        if kind == "key":
            return 390 if element_key_value == raw_ref else -1
        if kind == "name":
            if needle and any(name == needle for name in names):
                return 300
            return 200 if needle and any(needle in name for name in names) else -1
        if kind == "text":
            if needle and text == needle:
                return 280
            return 180 if needle and needle in text else -1
        if kind == "auto":
            if element_id == raw_ref:
                return 400
            if element_key_value == raw_ref:
                return 390
            if needle and any(name == needle for name in names):
                return 300
            if needle and text == needle:
                return 280
            if needle and any(needle in name for name in names):
                return 200
            if needle and needle in text:
                return 180
        return -1

    def find_elements_by_ref(
        self, context_id: str, context_type: str, element_ref: str, ref_kind: str = "auto"
    ) -> list[dict[str, Any]]:
        kind = (ref_kind or "auto").strip().lower()
        lookup_kind = kind if kind in {"name", "text", "id", "key"} else "auto"
        matches: list[tuple[int, dict[str, Any]]] = []
        seen: set[str] = set()

        def push(item: dict[str, Any], key_hint: str | None = None) -> None:
            if not isinstance(item, dict):
                return
            normalized = dict(item)
            path = self._host._normalize_payload_path(normalized.get("path", []))
            normalized["path"] = path
            match_key = f"{normalized.get('id')}|{'.'.join(path)}|{key_hint or ''}"
            if match_key in seen:
                return
            element = normalized.get("element", {})
            score = self._score_raw_element_match(
                element if isinstance(element, dict) else {}, element_ref, kind, key_hint
            )
            if score < 0:
                return
            seen.add(match_key)
            matches.append((score, normalized))

        def push_matching(items: list[dict[str, Any]]) -> None:
            for item in items:
                path = item.get("path", []) if isinstance(item, dict) else []
                key = path[-1] if isinstance(path, list) and path else item.get("key")
                if self._match_raw_element(item.get("element", {}), element_ref, lookup_kind, str(key or "")):
                    push(item, str(key or ""))

        push_matching(self._host.discovery.list_elements(context_id, context_type=context_type))
        push_matching(self._host._list_raw_context_elements(context_id, context_type))
        push_matching(self._host._list_module_context_elements(context_id, context_type))

        for item in self._host._list_index_context_elements(context_id, context_type):
            if not isinstance(item, dict):
                continue
            alias_id = str(item.get("id") or "")
            element_key = str(item.get("key") or "")
            element = item.get("element", {}) if isinstance(item.get("element"), dict) else {}
            if lookup_kind == "id":
                if alias_id == str(element_ref):
                    push(item, element_key)
            elif lookup_kind == "key":
                if element_key and element_key == str(element_ref):
                    push(item, element_key)
            elif element and self._match_raw_element(element, element_ref, lookup_kind, element_key):
                push(item, element_key)
            elif lookup_kind == "auto" and (alias_id == str(element_ref) or element_key == str(element_ref)):
                push(item, element_key)

        matches.sort(key=lambda match: match[0], reverse=True)
        return [item for _, item in matches]

    def find_element_by_ref(
        self,
        context_id: str,
        context_type: str,
        element_ref: str,
        ref_kind: str = "auto",
        match_index: int = 1,
    ) -> dict[str, Any] | None:
        matches = self.find_elements_by_ref(context_id, context_type, element_ref, ref_kind)
        index = max(1, int(match_index)) - 1
        return matches[index] if index < len(matches) else None

    def select_element_match(
        self,
        context_name: str,
        element_ref: str,
        ref_kind: str = "auto",
        match_index: int | None = None,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        context_id, context_type = self._host._find_context(context_name)
        if not context_id:
            logger.error(f"Context '{context_name}' not found.")
            return None, None, None
        matches = self.find_elements_by_ref(context_id, str(context_type or "page"), element_ref, ref_kind)
        if not matches:
            logger.error(f"Element '{element_ref}' not found in '{context_name}' by {ref_kind}.")
            return None, None, None
        selected = match_index if match_index is not None else (len(matches) if len(matches) > 1 else 1)
        if len(matches) > 1 and ref_kind in {"text", "name", "auto"}:
            logger.warning(
                f"Multiple matches found ({len(matches)}) for '{element_ref}' in '{context_name}'. "
                f"Using match #{selected}. Use --match-index or --ref-kind id/key to target explicitly."
            )
            for index, item in enumerate(matches[:5], start=1):
                logger.info(f"  [{index}] id={item.get('id')} path={'.'.join(item.get('path', []))}")
        pick = max(1, int(selected)) - 1
        if pick >= len(matches):
            logger.error(f"match-index {selected} out of range; found {len(matches)} matches.")
            return None, None, None
        return context_id, context_type, matches[pick]

    def collect_context_elements(self, context_id: str, context_type: str) -> list[dict[str, Any]]:
        """Collect normalized, deduplicated element rows from all read sources."""
        rows_by_key: dict[str, dict[str, Any]] = {}

        def opaque(value: Any) -> bool:
            raw = str(value or "").strip()
            return not raw or bool(re.fullmatch(r"[A-Za-z0-9]{3,8}", raw)) and not any(char in raw for char in "_- ")

        def placeholder(value: Any) -> bool:
            return str(value or "").strip() == "[truncated_max_depth]"

        def score(row: dict[str, Any]) -> int:
            value = 0
            name, element_type, path, element_id = row.get("name"), row.get("type"), row.get("path"), row.get("id")
            if str(name or "").strip():
                value += 2 + (0 if opaque(name) else 5)
            if str(element_type or "").strip() and str(element_type).lower() != "unknown":
                value += 4
            if isinstance(path, list) and path:
                value += 2
            if str(element_id or "").strip() and not opaque(element_id):
                value += 1
            return value

        def push(item: dict[str, Any]) -> None:
            if not isinstance(item, dict):
                return
            path = self._host._normalize_payload_path(item.get("path", []))
            element = item.get("element") if isinstance(item.get("element"), dict) else {}
            element_id = str(element.get("id") or item.get("id") or "").strip()
            key = str(item.get("key") or (path[-1] if path else "")).strip()
            name = str(element.get("%dn") or element.get("%nm") or element.get("name") or element.get("default_name") or "").strip()
            element_type = str(element.get("%x") or element.get("type") or "").strip()
            if any(placeholder(value) for value in (element_id, name, element_type, *path)) or not (element_id or name or element_type):
                return
            candidate = {"id": element_id or None, "key": key or None, "name": name, "type": element_type, "style_id": str(element.get("%s1") or "").strip() or None, "path": path}
            dedupe_key = f"{element_id}|{'.'.join(path)}|{key}"
            current = rows_by_key.get(dedupe_key)
            if not current or score(candidate) > score(current):
                rows_by_key[dedupe_key] = candidate

        for items in (
            self._host.discovery.list_elements(context_id, context_type=context_type),
            self._host._list_raw_context_elements(context_id, context_type),
            self._host._list_module_context_elements(context_id, context_type),
            self._host._list_index_context_elements(context_id, context_type),
            self._host._list_cached_context_elements(context_id, context_type),
        ):
            for item in items:
                push(item)
        rows = list(rows_by_key.values())
        rows.sort(key=lambda row: (self._host._norm_lookup(row.get("name")), self._host._norm_lookup(row.get("type")), ".".join(row.get("path", [])), str(row.get("id") or "")))
        return rows
