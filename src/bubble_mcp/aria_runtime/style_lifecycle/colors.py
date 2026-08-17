"""Discovery-first color token reads and grouped lifecycle writes."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any, Mapping, cast

if TYPE_CHECKING:
    from ..bubble_sdk import ColorBuilder, DEFAULT_COLOR_NAMES, PayloadBuilder
else:
    try:
        from ..bubble_sdk import ColorBuilder, DEFAULT_COLOR_NAMES, PayloadBuilder
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import ColorBuilder, DEFAULT_COLOR_NAMES, PayloadBuilder

from .protocols import StyleTokenHost, TokenMutationResult, dispatch_token_mutation


@dataclass(frozen=True)
class ColorSnapshot:
    """One normalized, detached view of default and custom color tokens."""

    defaults: dict[str, Any]
    custom: dict[str, dict[str, Any]]
    wire_custom: dict[str, Any]


class ColorTokenService:
    """Resolve and mutate Bubble color tokens through one host boundary."""

    _WEB_COLORS = {
        "white": "#FFFFFF",
        "black": "#000000",
        "red": "#FF0000",
        "green": "#008000",
        "blue": "#0000FF",
        "yellow": "#FFFF00",
        "orange": "#FFA500",
        "purple": "#800080",
        "gray": "#808080",
        "grey": "#808080",
        "transparent": "rgba(0,0,0,0)",
    }

    def __init__(self, host: StyleTokenHost) -> None:
        self._host = host

    def snapshot(self) -> ColorSnapshot:
        discovery, cache = self._host.style_reference_snapshots()
        client_safe = self._client_safe(discovery)
        defaults = self._normalize_defaults(client_safe.get("color_tokens"))
        wire_custom = self._custom_wire_map(client_safe.get("color_tokens_user"))
        custom = self._normalize_custom_map(wire_custom)
        wire_custom.update(copy.deepcopy(custom))
        cache_colors = cache.get("colors") if isinstance(cache, dict) else None
        if isinstance(cache_colors, Mapping):
            for token_id, raw_entry in cache_colors.items():
                color_id = str(token_id or "").strip()
                if not color_id or color_id in wire_custom:
                    continue
                entry = self._normalize_custom_entry(raw_entry)
                if self._valid_custom_entry(entry):
                    custom[color_id] = entry
                    wire_custom[color_id] = copy.deepcopy(entry)
        return ColorSnapshot(defaults=defaults, custom=custom, wire_custom=wire_custom)

    def active_custom(self) -> dict[str, dict[str, Any]]:
        return self._active_custom(self.snapshot())

    def next_order(self) -> int:
        return self._next_order(self.snapshot().custom)

    def find(self, name: str) -> tuple[str, str, Any] | None:
        return self._find(self.snapshot(), name)

    def resolve(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return value
        snapshot = self.snapshot()
        normalized = self._normalize_name(raw)
        for token_id, entry in snapshot.custom.items():
            if bool(entry.get("%del")):
                continue
            if normalized in {
                self._normalize_name(token_id),
                self._normalize_name(entry.get("%nm")),
            }:
                return f"var(--color_{token_id}_default)"
        found = self._find(snapshot, raw)
        if found:
            token_type, token_id, _ = found
            return f"var(--color_{token_id}_default)"
        return self._WEB_COLORS.get(raw.lower(), value)

    def update(self, name: str, rgba: str, *, dry_run: bool = False) -> TokenMutationResult:
        snapshot = self.snapshot()
        found = self._find(snapshot, name)
        if found is None:
            return self._failure(f"Color '{name}' not found")
        token_type, token_id, current = found
        payload = self._payload()
        if token_type == "default":
            payload.add_change_app_setting(
                ColorBuilder.get_default_color_path() + [token_id],
                {"%d1": rgba},
            )
            return self._dispatch(payload, dry_run=dry_run, token_id=token_id)

        all_colors = dict(snapshot.wire_custom)
        updated = dict(current)
        updated["rgba"] = rgba
        all_colors[token_id] = updated
        payload.add_change_app_setting(
            ColorBuilder.get_custom_color_path(),
            ColorBuilder.build_custom_colors_body(all_colors),
        )
        return self._dispatch(
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=lambda: self._host.put_style_token_cache("colors", token_id, updated),
        )

    def create(
        self,
        name: str,
        rgba: str,
        description: str = "",
        *,
        dry_run: bool = False,
    ) -> TokenMutationResult:
        snapshot = self.snapshot()
        if self._find(snapshot, name) is not None:
            return self._failure(f"Color '{name}' already exists")
        builder = ColorBuilder()
        token_id = builder.generate_color_id()
        entry = ColorBuilder.build_color_entry(
            name=name,
            rgba=rgba,
            order=self._next_order(snapshot.custom),
            description=description,
        )
        all_colors = dict(snapshot.wire_custom)
        all_colors[token_id] = entry
        payload = self._payload()
        payload.add_change_app_setting(
            ColorBuilder.get_custom_color_path(),
            ColorBuilder.build_custom_colors_body(all_colors),
        )
        return self._dispatch(
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=lambda: self._host.put_style_token_cache("colors", token_id, entry),
        )

    def delete(self, name: str, *, dry_run: bool = False) -> TokenMutationResult:
        snapshot = self.snapshot()
        found = self._find(snapshot, name)
        if found is None:
            return self._failure(f"Color '{name}' not found")
        token_type, token_id, current = found
        if token_type == "default":
            return self._failure("Cannot delete default colors")
        all_colors = dict(snapshot.wire_custom)
        deleted = dict(current)
        deleted["%del"] = True
        all_colors[token_id] = deleted
        payload = self._custom_payload(all_colors)
        return self._dispatch(
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=lambda: self._host.remove_style_token_cache("colors", token_id),
        )

    def clear(self, *, dry_run: bool = False) -> TokenMutationResult:
        payload = self._custom_payload({})
        return self._dispatch(
            payload,
            dry_run=dry_run,
            after=lambda: self._host.clear_style_token_cache("colors"),
        )

    def delete_many(
        self,
        names: list[str] | None = None,
        pattern: str | None = None,
        *,
        dry_run: bool = False,
    ) -> TokenMutationResult:
        snapshot = self.snapshot()
        active = self._active_custom(snapshot)
        if not active:
            return self._failure("No custom colors found")
        requested = {self._normalize_name(name) for name in names or [] if str(name or "").strip()}
        regex: re.Pattern[str] | None = None
        if pattern:
            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                return self._failure(str(exc))
        target_ids: list[str] = []
        for token_id, entry in active.items():
            token_name = str(entry.get("%nm") or "")
            if self._normalize_name(token_name) in requested or (regex and regex.search(token_name)):
                target_ids.append(token_id)
        if not target_ids:
            return self._failure("No matching colors found to delete")

        all_colors = dict(snapshot.wire_custom)
        for token_id in target_ids:
            deleted = dict(all_colors[token_id])
            deleted["%del"] = True
            all_colors[token_id] = deleted
        payload = self._custom_payload(all_colors)

        def remove_targets() -> None:
            self._host.apply_style_token_cache_batch(
                "colors",
                upserts={},
                removals=tuple(target_ids),
            )

        return self._dispatch(payload, dry_run=dry_run, after=remove_targets)

    def reorder(
        self,
        mode: str,
        color_name: str | None = None,
        target: str | None = None,
        *,
        dry_run: bool = False,
    ) -> TokenMutationResult:
        snapshot = self.snapshot()
        active = self._active_custom(snapshot)
        if not active:
            return TokenMutationResult(ok=True)
        if mode == "sort-az":
            reordered = ColorBuilder.sort_colors_by_name(active)
        elif mode == "sort-za":
            reordered = ColorBuilder.sort_colors_by_name(active, reverse=True)
        elif mode == "move":
            if not color_name or target is None:
                return self._failure("'move' mode requires color_name and target position")
            found = self._find(snapshot, color_name)
            if found is None or found[0] != "custom":
                return self._failure(f"Custom color '{color_name}' not found")
            try:
                reordered = ColorBuilder.move_color_to_position(active, found[1], int(target))
            except (TypeError, ValueError) as exc:
                return self._failure(str(exc))
        elif mode == "swap":
            if not color_name or not target:
                return self._failure("'swap' mode requires color_name and target color name")
            first = self._find(snapshot, color_name)
            second = self._find(snapshot, target)
            if first is None or first[0] != "custom":
                return self._failure(f"Custom color '{color_name}' not found")
            if second is None or second[0] != "custom":
                return self._failure(f"Custom color '{target}' not found")
            try:
                reordered = ColorBuilder.swap_colors(active, first[1], second[1])
            except ValueError as exc:
                return self._failure(str(exc))
        else:
            return self._failure(f"Unknown mode: {mode}")

        complete = dict(snapshot.wire_custom)
        complete.update(reordered)
        payload = self._custom_payload(complete)

        def cache_orders() -> None:
            self._host.apply_style_token_cache_batch(
                "colors",
                upserts=reordered,
            )

        return self._dispatch(payload, dry_run=dry_run, after=cache_orders)

    def _payload(self) -> PayloadBuilder:
        return cast(PayloadBuilder, self._host.new_style_token_payload())

    def _custom_payload(self, colors: dict[str, dict[str, Any]]) -> PayloadBuilder:
        payload = self._payload()
        payload.add_change_app_setting(
            ColorBuilder.get_custom_color_path(),
            ColorBuilder.build_custom_colors_body(colors),
        )
        return payload

    def _dispatch(
        self,
        payload: PayloadBuilder,
        *,
        dry_run: bool,
        token_id: str | None = None,
        after: Any | None = None,
    ) -> TokenMutationResult:
        return dispatch_token_mutation(
            self._host,
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=after,
        )

    @staticmethod
    def _failure(
        error: str,
        *,
        payload: PayloadBuilder | None = None,
        token_id: str | None = None,
    ) -> TokenMutationResult:
        return TokenMutationResult(ok=False, payload=payload, token_id=token_id, error=error)

    @staticmethod
    def _client_safe(discovery: dict[str, Any]) -> dict[str, Any]:
        settings = discovery.get("settings") if isinstance(discovery, dict) else None
        client_safe = settings.get("client_safe") if isinstance(settings, dict) else None
        return client_safe if isinstance(client_safe, dict) else {}

    @staticmethod
    def _normalize_defaults(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            return {}
        result: dict[str, Any] = {}
        for key, value in raw.items():
            token_id = str(key or "").strip()
            if not token_id:
                continue
            if isinstance(value, Mapping):
                value = value.get("%d1", value.get("default", value))
            result[token_id] = value
        return result

    @classmethod
    def _normalize_custom_map(cls, raw: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(raw, Mapping):
            return {}
        wrapped = raw.get("default")
        if not isinstance(wrapped, Mapping):
            wrapped = raw.get("%d1")
        source = wrapped if isinstance(wrapped, Mapping) else raw
        result: dict[str, dict[str, Any]] = {}
        for token_id, raw_entry in source.items():
            color_id = str(token_id or "").strip()
            entry = cls._normalize_custom_entry(raw_entry)
            if color_id and cls._valid_custom_entry(entry):
                result[color_id] = entry
        return result

    @staticmethod
    def _custom_wire_map(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            return {}
        wrapped = raw.get("default")
        if not isinstance(wrapped, Mapping):
            wrapped = raw.get("%d1")
        source = wrapped if isinstance(wrapped, Mapping) else raw
        return {
            str(token_id or "").strip(): copy.deepcopy(raw_entry)
            for token_id, raw_entry in source.items()
            if str(token_id or "").strip()
        }

    @staticmethod
    def _normalize_custom_entry(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            return {}
        nested = raw.get("default")
        if not isinstance(nested, Mapping):
            nested = raw.get("%d1")
        source = nested if isinstance(nested, Mapping) else raw
        entry = dict(source)
        name = str(entry.pop("name", "") or entry.get("%nm") or "").strip()
        description = str(entry.pop("description", "") or entry.get("%d3") or "")
        deleted = bool(entry.pop("deleted", entry.get("%del", False)))
        entry["%nm"] = name
        entry["%d3"] = description
        entry["%del"] = deleted
        entry.setdefault("rgba", "")
        entry.setdefault("order", 0)
        return entry

    @staticmethod
    def _valid_custom_entry(entry: Mapping[str, Any]) -> bool:
        return bool(str(entry.get("%nm") or "").strip() and str(entry.get("rgba") or "").strip())

    @staticmethod
    def _active_custom(snapshot: ColorSnapshot) -> dict[str, dict[str, Any]]:
        return {
            token_id: dict(entry)
            for token_id, entry in snapshot.custom.items()
            if not bool(entry.get("%del"))
        }

    @classmethod
    def _find(cls, snapshot: ColorSnapshot, name: str) -> tuple[str, str, Any] | None:
        raw = str(name or "").strip()
        if not raw:
            return None
        normalized = cls._normalize_name(raw)
        for token_id, value in snapshot.defaults.items():
            friendly = str(DEFAULT_COLOR_NAMES.get(token_id, ""))
            if normalized in {cls._normalize_name(token_id), cls._normalize_name(friendly)}:
                return "default", token_id, value
        for token_id, entry in snapshot.custom.items():
            if bool(entry.get("%del")):
                continue
            token_name = str(entry.get("%nm") or "")
            if normalized in {cls._normalize_name(token_id), cls._normalize_name(token_name)}:
                return "custom", token_id, dict(entry)
        return None

    @staticmethod
    def _normalize_name(value: Any) -> str:
        token = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
        token = re.sub(r"\bcolor\b", "", token)
        return re.sub(r"\s+", " ", token).strip()

    @staticmethod
    def _next_order(entries: Mapping[str, Mapping[str, Any]]) -> int:
        orders: list[int] = []
        for entry in entries.values():
            try:
                orders.append(int(entry.get("order", 0)))
            except (TypeError, ValueError):
                orders.append(0)
        return max(orders, default=-1) + 1
