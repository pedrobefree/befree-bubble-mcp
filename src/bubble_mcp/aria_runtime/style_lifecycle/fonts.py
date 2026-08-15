"""Discovery-first font token reads and grouped lifecycle writes."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

try:
    from ..bubble_sdk import FontBuilder, PayloadBuilder
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import FontBuilder, PayloadBuilder

from .protocols import StyleTokenHost, TokenMutationResult


@dataclass(frozen=True)
class FontSnapshot:
    """One normalized, detached view of the App Font and custom fonts."""

    app_font: str
    custom: dict[str, dict[str, Any]]
    wire_custom: dict[str, Any]


class FontTokenService:
    """Resolve and mutate Bubble font tokens through one host boundary."""

    _APP_FONT_NAMES = {"app font", "app_font", "default font", "default"}

    def __init__(self, host: StyleTokenHost) -> None:
        self._host = host

    def snapshot(self) -> FontSnapshot:
        discovery, cache = self._host.style_reference_snapshots()
        client_safe = self._client_safe(discovery)
        app_font = self._normalize_app_font(client_safe.get("font_tokens"))
        wire_custom = self._custom_wire_map(client_safe.get("font_tokens_user"))
        custom = self._normalize_custom_map(wire_custom)
        wire_custom.update(copy.deepcopy(custom))
        cache_fonts = cache.get("fonts") if isinstance(cache, dict) else None
        if isinstance(cache_fonts, Mapping):
            for token_id, raw_entry in cache_fonts.items():
                font_id = str(token_id or "").strip()
                if not font_id or font_id in custom:
                    continue
                entry = self._normalize_custom_entry(raw_entry)
                if self._valid_custom_entry(entry):
                    custom[font_id] = entry
                    wire_custom[font_id] = copy.deepcopy(entry)
        return FontSnapshot(app_font=app_font, custom=custom, wire_custom=wire_custom)

    def find(self, name: str) -> tuple[str, str, dict[str, Any]] | None:
        return self._find(self.snapshot(), name)

    def next_order(self) -> int:
        return self._next_order(self.snapshot().custom)

    def update(
        self,
        name: str,
        font_family: str,
        *,
        dry_run: bool = False,
    ) -> TokenMutationResult:
        snapshot = self.snapshot()
        found = self._find(snapshot, name)
        if found is None:
            return self._failure(f"Font '{name}' not found")
        token_type, token_id, current = found
        payload = self._payload()
        if token_type == "app":
            payload.add_change_app_setting(
                FontBuilder.get_app_font_path(),
                FontBuilder.build_app_font_body(font_family),
            )
            return self._dispatch(payload, dry_run=dry_run, token_id=token_id)

        all_fonts = dict(snapshot.wire_custom)
        updated = dict(current)
        updated["font_family"] = font_family
        all_fonts[token_id] = updated
        payload.add_change_app_setting(
            FontBuilder.get_custom_font_path(),
            FontBuilder.build_custom_fonts_body(all_fonts),
        )
        return self._dispatch(
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=lambda: self._host.put_style_token_cache("fonts", token_id, updated),
        )

    def create(
        self,
        name: str,
        font_family: str,
        description: str = "",
        *,
        dry_run: bool = False,
    ) -> TokenMutationResult:
        snapshot = self.snapshot()
        if self._find(snapshot, name) is not None or self._find(snapshot, font_family) is not None:
            return self._failure(f"Font '{name}' already exists")
        builder = FontBuilder()
        token_id = builder.generate_font_id()
        entry = FontBuilder.build_font_entry(
            name=name,
            font_family=font_family,
            order=self._next_order(snapshot.custom),
            description=description,
        )
        all_fonts = dict(snapshot.wire_custom)
        all_fonts[token_id] = entry
        payload = self._custom_payload(all_fonts)
        return self._dispatch(
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=lambda: self._host.put_style_token_cache("fonts", token_id, entry),
        )

    def delete(self, name: str, *, dry_run: bool = False) -> TokenMutationResult:
        snapshot = self.snapshot()
        found = self._find(snapshot, name)
        if found is None:
            return self._failure(f"Font '{name}' not found")
        token_type, token_id, current = found
        if token_type == "app":
            return self._failure("Cannot delete the App Font")
        all_fonts = dict(snapshot.wire_custom)
        deleted = dict(current)
        deleted["%del"] = True
        all_fonts[token_id] = deleted
        payload = self._custom_payload(all_fonts)
        return self._dispatch(
            payload,
            dry_run=dry_run,
            token_id=token_id,
            after=lambda: self._host.remove_style_token_cache("fonts", token_id),
        )

    def _payload(self) -> PayloadBuilder:
        return self._host.new_style_token_payload()

    def _custom_payload(self, fonts: dict[str, dict[str, Any]]) -> PayloadBuilder:
        payload = self._payload()
        payload.add_change_app_setting(
            FontBuilder.get_custom_font_path(),
            FontBuilder.build_custom_fonts_body(fonts),
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
        if dry_run:
            return TokenMutationResult(ok=True, payload=payload, token_id=token_id)
        try:
            self._host.dispatch_style_token_payload(payload)
        except Exception as exc:
            return self._failure(str(exc), payload=payload, token_id=token_id)
        if after is not None:
            after()
        return TokenMutationResult(ok=True, payload=payload, token_id=token_id)

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
    def _normalize_app_font(raw: Any) -> str:
        if isinstance(raw, Mapping):
            raw = raw.get("default", raw.get("%d1", "not set"))
        value = str(raw or "").strip()
        return value or "not set"

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
            font_id = str(token_id or "").strip()
            entry = cls._normalize_custom_entry(raw_entry)
            if font_id and cls._valid_custom_entry(entry):
                result[font_id] = entry
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
        entry.setdefault("font_family", "")
        entry.setdefault("order", 0)
        return entry

    @staticmethod
    def _valid_custom_entry(entry: Mapping[str, Any]) -> bool:
        return bool(
            str(entry.get("%nm") or "").strip()
            and str(entry.get("font_family") or "").strip()
        )

    @classmethod
    def _find(cls, snapshot: FontSnapshot, name: str) -> tuple[str, str, dict[str, Any]] | None:
        raw = str(name or "").strip()
        normalized = raw.lower()
        if normalized in cls._APP_FONT_NAMES:
            return "app", "app_font", {"font_family": snapshot.app_font}
        if not normalized:
            return None
        for token_id, entry in snapshot.custom.items():
            if bool(entry.get("%del")):
                continue
            candidates = {
                token_id.lower(),
                str(entry.get("%nm") or "").strip().lower(),
                str(entry.get("font_family") or "").strip().lower(),
            }
            if normalized in candidates:
                return "custom", token_id, dict(entry)
        return None

    @staticmethod
    def _next_order(entries: Mapping[str, Mapping[str, Any]]) -> int:
        orders: list[int] = []
        for entry in entries.values():
            try:
                orders.append(int(entry.get("order", 0)))
            except (TypeError, ValueError):
                orders.append(0)
        return max(orders, default=-1) + 1
