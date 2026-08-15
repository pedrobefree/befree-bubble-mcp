"""Bounded, deterministic Figma design-token planning and application."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from stat import S_ISREG
from typing import TYPE_CHECKING, Any, Callable, Mapping, cast

if TYPE_CHECKING:
    from ..bubble_sdk import ColorBuilder, DEFAULT_COLOR_NAMES, FontBuilder
    from ..figma_bridge.transform_tokens import TokenTransformer
else:
    try:
        from ..bubble_sdk import ColorBuilder, DEFAULT_COLOR_NAMES, FontBuilder
        from ..figma_bridge.transform_tokens import TokenTransformer
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import ColorBuilder, DEFAULT_COLOR_NAMES, FontBuilder
        from figma_bridge.transform_tokens import TokenTransformer

from .colors import ColorSnapshot, ColorTokenService
from .fonts import FontSnapshot, FontTokenService
from .protocols import StyleDefinitionSink, StyleTokenHost


@dataclass(frozen=True)
class DefaultColorUpdate:
    """One ordered default-color setting change."""

    token_id: str
    rgba: str


@dataclass(frozen=True)
class StyleDefinitionOperation:
    """One text-style definition routed through the compatibility sink."""

    name: str
    element_type: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class FigmaTokenCounts:
    """Legacy-compatible token import counters."""

    fonts: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    styles: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "fonts": self.fonts,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "styles": self.styles,
        }


@dataclass(frozen=True)
class FigmaTokenPlan:
    """Side-effect-free import plan in the required font/color/style order."""

    font_map: dict[str, Any] | None
    font_cache_updates: tuple[tuple[str, dict[str, Any]], ...]
    default_color_updates: tuple[DefaultColorUpdate, ...]
    color_map: dict[str, Any] | None
    color_cache_updates: tuple[tuple[str, dict[str, Any]], ...]
    styles: tuple[StyleDefinitionOperation, ...]
    counts: FigmaTokenCounts

    @property
    def phases(self) -> tuple[str, ...]:
        phases: list[str] = []
        if self.font_map is not None:
            phases.append("fonts")
        if self.default_color_updates or self.color_map is not None:
            phases.append("colors")
        if self.styles:
            phases.append("styles")
        return tuple(phases)


@dataclass(frozen=True)
class FigmaTokenSyncResult:
    """Structured internal result behind BubbleCLI's boolean facade."""

    ok: bool
    dry_run: bool
    counts: FigmaTokenCounts
    applied_counts: dict[str, int]
    payloads: tuple[dict[str, Any], ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "counts": self.counts.as_dict(),
            "applied_counts": dict(self.applied_counts),
            "payloads": [copy.deepcopy(payload) for payload in self.payloads],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class FigmaTokenImportService:
    """Validate, plan, and apply Figma tokens without incremental discovery reads."""

    DEFAULT_MAX_JSON_BYTES = 5_000_000
    DEFAULT_MAX_JSON_DEPTH = 64
    DEFAULT_MAX_JSON_NODES = 100_000
    _SUPPORTED_TYPES = {"font", "color", "style"}
    _DEFAULT_COLOR_REFERENCES = {"%3": "text"}

    def __init__(
        self,
        host: StyleTokenHost,
        colors: ColorTokenService,
        fonts: FontTokenService,
        styles: StyleDefinitionSink | None = None,
        *,
        transformer_factory: Callable[[str], TokenTransformer] = TokenTransformer,
        max_json_bytes: int = DEFAULT_MAX_JSON_BYTES,
        max_json_depth: int = DEFAULT_MAX_JSON_DEPTH,
        max_json_nodes: int = DEFAULT_MAX_JSON_NODES,
    ) -> None:
        self._host = host
        self._colors = colors
        self._fonts = fonts
        self._styles = styles if styles is not None else cast(StyleDefinitionSink, host)
        self._transformer_factory = transformer_factory
        self._max_json_bytes = max(1, int(max_json_bytes))
        self._max_json_depth = max(1, int(max_json_depth))
        self._max_json_nodes = max(1, int(max_json_nodes))

    def load_document(self, tokens_path: str | Path) -> dict[str, Any]:
        path = Path(tokens_path).expanduser()
        try:
            file_stat = path.stat()
        except OSError as exc:
            raise ValueError(f"Unable to read Figma token JSON: {exc}") from exc
        if not S_ISREG(file_stat.st_mode):
            raise ValueError("Figma token JSON must be a regular file.")
        if file_stat.st_size > self._max_json_bytes:
            raise ValueError(
                f"Figma token JSON exceeds maximum size of {self._max_json_bytes} bytes."
            )
        try:
            with path.open("rb") as stream:
                raw_bytes = stream.read(self._max_json_bytes + 1)
            if len(raw_bytes) > self._max_json_bytes:
                raise ValueError(
                    f"Figma token JSON exceeds maximum size of {self._max_json_bytes} bytes."
                )
            document = json.loads(raw_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(f"Figma token file must contain valid JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError("Figma token file must contain a JSON object.")
        self._validate_structure(document)
        if document.get("action") == "sync_tokens":
            content = document.get("content")
            if not isinstance(content, dict):
                raise ValueError("Figma token bridge content must be a JSON object.")
            return content
        return document

    def list_options(
        self,
        tokens_path: str | Path,
        *,
        config_path: str,
    ) -> dict[str, list[str]]:
        transformer = self._transformer_factory(config_path)
        tokens = transformer.flatten_tokens(self.load_document(tokens_path))
        return transformer.get_available_groups(tokens)

    def plan(
        self,
        tokens_path: str | Path,
        *,
        config_path: str,
        types: str | None = None,
        color_bases: str | None = None,
        all_tokens: bool = False,
        filter_text: str | None = None,
    ) -> FigmaTokenPlan:
        transformer = self._transformer_factory(config_path)
        raw_tokens = transformer.flatten_tokens(self.load_document(tokens_path))
        filtered = transformer.filter_tokens(raw_tokens)
        sync_types = self._parse_types(types)
        bases = tuple(
            sorted(
                {part.strip().casefold() for part in str(color_bases or "").split(",") if part.strip()}
            )
        )
        font_snapshot = self._fonts.snapshot()
        color_snapshot = self._colors.snapshot()

        font_map, font_updates, font_variables, fonts_count, font_skips = self._plan_fonts(
            filtered.get("font", []),
            font_snapshot,
            include="font" in sync_types,
        )
        (
            default_updates,
            color_map,
            color_updates,
            color_variables,
            created,
            updated,
            color_skips,
        ) = self._plan_colors(
            filtered.get("color", []),
            color_snapshot,
            transformer,
            include="color" in sync_types,
            bases=bases,
            all_tokens=all_tokens,
        )
        styles = self._plan_styles(
            filtered.get("style", []),
            transformer,
            include="style" in sync_types,
            filter_text=filter_text,
            font_variables=font_variables,
            color_variables=color_variables,
        )
        return FigmaTokenPlan(
            font_map=font_map,
            font_cache_updates=font_updates,
            default_color_updates=default_updates,
            color_map=color_map,
            color_cache_updates=color_updates,
            styles=styles,
            counts=FigmaTokenCounts(
                fonts=fonts_count,
                created=created,
                updated=updated,
                skipped=font_skips + color_skips,
                styles=len(styles),
            ),
        )

    def sync(
        self,
        tokens_path: str | Path,
        *,
        config_path: str,
        dry_run: bool = False,
        types: str | None = None,
        color_bases: str | None = None,
        all_tokens: bool = False,
        filter_text: str | None = None,
    ) -> FigmaTokenSyncResult:
        try:
            plan = self.plan(
                tokens_path,
                config_path=config_path,
                types=types,
                color_bases=color_bases,
                all_tokens=all_tokens,
                filter_text=filter_text,
            )
        except Exception as exc:
            return FigmaTokenSyncResult(
                ok=False,
                dry_run=dry_run,
                counts=FigmaTokenCounts(),
                applied_counts={"fonts": 0, "colors": 0, "styles": 0},
                payloads=(),
                errors=(f"planning: {exc}",),
            )
        payload_builders = self._build_token_payloads(plan)
        planned_payloads = self._structured_payloads(plan, payload_builders)
        applied = {"fonts": 0, "colors": 0, "styles": 0}
        if dry_run:
            return FigmaTokenSyncResult(
                ok=True,
                dry_run=True,
                counts=plan.counts,
                applied_counts=applied,
                payloads=planned_payloads,
            )

        warnings: list[str] = []
        for phase, builder, cache_kind, cache_updates in payload_builders:
            try:
                self._host.dispatch_style_token_payload(builder)
            except Exception as exc:
                return FigmaTokenSyncResult(
                    ok=False,
                    dry_run=False,
                    counts=plan.counts,
                    applied_counts=applied,
                    payloads=planned_payloads,
                    errors=(f"{phase}: {exc}",),
                    warnings=tuple(warnings),
                )
            if phase == "fonts":
                applied[phase] = len(cache_updates)
            else:
                applied[phase] = len(plan.default_color_updates) + len(cache_updates)
            try:
                self._host.apply_style_token_cache_batch(
                    cache_kind,
                    upserts=dict(cache_updates),
                )
            except Exception as exc:
                warnings.append(f"{phase} cache: {exc}")

        for index, operation in enumerate(plan.styles):
            try:
                ok = self._styles.create_style(
                    operation.name,
                    operation.element_type,
                    dry_run=False,
                    **operation.properties,
                )
            except Exception as exc:
                ok = False
                detail = str(exc)
            else:
                detail = "style definition returned false"
            if not ok:
                return FigmaTokenSyncResult(
                    ok=False,
                    dry_run=False,
                    counts=plan.counts,
                    applied_counts=applied,
                    payloads=planned_payloads,
                    errors=(f"styles[{index}] {operation.name}: {detail}",),
                    warnings=tuple(warnings),
                )
            applied["styles"] += 1

        return FigmaTokenSyncResult(
            ok=True,
            dry_run=False,
            counts=plan.counts,
            applied_counts=applied,
            payloads=planned_payloads,
            warnings=tuple(warnings),
        )

    def _validate_structure(self, document: dict[str, Any]) -> None:
        stack: list[tuple[Any, int]] = [(document, 1)]
        nodes = 0
        while stack:
            value, depth = stack.pop()
            nodes += 1
            if nodes > self._max_json_nodes:
                raise ValueError(
                    f"Figma token JSON exceeds maximum node count of {self._max_json_nodes}."
                )
            if depth > self._max_json_depth:
                raise ValueError(
                    f"Figma token JSON exceeds maximum depth of {self._max_json_depth}."
                )
            if isinstance(value, Mapping):
                stack.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                stack.extend((child, depth + 1) for child in value)

    @classmethod
    def _parse_types(cls, raw_types: str | None) -> set[str]:
        if not raw_types:
            return set(cls._SUPPORTED_TYPES)
        requested = {part.strip().casefold() for part in raw_types.split(",") if part.strip()}
        unsupported = sorted(requested - cls._SUPPORTED_TYPES)
        if unsupported:
            raise ValueError(f"Unsupported Figma token types: {', '.join(unsupported)}")
        return requested

    def _plan_fonts(
        self,
        tokens: list[dict[str, Any]],
        snapshot: FontSnapshot,
        *,
        include: bool,
    ) -> tuple[
        dict[str, Any] | None,
        tuple[tuple[str, dict[str, Any]], ...],
        dict[str, str],
        int,
        int,
    ]:
        variables: dict[str, str] = {}
        if snapshot.app_font and snapshot.app_font != "not set":
            variables[snapshot.app_font.casefold()] = "var(--font_default)"
        for token_id, entry in sorted(snapshot.custom.items()):
            if entry.get("%del"):
                continue
            reference = f"var(--font_{token_id}_default)"
            for candidate in (entry.get("%nm"), entry.get("font_family")):
                if str(candidate or "").strip():
                    variables[str(candidate).strip().casefold()] = reference
        if not include:
            return None, (), variables, 0, 0

        families: dict[str, str] = {}
        for token in tokens:
            family = self._font_family(token.get("value"))
            if family:
                families.setdefault(family.casefold(), family)
        final_map = copy.deepcopy(snapshot.wire_custom)
        updates: list[tuple[str, dict[str, Any]]] = []
        used_ids = set(final_map)
        next_order = self._next_order(snapshot.custom)
        skipped = 0
        for normalized, family in sorted(families.items()):
            if normalized in variables:
                skipped += 1
                continue
            token_id = self._stable_token_id("font", family, used_ids)
            used_ids.add(token_id)
            entry = FontBuilder.build_font_entry(family, family, order=next_order)
            next_order += 1
            final_map[token_id] = entry
            updates.append((token_id, entry))
            variables[normalized] = f"var(--font_{token_id}_default)"
        return (final_map if updates else None), tuple(updates), variables, len(updates), skipped

    def _plan_colors(
        self,
        tokens: list[dict[str, Any]],
        snapshot: ColorSnapshot,
        transformer: TokenTransformer,
        *,
        include: bool,
        bases: tuple[str, ...],
        all_tokens: bool,
    ) -> tuple[
        tuple[DefaultColorUpdate, ...],
        dict[str, Any] | None,
        tuple[tuple[str, dict[str, Any]], ...],
        dict[str, str],
        int,
        int,
        int,
    ]:
        variables = self._existing_color_variables(snapshot, transformer)
        if not include:
            return (), None, (), variables, 0, 0, 0
        mappings = transformer.get_default_color_mappings()
        selected: list[dict[str, Any]] = []
        for token in tokens:
            parts = token.get("parts") or []
            group = str(parts[1] if len(parts) > 1 else "").casefold()
            if all_tokens or not bases or any(base in group or group in base for base in bases):
                selected.append(token)
        selected.sort(key=lambda token: str(token.get("path") or "").casefold())

        final_map = copy.deepcopy(snapshot.wire_custom)
        active_custom = {
            token_id: dict(entry)
            for token_id, entry in snapshot.custom.items()
            if not entry.get("%del")
        }
        used_ids = set(final_map)
        next_order = self._next_order(snapshot.custom)
        default_updates: list[DefaultColorUpdate] = []
        cache_updates: dict[str, dict[str, Any]] = {}
        seen_targets: set[str] = set()
        created = 0
        updated = 0
        skipped = 0

        for token in selected:
            parts = [str(part) for part in token.get("parts") or []]
            raw_name = transformer.format_name(parts, token_type="color")
            rgba = transformer.hex_to_rgba(cast(str, token.get("value")))
            clean_path = ".".join(parts[1:])
            explicit_defaults = clean_path in mappings
            targets = mappings.get(clean_path, [raw_name])
            for target in sorted({str(item).strip() for item in targets if str(item).strip()}, key=str.casefold):
                normalized_target = self._normalize_name(target)
                if normalized_target in seen_targets:
                    continue
                seen_targets.add(normalized_target)
                found = self._find_color(snapshot, target, prefer_default=explicit_defaults)
                if found is None:
                    token_id = self._stable_token_id("color", target, used_ids)
                    used_ids.add(token_id)
                    entry = ColorBuilder.build_color_entry(target, rgba, order=next_order)
                    next_order += 1
                    final_map[token_id] = entry
                    active_custom[token_id] = entry
                    cache_updates[token_id] = entry
                    created += 1
                else:
                    token_type, token_id, current = found
                    current_rgba = current.get("rgba") if isinstance(current, Mapping) else current
                    if transformer.normalize_rgba(cast(str, current_rgba)) == transformer.normalize_rgba(
                        rgba
                    ):
                        skipped += 1
                    elif token_type == "default":
                        default_updates.append(DefaultColorUpdate(token_id=token_id, rgba=rgba))
                        updated += 1
                    else:
                        entry = dict(active_custom[token_id])
                        entry["rgba"] = rgba
                        final_map[token_id] = entry
                        active_custom[token_id] = entry
                        cache_updates[token_id] = entry
                        updated += 1
        projected_defaults = dict(snapshot.defaults)
        for update in default_updates:
            projected_defaults[update.token_id] = update.rgba
        variables = self._existing_color_variables(
            ColorSnapshot(
                defaults=projected_defaults,
                custom=active_custom,
                wire_custom=final_map,
            ),
            transformer,
        )
        ordered_cache_updates = tuple(sorted(cache_updates.items()))
        return (
            tuple(default_updates),
            final_map if cache_updates else None,
            ordered_cache_updates,
            variables,
            created,
            updated,
            skipped,
        )

    def _plan_styles(
        self,
        tokens: list[dict[str, Any]],
        transformer: TokenTransformer,
        *,
        include: bool,
        filter_text: str | None,
        font_variables: dict[str, str],
        color_variables: dict[str, str],
    ) -> tuple[StyleDefinitionOperation, ...]:
        if not include:
            return ()
        requested = str(filter_text or "").strip().casefold()
        operations: dict[str, StyleDefinitionOperation] = {}
        for token in sorted(tokens, key=lambda item: str(item.get("path") or "").casefold()):
            value = token.get("value")
            if not isinstance(value, Mapping):
                continue
            name = transformer.format_name(token.get("parts") or [], token_type="style")
            if requested and requested not in name.casefold():
                continue
            normalized_name = name.casefold()
            if normalized_name in operations:
                continue
            font_family = self._font_family(value)
            resolved_font = font_variables.get(font_family.casefold(), font_family) if font_family else ""
            raw_color = self._unwrap(value.get("color")) or "#000000"
            rgba = transformer.hex_to_rgba(raw_color)
            resolved_color = color_variables.get(transformer.normalize_rgba(rgba), rgba)
            properties: dict[str, Any] = {
                "font_size": self._font_size(value.get("fontSize")),
                "font_weight": transformer.normalize_font_weight(value.get("fontWeight")),
                "bold": False,
            }
            line_height = self._line_height(value.get("lineHeight"), properties["font_size"])
            if line_height is not None:
                properties["line_height"] = line_height
            if resolved_font:
                properties["font_face"] = f"{resolved_font}:::regular"
            if resolved_color:
                properties["font_color"] = resolved_color
            operations[normalized_name] = StyleDefinitionOperation(
                name=name,
                element_type="Text",
                properties=properties,
            )
        return tuple(operations.values())

    def _build_token_payloads(
        self,
        plan: FigmaTokenPlan,
    ) -> list[tuple[str, Any, str, tuple[tuple[str, dict[str, Any]], ...]]]:
        payloads: list[tuple[str, Any, str, tuple[tuple[str, dict[str, Any]], ...]]] = []
        if plan.font_map is not None:
            payload = self._host.new_style_token_payload()
            payload.add_change_app_setting(
                FontBuilder.get_custom_font_path(),
                FontBuilder.build_custom_fonts_body(copy.deepcopy(plan.font_map)),
            )
            payloads.append(("fonts", payload, "fonts", plan.font_cache_updates))
        if plan.default_color_updates or plan.color_map is not None:
            payload = self._host.new_style_token_payload()
            for update in plan.default_color_updates:
                payload.add_change_app_setting(
                    ColorBuilder.get_default_color_path() + [update.token_id],
                    {"%d1": update.rgba},
                )
            if plan.color_map is not None:
                payload.add_change_app_setting(
                    ColorBuilder.get_custom_color_path(),
                    ColorBuilder.build_custom_colors_body(copy.deepcopy(plan.color_map)),
                )
            payloads.append(("colors", payload, "colors", plan.color_cache_updates))
        return payloads

    @staticmethod
    def _structured_payloads(
        plan: FigmaTokenPlan,
        token_payloads: list[tuple[str, Any, str, tuple[tuple[str, dict[str, Any]], ...]]],
    ) -> tuple[dict[str, Any], ...]:
        payloads = [
            {"phase": phase, "payload": builder.build()}
            for phase, builder, _cache_kind, _cache_updates in token_payloads
        ]
        payloads.extend(
            {
                "phase": "styles",
                "name": operation.name,
                "element_type": operation.element_type,
                "properties": copy.deepcopy(operation.properties),
            }
            for operation in plan.styles
        )
        return tuple(payloads)

    @classmethod
    def _existing_color_variables(
        cls,
        snapshot: ColorSnapshot,
        transformer: TokenTransformer,
    ) -> dict[str, str]:
        variables: dict[str, str] = {}
        for token_id, rgba in sorted(snapshot.defaults.items()):
            if rgba:
                variables[transformer.normalize_rgba(rgba)] = cls._color_reference(token_id)
        for token_id, entry in sorted(snapshot.custom.items()):
            if entry.get("%del") or not entry.get("rgba"):
                continue
            variables[transformer.normalize_rgba(entry["rgba"])] = cls._color_reference(token_id)
        return variables

    @classmethod
    def _find_color(
        cls,
        snapshot: ColorSnapshot,
        name: str,
        *,
        prefer_default: bool,
    ) -> tuple[str, str, Any] | None:
        normalized = cls._normalize_name(name)
        defaults: list[tuple[str, str, Any]] = []
        custom: list[tuple[str, str, Any]] = []
        for token_id, rgba in snapshot.defaults.items():
            friendly = DEFAULT_COLOR_NAMES.get(token_id, "")
            if normalized in {cls._normalize_name(token_id), cls._normalize_name(friendly)}:
                defaults.append(("default", token_id, rgba))
        for token_id, entry in snapshot.custom.items():
            if entry.get("%del"):
                continue
            if normalized in {
                cls._normalize_name(token_id),
                cls._normalize_name(entry.get("%nm")),
            }:
                custom.append(("custom", token_id, dict(entry)))
        candidates = (*defaults, *custom) if prefer_default else (*custom, *defaults)
        return candidates[0] if candidates else None

    @classmethod
    def _color_reference(cls, token_id: str) -> str:
        reference_id = cls._DEFAULT_COLOR_REFERENCES.get(token_id, token_id)
        return f"var(--color_{reference_id}_default)"

    @staticmethod
    def _normalize_name(value: Any) -> str:
        return " ".join(
            str(value or "").strip().casefold().replace("-", " ").replace("_", " ").split()
        )

    @staticmethod
    def _stable_token_id(kind: str, name: str, used_ids: set[str]) -> str:
        namespace_size = 16**4
        seed = f"figma:{kind}:{name.casefold()}:0".encode()
        start = int(hashlib.sha256(seed).hexdigest()[:4], 16)
        for offset in range(namespace_size):
            candidate = f"b{(start + offset) % namespace_size:04x}"
            if candidate not in used_ids:
                return candidate
        raise RuntimeError("deterministic token ID namespace exhausted")

    @staticmethod
    def _next_order(entries: Mapping[str, Mapping[str, Any]]) -> int:
        orders: list[int] = []
        for entry in entries.values():
            try:
                orders.append(int(entry.get("order", 0)))
            except (TypeError, ValueError):
                orders.append(0)
        return max(orders, default=-1) + 1

    @classmethod
    def _font_family(cls, value: Any) -> str:
        if isinstance(value, Mapping):
            value = cls._unwrap(value.get("fontFamily", value.get("value")))
        return str(value or "").strip()

    @staticmethod
    def _unwrap(value: Any) -> Any:
        if isinstance(value, Mapping):
            return value.get("value")
        return value

    @classmethod
    def _font_size(cls, value: Any) -> int | float | None:
        value = cls._unwrap(value)
        if value in (None, ""):
            return None
        try:
            number = float(str(value).strip().removesuffix("px"))
        except (TypeError, ValueError):
            return None
        return int(number) if number.is_integer() else number

    @classmethod
    def _line_height(cls, value: Any, font_size: Any) -> float | None:
        value = cls._unwrap(value)
        if value in (None, ""):
            return None
        try:
            if isinstance(value, str) and value.strip().endswith("%"):
                return round(float(value.strip()[:-1]) / 100, 2)
            number = float(str(value).strip().removesuffix("px"))
            if number > 5 and isinstance(font_size, (int, float)) and font_size > 0:
                return round(number / font_size, 2)
            return round(number, 2) if number <= 5 else None
        except (TypeError, ValueError):
            return None
