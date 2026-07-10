#!/usr/bin/env python3
"""
Bubble SDK - Framework completo para manipulação da API do Bubble Editor
Consolida todos os geradores e helpers em uma única biblioteca
"""

import os
import json
import random
import string
import requests
import copy
import pickle
import tempfile
from datetime import datetime
import re
from typing import Dict, List, Any, Optional, Union, Tuple


# ==========================================
# CORE: LOGGER
# ==========================================

class BubbleLogger:
    """Padronização de logs com emojis e níveis"""

    def __init__(self, debug: bool = False):
        self.debug_mode = debug

    def info(self, msg: str):
        print(f"ℹ️ {msg}")

    def success(self, msg: str):
        print(f"✅ {msg}")

    def warning(self, msg: str):
        print(f"⚠️ {msg}")

    def error(self, msg: str):
        print(f"❌ {msg}")

    def debug(self, msg: str):
        if self.debug_mode:
            print(f" {msg}")

    def log(self, msg: str):
        print(msg)

logger = BubbleLogger(debug=True)

# ==========================================
# CORE: ID GENERATORS
# ==========================================

class BubbleIDGenerator:
    """Gerador centralizado de IDs no padrão Bubble"""

    @staticmethod
    def element_id(length: int = 5) -> str:
        """Gera ID de elemento: bXXXX"""
        chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
        return 'b' + ''.join(random.choices(chars, k=length-1))

    @staticmethod
    def fiber_id() -> str:
        """Gera Fiber ID: timestamp_ms x random_18_digits"""
        ts = int(datetime.now().timestamp() * 1000)
        rand = random.randint(100000000000000000, 999999999999999999)
        return f"{ts}x{rand}"

    @staticmethod
    def session_id() -> str:
        """Gera Session ID: timestamp_ms x random_2_digits"""
        ts = int(datetime.now().timestamp() * 1000)
        rand = random.randint(10, 99)
        return f"{ts}x{rand}"

    @staticmethod
    def pl_id() -> str:
        """Gera PL ID: timestamp_ms x random_2_digits"""
        return BubbleIDGenerator.session_id()


# ==========================================
# CORE: PATH BUILDER
# ==========================================

class PathBuilder:
    """Construtor e validador de path arrays"""

    # Path Prefixes
    PREFIX_ELEMENT_DEFINITION = "%ed"  # Page Settings / Structure
    PREFIX_PAGE_ELEMENTS = "%p3"       # UI Elements and Workflows

    @staticmethod
    def build_for_structure(page_id: str, *container_ids: str) -> List[str]:
        """
        Constrói path para Page Settings / Element Definitions (%ed)
        Use for: Page properties, global settings
        """
        path = ["%ed", page_id]
        for container_id in container_ids:
            path.extend(["%el", container_id])
        return path

    @staticmethod
    def build_for_elements(page_id: str, *container_ids: str) -> List[str]:
        """
        Constrói path para UI Elements and Workflows (%p3)
        Use for: Groups, Buttons, Text, Workflows, Actions
        """
        path = ["%p3", page_id]
        for container_id in container_ids:
            path.extend(["%el", container_id])
        return path

    @staticmethod
    def build_for_workflow(page_id: str, workflow_id: str) -> List[str]:
        """
        Constrói path para Workflows (%p3 -> %wf)
        """
        return ["%p3", page_id, "%wf", workflow_id]

    @staticmethod
    def validate_create_path(path: List[str]) -> tuple:
        """Valida se path é adequado para CreateElement"""
        if not isinstance(path, list):
            return False, "Path deve ser uma lista"

        if not path:
            return False, "Path vazio"

        valid_prefixes = ["%ed", "%p3", "CustomDefinition"]
        if path[0] not in valid_prefixes:
            return False, f"Path deve começar com {valid_prefixes}"

        # Elements inside a parent need at least 2 elements (e.g. ["%ed", parent_id])
        # But root-level CustomDefinition creation uses length 1
        if len(path) < 2 and path[0] != "CustomDefinition":
            return False, "Path muito curto (mínimo: 2 elementos)"

        # CreateElement NÃO deve conter %p
        if "%p" in path:
            return False, "Path para criar elementos não pode conter '%p'"

        return True, "Path válido para CreateElement"

    @staticmethod
    def validate_edit_path(path: List[str]) -> tuple:
        """Valida se path é adequado para SetData"""
        if not isinstance(path, list):
            return False, "Path deve ser uma lista"

        if len(path) < 4:
            return False, "Path de edição muito curto"

        # SetData DEVE conter %p para property edits
        if "%p" not in path:
            return False, "Path de edição deve conter '%p'"

        return True, "Path válido para SetData"


# ==========================================
# CORE: ELEMENT BUILDERS
# ==========================================

