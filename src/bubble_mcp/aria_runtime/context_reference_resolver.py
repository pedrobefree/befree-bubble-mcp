"""Read-oriented cached element materialization and editor-capture parsing."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol, cast

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
    def _list_context_workflows(self, context_id: str, context_type: str) -> list[dict[str, Any]]: ...
    def _resolve_parent_element(
        self,
        context_id: str,
        context_type: str,
        context_name: str,
        parent_ref: str,
    ) -> dict[str, Any] | None: ...
    def _resolve_element_alias_from_id_to_path(
        self,
        context_id: str,
        context_type: str,
        element_ref: str,
    ) -> dict[str, Any] | None: ...
    def _resolve_cached_element_alias(
        self,
        context_id: str,
        context_type: str,
        element_ref: str,
    ) -> dict[str, Any] | None: ...
    def _resolve_workflow_ref(
        self,
        context_id: str,
        context_type: str,
        event_ref: str,
        ref_kind: str = "auto",
    ) -> dict[str, Any] | None: ...
    def find_style_id(self, style_ref: str, element_type: str | None = None) -> str | None: ...
    def _resolve_data_type_key(self, data_type_ref: str, ref_kind: str = "key") -> str | None: ...
    def _get_user_types(self, include_cache: bool = True) -> dict[str, Any]: ...
    def _resolve_option_set_key(self, option_set_ref: str, ref_kind: str = "auto") -> str | None: ...
    def _get_option_sets(self, include_cache: bool = True) -> dict[str, Any]: ...
    def _resolve_option_value_key(
        self,
        option_set_key: str,
        value_ref: str,
        ref_kind: str = "key",
    ) -> str | None: ...
    def _get_option_set_values(self, option_set_key: str) -> dict[str, Any] | None: ...


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
            return self._host._normalize_payload_path(parts) if parts else []
        except (RecursionError, TypeError, ValueError):
            return []

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

    @classmethod
    def _canonical_capture_element_path(
        cls,
        path_parts: list[str],
    ) -> tuple[str, str, list[str]] | None:
        if len(path_parts) < 4:
            return None
        context_type = cls._context_type_from_prefix(path_parts[0])
        context_id = str(path_parts[1] or "").strip()
        if not context_type or not context_id:
            return None

        cursor = 2
        while (
            cursor + 1 < len(path_parts)
            and path_parts[cursor] == "%el"
            and str(path_parts[cursor + 1] or "").strip()
        ):
            cursor += 2
        if cursor == 2:
            return None

        trailing_path = path_parts[cursor:]
        if "%el" in trailing_path:
            return None
        element_path = path_parts[:cursor]
        return context_type, context_id, element_path

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

        def register_name(
            context_type: str,
            context_id: str,
            element_path: list[str],
            candidate_name: Any,
        ) -> None:
            if not isinstance(candidate_name, str):
                return
            name = candidate_name.strip()
            element_id = str(element_path[-1] or "").strip()
            if not name or not element_id:
                return
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
            canonical = self._canonical_capture_element_path(path_parts)
            if canonical is None:
                continue
            context_type, context_id, element_path = canonical
            intent = row.get("intent")
            intent_name = str(intent.get("name") or "") if isinstance(intent, dict) else str(intent or "")
            body = row.get("body")
            if path_parts[-1] in {"%nm", "%dn"} and isinstance(body, str):
                register_name(context_type, context_id, element_path, body)
            if (
                len(path_parts) == len(element_path)
                and intent_name == "CreateElement"
                and isinstance(body, dict)
            ):
                register_name(
                    context_type,
                    context_id,
                    element_path,
                    body.get("%nm")
                    or body.get("%dn")
                    or body.get("name")
                    or body.get("default_name"),
                )

            node = self._host._get_value_at_path(element_path)
            if isinstance(node, dict):
                register_name(
                    context_type,
                    context_id,
                    element_path,
                    node.get("%nm")
                    or node.get("%dn")
                    or node.get("name")
                    or node.get("default_name"),
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
        match_positions: dict[str, int] = {}

        def push(
            item: dict[str, Any],
            key_hint: str | None = None,
            score_override: int | None = None,
        ) -> None:
            if not isinstance(item, dict):
                return
            normalized = dict(item)
            path = self._host._normalize_payload_path(normalized.get("path", []))
            normalized["path"] = path
            element = normalized.get("element", {})
            score = (
                score_override
                if score_override is not None
                else self._score_raw_element_match(
                    element if isinstance(element, dict) else {}, element_ref, kind, key_hint
                )
            )
            if score < 0:
                return
            element_id = str(normalized.get("id") or "").strip()
            match_key = (
                f"id:{element_id}"
                if element_id
                else f"path:{'.'.join(path)}|key:{key_hint or ''}"
            )
            previous_position = match_positions.get(match_key)
            if previous_position is not None:
                previous_score, previous_item = matches[previous_position]
                if score > previous_score:
                    matches[previous_position] = (score, previous_item)
                return
            match_positions[match_key] = len(matches)
            matches.append((score, normalized))

        def push_matching(items: list[dict[str, Any]]) -> None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                path = item.get("path", [])
                key = path[-1] if isinstance(path, list) and path else item.get("key")
                if self._match_raw_element(item.get("element", {}), element_ref, lookup_kind, str(key or "")):
                    push(item, str(key or ""))

        push_matching(self._host.discovery.list_elements(context_id, context_type=context_type))
        push_matching(self._host._list_raw_context_elements(context_id, context_type))
        push_matching(self._host._list_module_context_elements(context_id, context_type))

        for item in self._host._list_index_context_elements(context_id, context_type):
            if not isinstance(item, dict):
                continue
            canonical_id = str(item.get("id") or "")
            alias_id = str(item.get("alias_id") or "")
            element_key = str(item.get("key") or "")
            element = item.get("element", {}) if isinstance(item.get("element"), dict) else {}
            if lookup_kind == "id":
                if str(element_ref) in {canonical_id, alias_id}:
                    push(item, element_key, 400)
            elif lookup_kind == "key":
                if element_key and element_key == str(element_ref):
                    push(item, element_key)
            elif lookup_kind == "auto":
                if str(element_ref) in {canonical_id, alias_id}:
                    push(item, element_key, 400)
                elif element_key and element_key == str(element_ref):
                    push(item, element_key, 390)
                elif element and self._match_raw_element(
                    element, element_ref, lookup_kind, element_key
                ):
                    push(item, element_key)
            elif element and self._match_raw_element(element, element_ref, lookup_kind, element_key):
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

    def inspect_context(
        self,
        context_name: str | None = None,
        scope: str = "all",
        include_elements: bool = False,
        include_workflows: bool = False,
        include_styles: bool = False,
        limit: int = 200,
        as_json: bool = False,
    ) -> bool:
        """Inspect one context or list contexts with counts/details."""
        limit_n = max(1, int(limit))

        def style_name_map() -> dict[str, str]:
            mapping: dict[str, str] = {}
            for style in self._host.discovery.list_styles():
                style_id = str(style.get("id") or "").strip()
                style_name = str(style.get("name") or "").strip()
                if style_id:
                    mapping[style_id] = style_name
            return mapping

        if context_name:
            context_id, context_type = self._host._find_context(context_name)
            if not context_id:
                logger.error(f"Context '{context_name}' not found.")
                return False

            contexts = self.iter_contexts(scope="all")
            context_label = next(
                (
                    row.get("name")
                    for row in contexts
                    if row.get("id") == context_id and row.get("type") == context_type
                ),
                context_name,
            )

            elements = self.collect_context_elements(context_id, cast(str, context_type))
            workflows = self._host._list_context_workflows(context_id, cast(str, context_type))

            output: dict[str, Any] = {
                "context": {
                    "id": context_id,
                    "type": context_type,
                    "name": context_label,
                },
                "counts": {
                    "elements": len(elements),
                    "workflows": len(workflows),
                },
            }

            if include_elements:
                output["elements"] = elements[:limit_n]
                output["elements_truncated"] = len(elements) > limit_n

            if include_workflows:
                workflow_rows: list[dict[str, Any]] = []
                for workflow in workflows[:limit_n]:
                    workflow_object = (
                        workflow.get("workflow", {})
                        if isinstance(workflow.get("workflow"), dict)
                        else {}
                    )
                    workflow_properties = (
                        workflow_object.get("%p")
                        if isinstance(workflow_object.get("%p"), dict)
                        else workflow_object.get("properties", {})
                    )
                    if not isinstance(workflow_properties, dict):
                        workflow_properties = {}
                    workflow_rows.append(
                        {
                            "key": str(workflow.get("key") or ""),
                            "id": str(workflow.get("id") or ""),
                            "type": str(
                                workflow.get("type")
                                or workflow_object.get("%x")
                                or workflow_object.get("type")
                                or ""
                            ),
                            "name": str(workflow.get("name") or ""),
                            "element_id": str(
                                workflow_properties.get("%ei")
                                or workflow_properties.get("element_id")
                                or ""
                            )
                            or None,
                        }
                    )
                output["workflows"] = workflow_rows
                output["workflows_truncated"] = len(workflows) > limit_n

            if include_styles:
                style_ids = sorted(
                    {
                        str(row.get("style_id") or "").strip()
                        for row in elements
                        if str(row.get("style_id") or "").strip()
                    }
                )
                styles_by_id = style_name_map()
                output["styles_used"] = [
                    {"id": style_id, "name": styles_by_id.get(style_id) or ""}
                    for style_id in style_ids[:limit_n]
                ]
                output["styles_used_truncated"] = len(style_ids) > limit_n
                output["counts"]["styles_used"] = len(style_ids)

            if as_json:
                print(json.dumps(output, indent=2, ensure_ascii=False))
                return True

            context = output["context"]
            counts = output["counts"]
            logger.log(
                f"Context: {context['name']} ({context['type']}, {context['id']})"
            )
            logger.log(
                f"Counts: elements={counts['elements']} workflows={counts['workflows']}"
            )
            if include_styles:
                logger.log(f"Styles used: {counts.get('styles_used', 0)}")
            if include_elements:
                logger.log(f"Elements (showing up to {limit_n}):")
                for row in output.get("elements", []):
                    logger.log(
                        f"  - {row.get('name') or '<unnamed>'} "
                        f"[{row.get('type') or 'unknown'}] id={row.get('id') or '?'}"
                    )
            if include_workflows:
                logger.log(f"Workflows (showing up to {limit_n}):")
                for workflow in output.get("workflows", []):
                    logger.log(
                        f"  - key={workflow.get('key')} id={workflow.get('id')} "
                        f"type={workflow.get('type')} element={workflow.get('element_id') or '-'}"
                    )
            return True

        contexts = self.iter_contexts(scope=scope)
        rows: list[dict[str, Any]] = []
        for context in contexts:
            context_id = str(context.get("id") or "")
            context_type = str(context.get("type") or "")
            context_row: dict[str, Any] = {
                "id": context_id,
                "type": context_type,
                "name": str(context.get("name") or ""),
            }
            if include_elements:
                context_row["elements_count"] = len(
                    self.collect_context_elements(context_id, context_type)
                )
            if include_workflows:
                context_row["workflows_count"] = len(
                    self._host._list_context_workflows(context_id, context_type)
                )
            if include_styles:
                style_ids = {
                    str(row.get("style_id") or "").strip()
                    for row in self.collect_context_elements(context_id, context_type)
                    if str(row.get("style_id") or "").strip()
                }
                context_row["styles_used_count"] = len(style_ids)
            rows.append(context_row)

        if as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return True

        logger.log(f"Contexts ({len(rows)}):")
        for row in rows:
            suffix = []
            if "elements_count" in row:
                suffix.append(f"elements={row.get('elements_count')}")
            if "workflows_count" in row:
                suffix.append(f"workflows={row.get('workflows_count')}")
            if "styles_used_count" in row:
                suffix.append(f"styles={row.get('styles_used_count')}")
            suffix_text = f" ({', '.join(suffix)})" if suffix else ""
            logger.log(
                f"- {row.get('name') or '<unnamed>'} [{row.get('type')}] "
                f"id={row.get('id')}{suffix_text}"
            )
        return True

    def resolve_refs(
        self,
        *,
        context_name: str | None = None,
        parent_ref: str | None = None,
        parent_match_index: int = 1,
        element_ref: str | None = None,
        element_ref_kind: str = "auto",
        match_index: int = 1,
        event_ref: str | None = None,
        event_ref_kind: str = "auto",
        style_ref: str | None = None,
        style_element_type: str | None = None,
        data_type_ref: str | None = None,
        data_type_ref_kind: str = "auto",
        option_set_ref: str | None = None,
        option_set_ref_kind: str = "auto",
        option_value_ref: str | None = None,
        as_json: bool = False,
    ) -> bool:
        """Resolve user-friendly references into canonical ids/keys."""
        del parent_match_index
        payload: dict[str, Any] = {}
        errors: list[str] = []

        context_id: str | None = None
        context_type: str | None = None
        if context_name:
            context_id, context_type = self._host._find_context(context_name)
            if not context_id:
                errors.append(f"Context '{context_name}' not found.")
            else:
                payload["context"] = {
                    "name": context_name,
                    "id": context_id,
                    "type": context_type,
                }

        if parent_ref:
            if not context_id:
                errors.append("parent_ref requires a resolvable context.")
            else:
                parent_found = self._host._resolve_parent_element(
                    context_id,
                    context_type or "page",
                    context_name or context_id,
                    parent_ref,
                )
                if not parent_found:
                    errors.append(f"Parent '{parent_ref}' not found.")
                else:
                    payload["parent"] = {
                        "ref": parent_ref,
                        "id": parent_found.get("id"),
                        "path": parent_found.get("path", []),
                    }

        if element_ref:
            if not context_id:
                errors.append("element_ref requires a resolvable context.")
            else:
                element_found = self.find_element_by_ref(
                    context_id,
                    context_type or "page",
                    element_ref,
                    ref_kind=element_ref_kind,
                    match_index=max(1, int(match_index)),
                )
                if not element_found and element_ref_kind in {"auto", "id"}:
                    element_found = self._host._resolve_element_alias_from_id_to_path(
                        context_id,
                        context_type or "page",
                        str(element_ref),
                    )
                if not element_found:
                    element_found = self._host._resolve_cached_element_alias(
                        context_id,
                        context_type or "page",
                        element_ref,
                    )
                if not element_found:
                    errors.append(
                        f"Element '{element_ref}' not found in "
                        f"'{context_name or context_id}' by {element_ref_kind}."
                    )
                else:
                    element_payload = (
                        element_found.get("element")
                        if isinstance(element_found.get("element"), dict)
                        else {}
                    )
                    path = self._host._normalize_payload_path(
                        element_found.get("path", [])
                    )
                    payload["element"] = {
                        "ref": element_ref,
                        "id": str(element_found.get("id") or ""),
                        "key": str(
                            element_found.get("key") or (path[-1] if path else "")
                        )
                        or None,
                        "name": (
                            element_payload.get("%dn")
                            or element_payload.get("%nm")
                            or element_payload.get("name")
                            or element_payload.get("default_name")
                            or ""
                        ),
                        "type": element_payload.get("%x")
                        or element_payload.get("type")
                        or "",
                        "path": path,
                    }

        if event_ref:
            if not context_id:
                errors.append("event_ref requires a resolvable context.")
            else:
                workflow = self._host._resolve_workflow_ref(
                    context_id,
                    context_type or "page",
                    event_ref,
                    ref_kind=event_ref_kind,
                )
                if not workflow:
                    errors.append(
                        f"Workflow '{event_ref}' not found in "
                        f"'{context_name or context_id}' by {event_ref_kind}."
                    )
                else:
                    workflow_object = (
                        workflow.get("workflow", {})
                        if isinstance(workflow.get("workflow"), dict)
                        else {}
                    )
                    workflow_properties = (
                        workflow_object.get("%p")
                        if isinstance(workflow_object.get("%p"), dict)
                        else workflow_object.get("properties", {})
                        if isinstance(workflow_object.get("properties"), dict)
                        else {}
                    )
                    payload["event"] = {
                        "ref": event_ref,
                        "key": str(workflow.get("key") or ""),
                        "id": str(workflow.get("id") or ""),
                        "type": str(
                            workflow.get("type")
                            or workflow_object.get("%x")
                            or workflow_object.get("type")
                            or ""
                        ),
                        "name": str(workflow.get("name") or ""),
                        "element_id": str(
                            workflow_properties.get("%ei")
                            or workflow_properties.get("element_id")
                            or ""
                        )
                        or None,
                    }

        if style_ref:
            style_id = self._host.find_style_id(
                style_ref,
                element_type=style_element_type,
            )
            if not style_id:
                errors.append(f"Style '{style_ref}' not found.")
            else:
                style_object: dict[str, Any] = {}
                data = (
                    self._host.discovery.data
                    if isinstance(self._host.discovery.data, dict)
                    else {}
                )
                if isinstance(data.get("styles"), dict):
                    candidate = data.get("styles", {}).get(style_id)
                    style_object = candidate if isinstance(candidate, dict) else {}
                payload["style"] = {
                    "ref": style_ref,
                    "id": style_id,
                    "name": style_object.get("%d") or style_ref,
                    "type": style_object.get("%x") or style_element_type or "",
                }

        if data_type_ref:
            data_type_kind = (data_type_ref_kind or "auto").strip().lower()
            if data_type_kind == "auto":
                data_type_key = self._host._resolve_data_type_key(
                    data_type_ref,
                    ref_kind="key",
                )
                if not data_type_key:
                    data_type_key = self._host._resolve_data_type_key(
                        data_type_ref,
                        ref_kind="label",
                    )
            else:
                data_type_key = self._host._resolve_data_type_key(
                    data_type_ref,
                    ref_kind=(
                        "label"
                        if data_type_kind in {"label", "name", "display"}
                        else "key"
                    ),
                )
            if not data_type_key:
                errors.append(f"Data type '{data_type_ref}' not found.")
            else:
                data_type_metadata = self._host._get_user_types(
                    include_cache=True
                ).get(data_type_key, {})
                payload["data_type"] = {
                    "ref": data_type_ref,
                    "key": data_type_key,
                    "display": (
                        data_type_metadata.get("%d")
                        if isinstance(data_type_metadata, dict)
                        else ""
                    )
                    or "",
                }

        resolved_option_set_key: str | None = None
        if option_set_ref:
            option_set_kind = (option_set_ref_kind or "auto").strip().lower()
            resolved_option_set_key = self._host._resolve_option_set_key(
                option_set_ref,
                ref_kind=(
                    option_set_kind
                    if option_set_kind
                    in {"key", "label", "name", "display", "auto"}
                    else "auto"
                ),
            )
            if not resolved_option_set_key:
                errors.append(f"Option set '{option_set_ref}' not found.")
            else:
                option_set_metadata = self._host._get_option_sets(
                    include_cache=True
                ).get(resolved_option_set_key, {})
                payload["option_set"] = {
                    "ref": option_set_ref,
                    "key": resolved_option_set_key,
                    "display": (
                        option_set_metadata.get("%d")
                        or option_set_metadata.get("display")
                        if isinstance(option_set_metadata, dict)
                        else ""
                    )
                    or "",
                }

        if option_value_ref:
            if not resolved_option_set_key:
                errors.append(
                    "option_value_ref requires a resolvable option_set_ref."
                )
            else:
                value_key = self._host._resolve_option_value_key(
                    resolved_option_set_key,
                    option_value_ref,
                    ref_kind="key",
                )
                if not value_key:
                    errors.append(
                        f"Option value '{option_value_ref}' not found in option set "
                        f"'{resolved_option_set_key}'."
                    )
                else:
                    values_map = (
                        self._host._get_option_set_values(resolved_option_set_key)
                        or {}
                    )
                    value_metadata = (
                        values_map.get(value_key, {})
                        if isinstance(values_map, dict)
                        else {}
                    )
                    payload["option_value"] = {
                        "ref": option_value_ref,
                        "key": value_key,
                        "db_value": (
                            value_metadata.get("db_value")
                            if isinstance(value_metadata, dict)
                            else None
                        ),
                        "display": (
                            value_metadata.get("%d")
                            or value_metadata.get("display")
                            if isinstance(value_metadata, dict)
                            else ""
                        )
                        or "",
                    }

        payload["ok"] = len(errors) == 0
        payload["errors"] = errors

        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return payload["ok"] or bool(payload)

        if payload.get("context"):
            context = payload["context"]
            logger.log(
                f"Context: {context.get('name')} -> "
                f"{context.get('type')}:{context.get('id')}"
            )
        for key in (
            "parent",
            "element",
            "event",
            "style",
            "data_type",
            "option_set",
            "option_value",
        ):
            if key in payload:
                logger.log(f"{key}: {json.dumps(payload[key], ensure_ascii=False)}")
        for error in errors:
            logger.error(error)
        return len(errors) == 0
