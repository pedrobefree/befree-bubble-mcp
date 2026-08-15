"""Style definition and conditional-state lifecycle orchestration."""

from __future__ import annotations

import copy
import json
import random
import re
import string
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..bubble_sdk import PayloadBuilder, StyleBuilder, logger
else:
    try:
        from ..bubble_sdk import PayloadBuilder, StyleBuilder, logger
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import PayloadBuilder, StyleBuilder, logger

from .protocols import StyleDefinitionHost
from .references import StyleReferenceResolver


class StyleDefinitionService:
    """Coordinate Bubble style definitions without owning SDK wire construction."""

    _COLOR_KEYS = {
        "background_color",
        "bg_color",
        "slider_background_color",
        "font_color",
        "icon_color",
        "placeholder_color",
        "text_shadow_color",
        "border_color",
        "border_color_top",
        "border_color_bottom",
        "border_color_left",
        "border_color_right",
        "shadow_color",
        "gradient_start_color",
        "gradient_end_color",
        "gradient_mid_color",
        "gradient_start",
        "gradient_end",
        "gradient_mid",
        "background_color_if_empty_image",
        "greyout_color",
        "grayout_color",
        "separator_color",
        "handle_color",
        "range_area_color",
    }
    _DIRECT_STYLE_ID_TYPES = {
        "Button",
        "Text",
        "Group",
        "Alert",
        "Input",
        "Popup",
        "RepeatingGroup",
        "FloatingGroup",
        "GroupFocus",
        "Shape",
        "Image",
        "Video",
        "HTML",
        "Icon",
        "Link",
        "Dropdown",
        "DateInput",
        "Checkbox",
        "RadioButtons",
        "SliderInput",
        "FileInput",
        "PictureInput",
        "MultiLineInput",
        "AutocompleteDropdown",
    }

    def __init__(
        self,
        host: StyleDefinitionHost,
        references: StyleReferenceResolver,
        resolve_color: Callable[[str], str] | Any,
    ) -> None:
        self._host = host
        self._references = references
        resolver = getattr(resolve_color, "resolve", resolve_color)
        if not callable(resolver):
            raise TypeError("resolve_color must be callable or expose resolve()")
        self._resolve_color: Callable[[str], str] = resolver

    @staticmethod
    def normalize_state_definitions(raw_states: Any) -> list[tuple[str, dict[str, Any]]]:
        """Normalize supported state inputs while preserving caller order."""
        if raw_states is None:
            return []
        parsed = raw_states
        if isinstance(raw_states, str):
            text = raw_states.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception as exc:
                raise ValueError(f"Invalid states_json payload: {exc}") from exc

        normalized: list[tuple[str, dict[str, Any]]] = []
        if isinstance(parsed, dict):
            for condition, properties in parsed.items():
                name = str(condition or "").strip()
                if not name:
                    continue
                if not isinstance(properties, dict):
                    raise ValueError(f"State '{name}' must map to an object of properties.")
                normalized.append((name, dict(properties)))
            return normalized

        if isinstance(parsed, list):
            for index, entry in enumerate(parsed):
                if not isinstance(entry, dict):
                    raise ValueError(f"State entry #{index + 1} must be an object.")
                name = str(entry.get("condition") or entry.get("state") or "").strip()
                if not name:
                    raise ValueError(f"State entry #{index + 1} is missing 'condition'.")
                properties = entry.get("properties")
                if properties is None:
                    properties = entry.get("props")
                if not isinstance(properties, dict):
                    raise ValueError(f"State '{name}' must include 'properties' object.")
                normalized.append((name, dict(properties)))
            return normalized

        raise ValueError("states_json must be a JSON object or array.")

    @staticmethod
    def normalize_kwargs(kwargs: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize shared create/update aliases before SDK wire construction."""
        normalized = dict(kwargs or {})

        def is_blank(value: Any) -> bool:
            return value is None or (isinstance(value, str) and value.strip() == "")

        if normalized.get("background_style") is None and normalized.get("bg_style") is not None:
            normalized["background_style"] = normalized.pop("bg_style")
        background_style = normalized.get("background_style")
        if background_style is not None:
            raw_style = str(background_style).strip().lower().replace("_", " ").replace("-", " ")
            normalized["background_style"] = {
                "none": "none",
                "flat color": "bgcolor",
                "flat": "bgcolor",
                "flatcolor": "bgcolor",
                "bgcolor": "bgcolor",
                "color": "bgcolor",
                "gradient": "gradient",
                "image": "image",
            }.get(raw_style, str(background_style).strip().lower())

        if normalized.get("background_style") == "image":
            explicit_fallback = normalized.get("background_color_if_empty_image")
            has_explicit_fallback = explicit_fallback is not None and (
                not isinstance(explicit_fallback, str) or bool(explicit_fallback.strip())
            )
            fallback_color = None
            for color_key in ("background_color", "bg_color"):
                raw_color = normalized.get(color_key)
                if raw_color is None:
                    continue
                if isinstance(raw_color, str) and not raw_color.strip():
                    normalized.pop(color_key, None)
                    continue
                if fallback_color is None:
                    fallback_color = raw_color
                normalized.pop(color_key, None)
            if fallback_color is not None and not has_explicit_fallback:
                normalized["background_color_if_empty_image"] = fallback_color

        aliases = {
            "gradient_color1": "gradient_start_color",
            "gradient_color2": "gradient_end_color",
            "gradient_mid": "gradient_mid_color",
            "gradient_type": "gradient_style",
        }
        for alias, canonical in aliases.items():
            if normalized.get(canonical) is None and normalized.get(alias) is not None:
                normalized[canonical] = normalized.pop(alias)

        raw_border_mode = normalized.get("border_type")
        border_mode = (
            str(raw_border_mode).strip().lower().replace("-", "_").replace(" ", "_")
            if raw_border_mode is not None
            else ""
        )
        independent = bool(normalized.get("four_border_style") is True) or border_mode in {
            "independent",
            "all_4_borders",
        }
        if independent:
            sides = ("top", "right", "bottom", "left")
            explicit_sides = {
                side: any(
                    not is_blank(normalized.get(f"{prefix}_{side}"))
                    for prefix in ("border_style", "border_width", "border_color")
                )
                for side in sides
            }
            if any(explicit_sides.values()):
                for side in sides:
                    if explicit_sides[side]:
                        continue
                    normalized.setdefault(f"border_style_{side}", "none")
                    normalized.setdefault(f"border_width_{side}", 0)
                    normalized.setdefault(f"border_roundness_{side}", 0)

        if normalized.get("custom_style") is None and normalized.get("style_json") is not None:
            normalized["custom_style"] = normalized.pop("style_json")
        else:
            normalized.pop("style_json", None)

        if normalized.get("map_type") is not None:
            raw_map_type = str(normalized["map_type"]).strip()
            if raw_map_type:
                lowered = raw_map_type.lower().replace("-", "_").replace(" ", "_")
                normalized["map_type"] = {
                    "road": "ROADMAP",
                    "roadmap": "ROADMAP",
                    "satellite": "SATELLITE",
                    "hybrid": "HYBRID",
                    "terrain": "TERRAIN",
                }.get(lowered, raw_map_type.upper())
            else:
                normalized.pop("map_type", None)

        if normalized.get("map_style") is not None:
            raw_map_style = str(normalized["map_style"]).strip()
            if raw_map_style:
                lowered = raw_map_style.lower().replace("-", "_").replace(" ", "_")
                known = {
                    "mapbox",
                    "normal",
                    "apple",
                    "pale_down",
                    "blue_water",
                    "flat_green",
                    "blue_gray",
                    "neutral_blue",
                    "grey_shades",
                    "greyscale",
                    "subtle_greyscale",
                    "bright_bubbly",
                    "retro",
                    "old_timey",
                    "just_places",
                    "_custom",
                }
                if lowered in {"custom", "custom_style"}:
                    lowered = "_custom"
                normalized["map_style"] = lowered if lowered in known else lowered
            else:
                normalized.pop("map_style", None)

        if normalized.get("range_type") is not None:
            range_type = str(normalized["range_type"]).strip().lower().replace("-", "_").replace(" ", "_")
            if range_type:
                normalized["range_type"] = range_type
            else:
                normalized.pop("range_type", None)

        padding = normalized.pop("padding", None)
        if padding is not None:
            for side in ("top", "bottom", "left", "right"):
                normalized.setdefault(f"padding_{side}", padding)

        if normalized.get("greyout_color") is None and normalized.get("grayout_color") is not None:
            normalized["greyout_color"] = normalized.pop("grayout_color")
        else:
            normalized.pop("grayout_color", None)
        if normalized.get("greyout_blur") is None and normalized.get("grayout_blur") is not None:
            normalized["greyout_blur"] = normalized.pop("grayout_blur")
        else:
            normalized.pop("grayout_blur", None)
        if normalized.get("greyout_blur") is not None:
            try:
                normalized["greyout_blur"] = int(normalized["greyout_blur"])
            except Exception:
                pass

        if normalized.get("separator_style") is not None:
            normalized["separator_style"] = str(normalized["separator_style"]).strip().lower()
        if normalized.get("separator_width") is not None:
            try:
                normalized["separator_width"] = int(normalized["separator_width"])
            except Exception:
                pass

        if raw_border_mode is not None:
            if border_mode in {"all_4_borders", "independent"}:
                normalized["border_type"] = "independent"
            elif border_mode == "shared":
                normalized["border_type"] = "shared"

        if normalized.get("border_type") == "independent":
            side_style_keys = tuple(f"border_style_{side}" for side in ("top", "bottom", "left", "right"))
            if any(not is_blank(normalized.get(key)) for key in side_style_keys):
                for key in side_style_keys:
                    if is_blank(normalized.get(key)):
                        normalized[key] = "none"
            corner_keys = (
                "radius_top_left",
                "radius_top_right",
                "radius_bottom_right",
                "radius_bottom_left",
            )
            if any(not is_blank(normalized.get(key)) for key in corner_keys):
                for key in corner_keys:
                    if is_blank(normalized.get(key)):
                        normalized[key] = 0
        return normalized

    @staticmethod
    def state_property_wire_map() -> dict[str, str]:
        return {
            "border_radius": "%br",
            "border_width": "%bw",
            "border_color": "%bc",
            "border_style": "%bos",
            "font_size": "%fs",
            "font_color": "%fc",
            "alignment": "%fa",
            "bg_color": "%bgc",
            "background_color": "%bgc",
            "background_color_if_empty_image": "background_color_if_empty_image",
            "background_style": "%bas",
            "shadow_style": "%bs",
            "shadow_color": "%bsc",
            "shadow_h": "%bh",
            "shadow_v": "%bv",
            "shadow_blur": "%bsb",
            "shadow_spread": "%bsp",
            "separator_style": "%ss",
            "separator_width": "%sw",
            "separator_color": "%sc",
            "icon_color": "%ic",
            "word_spacing": "%ws",
            "line_height": "%lh",
            "letter_spacing": "%ls",
            "text_shadow": "%tes",
            "text_shadow_h": "%tsh",
            "text_shadow_v": "%tsv",
            "text_shadow_blur": "%tsb",
            "text_shadow_color": "%tsc",
            "greyout_color": "greyout_color",
            "grayout_color": "greyout_color",
            "greyout_blur": "greyout_blur",
            "grayout_blur": "greyout_blur",
            "padding_top": "padding_top",
            "padding_bottom": "padding_bottom",
            "padding_left": "padding_left",
            "padding_right": "padding_right",
            "center_text_vertically": "%vc",
            "container_layout": "container_layout",
            "fit_width": "fit_width",
            "fit_height": "fit_height",
            "min_width_css": "min_width_css",
            "max_width_css": "max_width_css",
            "min_height_css": "min_height_css",
            "max_height_css": "max_height_css",
            "single_width": "single_width",
            "single_height": "single_height",
            "use_gap": "use_gap",
            "row_gap": "row_gap",
            "column_gap": "column_gap",
            "nonant_alignment": "nonant_alignment",
            "gap": "button_gap",
            "button_gap": "button_gap",
            "icon_size": "icon_size",
        }

    @staticmethod
    def build_transition_intents(
        style_id: str,
        properties: dict[str, Any],
        *,
        comparison_map: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        del comparison_map
        return StyleBuilder().build_state_transition_intents(style_id, properties)

    @staticmethod
    def normalize_trigger_alias(token: str) -> str | None:
        raw = str(token or "").strip().lower()
        if not raw:
            return None
        normalized = re.sub(r"[_-]+", " ", raw)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        aliases = {
            "hover": "hover",
            "hovered": "hover",
            "is hovered": "hover",
            "is hover": "hover",
            "is hovered yes": "hover",
            "disabled": "disabled",
            "disable": "disabled",
            "is disabled": "disabled",
            "not clickable": "disabled",
            "isnt clickable": "disabled",
            "isn't clickable": "disabled",
            "pressed": "pressed",
            "is pressed": "pressed",
            "active": "pressed",
            "focus": "focus",
            "focused": "focus",
            "is focused": "focus",
            "invalid": "invalid",
            "isnt valid": "invalid",
            "isn't valid": "invalid",
            "not valid": "invalid",
            "visible": "visible",
            "is visible": "visible",
            "shown": "visible",
            "is shown": "visible",
            "hidden": "not_visible",
            "is hidden": "not_visible",
            "not visible": "not_visible",
            "isnt visible": "not_visible",
            "isn't visible": "not_visible",
            "invisible": "not_visible",
        }
        if normalized in aliases:
            return aliases[normalized]
        if "clickable" in normalized and any(part in normalized for part in ("not", "isnt", "isn't")):
            return "disabled"
        if "hover" in normalized:
            return "hover"
        if "press" in normalized or "active" in normalized:
            return "pressed"
        if "focus" in normalized:
            return "focus"
        if "valid" in normalized and any(part in normalized for part in ("not", "isnt", "isn't")):
            return "invalid"
        if "visible" in normalized:
            if any(part in normalized for part in ("not", "isnt", "isn't", "hidden", "invisible")):
                return "not_visible"
            return "visible"
        if "hidden" in normalized or "invisible" in normalized:
            return "not_visible"
        return None

    @classmethod
    def parse_reorder_order(cls, order_input: list[str] | str) -> list[str]:
        raw = ",".join(str(item) for item in order_input if str(item).strip()) if isinstance(order_input, list) else str(order_input or "")
        text = raw.strip().lower()
        if not text:
            return []

        def dedupe(items: list[str | None]) -> list[str]:
            result: list[str] = []
            for item in items:
                if item and item not in result:
                    result.append(item)
            return result

        relations = (
            (r"(.+?)\s+(?:stronger than|overrides|override|below|under|after)\s+(.+)", True),
            (r"(.+?)\s+(?:weaker than|above|before|prior to)\s+(.+)", False),
        )
        for pattern, reverse in relations:
            match = re.fullmatch(pattern, text)
            if not match:
                continue
            left = cls.normalize_trigger_alias(match.group(1))
            right = cls.normalize_trigger_alias(match.group(2))
            if left and right:
                return dedupe([right, left] if reverse else [left, right])

        sequence = re.sub(r"\b(and then|then|next)\b", ",", text)
        sequence = re.sub(r"[>/;|]", ",", sequence)
        parts = [part.strip() for part in sequence.split(",") if part.strip()]
        parsed = dedupe([cls.normalize_trigger_alias(part) for part in parts])
        if parsed:
            return parsed
        patterns = (
            ("disabled", r"\b(disabled|isn['’]?t clickable|isnt clickable|not clickable)\b"),
            ("hover", r"\b(hover|hovered)\b"),
            ("pressed", r"\b(pressed|active)\b"),
            ("focus", r"\b(focus|focused)\b"),
            ("invalid", r"\b(invalid|isn['’]?t valid|isnt valid|not valid)\b"),
            ("not_visible", r"\b(hidden|invisible|not visible|isn['’]?t visible)\b"),
            ("visible", r"\b(visible|is visible)\b"),
        )
        hits: list[tuple[int, str]] = []
        for trigger, pattern in patterns:
            hits.extend((match.start(), trigger) for match in re.finditer(pattern, text))
        hits.sort(key=lambda item: item[0])
        return dedupe([trigger for _, trigger in hits])

    def set_default_style(self, element_type: str, style_id: str, dry_run: bool = False) -> bool:
        settings_key = self._references.default_style_settings_key(element_type)
        payload = PayloadBuilder(self._host.appname)
        payload.add_change(
            intent_name="ChangeAppSetting",
            path_array=["settings", "client_safe", "default_styles"],
            body={settings_key: style_id},
        )
        if dry_run:
            logger.info("\n DRY RUN - Set Default Style Payload:")
            logger.log(payload.to_json())
            return True
        return self._dispatch(payload, "Failed to set default style")

    def create_style(
        self,
        name: str,
        element_type: str,
        dry_run: bool = False,
        allow_property_match: bool = True,
        **properties: Any,
    ) -> bool:
        if not element_type:
            logger.error("Element type is required for create_style")
            return False
        element_type = self._references.normalize_element_type(element_type)
        normalized = self.normalize_kwargs(properties)
        states_raw = normalized.pop("states", None)
        if states_raw is None:
            states_raw = normalized.pop("states_json", None)
        else:
            normalized.pop("states_json", None)
        try:
            states = self.normalize_state_definitions(states_raw)
        except ValueError as exc:
            logger.error(str(exc))
            return False
        normalized = self._resolve_color_kwargs(normalized)
        if element_type == "Popup":
            shadow_fields = (
                "shadow_style",
                "shadow_h",
                "shadow_v",
                "shadow_blur",
                "shadow_spread",
                "shadow_color",
            )
            if not any(
                normalized.get(field) is not None
                and (not isinstance(normalized.get(field), str) or bool(str(normalized[field]).strip()))
                for field in shadow_fields
            ):
                normalized["shadow_style"] = "none"
        default_style = bool(normalized.pop("default_style", False))
        if not dry_run and not self._remove_stale_cache_aliases(name, element_type):
            return False
        expected_id = self._references.canonical_style_id(name, element_type)
        if not expected_id:
            logger.error(f"Could not generate style ID for '{name}'.")
            return False

        target = self._existing_create_target(name, element_type, expected_id)
        if target is None and allow_property_match and normalized:
            target = self._property_match(name, element_type, normalized)
        if target is not None:
            style_id = str(target.get("id") or "")
            if default_style and not self.set_default_style(element_type, style_id, dry_run=dry_run):
                return False
            if normalized:
                if not self.update_style_definition(
                    name,
                    element_type,
                    dry_run=dry_run,
                    style_id_override=style_id,
                    **normalized,
                ):
                    return False
            elif dry_run:
                self._hydrate(style_id, name, element_type, {})
            return self.apply_state_definitions(name, states, dry_run=dry_run)

        style_id = expected_id
        payload = PayloadBuilder(self._host.appname)
        builder = StyleBuilder(self._host.id_gen)
        style_payload = builder.create_style(name, element_type=element_type)
        style_payload["id"] = style_id
        style_payload.pop("%p", None)
        style_payload.pop("%s", None)
        payload.add_update_index(["_index", "id_to_path", style_id], f"styles.{style_id}")
        payload.add_create_style(style_id, style_payload)
        payload.changes.append(
            {
                "intent": {"name": "IdToPathFixer"},
                "path_array": ["_index", "id_to_path", style_id],
                "body": None,
                "version_control_api_version": 4,
                "changelog_data": [],
                "session_id": payload.id_gen.session_id(),
            }
        )
        if default_style:
            payload.add_change(
                intent_name="ChangeAppSetting",
                path_array=["settings", "client_safe", "default_styles"],
                body={self._references.default_style_settings_key(element_type): style_id},
            )
        payload.add_change_raw({"type": "id_counter", "value": random.randint(10000000, 20000000)})

        if dry_run:
            logger.info(f"\n DRY RUN - Style Creation Payload ({style_id}):")
            logger.log(payload.to_json())
            self._hydrate(style_id, name, element_type, {})
        else:
            if not self._dispatch(payload, "Failed to send creation payload"):
                return False
            if not self._put_cache(name, {"id": style_id, "type": element_type, "%p": {}}):
                return False
            self._hydrate(style_id, name, element_type, {})

        if normalized:
            if element_type in {"FileInput", "PictureInput", "Alert"} and normalized.get("bold") is None:
                typography_fields = {
                    "font_weight",
                    "font_size",
                    "font_family",
                    "font_color",
                    "alignment",
                    "line_height",
                    "letter_spacing",
                    "word_spacing",
                }
                if any(normalized.get(field) is not None for field in typography_fields):
                    normalized["bold"] = False
            if not self.update_style_definition(
                name,
                element_type,
                dry_run=dry_run,
                style_id_override=style_id,
                **normalized,
            ):
                return False
        return self.apply_state_definitions(name, states, dry_run=dry_run)

    def update_style_definition(
        self,
        name: str,
        element_type: str,
        dry_run: bool = False,
        style_id_override: str | None = None,
        **properties: Any,
    ) -> bool:
        element_type = self._references.normalize_element_type(element_type)
        raw_properties = dict(properties)
        if "bg_color" in raw_properties:
            raw_properties["background_color"] = raw_properties.pop("bg_color")
        if "bg_style" in raw_properties:
            raw_properties["background_style"] = raw_properties.pop("bg_style")
        states_raw = raw_properties.pop("states", None)
        if states_raw is None:
            states_raw = raw_properties.pop("states_json", None)
        else:
            raw_properties.pop("states_json", None)
        try:
            states = self.normalize_state_definitions(states_raw)
        except ValueError as exc:
            logger.error(str(exc))
            return False
        normalized = self._resolve_color_kwargs(self.normalize_kwargs(raw_properties))
        default_style = bool(normalized.pop("default_style", False))
        if not dry_run and not self._remove_stale_cache_aliases(name, element_type):
            return False
        style_id = str(style_id_override or "").strip() or self._find_update_style_id(name, element_type)
        if not style_id:
            logger.error(f"Style '{name}' not found.")
            return False

        changes = StyleBuilder(self._host.id_gen).update_style(style_id, **normalized)
        if not changes:
            return self.apply_state_definitions(name, states, dry_run=dry_run)
        payload = PayloadBuilder(self._host.appname)
        clear_font_family = normalized.get("font_face") is not None and normalized.get("font_family") in (
            None,
            "",
        )
        for change in changes:
            payload.add_set_style_data(change["path"], change["body"])
        if clear_font_family:
            payload.add_set_style_data(["styles", style_id, "%p", "font_family"], None)
        if default_style:
            payload.add_change(
                intent_name="ChangeAppSetting",
                path_array=["settings", "client_safe", "default_styles"],
                body={self._references.default_style_settings_key(element_type): style_id},
            )

        wire_changes = self._wire_properties(changes)
        if dry_run:
            logger.info(f" DRY RUN - Style Update Payload ({style_id}):")
            logger.log(json.dumps(payload.changes, indent=2))
            self._hydrate(
                style_id,
                name,
                element_type,
                wire_changes,
                clear_properties=("font_family",) if clear_font_family else (),
            )
            return self.apply_state_definitions(name, states, dry_run=True)
        if not self._dispatch(payload, "Failed to send/cache"):
            return False

        merged = self._host.base_style_properties(style_id)
        merged.update(wire_changes)
        if clear_font_family:
            merged.pop("font_family", None)
        if not self._put_cache(
            name,
            {"id": style_id, "type": element_type, "%p": merged},
        ):
            return False
        return self.apply_state_definitions(name, states, dry_run=False)

    def rename_style(self, style_id: str, new_name: str, dry_run: bool = False) -> bool:
        payload = PayloadBuilder(self._host.appname)
        payload.add_change(
            intent_name="SetStyleData",
            path_array=["styles", style_id, "%d"],
            body=new_name,
        )
        if dry_run:
            logger.info(f"\n DRY RUN - Rename Payload ({style_id}):")
            logger.log(json.dumps(payload.changes, indent=2))
            return True
        return self._dispatch(payload, "Failed to rename")

    def create_button_style(self, name: str, theme_json: str, dry_run: bool = False) -> bool:
        try:
            theme = json.loads(theme_json)
        except json.JSONDecodeError:
            logger.error(f"Invalid theme_json: {theme_json}")
            return False
        if not isinstance(theme, dict):
            logger.error("theme_json must contain an object")
            return False
        theme = {key: value for key, value in theme.items() if isinstance(value, dict)}
        for state in theme.values():
            for property_name, value in list(state.items()):
                if isinstance(value, str) and (
                    value.startswith("#") or value.startswith("rgba") or value.startswith("var(")
                ):
                    state[property_name] = self._resolve_color(value)

        style_id = self._references.find_style_id(name, "Button")

        builder = StyleBuilder(self._host.id_gen)
        payload = PayloadBuilder(self._host.appname)
        if not style_id:
            style_payload = builder.create_style(name, element_type="Button")
            style_id = str(style_payload["id"])
            payload.add_update_index(["_index", "id_to_path", style_id], f"styles.{style_id}")
            payload.add_create_style(style_id, style_payload)
        for intent in builder.apply_theme(style_id=style_id, theme=theme, element_type="Button"):
            payload.add_intent(intent)
        if dry_run or bool(getattr(self._host, "dry_run", False)):
            logger.info(f"\n DRY RUN - Composite Style Payload ({style_id}):")
            logger.log(json.dumps(payload.changes, indent=2))
            return True
        if not self._dispatch(payload, "Failed to send"):
            return False
        return self._put_cache(name, {"id": style_id, "type": "Button"})

    def add_style_condition(
        self,
        style_name: str,
        condition: str,
        dry_run: bool = False,
        index: str | None = None,
        **properties: Any,
    ) -> bool:
        style_id = self._references.find_style_id(style_name)
        if not style_id:
            logger.error(f"Style '{style_name}' not found.")
            return False
        raw_condition = str(condition or "").strip()
        if not raw_condition:
            logger.error("Missing condition.")
            return False
        chain = self._parse_condition_chain(raw_condition)
        if not chain:
            logger.error(f"Could not parse condition '{condition}'.")
            return False

        comparison_map = self.state_property_wire_map()
        base_properties = self._host.base_style_properties(style_id)
        color_keys = {
            "bg_color",
            "font_color",
            "icon_color",
            "border_color",
            "shadow_color",
            "border_color_top",
            "border_color_bottom",
            "border_color_left",
            "border_color_right",
            "text_shadow_color",
        }
        clean_properties: dict[str, Any] = {}
        for property_name, value in properties.items():
            if value is None or (isinstance(value, bool) and value is False):
                continue
            if property_name in color_keys and isinstance(value, str):
                resolved = self._resolve_color(value)
                wire_key = comparison_map.get(property_name, property_name)
                base_value = base_properties.get(wire_key, base_properties.get(property_name))
                clean_properties[property_name] = value if resolved != value and base_value == resolved else resolved
            else:
                clean_properties[property_name] = value
        if chain[0][0] == "not_clickable":
            clean_properties = self._host.augment_disabled_style_state(
                style_id,
                clean_properties,
                comparison_map,
                base_properties,
            )
        clean_properties = self._host.compensate_style_state_padding(style_id, clean_properties)
        transition_intents = self.build_transition_intents(
            style_id,
            clean_properties,
            comparison_map=comparison_map,
        )
        existing_condition_id = self.find_style_condition_id(style_id, chain)
        if index:
            condition_id = str(index)
            is_new = existing_condition_id is None or condition_id != existing_condition_id
        elif existing_condition_id:
            condition_id = existing_condition_id
            is_new = False
        else:
            condition_id = f"b{''.join(random.choices(string.ascii_letters + string.digits, k=5))}"
            is_new = True
        intents = StyleBuilder.add_style_condition(
            style_id=style_id,
            condition_id=condition_id,
            condition_type=chain,
            properties=clean_properties,
            is_new=is_new,
        )
        if dry_run:
            logger.info(f" DRY RUN - add/update condition '{condition}' on style '{style_name}'")
            logger.log(json.dumps(transition_intents + intents, indent=2))
            return True

        if transition_intents:
            payload = PayloadBuilder(self._host.appname)
            for intent in transition_intents:
                payload.add_intent(intent)
            if not self._dispatch(payload, "Failed to apply style transitions"):
                return False
        creation = [intent for intent in intents if intent.get("intent") == "NewStyleState"]
        properties_intents = [intent for intent in intents if intent.get("intent") != "NewStyleState"]
        if creation:
            payload = PayloadBuilder(self._host.appname)
            for intent in creation:
                payload.add_intent(intent)
            payload.add_change_raw({"type": "id_counter", "value": random.randint(10000000, 20000000)})
            if not self._dispatch(payload, "Failed to initialize style condition"):
                return False
        if properties_intents:
            payload = PayloadBuilder(self._host.appname)
            for intent in properties_intents:
                payload.add_intent(intent)
            if not self._dispatch(payload, "Failed to apply condition properties"):
                return False

        cache_entry = self._cache_entry_for_style(style_name, style_id)
        conditions = cache_entry.get("conditions")
        if not isinstance(conditions, dict):
            conditions = {}
        if len(chain) == 1:
            friendly = {
                "is_hovered": "hover",
                "is_pressed": "pressed",
                "is_focused": "focus",
                "not_clickable": "not_clickable",
                "isnt_valid": "isnt_valid",
                "is_visible": "visible",
                "isnt_visible": "not_visible",
            }
            conditions[friendly.get(chain[0][0], chain[0][0])] = condition_id
        else:
            conditions[raw_condition] = condition_id
        cache_entry["conditions"] = conditions
        return self._put_cache(style_name, cache_entry)

    def apply_state_definitions(
        self,
        style_name: str,
        states: list[tuple[str, dict[str, Any]]],
        *,
        dry_run: bool = False,
    ) -> bool:
        for condition, properties in states:
            if not self.add_style_condition(
                style_name,
                condition,
                dry_run=dry_run,
                **properties,
            ):
                return False
        return True

    def find_style_condition_id(
        self,
        style_id: str,
        condition_type: str | list[tuple[str, str | None]],
    ) -> str | None:
        target_chain = self._target_condition_chain(condition_type)
        if not target_chain:
            return None
        discovery, cache = self._host.style_reference_snapshots()
        candidates: list[dict[str, Any]] = []
        raw_style = discovery.get("styles", {}).get(style_id) if isinstance(discovery.get("styles"), dict) else None
        if isinstance(raw_style, dict):
            candidates.append(raw_style)
        cache_styles = cache.get("styles") if isinstance(cache, dict) else None
        if isinstance(cache_styles, dict):
            candidates.extend(
                entry
                for entry in cache_styles.values()
                if isinstance(entry, dict) and str(entry.get("id") or "") == style_id
            )
        for candidate in candidates:
            states = candidate.get("%s")
            if not isinstance(states, dict):
                continue
            for condition_id, state in states.items():
                condition = state.get("%c") if isinstance(state, dict) else None
                if self._extract_condition_chain(condition) == target_chain:
                    return str(condition_id)
        return None

    def reorder_style_states(
        self,
        style_name: str,
        order_list: list[str] | str,
        dry_run: bool = False,
        prune_missing: bool = False,
    ) -> bool:
        style_id = self._references.find_style_id(style_name)
        if not style_id:
            logger.error(f"Style '{style_name}' not found.")
            return False
        style = self._style_snapshot(style_id)
        states = style.get("%s") if isinstance(style, dict) else None
        if not isinstance(states, dict) or not states:
            logger.error(f"No states found for style '{style_name}'.")
            return False
        wire_to_trigger = {
            "isnt_clickable": "disabled",
            "is_hovered": "hover",
            "is_pressed": "pressed",
            "is_focused": "focus",
            "isnt_valid": "invalid",
            "is_visible": "visible",
            "isnt_visible": "not_visible",
        }
        identified: dict[str, dict[str, Any]] = {}
        for state in states.values():
            condition = state.get("%c") if isinstance(state, dict) else None
            node = condition.get("%n") if isinstance(condition, dict) else None
            name = node.get("%nm") if isinstance(node, dict) else None
            trigger = wire_to_trigger.get(str(name)) if name is not None else None
            if trigger and isinstance(state, dict):
                identified[trigger] = state
        if not identified:
            logger.error(f"Could not identify known triggers in style '{style_name}' states.")
            return False
        requested = self.parse_reorder_order(order_list)
        if not requested:
            logger.error("Could not parse 'order'.")
            return False
        ordered: list[dict[str, Any]] = []
        for trigger in requested:
            state = identified.pop(trigger, None)
            if state is not None:
                ordered.append(self._ensure_state_type(state))
        if not prune_missing:
            for trigger in sorted(identified):
                ordered.append(self._ensure_state_type(identified[trigger]))
        ordered_map = {str(index): state for index, state in enumerate(ordered)}
        payload = PayloadBuilder(self._host.appname)
        for intent in StyleBuilder.reorder_states(style_id, ordered_map):
            payload.add_intent(intent)
        if dry_run:
            logger.info(f" DRY RUN - Reordering states for '{style_name}'")
            logger.log(json.dumps(payload.changes, indent=2))
            return True
        if not self._dispatch(payload, "Failed to reorder states"):
            return False
        cache_entry = self._cache_entry_for_style(style_name, style_id)
        cache_entry["%s"] = copy.deepcopy(ordered_map)
        conditions: dict[str, str] = {}
        for condition_id, state in ordered_map.items():
            name = (((state.get("%c", {}) if isinstance(state, dict) else {}).get("%n", {})).get("%nm"))
            friendly = {
                "is_hovered": "hover",
                "is_pressed": "pressed",
                "is_focused": "focus",
                "isnt_clickable": "not_clickable",
                "isnt_valid": "isnt_valid",
                "is_visible": "visible",
                "isnt_visible": "not_visible",
            }.get(name)
            if friendly:
                conditions[friendly] = condition_id
        if conditions:
            existing_conditions = cache_entry.get("conditions")
            cache_entry["conditions"] = {
                **(existing_conditions if isinstance(existing_conditions, dict) else {}),
                **conditions,
            }
        return self._put_cache(style_name, cache_entry)

    def delete_style(
        self,
        name: str,
        element_type: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        normalized_type = self._references.normalize_element_type(element_type) if element_type else None
        style_id = self._references.find_style_id(name, normalized_type)
        if not style_id and self._references.looks_like_style_id(name, normalized_type):
            style_id = name
        if not style_id:
            logger.error(f"Style '{name}' not found.")
            return False
        payload = PayloadBuilder(self._host.appname)
        payload.add_delete_style(style_id)
        if dry_run:
            logger.info(f"\n DRY RUN - Delete Style ({style_id})")
            return True
        if not self._dispatch(payload, "Failed to delete style"):
            return False
        return self._remove_cache_ids({style_id}, names={name})

    def delete_styles(
        self,
        names: list[str] | None = None,
        pattern: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        candidates = self._style_candidates()
        if not candidates:
            logger.error("No styles found")
            return False
        requested = {str(name).lower().strip() for name in names or []}
        try:
            regex = re.compile(pattern, re.IGNORECASE) if pattern else None
        except re.error as exc:
            logger.error(str(exc))
            return False
        targets: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for candidate in candidates:
            candidate_names = [
                str(candidate.get("name") or ""),
                *(str(alias) for alias in candidate.get("aliases", ())),
            ]
            selected = any(
                candidate_name.lower().strip() in requested
                or bool(regex and regex.search(candidate_name))
                for candidate_name in candidate_names
            )
            style_id = str(candidate.get("id") or "")
            if (
                selected
                and style_id
                and style_id not in seen_ids
                and not bool(candidate.get("is_default"))
            ):
                targets.append(candidate)
                seen_ids.add(style_id)
        if not targets:
            logger.error("No matching custom styles found to delete")
            return False
        payload = PayloadBuilder(self._host.appname)
        for target in targets:
            payload.add_delete_style(str(target["id"]))
        if dry_run:
            logger.info(f"\n DRY RUN - Delete {len(targets)} Styles")
            return True
        if not self._dispatch(payload, "Failed to delete styles"):
            return False
        return self._remove_cache_ids(
            {str(target["id"]) for target in targets},
            names={str(target.get("name") or "") for target in targets},
        )

    def clear_custom_styles(self, dry_run: bool = False) -> bool:
        custom = [candidate for candidate in self._style_candidates() if not candidate.get("is_default")]
        if not custom:
            return True
        return self.delete_styles(
            names=[str(candidate.get("name") or "") for candidate in custom],
            dry_run=dry_run,
        )

    def _resolve_color_kwargs(self, properties: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(properties)
        for property_name in self._COLOR_KEYS:
            value = resolved.get(property_name)
            if value is not None:
                resolved[property_name] = self._resolve_color(str(value))
        return resolved

    def _existing_create_target(
        self,
        name: str,
        element_type: str,
        expected_id: str,
    ) -> dict[str, Any] | None:
        candidates = self._style_candidates(current_only=True)
        legacy: dict[str, Any] | None = None
        for candidate in candidates:
            if str(candidate.get("name") or "").casefold() != str(name).casefold():
                continue
            candidate_type = self._references.normalize_element_type(str(candidate.get("type") or ""))
            if candidate_type != element_type:
                continue
            candidate_id = str(candidate.get("id") or "")
            if candidate_id == expected_id:
                return candidate
            if candidate_id.startswith(f"{element_type}_"):
                legacy = legacy or candidate
        if legacy:
            logger.warning(
                f"Found non-canonical style '{name}' (ID: {legacy.get('id')}); "
                f"expected '{expected_id}'. Creating canonical style ID."
            )
        return None

    def _property_match(
        self,
        name: str,
        element_type: str,
        properties: dict[str, Any],
    ) -> dict[str, Any] | None:
        expected = self._wire_properties(StyleBuilder(self._host.id_gen).update_style("dummy", **properties))
        if not expected:
            return None
        discovery, _ = self._host.style_reference_snapshots()
        raw_styles = discovery.get("styles") if isinstance(discovery, dict) else None
        raw_styles = raw_styles if isinstance(raw_styles, dict) else {}
        candidates: list[tuple[str, dict[str, Any]]] = [
            (str(style_id), raw)
            for style_id, raw in raw_styles.items()
            if isinstance(raw, dict)
        ]
        for style_id, raw in candidates:
            candidate_type = str(raw.get("type") or raw.get("%x") or "")
            if not candidate_type and style_id.startswith(f"{element_type}_"):
                candidate_type = element_type
            if self._references.normalize_element_type(candidate_type) != element_type:
                continue
            candidate_name = str(
                raw.get("name") or raw.get("display") or raw.get("%d") or style_id
            ).strip()
            if not self._is_generic_name(name) and self._is_generic_name(candidate_name):
                continue
            if element_type == "Image":
                generic = {"content", "image", "wrapper"}
                if ("/" in name and candidate_name.casefold() in generic) or (
                    name.casefold() in generic and "/" in candidate_name
                ):
                    continue
            candidate_properties = raw.get("%p")
            if not isinstance(candidate_properties, dict) or not candidate_properties:
                continue
            if all(
                self._property_values_match(candidate_properties.get(key), value, key)
                for key, value in expected.items()
            ):
                return {"id": style_id, "name": candidate_name, "type": element_type}
        return None

    def _find_update_style_id(self, name: str, element_type: str) -> str:
        candidates = self._style_candidates(current_only=True)
        legacy = ""
        for candidate in candidates:
            if str(candidate.get("name") or "").casefold() != str(name).casefold():
                continue
            if self._references.normalize_element_type(str(candidate.get("type") or "")) != element_type:
                continue
            style_id = str(candidate.get("id") or "")
            if style_id.startswith(f"{element_type}_"):
                return style_id
            legacy = legacy or style_id
        if legacy:
            return legacy
        if self._references.looks_like_style_id(name):
            prefix = name.split("_", 1)[0]
            if prefix in self._DIRECT_STYLE_ID_TYPES:
                return name
        return ""

    def _style_candidates(self, *, current_only: bool = False) -> list[dict[str, Any]]:
        discovery, cache = self._host.style_reference_snapshots()
        raw_styles = discovery.get("styles") if isinstance(discovery, dict) else None
        raw_styles = raw_styles if isinstance(raw_styles, dict) else {}
        default_ids = self._references.default_style_ids()
        candidates_by_id: dict[str, dict[str, Any]] = {}

        def merge_candidate(
            style_id: str,
            name: str,
            element_type: Any,
            *,
            is_default: bool,
            properties: Any,
            states: Any,
        ) -> None:
            if not style_id:
                return
            existing = candidates_by_id.get(style_id)
            if existing is not None:
                aliases = list(existing.get("aliases", ()))
                if name and name != existing["name"] and name not in aliases:
                    aliases.append(name)
                existing["aliases"] = tuple(aliases)
                existing["is_default"] = bool(
                    existing.get("is_default") or is_default or style_id in default_ids
                )
                return
            candidates_by_id[style_id] = {
                "id": style_id,
                "name": name,
                "aliases": (),
                "type": element_type,
                "is_default": bool(is_default or style_id in default_ids),
                "%p": copy.deepcopy(properties if isinstance(properties, dict) else {}),
                "%s": copy.deepcopy(states if isinstance(states, dict) else {}),
            }

        for style_id, raw in raw_styles.items():
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or raw.get("display") or raw.get("%d") or style_id)
            merge_candidate(
                str(style_id),
                name,
                raw.get("type") or raw.get("%x") or str(style_id).split("_", 1)[0],
                is_default=bool(raw.get("is_default")),
                properties=raw.get("%p"),
                states=raw.get("%s"),
            )
        cached_styles = cache.get("styles") if isinstance(cache, dict) else None
        if isinstance(cached_styles, dict):
            for name, raw in cached_styles.items():
                if not isinstance(raw, dict):
                    continue
                cached_id = str(raw.get("id") or "")
                if current_only and cached_id not in raw_styles:
                    continue
                merge_candidate(
                    cached_id,
                    str(name),
                    raw.get("type") or raw.get("%x") or "",
                    is_default=bool(raw.get("is_default")),
                    properties=raw.get("%p"),
                    states=raw.get("%s"),
                )
        return list(candidates_by_id.values())

    def _remove_stale_cache_aliases(self, name: str, element_type: str) -> bool:
        discovery, cache = self._host.style_reference_snapshots()
        raw_styles = discovery.get("styles") if isinstance(discovery, dict) else None
        current_ids = {str(style_id) for style_id in raw_styles} if isinstance(raw_styles, dict) else set()
        cached_styles = cache.get("styles") if isinstance(cache, dict) else None
        if not isinstance(cached_styles, dict):
            return True
        stale_aliases: list[str] = []
        for alias, raw in cached_styles.items():
            if str(alias).casefold() != str(name).casefold() or not isinstance(raw, dict):
                continue
            cached_type = self._references.normalize_element_type(
                str(raw.get("type") or raw.get("%x") or "")
            )
            if cached_type and cached_type != element_type:
                continue
            style_id = str(raw.get("id") or "").strip()
            if style_id and style_id not in current_ids:
                stale_aliases.append(str(alias))
        if not stale_aliases:
            return True
        try:
            for alias in stale_aliases:
                self._host.remove_style_definition_cache(alias)
            self._host.save_style_definition_cache()
        except Exception as exc:
            logger.error(f"Failed to remove stale style cache for '{name}': {exc}")
            return False
        self._references.invalidate()
        return True

    def _style_snapshot(self, style_id: str) -> dict[str, Any]:
        discovery, cache = self._host.style_reference_snapshots()
        raw_styles = discovery.get("styles") if isinstance(discovery, dict) else None
        raw = raw_styles.get(style_id) if isinstance(raw_styles, dict) else None
        if isinstance(raw, dict) and raw.get("%s"):
            return raw
        cached_styles = cache.get("styles") if isinstance(cache, dict) else None
        if isinstance(cached_styles, dict):
            for cached in cached_styles.values():
                if isinstance(cached, dict) and str(cached.get("id") or "") == style_id:
                    if cached.get("%s"):
                        return cached
        return raw if isinstance(raw, dict) else {}

    def _cache_entry_for_style(self, style_name: str, style_id: str) -> dict[str, Any]:
        _, cache = self._host.style_reference_snapshots()
        cached_styles = cache.get("styles") if isinstance(cache, dict) else None
        cached = cached_styles.get(style_name) if isinstance(cached_styles, dict) else None
        if isinstance(cached, dict):
            return copy.deepcopy(cached)
        style = self._style_snapshot(style_id)
        element_type = str(style.get("type") or style.get("%x") or style_id.split("_", 1)[0])
        return {
            "id": style_id,
            "type": element_type,
            "%p": copy.deepcopy(style.get("%p") or {}),
        }

    @classmethod
    def _parse_condition_chain(cls, raw_condition: str) -> list[tuple[str, str | None]]:
        tokens: list[str] = []
        operators: list[str] = []
        current = ""
        for character in raw_condition:
            if character in {"+", ","}:
                tokens.append(current.strip())
                operators.append("and_" if character == "+" else "or_")
                current = ""
            else:
                current += character
        tokens.append(current.strip())
        mappings = {
            "disabled": "not_clickable",
            "not clickable": "not_clickable",
            "not_clickable": "not_clickable",
            "isnt_clickable": "not_clickable",
            "invalid": "isnt_valid",
            "pressed": "is_pressed",
            "visible": "is_visible",
            "not_visible": "isnt_visible",
        }
        chain: list[tuple[str, str | None]] = []
        for index, token in enumerate(tokens):
            if not token:
                continue
            raw = token.strip().lower()
            canonical = cls.normalize_trigger_alias(raw) or raw
            chain.append((mappings.get(canonical, canonical), operators[index] if index < len(operators) else None))
        return chain

    @staticmethod
    def _target_condition_chain(
        condition_type: str | list[tuple[str, str | None]],
    ) -> list[tuple[str, str | None]]:
        mapping = {
            "hover": "is_hovered",
            "pressed": "is_pressed",
            "focus": "is_focused",
            "not_clickable": "isnt_clickable",
            "isnt_valid": "isnt_valid",
            "invalid": "isnt_valid",
            "disabled": "isnt_clickable",
            "visible": "is_visible",
            "not_visible": "isnt_visible",
            "hidden": "isnt_visible",
        }
        if isinstance(condition_type, str):
            tokens = [token.strip().lower() for token in condition_type.split(",")]
            return [
                (mapping.get(token, token), "or_" if index < len(tokens) - 1 else None)
                for index, token in enumerate(tokens)
            ]
        return [(mapping.get(name, name), operator) for name, operator in condition_type]

    @classmethod
    def _extract_condition_chain(cls, definition: Any) -> list[tuple[str, str | None]]:
        if not isinstance(definition, dict):
            return []
        node = definition.get("%n")
        if not isinstance(node, dict):
            return []
        name = node.get("%nm")
        if not name:
            return []
        next_node = node.get("%n")
        operator = None
        remaining: list[tuple[str, str | None]] = []
        if isinstance(next_node, dict) and next_node.get("%nm") in {"or_", "and_"}:
            operator = str(next_node["%nm"])
            remaining = cls._extract_condition_chain(next_node.get("%a"))
        return [(str(name), operator), *remaining]

    @staticmethod
    def _ensure_state_type(state: dict[str, Any]) -> dict[str, Any]:
        return dict(state) if "%x" in state else {**state, "%x": "State"}

    @staticmethod
    def _wire_properties(changes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            str(path[3]): change.get("body")
            for change in changes
            if isinstance((path := change.get("path")), list)
            and len(path) >= 4
            and path[2] == "%p"
        }

    @staticmethod
    def _property_values_match(existing: Any, expected: Any, property_name: str) -> bool:
        if existing == expected:
            return True
        falsy = (None, "", "none", 0, "0", False)
        return (existing in falsy and expected in falsy) or (
            property_name == "boxshadow_enable" and existing is None and expected is True
        )

    @staticmethod
    def _is_generic_name(value: str) -> bool:
        normalized = " ".join(str(value or "").casefold().replace("-", " ").replace("_", " ").split())
        return normalized in {"button", "text", "group", "input", "image", "content", "wrapper"}

    def _dispatch(self, payload: PayloadBuilder, error_prefix: str) -> bool:
        try:
            self._host.dispatch_style_definition_payload(payload)
            return True
        except Exception as exc:
            logger.error(f"{error_prefix}: {exc}")
            return False

    def _put_cache(self, name: str, data: dict[str, Any]) -> bool:
        try:
            self._host.put_style_definition_cache(name, copy.deepcopy(data))
            self._host.save_style_definition_cache()
            return True
        except Exception as exc:
            logger.error(f"Failed to cache style '{name}': {exc}")
            return False

    def _remove_cache_ids(self, style_ids: set[str], *, names: set[str]) -> bool:
        try:
            _, cache = self._host.style_reference_snapshots()
            cached_styles = cache.get("styles") if isinstance(cache, dict) else None
            keys = set(names)
            if isinstance(cached_styles, dict):
                keys.update(
                    str(cache_name)
                    for cache_name, raw in cached_styles.items()
                    if isinstance(raw, dict) and str(raw.get("id") or "") in style_ids
                )
            for name in keys:
                if name:
                    self._host.remove_style_definition_cache(name)
            self._host.save_style_definition_cache()
            return True
        except Exception as exc:
            logger.error(f"Failed to clean style cache: {exc}")
            return False

    def _hydrate(
        self,
        style_id: str,
        name: str,
        element_type: str,
        properties: dict[str, Any],
        *,
        clear_properties: tuple[str, ...] = (),
    ) -> None:
        self._host.hydrate_style_definition(
            style_id,
            name,
            element_type,
            properties,
            clear_properties=clear_properties,
        )
        self._references.invalidate()
