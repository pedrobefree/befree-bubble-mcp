"""Style assignment intents and element override policy."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..bubble_sdk import PayloadBuilder, logger
else:
    try:
        from ..bubble_sdk import PayloadBuilder, logger
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import PayloadBuilder, logger

from .protocols import StyleAssignmentHost
from .references import StyleReferenceResolver


def _is_payload_builder(value: Any) -> bool:
    """Accept package and direct-CLI PayloadBuilder module identities."""
    return (
        isinstance(getattr(value, "changes", None), list)
        and callable(getattr(value, "add_set_data", None))
        and callable(getattr(getattr(value, "id_gen", None), "session_id", None))
    )


class StyleOverridePolicy:
    """Identify and prune style-driven element properties."""

    _MARKER_KEYS = (
        "%s1",
        "style",
        "style_id",
        "style_name",
        "style_ref",
        "style_reference",
    )
    _BASE_OVERRIDE_KEYS = (
        "opacity", "font_family", "font_weight", "%fs", "font_size", "%fa", "font_alignment",
        "%b", "bold", "%i", "italic", "%u", "underline", "%fc", "font_color", "%ws", "%lh",
        "%ls", "%vc", "%tes", "%tsh", "%tsv", "%tsb", "%tsc", "%bas", "%bgc", "%bgi",
        "background_color_if_empty_image", "%bgf", "%bgt", "background_gradient_mid", "%bgd",
        "background_gradient_style", "%b4", "%bga", "%bgp", "background_repeat", "%cb", "%rbv",
        "%rbh", "center_background", "repeat_background_vertical", "repeat_background_horizontal",
        "crop_responsive", "background_size_cover", "background_radial_gradient_shape",
        "background_radial_gradient_size", "background_radial_gradient_xpos",
        "background_radial_gradient_ypos", "four_border_style", "%bos", "%bw", "%bc", "%br",
        "border_roundness", "border_roundness_top", "border_roundness_right", "border_roundness_bottom",
        "border_roundness_left", "border_style_top", "border_style_bottom", "border_style_left",
        "border_style_right", "border_width_top", "border_width_bottom", "border_width_left",
        "border_width_right", "border_color_top", "border_color_bottom", "border_color_left",
        "border_color_right", "%bs", "%bh", "%bv", "%bsb", "%bsp", "%bsc", "boxshadow_enable",
        "padding_top", "padding_bottom", "padding_left", "padding_right", "button_gap", "icon_size",
        "tag_type", "greyout_color", "grayout_color", "greyout_blur", "grayout_blur",
        "prevent_user_from_closing_through_esc",
    )
    _ALIAS_MAP = {
        "%bas": ("background_style", "bg_style"),
        "%bgc": ("background_color", "bg_color", "bgcolor"),
        "%bgi": ("background_image", "bg_image"),
        "%bgf": ("background_gradient_color1", "gradient_color1"),
        "%bgt": ("background_gradient_color2", "gradient_color2"),
        "%bgd": ("background_gradient_style", "gradient_style"),
        "%bgp": ("background_repeat",),
        "%cb": ("center_background",),
        "%rbv": ("repeat_background_vertical",),
        "%rbh": ("repeat_background_horizontal",),
        "%bc": ("border_color",),
        "%bw": ("border_width",),
        "%bos": ("border_style",),
        "%br": ("border_roundness", "border_radius"),
        "%bs": ("shadow_style",),
        "%bh": ("shadow_h",),
        "%bv": ("shadow_v",),
        "%bsb": ("shadow_blur",),
        "%bsp": ("shadow_spread",),
        "%bsc": ("shadow_color",),
        "%fa": ("font_alignment",),
        "%fs": ("font_size",),
        "%fc": ("font_color",),
        "%lh": ("line_height",),
        "%ls": ("letter_spacing",),
        "%ws": ("word_spacing",),
        "%ss": ("separator_style",),
        "%sw": ("separator_width",),
        "%sc": ("separator_color",),
        "padding_top": ("pt",),
        "padding_bottom": ("pb",),
        "padding_left": ("pl",),
        "padding_right": ("pr",),
        "greyout_color": ("grayout_color",),
        "greyout_blur": ("grayout_blur",),
    }
    _DEFAULT_FALSE_KEYS = {
        "crop_responsive",
        "background_size_cover",
        "center_background",
        "repeat_background_vertical",
        "repeat_background_horizontal",
        "%cb",
        "%rbv",
        "%rbh",
    }
    _GROUP_STRUCTURAL_KEYS = {
        "%gt", "%ds", "unique_id", "%iv", "collapse_when_hidden", "button_disabled",
        "container_layout", "%3f", "floating_reference_horizontal_resp", "%b4", "float_zindex",
        "parallax", "%w", "%h", "min_width_css", "max_width_css", "min_height_css",
        "max_height_css", "single_width", "single_height", "fit_width", "fit_height", "%t", "%l",
        "margin_top", "margin_right", "margin_bottom", "margin_left", "reference", "offset_top",
        "offset_left",
    }
    _POPUP_STRUCTURAL_KEYS = _GROUP_STRUCTURAL_KEYS - {"%b4"}
    _PROTECTED_KEYS = {
        "Group": _GROUP_STRUCTURAL_KEYS,
        "FloatingGroup": _GROUP_STRUCTURAL_KEYS,
        "GroupFocus": _GROUP_STRUCTURAL_KEYS,
        "Table": {"container_layout", "%ds", "%gt", "%rs", "%nm"},
        "RepeatingGroup": {
            "%ds", "%v", "%gt", "container_layout", "%rs", "%c5", "%w", "%h",
            "min_width_css", "max_width_css", "min_height_css", "max_height_css", "fixed_rows",
            "fixed_columns", "show_all_items", "scroll_direction", "row_gap", "row_cell_gap",
            "column_cell_gap", "cell_min_width_css", "cell_min_height_css",
        },
        "Popup": _POPUP_STRUCTURAL_KEYS,
        "DateInput": {
            "%c1", "initial_content", "input_type", "binding_content_format", "content_format",
            "date_format", "custom_format", "start_monday", "show_month_year_picker", "time_format",
            "time_interval", "min_date", "max_date", "min_hour", "max_hour", "%1m", "disabled",
            "auto_binding", "bind_field",
        },
    }
    _SDK_KEY_MAP = {
        "bg_color": "%bgc", "background_color": "%bgc", "background_style": "%bas",
        "bg_style": "%bas", "border_radius": "%br", "border_roundness": "%br",
        "border_width": "%bw", "border_color": "%bc", "border_style": "%bos",
        "border_style_top": "border_style_top", "border_style_bottom": "border_style_bottom",
        "border_style_left": "border_style_left", "border_style_right": "border_style_right",
        "border_width_top": "border_width_top", "border_width_bottom": "border_width_bottom",
        "border_width_left": "border_width_left", "border_width_right": "border_width_right",
        "border_color_top": "border_color_top", "border_color_bottom": "border_color_bottom",
        "border_color_left": "border_color_left", "border_color_right": "border_color_right",
        "border_roundness_top_left": "border_roundness_top",
        "border_roundness_top_right": "border_roundness_right",
        "border_roundness_bottom_right": "border_roundness_bottom",
        "border_roundness_bottom_left": "border_roundness_left", "four_border_style": "four_border_style",
        "padding_top": "padding_top", "padding_bottom": "padding_bottom", "padding_left": "padding_left",
        "padding_right": "padding_right", "row_gap": "row_gap", "column_gap": "column_gap",
        "gap": "button_gap", "shadow_style": "%bs", "shadow_h": "%bh", "shadow_v": "%bv",
        "shadow_blur": "%bsb", "shadow_spread": "%bsp", "shadow_color": "%bsc",
        "font_size": "%fs", "line_height": "%lh", "font_color": "%fc", "text_color": "%fc",
        "font_family": "font_family", "font_weight": "font_weight", "min_width": "min_width_css",
        "min_width_css": "min_width_css", "max_width": "max_width_css",
        "max_width_css": "max_width_css", "min_height": "min_height_css",
        "min_height_css": "min_height_css", "max_height": "max_height_css",
        "max_height_css": "max_height_css", "fit_width": "fit_width", "fit_height": "fit_height",
        "single_width": "single_width", "single_height": "single_height",
        "container_layout": "container_layout", "use_gap": "use_gap", "order": "order",
        "nonant_alignment": "nonant_alignment", "vertical_alignment": "vert_alignment",
        "horizontal_alignment": "horiz_alignment", "container_horiz_alignment": "container_horiz_alignment",
        "container_vert_alignment": "container_vert_alignment",
    }
    _SDK_LINKED_KEYS = {
        "%br": (
            "border_roundness", "border_roundness_top_left", "border_roundness_top_right",
            "border_roundness_bottom_right", "border_roundness_left",
        ),
        "%bw": ("border_width", "border_width_top", "border_width_bottom", "border_width_left", "border_width_right"),
        "%bc": ("border_color", "border_color_top", "border_color_bottom", "border_color_left", "border_color_right"),
        "%bos": ("border_style", "border_style_top", "border_style_bottom", "border_style_left", "border_style_right"),
        "font_weight": ("bold",),
    }

    def __init__(self, host: StyleAssignmentHost, references: StyleReferenceResolver) -> None:
        self._host = host
        self._references = references

    @classmethod
    def marker_keys(cls) -> list[str]:
        return list(cls._MARKER_KEYS)

    @classmethod
    def base_override_keys(cls) -> list[str]:
        return list(cls._BASE_OVERRIDE_KEYS)

    def protected_keys(self, element_type: str | None) -> set[str]:
        normalized = self._references.normalize_element_type(element_type)
        return set(self._PROTECTED_KEYS.get(normalized, set()))

    def override_keys(
        self,
        element_type: str | None,
        *,
        target_style_id: str | None = None,
    ) -> list[str]:
        normalized_type = self._references.normalize_element_type(element_type)
        if not normalized_type:
            return []

        keys: list[str] = []
        seen: set[str] = set()

        def add_key(key: Any) -> None:
            key_str = str(key or "").strip()
            if not key_str or key_str in {"%s1", "style"} or key_str in seen:
                return
            seen.add(key_str)
            keys.append(key_str)

        for key in self._BASE_OVERRIDE_KEYS:
            add_key(key)

        discovery, cache = self._host.style_reference_snapshots()
        for snapshot in (discovery, cache):
            styles = snapshot.get("styles", {}) if isinstance(snapshot, dict) else {}
            if not isinstance(styles, dict):
                continue
            for style_obj in styles.values():
                if not isinstance(style_obj, dict):
                    continue
                style_type = str(style_obj.get("%x") or style_obj.get("type") or "").strip()
                if self._references.normalize_element_type(style_type) != normalized_type:
                    continue
                style_props = style_obj.get("%p")
                if isinstance(style_props, dict):
                    for key in style_props:
                        add_key(key)

        if target_style_id:
            for key in self._references.base_properties(str(target_style_id)):
                add_key(key)

        if normalized_type == "RepeatingGroup":
            for key in ("%ss", "%sw", "%sc", "separator_style", "separator_width", "separator_color"):
                add_key(key)

        for canonical_key, aliases in self._ALIAS_MAP.items():
            if canonical_key in seen or any(alias in seen for alias in aliases):
                add_key(canonical_key)
                for alias in aliases:
                    add_key(alias)
        return keys

    def prune(
        self,
        properties: dict[str, Any],
        *,
        element_type: str | None,
        style_id: str | None,
        sdk_properties: bool = False,
    ) -> None:
        if not isinstance(properties, dict):
            return
        resolved_style = str(style_id or "").strip()
        if not resolved_style:
            return
        style_props = self._references.base_properties(resolved_style)
        if sdk_properties:
            if not style_props:
                return
            self._prune_sdk_properties(properties, style_props)
            return
        self._prune_wire_properties(properties, element_type, resolved_style, style_props)

    def _prune_wire_properties(
        self,
        properties: dict[str, Any],
        element_type: str | None,
        style_id: str,
        style_props: dict[str, Any],
    ) -> None:
        override_keys = set(self.override_keys(element_type, target_style_id=style_id))
        protected_keys = self.protected_keys(element_type)
        removed: list[str] = []
        for key in list(properties):
            key_str = str(key or "").strip()
            if not key_str or key_str not in override_keys or key_str in protected_keys:
                continue
            value = properties.get(key)
            aliases = self._equivalent_keys(key_str)
            if any(alias in style_props and style_props.get(alias) == value for alias in aliases):
                properties.pop(key, None)
                removed.append(key_str)
            elif key_str in self._DEFAULT_FALSE_KEYS and value is False:
                if not any(alias in style_props for alias in aliases):
                    properties.pop(key, None)
                    removed.append(key_str)
        self._log_removed(removed)

    @classmethod
    def _equivalent_keys(cls, key: str) -> tuple[str, ...]:
        for canonical, aliases in cls._ALIAS_MAP.items():
            group = (canonical, *aliases)
            if key in group:
                return group
        return (key,)

    def _prune_sdk_properties(
        self,
        properties: dict[str, Any],
        style_props: dict[str, Any],
    ) -> None:
        removed: list[str] = []
        for key in list(properties):
            if key == "max_width_css" and properties.get("fit_width") is True:
                properties.pop(key, None)
                removed.append(key)
                continue
            if key == "max_height_css" and properties.get("fit_height") is True:
                properties.pop(key, None)
                removed.append(key)
                continue
            if properties.get("four_border_style") is True and not style_props.get("four_border_style"):
                if key.startswith(("border_style_", "border_width_", "border_color_", "border_roundness_")):
                    continue
            style_key = self._SDK_KEY_MAP.get(key)
            if not style_key or style_props.get(style_key) is None:
                continue
            if self._normalize_value(properties[key]) != self._normalize_value(style_props[style_key]):
                continue
            properties.pop(key, None)
            removed.append(key)
            for linked_key in self._SDK_LINKED_KEYS.get(style_key, ()):
                if linked_key in properties:
                    properties.pop(linked_key, None)
                    removed.append(linked_key)
        if properties.get("fit_width") is True and "max_width_css" in properties:
            properties.pop("max_width_css", None)
            removed.append("max_width_css")
        if properties.get("fit_height") is True and "max_height_css" in properties:
            properties.pop("max_height_css", None)
            removed.append("max_height_css")
        if (
            "bg_color" in properties
            and "background_style" not in properties
            and "bg_style" not in properties
            and style_props.get("%bas") == "none"
        ):
            properties["background_style"] = "bgcolor"
        self._log_removed(removed)

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized.endswith("px"):
                try:
                    numeric = float(normalized[:-2].strip())
                    return int(numeric) if numeric == int(numeric) else numeric
                except ValueError:
                    pass
            return normalized
        if isinstance(value, (int, float)):
            try:
                return int(value) if value == int(value) else value
            except (ValueError, TypeError):
                return value
        return value

    @staticmethod
    def _log_removed(removed: list[str]) -> None:
        if removed:
            logger.info("Pruned redundant style overrides: " + ", ".join(sorted(set(removed))))


class StyleAssignmentService:
    """Build ordered style assignment and removal payload changes."""

    def __init__(self, overrides: StyleOverridePolicy) -> None:
        self.overrides = overrides

    def assign(
        self,
        payload: PayloadBuilder,
        element_path: list[str],
        style_id: str | None,
        style_props: dict[str, Any] | None = None,
        include_set_data: bool = True,
        *,
        clear_override_keys: list[str] | None = None,
        marker_prop_updates: dict[str, Any] | None = None,
        extra_marker_keys: list[str] | None = None,
        explicit_props: dict[str, Any] | None = None,
    ) -> None:
        if not _is_payload_builder(payload):
            return
        resolved_style = str(style_id or "").strip()
        if not resolved_style:
            return
        blocked = {
            str(key)
            for key, value in (explicit_props or {}).items()
            if value is not None
        }
        if clear_override_keys is not None:
            self.clear_overrides(payload, element_path, clear_override_keys, blocked_keys=blocked)
            self.clear_markers(
                payload,
                element_path,
                prop_updates=marker_prop_updates,
                extra_keys=extra_marker_keys,
            )
        if include_set_data:
            payload.add_set_data(element_path + ["%s1"], resolved_style)

        intent_id = random.randint(1, 999999)
        normalized_props = None
        if isinstance(style_props, dict):
            normalized_props = {key: value for key, value in style_props.items() if value is not None}
        self._append_assign_style(payload, element_path + ["%s1"], resolved_style, intent_id)
        if normalized_props is not None:
            self._append_assign_style(payload, element_path + ["%p"], normalized_props, intent_id)
        for key, value in (explicit_props or {}).items():
            if value is not None:
                payload.add_set_data(element_path + ["%p", str(key)], value)

    def clear(
        self,
        payload: PayloadBuilder,
        element_path: list[str],
        include_set_data: bool = True,
    ) -> None:
        if not _is_payload_builder(payload):
            return
        if include_set_data:
            payload.add_set_data(element_path + ["%s1"], None)
        self._append_assign_style(
            payload,
            element_path + ["%s1"],
            None,
            random.randint(1, 999999),
        )

    def clear_markers(
        self,
        payload: PayloadBuilder,
        element_path: list[str],
        *,
        prop_updates: dict[str, Any] | None = None,
        extra_keys: list[str] | None = None,
    ) -> None:
        if not _is_payload_builder(payload):
            return
        blocked = {str(key) for key in (prop_updates or {})}
        keys = self.overrides.marker_keys()
        if isinstance(extra_keys, list):
            keys.extend(str(key) for key in extra_keys if str(key).strip())
        seen: set[str] = set()
        for key in keys:
            key_str = str(key or "").strip()
            if not key_str or key_str in blocked or key_str in seen:
                continue
            seen.add(key_str)
            payload.add_set_data(element_path + ["%p", key_str], None)

    @staticmethod
    def clear_overrides(
        payload: PayloadBuilder,
        element_path: list[str],
        override_keys: list[str],
        *,
        blocked_keys: set[str] | None = None,
    ) -> None:
        if not _is_payload_builder(payload):
            return
        blocked = blocked_keys or set()
        seen: set[str] = set()
        for key in override_keys:
            key_str = str(key or "").strip()
            if not key_str or key_str in blocked or key_str in seen:
                continue
            seen.add(key_str)
            payload.add_set_data(element_path + ["%p", key_str], None)

    @staticmethod
    def _append_assign_style(
        payload: PayloadBuilder,
        path: list[str],
        body: Any,
        intent_id: int,
    ) -> None:
        payload.changes.append(
            {
                "intent": {"name": "AssignStyle", "id": intent_id, "source_appname": ""},
                "path_array": path,
                "body": body,
                "version_control_api_version": 4,
                "changelog_data": [],
                "session_id": payload.id_gen.session_id(),
            }
        )
