"""Discovery-first style reference resolution."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any

from .protocols import StyleReferenceHost


@dataclass(frozen=True)
class _StyleEntry:
    style_id: str
    name: str
    element_type: str
    is_default: bool
    properties: dict[str, Any]
    source: str
    aliases: tuple[str, ...] = ()


class StyleReferenceResolver:
    """Resolve style names and IDs against one normalized snapshot index."""

    _GENERIC_CONTROL_LABELS = {
        "input",
        "dropdown",
        "multilineinput",
        "multiline input",
        "dateinput",
        "date input",
        "searchbox",
        "search box",
        "autocompletedropdown",
        "autocomplete dropdown",
    }
    _DEFAULT_TOKENS = {"default", "standard", "std"}

    def __init__(self, host: StyleReferenceHost) -> None:
        self._host = host
        self._snapshot_identity: tuple[int, ...] | None = None
        self._entries: tuple[_StyleEntry, ...] = ()
        self._by_id: dict[str, _StyleEntry] = {}
        self._by_name: dict[str, tuple[_StyleEntry, ...]] = {}
        self._by_compact_name: dict[str, tuple[_StyleEntry, ...]] = {}
        self._catalog_labels: dict[str, tuple[str, ...]] = {}
        self._elements: tuple[dict[str, Any], ...] = ()

    def invalidate(self) -> None:
        """Force the next read to rebuild normalized snapshot indexes."""
        self._snapshot_identity = None

    @staticmethod
    def normalize_element_type(element_type: str | None) -> str:
        raw = str(element_type or "").strip()
        if not raw:
            return raw
        key = "".join(character for character in raw.lower() if character.isalnum())
        aliases = {
            "button": "Button",
            "text": "Text",
            "group": "Group",
            "popup": "Popup",
            "input": "Input",
            "multilineinput": "MultiLineInput",
            "dropdown": "Dropdown",
            "checkbox": "Checkbox",
            "radio": "RadioButtons",
            "radiobutton": "RadioButtons",
            "radiobuttons": "RadioButtons",
            "dateinput": "DateInput",
            "datepicker": "DateInput",
            "searchbox": "SearchBox",
            "autocompletedropdown": "AutocompleteDropdown",
            "fileinput": "FileInput",
            "pictureinput": "PictureInput",
            "pictureuploader": "PictureInput",
            "slider": "SliderInput",
            "sliderinput": "SliderInput",
            "alert": "Alert",
            "image": "Image",
            "icon": "Icon",
            "shape": "Shape",
            "video": "Video",
            "repeatinggroup": "RepeatingGroup",
            "floatinggroup": "FloatingGroup",
            "groupfocus": "GroupFocus",
            "page": "Page",
            "map": "GoogleMap",
            "googlemap": "GoogleMap",
            "html": "HTML",
            "link": "Link",
        }
        return aliases.get(key, raw)

    def default_style_settings_key(self, element_type: str | None) -> str:
        normalized = self.normalize_element_type(element_type)
        return {
            "SearchBox": "AutocompleteDropdown",
            "RadioButton": "RadioButtons",
        }.get(normalized, normalized)

    def configured_default_style_id(self, element_type: str | None) -> str | None:
        normalized = self.normalize_element_type(element_type)
        if not normalized:
            return None
        data, _ = self._host.style_reference_snapshots()
        settings = data.get("settings", {}) if isinstance(data, dict) else {}
        if not isinstance(settings, dict):
            return None
        client_safe = settings.get("client_safe", {})
        if not isinstance(client_safe, dict):
            return None
        default_styles = client_safe.get("default_styles", {})
        if not isinstance(default_styles, dict):
            return None
        for candidate in (self.default_style_settings_key(normalized), normalized):
            style_id = str(default_styles.get(candidate) or "").strip()
            if style_id:
                return style_id
        return None

    def first_available_style_id(self, element_type: str | None) -> str | None:
        normalized = self.normalize_element_type(element_type)
        if not normalized:
            return None
        configured = self.configured_default_style_id(normalized)
        if configured:
            return configured
        self._ensure_index()
        for prefer_default in (True, False):
            for entry in self._entries:
                if entry.is_default == prefer_default and self._type_matches(entry, normalized):
                    return entry.style_id
        return None

    @staticmethod
    def canonical_style_id(style_name: str, element_type: str) -> str | None:
        raw_name = str(style_name or "").strip()
        raw_type = str(element_type or "").strip()
        if not raw_name or not raw_type:
            return None
        if raw_name.lower().startswith(f"{raw_type.lower()}_") and "_" in raw_name:
            return raw_name
        normalized_name = "".join(
            character
            for character in raw_name.lower().replace(" ", "_")
            if character.isalnum() or character == "_"
        )
        if not normalized_name:
            return None
        return f"{raw_type}_{normalized_name}_"

    @staticmethod
    def looks_like_style_id(value: Any, element_type: str | None = None) -> bool:
        raw = str(value or "").strip()
        if not raw or "_" not in raw:
            return False
        if element_type:
            prefix = str(element_type).strip().lower() + "_"
            return raw.lower().startswith(prefix) and len(raw) > len(prefix)
        return bool(re.match(r"^[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+_?$", raw))

    def find_style_id(self, name: str, element_type: str | None = None) -> str | None:
        raw = str(name or "").strip()
        if not raw:
            return None
        self._ensure_index()
        normalized_type = self.normalize_element_type(element_type)
        normalized_name = self._host.normalize_style_reference(raw)
        compact_name = self._host.compact_style_reference(raw)

        if normalized_type and normalized_name in self._GENERIC_CONTROL_LABELS:
            configured = self.configured_default_style_id(normalized_type)
            if configured:
                return configured

        exact_candidates = list(self._by_name.get(normalized_name, ()))
        exact_candidates.extend(self._by_compact_name.get(compact_name, ()))
        for entry in self._dedupe_entries(exact_candidates):
            if self._type_matches(entry, normalized_type):
                return entry.style_id

        catalog_style = self._find_catalog_style(raw, normalized_type)
        if catalog_style:
            return catalog_style

        if normalized_type:
            canonical_id = self.canonical_style_id(raw, normalized_type)
            canonical_entry = self._by_id.get(str(canonical_id or ""))
            if canonical_entry and self._type_matches(canonical_entry, normalized_type):
                return canonical_entry.style_id

        target_tokens = set(re.findall(r"[a-z0-9]+", normalized_name))
        if target_tokens:
            for entry in self._entries:
                if not self._type_matches(entry, normalized_type):
                    continue
                candidate_tokens = set(re.findall(r"[a-z0-9]+", f"{entry.name} {entry.style_id}".lower()))
                if target_tokens.issubset(candidate_tokens):
                    return entry.style_id

        normalized_underscores = raw.lower().replace(" ", "_")
        for entry in self._entries:
            if not self._type_matches(entry, normalized_type):
                continue
            if f"_{normalized_underscores}_" in f"_{entry.style_id.lower()}_":
                return entry.style_id

        if normalized_type and target_tokens & self._DEFAULT_TOKENS:
            return self.first_available_style_id(normalized_type)
        return None

    def resolve(
        self,
        value: str | None,
        element_type: str | None = None,
        strict: bool = False,
    ) -> str | None:
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        self._ensure_index()
        normalized_type = self.normalize_element_type(element_type)
        raw_tokens = set(re.findall(r"[a-z0-9]+", raw.lower()))

        if normalized_type == "Button" and not (raw_tokens & self._DEFAULT_TOKENS):
            semantic = self._infer_semantic_button_style(raw)
            if semantic:
                return semantic

        resolved = self.find_style_id(raw, normalized_type or None)
        if resolved:
            return resolved

        known_ids = self.known_style_ids(normalized_type or None)
        if self.looks_like_style_id(raw, normalized_type or None):
            if raw in known_ids or not strict:
                return raw
            return None

        inferred = self.canonical_style_id(raw, normalized_type)
        if inferred:
            if not known_ids or inferred in known_ids:
                return inferred
            if strict and not self.known_non_default_style_ids(normalized_type):
                return inferred
            return None

        fallback = self.first_available_style_id(normalized_type or None)
        if fallback:
            return fallback
        return None

    def infer_element_type(self, style_id: str | None) -> str | None:
        sid = str(style_id or "").strip()
        if not sid:
            return None
        self._ensure_index()
        entry = self._by_id.get(sid)
        return entry.element_type or None if entry else None

    def base_properties(self, style_id: str) -> dict[str, Any]:
        self._ensure_index()
        entry = self._by_id.get(str(style_id or "").strip())
        return dict(entry.properties) if entry else {}

    def known_style_ids(self, element_type: str | None = None) -> set[str]:
        self._ensure_index()
        normalized_type = self.normalize_element_type(element_type)
        return {
            entry.style_id
            for entry in self._entries
            if self._type_matches(entry, normalized_type)
        }

    def known_non_default_style_ids(self, element_type: str | None = None) -> set[str]:
        self._ensure_index()
        normalized_type = self.normalize_element_type(element_type)
        return {
            entry.style_id
            for entry in self._entries
            if not entry.is_default and self._type_matches(entry, normalized_type)
        }

    def current_snapshot_style_ids(self, element_type: str | None = None) -> set[str]:
        data, _ = self._host.style_reference_snapshots()
        styles = data.get("styles", {}) if isinstance(data, dict) else {}
        if not isinstance(styles, dict):
            return set()
        normalized_type = self.normalize_element_type(element_type)
        result: set[str] = set()
        for style_id, raw_style in styles.items():
            sid = str(style_id or "").strip()
            if not sid:
                continue
            style = raw_style if isinstance(raw_style, dict) else {}
            candidate_type = str(style.get("type") or style.get("%x") or "").strip()
            entry = _StyleEntry(sid, sid, candidate_type, False, {}, "discovery")
            if self._type_matches(entry, normalized_type):
                result.add(sid)
        return result

    @staticmethod
    def _dedupe_entries(entries: list[_StyleEntry]) -> list[_StyleEntry]:
        result: list[_StyleEntry] = []
        seen: set[str] = set()
        for entry in entries:
            if entry.style_id not in seen:
                seen.add(entry.style_id)
                result.append(entry)
        return result

    def _type_matches(self, entry: _StyleEntry, element_type: str) -> bool:
        if not element_type:
            return True
        candidates = {
            self.normalize_element_type(element_type).lower(),
            self.default_style_settings_key(element_type).lower(),
        }
        entry_type = self.normalize_element_type(entry.element_type).lower()
        if entry_type:
            return entry_type in candidates
        return entry.style_id.lower().startswith(tuple(f"{candidate}_" for candidate in candidates))

    def _ensure_index(self) -> None:
        data, cache = self._host.style_reference_snapshots()
        data_styles = data.get("styles") if isinstance(data, dict) else None
        cache_styles = cache.get("styles") if isinstance(cache, dict) else None
        settings = data.get("settings") if isinstance(data, dict) else None
        identity = (id(data), id(cache), id(data_styles), id(cache_styles), id(settings))
        if identity == self._snapshot_identity:
            return
        self._build_index(data, cache)
        self._snapshot_identity = identity

    def _build_index(self, data: dict[str, Any], cache: dict[str, Any]) -> None:
        entries: dict[str, _StyleEntry] = {}
        order: list[str] = []

        def add_discovery(style_id: Any, style: Any, fallback_name: Any = "", is_default: bool = False) -> None:
            sid = str(style_id or "").strip()
            if not sid:
                return
            payload = style if isinstance(style, dict) else {}
            name = str(
                payload.get("name")
                or payload.get("display")
                or payload.get("%d")
                or fallback_name
                or sid
            ).strip()
            element_type = str(payload.get("type") or payload.get("%x") or "").strip()
            raw_properties = payload.get("%p")
            properties: dict[str, Any] = raw_properties if isinstance(raw_properties, dict) else {}
            existing = entries.get(sid)
            if existing is None:
                entries[sid] = _StyleEntry(
                    sid,
                    name,
                    element_type,
                    bool(is_default or payload.get("is_default")),
                    dict(properties),
                    "discovery",
                )
                order.append(sid)
                return
            entries[sid] = replace(
                existing,
                name=name if name != sid or existing.name == sid else existing.name,
                element_type=element_type or existing.element_type,
                is_default=existing.is_default or bool(is_default or payload.get("is_default")),
                properties=dict(properties) if properties else existing.properties,
            )

        settings = data.get("settings", {}) if isinstance(data, dict) else {}
        client_safe = settings.get("client_safe", {}) if isinstance(settings, dict) else {}
        defaults = client_safe.get("default_styles", {}) if isinstance(client_safe, dict) else {}
        if isinstance(defaults, dict):
            for element_type, style_id in defaults.items():
                add_discovery(
                    style_id,
                    {"type": element_type, "name": f"{element_type} (default)"},
                    is_default=True,
                )

        for style in self._host.list_style_references():
            if not isinstance(style, dict):
                continue
            add_discovery(
                style.get("id"),
                style,
                style.get("name"),
                bool(style.get("is_default")),
            )

        raw_styles = data.get("styles", {}) if isinstance(data, dict) else {}
        if isinstance(raw_styles, dict):
            for style_id, style in raw_styles.items():
                add_discovery(style_id, style)

        cached_styles = cache.get("styles", {}) if isinstance(cache, dict) else {}
        if isinstance(cached_styles, dict):
            for cached_name, raw_style in cached_styles.items():
                if not isinstance(raw_style, dict):
                    continue
                if bool(raw_style.get("%del") or raw_style.get("deleted")):
                    continue
                sid = str(raw_style.get("id") or "").strip()
                if not sid:
                    continue
                existing = entries.get(sid)
                alias = str(cached_name or "").strip()
                if existing:
                    if alias and alias not in existing.aliases and alias != existing.name:
                        entries[sid] = replace(existing, aliases=(*existing.aliases, alias))
                    continue
                element_type = str(raw_style.get("type") or raw_style.get("%x") or "").strip()
                raw_properties = raw_style.get("%p")
                properties = raw_properties if isinstance(raw_properties, dict) else {}
                entries[sid] = _StyleEntry(
                    sid,
                    alias or sid,
                    element_type,
                    False,
                    dict(properties),
                    "cache",
                )
                order.append(sid)

        self._entries = tuple(entries[style_id] for style_id in order)
        self._by_id = {entry.style_id: entry for entry in self._entries}
        name_buckets: dict[str, list[_StyleEntry]] = {}
        compact_buckets: dict[str, list[_StyleEntry]] = {}
        for entry in self._entries:
            for label in (entry.name, entry.style_id, *entry.aliases):
                normalized = self._host.normalize_style_reference(label)
                compact = self._host.compact_style_reference(label)
                if normalized:
                    name_buckets.setdefault(normalized, []).append(entry)
                if compact:
                    compact_buckets.setdefault(compact, []).append(entry)
        self._by_name = {key: tuple(value) for key, value in name_buckets.items()}
        self._by_compact_name = {key: tuple(value) for key, value in compact_buckets.items()}

        self._elements = tuple(
            row for row in self._host.list_style_reference_elements() if isinstance(row, dict)
        )
        catalog: dict[str, list[str]] = {}
        for row in self._elements:
            element = row.get("element")
            if not isinstance(element, dict):
                continue
            raw_props = element.get("%p")
            props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
            text_payload = props.get("text") or props.get("%3") or element.get("text")
            label = self._host.plain_style_reference_text(text_payload)
            style_id = str(element.get("%s1") or element.get("style") or props.get("%s1") or "").strip()
            compact = self._host.compact_style_reference(label)
            if compact and style_id and style_id in self._by_id:
                bucket = catalog.setdefault(compact, [])
                if style_id not in bucket:
                    bucket.append(style_id)
        self._catalog_labels = {key: tuple(value) for key, value in catalog.items()}

    def _find_catalog_style(self, name: str, element_type: str) -> str | None:
        compact = self._host.compact_style_reference(name)
        for style_id in self._catalog_labels.get(compact, ()):
            entry = self._by_id.get(style_id)
            if entry and self._type_matches(entry, element_type):
                return style_id
        return None

    def _infer_semantic_button_style(self, name: str) -> str | None:
        if self.looks_like_style_id(name, "Button"):
            return None
        tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
        if not tokens:
            return None
        size = next((candidate for candidate in ("xs", "sm", "md", "lg", "xl", "2xl") if candidate in tokens), None)
        hierarchy = next(
            (
                candidate
                for candidate in (
                    "primary",
                    "secondary",
                    "tertiary",
                    "destructive",
                    "success",
                    "warning",
                    "ghost",
                    "link",
                    "breadcrumb",
                )
                if candidate in tokens
            ),
            None,
        )
        matches: list[tuple[int, str]] = []
        seen: set[str] = set()
        current_ids = self.current_snapshot_style_ids("Button")
        for row in self._elements:
            element = row.get("element")
            if not isinstance(element, dict):
                continue
            if self.normalize_element_type(str(element.get("%x") or element.get("type") or "")) != "Button":
                continue
            raw_props = element.get("%p")
            props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
            style_id = str(element.get("%s1") or element.get("style") or props.get("%s1") or "").strip()
            if not style_id or style_id in seen or style_id not in current_ids:
                continue
            seen.add(style_id)
            text_payload = props.get("text") or props.get("%3") or element.get("text")
            text = self._host.plain_style_reference_text(text_payload)
            blob = " ".join((str(element.get("%nm") or ""), str(element.get("%dn") or ""), text)).lower()
            blob_tokens = set(re.findall(r"[a-z0-9]+", blob))
            gallery = "buttons/button" in blob or ("hierarchy=" in blob and "size=" in blob)
            size_ok = size is None or f"size={size}" in blob or size in blob_tokens
            hierarchy_ok = hierarchy is None or f"hierarchy={hierarchy}" in blob or hierarchy in blob_tokens
            button_ok = "button" not in tokens or "button" in blob_tokens
            if not (size_ok and hierarchy_ok and button_ok):
                continue
            entry = self._by_id.get(style_id)
            has_states = bool(entry and self._raw_style_has_states(style_id))
            generated = bool(re.fullmatch(r"Button_b[A-Za-z0-9]{4,}", style_id))
            matches.append((100 * has_states + 20 * generated + 10 * gallery, style_id))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def _raw_style_has_states(self, style_id: str) -> bool:
        data, _ = self._host.style_reference_snapshots()
        styles = data.get("styles", {}) if isinstance(data, dict) else {}
        style = styles.get(style_id, {}) if isinstance(styles, dict) else {}
        return isinstance(style, dict) and isinstance(style.get("%s"), dict) and bool(style.get("%s"))
