"""Typed source-loading boundary for the legacy Aria path discovery runtime."""

from __future__ import annotations

import copy
import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Protocol


JsonObject = dict[str, Any]


class DiscoveryLogger(Protocol):
    """Small logging contract shared with the legacy runtime logger."""

    def info(self, message: str) -> object: ...

    def warning(self, message: str) -> object: ...


class DiscoveryDataBoundary:
    """Load, cache, refresh, and overlay discovery data from configured artifacts.

    Subclasses provide crawler merging and source-specific normalization. Keeping
    this boundary independent from the legacy runtime makes source precedence,
    cache behavior, and overlay semantics testable under strict typing.
    """

    def __init__(
        self,
        app_json_path: str | None = None,
        consolelog_json_path: str | None = None,
        crawler_index_path: str | None = None,
        mutation_overlay_path: str | None = None,
        *,
        logger: DiscoveryLogger,
    ) -> None:
        self.app_json_path = app_json_path
        self.consolelog_json_path = consolelog_json_path
        self.crawler_index_path = crawler_index_path
        self.mutation_overlay_path = mutation_overlay_path
        self._logger = logger
        self._data: JsonObject | None = None
        self._data_source: str | None = None
        self._source_path: str | None = None
        self._force_source_reload = False

    def _load_crawler_index(self, path: str | None) -> JsonObject | None:
        """Hook for the legacy crawler-index adapter."""

        return None

    def _merge_crawler_into_data(self, data: JsonObject, crawler: JsonObject) -> JsonObject:
        """Hook for the legacy crawler merge implementation."""

        return data

    def _normalize_api_connector_collections(self, data: JsonObject) -> JsonObject:
        """Hook for the legacy API Connector normalizer."""

        return data

    def _load_mutation_overlay(self, path: str | None) -> list[JsonObject]:
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as handle:
                raw: Any = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._logger.warning(f"[PathDiscovery] Could not read mutation overlay at {path}: {exc}")
            return []

        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            return []
        return [
            entry
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("changes"), list)
        ]

    @staticmethod
    def _normalize_overlay_path_array(path_array: Any) -> list[str]:
        if not isinstance(path_array, list):
            return []
        normalized: list[str] = []
        for segment in path_array:
            if isinstance(segment, (str, int, float)):
                text = str(segment)
                if text:
                    normalized.append(text)
        return normalized

    @staticmethod
    def _set_nested_overlay_value(
        target: JsonObject,
        path_parts: list[str],
        value: Any,
    ) -> None:
        if not path_parts:
            return
        current = target
        for token in path_parts[:-1]:
            nested = current.get(token)
            if not isinstance(nested, dict):
                nested = {}
                current[token] = nested
            current = nested
        current[path_parts[-1]] = copy.deepcopy(value)

    @staticmethod
    def _delete_nested_overlay_value(target: JsonObject, path_parts: list[str]) -> None:
        if not path_parts:
            return
        current = target
        for token in path_parts[:-1]:
            nested = current.get(token)
            if not isinstance(nested, dict):
                return
            current = nested
        current.pop(path_parts[-1], None)

    @staticmethod
    def _delete_aliased_overlay_record(
        target: JsonObject,
        bucket_names: list[str],
        key: str,
    ) -> None:
        aliases = {key}
        for bucket_name in bucket_names:
            bucket = target.get(bucket_name)
            if not isinstance(bucket, dict):
                continue
            direct = bucket.get(key)
            if not isinstance(direct, dict):
                continue
            for alias in (direct.get("id"), direct.get("%nm"), direct.get("name"), direct.get("%d")):
                if isinstance(alias, str) and alias.strip():
                    aliases.add(alias.strip())

        for bucket_name in bucket_names:
            bucket = target.get(bucket_name)
            if not isinstance(bucket, dict):
                continue
            for candidate_key, value in list(bucket.items()):
                should_delete = candidate_key in aliases
                if not should_delete and isinstance(value, dict):
                    record_aliases = (value.get("id"), value.get("%nm"), value.get("name"), value.get("%d"))
                    should_delete = any(
                        isinstance(alias, str) and alias.strip() in aliases
                        for alias in record_aliases
                    )
                if should_delete:
                    bucket.pop(candidate_key, None)

    def _delete_overlay_value(self, target: JsonObject, path_parts: list[str]) -> None:
        if len(path_parts) == 2 and path_parts[0] in {"%p3", "pages", "all_pages"}:
            self._delete_aliased_overlay_record(
                target,
                ["%p3", "pages", "all_pages"],
                path_parts[1],
            )
            return
        if len(path_parts) == 2 and path_parts[0] in {
            "%ed",
            "element_definitions",
            "CustomDefinition",
            "custom_definitions",
        }:
            self._delete_aliased_overlay_record(
                target,
                ["%ed", "element_definitions", "CustomDefinition", "custom_definitions"],
                path_parts[1],
            )
            return
        self._delete_nested_overlay_value(target, path_parts)

    def _apply_mutation_overlay(
        self,
        data: JsonObject,
        entries: list[JsonObject],
    ) -> JsonObject:
        if not entries:
            return data
        for entry in entries:
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                path_parts = self._normalize_overlay_path_array(change.get("path_array"))
                if not path_parts:
                    continue
                raw_intent = change.get("intent")
                intent = raw_intent if isinstance(raw_intent, dict) else {}
                intent_name = str(intent.get("name") or "").strip()
                lowered_intent = intent_name.lower()
                is_delete = (
                    intent_name == "RemoveElement"
                    or lowered_intent.startswith("delete")
                    or lowered_intent == "removeelement"
                    or path_parts[-1] == "%del"
                )
                if is_delete:
                    delete_path = path_parts[:-1] if path_parts[-1] == "%del" else path_parts
                    self._delete_overlay_value(data, delete_path)
                    continue
                if "body" in change:
                    self._set_nested_overlay_value(data, path_parts, change.get("body"))
        return data

    @staticmethod
    def _cache_enabled() -> bool:
        raw = str(os.getenv("BUBBLE_CLI_DISCOVERY_CACHE", "1")).strip().lower()
        return raw not in {"0", "false", "no", "off"}

    @staticmethod
    def _cache_path_for_source(source_path: str) -> str:
        return f"{source_path}.parsed-cache.pkl"

    @staticmethod
    def _read_json_object(source_path: str) -> JsonObject:
        with open(source_path, encoding="utf-8") as handle:
            payload: Any = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Discovery source must contain a JSON object: {source_path}")
        return payload

    @staticmethod
    def _source_metadata(source_path: str) -> tuple[int, int]:
        stat = os.stat(source_path)
        return int(stat.st_mtime_ns), int(stat.st_size)

    def _write_disk_cache(
        self,
        cache_path: str,
        *,
        source_mtime_ns: int,
        source_size: int,
        data: JsonObject,
    ) -> bool:
        cache_file = Path(cache_path)
        temporary_path: Path | None = None
        try:
            descriptor, raw_temporary_path = tempfile.mkstemp(
                prefix=f".{cache_file.name}.",
                dir=cache_file.parent,
            )
            os.close(descriptor)
            temporary_path = Path(raw_temporary_path)
            cache_payload = {
                "__meta__": {"mtime_ns": source_mtime_ns, "size": source_size},
                "data": data,
            }
            with temporary_path.open("wb") as handle:
                pickle.dump(cache_payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temporary_path, cache_file)
            return True
        except OSError:
            return False
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def _load_json_with_disk_cache(
        self,
        source_path: str,
        *,
        bypass_cache: bool = False,
    ) -> JsonObject:
        if not self._cache_enabled():
            return self._read_json_object(source_path)

        try:
            source_mtime_ns, source_size = self._source_metadata(source_path)
        except OSError:
            return self._read_json_object(source_path)

        cache_path = self._cache_path_for_source(source_path)
        if not bypass_cache:
            try:
                with open(cache_path, "rb") as handle:
                    payload: Any = pickle.load(handle)
                if isinstance(payload, dict):
                    metadata = payload.get("__meta__")
                    cached_data = payload.get("data")
                    if (
                        isinstance(metadata, dict)
                        and int(metadata.get("mtime_ns", -1)) == source_mtime_ns
                        and int(metadata.get("size", -1)) == source_size
                        and isinstance(cached_data, dict)
                        and cached_data
                    ):
                        return cached_data
            except (OSError, pickle.PickleError, EOFError, TypeError, ValueError):
                pass

        data = self._read_json_object(source_path)
        self._write_disk_cache(
            cache_path,
            source_mtime_ns=source_mtime_ns,
            source_size=source_size,
            data=data,
        )
        return data

    def _load_primary_source(self) -> None:
        candidates = (
            ("app.bubble", self.app_json_path),
            ("consolelog", self.consolelog_json_path),
        )
        for source_name, source_path in candidates:
            if not source_path or not os.path.exists(source_path):
                continue
            try:
                if source_name == "consolelog":
                    print(f"[PathDiscovery] Opening consolelog: {source_path}")
                self._data = self._load_json_with_disk_cache(
                    source_path,
                    bypass_cache=self._force_source_reload,
                )
                self._data = self._normalize_api_connector_collections(self._data)
                self._data_source = source_name
                self._source_path = source_path
                if source_name == "consolelog":
                    self._logger.info(f"Using console.log fallback: {source_path}")
                return
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                self._logger.warning(
                    f"[PathDiscovery] Could not read {source_name} source at {source_path}: {exc}"
                )

    @property
    def data(self) -> JsonObject:
        """Lazily load the preferred source, then apply crawler and overlay enrichment."""

        if self._data is not None:
            return self._data

        try:
            self._load_primary_source()

            if self._data is not None and self.crawler_index_path and os.path.exists(
                self.crawler_index_path
            ):
                crawler = self._load_crawler_index(self.crawler_index_path)
                if crawler:
                    self._data = self._merge_crawler_into_data(self._data, crawler)
                    self._data_source = f"{self._data_source}+crawler"
                    self._logger.info(
                        f"[PathDiscovery] Merged crawler-index into {self._data_source} data"
                    )

            if self._data is not None and self.mutation_overlay_path and os.path.exists(
                self.mutation_overlay_path
            ):
                overlay_entries = self._load_mutation_overlay(self.mutation_overlay_path)
                if overlay_entries:
                    self._data = self._apply_mutation_overlay(self._data, overlay_entries)
                    self._data_source = f"{self._data_source}+overlay"
                    self._logger.info(
                        f"[PathDiscovery] Applied mutation overlay into {self._data_source} data"
                    )

            if self._data is None:
                self._logger.warning("No app data source found")
                self._data = {}
                self._data_source = "none"
                self._source_path = None

            self._logger.info(
                f" [DEBUG] load_discovery_cache: data loaded from {self._data_source}. "
                f"Keys: {list(self._data.keys())}"
            )
            return self._data
        finally:
            self._force_source_reload = False

    def refresh(self) -> JsonObject:
        """Force the next load to parse the configured source instead of using disk cache."""

        self._data = None
        self._data_source = None
        self._source_path = None
        self._force_source_reload = True
        return self.data

    @property
    def source_path(self) -> str | None:
        """Return the primary source path, independent of enrichment suffixes."""

        if self._data is None:
            _ = self.data
        return self._source_path

    def persist_disk_cache(self) -> bool:
        """Persist the current in-memory discovery snapshot to the active source cache."""

        if self._data is None or not self._cache_enabled():
            return False
        source_path = self.source_path
        if not source_path:
            return False
        try:
            source_mtime_ns, source_size = self._source_metadata(source_path)
        except OSError:
            return False
        return self._write_disk_cache(
            self._cache_path_for_source(source_path),
            source_mtime_ns=source_mtime_ns,
            source_size=source_size,
            data=self._data,
        )
