"""Current-first typed references for Bubble data schema settings."""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from .protocols import SchemaReferenceHost


Source = Literal["current", "module", "cache"]


@dataclass(frozen=True)
class SchemaReferenceResult:
    """Immutable successful lookup result, including the source that supplied it."""

    key: str
    source: Source


@dataclass(frozen=True)
class SchemaReferenceSnapshot:
    """Immutable, normalized input maps used to build resolver indexes."""

    user_types: dict[str, dict[str, Any]]
    option_sets: dict[str, dict[str, Any]]
    redirects: dict[str, dict[str, Any]]
    user_type_sources: dict[str, Source]
    option_set_sources: dict[str, Source]
    redirect_sources: dict[str, Source]


@dataclass(frozen=True)
class _EntryIndex:
    """Normalized exact-match indexes for one immutable entry map."""

    keys: dict[str, tuple[str, ...]]
    labels: dict[str, tuple[str, ...]]


class SchemaReferenceResolver:
    """Resolve typed schema IDs from detached, current-first snapshots."""

    _FAMILIES = frozenset({"user_types", "option_sets", "redirects"})

    def __init__(self, host: SchemaReferenceHost) -> None:
        self._host = host
        self._revision: int | None = None
        self._current = SchemaReferenceSnapshot({}, {}, {}, {}, {}, {})
        self._with_cache = SchemaReferenceSnapshot({}, {}, {}, {}, {}, {})
        self._entry_indexes: dict[tuple[int, tuple[str, ...]], _EntryIndex] = {}
        self._dirty_families = set(self._FAMILIES)

    def invalidate(self, *families: str) -> None:
        """Force the next lookup to rebuild from the host's projected state."""
        requested = set(families) if families else set(self._FAMILIES)
        self._dirty_families.update(requested & self._FAMILIES)

    def user_types(self, *, include_cache: bool = True) -> dict[str, Any]:
        return copy.deepcopy(self._snapshot(include_cache).user_types)

    def option_sets(self, *, include_cache: bool = True) -> dict[str, Any]:
        return copy.deepcopy(self._snapshot(include_cache).option_sets)

    def option_values(self, option_set_key: str, *, include_cache: bool = True) -> dict[str, Any] | None:
        option_set = self._snapshot(include_cache).option_sets.get(str(option_set_key or "").strip())
        if not isinstance(option_set, dict):
            return None
        values = option_set.get("values")
        return copy.deepcopy(values) if isinstance(values, dict) else None

    def redirects(self) -> dict[str, Any]:
        return copy.deepcopy(self._snapshot(False).redirects)

    def resolve_data_type(
        self,
        value: str,
        *,
        ref_kind: str = "key",
        include_cache: bool = True,
    ) -> str | None:
        raw = self._strip_custom_prefix(value)
        if not raw:
            return None
        entries = self._snapshot(include_cache).user_types
        if (
            self._kind(ref_kind) in {"key", "auto", "label", "name", "display"}
            and self._host.normalize_schema_reference(raw) in {"user", "current user", "current_user"}
            and entries
        ):
            return "user"
        return self._resolve_entries(entries, raw, ref_kind=ref_kind, label_keys=("%d", "display", "name"))

    def resolve_data_field(
        self,
        data_type_ref: str,
        value: str,
        *,
        ref_kind: str = "key",
        include_cache: bool = True,
    ) -> str | None:
        type_key = self.resolve_data_type(data_type_ref, ref_kind="auto", include_cache=include_cache)
        if not type_key:
            return None
        entry = self._snapshot(include_cache).user_types.get(type_key)
        fields = self._fields(entry)
        return self._resolve_entries(fields, str(value or "").strip(), ref_kind=ref_kind, label_keys=("%d", "display", "name"))

    def resolve_option_set(
        self,
        value: str,
        *,
        ref_kind: str = "key",
        include_cache: bool = True,
    ) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        entries = self._snapshot(include_cache).option_sets
        aliases = self._option_set_key_aliases(raw)
        for alias in aliases:
            if alias in entries and self._kind_allows_key(ref_kind):
                return alias
        return self._resolve_entries(entries, raw, ref_kind=ref_kind, label_keys=("%d", "display", "name"))

    def resolve_option_value(
        self,
        option_set_ref: str,
        value: str,
        *,
        ref_kind: str = "key",
        include_cache: bool = True,
    ) -> str | None:
        option_key = self.resolve_option_set(option_set_ref, ref_kind="auto", include_cache=include_cache)
        if not option_key:
            return None
        option_set = self._snapshot(include_cache).option_sets.get(option_key)
        values = option_set.get("values") if isinstance(option_set, dict) else None
        if not isinstance(values, dict):
            return None
        kind = self._kind(ref_kind)
        raw = str(value or "").strip()
        if not raw:
            return None
        if kind in {"key", "auto"} and raw in values:
            return raw
        label_keys: tuple[str, ...] = (
            ("db_value", "%d", "display") if kind in {"key", "auto"} else ("%d", "display")
        )
        if kind in {"db", "db_value", "db-value"}:
            label_keys = ("db_value",)
        return self._resolve_entries(values, raw, ref_kind="label", label_keys=label_keys)

    def resolve_redirect(self, value: str, *, ref_kind: str = "key") -> str | None:
        return self._resolve_entries(
            self._snapshot(False).redirects,
            str(value or "").strip(),
            ref_kind=ref_kind,
            label_keys=("%fr", "from", "to"),
        )

    def data_type_result(self, value: str, *, ref_kind: str = "key", include_cache: bool = True) -> SchemaReferenceResult | None:
        key = self.resolve_data_type(value, ref_kind=ref_kind, include_cache=include_cache)
        if not key:
            return None
        source = self._snapshot(include_cache).user_type_sources.get(key)
        return SchemaReferenceResult(key, source) if source is not None else None

    def _snapshot(self, include_cache: bool) -> SchemaReferenceSnapshot:
        revision = self._host.schema_reference_revision()
        if self._revision != revision:
            self._dirty_families.update(self._FAMILIES)
        if self._dirty_families:
            self._rebuild(revision, self._dirty_families)
            self._dirty_families.clear()
        return self._with_cache if include_cache else self._current

    def _rebuild(self, revision: int, families: set[str]) -> None:
        discovery, cache = self._host.schema_reference_snapshots()
        cache_types, cache_sets = self._cache_maps(cache)
        root = self._host.schema_reference_modules_dir()

        if "user_types" in families:
            self._discard_indexes(self._current.user_types, self._with_cache.user_types)
            current_types = self._normalized_map(discovery.get("user_types") if isinstance(discovery, dict) else None)
            current_sources: dict[str, Source] = {key: "current" for key in current_types}
            module_types = self._module_family(root, "user_types", include_values=False) if root else {}
            self._merge_missing(current_types, module_types, current_sources, "module")
            with_cache_types = copy.deepcopy(current_types)
            with_cache_sources = dict(current_sources)
            self._merge_missing(with_cache_types, cache_types, with_cache_sources, "cache")
            self._current = replace(self._current, user_types=current_types, user_type_sources=current_sources)
            self._with_cache = replace(
                self._with_cache,
                user_types=with_cache_types,
                user_type_sources=with_cache_sources,
            )

        if "option_sets" in families:
            self._discard_indexes(self._current.option_sets, self._with_cache.option_sets)
            current_sets = self._normalized_map(discovery.get("option_sets") if isinstance(discovery, dict) else None)
            current_sources = {key: "current" for key in current_sets}
            module_sets = self._module_family(root, "option_sets", include_values=True) if root else {}
            self._merge_missing(current_sets, module_sets, current_sources, "module")
            self._normalize_option_values(current_sets)
            with_cache_sets = copy.deepcopy(current_sets)
            with_cache_sources = dict(current_sources)
            self._merge_missing(with_cache_sets, cache_sets, with_cache_sources, "cache")
            self._normalize_option_values(with_cache_sets)
            self._current = replace(self._current, option_sets=current_sets, option_set_sources=current_sources)
            self._with_cache = replace(
                self._with_cache,
                option_sets=with_cache_sets,
                option_set_sources=with_cache_sources,
            )

        if "redirects" in families:
            self._discard_indexes(self._current.redirects, self._with_cache.redirects)
            redirects = self._redirects(discovery)
            redirect_sources: dict[str, Source] = {key: "current" for key in redirects}
            self._current = replace(self._current, redirects=redirects, redirect_sources=redirect_sources)
            self._with_cache = replace(
                self._with_cache,
                redirects=copy.deepcopy(redirects),
                redirect_sources=dict(redirect_sources),
            )
        self._revision = revision

    @staticmethod
    def _is_live(value: Any) -> bool:
        return isinstance(value, dict) and value.get("%del") is not True

    def _normalized_map(self, value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key): copy.deepcopy(entry)
            for key, entry in value.items()
            if str(key).strip() and self._is_live(entry)
        }

    def _cache_maps(self, cache: Any) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        if not isinstance(cache, dict):
            return {}, {}
        schema = cache.get("schema")
        profiles = schema.get("profiles") if isinstance(schema, dict) else None
        profile_key = self._host.schema_reference_profile_key()
        profile = profiles.get(profile_key) if isinstance(profiles, dict) else None
        if not isinstance(profile, dict):
            return {}, {}
        return self._normalized_map(profile.get("user_types")), self._normalized_map(profile.get("option_sets"))

    @staticmethod
    def _merge_missing(
        target: dict[str, dict[str, Any]],
        incoming: dict[str, dict[str, Any]],
        sources: dict[str, Source],
        source: Source,
    ) -> None:
        for key, value in incoming.items():
            current = target.get(key)
            if current is None:
                target[key] = copy.deepcopy(value)
                sources[key] = source
                continue
            for name in ("%d", "display", "name", "%f3", "fields", "values"):
                if not current.get(name) and value.get(name):
                    current[name] = copy.deepcopy(value[name])

    def _module_family(self, root: str, family: str, *, include_values: bool) -> dict[str, dict[str, Any]]:
        directory = os.path.join(root, family)
        index = self._read_json(os.path.join(directory, "__index.json"))
        if not isinstance(index, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for raw_key, display in index.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            entry: dict[str, Any] = {"%d": display if isinstance(display, str) else key, "display": display if isinstance(display, str) else key}
            payload = self._read_json(os.path.join(directory, f"{key}.json"))
            if isinstance(payload, dict):
                entry.update({name: copy.deepcopy(value) for name, value in payload.items() if name != "%del"})
            if include_values:
                values = entry.get("values")
                if isinstance(values, dict):
                    entry["values"] = self._normalized_map(values)
            result[key] = entry
        return result

    def _discard_indexes(self, *entries: dict[str, dict[str, Any]]) -> None:
        ids: set[int] = set()

        def collect(value: Any) -> None:
            if not isinstance(value, dict):
                return
            value_id = id(value)
            if value_id in ids:
                return
            ids.add(value_id)
            for child in value.values():
                collect(child)

        for entry in entries:
            collect(entry)
        self._entry_indexes = {
            key: index for key, index in self._entry_indexes.items() if key[0] not in ids
        }

    @staticmethod
    def _read_json(path: str) -> Any:
        try:
            with open(path, encoding="utf-8") as file:
                return json.load(file)
        except (OSError, ValueError, TypeError):
            return None

    def _redirects(self, discovery: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(discovery, dict):
            return {}
        settings = discovery.get("settings")
        client_safe = settings.get("client_safe") if isinstance(settings, dict) else None
        return self._normalized_map(client_safe.get("301_redirects") if isinstance(client_safe, dict) else None)

    def _normalize_option_values(self, option_sets: dict[str, dict[str, Any]]) -> None:
        for entry in option_sets.values():
            values = entry.get("values")
            if not isinstance(values, dict):
                continue
            entry["values"] = self._normalized_map(values)
            for value in entry["values"].values():
                if not value.get("%d") and isinstance(value.get("display"), str):
                    value["%d"] = value["display"]

    @staticmethod
    def _fields(entry: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(entry, dict):
            return {}
        fields = entry.get("%f3") if isinstance(entry.get("%f3"), dict) else entry.get("fields")
        if not isinstance(fields, dict):
            return {}
        return {str(key): value for key, value in fields.items() if str(key).strip() and isinstance(value, dict) and value.get("%del") is not True}

    def _resolve_entries(
        self,
        entries: dict[str, dict[str, Any]],
        raw: str,
        *,
        ref_kind: str,
        label_keys: tuple[str, ...],
    ) -> str | None:
        if not raw or not entries:
            return None
        kind = self._kind(ref_kind)
        if kind in {"key", "auto"} and raw in entries:
            return raw
        needle = self._host.normalize_schema_reference(raw)
        if not needle:
            return None
        index = self._entry_index(entries, label_keys)
        normalized_forms = self._normalized_forms(needle)
        if kind in {"key", "auto"}:
            key_matches = self._indexed_matches(index.keys, normalized_forms)
            if len(key_matches) == 1:
                return key_matches[0]
            if len(key_matches) > 1:
                return None
        if kind in {"key", "auto", "label", "name", "display", "db", "db_value", "db-value"}:
            exact = self._indexed_matches(index.labels, normalized_forms)
            if len(exact) == 1:
                return exact[0]
            if len(exact) > 1:
                return None
            substring = self._substring_label_matches(entries, needle, label_keys)
            return substring[0] if len(substring) == 1 else None
        return None

    def _entry_index(self, entries: dict[str, dict[str, Any]], label_keys: tuple[str, ...]) -> _EntryIndex:
        cache_key = (id(entries), label_keys)
        cached = self._entry_indexes.get(cache_key)
        if cached is not None:
            return cached
        keys: dict[str, list[str]] = {}
        labels: dict[str, list[str]] = {}
        for key, entry in entries.items():
            for normalized in self._normalized_forms(self._host.normalize_schema_reference(key)):
                keys.setdefault(normalized, []).append(key)
            if not isinstance(entry, dict):
                continue
            for label_key in label_keys:
                for normalized in self._normalized_forms(self._host.normalize_schema_reference(entry.get(label_key))):
                    labels.setdefault(normalized, []).append(key)
        index = _EntryIndex(
            keys={normalized: tuple(dict.fromkeys(matches)) for normalized, matches in keys.items()},
            labels={normalized: tuple(dict.fromkeys(matches)) for normalized, matches in labels.items()},
        )
        self._entry_indexes[cache_key] = index
        return index

    @staticmethod
    def _indexed_matches(index: dict[str, tuple[str, ...]], normalized_forms: tuple[str, ...]) -> list[str]:
        return list(dict.fromkeys(key for normalized in normalized_forms for key in index.get(normalized, ())))

    @staticmethod
    def _normalized_forms(value: str) -> tuple[str, ...]:
        if not value:
            return ()
        compact = re.sub(r"[^a-z0-9]+", "", value)
        return (value,) if not compact or compact == value else (value, compact)

    def _substring_label_matches(
        self,
        entries: dict[str, dict[str, Any]],
        needle: str,
        label_keys: tuple[str, ...],
    ) -> list[str]:
        matches: list[str] = []
        for key, data in entries.items():
            if not isinstance(data, dict):
                continue
            for label_key in label_keys:
                candidate = self._host.normalize_schema_reference(data.get(label_key))
                if not candidate:
                    continue
                if needle in candidate or candidate in needle:
                    matches.append(key)
                    break
        return matches

    @staticmethod
    def _kind(value: str) -> str:
        return str(value or "key").strip().lower()

    def _kind_allows_key(self, value: str) -> bool:
        return self._kind(value) in {"key", "auto"}

    @staticmethod
    def _strip_custom_prefix(value: str) -> str:
        raw = str(value or "").strip()
        return raw.split(".", 1)[1].strip() if raw.lower().startswith("custom.") else raw

    def _option_set_key_aliases(self, raw: str) -> tuple[str, ...]:
        candidates = [raw]
        lower = raw.lower()
        if lower.startswith("option."):
            candidates.append(raw.split(".", 1)[1])
        if lower.startswith("os:"):
            slug = self._host.slugify_schema_reference(raw.split(":", 1)[1])
            if slug:
                candidates.append(f"os_{slug}")
        if lower.startswith("os_"):
            slug = self._host.slugify_schema_reference(raw[3:])
            if slug:
                candidates.append(f"os_{slug}")
        return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))
