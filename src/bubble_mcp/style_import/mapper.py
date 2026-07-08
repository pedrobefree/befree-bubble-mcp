from __future__ import annotations

import re
from collections.abc import Iterable

from bubble_mcp.style_import.models import BubbleStyleCandidate, ExtractedStyleRule


SUPPORTED_BORDER_STYLES = {
    "none",
    "hidden",
    "dotted",
    "dashed",
    "solid",
    "double",
    "groove",
    "ridge",
    "inset",
    "outset",
}

SIDE_SUFFIXES = {
    "top": "top",
    "right": "right",
    "bottom": "bottom",
    "left": "left",
}

RADIUS_CORNERS = {
    "border-top-left-radius": "radius_top_left",
    "border-top-right-radius": "radius_top_right",
    "border-bottom-right-radius": "radius_bottom_right",
    "border-bottom-left-radius": "radius_bottom_left",
}
BOX_SIDES = ("top", "right", "bottom", "left")
RADIUS_FIELDS = ("radius_top_left", "radius_top_right", "radius_bottom_right", "radius_bottom_left")


def _pixel_int(value: str) -> int | None:
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)px\s*", value)
    if match is None:
        return None
    return int(round(float(match.group(1))))


def _css_length_int(value: str) -> int | None:
    pixel = _pixel_int(value)
    if pixel is not None:
        return pixel
    if re.fullmatch(r"\s*0+(?:\.0+)?\s*", value):
        return 0
    return None


def _lower_hex(value: str) -> str | None:
    stripped = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", stripped):
        return stripped.lower()
    return None


def _split_border(value: str) -> tuple[dict[str, object], bool, list[str]]:
    mapped: dict[str, object] = {}
    recognized_any = False
    unparsed: list[str] = []

    for part in value.split():
        width = _pixel_int(part)
        if width is not None:
            mapped["border_width"] = width
            recognized_any = True
            continue

        lower_part = part.lower()
        if lower_part in SUPPORTED_BORDER_STYLES:
            mapped["border_style"] = lower_part
            recognized_any = True
            continue

        color = _lower_hex(part)
        if color is not None:
            mapped["border_color"] = color
            recognized_any = True
            continue

        unparsed.append(part)

    return mapped, recognized_any, unparsed


def _split_padding(value: str) -> dict[str, int]:
    parsed = [_pixel_int(part) for part in value.split()]
    if not parsed or any(part is None for part in parsed):
        return {}
    pixels = [int(part) for part in parsed if part is not None]
    if len(pixels) == 1:
        return {"padding": pixels[0]}
    if len(pixels) == 2:
        return {
            "padding_top": pixels[0],
            "padding_bottom": pixels[0],
            "padding_left": pixels[1],
            "padding_right": pixels[1],
        }
    if len(pixels) == 3:
        return {
            "padding_top": pixels[0],
            "padding_left": pixels[1],
            "padding_right": pixels[1],
            "padding_bottom": pixels[2],
        }
    return {
        "padding_top": pixels[0],
        "padding_right": pixels[1],
        "padding_bottom": pixels[2],
        "padding_left": pixels[3],
    }


def _expand_box_values(parts: list[object]) -> list[object]:
    if len(parts) == 1:
        return [parts[0], parts[0], parts[0], parts[0]]
    if len(parts) == 2:
        return [parts[0], parts[1], parts[0], parts[1]]
    if len(parts) == 3:
        return [parts[0], parts[1], parts[2], parts[1]]
    return [parts[0], parts[1], parts[2], parts[3]]


def _split_border_widths(value: str) -> dict[str, int]:
    parsed = [_pixel_int(part) for part in value.split()]
    if not parsed or any(part is None for part in parsed):
        return {}
    widths = [int(part) for part in parsed if part is not None]
    if len(widths) == 1:
        return {"border_width": widths[0]}
    return {
        f"border_width_{side}": width
        for side, width in zip(BOX_SIDES, _expand_box_values(widths), strict=True)
    }


def _split_border_styles(value: str) -> dict[str, str]:
    styles = [part.lower() for part in value.split()]
    if not styles or any(style not in SUPPORTED_BORDER_STYLES for style in styles):
        return {}
    if len(styles) == 1:
        return {"border_style": styles[0]}
    return {
        f"border_style_{side}": style
        for side, style in zip(BOX_SIDES, _expand_box_values(styles), strict=True)
    }


def _split_border_colors(value: str) -> dict[str, str]:
    colors = [_lower_hex(part) for part in value.split()]
    if not colors or any(color is None for color in colors):
        return {}
    parsed = [str(color) for color in colors if color is not None]
    if len(parsed) == 1:
        return {"border_color": parsed[0]}
    return {
        f"border_color_{side}": color
        for side, color in zip(BOX_SIDES, _expand_box_values(parsed), strict=True)
    }


def _split_border_radius(value: str) -> dict[str, int]:
    parsed = [_pixel_int(part) for part in value.split()]
    if not parsed or any(part is None for part in parsed):
        return {}
    radii = [int(part) for part in parsed if part is not None]
    if len(radii) == 1:
        return {"border_radius": radii[0]}
    return {
        field: radius
        for field, radius in zip(RADIUS_FIELDS, _expand_box_values(radii), strict=True)
    }