class ElementBuilder:
    """Construtores de elementos do Bubble"""

    def __init__(self, id_gen: Optional[BubbleIDGenerator] = None):
        self.id_gen = id_gen or BubbleIDGenerator()

    @staticmethod
    def _normalize_container_layout(layout: Optional[str]) -> str:
        """Normalize user-friendly layout names to Bubble container_layout values."""
        raw = str(layout or "column").strip().lower().replace("-", "_").replace(" ", "_")
        if raw in {"align_to_parent", "align_parent"}:
            return "align_to_parent"
        if raw in {"relative"}:
            return "relative"
        if raw in {"fixed"}:
            return "fixed"
        if raw in {"row", "column"}:
            return raw
        return "column"

    @staticmethod
    def _normalize_css_length(value: Any) -> Optional[str]:
        """Normalize numeric/string length to Bubble CSS length format."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            n = int(value) if float(value).is_integer() else value
            return f"{n}px"
        raw = str(value).strip().lower()
        if not raw:
            return None
        if re.fullmatch(r"\d+(?:\.\d+)?(px|%)", raw):
            return raw
        if re.fullmatch(r"\d+(?:\.\d+)?", raw):
            return f"{raw}px"
        return str(value)

    @staticmethod
    def _apply_width_unset(properties: Dict[str, Any]) -> Dict[str, Any]:
        """Remove width-related defaults and disable fit-width behavior."""
        if not isinstance(properties, dict):
            return properties
        properties.pop("%w", None)
        explicit = properties.get("__explicit_dims", [])
        # Only pop defaults if they weren't explicitly overridden by something else
        # (e.g. min_width_css from _apply_dimensions)
        if "min_width" not in explicit and "fixed_width" not in explicit:
             properties.pop("min_width_css", None)
        if "max_width" not in explicit:
             properties.pop("max_width_css", None)

        return properties

    @staticmethod
    def _apply_dimensions(properties: Dict[str, Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply advanced dimension properties (min/max/fixed/fit) to the properties dict.

        Args:
            properties: The properties dict to update.
            kwargs: The kwargs containing dimension arguments.
        """
        explicit = properties.setdefault("__explicit_dims", [])

        # WIDTH
        # 1. Min Width
        if "min_width" in kwargs and kwargs["min_width"] is not None:
            normalized = ElementBuilder._normalize_css_length(kwargs["min_width"])
            if normalized is not None:
                properties["min_width_css"] = normalized
            if "min_width" not in explicit: explicit.append("min_width")

        # 2. Max Width
        if "max_width" in kwargs and kwargs["max_width"] is not None:
            normalized = ElementBuilder._normalize_css_length(kwargs["max_width"])
            if normalized is not None:
                properties["max_width_css"] = normalized
            if "max_width" not in explicit: explicit.append("max_width")

        # 3. Fit Width to Content
        if "fit_width" in kwargs and kwargs["fit_width"] is True:
            properties["fit_width"] = True
            if "fit_width" not in explicit: explicit.append("fit_width")

        # 4. Fixed Width (overrides fit_width)
        if "fixed_width" in kwargs and kwargs["fixed_width"] is True:
            properties["fit_width"] = False
            properties["fixed_width"] = True
            properties["single_width"] = True
            if "fixed_width" not in explicit: explicit.append("fixed_width")

        # HEIGHT
        # 1. Min Height
        if "min_height" in kwargs and kwargs["min_height"] is not None:
            normalized = ElementBuilder._normalize_css_length(kwargs["min_height"])
            if normalized is not None:
                properties["min_height_css"] = normalized
            if "min_height" not in explicit: explicit.append("min_height")

        # 2. Max Height
        if "max_height" in kwargs and kwargs["max_height"] is not None:
            normalized = ElementBuilder._normalize_css_length(kwargs["max_height"])
            if normalized is not None:
                properties["max_height_css"] = normalized
            if "max_height" not in explicit: explicit.append("max_height")

        # 3. Fit Height to Content
        if "fit_height" in kwargs and kwargs["fit_height"] is True:
            properties["fit_height"] = True
            if "fit_height" not in explicit: explicit.append("fit_height")

        # 4. Fixed Height (overrides fit_height)
        if "fixed_height" in kwargs and kwargs["fixed_height"] is True:
            properties["fit_height"] = False
            properties["fixed_height"] = True
            properties["single_height"] = True
            if "fixed_height" not in explicit: explicit.append("fixed_height")

        return properties

    def _add_visual_props(self, properties: Dict[str, Any], kwargs: Dict[str, Any]):
        """Adds visual properties (margin, border, shadow) to the properties dict"""
        # Bubble rejects several keys when explicitly set to null; preserve false/0.
        kwargs = {k: v for k, v in (kwargs or {}).items() if v is not None}

        # Margins
        if "margin_top" in kwargs:
            properties["margin_top"] = kwargs["margin_top"]
        if "margin_bottom" in kwargs:
            properties["margin_bottom"] = kwargs["margin_bottom"]
        if "margin_left" in kwargs:
            properties["margin_left"] = kwargs["margin_left"]
        if "margin_right" in kwargs:
            properties["margin_right"] = kwargs["margin_right"]

        if any(k in kwargs for k in ("margin_top", "margin_bottom", "margin_left", "margin_right")):
             print(f"DEBUG SDK: Applied margins to properties: {[(k, properties.get(k)) for k in ('margin_top', 'margin_bottom', 'margin_left', 'margin_right')]}")

        # Position aliases
        if "top" in kwargs: properties["%t"] = kwargs["top"]
        if "left" in kwargs: properties["%l"] = kwargs["left"]
        if "bottom" in kwargs: properties["%b"] = kwargs["bottom"]
        if "right" in kwargs: properties["%r"] = kwargs["right"]

        # Global element properties
        visible_value = kwargs.get("is_visible", kwargs.get("visible"))
        if visible_value is not None:
            properties["%iv"] = bool(visible_value)
        if "collapse_when_hidden" in kwargs:
            properties["collapse_when_hidden"] = bool(kwargs["collapse_when_hidden"])
        if "title_attribute" in kwargs:
            properties["title_attribute"] = kwargs["title_attribute"]
        if "button_disabled" in kwargs:
            properties["button_disabled"] = bool(kwargs["button_disabled"])
        if "spin_icon" in kwargs:
            properties["spin_icon"] = bool(kwargs["spin_icon"])
        if "rotation_angle" in kwargs:
            try:
                properties["rotation_angle"] = int(kwargs["rotation_angle"])
            except Exception:
                properties["rotation_angle"] = kwargs["rotation_angle"]
        if "zindex" in kwargs:
            try:
                properties["%z"] = int(kwargs["zindex"])
            except Exception:
                properties["%z"] = kwargs["zindex"]
        unique_id_value = kwargs.get(
            "html_id",
            kwargs.get("unique_id", kwargs.get("id_attribute", kwargs.get("id_attr"))),
        )
        if unique_id_value is not None:
            if isinstance(unique_id_value, dict) and unique_id_value.get("%x") == "TextExpression":
                properties["unique_id"] = unique_id_value
            else:
                properties["unique_id"] = {
                    "%x": "TextExpression",
                    "%e": {"0": str(unique_id_value)}
                }

        # Padding
        if kwargs.get("padding_top") is not None: properties["padding_top"] = kwargs["padding_top"]
        if kwargs.get("padding_bottom") is not None: properties["padding_bottom"] = kwargs["padding_bottom"]
        if kwargs.get("padding_left") is not None: properties["padding_left"] = kwargs["padding_left"]
        if kwargs.get("padding_right") is not None: properties["padding_right"] = kwargs["padding_right"]

        if kwargs.get("four_border_style") is not None: properties["four_border_style"] = kwargs["four_border_style"]
        if kwargs.get("all_4_borders") is True:
            properties["four_border_style"] = True
        if "border_type" in kwargs and kwargs.get("border_type") is not None:
            raw_border_type = str(kwargs.get("border_type")).strip().lower()
            if raw_border_type in {"independent", "all_4_borders", "all-4-borders"}:
                properties["four_border_style"] = True
            elif raw_border_type == "shared":
                properties["four_border_style"] = False

        # Border
        if kwargs.get("border_style") is not None: properties["%bos"] = kwargs["border_style"] # e.g. "solid"
        if kwargs.get("border_width") is not None: properties["%bw"] = kwargs["border_width"]
        if kwargs.get("border_color") is not None: properties["%bc"] = kwargs["border_color"]
        if kwargs.get("border_radius") is not None:
            radius = kwargs["border_radius"]
            properties["%br"] = radius
            # Keep shared + per-corner roundness in sync so editor mode
            # differences do not drop the intended radius.
            properties["border_roundness"] = radius
            properties["border_roundness_top"] = radius
            properties["border_roundness_right"] = radius
            properties["border_roundness_bottom"] = radius
            properties["border_roundness_left"] = radius
        if kwargs.get("border_style_top") is not None: properties["border_style_top"] = kwargs["border_style_top"]
        if kwargs.get("border_style_bottom") is not None: properties["border_style_bottom"] = kwargs["border_style_bottom"]
        if kwargs.get("border_style_left") is not None: properties["border_style_left"] = kwargs["border_style_left"]
        if kwargs.get("border_style_right") is not None: properties["border_style_right"] = kwargs["border_style_right"]
        if kwargs.get("border_width_top") is not None: properties["border_width_top"] = kwargs["border_width_top"]
        if kwargs.get("border_width_bottom") is not None: properties["border_width_bottom"] = kwargs["border_width_bottom"]
        if kwargs.get("border_width_left") is not None: properties["border_width_left"] = kwargs["border_width_left"]
        if kwargs.get("border_width_right") is not None: properties["border_width_right"] = kwargs["border_width_right"]
        if kwargs.get("border_color_top") is not None: properties["border_color_top"] = kwargs["border_color_top"]
        if kwargs.get("border_color_bottom") is not None: properties["border_color_bottom"] = kwargs["border_color_bottom"]
        if kwargs.get("border_color_left") is not None: properties["border_color_left"] = kwargs["border_color_left"]
        if kwargs.get("border_color_right") is not None: properties["border_color_right"] = kwargs["border_color_right"]
        if kwargs.get("border_roundness_top") is not None: properties["border_roundness_top"] = kwargs["border_roundness_top"]
        if kwargs.get("border_roundness_bottom") is not None: properties["border_roundness_bottom"] = kwargs["border_roundness_bottom"]
        if kwargs.get("border_roundness_left") is not None: properties["border_roundness_left"] = kwargs["border_roundness_left"]
        if kwargs.get("border_roundness_right") is not None: properties["border_roundness_right"] = kwargs["border_roundness_right"]
        if kwargs.get("border_roundness_top_left") is not None: properties["border_roundness_top_left"] = kwargs["border_roundness_top_left"]
        if kwargs.get("border_roundness_top_right") is not None: properties["border_roundness_top_right"] = kwargs["border_roundness_top_right"]
        if kwargs.get("border_roundness_bottom_left") is not None: properties["border_roundness_bottom_left"] = kwargs["border_roundness_bottom_left"]
        if kwargs.get("border_roundness_bottom_right") is not None: properties["border_roundness_bottom_right"] = kwargs["border_roundness_bottom_right"]

        # Shadow
        if kwargs.get("shadow_style") is not None: properties["%bs"] = kwargs["shadow_style"] # "outset", "inset", "none"
        if kwargs.get("shadow_h") is not None: properties["%bh"] = kwargs["shadow_h"]
        if kwargs.get("shadow_v") is not None: properties["%bv"] = kwargs["shadow_v"]
        if kwargs.get("shadow_blur") is not None: properties["%bsb"] = kwargs["shadow_blur"]
        if kwargs.get("shadow_spread") is not None:
            properties["%bsp"] = kwargs["shadow_spread"]
        if kwargs.get("shadow_color") is not None: properties["%bsc"] = kwargs["shadow_color"]

        # Background (Generic override)
        if kwargs.get("bg_color") is not None:
            properties["%bgc"] = kwargs["bg_color"]
            if kwargs.get("background_style") is None:
                properties["%bas"] = "bgcolor" # Flat color style
        if kwargs.get("background_style") is not None:
            properties["%bas"] = kwargs["background_style"]
        elif kwargs.get("bg_style") is not None:
            properties["%bas"] = kwargs["bg_style"]
        gradient_start = kwargs.get("gradient_start_color", kwargs.get("gradient_color1"))
        gradient_end = kwargs.get("gradient_end_color", kwargs.get("gradient_color2"))
        gradient_mid = kwargs.get("gradient_mid_color", kwargs.get("gradient_mid"))
        gradient_style = kwargs.get("gradient_style")
        gradient_direction = kwargs.get("gradient_direction")
        gradient_angle = kwargs.get("gradient_angle")
        gradient_shape = kwargs.get("gradient_shape")
        gradient_size = kwargs.get("gradient_size")
        gradient_xpos = kwargs.get("gradient_xpos")
        gradient_ypos = kwargs.get("gradient_ypos")
        if gradient_start is not None:
            properties["%bgf"] = gradient_start
        if gradient_end is not None:
            properties["%bgt"] = gradient_end
        if gradient_mid is not None:
            properties["background_gradient_mid"] = gradient_mid
        normalized_gradient_style = None
        linear_direction = None
        if gradient_style is not None:
            style_token = str(gradient_style).strip().lower().replace("-", "_").replace(" ", "_")
            if style_token in {"linear", "radial"}:
                normalized_gradient_style = style_token
        if gradient_direction is not None:
            direction_token = str(gradient_direction).strip().lower().replace("-", "_").replace(" ", "_")
            if direction_token in {"linear", "radial"}:
                if normalized_gradient_style is None:
                    normalized_gradient_style = direction_token
            elif direction_token in {"top", "right", "bottom", "left", "custom"}:
                if normalized_gradient_style is None:
                    normalized_gradient_style = "linear"
                linear_direction = direction_token
        if gradient_angle is not None and normalized_gradient_style != "radial":
            normalized_gradient_style = "linear"
            linear_direction = "custom"
            properties["%bga"] = gradient_angle
            properties["background_gradient_custom_angle"] = gradient_angle
        if normalized_gradient_style is not None:
            properties["%bgd"] = normalized_gradient_style
            properties["background_gradient_style"] = normalized_gradient_style
        if normalized_gradient_style == "linear" and linear_direction is not None:
            properties["%b4"] = linear_direction
        if normalized_gradient_style == "radial":
            if gradient_shape is not None:
                properties["background_radial_gradient_shape"] = gradient_shape
            if gradient_size is not None:
                properties["background_radial_gradient_size"] = gradient_size
            if gradient_xpos is not None:
                properties["background_radial_gradient_xpos"] = gradient_xpos
            if gradient_ypos is not None:
                properties["background_radial_gradient_ypos"] = gradient_ypos
        if (
            ("background_style" not in kwargs and "bg_style" not in kwargs)
            and any(
                v is not None
                for v in (
                    gradient_start,
                    gradient_end,
                    gradient_mid,
                    gradient_style,
                    gradient_direction,
                    gradient_shape,
                    gradient_size,
                    gradient_xpos,
                    gradient_ypos,
                    gradient_angle,
                )
            )
        ):
            properties["%bas"] = "gradient"
        if "background_image" in kwargs:
            properties["%bgi"] = kwargs["background_image"]
        elif "bg_image" in kwargs:
            bg_image_value = kwargs["bg_image"]
            if isinstance(bg_image_value, dict):
                properties["%bgi"] = bg_image_value
            else:
                properties["%bgi"] = {"%x": "TextExpression", "%e": {"0": str(bg_image_value)}}

        # Advanced background properties
        if "background_color_if_empty_image" in kwargs:
            properties["background_color_if_empty_image"] = kwargs["background_color_if_empty_image"]
        if "crop_responsive" in kwargs:
            properties["crop_responsive"] = bool(kwargs["crop_responsive"])
        if "background_size_cover" in kwargs:
            properties["background_size_cover"] = bool(kwargs["background_size_cover"])
        # Image background options: center (%cb), repeat vertical (%rbv), repeat horizontal (%rbh)
        if "center_background" in kwargs:
            properties["%cb"] = bool(kwargs["center_background"])
        elif "%cb" in kwargs:
            properties["%cb"] = bool(kwargs["%cb"])
        if "repeat_background_vertical" in kwargs:
            properties["%rbv"] = bool(kwargs["repeat_background_vertical"])
        elif "%rbv" in kwargs:
            properties["%rbv"] = bool(kwargs["%rbv"])
        if "repeat_background_horizontal" in kwargs:
            properties["%rbh"] = bool(kwargs["repeat_background_horizontal"])
        elif "%rbh" in kwargs:
            properties["%rbh"] = bool(kwargs["%rbh"])

        # Font Color
        if "text_color" in kwargs:
             properties["%fc"] = kwargs["text_color"]
        if "font_color" in kwargs:
             properties["%fc"] = kwargs["font_color"]
             properties["font_color"] = kwargs["font_color"]
        if "placeholder_color" in kwargs:
             properties["placeholder_color"] = kwargs["placeholder_color"]
        if "font_family" in kwargs:
             properties["font_family"] = kwargs["font_family"]
        if "font_weight" in kwargs:
             properties["font_weight"] = str(kwargs["font_weight"])
        if "font_size" in kwargs:
             properties["%fs"] = kwargs["font_size"]
             properties["font_size"] = kwargs["font_size"]
        if "font_face" in kwargs:
             properties["font_face"] = kwargs["font_face"]
        if "font_alignment" in kwargs:
             properties["%fa"] = kwargs["font_alignment"]
             properties["font_alignment"] = kwargs["font_alignment"]
        if "letter_spacing" in kwargs:
             properties["%ls"] = kwargs["letter_spacing"]
             properties["letter_spacing"] = kwargs["letter_spacing"]
        if "line_height" in kwargs:
             properties["%lh"] = kwargs["line_height"]
             properties["line_height"] = kwargs["line_height"]
        if "word_spacing" in kwargs:
             properties["%ws"] = kwargs["word_spacing"]
        if "bold" in kwargs:
             properties["%b"] = bool(kwargs["bold"])
             properties["bold"] = bool(kwargs["bold"])
        if "italic" in kwargs:
             properties["%i"] = bool(kwargs["italic"])
             properties["italic"] = bool(kwargs["italic"])
        if "underline" in kwargs:
             properties["%u"] = bool(kwargs["underline"])
             properties["underline"] = bool(kwargs["underline"])
        if "vertical_centering" in kwargs:
             properties["%vc"] = bool(kwargs["vertical_centering"])

        # Text-specific behavior and link controls
        if "no_bbcode" in kwargs:
            properties["no_bbcode"] = bool(kwargs["no_bbcode"])
        if "recognize_links" in kwargs:
            properties["recognize_links"] = bool(kwargs["recognize_links"])
        if "link_color" in kwargs:
            properties["link_color"] = kwargs["link_color"]
        if "nofollow" in kwargs:
            properties["nofollow"] = bool(kwargs["nofollow"])

        # Text shadow controls
        if "text_shadow" in kwargs:
            properties["%tes"] = bool(kwargs["text_shadow"])
        if "text_shadow_h" in kwargs:
            properties["%tsh"] = kwargs["text_shadow_h"]
        if "text_shadow_v" in kwargs:
            properties["%tsv"] = kwargs["text_shadow_v"]
        if "text_shadow_blur" in kwargs:
            properties["%tsb"] = kwargs["text_shadow_blur"]
        if "text_shadow_color" in kwargs:
            properties["%tsc"] = kwargs["text_shadow_color"]

        # Button/Icon specific controls
        if "icon_color" in kwargs:
            properties["%ic"] = kwargs["icon_color"]
            properties["icon_color"] = kwargs["icon_color"]
        if "icon_size" in kwargs:
            properties["icon_size"] = kwargs["icon_size"]
        if "icon_placement" in kwargs:
            properties["icon_placement"] = kwargs["icon_placement"]
        if "button_gap" in kwargs:
            properties["button_gap"] = kwargs["button_gap"]
        if "gap" in kwargs and "button_gap" not in kwargs:
            properties["button_gap"] = kwargs["gap"]

        # HTML rendering controls
        if "display_as_iframe" in kwargs:
            properties["%u2"] = bool(kwargs["display_as_iframe"])
        wait_until_visible = kwargs.get("wait_until_visible")
        if wait_until_visible is None and "defer_drawing" in kwargs:
            wait_until_visible = kwargs.get("defer_drawing")
        if wait_until_visible is not None:
            properties["defer_drawing"] = bool(wait_until_visible)

        # Sizing / fit behavior
        if "min_width_css" in kwargs: properties["min_width_css"] = kwargs["min_width_css"]
        if "max_width_css" in kwargs: properties["max_width_css"] = kwargs["max_width_css"]
        if "min_height_css" in kwargs: properties["min_height_css"] = kwargs["min_height_css"]
        if "max_height_css" in kwargs: properties["max_height_css"] = kwargs["max_height_css"]
        if "single_width" in kwargs: properties["single_width"] = kwargs["single_width"]
        if "opacity" in kwargs: properties["opacity"] = kwargs["opacity"]
        if "single_height" in kwargs: properties["single_height"] = kwargs["single_height"]
        if "fit_width" in kwargs: properties["fit_width"] = kwargs["fit_width"]
        if "fit_height" in kwargs: properties["fit_height"] = kwargs["fit_height"]
        if "overflow_scroll" in kwargs: properties["overflow_scroll"] = kwargs["overflow_scroll"]

        # Layout Alignments (Standardized)
        if "horiz_alignment" in kwargs: properties["horiz_alignment"] = kwargs["horiz_alignment"]
        if "vert_alignment" in kwargs: properties["vert_alignment"] = kwargs["vert_alignment"]
        if "nonant_alignment" in kwargs:
            properties["nonant_alignment"] = kwargs["nonant_alignment"]
            properties["align_to_parent_pos"] = kwargs["nonant_alignment"]
        if "container_horiz_alignment" in kwargs: properties["container_horiz_alignment"] = kwargs["container_horiz_alignment"]
        if "container_vert_alignment" in kwargs: properties["container_vert_alignment"] = kwargs["container_vert_alignment"]

        # Element Order (Z-index / Visual sequence)
        if "order" in kwargs:
             properties["order"] = int(kwargs["order"])

    def _resolve_style_ref(
        self,
        kwargs: Optional[Dict[str, Any]] = None,
        *,
        explicit_style: Any = None,
    ) -> Optional[str]:
        """Resolve style reference from canonical/legacy style keys."""
        def _normalize_candidate(candidate: Any) -> Optional[str]:
            if candidate is None:
                return None
            value = candidate.strip() if isinstance(candidate, str) else str(candidate).strip()
            if not value:
                return None
            lowered = value.lower()
            if lowered in {
                "none",
                "null",
                "undefined",
                "custom",
                "none (custom)",
                "none(custom)",
                "no style",
            }:
                return None
            return value

        candidates = [explicit_style]
        if isinstance(kwargs, dict):
            candidates.extend([
                kwargs.get("style"),
                kwargs.get("style_id"),
                kwargs.get("%s1"),
            ])
        for candidate in candidates:
            normalized = _normalize_candidate(candidate)
            if normalized:
                return normalized
        return None

    def _has_non_default_text_visual_overrides(
        self,
        properties: Dict[str, Any],
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Detect whether a Text carries explicit HTML-driven visual overrides."""
        props = properties or {}
        args = kwargs or {}

        if props.get("%fc") not in (None, "", "#000000", "rgb(0, 0, 0)", "rgb(0,0,0)"):
            return True
        if props.get("%fs") not in (None, 16, "16"):
            return True
        if str(props.get("font_weight")) not in ("", "None", "400"):
            return True
        if props.get("%fa") not in (None, "", "left"):
            return True
        if props.get("horiz_alignment") not in (None, "", "flex-start"):
            return True

        for key in (
            "font_family",
            "font_face",
            "%lh",
            "line_height",
            "%ls",
            "letter_spacing",
            "%ws",
            "%tes",
            "%tsh",
            "%tsv",
            "%tsb",
            "%tsc",
            "link_color",
            "placeholder_color",
            "bold",
            "italic",
            "underline",
            "%b",
            "%i",
            "%u",
            "%vc",
            "%bgc",
            "%bas",
            "%bgi",
            "%bos",
            "%bw",
            "%bc",
            "%br",
            "%bs",
            "%bh",
            "%bv",
            "%bsb",
            "%bsp",
            "%bsc",
        ):
            if props.get(key) not in (None, "", False):
                return True

        for key in (
            "font_color",
            "text_color",
            "font_family",
            "font_face",
            "font_weight",
            "line_height",
            "letter_spacing",
            "word_spacing",
            "text_shadow",
            "text_shadow_h",
            "text_shadow_v",
            "text_shadow_blur",
            "text_shadow_color",
            "bg_color",
            "background_style",
            "bg_image",
            "gradient_color1",
            "gradient_color2",
            "gradient_mid",
            "gradient_style",
            "gradient_direction",
            "gradient_angle",
            "gradient_shape",
            "gradient_size",
            "gradient_xpos",
            "gradient_ypos",
            "border_style",
            "border_width",
            "border_color",
            "border_radius",
            "shadow_style",
            "shadow_h",
            "shadow_v",
            "shadow_blur",
            "shadow_spread",
            "shadow_color",
        ):
            if args.get(key) is not None:
                return True

        return False

    def _has_button_visual_overrides(
        self,
        properties: Dict[str, Any],
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Detect whether a Button carries explicit visual overrides that should win over default styles."""
        props = properties or {}
        args = kwargs or {}

        for key in (
            "%fc",
            "font_color",
            "%ic",
            "icon_color",
            "%bgc",
            "%bas",
            "%bgi",
            "%bos",
            "%bw",
            "%bc",
            "%br",
            "%bs",
            "%bh",
            "%bv",
            "%bsb",
            "%bsp",
            "%bsc",
            "%fa",
            "font_alignment",
            "%fs",
            "font_size",
            "font_family",
            "font_face",
            "font_weight",
            "%lh",
            "line_height",
            "%ls",
            "letter_spacing",
            "icon_placement",
            "button_gap",
            "padding_top",
            "padding_right",
            "padding_bottom",
            "padding_left",
        ):
            if props.get(key) not in (None, "", False):
                return True

        for key in (
            "font_color",
            "text_color",
            "icon_color",
            "bg_color",
            "background_style",
            "bg_style",
            "bg_image",
            "gradient_color1",
            "gradient_color2",
            "gradient_mid",
            "gradient_style",
            "gradient_direction",
            "gradient_angle",
            "gradient_shape",
            "gradient_size",
            "gradient_xpos",
            "gradient_ypos",
            "border_style",
            "border_width",
            "border_color",
            "border_radius",
            "shadow_style",
            "shadow_h",
            "shadow_v",
            "shadow_blur",
            "shadow_spread",
            "shadow_color",
            "font_alignment",
            "font_size",
            "font_family",
            "font_face",
            "font_weight",
            "line_height",
            "letter_spacing",
            "icon_placement",
            "button_gap",
            "gap",
            "padding_top",
            "padding_right",
            "padding_bottom",
            "padding_left",
        ):
            if args.get(key) is not None:
                return True

        return False

    def _resolve_default_text_style_ref(
        self,
        properties: Dict[str, Any],
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            return style_ref
        if self._has_non_default_text_visual_overrides(properties, kwargs):
            return None
        return "Text_body_small_"

    def _resolve_default_button_style_ref(
        self,
        properties: Dict[str, Any],
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            return style_ref
        if self._has_button_visual_overrides(properties, kwargs):
            return None
        return "Button_primary_button_"

    def _prune_typography_overrides_for_style(
        self,
        properties: Dict[str, Any],
        kwargs: Dict[str, Any],
        *,
        style_applied: bool,
    ) -> None:
        """
        When a style is explicitly provided, avoid sending typography override keys
        unless caller explicitly requested typography controls.
        """
        # Treat explicit style references as style-applied, even if callers used
        # legacy kwargs (style_id/%s1) instead of style.
        if not (bool(style_applied) or bool(self._resolve_style_ref(kwargs))):
            return
        if bool((kwargs or {}).get("keep_overrides")):
            return

        explicit_typography_keys = {
            "font_size",
            "font_family",
            "font_weight",
            "font_alignment",
            "font_color",
            "text_color",
            "line_height",
            "letter_spacing",
            "word_spacing",
            "bold",
            "italic",
            "underline",
            "vertical_centering",
            "text_shadow",
            "text_shadow_h",
            "text_shadow_v",
            "text_shadow_blur",
            "text_shadow_color",
        }
        if any(key in (kwargs or {}) for key in explicit_typography_keys):
            return

        override_keys = (
            "%fs",
            "font_size",
            "font_family",
            "font_weight",
            "%fa",
            "font_alignment",
            "%fc",
            "font_color",
            "%lh",
            "line_height",
            "%ls",
            "letter_spacing",
            "%ws",
            "%b",
            "bold",
            "%i",
            "italic",
            "%u",
            "underline",
            "%vc",
            "%tes",
            "%tsh",
            "%tsv",
            "%tsb",
            "%tsc",
        )
        for key in override_keys:
            properties.pop(key, None)

    def group(
        self,
        name: str,
        layout: str = "column",
        width: Optional[int] = None,
        height: Optional[int] = None,
        row_gap: Optional[int] = None,
        column_gap: Optional[int] = None,
        data_class: str = None,
        data_source: str = None,
        width_unset: bool = False,
        style: str = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Group"""
        element_id = self.id_gen.element_id()
        normalized_layout = self._normalize_container_layout(layout)
        wire_layout = "relative" if normalized_layout == "align_to_parent" else normalized_layout

        properties = {
            "container_layout": wire_layout,
            **kwargs.get("extra_props", {})
        }
        if wire_layout in {"fixed", "relative"}:
            properties["%t"] = kwargs.get("top", 0)
            properties["%l"] = kwargs.get("left", 0)
        if width is not None:
            properties["%w"] = width
        if height is not None:
            properties["%h"] = height

        # Apply new dimension logic
        # Prepare kwargs for _apply_dimensions including explicit args
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        # Merge into kwargs for _add_visual_props consumption if needed, or just pass separately
        # Actually _add_visual_props doesn't handle these new names well yet, so we use _apply_dimensions
        self._apply_dimensions(properties, dim_args)

        if kwargs.get("background_style") is not None:
             properties["%bas"] = kwargs["background_style"]
        elif not style:
             properties["%bas"] = "none"

        resolved_row_gap = int(row_gap) if row_gap is not None else None
        resolved_column_gap = int(column_gap) if column_gap is not None else None

        if resolved_row_gap is not None or resolved_column_gap is not None or kwargs.get("use_gap"):
            properties["use_gap"] = True
            if resolved_row_gap is not None:
                properties["row_gap"] = resolved_row_gap
            if resolved_column_gap is not None:
                properties["column_gap"] = resolved_column_gap

        if kwargs.get("collapse_animation") is not None:
            properties["collapse_animation"] = bool(kwargs.get("collapse_animation"))
        if kwargs.get("animation_type") is not None:
            properties["animation_type"] = str(kwargs.get("animation_type")).strip().lower()

        if data_class:
            properties["%gt"] = data_class

        if data_source == "current_cell":
             # Special payload for "Current Cell's Content"
             # It refers to the parent element (the Repeating Group cell)
             properties["%ds"] = {
                 "%x": "ElementParent",
                 "%p": None,
                 "%n": None,
                 "is_slidable": False
             }
        elif isinstance(data_source, dict):
             properties["%ds"] = data_source

        if kwargs.get("container_horiz_alignment"):
            properties["container_horiz_alignment"] = kwargs.get("container_horiz_alignment")
        if kwargs.get("container_vert_alignment"):
            properties["container_vert_alignment"] = kwargs.get("container_vert_alignment")
        if kwargs.get("horiz_alignment"):
            properties["horiz_alignment"] = kwargs.get("horiz_alignment")
        if kwargs.get("vert_alignment"):
            properties["vert_alignment"] = kwargs.get("vert_alignment")
        if kwargs.get("nonant_alignment"):
            properties["nonant_alignment"] = kwargs.get("nonant_alignment")
            properties["align_to_parent_pos"] = kwargs.get("nonant_alignment")
        # Bubble fixed-size toggles for container elements.
        if fixed_width:
            properties["single_width"] = True
            properties["fit_width"] = False
            if min_width is None:
                fixed_src = width if width is not None else max_width
                normalized = self._normalize_css_length(fixed_src)
                if normalized is not None:
                    properties["min_width_css"] = normalized
        elif fit_width:
            properties.pop("single_width", None)

        if fixed_height:
            properties["single_height"] = True
            properties["fit_height"] = False
            if min_height is None:
                fixed_src = height if height is not None else max_height
                normalized = self._normalize_css_length(fixed_src)
                if normalized is not None:
                    properties["min_height_css"] = normalized
        elif fit_height:
            properties.pop("single_height", None)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        body = {
            "id": element_id,
            "type": "Group",
            "%x": "Group",
            "%dn": name,
            "%p": properties,
            "%el": {}
        }
        if style:
            body["%s1"] = style
        return body

    def popup(
        self,
        name: str,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Popup"""
        # Popup is just a Group with type Popup?
        # Actually it uses %x: "Popup"
        element_id = self.id_gen.element_id()
        normalized_layout = self._normalize_container_layout(kwargs.get("layout", "column"))
        row_gap_value = kwargs.get("row_gap", 16)
        column_gap_value = kwargs.get("column_gap")
        use_gap_value = kwargs.get("use_gap", True)
        has_style = bool(self._resolve_style_ref(kwargs))

        properties = {
            # Layout
            "container_layout": normalized_layout,
            "%w": kwargs.get("width", 400),
            "%h": kwargs.get("height", 300),

            # IMPORTANTE: Min height para evitar popup vazio
            "min_width_css": kwargs.get("min_width", "400px"),
            "min_height_css": kwargs.get("min_height", "300px"),

            # Visibilidade
            "%vc": kwargs.get("visible", False),
            "%iv": kwargs.get("visible", False),
            "collapse_when_hidden": kwargs.get("collapse_when_hidden", True),

            # Layout interno
            "fit_height": fit_height,
            "use_gap": bool(use_gap_value),
            "row_gap": int(row_gap_value) if row_gap_value is not None else 16,
            "horiz_alignment": kwargs.get("horiz_alignment", "center"),
            "vert_alignment": kwargs.get("vert_alignment", "flex-start"),
            **kwargs.get("extra_props", {})
        }

        # Formatting properties: only set defaults when no style is applied.
        # When a style is set, only include these if the caller explicitly passed them.
        if kwargs.get("bg_color") is not None:
            properties["%bgc"] = kwargs["bg_color"]
        elif not has_style:
            properties["%bgc"] = "#FFFFFF"

        if kwargs.get("background_style") is not None:
            properties["%bas"] = kwargs["background_style"]
        elif not has_style:
            properties["%bas"] = "bgcolor"

        if kwargs.get("border_radius") is not None:
            properties["%br"] = kwargs["border_radius"]
        elif not has_style:
            properties["%br"] = 12

        # Shadow: default to "none" unless the caller explicitly requested shadow props.
        # Without this Bubble applies its own default outset shadow to every popup.
        _shadow_args = ("shadow_style", "shadow_h", "shadow_v", "shadow_blur", "shadow_spread", "shadow_color",
                        "%bs", "%bh", "%bv", "%bsb", "%bsp", "%bsc")
        if not any(kwargs.get(k) is not None for k in _shadow_args):
            properties["%bs"] = "none"

        if kwargs.get("padding_top") is not None:
            properties["padding_top"] = kwargs["padding_top"]
        elif not has_style:
            properties["padding_top"] = 32

        if kwargs.get("padding_bottom") is not None:
            properties["padding_bottom"] = kwargs["padding_bottom"]
        elif not has_style:
            properties["padding_bottom"] = 32

        if kwargs.get("padding_left") is not None:
            properties["padding_left"] = kwargs["padding_left"]
        elif not has_style:
            properties["padding_left"] = 32

        if kwargs.get("padding_right") is not None:
            properties["padding_right"] = kwargs["padding_right"]
        elif not has_style:
            properties["padding_right"] = 32
        prevent_close_esc = kwargs.get("prevent_user_from_closing_through_esc")
        if prevent_close_esc is None and kwargs.get("close_by_esc") is not None:
            prevent_close_esc = not bool(kwargs.get("close_by_esc"))
        if prevent_close_esc is not None:
            properties["prevent_user_from_closing_through_esc"] = bool(prevent_close_esc)

        greyout_color = kwargs.get("greyout_color")
        if greyout_color is None:
            greyout_color = kwargs.get("grayout_color")
        if greyout_color is not None:
            properties["greyout_color"] = greyout_color

        greyout_blur = kwargs.get("greyout_blur")
        if greyout_blur is None:
            greyout_blur = kwargs.get("grayout_blur")
        if greyout_blur is not None:
            try:
                properties["greyout_blur"] = int(greyout_blur)
            except Exception:
                properties["greyout_blur"] = greyout_blur

        if column_gap_value is not None:
            properties["column_gap"] = int(column_gap_value)
        if kwargs.get("nonant_alignment"):
            properties["nonant_alignment"] = kwargs.get("nonant_alignment")
            properties["align_to_parent_pos"] = kwargs.get("nonant_alignment")
        if kwargs.get("container_horiz_alignment"):
            properties["container_horiz_alignment"] = kwargs.get("container_horiz_alignment")
        if kwargs.get("container_vert_alignment"):
            properties["container_vert_alignment"] = kwargs.get("container_vert_alignment")
        if kwargs.get("data_class"):
            properties["%gt"] = kwargs.get("data_class")
        if kwargs.get("data_source") is not None:
            properties["%ds"] = kwargs.get("data_source")

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        body = {
            "id": element_id,
            "%x": "Popup",
            "%dn": name,
            "%p": properties,
            "%el": {}
        }
        style = self._resolve_style_ref(kwargs)
        if style:
            body["%s1"] = style
        return body

    def text(
        self,
        name: str,
        content: Union[str, Dict],
        font_size: int = 16,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Text"""
        element_id = self.id_gen.element_id()

        # Check if content is already a full TextExpression dict
        if isinstance(content, dict) and content.get("%x") == "TextExpression":
             text_prop = content
        elif isinstance(content, str) and content.startswith("current_cell_field:"):
             # Handle "current_cell_field:title"
             field_name = content.split(":")[1]
             # Construct Bubble Expression: ParentGroup -> Field
             text_prop = {
                 "%x": "TextExpression",
                 "%e": {
                     "0": "", # Pre-text
                     "1": {
                         "%x": "ElementParent",
                         "%p": None,
                         "%n": {
                             "%x": "Message",
                             "%nm": f"{field_name}_text", # Heuristic: field_text? Or just field?
                             # Actually for "Parent Group's Project's Title"
                             # It is ElementParent -> .title (Message?)
                             # Let's try mimicking the structure
                             # The user payload showed: ElementParent -> Message(title_text)
                             "%n": None,
                             "%a": None,
                             "is_slidable": False
                         },
                         "is_slidable": False
                     },
                     "2": "" # Post-text
                 }
             }
        else:
             text_prop = {
                "%x": "TextExpression",
                "%e": {"0": content}
             }

        properties = {
            "%3": text_prop,
            "%fs": font_size,
            "font_size": font_size,
            "color": kwargs.get("font_color") or kwargs.get("text_color") or kwargs.get("color", "#000000"),
            "font_weight": kwargs.get("font_weight", "400"),
            "horiz_alignment": kwargs.get("horiz_alignment", "flex-start"),
            "%fa": kwargs.get("font_alignment", kwargs.get("fa", "left")),
            "order": kwargs.get("order", 0), # Ensure order is present for auto-layout
            **kwargs.get("extra_props", {})
        }

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        body = {
            "id": element_id,
            "type": "Text",
            "%x": "Text",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_default_text_style_ref(properties, kwargs)
        if style_ref:
            body["%s1"] = style_ref
        return body

    # Valid button_type values - MANDATORY from docs/bubble-api-elements.md
    VALID_BUTTON_TYPES = ["label", "label_icon", "icon"]

    def button(
        self,
        name: str,
        label: str,
        button_type: str = "label",  # MANDATORY: "label", "label_icon", "icon"
        icon: str = None,            # Icon name, e.g., "feather star"
        width: int = 150,
        height: int = 44,
        width_unset: bool = False,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Cria um Button seguindo estrutura documentada em docs/bubble-api-elements.md (lines 98-112)

        CRITICAL: button_type must be "label", "label_icon", or "icon"
        Using incorrect values causes "MISSING TYPE INFO" errors!

        Args:
            name: Display name (%dn)
            label: Button text
            button_type: "label" (text only), "label_icon" (icon + text), "icon" (icon only)
            icon: Icon name for button_type "label_icon" or "icon", e.g., "feather star"
        """
        # VALIDATION: Ensure button_type is valid
        if button_type not in self.VALID_BUTTON_TYPES:
            raise ValueError(
                f"Invalid button_type: '{button_type}'. "
                f"Must be one of: {self.VALID_BUTTON_TYPES}"
            )

        # VALIDATION: Icon required for label_icon and icon types
        if button_type in ["label_icon", "icon"] and not icon:
            icon = "feather star"  # Default icon

        element_id = self.id_gen.element_id()

        # Properties following docs/bubble-api-elements.md lines 103-111
        properties = {
            # Position and Size (documented line 104)
            "%t": kwargs.get("top", 0),
            "%l": kwargs.get("left", 0),
            "%w": width,
            "%h": height,
            "%z": kwargs.get("zindex", 10),
            "order": kwargs.get("order", 100),

            # MANDATORY: button_type (documented line 106)
            "button_type": button_type,

            # Text content (documented lines 107-110)
            "%3": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },

            # Layout properties (from working captured payload)
            "single_width": False,
            "single_height": False,

            **kwargs.get("extra_props", {})
        }

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        # Add icon if specified (documented line 105)
        if icon:
            properties["%9i"] = icon

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        body = {
            "id": element_id,
            "%x": "Button",
            "%dn": name,
            "%p": properties
        }
        style_id = self._resolve_default_button_style_ref(properties, kwargs)
        if style_id:
            body["%s1"] = style_id
        return body


    def input(
        self,
        name: str,
        placeholder: str = "",
        initial_content: Any = "",
        content_format: str = "text",
        required: bool = False,
        disabled: bool = False,
        width: int = 250,
        height: int = 48,
        width_unset: bool = False,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Input"""
        element_id = self.id_gen.element_id()
        style_value = kwargs.get("style") or "Input_std_dash_"

        def _maybe_number(value: Any) -> Any:
            if isinstance(value, str):
                raw = value.strip()
                if raw.isdigit():
                    return int(raw)
            return value

        initial_content_expr = None
        if isinstance(initial_content, dict) and initial_content.get("%x") == "TextExpression":
            initial_content_expr = initial_content
        elif (
            isinstance(initial_content, dict)
            and initial_content.get("type") == "TextExpression"
            and isinstance(initial_content.get("entries"), dict)
        ):
            initial_content_expr = {
                "%x": "TextExpression",
                "%e": dict(initial_content.get("entries") or {}),
            }
        elif initial_content not in (None, ""):
            if isinstance(initial_content, dict):
                # Canonical Bubble dynamic text shape:
                # literal slot + dynamic slot + trailing literal slot.
                initial_content_expr = {
                    "%x": "TextExpression",
                    "%e": {
                        "0": "",
                        "1": initial_content,
                        "2": "",
                    },
                }
            else:
                initial_content_expr = {
                    "%x": "TextExpression",
                    "%e": {"0": initial_content}
                }

        placeholder_expr = {
            "%x": "TextExpression",
            "%e": {"0": str(placeholder or "")}
        }
        placeholder_expr_canonical = {
            "type": "TextExpression",
            "entries": {"0": str(placeholder or "")}
        }
        initial_content_canonical = initial_content_expr
        if isinstance(initial_content_expr, dict):
            if initial_content_expr.get("type") == "TextExpression" and isinstance(initial_content_expr.get("entries"), dict):
                initial_content_canonical = initial_content_expr
            elif initial_content_expr.get("%x") == "TextExpression" and isinstance(initial_content_expr.get("%e"), dict):
                initial_content_canonical = {
                    "type": "TextExpression",
                    "entries": dict(initial_content_expr.get("%e") or {}),
                }

        properties = {
            "%ps": placeholder_expr,
            "placeholder": placeholder_expr_canonical,
            "%cf": content_format,
            "content_format": content_format,
            "%c1": initial_content_expr,
            "initial_content": initial_content_canonical,
            "%1m": required,
            "mandatory": bool(required),
            "disabled": disabled,
            "%w": _maybe_number(width),
            "%h": _maybe_number(height),
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            "currency_symbol": kwargs.get("currency_symbol"),
            "not_submit_on_enter": kwargs.get("not_submit_on_enter"),
            "%0l": kwargs.get("limit_characters"),
            "character_limit": kwargs.get("character_limit"),
            **kwargs.get("extra_props", {})
        }

        if properties.get("character_limit") is not None:
            try:
                properties["character_limit"] = int(properties["character_limit"])
            except Exception:
                pass

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        # Clean up None values
        properties = {k: v for k, v in properties.items() if v is not None}

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        # Bubble editor fixed-height behavior for Input:
        # single_height=true + min_height_css=<value>.
        if fixed_height:
            properties["single_height"] = True
            if min_height is None and height is not None:
                normalized = self._normalize_css_length(height)
                if normalized:
                    properties["min_height_css"] = normalized

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        return {
            "id": element_id,
            "%x": "Input",
            "%dn": name,
            "%s1": style_value,
            "%p": properties
        }

    def checkbox(
        self,
        name: str,
        label: str = "Checkbox",
        checked: bool = False,
        required: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Checkbox"""
        element_id = self.id_gen.element_id()

        properties = {
            "%lab": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },
            "%ct": "checked" if checked else "unchecked",
            "%1m": required,
            "disabled": kwargs.get("disabled", False),
            "%9i": kwargs.get("icon", "feather square"),
            "min_height_css": "36px",
            "min_width_css": "150px",
            "fit_height": True,
            "fit_width": True,
            **kwargs.get("extra_props", {})
        }

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        return {
            "id": element_id,
            "%x": "Checkbox",
            "%dn": name,
            "%s1": kwargs.get("style", "Checkbox_standard"),
            "%p": properties
        }

    def radio_button(
        self,
        name: str,
        label: str = "Radio",
        group_name: str = "radio_group",
        selected: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Radio Button"""
        element_id = self.id_gen.element_id()

        properties = {
            "%lab": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },
            "radio_group": group_name,
            "%ct": "checked" if selected else "unchecked",
            "%9i": kwargs.get("icon", "feather circle"),
            "min_height_css": "36px",
            "min_width_css": "150px",
            "fit_height": True,
            "fit_width": True,
            **kwargs.get("extra_props", {})
        }

        self._add_visual_props(properties, kwargs)

        return {
            "id": element_id,
            "%x": "RadioButton",
            "%dn": name,
            "%s1": kwargs.get("style", "RadioButton_standard"),
            "%p": properties
        }

    def date_picker(
        self,
        name: str,
        placeholder: str = "Select date...",
        show_time: bool = False,
        required: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Date/Time Picker"""
        element_id = self.id_gen.element_id()

        properties = {
            "%w": kwargs.get("width", 250),
            "%h": kwargs.get("height", 48),
            "min_width_css": "250px",
            "min_height_css": "48px",
            "placeholder": {
                "%x": "TextExpression",
                "%e": {"0": placeholder}
            },
            "input_type": "date_time" if show_time else "date",
            "%1m": required,
            "fit_width": True,
            **kwargs.get("extra_props", {})
        }

        self._add_visual_props(properties, kwargs)

        return {
            "id": element_id,
            "%x": "DateInput",
            "%dn": name,
            "%s1": kwargs.get("style", "DateInput_standard"),
            "%p": properties
        }

    def file_uploader(
        self,
        name: str,
        label: str = "Upload file",
        accept_types: str = "*",
        max_file_size: int = 10,  # MB
        required: bool = False,
        disabled: bool = False,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um File Uploader"""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return None

        parsed_width = _parse_int_dimension(kwargs.get("width"))
        parsed_height = _parse_int_dimension(kwargs.get("height"))

        def _parse_jsonish(value: Any) -> Any:
            if value is None or isinstance(value, (dict, list, int, float, bool)):
                return value
            raw = str(value).strip()
            if not raw:
                return None
            if raw.startswith("{") or raw.startswith("["):
                try:
                    return json.loads(raw)
                except Exception:
                    return value
            return value

        dynamic_link_value = kwargs.get("dynamic_link", kwargs.get("src"))
        dynamic_link_value = _parse_jsonish(dynamic_link_value)
        if isinstance(dynamic_link_value, str):
            dynamic_link_value = {"%x": "TextExpression", "%e": {"0": dynamic_link_value}}

        attach_to_value = kwargs.get("attach_to")
        if isinstance(attach_to_value, dict):
            for wrapper_key in ("attach_to", "value", "expression", "data_source"):
                if set(attach_to_value.keys()) == {wrapper_key}:
                    attach_to_value = attach_to_value.get(wrapper_key)
                    break
        attach_to_value = _parse_jsonish(attach_to_value)
        if isinstance(attach_to_value, str):
            lower_attach = attach_to_value.strip().lower()
            if lower_attach in {"@current_user", "current_user", "@currentuser", "currentuser"}:
                attach_to_value = {"%x": "CurrentUser", "%p": None, "%n": None, "is_slidable": False}
            elif lower_attach in {"@current_page", "current_page", "@currentpage", "currentpage"}:
                attach_to_value = {"%x": "CurrentPageItem", "is_slidable": False}

        max_size_mb = kwargs.get("max_file_size_mb")
        if max_size_mb is None:
            max_size_mb = kwargs.get("max_size", kwargs.get("max_file_size", max_file_size))
        try:
            max_size_mb = int(max_size_mb)
        except Exception:
            max_size_mb = int(max_file_size)

        private_value = kwargs.get("private_file")
        if private_value is None:
            private_value = kwargs.get("private")

        properties = {
            "%w": parsed_width if parsed_width is not None else 250,
            "%h": parsed_height if parsed_height is not None else 48,
            "min_width_css": "250px",
            "min_height_css": "48px",
            "%ps": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },
            "accept": accept_types,
            "%1m": bool(required),
            "disabled": bool(disabled),
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            "src": dynamic_link_value,
            "private": bool(private_value) if private_value is not None else None,
            "attach_to": attach_to_value,
            "max_size": max_size_mb,
            "max_file_size": max_size_mb * 1024 * 1024,
            "fit_width": True if fit_width else False,
            **kwargs.get("extra_props", {})
        }
        properties = {k: v for k, v in properties.items() if v is not None}

        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        properties.pop("__explicit_dims", None)

        file_obj = {
            "id": element_id,
            "%x": "FileInput",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            file_obj["%s1"] = style_ref
        return file_obj

    def picture_uploader(
        self,
        name: str,
        label: str = "Upload picture",
        accept_types: str = "image/*",
        required: bool = False,
        disabled: bool = False,
        limit_image_width: Optional[bool] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Picture Uploader"""
        element_id = self.id_gen.element_id()
        style_ref = self._resolve_style_ref(kwargs)

        if not style_ref and kwargs.get("bold") is None:
            if any(
                kwargs.get(key) is not None
                for key in (
                    "font_weight",
                    "font_size",
                    "font_family",
                    "font_color",
                    "font_alignment",
                    "word_spacing",
                    "line_height",
                    "letter_spacing",
                )
            ):
                kwargs = dict(kwargs)
                kwargs["bold"] = False

        def _parse_int_dimension(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return None

        parsed_width = _parse_int_dimension(kwargs.get("width"))
        parsed_height = _parse_int_dimension(kwargs.get("height"))

        def _parse_jsonish(value: Any) -> Any:
            if value is None or isinstance(value, (dict, list, int, float, bool)):
                return value
            raw = str(value).strip()
            if not raw:
                return None
            if raw.startswith("{") or raw.startswith("["):
                try:
                    return json.loads(raw)
                except Exception:
                    return value
            return value

        dynamic_link_value = kwargs.get("dynamic_link", kwargs.get("src"))
        dynamic_link_value = _parse_jsonish(dynamic_link_value)
        if isinstance(dynamic_link_value, str):
            dynamic_link_value = {"%x": "TextExpression", "%e": {"0": dynamic_link_value}}

        attach_to_value = kwargs.get("attach_to")
        if isinstance(attach_to_value, dict):
            for wrapper_key in ("attach_to", "value", "expression", "data_source"):
                if set(attach_to_value.keys()) == {wrapper_key}:
                    attach_to_value = attach_to_value.get(wrapper_key)
                    break
        attach_to_value = _parse_jsonish(attach_to_value)
        if isinstance(attach_to_value, str):
            lower_attach = attach_to_value.strip().lower()
            if lower_attach in {"@current_user", "current_user", "@currentuser", "currentuser"}:
                attach_to_value = {"%x": "CurrentUser", "%p": None, "%n": None, "is_slidable": False}
            elif lower_attach in {"@current_page", "current_page", "@currentpage", "currentpage"}:
                attach_to_value = {"%x": "CurrentPageItem", "is_slidable": False}

        private_value = kwargs.get("private_file")
        if private_value is None:
            private_value = kwargs.get("private")
        if limit_image_width is None:
            limit_image_width = kwargs.get("limit_image_width")
        if limit_image_width is None:
            limit_image_width = kwargs.get("limit_image_size_before_upload")

        properties = {
            "%w": parsed_width if parsed_width is not None else 150,
            "%h": parsed_height if parsed_height is not None else 150,
            "min_width_css": "150px",
            "min_height_css": "150px",
            "%ps": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },
            "accept": accept_types,
            "%1m": bool(required),
            "disabled": bool(disabled),
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            "src": dynamic_link_value,
            "private": bool(private_value) if private_value is not None else None,
            "attach_to": attach_to_value,
            "limit_image_width": bool(limit_image_width) if limit_image_width is not None else None,
            "fit_width": True if fit_width else False,
            **kwargs.get("extra_props", {})
        }
        properties = {k: v for k, v in properties.items() if v is not None}

        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(style_ref),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        properties.pop("__explicit_dims", None)

        picture_obj = {
            "id": element_id,
            "%x": "PictureInput",
            "%dn": name,
            "%p": properties,
        }
        if style_ref:
            picture_obj["%s1"] = style_ref
        else:
            picture_obj["%s"] = {
                "0": {
                    "%x": "State",
                    "%c": {
                        "%x": "ThisElement",
                        "%n": {
                            "%x": "Message",
                            "%nm": "is_focused",
                        },
                    },
                    "%p": {
                        "%bc": "#52A8EC",
                        "%bsc": "#52A8EC",
                        "%bs": "outset",
                        "%bh": 0,
                        "%bv": 0,
                        "%bsb": 6,
                    },
                },
                "1": {
                    "%x": "State",
                    "%c": {
                        "%x": "ThisElement",
                        "%n": {
                            "%x": "Message",
                            "%nm": "isnt_valid",
                        },
                    },
                    "%p": {
                        "%bc": "#FF0000",
                        "%bsc": "#FF0000",
                        "%bs": "outset",
                        "%bh": 0,
                        "%bv": 0,
                        "%bsb": 6,
                    },
                },
            }
        return picture_obj


    def dropdown(
        self,
        name: str,
        placeholder: str = "Choose an option...",
        choice_style: str = "dynamic", # "static" or "dynamic" (Renamed from style to avoid conflict)
        choices: Union[str, Dict] = None, # String for static, Search Dict for dynamic
        choice_type: str = "text", # "text", "user", "custom.x", "option.y"
        required: bool = False,
        disabled: bool = False,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        style: str = None, # Visual style
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Dropdown"""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return None

        properties = {
            "%ps": {
                "%x": "TextExpression",
                "%e": {"0": str(placeholder or "")}
            },
            "choices_style": choice_style,
            "computed_value": choice_type,
            "%1m": bool(required),
            "disabled": bool(disabled),
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            "min_width_css": "200px",
            "min_height_css": "48px",
            **kwargs.get("extra_props", {})
        }
        parsed_width = _parse_int_dimension(width)
        parsed_height = _parse_int_dimension(height)
        if parsed_width is not None:
            properties["%w"] = parsed_width
        if parsed_height is not None:
            properties["%h"] = parsed_height

        # Apply dimensions (Dropdown does not support fit flags in the same way as Group/Text).
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height
        }
        self._apply_dimensions(properties, dim_args)
        # Dropdowns should not expose fit sizing flags.
        properties.pop("fit_width", None)
        properties.pop("fit_height", None)
        if fixed_width:
            properties["single_width"] = True
            if min_width is None and width is not None:
                normalized = self._normalize_css_length(width)
                if normalized is not None:
                    properties["min_width_css"] = normalized
        else:
            properties.pop("single_width", None)
        if fixed_height:
            properties["single_height"] = True
            if min_height is None and height is not None:
                normalized = self._normalize_css_length(height)
                if normalized is not None:
                    properties["min_height_css"] = normalized
        else:
            properties.pop("single_height", None)

        if choice_style == "static" and isinstance(choices, str):
             properties["%ch"] = choices
        elif choice_style == "dynamic":
             # Normalize OS:Name -> option.os_name
             if choice_type.startswith("OS:"):
                 parts = choice_type.split(":")
                 if len(parts) > 1:
                     # OS:role -> option.os_role
                     choice_type = f"option.os_{parts[1].lower()}"

             properties["dynamic_type"] = choice_type

             # Check if it's an Option Set (starts with "option.")
             if choice_type.startswith("option."):
                 # Use AllOptionValue for Option Sets
                 properties["%ds"] = {
                     "%x": "AllOptionValue",
                     "%p": {"option_set": choice_type}
                 }
             else:
                 # Default to Search for other types
                 if isinstance(choices, dict):
                     properties["%ds"] = choices
                 else:
                     search_p = {
                         "%t5": choice_type
                     }
                     sort_field = kwargs.get("sort_field")
                     sort_direction = kwargs.get("sort_direction")
                     if sort_field:
                         search_p["%sf"] = sort_field
                     if sort_direction:
                         search_p["%sd"] = sort_direction
                     properties["%ds"] = {
                         "%x": "Search",
                         "%p": search_p
                     }

             # Optional dynamic caption field (e.g. title_text).
             caption_field = str(kwargs.get("option_caption_field") or "").strip()
             if caption_field:
                 properties["option_display_expression"] = {
                     "%x": "TextExpression",
                     "%e": {
                         "0": "",
                         "1": {
                             "%x": "InjectedValue",
                             "%n": {
                                 "%x": "Message",
                                 "%nm": caption_field,
                                 "%n": None,
                                 "%a": None,
                                 "is_slidable": False
                             }
                         },
                         "2": ""
                     }
                 }

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs, explicit_style=style)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        visual_style = self._resolve_style_ref(kwargs, explicit_style=style) or "Dropdown_dash_std_"

        return {
            "id": element_id,
            "type": "Dropdown",
            "%x": "Dropdown",
            "%dn": name,
            "%s1": visual_style,
            "%p": properties
        }

    def checkbox(
        self,
        name: str,
        label: str = "Checkbox",
        checked: bool = False,
        required: bool = False,
        disabled: bool = False,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Checkbox"""
        element_id = self.id_gen.element_id()

        properties = {
            "%lab": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },
            "%ct": "checked" if checked else "unchecked",
            "%1m": required,
            "disabled": disabled,
            "%9i": kwargs.get("icon", "feather square"),
            "min_height_css": "36px",
            "min_width_css": "150px",
            **kwargs.get("extra_props", {})
        }

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        return {
            "id": element_id,
            "%x": "Checkbox",
            "%dn": name,
            "%s1": kwargs.get("style", "Checkbox_standard"),
            "%p": properties
        }

    def date_picker(
        self,
        name: str,
        placeholder: str = "Select date...",
        show_time: bool = False,
        required: bool = False,
        disabled: bool = False,
        initial_content: Any = None,
        input_type: Optional[str] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Date/Time Picker"""
        element_id = self.id_gen.element_id()

        properties = {
            "%w": kwargs.get("width", 250),
            "%h": kwargs.get("height", 48),
            "min_width_css": "250px",
            "min_height_css": "48px",
            "placeholder": {
                "%x": "TextExpression",
                "%e": {"0": placeholder}
            },
            "input_type": str(input_type or ("date_time" if show_time else "date")),
            "%1m": bool(required),
            "disabled": bool(disabled),
            "%c1": initial_content,
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            "binding_content_format": kwargs.get("binding_content_format", kwargs.get("content_format")),
            "date_format": kwargs.get("date_format"),
            "custom_format": kwargs.get("custom_format"),
            "start_monday": kwargs.get("start_monday", kwargs.get("start_week_monday")),
            "show_month_year_picker": kwargs.get("show_month_year_picker"),
            "time_format": kwargs.get("time_format"),
            "time_interval": kwargs.get("time_interval"),
            "min_date": kwargs.get("min_date", kwargs.get("minimum_date")),
            "max_date": kwargs.get("max_date", kwargs.get("maximum_date")),
            "min_hour": kwargs.get("min_hour", kwargs.get("minimum_hour")),
            "max_hour": kwargs.get("max_hour", kwargs.get("maximum_hour")),
            **kwargs.get("extra_props", {})
        }

        properties = {k: v for k, v in properties.items() if v is not None}

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        return {
            "id": element_id,
            "%x": "DateInput",
            "%dn": name,
            "%s1": kwargs.get("style", "DateInput_standard"),
            "%p": properties
        }

    def radio_button(
        self,
        name: str,
        label: str = "Radio",
        group_name: str = "radio_group",
        selected: bool = False,
        choices: Optional[Union[str, Dict[str, Any]]] = None,
        choice_style: str = "static",
        choice_type: str = "text",
        required: bool = False,
        disabled: bool = False,
        option_caption_field: Optional[str] = None,
        default_value: Any = None,
        columns: Optional[int] = None,
        use_dynamic_columns: bool = False,
        min_column_width_px: Optional[int] = None,
        color: Optional[str] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um RadioButtons (native Bubble radio group)."""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return None

        parsed_width = _parse_int_dimension(kwargs.get("width"))
        parsed_height = _parse_int_dimension(kwargs.get("height"))

        properties = {
            "%w": parsed_width if parsed_width is not None else 200,
            "%h": parsed_height if parsed_height is not None else 75,
            "choices_style": str(choice_style or "static"),
            "computed_value": str(choice_type or "text"),
            "min_height_css": "75px",
            "min_width_css": "200px",
            "fit_height": True,
            "%1m": bool(required),
            "disabled": bool(disabled),
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            **kwargs.get("extra_props", {})
        }

        if selected:
            properties["selected"] = True
        if group_name:
            properties["radio_group"] = group_name
        if label:
            properties["%lab"] = {"%x": "TextExpression", "%e": {"0": label}}

        if str(choice_style or "static").lower() == "static":
            if isinstance(choices, str):
                properties["%ch"] = choices
        else:
            if str(choice_type).startswith("OS:"):
                parts = str(choice_type).split(":", 1)
                if len(parts) == 2:
                    choice_type = f"option.os_{parts[1].lower()}"
            properties["dynamic_type"] = str(choice_type or "text")

            if str(choice_type).startswith("option."):
                properties["%ds"] = {"%x": "AllOptionValue", "%p": {"option_set": choice_type}}
            elif isinstance(choices, dict):
                properties["%ds"] = choices
            else:
                properties["%ds"] = {"%x": "Search", "%p": {"%t5": str(choice_type or "text")}}

            caption_field = str(option_caption_field or "").strip()
            if caption_field:
                properties["option_display_expression"] = {
                    "%x": "TextExpression",
                    "%e": {
                        "0": "",
                        "1": {
                            "%x": "InjectedValue",
                            "%n": {
                                "%x": "Message",
                                "%nm": caption_field,
                                "%n": None,
                                "%a": None,
                                "is_slidable": False
                            }
                        },
                        "2": ""
                    }
                }

        if default_value is not None:
            properties["%d1"] = default_value
        if columns is not None:
            properties["%c5"] = int(columns)
        if use_dynamic_columns:
            properties["use_dynamic_columns"] = True
            if min_column_width_px is not None:
                properties["min_column_width_px"] = int(min_column_width_px)
        if color:
            properties["color"] = str(color).strip().lower()

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        radio_obj = {
            "id": element_id,
            "%x": "RadioButtons",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            radio_obj["%s1"] = style_ref
        return radio_obj

    def slider(
        self,
        name: str,
        min_value: float = 0,
        max_value: float = 100,
        initial_value: Optional[float] = None,
        range_initial_value: Any = None,
        step: float = 1,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        range_type: Optional[str] = None,
        orientation: Optional[str] = None,
        background_color: Optional[str] = None,
        handle_color: Optional[str] = None,
        range_area_color: Optional[str] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um SliderInput (native Bubble slider)."""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return None

        parsed_width = _parse_int_dimension(width)
        parsed_height = _parse_int_dimension(height)

        properties = {
            "%w": parsed_width if parsed_width is not None else 200,
            "%h": parsed_height if parsed_height is not None else 45,
            "min_value": min_value,
            "max_value": max_value,
            "step": step,
            "auto_binding": kwargs.get("auto_binding"),
            "bind_field": kwargs.get("bind_field"),
            "disabled": kwargs.get("disabled"),
            "min_height_css": f"{parsed_height}px" if parsed_height is not None else "45px",
            "min_width_css": f"{parsed_width}px" if parsed_width is not None else "200px",
            "fit_height": False,
            **kwargs.get("extra_props", {})
        }
        if initial_value is not None:
            properties["%v"] = initial_value
            properties["%c1"] = initial_value
        if range_initial_value is not None:
            properties["%c1"] = range_initial_value
            properties.pop("%v", None)
        if range_type is not None:
            properties["range_type"] = str(range_type).strip().lower()
        if orientation is not None:
            properties["orientation"] = str(orientation).strip().lower()
        if background_color is not None:
            properties["background_color"] = background_color
        if handle_color is not None:
            properties["handle_color"] = handle_color
        if range_area_color is not None:
            properties["range_area_color"] = range_area_color

        properties = {k: v for k, v in properties.items() if v is not None}

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        slider_obj = {
            "id": element_id,
            "%x": "SliderInput",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            slider_obj["%s1"] = style_ref
        return slider_obj

    def html(
        self,
        name: str,
        content: str = "<div>HTML Content</div>",
        width: int = 300,
        height: int = 200,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um HTML Element"""
        element_id = self.id_gen.element_id()

        properties = {
            "%ht": {
                "%x": "TextExpression",
                "%e": {"0": content}
            },
            "%w": kwargs.get("width", width),
            "%h": kwargs.get("height", height),
            "min_width_css": "50px",
            "min_height_css": "50px",
            **kwargs.get("extra_props", {})
        }

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        return {
            "id": element_id,
            "%x": "HTML",
            "%dn": name,
            "%s1": kwargs.get("style", "HTML_standard"),
            "%p": properties
        }

    def shape(
        self,
        name: str,
        width: int = 100,
        height: int = 100,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria uma Shape."""
        element_id = self.id_gen.element_id()

        properties = {
            "%w": width,
            "%h": height,
            "min_width_css": f"{width}px",
            "min_height_css": f"{height}px",
            **kwargs.get("extra_props", {})
        }

        bg_color = kwargs.get("bg_color")
        if bg_color is not None:
            properties["%bgc"] = bg_color
            if not kwargs.get("background_style"):
                properties["%bas"] = "bgcolor"
        if kwargs.get("background_style") is not None:
            properties["%bas"] = kwargs.get("background_style")
        if kwargs.get("border_radius") is not None:
            properties["%br"] = kwargs.get("border_radius")

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        body = {
            "id": element_id,
            "%x": "Shape",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref is not None:
            body["%s1"] = style_ref
        return body

    def video_player(
        self,
        name: str,
        video_url: Optional[str] = None,
        video_id: Optional[str] = None,
        video_origin: str = "youtube",
        vimeo_control_color: Optional[str] = None,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        autoplay: Optional[bool] = None,
        controls: Optional[bool] = None,
        loop: Optional[bool] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Video Player"""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any, fallback: int) -> int:
            if value is None:
                return fallback
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return fallback

        parsed_width = _parse_int_dimension(width, 560)
        parsed_height = _parse_int_dimension(height, 315)

        properties = {
            "%w": parsed_width,
            "%h": parsed_height,
            "min_width_css": f"{parsed_width}px",
            "min_height_css": f"{parsed_height}px",
            # Bubble expects provider under `video_source` (e.g. youtube, vimeo).
            "video_source": str(video_origin or "youtube").strip().lower(),
            **kwargs.get("extra_props", {})
        }
        # Backward-compat: keep legacy key for older payload consumers.
        properties["video_origin"] = properties.get("video_source")
        if autoplay is not None:
            properties["autoplay"] = bool(autoplay)
        if controls is not None:
            properties["controls"] = bool(controls)
        if loop is not None:
            properties["loop"] = bool(loop)
        if kwargs.get("use_aspect_ratio") is not None:
            properties["use_aspect_ratio"] = bool(kwargs.get("use_aspect_ratio"))
        if kwargs.get("aspect_ratio_width") is not None:
            properties["aspect_ratio_width"] = int(kwargs.get("aspect_ratio_width"))
        if kwargs.get("aspect_ratio_height") is not None:
            properties["aspect_ratio_height"] = int(kwargs.get("aspect_ratio_height"))

        # Set Video ID or Source
        if video_id:
            properties["video_id"] = {
                "%x": "TextExpression",
                "%e": {"0": video_id}
            }
        elif video_url:
            properties["video_source"] = {
                "%x": "TextExpression",
                "%e": {"0": video_url}
            }

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        if vimeo_control_color is not None:
            properties["control_color_vimeo"] = vimeo_control_color
        elif kwargs.get("vimeo_control_color") is not None:
            properties["control_color_vimeo"] = kwargs.get("vimeo_control_color")

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        video_obj = {
            "id": element_id,
            "%x": "Video",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            video_obj["%s1"] = style_ref
        return video_obj


    def checkbox(
        self,
        name: str,
        label: str = "Checkbox",
        preset_status: str = "unchecked", # "checked", "unchecked", "dynamic"
        dynamic_status_expression: Dict = None, # Bubble expression dict
        required: bool = False,
        disabled: bool = False,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Checkbox"""
        element_id = self.id_gen.element_id()

        properties = {
            "%lab": {
                "%x": "TextExpression",
                "%e": {"0": label}
            },
            "%ct": "dynamic_state" if preset_status == "dynamic" else preset_status,
            "%1m": required,
            "disabled": disabled,
            "%9i": "feather square", # Default icon style
            "min_height_css": "36px",
            "min_width_css": "150px",
            **kwargs.get("extra_props", {})
        }
        if width is not None:
            if isinstance(width, str) and width.strip().endswith("px") and width.strip()[:-2].isdigit():
                properties["%w"] = int(width.strip()[:-2])
            elif isinstance(width, str) and width.strip().isdigit():
                properties["%w"] = int(width.strip())
            else:
                properties["%w"] = width
        if height is not None:
            if isinstance(height, str) and height.strip().endswith("px") and height.strip()[:-2].isdigit():
                properties["%h"] = int(height.strip()[:-2])
            elif isinstance(height, str) and height.strip().isdigit():
                properties["%h"] = int(height.strip())
            else:
                properties["%h"] = height

        if preset_status == "dynamic" and dynamic_status_expression:
            properties["dynamic"] = dynamic_status_expression

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        return {
            "id": element_id,
            "%x": "Checkbox",
            "%dn": name,
            "%s1": kwargs.get("style", "Checkbox_standard"),
            "%p": properties
        }

    def image(
        self,
        name: str,
        source_url: str,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Image"""
        element_id = self.id_gen.element_id()
        kwargs = dict(kwargs)
        kwargs.pop("single_width", None)
        kwargs.pop("single_height", None)

        def _parse_int_dimension(value: Any, fallback: int) -> int:
            if value is None:
                return fallback
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return fallback

        parsed_width = _parse_int_dimension(width, 48)
        parsed_height = _parse_int_dimension(height, 48)
        use_aspect_ratio = kwargs.get("use_aspect_ratio")
        aspect_ratio_width = kwargs.get("aspect_ratio_width")
        aspect_ratio_height = kwargs.get("aspect_ratio_height")
        if use_aspect_ratio is None and (aspect_ratio_width is not None or aspect_ratio_height is not None):
            use_aspect_ratio = True
        normalized_min_width = self._normalize_css_length(min_width)
        normalized_min_height = self._normalize_css_length(min_height)

        properties = {
            "src": {
                "%x": "TextExpression",
                "%e": {"0": source_url}
            },
            **kwargs.get("extra_props", {})
        }
        if width is not None or normalized_min_width is None:
            properties["%w"] = parsed_width
        if not bool(use_aspect_ratio):
            properties["%h"] = parsed_height
        if kwargs.get("alt_tag") is not None:
            properties["alt_tag"] = kwargs.get("alt_tag")
        if kwargs.get("title_attribute") is not None:
            properties["title_attribute"] = kwargs.get("title_attribute")
        if kwargs.get("button_disabled") is not None:
            properties["button_disabled"] = bool(kwargs.get("button_disabled"))
        if kwargs.get("rotation_angle") is not None:
            properties["rotation_angle"] = int(kwargs.get("rotation_angle"))
        if use_aspect_ratio is not None:
            properties["use_aspect_ratio"] = bool(use_aspect_ratio)
            if bool(use_aspect_ratio):
                if aspect_ratio_width is not None:
                    properties["aspect_ratio_width"] = int(aspect_ratio_width)
                elif width is not None:
                    properties["aspect_ratio_width"] = parsed_width
                if aspect_ratio_height is not None:
                    properties["aspect_ratio_height"] = int(aspect_ratio_height)
                elif height is not None:
                    properties["aspect_ratio_height"] = parsed_height

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        image_obj = {
            "id": element_id,
            "%x": "Image",
            "%dn": name,
            "%p": properties
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            image_obj["%s1"] = style_ref
        return image_obj

    def icon(
        self,
        name: str,
        icon_name: str,
        width: int = 24,
        height: int = 24,
        color: str = "#000000",
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        width_unset: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Icon"""
        element_id = self.id_gen.element_id()
        style_ref = self._resolve_style_ref(kwargs)
        explicit_icon_size = kwargs.get("icon_size")
        if explicit_icon_size is None:
            try:
                explicit_icon_size = max(int(width or 0), int(height or 0))
            except Exception:
                explicit_icon_size = None

        properties = {
            "%w": width,
            "%h": height,
            "%9i": icon_name,
            "%ic": color,
            **kwargs.get("extra_props", {})
        }
        if explicit_icon_size:
            properties["icon_size"] = explicit_icon_size

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        icon_obj = {
            "id": element_id,
            "%x": "Icon",
            "%dn": name,
            "%p": properties
        }
        if style_ref:
            icon_obj["%s1"] = style_ref
        return icon_obj

    def link(
        self,
        name: str,
        label: Union[str, Dict[str, Any]],
        *,
        link_destination: Optional[str] = None,
        destination_page: Optional[str] = None,
        url: Optional[Union[str, Dict[str, Any]]] = None,
        data_to_send: Optional[Any] = None,
        open_in_new_tab: Optional[bool] = None,
        link_disabled: Optional[bool] = None,
        nofollow: Optional[bool] = None,
        keep_current_page_params: Optional[bool] = None,
        add_parameters: Optional[bool] = None,
        url_parameters: Optional[Dict[str, Any]] = None,
        show_icon: Optional[bool] = None,
        icon: Optional[str] = None,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        min_width: str = None,
        max_width: str = None,
        fixed_width: bool = False,
        fit_width: bool = False,
        min_height: str = None,
        max_height: str = None,
        fixed_height: bool = False,
        fit_height: bool = False,
        width_unset: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a Link element."""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any, fallback: int) -> int:
            if value is None:
                return fallback
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return fallback

        parsed_width = _parse_int_dimension(width, 150)
        parsed_height = _parse_int_dimension(height, 20)

        if isinstance(label, dict) and label.get("%x") == "TextExpression":
            label_expr = label
        else:
            label_expr = {"%x": "TextExpression", "%e": {"0": str(label or "")}}

        properties: Dict[str, Any] = {
            "%t": kwargs.get("top", 0),
            "%l": kwargs.get("left", 0),
            "%w": parsed_width,
            "%h": parsed_height,
            "%z": kwargs.get("zindex", 2),
            "order": kwargs.get("order", 1),
            "%3": label_expr,
            "horiz_alignment": kwargs.get("horiz_alignment", "flex-start"),
            "fit_width": True,
            "fit_height": True,
            "single_width": False,
            "single_height": False,
            "min_width_css": kwargs.get("min_width_css", "60px"),
            "min_height_css": kwargs.get("min_height_css", "20px"),
            "%vc": bool(kwargs.get("vertical_centering", True)),
            "no_html": True,
            **kwargs.get("extra_props", {}),
        }

        # Use link_disabled as the canonical clickable field for Link.
        if link_disabled is None and kwargs.get("button_disabled") is not None:
            link_disabled = bool(kwargs.get("button_disabled"))
        # Avoid emitting button_disabled on Link payloads.
        if "button_disabled" in kwargs:
            kwargs = dict(kwargs)
            kwargs.pop("button_disabled", None)

        if show_icon is not None:
            properties["show_icon"] = bool(show_icon)
        if icon is not None:
            properties["%9i"] = str(icon)
        if link_destination is not None:
            properties["%1l"] = str(link_destination)
        if destination_page is not None:
            properties["%pa"] = str(destination_page)
        if url is not None:
            if isinstance(url, dict):
                properties["url"] = url
            else:
                properties["url"] = {"%x": "TextExpression", "%e": {"0": str(url)}}
        if data_to_send is not None:
            properties["data_to_send"] = data_to_send
        if open_in_new_tab is not None:
            properties["%o9"] = bool(open_in_new_tab)
        if link_disabled is not None:
            properties["link_disabled"] = bool(link_disabled)
        if nofollow is not None:
            properties["nofollow"] = bool(nofollow)
        if keep_current_page_params is not None:
            properties["keep_current_page_params"] = bool(keep_current_page_params)
        if add_parameters is not None:
            properties["add_parameters"] = bool(add_parameters)
        if url_parameters is not None:
            properties["url_parameters"] = url_parameters

        dim_args = {
            "min_width": min_width,
            "max_width": max_width,
            "fixed_width": fixed_width,
            "fit_width": fit_width,
            "min_height": min_height,
            "max_height": max_height,
            "fixed_height": fixed_height,
            "fit_height": fit_height,
        }
        self._apply_dimensions(properties, dim_args)

        self._add_visual_props(properties, kwargs)

        if width_unset:
            properties = self._apply_width_unset(properties)

        properties.pop("__explicit_dims", None)

        link_obj: Dict[str, Any] = {
            "id": element_id,
            "%x": "Link",
            "%dn": name,
            "%p": properties,
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            link_obj["%s1"] = style_ref
        return link_obj

    def alert(
        self,
        name: str,
        content: Union[str, Dict[str, Any]],
        *,
        at_to_top: Optional[bool] = None,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        min_width: str = None,
        max_width: str = None,
        fixed_width: bool = False,
        fit_width: bool = False,
        min_height: str = None,
        max_height: str = None,
        fixed_height: bool = False,
        fit_height: bool = False,
        width_unset: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create an Alert element."""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any, fallback: int) -> int:
            if value is None:
                return fallback
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return fallback

        parsed_width = _parse_int_dimension(width, 280)
        parsed_height = _parse_int_dimension(height, 48)

        if isinstance(content, dict) and content.get("%x") == "TextExpression":
            content_expr = content
        else:
            content_expr = {"%x": "TextExpression", "%e": {"0": str(content or "")}}

        properties: Dict[str, Any] = {
            "%t": kwargs.get("top", 0),
            "%l": kwargs.get("left", 0),
            "%w": parsed_width,
            "%h": parsed_height,
            "%z": kwargs.get("zindex", 2),
            "order": kwargs.get("order", 1),
            "%3": content_expr,
            "horiz_alignment": kwargs.get("horiz_alignment", "flex-start"),
            "fit_width": True,
            "fit_height": True,
            "single_width": False,
            "single_height": False,
            "min_width_css": kwargs.get("min_width_css", "96px"),
            "min_height_css": kwargs.get("min_height_css", "48px"),
            "%vc": bool(kwargs.get("vertical_centering", True)),
            "collapse_when_hidden": bool(kwargs.get("collapse_when_hidden", True)),
            **kwargs.get("extra_props", {}),
        }

        if at_to_top is not None:
            properties["at_to_top"] = bool(at_to_top)

        dim_args = {
            "min_width": min_width,
            "max_width": max_width,
            "fixed_width": fixed_width,
            "fit_width": fit_width,
            "min_height": min_height,
            "max_height": max_height,
            "fixed_height": fixed_height,
            "fit_height": fit_height,
        }
        self._apply_dimensions(properties, dim_args)
        self._add_visual_props(properties, kwargs)
        self._prune_typography_overrides_for_style(
            properties,
            kwargs,
            style_applied=bool(self._resolve_style_ref(kwargs)),
        )

        if width_unset:
            properties = self._apply_width_unset(properties)

        properties.pop("__explicit_dims", None)

        alert_obj: Dict[str, Any] = {
            "id": element_id,
            "%x": "Alert",
            "%dn": name,
            "%p": properties,
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            alert_obj["%s1"] = style_ref
        return alert_obj

    def google_map(
        self,
        name: str,
        *,
        data_source: Optional[Any] = None,
        map_type: Optional[str] = None,
        map_style: Optional[str] = None,
        custom_style: Optional[str] = None,
        allow_zoom_drag: Optional[bool] = None,
        disable_zoom_scroll: Optional[bool] = None,
        initial_zoom: Optional[int] = None,
        use_customized_marker_icon: Optional[bool] = None,
        custom_marker_icon: Optional[str] = None,
        marker_type: Optional[str] = None,
        marker_data_type: Optional[str] = None,
        location_field: Optional[str] = None,
        manual_setting: Optional[bool] = None,
        center: Optional[Any] = None,
        use_customized_marker_icon_for_list: Optional[str] = None,
        custom_marker_field: Optional[str] = None,
        custom_selected_icon: Optional[str] = None,
        custom_selected_icon_image: Optional[str] = None,
        show_info_window: Optional[str] = None,
        autoclose: Optional[bool] = None,
        marker_caption_expression: Optional[Any] = None,
        show_title_window: Optional[bool] = None,
        auto_close_window: Optional[bool] = None,
        number_of_markers: Optional[int] = None,
        marker_address: Optional[Any] = None,
        width: Optional[Union[int, str]] = None,
        height: Optional[Union[int, str]] = None,
        min_width: str = None,
        max_width: str = None,
        fixed_width: bool = False,
        fit_width: bool = False,
        min_height: str = None,
        max_height: str = None,
        fixed_height: bool = False,
        fit_height: bool = False,
        width_unset: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a GoogleMap element."""
        element_id = self.id_gen.element_id()

        def _parse_int_dimension(value: Any, fallback: int) -> int:
            if value is None:
                return fallback
            if isinstance(value, (int, float)):
                return int(value)
            raw = str(value).strip().lower()
            if re.fullmatch(r"\d+", raw):
                return int(raw)
            if re.fullmatch(r"\d+px", raw):
                return int(raw[:-2])
            return fallback

        parsed_width = _parse_int_dimension(width, 184)
        parsed_height = _parse_int_dimension(height, 140)

        properties: Dict[str, Any] = {
            "%t": kwargs.get("top", 0),
            "%l": kwargs.get("left", 0),
            "%w": parsed_width,
            "%h": parsed_height,
            "%z": kwargs.get("zindex", 2),
            "%vc": bool(kwargs.get("vertical_centering", True)),
            "collapse_when_hidden": bool(kwargs.get("collapse_when_hidden", True)),
            "single_width": bool(kwargs.get("single_width", True)),
            "min_width_css": kwargs.get("min_width_css", f"{parsed_width}px"),
            "horiz_alignment": kwargs.get("horiz_alignment", "flex-start"),
            "min_height_css": kwargs.get("min_height_css", f"{parsed_height}px"),
            "fit_height": bool(kwargs.get("fit_height_default", False)),
            "single_height": bool(kwargs.get("single_height", True)),
            "order": kwargs.get("order", 1),
            **kwargs.get("extra_props", {}),
        }

        if data_source is not None:
            properties["%ds"] = data_source
        if map_type is not None:
            properties["map_type"] = str(map_type)
        if map_style is not None:
            properties["map_style"] = str(map_style)
        if custom_style is not None:
            properties["custom_style"] = str(custom_style)
        if allow_zoom_drag is not None:
            properties["allow_zoom_drag"] = bool(allow_zoom_drag)
        if disable_zoom_scroll is not None:
            properties["disable_zoom_scroll"] = bool(disable_zoom_scroll)
        if initial_zoom is not None:
            properties["initial_zoom"] = int(initial_zoom)
        if use_customized_marker_icon is not None:
            properties["use_customized_marker_icon"] = bool(use_customized_marker_icon)
        if custom_marker_icon is not None:
            properties["custom_marker_icon"] = str(custom_marker_icon)
        if marker_type is not None:
            properties["marker_type"] = str(marker_type)
        if marker_data_type is not None:
            properties["marker_data_type"] = str(marker_data_type)
        if location_field is not None:
            properties["location_field"] = str(location_field)
        if manual_setting is not None:
            properties["manual_setting"] = bool(manual_setting)
        if center is not None:
            properties["center"] = center
        if use_customized_marker_icon_for_list is not None:
            properties["use_customized_marker_icon_for_list"] = str(use_customized_marker_icon_for_list)
        if custom_marker_field is not None:
            properties["custom_marker_field"] = str(custom_marker_field)
        if custom_selected_icon is not None:
            properties["custom_selected_icon"] = str(custom_selected_icon)
        if custom_selected_icon_image is not None:
            properties["custom_selected_icon_image"] = str(custom_selected_icon_image)
        if show_info_window is not None:
            properties["show_info_window"] = str(show_info_window)
        elif show_title_window is not None:
            # Backward-compatible alias: bool => canonical enum payload
            properties["show_info_window"] = "on_click" if bool(show_title_window) else "no"
        if autoclose is not None:
            properties["autoclose"] = bool(autoclose)
        elif auto_close_window is not None:
            # Backward-compatible alias for legacy CLI/MCP fields
            properties["autoclose"] = bool(auto_close_window)
        if marker_caption_expression is not None:
            properties["marker_caption_expression"] = marker_caption_expression
        if number_of_markers is not None:
            properties["number_of_markers"] = int(number_of_markers)
        if marker_address is not None:
            properties["marker_address"] = marker_address

        dim_args = {
            "min_width": min_width,
            "max_width": max_width,
            "fixed_width": fixed_width,
            "fit_width": fit_width,
            "min_height": min_height,
            "max_height": max_height,
            "fixed_height": fixed_height,
            "fit_height": fit_height,
        }
        self._apply_dimensions(properties, dim_args)
        self._add_visual_props(properties, kwargs)

        if width_unset:
            properties = self._apply_width_unset(properties)

        properties.pop("__explicit_dims", None)

        map_obj: Dict[str, Any] = {
            "id": element_id,
            "%x": "GoogleMap",
            "%dn": name,
            "%p": properties,
        }
        style_ref = self._resolve_style_ref(kwargs)
        if style_ref:
            map_obj["%s1"] = style_ref
        return map_obj

    def repeating_group(
        self,
        name: str,
        data_type: Optional[str] = None,
        width: int = 280,
        height: int = 280,
        width_unset: bool = False,
        style: str = None,
        min_width: str = None, max_width: str = None, fixed_width: bool = False, fit_width: bool = False,
        min_height: str = None, max_height: str = None, fixed_height: bool = False, fit_height: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Repeating Group"""
        element_id = self.id_gen.element_id()

        normalized_data_type = str(data_type).strip() if data_type is not None else ""

        if "data_source" in kwargs and kwargs["data_source"] is not None:
            data_source = kwargs["data_source"]
        elif normalized_data_type:
            search_p = {
                "%t5": normalized_data_type,
                "%co": kwargs.get("constraints", {})
            }
            sort_field = kwargs.get("sort_field")
            sort_direction = kwargs.get("sort_direction")
            if sort_field:
                search_p["%sf"] = sort_field
            if sort_direction:
                search_p["%sd"] = sort_direction

            data_source = {
                "%x": "Search",
                "%p": search_p
            }
        else:
            data_source = None
        normalized_layout = self._normalize_container_layout(kwargs.get("layout", "column"))

        properties = {
            "min_width_css": f"{width}px" if width is not None else "0px",
            "min_height_css": f"{height}px" if height is not None else "0px",
            "container_layout": normalized_layout,
            "fixed_rows": kwargs.get("fixed_rows", False),
            # "%ss": kwargs.get("separator_style", "none"), # Moved logic below
            "overflow_scroll": kwargs.get("scroll", True),
            **kwargs.get("extra_props", {})
        }
        if normalized_data_type:
            properties["%gt"] = normalized_data_type
        if data_source is not None:
            properties["%ds"] = data_source
        cell_height_value = kwargs.get("cell_height")
        if cell_height_value in (None, ""):
            properties["cell_min_height_css"] = "80px"
        else:
            properties["cell_min_height_css"] = str(cell_height_value)
        row_gap_value = kwargs.get("row_gap")
        use_gap_value = kwargs.get("use_gap")
        if use_gap_value is None:
            use_gap_value = row_gap_value is not None
        properties["use_gap"] = bool(use_gap_value)
        if row_gap_value is not None:
            properties["row_gap"] = int(row_gap_value)
        if width is not None:
            properties["%w"] = width
        if height is not None:
            properties["%h"] = height
        if kwargs.get("horiz_alignment"):
            properties["horiz_alignment"] = kwargs.get("horiz_alignment")
        if kwargs.get("vert_alignment"):
            properties["vert_alignment"] = kwargs.get("vert_alignment")
        if kwargs.get("nonant_alignment"):
            properties["nonant_alignment"] = kwargs.get("nonant_alignment")
            properties["align_to_parent_pos"] = kwargs.get("nonant_alignment")

        # Apply new dimension logic
        dim_args = {
            "min_width": min_width, "max_width": max_width, "fixed_width": fixed_width, "fit_width": fit_width,
            "min_height": min_height, "max_height": max_height, "fixed_height": fixed_height, "fit_height": fit_height
        }
        self._apply_dimensions(properties, dim_args)

        if "separator_style" in kwargs:
             properties["%ss"] = kwargs["separator_style"]
        elif not style:
             properties["%ss"] = "none"
        if kwargs.get("separator_width") is not None:
            properties["%sw"] = int(kwargs.get("separator_width"))
        if kwargs.get("separator_color") is not None:
            properties["%sc"] = kwargs.get("separator_color")

        self._add_visual_props(properties, kwargs)

        if width_unset:
             properties = self._apply_width_unset(properties)

        # Clean up internal markers
        properties.pop("__explicit_dims", None)

        return {
            "id": element_id,
            "%x": "RepeatingGroup",
            "%dn": name,
            "%s1": style if style else None,
            "%p": properties
        }

    def floating_group(
        self,
        name: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Cria um Floating Group"""
        element_id = self.id_gen.element_id()
        normalized_layout = self._normalize_container_layout(kwargs.get("layout", "row"))

        properties = {
            "container_layout": normalized_layout,
            "min_width_css": kwargs.get("width", "100%"),
            "fit_height": True,
            "%3f": kwargs.get("vertical_float", "top"),
            "floating_reference_horizontal_resp": kwargs.get("horizontal_float", "center"),
            "%b4": kwargs.get("horizontal_float", "center"),
            "%bas": kwargs.get("background_style", "bgcolor"),
            "%bgc": kwargs.get("bg_color", "#FFFFFF"),
            "%bs": kwargs.get("shadow_style", "outset"),
            "%bh": kwargs.get("shadow_h", 0),
            "%bsb": kwargs.get("shadow_blur", 8),
            "padding_left": kwargs.get("padding_left", 24),
            "padding_right": kwargs.get("padding_right", 24),
            "padding_top": kwargs.get("padding_top", 12),
            "padding_bottom": kwargs.get("padding_bottom", 12),
            **kwargs.get("extra_props", {})
        }

        self._add_visual_props(properties, kwargs)

        return {
            "id": element_id,
            "%x": "FloatingGroup",
            "%dn": name,
            "%p": properties
        }

    def text(
        self,
        name: str,
        content: str,
        style_id: str = None,
        horiz_alignment: str = None,
        width: int = None,
        height: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a Text element with dynamic content support"""
        import re
        element_id = self.id_gen.element_id()
        # Avoid propagating null-style typography/dimension keys.
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        width_unset = bool(kwargs.pop("width_unset", True))
        min_width = kwargs.pop("min_width", None)
        max_width = kwargs.pop("max_width", None)
        fixed_width = bool(kwargs.pop("fixed_width", False))
        fit_width = bool(kwargs.pop("fit_width", False))
        min_height = kwargs.pop("min_height", None)
        max_height = kwargs.pop("max_height", None)
        fixed_height = bool(kwargs.pop("fixed_height", False))
        fit_height = bool(kwargs.pop("fit_height", False))

        # 1. Handle Dynamic Content
        normalized_content = content.lower().replace("\n", " ").replace("\r", "")

        def _build_dynamic_parts(text: str):
            parts = []
            cursor = text
            # Current user's name
            m_user = re.search(r"current\s+user'?s\s+name", cursor, re.IGNORECASE)
            if m_user:
                before = cursor[:m_user.start()]
                after = cursor[m_user.end():]
                if before: parts.append(before)
                parts.append(DynamicTextBuilder.current_user("name", "text"))
                cursor = after

            # Current date/time:extract year
            m_year = re.search(r"current\s+date/time\s*:?\s*extract\s+year", cursor, re.IGNORECASE)
            if m_year:
                before = cursor[:m_year.start()]
                after = cursor[m_year.end():]
                if before: parts.append(before)
                parts.append({
                    "%x": "CurrentDateTime",
                    "%p": None,
                    "%n": {
                        "%x": "Message",
                        "%nm": "extract_year",
                        "%n": None,
                        "%a": None,
                        "is_slidable": False
                    },
                    "is_slidable": False
                })
                cursor = after

            if cursor: parts.append(cursor)
            return parts

        has_dynamic = bool(re.search(r"current\s+user'?s\s+name|current\s+date/time", content, re.IGNORECASE))
        if has_dynamic:
            try:
                parts = _build_dynamic_parts(content)
                final_content = DynamicTextBuilder.build(parts)
            except Exception:
                final_content = content
        else:
            final_content = content

        # 2. Alignment / Center BBCode
        def _wrap_center_bbcode(text_expr: Any) -> Any:
            if isinstance(text_expr, str):
                return f"[center]{text_expr}[/center]"
            if not (isinstance(text_expr, dict) and text_expr.get("%x") == "TextExpression" and isinstance(text_expr.get("%e"), dict)):
                return text_expr
            values = [v for _, v in sorted(text_expr["%e"].items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 9999)]
            if not values:
                values = ["[center][/center]"]
            else:
                if isinstance(values[0], str): values[0] = "[center]" + values[0]
                else: values.insert(0, "[center]")
                if isinstance(values[-1], str): values[-1] = values[-1] + "[/center]"
                else: values.append("[/center]")
            return {"%x": "TextExpression", "%e": {str(i): v for i, v in enumerate(values)}}

        if horiz_alignment == "center" and not kwargs.get("keep_overrides"):
            final_content = _wrap_center_bbcode(final_content)
            # We don't clear horiz_alignment here because we might want %fa property too?
            # CLI cleared it: horiz_alignment = None
            horiz_alignment = None

        if isinstance(final_content, str):
            final_content = {
                "%x": "TextExpression",
                "%e": {"0": final_content}
            }

        # 3. Build Properties
        properties = {
            "%t": kwargs.get("top", 0),
            "%l": kwargs.get("left", 0),
            "%w": width if width is not None else 100,
            "%3": final_content,
            "fit_height": True # Default for text
        }
        if height is not None:
            properties["%h"] = height

        # Apply min/max/fixed/fit sizing controls consistently.
        dim_args = {
            "min_width": min_width,
            "max_width": max_width,
            "fixed_width": fixed_width,
            "fit_width": fit_width,
            "min_height": min_height,
            "max_height": max_height,
            "fixed_height": fixed_height,
            "fit_height": fit_height,
        }
        self._apply_dimensions(properties, dim_args)

        # Typography
        font_size = kwargs.get("font_size")
        if font_size is not None:
            properties["%fs"] = font_size
            properties["font_size"] = font_size
        font_weight = kwargs.get("font_weight")
        if font_weight is not None:
            properties["font_weight"] = str(font_weight)
        line_height = kwargs.get("line_height")
        if line_height is not None:
            try:
                properties["line_height"] = float(line_height)
            except Exception:
                properties["line_height"] = line_height
        text_color = kwargs.get("text_color") or kwargs.get("color") or kwargs.get("font_color")
        if text_color:
            properties["%fc"] = text_color
            properties["font_color"] = text_color
        font_alignment = kwargs.get("font_alignment") or kwargs.get("fa")
        if font_alignment:
            properties["font_alignment"] = font_alignment
            properties["%fa"] = font_alignment

        # Style logic
        resolved_style_id = self._resolve_style_ref(kwargs, explicit_style=style_id)

        # Visual props
        self._add_visual_props(properties, kwargs)

        # Extra props (e.g., margins, explicit width)
        extra_props = kwargs.get("extra_props") or {}
        if isinstance(extra_props, dict) and extra_props:
            properties.update(extra_props)

        # Extra props for alignment if passed and not cleared
        if horiz_alignment:
             properties["horiz_alignment"] = horiz_alignment
             if horiz_alignment == "center": properties["%fa"] = "center"
             elif horiz_alignment == "right": properties["%fa"] = "right"

        explicit_typography = any(
            k in kwargs
            for k in (
                "font_size",
                "font_family",
                "font_weight",
                "font_alignment",
                "font_color",
                "text_color",
                "line_height",
                "letter_spacing",
                "word_spacing",
                "bold",
                "italic",
                "underline",
            )
        )

        style_for_body = resolved_style_id
        if style_for_body is None:
            style_for_body = self._resolve_default_text_style_ref(properties, kwargs)

        # Cleanup style overrides if style is present and typography wasn't
        # explicitly requested by the caller.
        if style_for_body and not kwargs.get("keep_overrides") and not explicit_typography:
             for k in ["%fs", "%fa", "%fc", "%f", "color", "font_size", "font_family", "font_weight", "font_alignment", "font_color"]:
                 properties.pop(k, None)

        if width_unset:
            properties = self._apply_width_unset(properties)

        # Internal bookkeeping key from _apply_dimensions
        properties.pop("__explicit_dims", None)


        return {
            "id": element_id,
            "type": "Text",
            "%x": "Text",
            "%dn": name,
            "%p": properties,
            **(
                {"%s1": style_for_body}
                if isinstance(style_for_body, str) and style_for_body.strip()
                else {}
            ),
        }



# ==========================================
# CORE: PAGE BUILDER
# ==========================================

class PageBuilder:
    """Builder for Bubble Page objects"""

    def __init__(self, id_gen: Optional[BubbleIDGenerator] = None):
        self.id_gen = id_gen or BubbleIDGenerator()

    def page(
        self,
        name: str,  # URL slug (e.g., "new_blank_page")
        title: str = None,  # Browser title (defaults to name)
        width: int = 1080,
        height: int = 767,
        layout: str = "column",  # "column", "row", "relative", "fixed"
        meta_title: str = None,
        meta_description: str = None,
        html_header: str = None,
        # Layout options
        row_gap: int = None,
        column_gap: int = None,
        use_gap: bool = False,
        container_vert_alignment: str = None,  # "center", "flex-end", "space-around", "space-between"
        container_horiz_alignment: str = None,
        default_width: int = None,
        min_height_px: int = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a Page element body.

        Args:
            name: Page URL slug (e.g., "new_page")
            title: Browser tab title (defaults to name)
            width: Default page width (default: 1080)
            height: Default page height (default: 767)
            layout: Container layout ("column", "row", "relative", "fixed")
            meta_title: SEO title
            meta_description: SEO description
            html_header: Custom HTML header scripts
            row_gap: Row gap in pixels
            column_gap: Column gap in pixels
            use_gap: Enable gap settings
            container_vert_alignment: Vertical alignment
            container_horiz_alignment: Horizontal alignment

        Returns:
            Dict with page body structure ready for CreateElement
        """
        page_id = self.id_gen.element_id()

        props = {
            "new_responsive": True,
            "fixed_width": True,
            "%w": width,
            "%h": height,
            "min_width_px": 0,
            "responsive_version": 1,
            "element_version": 5,
            "%t1": {
                "%x": "TextExpression",
                "%e": {"0": title or name}
            }
        }

        # Container layout
        if layout:
            props["container_layout"] = layout

        # Default width / min height
        if default_width is not None:
            props["default_width"] = default_width
        if min_height_px is not None:
            props["min_height_px"] = min_height_px

        # SEO / Meta properties
        if meta_title:
            props["meta_title"] = {"%x": "TextExpression", "%e": {"0": meta_title}}
        if meta_description:
            props["%md"] = {"%x": "TextExpression", "%e": {"0": meta_description}}
        if html_header:
            props["html_header"] = {"%x": "TextExpression", "%e": {"0": html_header}}

        # Layout / Gaps
        if row_gap is not None:
            props["row_gap"] = row_gap
        if column_gap is not None:
            props["column_gap"] = column_gap
        if use_gap:
            props["use_gap"] = True

        # Alignment
        if container_vert_alignment:
            props["container_vert_alignment"] = container_vert_alignment
        if container_horiz_alignment:
            props["container_horiz_alignment"] = container_horiz_alignment

        # Additional kwargs (background, borders, etc.)
        for k, v in kwargs.items():
            if v is not None and k not in ["extra_props"]:
                props[k] = v

        # Extra props dict overrides
        if "extra_props" in kwargs and kwargs["extra_props"]:
            props.update(kwargs["extra_props"])

        return {
            "id": page_id,
            "type": "Page",
            "%x": "Page",
            "%dn": name,
            "%s1": kwargs.get("style", "Page_standard_"),
            "%p": props
        }

    def reusable(
        self,
        name: str,
        width: int = 280,
        height: int = 280,
        layout: str = "column",
        element_type: str = "Group", # Default to Group
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a Reusable Element (CustomDefinition) body.

        Args:
            name: Reusable element name
            width: Initial width
            height: Initial height
            layout: Container layout ("column", "row", "relative", "fixed")
            element_type: Base element type ("Group", "Popup", "FloatingGroup")

        Returns:
            Dict with CustomDefinition body structure
        """
        reusable_id = self.id_gen.element_id()

        # NOTE: CustomDefinition uses "clean" keys WITHOUT % prefix for its root properties
        props = {
            "new_responsive": True,
            "%w": int(width),
            "%h": int(height),
            "%et": element_type,
            "responsive_version": 1,
            "element_version": 5,
            "custom_element_platform": "web"
        }

        if layout:
            props["container_layout"] = layout

        # Special dimension/layout/floating handling for CustomDefinition
        if "min_height_px" in kwargs:
            props["min_height_px"] = int(kwargs.pop("min_height_px"))
        if "default_width" in kwargs:
            props["default_width"] = int(kwargs.pop("default_width"))
        if "row_gap" in kwargs:
            props["row_gap"] = int(kwargs.pop("row_gap"))
        if "column_gap" in kwargs:
            props["column_gap"] = int(kwargs.pop("column_gap"))
        if "use_gap" in kwargs:
            props["use_gap"] = bool(kwargs.pop("use_gap"))

        # Floating Group specific
        if "float_v_relative" in kwargs:
            props["%3f"] = str(kwargs.pop("float_v_relative")).lower()  # top, bottom, both, none
        if "float_h_relative" in kwargs:
            horiz = str(kwargs.pop("float_h_relative")).lower()
            # Bubble stores horizontal floating reference under this key for floating containers.
            props["floating_reference_horizontal_resp"] = horiz
            # Keep legacy key for compatibility with older payload variants.
            props["%b4"] = horiz
        if "float_zindex" in kwargs:
            props["float_zindex"] = kwargs.pop("float_zindex") # front, back
        if "parallax" in kwargs:
            try:
                p = float(kwargs.pop("parallax"))
                props["parallax"] = int(p) if float(p).is_integer() else p
            except Exception:
                kwargs.pop("parallax", None)

        # Data Class and Source
        if "data_class" in kwargs:
            props["%gt"] = kwargs.pop("data_class")
        if "data_source" in kwargs:
            props["%ds"] = kwargs.pop("data_source")

        # Custom Properties (Parameters)
        if "parameters" in kwargs:
            props["parameters"] = kwargs.pop("parameters")

        # Additional kwargs
        for k, v in kwargs.items():
            if v is not None and k not in ["extra_props"]:
                props[k] = v

        # Extra props dict overrides
        if "extra_props" in kwargs and kwargs["extra_props"]:
            props.update(kwargs["extra_props"])

        return {
            "%x": "CustomDefinition",
            "id": reusable_id,
            "%nm": name,
            "%p": props
        }



# ==========================================
# CORE: ACTION BUILDER
# ==========================================

class DynamicTextBuilder:
    """Construtor de expressões de texto dinâmico (TextExpression)"""

    @staticmethod
    def build(parts: List[Union[str, Dict]]) -> Dict[str, Any]:
        """
        Constrói estrutura TextExpression a partir de lista de partes.
        Ex: ["Hello ", current_user_name_obj] -> { "%x": "TextExpression", "%e": { "0": "Hello ", "1": ... } }
        """
        expression = {
            "%x": "TextExpression",
            "%e": {}
        }

        for i, part in enumerate(parts):
            expression["%e"][str(i)] = part

        return expression

    @staticmethod
    def current_user(field: str = None, field_type: str = "text") -> Dict[str, Any]:
        """
        Retorna objeto representando CurrentUser.
        Se field for fornecido, aninha o acesso ao campo.
        """
        base = {
            "%x": "CurrentUser",
            "%p": None,
            "%n": None,
            "is_slidable": False
        }

        if field:
            # Bubble uses "FIELDNAME_TYPE" format typically
            field_val = f"{field}_{field_type}"

            field_node = {
                "%x": "Message",
                "%nm": field_val,
                "%n": None,
                "%a": None,
                "is_slidable": False
            }
            base["%n"] = field_node

        return base

class WorkflowBuilder:
    """Construtor de workflows com eventos corretos"""

    def __init__(self, id_gen=None):
        self.id_gen = id_gen or BubbleIDGenerator()

    def button_clicked(self, button_id: str) -> Dict:
        """
        Cria workflow ButtonClicked CORRETO
        Using "%x": "ButtonClicked" instead of "ElementEvent"
        """
        wf_id = self.id_gen.element_id()

        return {
            "id": wf_id,
            "%x": "ButtonClicked",  # CORRETO
            "%p": {
                "%ei": button_id
            },
            "actions": {}  # Vazio inicialmente
        }

    def element_event(self, element_id: str, event_type: str = "click") -> Dict:
        """
        Cria workflow genérico ElementEvent
        """
        wf_id = self.id_gen.element_id()

        return {
            "id": wf_id,
            "%x": "ElementEvent",
            "%p": {
                "%ei": element_id,
                "%et": event_type,
                "%eC": True
            },
            "actions": {}
        }

class ActionBuilder:
    """Construtor de ações de workflow"""

    def __init__(self, id_gen: Optional[BubbleIDGenerator] = None):
        self.id_gen = id_gen or BubbleIDGenerator()

    def reset_inputs(
        self,
        index: int = 0,
        element_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria ação Reset Inputs (se element_id=None) ou Reset Group.
        """
        action_id = self.id_gen.element_id()

        if element_id:
            # Reset Group/Popup
            return {
                str(index): {
                    "%x": "ResetGroup",
                    "%p": {"%ei": element_id},
                    "id": action_id
                }
            }
        else:
            # Reset Page/Group Inputs
            return {
                str(index): {
                    "%x": "ResetInputs",
                    "%p": None,
                    "id": action_id
                }
            }

    def open_url(
        self,
        index: int = 0,
        url: str = "https://",
        open_in_new_tab: bool = True
    ) -> Dict[str, Any]:
        """Cria ação Open External URL"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "OpenURL",
                "%p": {
                    "url": {
                        "%x": "TextExpression",
                        "%e": {"0": url}
                    },
                    "%o9": open_in_new_tab
                },
                "id": action_id
            }
        }

    def navigate_to_page(
        self,
        index: int = 0,
        page_name: str = "index",
        send_data: Optional[Any] = None,
        open_in_new_tab: Optional[bool] = None,
        keep_current_page_params: Optional[bool] = None,
        add_parameters: Optional[bool] = None,
        url_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Cria ação Change Page"""
        action_id = self.id_gen.element_id()
        properties = {
            # ChangePage destination uses element_id in Bubble schema.
            "element_id": page_name,
            # Compatibility alias: some editors still read %ei for ChangePage.
            "%ei": page_name,
        }
        if send_data is not None:
            properties["data_to_send"] = send_data
        if open_in_new_tab is not None:
            properties["%o9"] = bool(open_in_new_tab)
        if keep_current_page_params is not None:
            properties["keep_current_page_params"] = bool(keep_current_page_params)
        if add_parameters is not None:
            properties["add_parameters"] = bool(add_parameters)
        if url_parameters is not None:
            properties["url_parameters"] = url_parameters

        return {
            str(index): {
                "%x": "ChangePage",
                "%p": properties,
                "id": action_id
            }
        }

    def refresh_page(self, index: int = 0) -> Dict[str, Any]:
        """Cria ação Refresh Page."""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "RefreshPage",
                "%p": None,
                "id": action_id,
            }
        }

    def go_previous(self, index: int = 0) -> Dict[str, Any]:
        """Cria ação Go to Previous Page."""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "GoPrevious",
                "%p": None,
                "id": action_id,
            }
        }

    def pause_workflow_client(
        self,
        index: int = 0,
        length: Optional[int] = None,
        hide_status_bar: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Cria ação Pause Workflow Client."""
        action_id = self.id_gen.element_id()
        props: Optional[Dict[str, Any]] = None
        if length is not None or hide_status_bar is not None:
            props = {}
            if length is not None:
                props["length"] = int(length)
            if hide_status_bar is not None:
                props["hide_status_bar"] = bool(hide_status_bar)
        return {
            str(index): {
                "%x": "PauseWFClient",
                "%p": props,
                "id": action_id,
            }
        }

    def terminate_workflow(self, index: int = 0) -> Dict[str, Any]:
        """Cria ação Terminate Workflow."""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "TerminateWorkflow",
                "%p": None,
                "id": action_id,
            }
        }

    def show_element(self, index: int = 0, element_id: str = "") -> Dict[str, Any]:
        """Cria ação Show Element"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "ShowElement",
                "%p": {"%ei": element_id},
                "id": action_id
            }
        }

    def hide_element(self, index: int = 0, element_id: str = "") -> Dict[str, Any]:
        """Cria ação Hide Element"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "HideElement",
                "%p": {"%ei": element_id},
                "id": action_id
            }
        }

    def toggle_element(self, index: int = 0, element_id: str = "") -> Dict[str, Any]:
        """Cria ação Toggle Element"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "ToggleElement",
                "%p": {"%ei": element_id},
                "id": action_id
            }
        }

    def animate_element(
        self,
        index: int = 0,
        element_id: str = "",
        animation: str = "",
        duration: Optional[int] = None,
        customize_duration: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Cria ação Animate Element"""
        action_id = self.id_gen.element_id()
        props: Dict[str, Any] = {"%ei": element_id}
        if animation:
            props["animation"] = str(animation)
        if duration is not None:
            props["duration"] = int(duration)
        if customize_duration is not None:
            props["customize_duration"] = bool(customize_duration)
        return {
            str(index): {
                "%x": "AnimateElement",
                "%p": props,
                "id": action_id
            }
        }

    def scroll_to_element(
        self,
        index: int = 0,
        element_id: str = "",
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Cria ação Scroll To Element"""
        action_id = self.id_gen.element_id()
        props: Dict[str, Any] = {"%ei": element_id}
        if offset is not None:
            props["offset"] = int(offset)
        return {
            str(index): {
                "%x": "ScrollToElement",
                "%p": props,
                "id": action_id
            }
        }

    def set_focus_to_element(
        self,
        index: int = 0,
        element_id: str = "",
    ) -> Dict[str, Any]:
        """Cria ação Set Focus To Element"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "SetFocusToElement",
                "%p": {"%ei": element_id},
                "id": action_id
            }
        }

    def display_group_data(
        self,
        index: int = 0,
        element_id: str = "",
        data_source: Any = None,
    ) -> Dict[str, Any]:
        """Cria ação Display data in a group/popup"""
        action_id = self.id_gen.element_id()
        props: Dict[str, Any] = {"%ei": element_id}
        if data_source is not None:
            props["%ds"] = data_source
        return {
            str(index): {
                "%x": "DisplayGroupData",
                "%p": props,
                "id": action_id
            }
        }

    def set_custom_state(
        self,
        index: int = 0,
        element_id: str = "",
        custom_state: str = "",
        value: Any = None,
    ) -> Dict[str, Any]:
        """Cria ação Set state of an element"""
        action_id = self.id_gen.element_id()
        props: Dict[str, Any] = {"%ei": element_id}
        if custom_state:
            props["custom_state"] = str(custom_state)
        if value is not None:
            props["%v"] = value
        return {
            str(index): {
                "%x": "SetCustomState",
                "%p": props,
                "id": action_id
            }
        }

    def make_changes_to_thing(
        self,
        index: int = 0,
        thing_expr: Dict[str, Any] = None,
        field_values: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Cria ação Make Changes to Thing"""
        action_id = self.id_gen.element_id()

        if thing_expr is None:
            thing_expr = {
                "%x": "CurrentUser",
                "%p": None,
                "%n": None
            }

        i2_fields = {}
        if field_values:
            for idx, (field_name, value) in enumerate(field_values.items()):
                if isinstance(value, dict):
                    value_expr = value
                elif isinstance(value, bool):
                    value_expr = value
                elif isinstance(value, (int, float, list)):
                    value_expr = value
                elif isinstance(value, str):
                    value_expr = {
                        "%x": "TextExpression",
                        "%e": {"0": value, "1": {"%x": "Empty"}}
                    }
                else:
                    value_expr = {
                        "%x": "TextExpression",
                        "%e": {"0": str(value), "1": {"%x": "Empty"}}
                    }

                i2_fields[str(idx)] = {
                    "%k": field_name,
                    "%ak": {"%x": "Empty"},
                    "%v": value_expr
                }

        return {
            str(index): {
                "%x": "ChangeThing",
                "%p": {
                    "%tc": thing_expr,
                    "%cs": i2_fields
                },
                "id": action_id
            }
        }

    def make_changes_to_list_of_things(
        self,
        index: int = 0,
        type_name: str = "",
        list_expr: Dict[str, Any] = None,
        field_values: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Cria ação Make Changes to a List of Things"""
        action_id = self.id_gen.element_id()

        i2_fields = {}
        if field_values:
            for idx, (field_name, value) in enumerate(field_values.items()):
                if isinstance(value, dict):
                    value_expr = value
                elif isinstance(value, bool):
                    value_expr = value
                elif isinstance(value, (int, float)):
                    value_expr = value
                elif isinstance(value, str):
                    value_expr = {
                        "%x": "TextExpression",
                        "%e": {"0": value}
                    }
                else:
                    value_expr = {
                        "%x": "TextExpression",
                        "%e": {"0": str(value)}
                    }

                i2_fields[str(idx)] = {
                    "%k": field_name,
                    "%ak": {"%x": "Empty"},
                    "%v": value_expr
                }

        return {
            str(index): {
                "%x": "ChangeListOfThings",
                "%p": {
                    "type_to_change": type_name,
                    "%tc": list_expr,
                    "%cs": i2_fields
                },
                "id": action_id
            }
        }

    def delete_thing(
        self,
        index: int = 0,
        thing_expr: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Cria ação Delete Thing"""
        action_id = self.id_gen.element_id()

        if thing_expr is None:
            thing_expr = {
                "%x": "CurrentUser",
                "%p": None,
                "%n": None
            }

        return {
            str(index): {
                "%x": "DeleteThing",
                "%p": {
                    "to_delete": thing_expr
                },
                "id": action_id
            }
        }

    def delete_list_of_things(
        self,
        index: int = 0,
        type_name: str = "",
        list_expr: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Cria ação Delete a List of Things"""
        action_id = self.id_gen.element_id()

        if list_expr is None:
            list_expr = {
                "%x": "Search",
                "%p": None,
                "%n": None
            }
        elif isinstance(list_expr, dict) and str(list_expr.get("%x") or "") == "Search":
            list_expr = dict(list_expr)
            list_expr.setdefault("%n", None)

        return {
            str(index): {
                "%x": "DeleteListOfThings",
                "%p": {
                    "type_to_delete": type_name,
                    "to_delete": list_expr
                },
                "id": action_id
            }
        }

    def copy_list_of_things(
        self,
        index: int = 0,
        type_name: str = "",
        list_expr: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Cria ação Copy a List of Things"""
        action_id = self.id_gen.element_id()

        if list_expr is None:
            list_expr = {
                "%x": "Search",
                "%p": None,
                "%n": None
            }
        elif isinstance(list_expr, dict) and str(list_expr.get("%x") or "") == "Search":
            list_expr = dict(list_expr)
            list_expr.setdefault("%n", None)

        return {
            str(index): {
                "%x": "CopyListOfThings",
                "%p": {
                    "type_to_copy": type_name,
                    "to_copy": list_expr
                },
                "id": action_id
            }
        }

    def set_slug(
        self,
        index: int = 0,
        thing_expr: Dict[str, Any] = None,
        slug_expr: Any = None
    ) -> Dict[str, Any]:
        """Cria ação Set a Thing's Slug"""
        action_id = self.id_gen.element_id()

        if thing_expr is None:
            thing_expr = {
                "%x": "CurrentUser",
                "%p": None,
                "%n": None
            }

        if isinstance(slug_expr, dict) and slug_expr.get("%x") == "TextExpression":
            normalized_slug = {"%x": "TextExpression", "%e": dict(slug_expr.get("%e") or {})}
        elif isinstance(slug_expr, dict):
            normalized_slug = {
                "%x": "TextExpression",
                "%e": {"0": slug_expr}
            }
        else:
            normalized_slug = {
                "%x": "TextExpression",
                "%e": {"0": "" if slug_expr is None else str(slug_expr)}
            }

        return {
            str(index): {
                "%x": "SetSlug",
                "%p": {
                    "%tc": thing_expr,
                    "slug": normalized_slug
                },
                "id": action_id
            }
        }

    def send_email(
        self,
        index: int = 0,
        to_email: str = "",
        subject: str = "",
        body: str = ""
    ) -> Dict[str, Any]:
        """Cria ação Send Email"""
        action_id = self.id_gen.element_id()

        return {
            str(index): {
                "%x": "SendEmail",
                "%p": {
                    "to": {
                        "%x": "TextExpression",
                        "%e": {"0": to_email}
                    },
                    "subject": {
                        "%x": "TextExpression",
                        "%e": {"0": subject}
                    },
                    "body": {
                        "%x": "TextExpression",
                        "%e": {"0": body}
                    }
                },
                "id": action_id
            }
        }

    def show_alert(
        self,
        index: int = 0,
        message: str = "",
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cria ação Show Alert"""
        action_id = self.id_gen.element_id()

        params = {
            "message": {
                "%x": "TextExpression",
                "%e": {"0": message}
            }
        }

        if title:
            params["title"] = {
                "%x": "TextExpression",
                "%e": {"0": title}
            }

        return {
            str(index): {
                "%x": "ShowAlert",
                "%p": params,
                "id": action_id
            }
        }

    def sign_up_user(
        self,
        index: int = 0,
        email_id: str = "",
        password_id: str = ""
    ) -> Dict[str, Any]:
        """Cria ação Sign User Up"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "SignUp",
                "%p": {
                    "email": {
                        "%x": "TextExpression",
                        "%e": {"0": {"%x": "ElementParent", "%n": {"%nm": "value_text", "%e": email_id}}}
                    },
                    "password": {
                        "%x": "TextExpression",
                        "%e": {"0": {"%x": "ElementParent", "%n": {"%nm": "value_text", "%e": password_id}}}
                    }
                },
                "id": action_id
            }
        }

    def log_in_user(
        self,
        index: int = 0,
        email_id: str = "",
        password_id: str = ""
    ) -> Dict[str, Any]:
        """Cria ação Log User In"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "LogIn",
                "%p": {
                    "email": {
                        "%x": "TextExpression",
                        "%e": {"0": {"%x": "ElementParent", "%n": {"%nm": "value_text", "%e": email_id}}}
                    },
                    "password": {
                        "%x": "TextExpression",
                        "%e": {"0": {"%x": "ElementParent", "%n": {"%nm": "value_text", "%e": password_id}}}
                    },
                    "stay_logged_in": True
                },
                "id": action_id
            }
        }

    def log_out_user(self, index: int = 0) -> Dict[str, Any]:
        """Cria ação Log User Out"""
        action_id = self.id_gen.element_id()
        return {
            str(index): {
                "%x": "LogOut",
                "%p": {},
                "id": action_id
            }
        }

    def create_thing(
        self,
        index: int = 0,
        data_type: str = "",
        field_values: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Cria ação Create Thing (NewThing)

        Args:
            data_type: Tipo do dado (ex: "custom.user", "custom.event")
            field_values: Dict com {campo: valor/expressão}
        """
        action_id = self.id_gen.element_id()

        i2_fields = {}
        if field_values:
            for idx, (field_name, value) in enumerate(field_values.items()):
                if isinstance(value, dict):
                    value_expr = value
                elif isinstance(value, bool):
                    value_expr = value
                elif isinstance(value, (int, float, list)):
                    value_expr = value
                elif isinstance(value, str):
                    value_expr = {
                        "%x": "TextExpression",
                        "%e": {"0": value}
                    }
                else:
                    value_expr = {
                        "%x": "TextExpression",
                        "%e": {"0": str(value)}
                    }

                i2_fields[str(idx)] = {
                    "%k": field_name,
                    "%ak": {"%x": "Empty"},
                    "%v": value_expr
                }

        return {
            str(index): {
                "%x": "NewThing",
                "%p": {
                    "%tt": data_type,
                    "%i2": i2_fields
                },
                "id": action_id
            }
        }


# ==========================================
# COLOR BUILDER
# ==========================================

# Default color keys in Bubble
DEFAULT_COLOR_KEYS = [
    "primary",          # Primary color
    "primary_contrast", # Primary contrast
    "%3",               # Text color
    "surface",          # Surface
    "background",       # Background
    "destructive",      # Destructive/error
    "success",          # Success
    "alert"             # Alert/warning
]

# Friendly names for default colors
DEFAULT_COLOR_NAMES = {
    "primary": "Primary",
    "primary_contrast": "Primary Contrast",
    "%3": "Text",
    "surface": "Surface",
    "background": "Background",
    "destructive": "Destructive",
    "success": "Success",
    "alert": "Alert"
}


class ColorBuilder:
    """
    Builder for color variable operations.
    Handles both default (system) colors and custom colors.
    """

    def __init__(self, id_gen: 'BubbleIDGenerator' = None):
        self.id_gen = id_gen or BubbleIDGenerator()

    @staticmethod
    def build_color_entry(
        name: str,
        rgba: str,
        order: int = 0,
        description: str = "",
        deleted: bool = False
    ) -> Dict[str, Any]:
        """
        Build a single custom color entry.

        Args:
            name: Display name for the color
            rgba: RGBA color value (e.g., "rgba(255,0,0,1)")
            order: Display order (0-based)
            description: Optional description
            deleted: If True, marks for soft-delete

        Returns:
            Color entry dict ready for nested use
        """
        return {
            "%d3": description,
            "%nm": name,
            "%del": deleted,
            "rgba": rgba,
            "order": order
        }

    def generate_color_id(self) -> str:
        """Generate a new color ID (5-char format like bXXXX)"""
        return self.id_gen.element_id()

    @staticmethod
    def build_default_colors_body(colors: Dict[str, str]) -> Dict[str, Any]:
        """
        Build the body for updating default colors.

        Args:
            colors: Dict mapping color key to rgba value
                    e.g., {"primary": "rgba(0,0,255,1)", "background": "rgba(255,255,255,1)"}

        Returns:
            Body dict for ChangeAppSetting intent
        """
        body = {}
        for key, rgba_value in colors.items():
            body[key] = {"%d1": rgba_value}
        return body

    @staticmethod
    def build_custom_colors_body(colors: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build the body for updating custom colors.

        Args:
            colors: Dict mapping color_id to color entry
                    e.g., {"bXXXX": {"name": "...", "rgba": "...", "order": 0}}

        Returns:
            Body dict for ChangeAppSetting intent
        """
        return {"%d1": colors}

    @staticmethod
    def get_default_color_path() -> List[str]:
        """Get the path array for default colors"""
        return ["settings", "client_safe", "color_tokens"]

    @staticmethod
    def get_custom_color_path() -> List[str]:
        """Get the path array for custom colors"""
        return ["settings", "client_safe", "color_tokens_user"]

    @staticmethod
    def sort_colors_by_name(
        colors: Dict[str, Dict[str, Any]],
        reverse: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        Sort custom colors by name and update order values.

        Args:
            colors: Current custom colors dict
            reverse: If True, sort Z-A instead of A-Z

        Returns:
            New colors dict with updated order values
        """
        # Extract and sort by name
        sorted_items = sorted(
            colors.items(),
            key=lambda x: x[1].get("%nm", "").lower(),
            reverse=reverse
        )

        # Rebuild with new order values
        result = {}
        for idx, (color_id, color_data) in enumerate(sorted_items):
            updated = dict(color_data)
            updated["order"] = idx
            result[color_id] = updated

        return result

    @staticmethod
    def move_color_to_position(
        colors: Dict[str, Dict[str, Any]],
        color_id: str,
        new_position: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Move a color to a specific position and reorder others.

        Args:
            colors: Current custom colors dict
            color_id: ID of color to move
            new_position: Target position (0-based)

        Returns:
            New colors dict with updated order values
        """
        if color_id not in colors:
            raise ValueError(f"Color ID {color_id} not found")

        # Sort by current order
        sorted_items = sorted(
            colors.items(),
            key=lambda x: x[1].get("order", 0)
        )

        # Remove the target color and insert at new position
        items_list = list(sorted_items)
        current_idx = next(i for i, (cid, _) in enumerate(items_list) if cid == color_id)
        item = items_list.pop(current_idx)
        items_list.insert(new_position, item)

        # Rebuild with new order values
        result = {}
        for idx, (cid, color_data) in enumerate(items_list):
            updated = dict(color_data)
            updated["order"] = idx
            result[cid] = updated

        return result

    @staticmethod
    def swap_colors(
        colors: Dict[str, Dict[str, Any]],
        color_id_1: str,
        color_id_2: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Swap positions of two colors.

        Args:
            colors: Current custom colors dict
            color_id_1: First color ID
            color_id_2: Second color ID

        Returns:
            New colors dict with swapped order values
        """
        if color_id_1 not in colors or color_id_2 not in colors:
            raise ValueError(f"One or both color IDs not found")

        result = {}
        order_1 = colors[color_id_1].get("order", 0)
        order_2 = colors[color_id_2].get("order", 0)

        for cid, color_data in colors.items():
            updated = dict(color_data)
            if cid == color_id_1:
                updated["order"] = order_2
            elif cid == color_id_2:
                updated["order"] = order_1
            result[cid] = updated

        return result


# ==========================================
# FONT BUILDER
# ==========================================

class FontBuilder:
    """
    Builder for font variable operations.
    Handles both the default 'App Font' and custom font variables.
    Uses Google Fonts.
    """

    def __init__(self, id_gen: 'BubbleIDGenerator' = None):
        self.id_gen = id_gen or BubbleIDGenerator()

    @staticmethod
    def build_font_entry(
        name: str,
        font_family: str,
        order: int = 0,
        description: str = "",
        deleted: bool = False
    ) -> Dict[str, Any]:
        """
        Build a single custom font entry.

        Args:
            name: Display name for the font variable
            font_family: Google Font family name (e.g., "DM Mono", "Inter")
            order: Display order (0-based)
            description: Optional description
            deleted: If True, marks for soft-delete

        Returns:
            Font entry dict ready for nested use
        """
        return {
            "%d3": description,
            "%nm": name,
            "%del": deleted,
            "font_family": font_family,
            "order": order
        }

    def generate_font_id(self) -> str:
        """Generate a new font ID (5-char format like bXXXX)"""
        return self.id_gen.element_id()

    @staticmethod
    def build_app_font_body(font_family: str) -> Dict[str, Any]:
        """
        Build the body for updating the App Font (default font).

        Args:
            font_family: Google Font family name

        Returns:
            Body dict for ChangeAppSetting intent
        """
        return {"%d1": font_family}

    @staticmethod
    def build_custom_fonts_body(fonts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build the body for updating custom fonts.

        Args:
            fonts: Dict mapping font_id to font entry

        Returns:
            Body dict for ChangeAppSetting intent
        """
        return {"%d1": fonts}

    @staticmethod
    def get_app_font_path() -> List[str]:
        """Get the path array for the App Font (default font)"""
        return ["settings", "client_safe", "font_tokens"]

    @staticmethod
    def get_custom_font_path() -> List[str]:
        """Get the path array for custom fonts"""
        return ["settings", "client_safe", "font_tokens_user"]


# ==========================================
# STYLE BUILDERS
# ==========================================

class StyleBuilder:
    """
    Builder for generic Bubble styles.
    Handles creation and property mapping for various Bubble elements.
    """

    def __init__(self, id_gen: 'BubbleIDGenerator' = None):
        self.id_gen = id_gen or BubbleIDGenerator()

    def create_style(
        self,
        name: str,
        element_type: str = "Button",
        # Background
        background_style: str = None,          # %bas
        bg_color: str = None,                  # %bgc
        gradient_start_color: str = None,      # %bgf
        gradient_end_color: str = None,        # %bgt
        gradient_mid_color: str = None,        # background_gradient_mid
        gradient_style: str = None,            # background_gradient_style: linear, radial
        gradient_direction: str = None,        # background_gradient_style
        gradient_angle: int = None,            # background_gradient_custom_angle

        # Typography / Icon
        font_color: str = "#000000",           # %fc
        placeholder_color: str = None,         # %pc
        icon_color: str = None,                # %ic
        icon_size: int = None,                 # icon_size
        font_size: int = 14,                   # %fs
        font_family: str = "Inter",            # font_family
        font_weight: str = None,               # font_weight
        font_face: str = None,                 # font_face
        alignment: str = None,                 # %fa
        bold: bool = False,                    # %b
        italic: bool = False,                  # %i
        underline: bool = False,               # %u
        line_height: float = None,             # %lh
        letter_spacing: float = None,          # %ls
        tag: str = None,                       # bubble_tag

        # Layout
        padding: int = None,                   # padding_top, bottom, left, right (if same)
        padding_top: int = None,               # padding_top
        padding_bottom: int = None,            # padding_bottom
        padding_left: int = None,              # padding_left
        padding_right: int = None,             # padding_right
        gap: int = None,                       # button_gap
        # Border (Shared)
        border_color: str = None,              # %bc (shared)
        border_width: int = None,              # %bw (shared)
        border_radius: int = None,             # %br (shared)
        border_style: str = None,              # %bos (shared)

        # Borders (Combined Toggle)
        border_type: str = "shared",           # shared or independent

        # Independent Borders
        border_style_top: str = None,          # border_style_top
        border_style_bottom: str = None,       # border_style_bottom
        border_style_left: str = None,         # border_style_left
        border_style_right: str = None,        # border_style_right
        border_color_top: str = None,          # border_color_top
        border_color_bottom: str = None,       # border_color_bottom
        border_color_left: str = None,         # border_color_left
        border_color_right: str = None,        # border_color_right
        border_width_top: int = None,          # border_width_top
        border_width_bottom: int = None,       # border_width_bottom
        border_width_left: int = None,         # border_width_left
        border_width_right: int = None,        # border_width_right

        # Independent Radius
        radius_top_left: int = None,           # border_roundness_top
        radius_top_right: int = None,          # border_roundness_right
        radius_bottom_right: int = None,       # border_roundness_bottom
        radius_bottom_left: int = None,        # border_roundness_left

        shadow_style: str = None,
        shadow_color: str = None,              # %sc? Correct key is %bsc

        # DateInput Specific
        date_format: str = None,               # date_format
        custom_format: str = None,             # custom_format
        # SliderInput style specific
        range_type: str = None,                # range_type (simple/range)
        slider_background_color: str = None,   # background_color (slider track)
        handle_color: str = None,              # handle_color
        range_area_color: str = None,          # range_area_color

        # Transitions
        transitions: Dict[str, Dict[str, Any]] = None, # property -> {duration, fn}
        center_text_vertically: bool = True,           # %vc
        **kwargs
    ) -> Dict[str, Any]:
        """
        Creates a new style payload (CreateStyle).
        """
        # Handle SearchBox -> AutocompleteDropdown mapping
        # User sees "SearchBox", Bubble sees "AutocompleteDropdown"
        if element_type == "SearchBox":
            internal_type = "AutocompleteDropdown"
        elif element_type == "Popup":
            internal_type = "Popup"
        elif element_type == "DateInput":
            internal_type = "DateInput"
        else:
            internal_type = element_type

        # Generate Style ID: ElementType_RandomID (e.g. Button_b1234 or AutocompleteDropdown_sb1)
        # Use internal_type for the ID prefix to match Bubble's expectation
        style_id = f"{internal_type}_{self.id_gen.element_id()}"

        # Handle padding shortcut
        if padding is not None:
            if padding_top is None: padding_top = padding
            if padding_bottom is None: padding_bottom = padding
            if padding_left is None: padding_left = padding
            if padding_right is None: padding_right = padding

        # Handle background_color alias (CLI passes --background-color -> background_color)
        if "background_color" in kwargs:
            bg_color = kwargs.pop("background_color")

        # Use kwargs to pass all properties to a temporary update_style call to generate the changes
        # Then convert the changes to a properties dict

        # 1. Base props
        props = {}

        # 2. Use update_style logic to resolve all keys
        # We'll create a dummy update_style result and extract the %p values
        temp_builder = StyleBuilder(self.id_gen)
        # Pass all known arguments plus kwargs
        update_args = {
            "style_id": style_id,
            "background_style": background_style,
            "bg_color": bg_color,
            "gradient_start_color": gradient_start_color,
            "gradient_end_color": gradient_end_color,
            "gradient_mid_color": gradient_mid_color,
            "gradient_style": gradient_style,
            "gradient_direction": gradient_direction,
            "gradient_angle": gradient_angle,
            "font_color": font_color,
            "placeholder_color": placeholder_color,
            "icon_color": icon_color,
            "icon_size": icon_size,
            "font_size": font_size,
            "font_family": font_family,
            "font_weight": font_weight,
            "font_face": font_face,
            "tag": tag,
            "alignment": alignment,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "line_height": line_height,
            "letter_spacing": letter_spacing,
            "padding_top": padding_top,
            "padding_bottom": padding_bottom,
            "padding_left": padding_left,
            "padding_right": padding_right,
            "gap": gap,
            "border_color": border_color,
            "border_width": border_width,
            "border_radius": border_radius,
            "border_style": border_style,
            "border_type": border_type,
            "border_style_top": border_style_top,
            "border_style_bottom": border_style_bottom,
            "border_style_left": border_style_left,
            "border_style_right": border_style_right,
            "border_color_top": border_color_top,
            "border_color_bottom": border_color_bottom,
            "border_color_left": border_color_left,
            "border_color_right": border_color_right,
            "border_width_top": border_width_top,
            "border_width_bottom": border_width_bottom,
            "border_width_left": border_width_left,
            "border_width_right": border_width_right,
            "radius_top_left": radius_top_left,
            "radius_top_right": radius_top_right,
            "radius_bottom_right": radius_bottom_right,
            "radius_bottom_left": radius_bottom_left,
            "shadow_style": shadow_style,
            "shadow_color": shadow_color,
            "date_format": date_format,
            "custom_format": custom_format,
            "range_type": range_type,
            "slider_background_color": slider_background_color,
            "handle_color": handle_color,
            "range_area_color": range_area_color,
            "transitions": transitions,
            "center_text_vertically": center_text_vertically
        }
        update_args.update({k: v for k, v in kwargs.items() if k not in update_args})

        changes = temp_builder.update_style(inject_defaults=False, **update_args)

        # 3. Extract properties from changes
        transitions_payload = {}
        props = {}
        for change in changes:
            path = change.get("path", [])
            body = change.get("body")
            if len(path) >= 4 and path[2] == "%p":
                key = path[3]
                props[key] = body
            elif len(path) >= 4 and path[2] == "transitions":
                transitions_payload[path[3]] = body

        style_obj = {
            "id": style_id,
            "%d": name,
            "%x": internal_type,
            "%p": props,
            "%s": {} # Initialize empty states list
        }
        if transitions_payload:
            style_obj["transitions"] = transitions_payload

        return style_obj

    def update_style(
        self,
        style_id: str,
        # Background
        background_style: str = None,          # %bas: none, bgcolor, gradient, image
        bg_color: str = None,                  # %bgc
        gradient_start_color: str = None,      # %bgf
        gradient_end_color: str = None,        # %bgt
        gradient_mid_color: str = None,        # background_gradient_mid
        gradient_style: str = None,            # background_gradient_style: linear, radial
        gradient_direction: str = None,        # background_gradient_style: linear, radial
        gradient_angle: int = None,            # background_gradient_custom_angle
        background_image: str = None,          # %bgi
        background_repeat: str = None,         # %bgp
        background_color_if_empty_image: str = None,  # background_color_if_empty_image
        crop_responsive: bool = None,          # crop_responsive
        background_size_cover: bool = None,    # background_size_cover
        center_background: bool = None,        # %cb
        repeat_background_vertical: bool = None,       # %rbv
        repeat_background_horizontal: bool = None,     # %rbh

        # Web Shadow (Box Shadow)
        shadow_style: str = None,              # %bs: outset, inset, none
        shadow_h: int = None,                  # %bh
        shadow_v: int = None,                  # %bv
        shadow_blur: int = None,               # %bsb
        shadow_spread: int = None,             # %bsp
        # Typography / Icon
        font_color: str = None,                # %fc
        placeholder_color: str = None,         # %pc

        icon_color: str = None,                # %ic
        icon_size: int = None,                 # icon_size
        font_size: int = None,                 # %fs
        font_family: str = None,               # font_family
        font_weight: str = None,               # font_weight
        font_face: str = None,                 # font_face
        alignment: str = None,                 # %fa
        bold: bool = None,                     # %b
        italic: bool = None,                   # %i
        underline: bool = None,                # %u
        word_spacing: float = None,            # %ws
        line_height: float = None,             # %lh
        letter_spacing: float = None,          # %ls
        text_shadow: bool = None,              # %tes
        text_shadow_h: int = None,             # %tsh
        text_shadow_v: int = None,             # %tsv
        text_shadow_blur: int = None,          # %tsb
        text_shadow_color: str = None,         # %tsc
        tag: str = None,
        # Layout
        padding_top: int = None,               # padding_top
        padding_bottom: int = None,            # padding_bottom
        padding_left: int = None,              # padding_left
        padding_right: int = None,             # padding_right
        gap: int = None,                       # button_gap
        # Border
        border_color: str = None,              # %bc (shared)
        border_width: int = None,              # %bw (shared)
        border_radius: int = None,             # %br (shared)
        border_style: str = None,              # %bos (shared)

        # Independent Borders
        border_type: str = None,               # four_border_style: true (shared) / false (independent)
        border_style_top: str = None,          # border_style_top
        border_style_bottom: str = None,       # border_style_bottom
        border_style_left: str = None,         # border_style_left
        border_style_right: str = None,        # border_style_right
        border_color_top: str = None,          # border_color_top
        border_color_bottom: str = None,       # border_color_bottom
        border_color_left: str = None,         # border_color_left
        border_color_right: str = None,        # border_color_right
        border_width_top: int = None,          # border_width_top
        border_width_bottom: int = None,       # border_width_bottom
        border_width_left: int = None,         # border_width_left
        border_width_right: int = None,        # border_width_right

        # Independent Radius
        radius_top_left: int = None,           # border_roundness_top
        radius_top_right: int = None,          # border_roundness_right
        radius_bottom_right: int = None,       # border_roundness_bottom
        radius_bottom_left: int = None,        # border_roundness_left

        shadow_color: str = None,              # %bc (for shadow context) or %sc? Let's try %bc based on context.

        # DateInput Specific
        date_format: str = None,               # date_format
        custom_format: str = None,             # custom_format
        # SliderInput style specific
        range_type: str = None,                # range_type (simple/range)
        slider_background_color: str = None,   # background_color (slider track)
        handle_color: str = None,              # handle_color
        range_area_color: str = None,          # range_area_color

        # Transitions
        transitions: Dict[str, Dict[str, Any]] = None, # property -> {duration, fn}
        center_text_vertically: bool = None,   # %vc
        inject_defaults: bool = True,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Generates a list of SetStyleData payloads to update a style.
        """
        changes = []

        def add_change(key: str, value: Any):
            if value is not None:

                changes.append({
                    "path": ["styles", style_id, "%p", key],
                    "body": value
                })

        # Handle aliases
        if "background_color" in kwargs:
            val = kwargs.pop("background_color")
            if bg_color is None:
                bg_color = val
        if "slider_background_color" in kwargs:
            val = kwargs.pop("slider_background_color")
            if slider_background_color is None:
                slider_background_color = val

        # RepeatingGroup separator aliases.
        separator_style = kwargs.pop("separator_style", None)
        separator_width = kwargs.pop("separator_width", None)
        separator_color = kwargs.pop("separator_color", None)

        # Sizing / Layout
        fit_width = kwargs.pop("fit_width", None)
        fit_height = kwargs.pop("fit_height", None)
        min_width_css = kwargs.pop("min_width_css", None)
        max_width_css = kwargs.pop("max_width_css", None)
        min_height_css = kwargs.pop("min_height_css", None)
        max_height_css = kwargs.pop("max_height_css", None)
        single_width = kwargs.pop("single_width", None)
        single_height = kwargs.pop("single_height", None)

        container_layout = kwargs.pop("container_layout", None)
        use_gap = kwargs.pop("use_gap", None)
        row_gap = kwargs.pop("row_gap", None)
        col_gap = kwargs.pop("column_gap", None)
        nonant_alignment = kwargs.pop("nonant_alignment", None)

        if bg_color and background_style is None and inject_defaults:
            background_style = "bgcolor"

        add_change("%bas", background_style)
        add_change("%bgc", bg_color)
        add_change("%bgf", gradient_start_color)
        add_change("%bgt", gradient_end_color)
        resolved_gradient_style = gradient_style if gradient_style is not None else gradient_direction
        add_change("%bga", gradient_angle)
        add_change("%bgd", resolved_gradient_style)
        if gradient_direction in {"top", "right", "bottom", "left", "custom"}:
            add_change("%b4", gradient_direction)
        add_change("%bgi", background_image)
        add_change("%bgp", background_repeat)
        add_change("background_color_if_empty_image", background_color_if_empty_image)
        if crop_responsive is not None:
            add_change("crop_responsive", bool(crop_responsive))
        if background_size_cover is not None:
            add_change("background_size_cover", bool(background_size_cover))
        if center_background is not None:
            add_change("%cb", bool(center_background))
        if repeat_background_vertical is not None:
            add_change("%rbv", bool(repeat_background_vertical))
        if repeat_background_horizontal is not None:
            add_change("%rbh", bool(repeat_background_horizontal))
        add_change("%ss", separator_style)
        add_change("%sw", separator_width)
        add_change("%sc", separator_color)

        # Layout additions
        add_change("container_layout", container_layout)
        add_change("fit_width", fit_width)
        add_change("fit_height", fit_height)
        add_change("min_width_css", min_width_css)
        add_change("max_width_css", max_width_css)
        add_change("min_height_css", min_height_css)
        add_change("max_height_css", max_height_css)
        add_change("single_width", single_width)
        add_change("single_height", single_height)
        add_change("use_gap", use_gap)
        add_change("row_gap", row_gap)
        add_change("column_gap", col_gap)
        add_change("nonant_alignment", nonant_alignment)

        add_change("background_gradient_mid", gradient_mid_color)
        add_change("background_gradient_style", resolved_gradient_style)
        add_change("background_gradient_custom_angle", gradient_angle)

        # DateInput
        add_change("date_format", date_format)
        add_change("custom_format", custom_format)
        # SliderInput style-specific
        if range_type is not None:
            add_change("range_type", str(range_type).strip().lower())
        add_change("background_color", slider_background_color)
        add_change("handle_color", handle_color)
        add_change("range_area_color", range_area_color)

        # FileInput
        add_change("%vc", center_text_vertically)

        # Web Shadow
        if shadow_style and shadow_style != "none":
            add_change("%bs", shadow_style)
            add_change("%bh", shadow_h)
            add_change("%bv", shadow_v)
            add_change("%bsb", shadow_blur)
            add_change("%bsp", shadow_spread)
            if inject_defaults:
                add_change("boxshadow_enable", True)
        elif shadow_style == "none":
            add_change("%bs", "none")
            if inject_defaults:
                add_change("boxshadow_enable", False)
        elif shadow_spread is not None:
            # Preserve spread updates even when style itself isn't changed.
            add_change("%bsp", shadow_spread)

        # Typography / Icon Logic
        if font_color:
            add_change("%fc", font_color)

        if placeholder_color:
            add_change("placeholder_color", placeholder_color)

        if font_color:
             # If icon_color is NOT explicitly provided, sync it with font_color
            if icon_color is None:
                add_change("%ic", font_color)

        if icon_color:
             add_change("%ic", icon_color)

        if icon_size is not None:
             add_change("icon_size", icon_size)

        add_change("%fs", font_size)
        add_change("font_face", font_face)
        add_change("font_family", font_family)
        add_change("font_weight", font_weight)
        add_change("%fa", alignment)
        add_change("%b", bold)
        add_change("%i", italic)
        add_change("%u", underline)
        add_change("%ws", word_spacing)
        add_change("%lh", line_height)
        if letter_spacing is not None:
            add_change("%ls", float(letter_spacing))
        add_change("%tes", text_shadow)
        add_change("%tsh", text_shadow_h)
        add_change("%tsv", text_shadow_v)
        add_change("%tsb", text_shadow_blur)
        add_change("%tsc", text_shadow_color)
        add_change("tag_type", tag)

        # Layout
        add_change("padding_top", padding_top)
        add_change("padding_bottom", padding_bottom)
        add_change("padding_left", padding_left)
        add_change("padding_right", padding_right)
        add_change("button_gap", gap)

        # Border Logic
        add_change("%bc", border_color)
        add_change("%bw", border_width)
        add_change("%br", border_radius)
        add_change("%bos", border_style)

        # Independent Border Logic
        if border_type == "independent":
             add_change("four_border_style", True)
        elif border_type == "shared":
             add_change("four_border_style", False)

        add_change("border_style_top", border_style_top)
        add_change("border_style_bottom", border_style_bottom)
        add_change("border_style_left", border_style_left)
        add_change("border_style_right", border_style_right)

        add_change("border_color_top", border_color_top)
        add_change("border_color_bottom", border_color_bottom)
        add_change("border_color_left", border_color_left)
        add_change("border_color_right", border_color_right)

        add_change("border_width_top", border_width_top)
        add_change("border_width_bottom", border_width_bottom)
        add_change("border_width_left", border_width_left)
        add_change("border_width_right", border_width_right)

        add_change("border_roundness_top", radius_top_left)
        add_change("border_roundness_right", radius_top_right)
        add_change("border_roundness_bottom", radius_bottom_right)
        add_change("border_roundness_left", radius_bottom_left)

        # Handle any remaining kwargs as literal style properties
        for key, value in kwargs.items():
            add_change(key, value)

        if shadow_color:
            add_change("%bsc", shadow_color) # Correct Box Shadow Color key is %bsc, not %bc

        # Note: If shadow_style is set, ensure boxshadow_enable is None (or False?)
        # Actually, "Web shadow" (%bs) and "Mobile shadow" (boxshadow_enable) might coexist or conflict.
        # Usually web shadow overrides.



        # Transitions Logic
        if transitions:
            # Map friendly names to keys
            prop_map = {
                "background_style": "%bas",
                "background_color": "%bas",
                "bg_color": "%bas",
                "font_color": "%fc",
                "icon_color": "%ic",
                "border_color": "%bc",
                "border_radius": "%br",
                "border_width": "%bw",
                "shadow_style": "%bs",
                "box_shadow": "%bs",
                "opacity": "opacity",
                "width": "%w",
                "height": "%h"
            }

            for prop, settings in transitions.items():
                bubble_key = prop_map.get(prop, prop) # Fallback to prop if not in map
                changes.append({
                    "intent": "AddTransition",
                    "path": ["styles", style_id, "transitions", bubble_key],
                    "body": settings
                })

        return changes

    def apply_theme(
        self,
        style_id: str,
        theme: Dict[str, Any],
        element_type: str = "Button"
    ) -> List[Dict[str, Any]]:
        """
        Applies a composite theme (base + states) to a style.
        theme example: {
            "base": {"bg_color": "#fff", "font_size": 16},
            "hover": {"bg_color": "#eee"},
            "pressed": {"bg_color": "#ddd"}
        }
        """
        all_changes = []

        # 1. Apply base styles
        base_styles = theme.get("base", {})
        if base_styles:
            all_changes.extend(self.update_style(style_id=style_id, **base_styles))

        # 2. Apply states (hover, pressed, focus, disabled)
        state_map = {
            "hover": "hover",
            "pressed": "pressed",
            "focus": "focus",
            "focused": "focus",
            "disabled": "not_clickable",
            "active": "pressed"
        }

        for state_key, state_props in theme.items():
            if state_key == "base" or not state_props:
                continue

            condition_type = state_map.get(state_key.lower())
            if not condition_type:
                continue

            # Generate a consistent condition ID for the state
            condition_type_suffix = condition_type.replace("_", "")[:4]
            condition_id = f"st{condition_type_suffix}"

            all_changes.extend(self.add_style_condition(
                style_id=style_id,
                condition_id=condition_id,
                condition_type=condition_type,
                properties=state_props
            ))

        # 3. Automatic Transitions Rule
        # If any state change affects transitionable properties, add them to the base style
        transitionable_props = {
            "%bgc": "background_color",
            "%fc": "font_color",
            "%ic": "icon_color",
            "%bc": "border_color",
            "%br": "border_radius",
            "%bs": "shadow_style",
            "opacity": "opacity"
        }

        needed_transitions = {}
        for state_key, state_props in theme.items():
            if state_key == "base": continue
            for prop in state_props.keys():
                # Map prop to bubble key
                bkey = prop if prop.startswith("%") else None
                if not bkey:
                    # Try to find in reverse mapping or common names
                    for bk, pk in transitionable_props.items():
                        if prop == pk or prop == bk:
                            bkey = bk
                            break

                if bkey in transitionable_props:
                    needed_transitions[bkey] = {"duration": 200, "fn": "ease"}

        if needed_transitions:
            logger.info(f"Auto-injecting {len(needed_transitions)} transitions for style {style_id}")
            all_changes.extend(self.update_style(style_id=style_id, transitions=needed_transitions))

        return all_changes

    @staticmethod
    def _build_condition_node(ctype: str) -> Dict:
        mapping = {
            "hover": "is_hovered",
            "focus": "is_focused",
            "pressed": "is_pressed",
            "isnt_valid": "isnt_valid",
            "not_clickable": "isnt_clickable",
            "visible": "is_visible",
            "not_visible": "isnt_visible",
            "hidden": "isnt_visible",
            "invalid": "isnt_valid",
            "disabled": "isnt_clickable"
        }
        nm = mapping.get(ctype.lower(), ctype)
        return {
            "%x": "Message",
            "%nm": nm,
            "is_slidable": False
        }

    @staticmethod
    def _build_complex_condition(condition_chain: List[Tuple[str, Optional[str]]]) -> Dict:
        """
        Builds a recursive condition tree from a chain of (type, operator) tuples.
        operator can be 'and_', 'or_', or None.

        Example: [('isnt_valid', 'and_'), ('is_hovered', 'or_'), ('is_focused', None)]
        Result: isnt_valid -> AND -> is_hovered -> OR -> is_focused
        """
        if not condition_chain:
            return {}

        # 1. Create the root condition node
        root_type, root_op = condition_chain[0]
        root = {
            "%x": "ThisElement",
            "%n": StyleBuilder._build_condition_node(root_type),
            "is_slidable": False
        }

        current_cond_node = root["%n"] # The condition message node (e.g. is_hovered)

        # 2. Iterate remaining or link operators
        # The first item has an operator that links to the SECOND item.
        # We process item i's operator, which wraps item i+1.

        for i in range(len(condition_chain) - 1):
            current_type, op = condition_chain[i]
            next_type, next_op = condition_chain[i+1]

            # Use provided operator or default to or_ if missing (fallback)
            clean_op = op if op in ["and_", "or_"] else "or_"

            # Create operator node
            operator_node = {
                "%x": "Message",
                "%nm": clean_op,
                "is_slidable": False,
                "%a": { # The argument for the operator is the NEXT condition
                    "%x": "ThisElement",
                    "%n": StyleBuilder._build_condition_node(next_type),
                    "is_slidable": False
                }
            }

            # Link current condition to this operator
            current_cond_node["%n"] = operator_node

            # Advance current node to the NEXT condition message node
            current_cond_node = operator_node["%a"]["%n"]

        return root

    @staticmethod
    def add_style_condition(
        style_id: str,
        condition_id: str, # e.g. bTUud0
        condition_type: Union[str, List[str], List[Tuple[str, str]]], # "hover", ["hover", "focus"], [('hover', 'and_'), ('focus', None)]
        properties: Dict[str, Any],
        is_new: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Generates a SetStyleStateCondition payload.
        """
        # Normalize input to list of (type, operator)
        chain = []
        if isinstance(condition_type, str):
            # Legacy/Simple: "hover,focus" -> [('hover', 'or_'), ('focus', None)]
            parts = [c.strip() for c in condition_type.split(",")]
            for i, p in enumerate(parts):
                op = "or_" if i < len(parts) - 1 else None
                chain.append((p, op))
        elif isinstance(condition_type, list):
            if not condition_type:
                chain = []
            elif isinstance(condition_type[0], tuple):
                # Already (type, op) tuples
                chain = condition_type
            else:
                # List of strings (implicit OR)
                for i, p in enumerate(condition_type):
                    op = "or_" if i < len(condition_type) - 1 else None
                    chain.append((p, op))

        # 1. Build the Condition Definition (%c)
        cond_def = StyleBuilder._build_complex_condition(chain)

        # 2. Build the Properties (%p)
        # Use update_style logic to resolve keys
        temp_builder = StyleBuilder() # Create temporary builder

        # Handle padding shortcut in properties dict (copy to avoid mutating input if needed, but here it's fine)
        # Also need to ensure we don't pass keys that update_style doesn't accept

        update_args = {"style_id": style_id}
        update_args.update(properties)

        # Manually handle padding shortcut if present in properties
        if 'padding' in update_args:
            val = update_args.pop('padding')
            if val is not None:
                if 'padding_top' not in update_args: update_args['padding_top'] = val
                if 'padding_bottom' not in update_args: update_args['padding_bottom'] = val
                if 'padding_left' not in update_args: update_args['padding_left'] = val
                if 'padding_right' not in update_args: update_args['padding_right'] = val

        changes = temp_builder.update_style(inject_defaults=False, **update_args)

        results = []
        if is_new:
            results.append({
                "intent": "NewStyleState",
                "path": ["styles", style_id, "%s", condition_id],
                "body": {
                    "%x": "State",
                    "%c": None,
                    "%p": None
                }
            })

        # Match editor traffic: initialize the condition node, then set the full expression.
        results.append({
            "intent": "SetStyleStateCondition",
            "path": ["styles", style_id, "%s", condition_id, "%c"],
            "body": {
                "%x": "ThisElement",
                "%p": None,
                "%n": None,
                "is_slidable": False
            }
        })

        # Always update the condition trigger to ensure fidelity
        results.append({
            "intent": "SetStyleStateCondition",
            "path": ["styles", style_id, "%s", condition_id, "%c"],
            "body": cond_def
        })

        # Property application
        for change in changes:
             path = change.get("path", [])
             body = change.get("body")
             # Most style properties are under %p
             if len(path) >= 4 and path[2] == "%p":
                 key = path[3]
                 # Bubble often requires an "Empty" intent to "enable" a property override in a condition
                 results.append({
                     "intent": "SetStyleStateData",
                     "path": ["styles", style_id, "%s", condition_id, "%p", key],
                     "body": {"%x": "Empty"}
                 })
                 results.append({
                     "intent": "SetStyleStateData",
                     "path": ["styles", style_id, "%s", condition_id, "%p", key],
                     "body": body
                 })

        return results

    @staticmethod
    def reorder_states(style_id: str, ordered_states_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generates payloads to reorder style states.

        Bubble consistently accepts `SetStyleData` for style tree updates.
        `ReorderState` is kept as a compatibility fallback because some older
        internal flows referenced it, but editor traffic is typically
        `SetStyleData` on `styles.<style_id>.%s`.

        Args:
            style_id: The Bubble ID of the style
            ordered_states_map: A dictionary mapping index strings ("0", "1", etc.) to full state objects.
        """
        return [
            {
                "intent": "SetStyleData",
                "path": ["styles", style_id, "%s"],
                "body": ordered_states_map
            },
            {
                "intent": "ReorderState",
                "path": ["styles", style_id, "%s"],
                "body": ordered_states_map
            },
        ]



# ==========================================
# CORE: PAYLOAD BUILDER
# ==========================================

class PayloadBuilder:
    """Construtor de payloads completos"""

    # Comprehensive Property Mapping (Modular -> Wire)
    PROP_MAPPING = {
        "element_id": "%ei",
        "height": "%h", "width": "%w", "left": "%l", "top": "%t",
        "zindex": "%z", "min_width": "min_width_css", "min_height": "min_height_css",
        "visible_when_collapsed": "%vc", "is_visible": "%iv",
        "collapse_when_hidden": "collapse_when_hidden",
        "background_style": "%bas", "bgcolor": "%bgc", "background_color": "%bgc",
        "background_image": "%bgi",
        "gradient_from_color": "%bgf", "background_gradient_from": "%bgf",
        "gradient_to_color": "%bgt", "background_gradient_to": "%bgt",
        "border_style": "%bS", "border_width": "%bw", "border_color": "%bc",
        "border_radius": "%br", "border_roundness": "%br",
        "text": "%3", "font_size": "%fs", "font_color": "%fc", "color": "%fc",
        "font_alignment": "%fa", "horiz_alignment": "horiz_alignment",
        "container_layout": "container_layout", "vert_alignment": "vert_alignment",
        "vertical_centering": "%vc2", "row_gap": "row_gap", "column_gap": "column_gap",
        "padding_top": "padding_top", "padding_bottom": "padding_bottom",
        "padding_left": "padding_left", "padding_right": "padding_right",
        "fit_height": "fit_height", "fit_width": "fit_width",
        "placeholder": "placeholder", "initial_content": "initial_content", "placeholder_color": "placeholder_color",
        "icon": "%9i", "icon_color": "%ic",
        "custom_state": "custom_state", "display": "%nm", "value": "%v", "default_val": "%dn",
        "default_value": "%v",
        "name": "%nm", "type": "%x", "data_source": "%ds", "entries": "%e",
        "actions": "actions", "type_of_content": "%gt", "group_type": "%gt",
        "rows": "%rs"
    }

    STRUCT_MAPPING = {
        "type": "%x", "condition": "%c", "properties": "%p", "next": "%n",
        "name": "%nm", "entries": "%e", "states": "%s", "custom_states": "%s",
        "actions": "actions", "elements": "%el", "workflows": "%wf", "default_name": "%dn",
        "style": "%s1", "arguments": "%a", "args": "%a",
        "element_id": "%ei",
        "type_of_content": "%gt", "group_type": "%gt", "data_source": "%ds"
    }

    def __init__(self, appname: str = "synthetic-page", app_version: str = "test", metadata: Dict[str, str] = None):
        self.appname = appname
        self.app_version = app_version
        self.id_gen = BubbleIDGenerator()
        self.session_id = self.id_gen.session_id()
        self.changes = []
        self.metadata = metadata or {}

    def collect_ids(self, obj: Any, id_mapping: Dict[str, str]):
        """Recursively collect IDs from a modularized object."""
        if isinstance(obj, dict):
            if "id" in obj:
                old_id = obj["id"]
                if old_id not in id_mapping and isinstance(old_id, str) and len(old_id) >= 5:
                    id_mapping[old_id] = self.id_gen.element_id()
            if "param_id" in obj:
                old_pid = obj["param_id"]
                if old_pid not in id_mapping and isinstance(old_pid, str):
                    id_mapping[old_pid] = self.id_gen.element_id()
            for k, v in obj.items():
                if k in ["elements", "workflows"] and isinstance(v, dict):
                     for key, child_def in v.items():
                         if key not in id_mapping and isinstance(key, str) and len(key) >= 5:
                             child_id = child_def.get("id") if isinstance(child_def, dict) else None
                             if child_id and child_id in id_mapping:
                                 id_mapping[key] = id_mapping[child_id]
                             elif child_id and child_id not in id_mapping:
                                 new_id_for_both = self.id_gen.element_id()
                                 id_mapping[key] = new_id_for_both
                                 id_mapping[child_id] = new_id_for_both
                             else:
                                 id_mapping[key] = self.id_gen.element_id()
                self.collect_ids(v, id_mapping)
        elif isinstance(obj, list):
            for item in obj:
                self.collect_ids(item, id_mapping)

    def _resolve_type(self, type_name: str) -> str:
        """Resolve a user-friendly type name to its internal Bubble ID using metadata."""
        if not self.metadata:
            return type_name

        # 1. Direct lookup
        if type_name in self.metadata:
            return self.metadata[type_name]

        # 2. Case-insensitive lookup
        type_lower = type_name.lower()
        for key, val in self.metadata.items():
            if key.lower() == type_lower:
                return val

        # 3. Fallback: maybe it's already an internal ID?
        return type_name

    def convert_to_api_format(self, modular_data: Any, is_properties: bool = False, current_path: List[str] = None, id_mapping: Dict[str, str] = None, name_mapping: Dict[str, str] = None, compressed: bool = True, is_reusable: bool = False) -> Any:
        """
        Recursively converts modular JSON structure to Bubble's internal wire format.
        ...
        Args:
            ...
            is_reusable: Whether we are converting a reusable element (CustomDefinition).
        """
        if id_mapping is None:
            id_mapping = {}
        if name_mapping is None:
            name_mapping = {}

        if isinstance(modular_data, str):
            # Global ID remapping
            remapped = id_mapping.get(modular_data, modular_data)

            # SPECIAL: Reusable State Name Mapping (Sync with display name if needed)
            if is_reusable and isinstance(remapped, str) and remapped.startswith("custom."):
                if remapped == "custom.settings_nav_":
                    remapped = "custom.profile_nav_"

            if remapped.startswith("param_"):
                potential_id = remapped[6:]
                if potential_id in id_mapping:
                    return f"param_{id_mapping[potential_id]}"

            replaced_data = remapped
            # 1. Deep ID Replacement (Surgical for alphanumeric strings >= 5)
            if len(replaced_data) > 5 and not replaced_data.startswith("param_"):
                for old_id, new_id in sorted(id_mapping.items(), key=lambda x: len(x[0]), reverse=True):
                    if old_id in replaced_data:
                        replaced_data = replaced_data.replace(old_id, new_id)

            # 2. SAFE Deep Name Replacement (Token-based)
            # avoids replacing "admin-profile" in "built-in-mobile-landing" or other composite strings
            for old_name, new_name in name_mapping.items():
                if old_name in replaced_data:
                    # Replace only if it's a discrete token or part of a Bubble expression reference
                    # We look for word boundaries but allow for hyphens/dots commonly found in Bubble expressions
                    pattern = r'(?<![a-zA-Z0-9_\-])' + re.escape(old_name) + r'(?![a-zA-Z0-9_\-])'
                    replaced_data = re.sub(pattern, new_name, replaced_data)

            return replaced_data

        if isinstance(modular_data, dict):
            new_dict = {}
            for k, v in modular_data.items():
                api_key = k

                # 1. Determine the API Key
                if compressed:
                    if k == "custom_states" or k == "states":
                        # Pages use %c for conditionals, %s for root states
                        # Reusables use %s for BOTH.
                        if is_reusable:
                            api_key = "%s"
                        else:
                            api_key = "%s" if k == "custom_states" else "%c"
                    else:
                        api_key = self.STRUCT_MAPPING.get(k, k)
                        if is_properties:
                            api_key = self.PROP_MAPPING.get(k, api_key)

                # 2. Logic for State Lists (Conditionals or Declarations)
                if api_key in ("%s", "%c", "states", "custom_states") and isinstance(v, dict):
                    remapped_v = {}
                    # If modular key is 'states', it's an element conditional (numeric keys required)
                    is_element_conditional = (k == "states")

                    for i, (sid, sdef) in enumerate(v.items()):
                        target_sid = sid if not is_element_conditional else str(i)

                        if isinstance(sdef, dict):
                            state_remapped = {}
                            # Root State Type Inference (only for declarations)
                            current_type = None
                            if api_key in ("%s", "custom_states"):
                                current_type = sdef.get("type")
                                if not current_type and "value" in sdef:
                                    val = sdef["value"]
                                    if isinstance(val, str) and ("." in val or "x" in val):
                                        current_type = val
                                    else:
                                        current_type = "text"

                            for sk, sv in sdef.items():
                                sub_api_key = sk
                                if compressed:
                                    if sk == "type":
                                        sub_api_key = "%gt" if (api_key in ("%s", "custom_states") and not is_element_conditional) else "%x"
                                    elif sk == "name":
                                        sub_api_key = "%nm"
                                    elif sk in ("condition", "properties"):
                                        sub_api_key = self.STRUCT_MAPPING.get(sk, sk)
                                    else:
                                        sub_api_key = self.PROP_MAPPING.get(sk, sk)
                                else:
                                    # In uncompressed mode, some keys need specific mapping even if literal
                                    if sk == "type" and api_key in ("%s", "custom_states"):
                                        sub_api_key = "value" # Root state type is often 'value' in modular but 'default_val' in wire?
                                                            # No, usually 'value' is use for the Option Set / Custom Type.
                                        pass

                                # Resolve types for custom states
                                if api_key in ("%s", "custom_states") and sub_api_key in ("%gt", "%v", "value", "default_val") and isinstance(sv, str):
                                    sv = self._resolve_type(sv)

                                state_remapped[sub_api_key] = self.convert_to_api_format(
                                    sv,
                                    is_properties=(sub_api_key in ("%p", "properties")),
                                    current_path=current_path,
                                    id_mapping=id_mapping,
                                    name_mapping=name_mapping,
                                    compressed=compressed,
                                    is_reusable=is_reusable
                                )

                            if api_key in ("%s", "custom_states") and (compressed and "%x" not in state_remapped and "%gt" not in state_remapped or not compressed and "value" not in state_remapped) and current_type:
                                if is_element_conditional:
                                    # Element conditionals use %x: State
                                    state_remapped["%x"] = "State"
                                else:
                                    # Root state declarations use %gt for type
                                    type_key = "%gt" if compressed else "value"
                                    state_remapped[type_key] = self._resolve_type(current_type)

                            remapped_v[target_sid] = state_remapped
                        else:
                            remapped_v[target_sid] = self.convert_to_api_format(
                                sdef,
                                is_properties=True,
                                current_path=current_path,
                                id_mapping=id_mapping,
                                name_mapping=name_mapping,
                                compressed=compressed
                            )
                    new_dict[api_key] = remapped_v
                    continue

                # 3. Handle specific property resolution
                if (api_key in ("%gt", "%v", "%s", "type_of_content", "group_type", "custom_state")) and isinstance(v, str):
                    v = self._resolve_type(v)
                    # For uncompressed reusables, keep 'custom.' prefix if it's there

                # 4. Handle structural nesting
                sub_path = current_path[:] if current_path else []
                if api_key in ("%p", "properties"):
                    sub_path.append(api_key)
                    new_dict[api_key] = self.convert_to_api_format(v, is_properties=True, current_path=sub_path, id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=is_reusable)
                elif api_key in ("%el", "elements"):
                    sub_path.append(api_key)
                    remapped_el = {}
                    for old_key, child_def in v.items():
                        new_key = id_mapping.get(old_key, old_key)
                        remapped_el[new_key] = self.convert_to_api_format(child_def, is_properties=False, current_path=sub_path + [new_key], id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=is_reusable)
                    new_dict[api_key] = remapped_el
                elif api_key in ("%wf", "workflows"):
                    sub_path.append(api_key)
                    remapped_wf = {}
                    for old_key, wf_def in v.items():
                        new_key = id_mapping.get(old_key, old_key)
                        remapped_wf[new_key] = self.convert_to_api_format(wf_def, is_properties=False, current_path=sub_path + [new_key], id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=is_reusable)
                    new_dict[api_key] = remapped_wf
                else:
                    new_dict[api_key] = self.convert_to_api_format(v, is_properties=is_properties, current_path=sub_path, id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=is_reusable)
            # SPECIAL: Expression Header Defaulting (%p: null, %n: null)
            # Typed objects (elements, expression parts) must have these slots even if empty
            if "%x" in new_dict and not is_properties:
                xtype = new_dict["%x"]
                if xtype == "Message":
                    # Message nodes ONLY add nulls if they don't have a link
                    # If it has %n, it's a path part -> no %p: null
                    # If it has %a, it's a function -> HAS %p: null and %n: null
                    if "%a" in new_dict:
                        if "%p" not in new_dict: new_dict["%p"] = None
                        if "%n" not in new_dict: new_dict["%n"] = None
                    # REMOVED: elif "%n" not in new_dict branch that added nulls to terminal nodes
                elif xtype in ("ElementParent", "Breakpoint", "PageData"):
                    if "%p" not in new_dict: new_dict["%p"] = None
                    if "%n" not in new_dict: new_dict["%n"] = None
                elif xtype == "GetElement":
                    # GetElement usually has %p and %n already, but verify
                    pass
                elif xtype == "State":
                    # State nodes (conditional values)
                    if "%p" not in new_dict: new_dict["%p"] = None
                    if "%n" not in new_dict: new_dict["%n"] = None

            return new_dict

        if isinstance(modular_data, list):
            return [self.convert_to_api_format(item, is_properties=is_properties, id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=is_reusable) for item in modular_data]

        return modular_data

    def add_custom_state(
        self,
        element_id: str,
        state_name: str,
        state_def: Dict[str, Any],
        compressed: bool = True
    ) -> 'PayloadBuilder':
        """
        Adds a custom state to an existing element.
        Based on captured traffic (Intent: CreateCustomState).
        """
        # Bubble uses a key for the state, often the name lowercase with underscores + trailing _
        state_key = state_name.lower().replace(" ", "_")
        if not state_key.endswith("_"):
            state_key += "_"

        path = ["%ed", element_id, "custom_states", state_key]

        # Body format from capture:
        # { "%d": "Display Name", "%v": "type", "make_static": true, "rank": 0 }
        body = {
            "%d": state_name,
            "%v": state_def.get("type", "text"),
            "make_static": True,
            "rank": state_def.get("rank", 0)
        }

        # Optional: default value
        if "default_val" in state_def and state_def["default_val"] is not None:
             body["default_val"] = state_def["default_val"]

        self.add_change("CreateCustomState", path, body)
        return self

    def add_element_conditional(
        self,
        element_id: str,
        condition_idx: int,
        condition_expr: Dict[str, Any],
        properties: Dict[str, Any],
        child_id: Optional[str] = None,
        id_mapping: Optional[Dict[str, str]] = None,
        name_mapping: Optional[Dict[str, str]] = None,
        compressed: bool = True
    ) -> 'PayloadBuilder':
        """
        Adds a conditional state to an element.
        """
        if child_id:
            path = ["%ed", element_id, "%el", child_id, "%c"]
        else:
            path = ["%ed", element_id, "%c"]

        wire_condition = self.convert_to_api_format(condition_expr, id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=True)
        wire_properties = self.convert_to_api_format(properties, is_properties=True, id_mapping=id_mapping, name_mapping=name_mapping, compressed=compressed, is_reusable=True)

        # Element conditionals are generally "State" type with indexed keys
        body = {
            str(condition_idx): {
                "%x": "State",
                "%c": wire_condition,
                "%p": wire_properties
            }
        }

        self.add_change("NewState", path, body)
        return self

    def add_create_element(
        self,
        parent_path: List[str],
        element_body: Dict[str, Any]
    ) -> 'PayloadBuilder':
        """Adiciona uma mudança de CreateElement"""
        valid, msg = PathBuilder.validate_create_path(parent_path)
        if not valid:
            raise ValueError(f"Path inválido: {msg}")

        change = {
            "intent": {
                "name": "CreateElement",
                "id": random.randint(2, 999),
                "source_appname": ""
            },
            "path_array": parent_path,
            "body": element_body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)
        return self

    def add_clone_reusable(
        self,
        source_id: str,
        new_id: str,
        new_name: str,
        source_def: Dict[str, Any]
    ) -> Tuple['PayloadBuilder', Dict[str, str]]:
        """
        Clones a reusable element (CustomDefinition) from a modularized source.
        Adopts the high-fidelity conversion logic with shared class methods.
        """
        # 1. Prepare ID and Name mapping
        id_mapping = {source_id: new_id}

        # Original name for deep string replacement in expressions
        original_name = source_def.get("name") or source_def.get("%nm") or source_def.get("nm")
        name_mapping = {original_name: new_name} if original_name else {}

        # Aggressive name remapping: Scan for any previous clones in the entire source_def
        def collect_clone_names(obj):
            if isinstance(obj, str):
                # Look for CLONE_... patterns
                matches = re.findall(r'CLONE_[a-zA-Z0-9_\-]+_v\d+', obj)
                for m in matches:
                    if m != new_name:
                        name_mapping[m] = new_name
            elif isinstance(obj, dict):
                for v in obj.values(): collect_clone_names(v)
            elif isinstance(obj, list):
                for item in obj: collect_clone_names(item)

        collect_clone_names(source_def)

        # Force the internal root ID to map to the new_id as well
        internal_root_id = source_def.get("id")
        if internal_root_id:
            id_mapping[internal_root_id] = new_id

        # 2. Populate ID mapping recursively
        self.collect_ids(source_def, id_mapping)

        # 3. Comprehensive path and body conversion (COMPRESSED for creation)
        # Reusables live in the %ed (Element Definition) collection
        root_path = ["%ed", new_id]

        wire_body = self.convert_to_api_format(
            source_def,
            id_mapping=id_mapping,
            name_mapping=name_mapping,
            compressed=True,
            is_reusable=True
        )

        # Update name and basic ID in wire body
        wire_body["%nm"] = new_name
        wire_body["id"] = new_id
        wire_body["%x"] = "CustomDefinition"

        # Ensure Type of Content is also at the root for CustomDefinition if present in properties
        if "%p" in wire_body and "%gt" in wire_body["%p"]:
            wire_body["%gt"] = wire_body["%p"]["%gt"]

        # 4. Register structural sub-paths for editor tracking (issues_sub)
        self.add_update_index(["_index", "id_to_path", new_id], ".".join(root_path))

        # Recursively register all elements, workflows, and ACTIONS for issues_list/issues_sub
        all_child_ids = []
        def register_recursive(obj_id, obj_def, path):
            if not isinstance(obj_def, dict):
                return

            subs = []

            # Elements
            if "%el" in obj_def and isinstance(obj_def["%el"], dict):
                for el_id, el_val in obj_def["%el"].items():
                    el_path = path + ["%el", el_id]
                    self.add_update_index(["_index", "id_to_path", el_id], ".".join(el_path))
                    subs.append(el_id)
                    all_child_ids.append(el_id)
                    register_recursive(el_id, el_val, el_path)

            # Workflows
            if "%wf" in obj_def and isinstance(obj_def["%wf"], dict):
                for wf_id, wf_val in obj_def["%wf"].items():
                    wf_path = path + ["%wf", wf_id]
                    self.add_update_index(["_index", "id_to_path", wf_id], ".".join(wf_path))
                    subs.append(wf_id)
                    all_child_ids.append(wf_id)

                    # Actions in workflows
                    action_subs = []
                    if "actions" in wf_val and isinstance(wf_val["actions"], dict):
                        for action_idx, action_def in wf_val["actions"].items():
                            action_id = action_def.get("id")
                            if action_id:
                                action_path = wf_path + ["actions", action_idx]
                                self.add_update_index(["_index", "id_to_path", action_id], ".".join(action_path))
                                action_subs.append(action_id)
                                all_child_ids.append(action_id)

                    if action_subs:
                        self.register_issues_sub(wf_id, action_subs)

            # Element Conditionals
            # Reusables use %s for element conditionals.
            if "%s" in obj_def and isinstance(obj_def["%s"], dict):
                # For reusables, conditionals use NewState intent at path + [%s]
                if path != root_path:
                    self.add_change("NewState", path + ["%s"], obj_def["%s"])

                    # High-fidelity "poke": also send SetData for each condition expression individually
                    for sid, sdef in obj_def["%s"].items():
                        if isinstance(sdef, dict) and "%c" in sdef:
                            self.add_set_data(path + ["%s", sid, "%c"], sdef["%c"])

            if subs:
                self.register_issues_sub(obj_id, subs)

        register_recursive(new_id, wire_body, root_path)

        # 5. Register in Payload (Using CreateElement for the ROOT CustomDefinition)
        # Target path is ["%ed", new_id]
        self.add_create_element(root_path, wire_body)

        # Register issues_list for the root and all children (Using Update index as per working payload)
        self.add_update_index(["_index", "issues_list", new_id], "[]")
        for child_id in set(all_child_ids):
            self.add_update_index(["_index", "issues_list", child_id], "[]")

        return self, id_mapping

        return self, id_mapping


    def add_create_style(
        self,
        style_id: str,
        style_body: Dict[str, Any]
    ) -> 'PayloadBuilder':
        """Adiciona uma mudança de CreateStyle"""
        change = {
            "intent": {
                "name": "CreateStyle",
                "id": random.randint(2, 999),
                "source_appname": ""
            },
            "path_array": ["styles", style_id],
            "body": style_body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)
        return self

    def add_delete_style(
        self,
        style_id: str
    ) -> 'PayloadBuilder':
        """Adds a DeleteStyle change and its corresponding IdToPathFixer entry."""
        # 1. Main DeleteStyle intent
        delete_change = {
            "intent": {
                "name": "DeleteStyle",
                "id": random.randint(200, 9999), # Using wider range for batch safety
                "source_appname": ""
            },
            "path_array": ["styles", style_id],
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }
        self.changes.append(delete_change)

        # 2. IdToPathFixer intent (Crucial for Bubble to actually remove it from index)
        fixer_change = {
            "intent": {
                "name": "IdToPathFixer"
            },
            "path_array": ["_index", "id_to_path", style_id],
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }
        self.changes.append(fixer_change)

        return self

    def register_issues_sub(self, parent_id: str, child_ids: List[str]) -> 'PayloadBuilder':
        """
        Registers a list of child IDs under a parent in the issues_sub index.
        This notifies the Bubble Editor about nested elements and properties.
        """
        self.add_set_data(["_index", "issues_sub", parent_id], child_ids)
        return self


    def add_set_data(
        self,
        path_array: List[str],
        value: Any
    ) -> 'PayloadBuilder':
        """Adiciona uma mudança de SetData"""
        return self.add_change("SetData", path_array, value)

    def add_set_style_data(
        self,
        path_array: List[str],
        value: Any
    ) -> 'PayloadBuilder':
        """Adiciona uma mudança de SetStyleData (específico para propriedades de Estilos)"""
        return self.add_change("SetStyleData", path_array, value)

    def add_intent(self, intent_obj: Dict) -> 'PayloadBuilder':
        """Adds a pre-built intent object (with intent, path, body) to the payload."""
        return self.add_change(
            intent_obj.get("intent", "SetData"),
            intent_obj.get("path", []),
            intent_obj.get("body")
        )

    def add_change(
        self,
        intent_name: str,
        path_array: List[str],
        body: Any
    ) -> 'PayloadBuilder':
        """Generic method to add any change with proper Bubble wrapping."""
        change = {
            "intent": {
                "name": intent_name,
                "id": random.randint(1, 999999),
                "source_appname": ""
            },
            "path_array": path_array,
            "body": body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }
        self.changes.append(change)
        return self

    def add_update_index(self, path_array: List[str], body: Any) -> 'PayloadBuilder':
        """Adiciona Update index.
        Accepts either canonical path arrays or shorthand element-id strings.
        """
        normalized_path = path_array
        # Canonical Bubble traffic uses: ["_index", "id_to_path", "<element_id>"].
        # Some callers pass only "<element_id>" shorthand; normalize it here.
        if isinstance(path_array, str):
            normalized_path = ["_index", "id_to_path", path_array]

        change = {
            "intent": {
                "name": "Update index"
            },
            "path_array": normalized_path,
            "body": body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.id_gen.session_id()
        }

        self.changes.append(change)
        return self

    def add_create_workflow(self, page_id: str, workflow_body: Dict) -> 'PayloadBuilder':
        """
        Adiciona CreateEvent (workflow) CORRIGIDO
        Path: %p3 -> page_id -> %wf -> workflow_id
        """
        workflow_id = workflow_body["id"]
        path_array = ["%p3", page_id, "%wf", workflow_id]

        change = {
            "intent": {
                "name": "CreateEvent",
                "id": random.randint(2, 999),
                "source_appname": ""
            },
            "path_array": path_array,
            "body": workflow_body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)

        # Update index
        # self.add_update_index(workflow_id, f"%p3.{page_id}.%wf.{workflow_id}") # Removed as add_update_index is not defined

        return self

    def add_workflow_action(self, page_id: str, workflow_id: str, action_index: int, action_body: Dict) -> 'PayloadBuilder':
        """Adiciona ação em um workflow"""
        path_array = ["%p3", page_id, "%wf", workflow_id, "actions", str(action_index)]

        change = {
            "intent": {
                "name": "SetData",
                "id": random.randint(1, 999),
                "source_appname": ""
            },
            "path_array": path_array,
            "body": action_body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)

        # Update index para a ação
        # action_id = action_body.get("id")
        # if action_id:
        #     self.add_update_index(action_id, f"%p3.{page_id}.%wf.{workflow_id}.actions.{action_index}") # Removed as add_update_index is not defined

        return self

    def add_create_event(
        self,
        parent_path: List[str],
        event_body: Dict[str, Any]
    ) -> 'PayloadBuilder':
        """Adiciona uma mudança de CreateEvent (Workflow Trigger)"""
        change = {
            "intent": {
                "name": "CreateEvent",
                "id": random.randint(2, 999),
                "source_appname": ""
            },
            "path_array": parent_path,
            "body": event_body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)
        return self

    def add_create_action(
        self,
        parent_path: List[str],
        action_body: Dict[str, Any]
    ) -> 'PayloadBuilder':
        """Adiciona uma mudança de CreateAction (Workflow Step)"""
        change = {
            "intent": {
                "name": "CreateAction",
                "id": random.randint(2, 999),
                "source_appname": ""
            },
            "path_array": parent_path,
            "body": action_body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)
        return self

    def add_change_app_setting(
        self,
        path_array: List[str],
        body: Dict[str, Any]
    ) -> 'PayloadBuilder':
        """
        Add a ChangeAppSetting change for app-level settings (colors, fonts, etc.)

        Args:
            path_array: Path to the setting (e.g., ["settings", "client_safe", "color_tokens"])
            body: The updated settings body
        """
        change = {
            "intent": {
                "name": "ChangeAppSetting",
                "id": random.randint(1, 999),
                "source_appname": ""
            },
            "path_array": path_array,
            "body": body,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": self.session_id
        }

        self.changes.append(change)
        return self

    def add_change_raw(self, change: Dict[str, Any]) -> 'PayloadBuilder':
        """Add a raw change dictionary directly."""
        self.changes.append(change)
        return self


    def build(self) -> Dict[str, Any]:
        """Constrói o payload final"""
        return {
            "v": 1,
            "appname": self.appname,
            "app_version": self.app_version,
            "changes": self.changes
        }

    def to_json(self, indent: int = 2) -> str:
        """Retorna JSON string"""
        return json.dumps(self.build(), indent=indent)

    def to_json(self, indent: int = 2) -> str:
        """Retorna JSON string"""
        return json.dumps(self.build(), indent=indent)

    def save(self, filename: str):
        """Salva em arquivo JSON"""
        with open(filename, 'w') as f:
            json.dump(self.build(), f, indent=2)
        logger.success(f"Payload salvo em {filename}")

    def send_to_webhook(self, url: str = "local://bubble-mcp"):
        """Envia para o webhook do editor"""
        payload = self.build()
        client = WebhookClient(url=url, app_name=self.appname)
        return client.send(payload)



# ==========================================
# CORE: APP MAPPER
# ==========================================


class BubbleAppMapper:
    """Mapeia nomes de elementos para IDs usando o JSON do app"""

    def __init__(self, app_json_path: str = "src/app.bubble", consolelog_json_path: Optional[str] = None):
        self.app_json_path = app_json_path
        self.consolelog_json_path = consolelog_json_path
        self.pages = {} # {page_name: page_id}
        self.elements = {} # {page_name: {element_name: element_id}}
        self._load_map()


    def _load_map(self):
        """Carrega e indexa o JSON do app (Auto-detect format with fallback)"""
        data = None

        # Try primary source
        if self.app_json_path and os.path.exists(self.app_json_path):
            try:
                with open(self.app_json_path, 'r') as f:
                    data = json.load(f)
            except FileNotFoundError:
                pass

        # Fallback to console.log
        if data is None and self.consolelog_json_path and os.path.exists(self.consolelog_json_path):
            try:
                with open(self.consolelog_json_path, 'r') as f:
                    data = json.load(f)
            except FileNotFoundError:
                pass

        if not data:
            logger.warning("No app data found for mapping")
            return

        # Auto-detect format
        if 'pages' in data:
            self._load_native_map(data)
        elif '%p3' in data:
            self._load_legacy_map(data)
        else:
            logger.warning(f"Unknown app format")

    def _load_native_map(self, data: Dict[str, Any]):
        """Carrega formato nativo (app.bubble)"""
        # 1. Map Pages
        for page_id, page_data in data.get('pages', {}).items():
            if not isinstance(page_data, dict):
                continue

            page_name = page_data.get('name')
            if page_name:
                self.pages[page_name] = page_id
                self.elements[page_name] = {}
                self._map_elements_recursive(page_name, page_data.get('elements', {}))

        # 2. Map Reusable Elements (definitions)
        for el_id, el_data in data.get('element_definitions', {}).items():
             if not isinstance(el_data, dict):
                 continue

             # Often reusable elements have names too
             el_name = el_data.get('name') or el_data.get('default_name')
             if el_name:
                 # Treat reusable elements like pages for mapping purposes?
                 # Or accessible from any page? For now, map as their own "page" context
                 self.pages[el_name] = el_id
                 self.elements[el_name] = {}
                 self._map_elements_recursive(el_name, el_data.get('elements', {}))

    def _map_elements_recursive(self, context_name: str, elements_dict: Dict[str, Any]):
        """Recursively maps elements"""
        if not isinstance(elements_dict, dict):
            return

        for el_id, el_data in elements_dict.items():
            if not isinstance(el_data, dict):
                continue

            # Try specific name first, then default name
            el_name = el_data.get('name') or el_data.get('default_name')

            if el_name:
                self.elements[context_name][el_name] = el_id

            # Recurse
            if 'elements' in el_data:
                self._map_elements_recursive(context_name, el_data['elements'])

    def _load_legacy_map(self, data: Dict[str, Any]):
        """Carrega formato legacy/export (consolelog-app.json)"""
        p3 = data.get('%p3', {})
        for page_id, page_data in p3.items():
            if page_data.get('%x') in ['Page', 'ReusableElement']:
                page_name = page_data.get('%nm') or page_data.get('%dn')
                if page_name:
                    self.pages[page_name] = page_id
                    self.elements[page_name] = {}

                    # Legacy is usually flat in %el ? Or need recursion too?
                    # Assuming flat based on previous observations, but recursion is safer if structure varies.
                    elements = page_data.get('%el', {})
                    for el_id, el_data in elements.items():
                        el_name = el_data.get('%dn')
                        if el_name:
                            self.elements[page_name][el_name] = el_id

    def get_page_id(self, page_name: str) -> Optional[str]:
        return self.pages.get(page_name)

    def get_element_id(self, page_name: str, element_name: str) -> Optional[str]:
        if page_name not in self.elements:
            return None
        return self.elements[page_name].get(element_name)


# ==========================================
# PATH DISCOVERY ENGINE
# ==========================================

class PathDiscovery:
    """
    Auto-discovers element paths in app.bubble file.
    Eliminates manual path lookup for CLI operations.
    """

    def __init__(
        self,
        app_json_path: Optional[str] = None,
        consolelog_json_path: Optional[str] = None,
        crawler_index_path: Optional[str] = None,
        mutation_overlay_path: Optional[str] = None,
    ):
        print(f"[PathDiscovery] INIT: app_path={app_json_path}, console_path={consolelog_json_path}, crawler_path={crawler_index_path}, overlay_path={mutation_overlay_path}")
        self.app_json_path = app_json_path
        self.consolelog_json_path = consolelog_json_path
        self.crawler_index_path = crawler_index_path
        self.mutation_overlay_path = mutation_overlay_path
        self._data = None
        self._data_source = None  # Track which source was used

    def _load_crawler_index(self, path: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Load a crawler-index JSON and convert its array-based pages/reusables
        into dicts keyed by ID, matching the shape expected by _merge_crawler_into_data.

        Returns None if the path is absent, unreadable, or contains no useful data.
        """
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:
            logger.warning(f"[PathDiscovery] Could not read crawler-index at {path}: {exc}")
            return None

        if not isinstance(raw, dict):
            return None

        pages_by_id: Dict[str, Any] = {}
        for page in raw.get("pages", []):
            if not isinstance(page, dict):
                continue
            pid = page.get("id") or page.get("name")
            if pid:
                pages_by_id[pid] = page

        reusables_by_id: Dict[str, Any] = {}
        for reusable in raw.get("reusables", []):
            if not isinstance(reusable, dict):
                continue
            rid = reusable.get("id") or reusable.get("name")
            if rid:
                reusables_by_id[rid] = reusable

        backend_workflows_by_id: Dict[str, Any] = {}
        for workflow in raw.get("backendWorkflows", []):
            if not isinstance(workflow, dict):
                continue
            wid = workflow.get("id") or workflow.get("name")
            if wid:
                backend_workflows_by_id[wid] = workflow

        # ── API Connector calls ──────────────────────────────────────────────
        # Stored as a flat list in the crawler-index under "apiConnectorCalls".
        # Convert to a dict keyed by collectionId → calls → callId for easy lookup.
        api_connector_calls: list = raw.get("apiConnectorCalls", [])
        collections_by_id: Dict[str, Any] = {}
        for call in api_connector_calls:
            if not isinstance(call, dict):
                continue
            col_id   = call.get("collectionId", "")
            col_name = call.get("collectionName", col_id)
            call_id  = call.get("callId", "")
            call_name = call.get("callName", call_id)
            if not col_id or not call_id:
                continue
            if col_id not in collections_by_id:
                collections_by_id[col_id] = {
                    "%nm": col_name,
                    "%d":  col_name,
                    "calls": {},
                }
            collections_by_id[col_id]["calls"][call_id] = {
                "%nm": call_name,
                "%d":  call_name,
            }

        if not pages_by_id and not reusables_by_id and not backend_workflows_by_id and not collections_by_id:
            return None

        logger.info(
            f"[PathDiscovery] Loaded crawler-index: {len(pages_by_id)} pages, "
            f"{len(reusables_by_id)} reusables, "
            f"{len(backend_workflows_by_id)} backend workflows, "
            f"{sum(len(c['calls']) for c in collections_by_id.values())} API calls "
            f"from {path}"
        )
        return {
            "pages": pages_by_id,
            "element_definitions": reusables_by_id,
            "backend_workflows": backend_workflows_by_id,
            "api_connector_collections": collections_by_id,
        }

    def _load_mutation_overlay(self, path: Optional[str]) -> List[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as exc:
            logger.warning(f"[PathDiscovery] Could not read mutation overlay at {path}: {exc}")
            return []

        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict) and isinstance(entry.get("changes"), list)]

    @staticmethod
    def _normalize_overlay_path_array(path_array: Any) -> List[str]:
        if not isinstance(path_array, list):
            return []
        normalized: List[str] = []
        for segment in path_array:
            if isinstance(segment, (str, int, float)):
                text = str(segment)
                if text:
                    normalized.append(text)
        return normalized

    @staticmethod
    def _set_nested_overlay_value(target: Dict[str, Any], path_parts: List[str], value: Any) -> None:
        if not path_parts:
            return
        cur: Dict[str, Any] = target
        for token in path_parts[:-1]:
            nxt = cur.get(token)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[token] = nxt
            cur = nxt
        cur[path_parts[-1]] = copy.deepcopy(value)

    @staticmethod
    def _delete_nested_overlay_value(target: Dict[str, Any], path_parts: List[str]) -> None:
        if not path_parts:
            return
        cur: Dict[str, Any] = target
        for token in path_parts[:-1]:
            nxt = cur.get(token)
            if not isinstance(nxt, dict):
                return
            cur = nxt
        cur.pop(path_parts[-1], None)

    @staticmethod
    def _delete_aliased_overlay_record(target: Dict[str, Any], bucket_names: List[str], key: str) -> None:
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
                    for alias in (value.get("id"), value.get("%nm"), value.get("name"), value.get("%d")):
                        if isinstance(alias, str) and alias.strip() in aliases:
                            should_delete = True
                            break
                if should_delete:
                    bucket.pop(candidate_key, None)

    def _delete_overlay_value(self, target: Dict[str, Any], path_parts: List[str]) -> None:
        if len(path_parts) == 2 and path_parts[0] in {"%p3", "pages", "all_pages"}:
            self._delete_aliased_overlay_record(target, ["%p3", "pages", "all_pages"], path_parts[1])
            return
        if len(path_parts) == 2 and path_parts[0] in {"%ed", "element_definitions", "CustomDefinition", "custom_definitions"}:
            self._delete_aliased_overlay_record(target, ["%ed", "element_definitions", "CustomDefinition", "custom_definitions"], path_parts[1])
            return
        self._delete_nested_overlay_value(target, path_parts)

    def _apply_mutation_overlay(self, data: Dict[str, Any], entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(data, dict) or not entries:
            return data
        for entry in entries:
            changes = entry.get("changes") if isinstance(entry, dict) else None
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                path_parts = self._normalize_overlay_path_array(change.get("path_array"))
                if not path_parts:
                    continue
                intent = change.get("intent") if isinstance(change.get("intent"), dict) else {}
                intent_name = str(intent.get("name") or "").strip()
                lowered_intent = intent_name.lower()
                is_delete = (
                    intent_name == "RemoveElement"
                    or lowered_intent.startswith("delete")
                    or lowered_intent == "removeelement"
                    or (len(path_parts) > 0 and path_parts[-1] == "%del")
                )
                if is_delete:
                    delete_path = path_parts[:-1] if path_parts and path_parts[-1] == "%del" else path_parts
                    self._delete_overlay_value(data, delete_path)
                    continue
                if "body" in change:
                    self._set_nested_overlay_value(data, path_parts, change.get("body"))
        return data

    def _merge_crawler_into_data(
        self,
        data: Dict[str, Any],
        crawler: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Inject element trees from crawler-index into a consolelog data dict.

        For each page/reusable in the crawler, the "elements" dict (top-level
        children keyed by element-ID) is placed under the matching entry in
        data["pages"] / data["element_definitions"].  If the entry doesn't yet
        exist in data, a minimal stub is created so the context is always
        reachable by list_elements() and _collect_context_elements().

        The consolelog schema (user_types, styles, option_sets …) is preserved
        untouched; only the element trees are enriched.
        """
        import copy
        data = copy.deepcopy(data)

        # ── Pages ────────────────────────────────────────────────────────────
        # consolelog pages live under "pages" or "%p3" (same content, two aliases).
        # We normalise to "pages" and keep both keys in sync afterwards.
        pages_key = "pages" if "pages" in data else ("%p3" if "%p3" in data else "pages")
        if pages_key not in data or not isinstance(data[pages_key], dict):
            data[pages_key] = {}
        data_pages = data[pages_key]

        for pid, cpage in crawler.get("pages", {}).items():
            if pid not in data_pages or not isinstance(data_pages[pid], dict):
                # Stub entry — consolelog/.bubble didn't have this page
                data_pages[pid] = {
                    "%nm": cpage.get("name", pid),
                    "%d":  cpage.get("name", pid),
                    "id": pid,
                }

            target_page = data_pages[pid]

            # Merge Elements
            celements = cpage.get("elements")
            if isinstance(celements, dict) and celements:
                el_key = "elements" if "elements" in target_page else ("%el" if "%el" in target_page else "elements")
                if el_key not in target_page:
                    target_page[el_key] = {}

                # Deep merge elements: don't overwrite entire dict, add/update individual elements
                if isinstance(target_page[el_key], dict):
                    for eid, payl in celements.items():
                        if eid == "length": continue
                        if eid not in target_page[el_key]:
                            target_page[el_key][eid] = payl
                        else:
                            # Update existing element with crawler info if richer
                            if isinstance(target_page[el_key][eid], dict) and isinstance(payl, dict):
                                # Favor names from crawler if present
                                for name_key in ("%nm", "%dn", "name"):
                                    if payl.get(name_key) and not target_page[el_key][eid].get(name_key):
                                        target_page[el_key][eid][name_key] = payl[name_key]

                # Keep both common keys in sync
                target_page["elements"] = target_page[el_key]
                target_page["%el"] = target_page[el_key]

            # Merge Workflows
            cworkflows = cpage.get("workflows")
            if isinstance(cworkflows, dict) and cworkflows:
                wf_key = "workflows" if "workflows" in target_page else ("%wf" if "%wf" in target_page else "workflows")
                if wf_key not in target_page:
                    target_page[wf_key] = {}

                if isinstance(target_page[wf_key], dict):
                    for wfid, wfpayl in cworkflows.items():
                        if wfid not in target_page[wf_key]:
                            target_page[wf_key][wfid] = wfpayl

                target_page["workflows"] = target_page[wf_key]
                target_page["%wf"] = target_page[wf_key]

        # Keep the alternate key alias in sync
        alt_key = "%p3" if pages_key == "pages" else "pages"
        data[alt_key] = data_pages

        # ── Reusables / element_definitions ──────────────────────────────────
        # consolelog reusables live under "element_definitions" or "%ed".
        ed_key = "element_definitions" if "element_definitions" in data else (
            "%ed" if "%ed" in data else "element_definitions"
        )
        if ed_key not in data or not isinstance(data[ed_key], dict):
            data[ed_key] = {}
        data_ed = data[ed_key]

        for rid, creusable in crawler.get("element_definitions", {}).items():
            if rid not in data_ed or not isinstance(data_ed[rid], dict):
                data_ed[rid] = {
                    "%nm": creusable.get("name", rid),
                    "%d":  creusable.get("name", rid),
                    "id": rid,
                }

            target_reusable = data_ed[rid]

            # Merge Elements
            celements = creusable.get("elements")
            if isinstance(celements, dict) and celements:
                el_key = "elements" if "elements" in target_reusable else ("%el" if "%el" in target_reusable else "elements")
                if el_key not in target_reusable:
                    target_reusable[el_key] = {}

                if isinstance(target_reusable[el_key], dict):
                    for eid, payl in celements.items():
                        if eid == "length": continue
                        if eid not in target_reusable[el_key]:
                            target_reusable[el_key][eid] = payl
                        else:
                            if isinstance(target_reusable[el_key][eid], dict) and isinstance(payl, dict):
                                for name_key in ("%nm", "%dn", "name"):
                                    if payl.get(name_key) and not target_reusable[el_key][eid].get(name_key):
                                        target_reusable[el_key][eid][name_key] = payl[name_key]

                target_reusable["elements"] = target_reusable[el_key]
                target_reusable["%el"] = target_reusable[el_key]

            # Merge Workflows
            cworkflows = creusable.get("workflows")
            if isinstance(cworkflows, dict) and cworkflows:
                wf_key = "workflows" if "workflows" in target_reusable else ("%wf" if "%wf" in target_reusable else "workflows")
                if wf_key not in target_reusable:
                    target_reusable[wf_key] = {}

                if isinstance(target_reusable[wf_key], dict):
                    for wfid, wfpayl in cworkflows.items():
                        if wfid not in target_reusable[wf_key]:
                            target_reusable[wf_key][wfid] = wfpayl

                target_reusable["workflows"] = target_reusable[wf_key]
                target_reusable["%wf"] = target_reusable[wf_key]

        alt_ed_key = "%ed" if ed_key == "element_definitions" else "element_definitions"
        data[alt_ed_key] = data_ed

        # ── Backend workflows ────────────────────────────────────────────────
        api_bucket = data.get("api")
        if not isinstance(api_bucket, dict):
            api_bucket = {}
            data["api"] = api_bucket

        for wid, cworkflow in crawler.get("backend_workflows", {}).items():
            if wid not in api_bucket or not isinstance(api_bucket[wid], dict):
                api_bucket[wid] = {
                    "id": wid,
                    "%d": cworkflow.get("name", wid),
                    "name": cworkflow.get("name", wid),
                    "type": cworkflow.get("trigger", "APIEvent"),
                }

            target_workflow = api_bucket[wid]
            if cworkflow.get("name"):
                target_workflow.setdefault("%d", cworkflow.get("name"))
                target_workflow.setdefault("name", cworkflow.get("name"))
            if cworkflow.get("trigger") and not target_workflow.get("type"):
                target_workflow["type"] = cworkflow.get("trigger")

            cactions = cworkflow.get("actions")
            if isinstance(cactions, dict) and cactions:
                existing_actions = target_workflow.get("actions")
                if not isinstance(existing_actions, dict):
                    existing_actions = {}
                    target_workflow["actions"] = existing_actions
                for action_id, action_payload in cactions.items():
                    if action_id not in existing_actions:
                        existing_actions[action_id] = action_payload

        # ── API Connector calls ───────────────────────────────────────────────
        # Stored in the crawler-index as a dict keyed by collectionId.
        # We inject them under "api_connector_collections" so MCP tools can
        # enumerate available API calls without needing a fresh browser capture.
        api_collections = crawler.get("api_connector_collections", {})
        if api_collections:
            data["api_connector_collections"] = api_collections
            # Also populate plugin_special if it was null/absent in consolelog
            if not data.get("plugin_special"):
                data["plugin_special"] = api_collections
            logger.info(
                f"[PathDiscovery] Injected {sum(len(c.get('calls', {})) for c in api_collections.values())} "
                f"API Connector calls into data"
            )

        return data

    def _cache_enabled(self) -> bool:
        raw = str(os.getenv("BUBBLE_CLI_DISCOVERY_CACHE", "1")).strip().lower()
        return raw not in {"0", "false", "no", "off"}

    def _cache_path_for_source(self, source_path: str) -> str:
        return f"{source_path}.parsed-cache.pkl"

    def _normalize_api_connector_collections(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize API Connector collections from consolelog/app data into a stable alias.

        Bubble often stores API Connector data under settings.client_safe.apiconnector2
        while plugin_special remains null. We expose api_connector_collections in-memory
        so downstream discovery logic can rely on one shape without mutating the raw cache.
        """
        if not isinstance(data, dict):
            return data

        existing = data.get("api_connector_collections")
        if isinstance(existing, dict) and existing:
            if not data.get("plugin_special"):
                data["plugin_special"] = existing
            return data

        settings = data.get("settings")
        client_safe = settings.get("client_safe") if isinstance(settings, dict) else None
        api2 = client_safe.get("apiconnector2") if isinstance(client_safe, dict) else None
        if not isinstance(api2, dict):
            api2 = data.get("apiconnector2")
        if not isinstance(api2, dict) or not api2:
            return data

        collections: Dict[str, Any] = {}
        for col_id, col_val in api2.items():
            if not isinstance(col_val, dict):
                continue
            col_name = (
                col_val.get("human")
                or col_val.get("%nm")
                or col_val.get("%d")
                or col_val.get("name")
                or col_id
            )
            raw_calls = col_val.get("calls")
            calls = raw_calls if isinstance(raw_calls, dict) else {}
            normalized_calls: Dict[str, Any] = {}
            for call_id, call_val in calls.items():
                if not isinstance(call_val, dict):
                    continue
                call_name = (
                    call_val.get("%nm")
                    or call_val.get("%d")
                    or call_val.get("name")
                    or call_id
                )
                normalized_calls[call_id] = {
                    **call_val,
                    "%nm": call_name,
                    "%d": call_name,
                }

            collections[col_id] = {
                **col_val,
                "%nm": col_name,
                "%d": col_name,
                "calls": normalized_calls,
            }

        if collections:
            data["api_connector_collections"] = collections
            if not data.get("plugin_special"):
                data["plugin_special"] = collections
        return data

    def _load_json_with_disk_cache(self, source_path: str) -> Dict[str, Any]:
        """
        Load JSON source using a persistent pickle cache keyed by mtime+size.
        This avoids expensive full JSON parsing on every CLI/MCP subprocess call.
        """
        if not source_path:
            return {}
        if not self._cache_enabled():
            with open(source_path, "r", encoding="utf-8") as f:
                return json.load(f)

        try:
            stat = os.stat(source_path)
            source_mtime = float(getattr(stat, "st_mtime", 0.0))
            source_size = int(getattr(stat, "st_size", 0))
        except Exception:
            with open(source_path, "r", encoding="utf-8") as f:
                return json.load(f)

        cache_path = self._cache_path_for_source(source_path)
        try:
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as cf:
                    payload = pickle.load(cf)
                if isinstance(payload, dict):
                    meta = payload.get("__meta__", {})
                    cached_mtime = float(meta.get("mtime", -1))
                    cached_size = int(meta.get("size", -1))
                    cached_data = payload.get("data")
                    if (
                        cached_mtime == source_mtime
                        and cached_size == source_size
                        and isinstance(cached_data, dict)
                        and cached_data # Valid dict
                    ):
                        return cached_data
        except Exception:
            # Cache is best-effort; fallback to source parse.
            pass

        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            cache_payload = {
                "__meta__": {"mtime": source_mtime, "size": source_size},
                "data": data,
            }
            with open(cache_path, "wb") as cf:
                pickle.dump(cache_payload, cf, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            # Ignore cache write failures.
            pass
        return data

    @property
    def data(self) -> Dict[str, Any]:
        """Lazy load app data with fallback logic"""
        if self._data is None:
            # Try primary source first
            if self.app_json_path and os.path.exists(self.app_json_path):
                try:
                    self._data = self._load_json_with_disk_cache(self.app_json_path)
                    self._data = self._normalize_api_connector_collections(self._data)
                    self._data_source = "app.bubble"
                except FileNotFoundError:
                    pass

            # Fallback to console.log JSON
            if self._data is None and self.consolelog_json_path and os.path.exists(self.consolelog_json_path):
                try:
                    print(f"[PathDiscovery] Opening consolelog: {self.consolelog_json_path}")
                    self._data = self._load_json_with_disk_cache(self.consolelog_json_path)
                    self._data = self._normalize_api_connector_collections(self._data)
                    self._data_source = "consolelog"
                    logger.info(f"Using console.log fallback: {self.consolelog_json_path}")
                except FileNotFoundError:
                    pass

            # Enrich with crawler-index if available
            # We now do this for ALL sources, including .bubble, to ensure the most
            # recent discovery findings from Aria are integrated.
            if self._data is not None and self.crawler_index_path and os.path.exists(self.crawler_index_path):
                crawler = self._load_crawler_index(self.crawler_index_path)
                if crawler:
                    self._data = self._merge_crawler_into_data(self._data, crawler)
                    self._data_source = f"{self._data_source}+crawler"
                    logger.info(f"[PathDiscovery] Merged crawler-index into {self._data_source} data")

            if self._data is not None and self.mutation_overlay_path and os.path.exists(self.mutation_overlay_path):
                overlay_entries = self._load_mutation_overlay(self.mutation_overlay_path)
                if overlay_entries:
                    self._data = self._apply_mutation_overlay(self._data, overlay_entries)
                    self._data_source = f"{self._data_source}+overlay"
                    logger.info(f"[PathDiscovery] Applied mutation overlay into {self._data_source} data")

            # No data source found
            if self._data is None:
                logger.warning("No app data source found")
                self._data = {}
                self._data_source = "none"

            logger.info(f" [DEBUG] load_discovery_cache: data loaded from {self._data_source}. Keys: {list(self._data.keys())}")

        return self._data

    def refresh(self) -> Dict[str, Any]:
        """Force reload app data from disk"""
        self._data = None
        return self.data

    @property
    def source_path(self) -> str:
        """Returns the path of the source currently being used"""
        if self._data is None:
            _ = self.data # Trigger load

        if self._data_source == "consolelog":
            return self.consolelog_json_path
        return self.app_json_path

    def persist_disk_cache(self) -> bool:
        """
        Persist the current in-memory discovery snapshot to the parsed-cache pickle
        associated with the active source JSON file.

        This keeps CLI/MCP-created or updated elements discoverable across
        subprocesses without forcing a full profile refresh.
        """
        if self._data is None or not isinstance(self._data, dict):
            return False
        source_path = self.source_path
        if not source_path or not self._cache_enabled():
            return False
        try:
            stat = os.stat(source_path)
            source_mtime = float(getattr(stat, "st_mtime", 0.0))
            source_size = int(getattr(stat, "st_size", 0))
        except Exception:
            source_mtime = 0.0
            source_size = 0

        cache_path = self._cache_path_for_source(source_path)
        try:
            cache_payload = {
                "__meta__": {"mtime": source_mtime, "size": source_size},
                "data": self._data,
            }
            with open(cache_path, "wb") as cf:
                pickle.dump(cache_payload, cf, protocol=pickle.HIGHEST_PROTOCOL)
            return True
        except Exception:
            return False

    def _get_context_root(self, context_id: str, context_type: str) -> Optional[Dict]:
        """Get the root object for a context, handling standard and raw formats."""
        if context_type == "reusable":
            standard = self.data.get('element_definitions', {})
            raw = self.data.get('%ed', {})
            res = None
            if isinstance(standard, dict):
                res = standard.get(context_id)
            if not res and isinstance(raw, dict):
                res = raw.get(context_id)
            if not res:
                reusable_ids: List[str] = []
                if isinstance(standard, dict):
                    reusable_ids.extend(list(standard.keys()))
                if isinstance(raw, dict):
                    reusable_ids.extend([rid for rid in raw.keys() if rid not in reusable_ids])
                logger.info(f" [DEBUG] _get_context_root: '{context_id}' not found in reusables. IDs: {reusable_ids}")
            return res
        else:
            standard = self.data.get('pages', {})
            raw = self.data.get('%p3', {})
            res = None
            if isinstance(standard, dict):
                res = standard.get(context_id)
            if not res and isinstance(raw, dict):
                res = raw.get(context_id)
            if not res:
                page_ids: List[str] = []
                if isinstance(standard, dict):
                    page_ids.extend(list(standard.keys()))
                if isinstance(raw, dict):
                    page_ids.extend([pid for pid in raw.keys() if pid not in page_ids])
                logger.info(f" [DEBUG] _get_context_root: '{context_id}' not found in pages. IDs: {page_ids}")
            return res

    def find_reusable(self, name: str) -> Optional[str]:
        """
        Find reusable element ID by name (case-insensitive).
        Returns: reusable_id or None
        """
        reusables = self.data.get('element_definitions', {}) or self.data.get('%ed', {})
        if not reusables or not isinstance(reusables, dict):
            return None

        name_lower = self._norm_lookup(name)
        for el_id, el_data in reusables.items():
            if isinstance(el_data, dict):
                el_name = el_data.get('name') or el_data.get('%nm', '')
                if self._norm_lookup(el_name) == name_lower:
                    logger.info(f" [DEBUG] find_reusable: '{name}' -> '{el_id}'")
                    return el_id
        return None

    def find_page(self, name: str) -> Optional[str]:
        """
        Find page ID by name (case-insensitive).
        Returns: page_id or None
        """
        pages = self.data.get('pages') or self.data.get('%p3')
        if not pages or not isinstance(pages, dict):
            return None

        name_lower = self._norm_lookup(name)
        for page_id, page_data in pages.items():
            if isinstance(page_data, dict):
                page_name = page_data.get('name') or page_data.get('%nm', '')
                if self._norm_lookup(page_name) == name_lower:
                    return page_id
        return None

    def find_element_by_text(self, context_id: str, text: str, context_type: str = "reusable") -> Optional[Dict]:
        """
        Find element by its text content.
        Returns: {'path': [...], 'id': str, 'element': dict} or None
        """
        root = self._get_context_root(context_id, context_type)

        if not root:
            return None

        needle = self._norm_lookup(text)

        def search(obj, path_parts=[]):
            if isinstance(obj, dict):
                # Check full text content/candidates
                for candidate in self._element_match_candidates(obj):
                    if candidate and needle and needle in self._norm_lookup(candidate):
                        return {'path': path_parts, 'id': obj.get('id'), 'element': obj}

                # Search children
                elements = obj.get('elements') or obj.get('%el', {})
                if isinstance(elements, dict):
                    for key, value in elements.items():
                        if key == "length": continue
                        result = search(value, path_parts + (['%el', key] if '%el' in obj or '%x' in obj else ['elements', key]))
                        if result:
                            return result
            return None

        return search(root)

    def find_element_by_name(
        self,
        context_id: str,
        name: str,
        context_type: str = "reusable",
        prefer_last: bool = False
    ) -> Optional[Dict]:
        """
        Find element by its name property.
        Checks: name, default_name, and properties.element_name

        Exact matches (case-insensitive) always take priority over fuzzy
        substring matches. Without this, a query like the Bubble-generated
        default name "Text L" can accidentally match an unrelated element's
        synthesized "type + text content" candidate (e.g. "Text Login",
        built from a Text element whose content is "Login") purely because
        "text l" happens to be a text-prefix of "text login" -- silently
        renaming/editing the wrong element even though the intended one
        exists elsewhere in the tree.

        Returns: {'path': [...], 'id': str, 'element': dict} or None
        """
        root = self._get_context_root(context_id, context_type)

        if not root:
            return None

        name_lower = self._norm_lookup(name)

        exact_matches: List[Dict] = []
        fuzzy_matches: List[Dict] = []

        def visit(obj, path_parts=[]):
            if isinstance(obj, dict):
                normalized_candidates = [
                    self._norm_lookup(candidate)
                    for candidate in self._element_match_candidates(obj)
                    if candidate
                ]
                match = {'path': path_parts, 'id': obj.get('id'), 'element': obj}
                if any(candidate == name_lower for candidate in normalized_candidates):
                    exact_matches.append(match)
                elif any(name_lower in candidate for candidate in normalized_candidates):
                    fuzzy_matches.append(match)

                elements = obj.get('elements') or obj.get('%el', {})
                if isinstance(elements, dict):
                    for key, value in elements.items():
                        if key == "length": continue
                        visit(value, path_parts + (['%el', key] if '%el' in obj or '%x' in obj else ['elements', key]))

        visit(root)

        matches = exact_matches or fuzzy_matches
        if not matches:
            return None
        return matches[-1] if prefer_last else matches[0]

    def find_element_by_id(
        self,
        context_id: str,
        element_id: str,
        context_type: str = "reusable"
    ) -> Optional[Dict]:
        """
        Find element by its exact Bubble ID.
        Returns: {'path': [...], 'id': str, 'element': dict} or None
        """
        root = self._get_context_root(context_id, context_type)
        if not root:
            logger.warning(f" [DEBUG] find_element_by_id: root not found for {context_id}")
            return None

        logger.info(f" [DEBUG] find_element_by_id: searching for '{element_id}' in root {context_id}")

        def search(obj, path_parts=[]):
            if isinstance(obj, dict):
                # logger.info(f" [DEBUG] Checking node: id={obj.get('id')} name={obj.get('name') or obj.get('%nm')}")
                if str(obj.get('id')) == str(element_id):
                    return {'path': path_parts, 'id': obj.get('id'), 'element': obj}

                elements = obj.get('elements') or obj.get('%el', {})
                if isinstance(elements, dict):
                    for key, value in elements.items():
                        if key == "length": continue
                        result = search(value, path_parts + (['%el', key] if '%el' in obj or '%x' in obj else ['elements', key]))
                        if result:
                            return result
            return None

        res = search(root)
        if not res:
            logger.warning(f" [DEBUG] find_element_by_id: '{element_id}' NOT FOUND in root {context_id}")
            pass
        return res
    def find_element_by_exact_name(self, context_id: str, name: str, context_type: str = "reusable") -> Optional[Dict]:
        """
        Find element by exact name match (case-insensitive).
        Checks: name, default_name, and properties.element_name
        Returns: {'path': [...], 'id': str, 'element': dict} or None
        """
        root = self._get_context_root(context_id, context_type)

        if not root:
            return None

        name_lower = self._norm_lookup(name)

        def search(obj, path_parts=[]):
            if isinstance(obj, dict):
                candidates = self._element_match_candidates(obj)

                for candidate in candidates:
                    if candidate and self._norm_lookup(candidate) == name_lower:
                        return {'path': path_parts, 'id': obj.get('id'), 'element': obj}

                # Search children
                elements = obj.get('elements') or obj.get('%el', {})
                if isinstance(elements, dict):
                    for key, value in elements.items():
                        if key == "length": continue
                        result = search(value, path_parts + (['%el', key] if '%el' in obj or '%x' in obj else ['elements', key]))
                        if result:
                            return result
            return None

        return search(root)

    def _norm_lookup(self, value: Any) -> str:
        if value is None:
            return ""
        return (
            str(value)
            .replace("’", "'")
            .replace("‘", "'")
            .replace("`", "'")
            .replace("“", "\"")
            .replace("”", "\"")
            .strip()
            .lower()
        )

    def _plain_text_from_expr(self, expr: Any) -> str:
        """
        Best-effort plain text extraction from Bubble TextExpression-like objects.
        Keeps only literal string entries in order.
        """
        if not isinstance(expr, dict):
            return ""
        entries = expr.get("entries") or expr.get("%e")
        if not isinstance(entries, dict):
            return ""
        parts = []
        for key in sorted(entries.keys(), key=lambda x: int(x) if str(x).isdigit() else 9999):
            value = entries.get(key)
            if isinstance(value, str):
                parts.append(value)
        return "".join(parts).strip()

    def _element_match_candidates(self, obj: Dict[str, Any]) -> List[str]:
        """
        Build matching candidates including values users commonly see in Bubble editor.
        """
        if not isinstance(obj, dict):
            return []
        props = obj.get("properties", {}) if isinstance(obj.get("properties"), dict) else {}
        el_type = obj.get("type") or obj.get("%x") or ""
        el_type_norm = str(el_type).strip()

        candidates = []
        base_names = [
            obj.get("name", ""),
            obj.get("default_name", ""),
            props.get("element_name", "")
        ]
        for value in base_names:
            if value:
                candidates.append(str(value))
                if el_type_norm:
                    candidates.append(f"{el_type_norm} {value}")

        # Label/content-like values shown by Bubble UI
        text_plain = self._plain_text_from_expr(props.get("text"))
        if text_plain:
            candidates.append(text_plain)
            if el_type_norm:
                candidates.append(f"{el_type_norm} {text_plain}")
            if el_type_norm.lower() == "button":
                candidates.append(f"Button {text_plain}")
            if el_type_norm.lower() == "text":
                candidates.append(f"Text {text_plain}")

        # Icon values shown in Icon and some Button editors
        icon_value = props.get("icon") or props.get("%9i")
        if icon_value:
            icon_value = str(icon_value)
            candidates.append(icon_value)
            candidates.append(f"Icon {icon_value}")
            if el_type_norm.lower() == "button":
                candidates.append(f"Button {icon_value}")

        # Image source shorthand may appear in user phrasing
        src_plain = self._plain_text_from_expr(props.get("src"))
        if src_plain:
            candidates.append(src_plain)
            candidates.append(f"Image {src_plain}")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in candidates:
            n = self._norm_lookup(c)
            if not n or n in seen:
                continue
            seen.add(n)
            unique.append(c)
        return unique

    def list_styles(self, filter_text: str = "") -> List[Dict]:
        """
        List all styles (default + custom), optionally filtering by name.
        Returns: List of {'id': str, 'name': str, 'type': str}
        """
        results = []
        filter_lower = filter_text.lower() if filter_text else ""

        # Add default styles from settings
        settings = self.data.get('settings', {})
        client_safe = settings.get('client_safe', {})
        default_styles = client_safe.get('default_styles', {})

        for element_type, style_id in default_styles.items():
            style_name = f"{element_type} (default)"
            if not filter_lower or filter_lower in style_name.lower():
                results.append({
                    "id": style_id,
                    "name": style_name,
                    "type": element_type,
                    "is_default": True
                })

        # Add custom styles
        styles = self.data.get('styles', {})
        for style_id, style_data in styles.items():
            if isinstance(style_data, dict):
                 # Use 'display' as name if 'name' is missing (common in minified bubble apps)
                 style_name = style_data.get("name", style_data.get("display", style_data.get("%d", style_id)))

                 # Resolve type
                 style_type = style_data.get("type", style_data.get("%x"))
                 if not style_type:
                     # Infer from ID prefix (e.g. Text_bzsCm -> Text)
                     if "_" in style_id:
                         prefix = style_id.split("_")[0]
                         if prefix in ("Text", "Group", "Button", "Icon", "Input", "Image", "Checkbox", "RadioButtons", "Select", "DateRangePicker", "MultiSelect", "Searchbox", "Slider", "Toggle"):
                             style_type = prefix

                 if not style_type:
                     style_type = "Unknown"

                 if not filter_lower or filter_lower in style_name.lower():
                     results.append({
                         "id": style_id,
                         "name": style_name,
                         "type": style_type,
                         "is_default": False
                     })

        return results

    def inject_element(self, context_id: str, context_type: str, parent_id: Optional[str], element_data: Dict[str, Any], element_key: Optional[str] = None):
        """
        Manually inject a created element into the discovery cache.
        Enables sequential batch operations to find newly created elements.

        Args:
            element_key: The KEY used in the path (e.g. bKey). If None, uses element_data['id'].
                         CRITICAL: This must match the key used in the CreateElement path!
        """
        # Get Root
        root = self._get_context_root(context_id, context_type)

        if not root:
            # Auto-create context root for newly created reusables/pages
            # This handles the case where create_reusable sends via webhook
            # but the local JSON hasn't been refreshed yet.
            container_key = 'element_definitions' if context_type == "reusable" else 'pages'
            # Also try raw format keys
            raw_key = '%ed' if context_type == "reusable" else '%p3'

            # Determine which top-level key exists in data, prefer standard format
            if container_key in self.data:
                target_key = container_key
            elif raw_key in self.data:
                target_key = raw_key
            else:
                # Create standard format container
                self.data[container_key] = {}
                target_key = container_key

            # Create a minimal root entry
            self.data[target_key][context_id] = {
                "id": context_id,
                "name": element_data.get('%dn', '') or element_data.get('name', ''),
                "elements": {}
            }
            root = self.data[target_key][context_id]
            logger.info(f"Auto-created context root for {context_id} in {target_key}")

        # Determine children key based on root format
        # In raw format, it's %el. In standard format, it's elements.
        children_key = "%el" if "%el" in root or "%x" in root else "elements"

        # Prepare element structure for discovery (simplified)
        # discovery looks for 'name', 'default_name', 'id'
        extracted_name = element_data.get('%dn') or element_data.get('%nm') or element_data.get('name', '')

        object_id = element_data.get('id', element_key)
        new_el = {
            "id": object_id,
            "type": element_data.get('%x', 'Unknown'),
            "default_name": extracted_name,
            "name": extracted_name,
            "key": element_key,
            "properties": element_data.get('%p', {}),
            "elements": {}  # Empty children
        }

        # Use element_key if provided, otherwise ID.
        # PathDiscovery relies on this key being the PATH segment.
        dict_key = element_key if element_key else new_el['id']

        # CRITICAL:
        # - dict_key must stay as the PATH slot key used under %el/elements
        # - internal id must remain the Bubble object id from body.id
        # Overwriting id with dict_key breaks later parent resolution for nested creates
        # because find_element_by_id starts returning paths rooted in object ids instead of slot keys.
        if dict_key and not new_el.get("key"):
            new_el["key"] = dict_key

        # If parent_id is None or same as context (Root), add to root elements
        if not parent_id or parent_id == context_id:
             # Check if we are updating the root itself
             # We need to make sure we're updating the PERSISTENT self.data
             container_key = 'element_definitions' if context_type == "reusable" else 'pages'
             if container_key not in self.data and (container_key == 'element_definitions' and '%ed' in self.data):
                 container_key = '%ed'
             elif container_key not in self.data and (container_key == 'pages' and '%p3' in self.data):
                 container_key = '%p3'

             if container_key not in self.data:
                 self.data[container_key] = {}

             container = self.data[container_key]

             # If this is the root itself or if it has the same ID, update it
             if context_id in container and (not element_key or element_key == context_id or element_key == extracted_name):
                 container[context_id].update(new_el)
                 self.persist_disk_cache()
                 logger.info(f" Updated context root {context_id} with name '{extracted_name}'")
                 return

             # Fallback: if it's the root but not in container, add it!
             if context_id not in container:
                 container[context_id] = new_el
                 self.persist_disk_cache()
                 logger.info(f" Added new context root {context_id} with name '{extracted_name}'")
                 return

             if children_key not in root:
                 root[children_key] = {}
             root[children_key][dict_key] = new_el
             self.persist_disk_cache()
             logger.info(f" Injected {new_el['default_name']} ({dict_key}) into {context_id} root")
             return

        # If parent_id provided, find it first
        # We can reuse find_element_by_name logic but we need ID search
        # Quick search
        def find_node(obj):
            if isinstance(obj, dict):
                if obj.get('id') == parent_id:
                    return obj
                elements = obj.get('elements') or obj.get('%el')
                if isinstance(elements, dict):
                    for k, v in elements.items():
                        if k == "length": continue
                        res = find_node(v)
                        if res: return res
            return None

        parent_node = find_node(root)
        if parent_node:
             # Match children key of the parent
             node_children_key = "%el" if "%el" in parent_node or "%x" in parent_node else "elements"
             if node_children_key not in parent_node:
                 parent_node[node_children_key] = {}
             parent_node[node_children_key][dict_key] = new_el
             self.persist_disk_cache()
             logger.info(f" Injected {new_el['default_name']} ({dict_key}) into parent {parent_id}")
        else:
             logger.warning(f"Injection failed: Parent {parent_id} not found")

    def find_workflow_for_element(self, context_id: str, element_id: str, event_type: str = "click", context_type: str = "reusable") -> Optional[Dict]:
        """
        Find a workflow triggered by a specific element event.
        Returns: {'path': [...], 'id': str, 'workflow': dict} or None
        """
        root = self._get_context_root(context_id, context_type)

        if not root:
            return None

        # Workflows are usually in 'workflows' dict or equivalent
        # But in some internal formats they are in %p3 -> %wf
        # Let's search recursively for objects with type 'ElementEvent' (or similar)

        def search_workflow(obj, path_parts=[]):
            if isinstance(obj, dict):
                # Check if it's a workflow event
                obj_type = obj.get('%x') or obj.get('type')
                if obj_type:
                    props = obj.get('%p', {})
                    if not isinstance(props, dict):
                        props = obj.get('properties', {})
                    if not isinstance(props, dict):
                        props = {}
                    target_el = props.get('%ei') or props.get('element_id')
                    event_kind = props.get('%et') or props.get('event_type')

                    if obj_type == 'ElementEvent':
                        if target_el == element_id and event_kind == event_type:
                            return {'path': path_parts, 'id': obj.get('id'), 'workflow': obj}
                    elif obj_type == 'ButtonClicked':
                        if target_el == element_id and event_type in ['click', 'clicked', None]:
                            return {'path': path_parts, 'id': obj.get('id'), 'workflow': obj}
                    elif obj_type == 'InputValueChanged':
                        if target_el == element_id and event_type in ['change', 'value_changed', 'input', None]:
                            return {'path': path_parts, 'id': obj.get('id'), 'workflow': obj}
                    elif obj_type == 'DropdownValueChanged':
                        if target_el == element_id and event_type in ['change', 'value_changed', None]:
                            return {'path': path_parts, 'id': obj.get('id'), 'workflow': obj}
                    elif obj_type == 'PageLoaded':
                        if event_type in ['load', 'page_loaded', 'page load', None]:
                            return {'path': path_parts, 'id': obj.get('id'), 'workflow': obj}

                # Search children
                elements = obj.get('elements') or obj.get('%el')
                if isinstance(elements, dict):
                    for key, value in elements.items():
                        if key == "length": continue
                        child_path = path_parts + (['%el', key] if '%el' in obj or '%x' in obj else ['elements', key])
                        result = search_workflow(value, child_path)
                        if result: return result

                # Search workflows direct list if any
                workflows = obj.get('workflows') or obj.get('%wf')
                if isinstance(workflows, dict):
                    for key, value in workflows.items():
                        if key == "length": continue
                        child_path = path_parts + (['%wf', key] if '%wf' in obj or '%x' in obj else ['workflows', key])
                        result = search_workflow(value, child_path)
                        if result: return result
            return None

        # Optimization: Look in 'workflows' key first if it exists
        if 'workflows' in root:
             # Iterate newest first so action writes target the latest workflow.
             for wf_id, wf_data in reversed(list(root['workflows'].items())):
                 result = search_workflow(wf_data, ['workflows', wf_id]) # Path structure might vary
                 if result:
                     return result

        # Fallback to full search (legacy structure)
        return search_workflow(root)

    def list_elements(self, context_id: str, context_type: str = "reusable") -> List[Dict]:
        """List all elements with their paths in a context."""
        if context_type == "reusable":
            root = self.data.get('element_definitions', {}).get(context_id)
        else:
            root = self.data.get('pages', {}).get(context_id)

        if not root:
            return []

        results = []

        def walk(elements, path_parts):
            if not isinstance(elements, dict):
                return
            for key, value in elements.items():
                if not isinstance(value, dict):
                    continue
                results.append({
                    "path": path_parts + ["%el", key],
                    "id": value.get("id"),
                    "element": value
                })
                walk(value.get("elements", {}), path_parts + ["%el", key])

        walk(root.get("elements", {}), [])
        return results

    def inject_workflow(
        self,
        context_id: str,
        element_id: str,
        event_type: str,
        wf_id: str,
        context_type: str,
        workflow_obj: Optional[Dict] = None
    ):
        """Inject workflow into discovery"""
        if context_type == "reusable":
            root = self.data.get('element_definitions', {}).get(context_id)
        else:
            root = self.data.get('pages', {}).get(context_id)

        if not root: return

        if 'workflows' not in root:
            root['workflows'] = {}

        # Keep injected workflow shape aligned with what was created.
        if isinstance(workflow_obj, dict):
            wf_obj = dict(workflow_obj)
            wf_obj.setdefault("id", wf_id)
            wf_obj.setdefault("actions", {})
        else:
            wf_obj = {
                "id": wf_id,
                "%x": "ElementEvent",
                "%p": {
                    "%ei": element_id,
                    "%et": event_type
                },
                "actions": {}
            }

        root['workflows'][wf_id] = wf_obj
        logger.info(f" Injected Workflow {wf_id} for element {element_id}")

    def build_path_array(self, context_id: str, element_path: List[str], context_type: str = "reusable") -> List[str]:
        """
        Build full path_array for API calls.
        context_type: 'reusable' uses %ed, 'page' uses %p3
        """
        prefix = "%ed" if context_type == "reusable" else "%p3"
        token_map = {
            "pages": "%p3",
            "element_definitions": "%ed",
            "elements": "%el",
            "properties": "%p",
            "workflows": "%wf",
            "name": "%nm",
            "default_name": "%dn",
            "text": "%3",
        }
        normalized_path: List[str] = []
        for part in element_path or []:
            token = str(part)
            normalized_path.append(token_map.get(token, token))
        return [prefix, context_id] + normalized_path

    def get_element_style(self, element: Dict) -> Optional[str]:
        """Extract style from element if present"""
        return element.get('style') or element.get('%s1')

    def get_element_properties(self, element: Dict) -> Dict:
        """Extract all properties from element"""
        return element.get('properties', {})


# ==========================================
# API CLIENT
# ==========================================

class BubbleClient:
    """Cliente HTTP para enviar requisições ao Bubble"""

    def __init__(self, appname: str = "synthetic-page", cookies: Optional[str] = None):
        self.appname = appname
        self.cookies = cookies
        self.base_url = "https://bubble.io/appeditor/write"
        self.id_gen = BubbleIDGenerator()

    def send(self, payload: Dict[str, Any]) -> requests.Response:
        """Envia payload para o Bubble"""
        if not self.cookies:
            raise ValueError("Cookies de autenticação são obrigatórios!")

        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "content-type": "application/json",
            "x-bubble-appname": self.appname,
            "x-bubble-fiber-id": self.id_gen.fiber_id(),
            "x-bubble-pl": self.id_gen.pl_id(),
            "x-requested-with": "XMLHttpRequest",
            "x-bubble-platform": "web",
            "x-bubble-breaking-revision": "5",
            "Cookie": self.cookies
        }

        try:
            response = requests.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.error(f"Erro HTTP: {e}")
            logger.error(f"Response: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Erro: {e}")
            raise


class WebhookClient:
    """Cliente para enviar requisições ao gateway do editor (Webhook)"""

    def __init__(self, url: str = "local://bubble-mcp", app_name: str = "synthetic-page"):
        self.url = url
        self.app_name = app_name
        try:
            self.timeout_seconds = int(str(os.getenv("BUBBLE_CLI_WEBHOOK_TIMEOUT_SEC", "15")).strip())
        except Exception:
            self.timeout_seconds = 15
        if self.timeout_seconds <= 0:
            self.timeout_seconds = 15

    def send(self, payload: Dict[str, Any]) -> requests.Response:
        """Envia payload para o webhook configurado"""
        envelope_mode = str(os.getenv("BUBBLE_CLI_WEBHOOK_ENVELOPE_MODE", "body")).strip().lower()
        if envelope_mode not in {"root", "body", "both"}:
            envelope_mode = "root"

        if envelope_mode == "body":
            data = {
                "app-name": self.app_name,
                "appname": self.app_name,
                "body": payload,
            }
        elif envelope_mode == "both":
            data = {
                "app-name": self.app_name,
                "appname": self.app_name,
                "body": payload,
                **(payload if isinstance(payload, dict) else {})
            }
        else:
            data = {
                "app-name": self.app_name,
                "appname": self.app_name,
                **(payload if isinstance(payload, dict) else {})
            }

        try:
            debug_dir = os.path.join(tempfile.gettempdir(), "bubble-webhook-debug")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            with open(os.path.join(debug_dir, "last_payload.json"), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            with open(os.path.join(debug_dir, "last_envelope.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with open(os.path.join(debug_dir, f"payload_{timestamp}.json"), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            with open(os.path.join(debug_dir, f"envelope_{timestamp}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        logger.info(f" Enviando para Webhook: {self.url}...")

        try:
            response = requests.post(self.url, json=data, timeout=self.timeout_seconds)
            response.raise_for_status()
            logger.success("Webhook enviado com sucesso!")
            return response
        except Exception as e:
            logger.error(f"Erro ao enviar para Webhook: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            raise



# ==========================================
# EXAMPLE USAGE
# ==========================================

if __name__ == "__main__":
    print("=" * 70)
    print("BUBBLE SDK - Examples")
    print("=" * 70)

    # 1. Build paths
    print("\n1️⃣ Building paths:")
    path_structure = PathBuilder.build_for_structure("bTRKY")
    path_elements = PathBuilder.build_for_elements("bTRKY")
    path_workflow = PathBuilder.build_for_workflow("bTRKY", "bWF01")
    print(f"   Structure (%ed): {path_structure}")
    print(f"   Elements (%p3):  {path_elements}")
    print(f"   Workflow (%wf):  {path_workflow}")

    # 2. Create elements
    print("\n2️⃣ Creating elements:")
    builder = ElementBuilder()

    group = builder.group("Container", layout="column", width=800)
    text = builder.text("Title", "Hello World", font_size=24, font_weight="700")
    button = builder.button("CTA", "Click Me", bg_color="#10B981")

    print(f"   Group ID: {group['id']}")
    print(f"   Text ID: {text['id']}")
    print(f"   Button ID: {button['id']}")

    # 3. Build payload
    print("\n3️⃣ Building payload:")
    payload_builder = PayloadBuilder("synthetic-page", "test")

    page_path = PathBuilder.build_for_elements("bTRKY")

    payload_builder.add_create_element(page_path, group)
    payload_builder.add_create_element(page_path + ["%el", group["id"]], text)
    payload_builder.add_create_element(page_path + ["%el", group["id"]], button)

    payload = payload_builder.build()
    print(f"   Changes: {len(payload['changes'])}")

    # 4. Save
    print("\n4️⃣ Saving payload:")
    payload_builder.save("bubble_sdk_example.json")

    print("\n✨ Done!")