def _split_box_shadow(value: str) -> dict[str, object]:
    parts = value.split()
    if not parts:
        return {}
    shadow_style = "outset"
    inset_index = next((index for index, part in enumerate(parts) if part.lower() == "inset"), None)
    if inset_index is not None:
        shadow_style = "inset"
        parts = [part for index, part in enumerate(parts) if index != inset_index]
    lengths: list[int] = []
    color_parts: list[str] = []
    for part in parts:
        pixel = _css_length_int(part)
        if pixel is not None and not color_parts and len(lengths) < 4:
            lengths.append(pixel)
        else:
            color_parts.append(part)
    if len(lengths) < 2:
        return {}
    color = " ".join(color_parts).strip()
    mapped: dict[str, object] = {
        "shadow_style": shadow_style,
        "shadow_h": lengths[0],
        "shadow_v": lengths[1],
    }
    if len(lengths) >= 3:
        mapped["shadow_blur"] = lengths[2]
    if len(lengths) >= 4:
        mapped["shadow_spread"] = lengths[3]
    if color:
        mapped["shadow_color"] = color.lower()
    return mapped


def _selector_label(selector: str, element_type: str) -> str:
    cleaned = selector.strip().lstrip(".#")
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", cleaned) if part]
    if parts and parts[0].lower() in {element_type.lower(), "btn"}:
        parts = parts[1:]
    return " ".join(part.capitalize() for part in parts) or "Imported"


def _map_declarations(declarations: dict[str, str]) -> tuple[dict[str, object], list[dict[str, str]]]:
    mapped: dict[str, object] = {}
    unsupported: list[dict[str, str]] = []

    for property_name, raw_value in declarations.items():
        value = raw_value.strip()

        if property_name == "background-color":
            color = _lower_hex(value)
            if color is not None:
                mapped["bg_color"] = color
                continue
        elif property_name == "color":
            color = _lower_hex(value)
            if color is not None:
                mapped["font_color"] = color
                continue
        elif property_name == "border-radius":
            radius = _split_border_radius(value)
            if radius:
                mapped.update(radius)
                continue
        elif property_name in RADIUS_CORNERS:
            radius = _pixel_int(value)
            if radius is not None:
                mapped[RADIUS_CORNERS[property_name]] = radius
                continue
        elif property_name == "border":
            border, recognized, unparsed = _split_border(value)
            if recognized:
                mapped.update(border)
                if unparsed:
                    unsupported.append({"property": property_name, "value": " ".join(unparsed)})
                continue
        elif property_name in {"border-top", "border-right", "border-bottom", "border-left"}:
            border, recognized, unparsed = _split_border(value)
            if recognized:
                side = property_name.removeprefix("border-")
                suffix = SIDE_SUFFIXES[side]
                if "border_width" in border:
                    mapped[f"border_width_{suffix}"] = border["border_width"]
                if "border_style" in border:
                    mapped[f"border_style_{suffix}"] = border["border_style"]
                if "border_color" in border:
                    mapped[f"border_color_{suffix}"] = border["border_color"]
                if unparsed:
                    unsupported.append({"property": property_name, "value": " ".join(unparsed)})
                continue
        elif property_name == "border-color":
            colors = _split_border_colors(value)
            if colors:
                mapped.update(colors)
                continue
        elif property_name == "border-width":
            widths = _split_border_widths(value)
            if widths:
                mapped.update(widths)
                continue
        elif property_name == "border-style":
            styles = _split_border_styles(value)
            if styles:
                mapped.update(styles)
                continue
        elif property_name in {
            "border-top-color",
            "border-right-color",
            "border-bottom-color",
            "border-left-color",
        }:
            color = _lower_hex(value)
            if color is not None:
                side = property_name.removeprefix("border-").removesuffix("-color")
                mapped[f"border_color_{SIDE_SUFFIXES[side]}"] = color
                continue
        elif property_name in {
            "border-top-width",
            "border-right-width",
            "border-bottom-width",
            "border-left-width",
        }:
            width = _pixel_int(value)
            if width is not None:
                side = property_name.removeprefix("border-").removesuffix("-width")
                mapped[f"border_width_{SIDE_SUFFIXES[side]}"] = width
                continue
        elif property_name in {
            "border-top-style",
            "border-right-style",
            "border-bottom-style",
            "border-left-style",
        }:
            style = value.lower()
            if style in SUPPORTED_BORDER_STYLES:
                side = property_name.removeprefix("border-").removesuffix("-style")
                mapped[f"border_style_{SIDE_SUFFIXES[side]}"] = style
                continue
        elif property_name == "font-size":
            size = _pixel_int(value)
            if size is not None:
                mapped["font_size"] = size
                continue
        elif property_name == "font-weight":
            mapped["font_weight"] = value
            continue
        elif property_name == "box-shadow":
            shadow = _split_box_shadow(value)
            if shadow:
                mapped.update(shadow)
                continue
        elif property_name == "padding":
            padding = _split_padding(value)
            if padding:
                mapped.update(padding)
                continue
        elif property_name in {"padding-top", "padding-right", "padding-bottom", "padding-left"}:
            padding = _pixel_int(value)
            if padding is not None:
                mapped[property_name.replace("-", "_")] = padding
                continue

        unsupported.append({"property": property_name, "value": value})

    return mapped, unsupported


def map_rules_to_style_candidate(
    rules: Iterable[ExtractedStyleRule],
    *,
    style_prefix: str,
    element_type: str,
    selector: str,
) -> BubbleStyleCandidate:
    base: dict[str, object] = {}
    states: dict[str, dict[str, object]] = {}
    unsupported: list[dict[str, str]] = []

    for rule in rules:
        mapped, skipped = _map_declarations(rule.declarations)
        unsupported.extend({"state": rule.state, **item} for item in skipped)

        if rule.state == "base":
            base.update(mapped)
        elif mapped:
            states.setdefault(rule.state, {}).update(mapped)

    return BubbleStyleCandidate(
        name=f"{style_prefix} {element_type} {_selector_label(selector, element_type)}",
        element_type=element_type,
        selector=selector,
        base=base,
        states=states,
        unsupported=unsupported,
    )
