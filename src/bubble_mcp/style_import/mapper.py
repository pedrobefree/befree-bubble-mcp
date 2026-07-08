from __future__ import annotations

import re
from colorsys import hls_to_rgb
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


def _pixel_float(value: str) -> float | None:
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)px\s*", value)
    if match is None:
        return None
    return float(match.group(1))


def _css_number(value: str) -> float | None:
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*", value)
    if match is None:
        return None
    return float(match.group(1))


def _round_metric(value: float) -> float:
    return round(value, 4)


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


def _linear_rgb_to_srgb(channel: float) -> float:
    if channel <= 0.0031308:
        return 12.92 * channel
    return 1.055 * (channel ** (1 / 2.4)) - 0.055


def _lab_to_css_color(value: str) -> str | None:
    match = re.fullmatch(
        r"lab\(\s*(-?[0-9.]+)%?\s+(-?[0-9.]+)\s+(-?[0-9.]+)(?:\s*/\s*([0-9.]+%?))?\s*\)",
        value.strip(),
        flags=re.I,
    )
    if match is None:
        return None

    lightness = float(match.group(1))
    a_axis = float(match.group(2))
    b_axis = float(match.group(3))
    fy = (lightness + 16) / 116
    fx = fy + a_axis / 500
    fz = fy - b_axis / 200

    def inverse_lab(t: float) -> float:
        delta = 6 / 29
        return t**3 if t > delta else 3 * delta**2 * (t - 4 / 29)

    # CSS Lab uses D50. Convert to sRGB through the standard D50 -> D65 matrix.
    x = 0.96422 * inverse_lab(fx)
    y = 1.00000 * inverse_lab(fy)
    z = 0.82521 * inverse_lab(fz)
    red_linear = 3.1338561 * x - 1.6168667 * y - 0.4906146 * z
    green_linear = -0.9787684 * x + 1.9161415 * y + 0.0334540 * z
    blue_linear = 0.0719453 * x - 0.2289914 * y + 1.4052427 * z
    red, green, blue = [
        max(0, min(255, round(_linear_rgb_to_srgb(channel) * 255)))
        for channel in (red_linear, green_linear, blue_linear)
    ]
    alpha = match.group(4)
    if alpha is None:
        return f"#{red:02x}{green:02x}{blue:02x}"
    alpha_value = alpha.strip()
    if alpha_value.endswith("%"):
        alpha_value = str(float(alpha_value.removesuffix("%")) / 100)
    return f"rgba({red}, {green}, {blue}, {alpha_value})"


def _oklab_to_css_color(value: str) -> str | None:
    match = re.fullmatch(
        r"oklab\(\s*(-?[0-9.]+%?)\s+(-?[0-9.]+%?)\s+(-?[0-9.]+%?)(?:\s*/\s*([0-9.]+%?))?\s*\)",
        value.strip(),
        flags=re.I,
    )
    if match is None:
        return None

    def oklab_component(raw_value: str, *, lightness: bool = False) -> float:
        text = raw_value.strip()
        if text.endswith("%"):
            value_float = float(text.removesuffix("%")) / 100
            return value_float if lightness else value_float * 0.4
        return float(text)

    lightness = oklab_component(match.group(1), lightness=True)
    a_axis = oklab_component(match.group(2))
    b_axis = oklab_component(match.group(3))

    long_l = lightness + 0.3963377774 * a_axis + 0.2158037573 * b_axis
    medium_l = lightness - 0.1055613458 * a_axis - 0.0638541728 * b_axis
    short_l = lightness - 0.0894841775 * a_axis - 1.2914855480 * b_axis

    long = long_l**3
    medium = medium_l**3
    short = short_l**3

    red_linear = 4.0767416621 * long - 3.3077115913 * medium + 0.2309699292 * short
    green_linear = -1.2684380046 * long + 2.6097574011 * medium - 0.3413193965 * short
    blue_linear = -0.0041960863 * long - 0.7034186147 * medium + 1.7076147010 * short
    red, green, blue = [
        max(0, min(255, round(_linear_rgb_to_srgb(channel) * 255)))
        for channel in (red_linear, green_linear, blue_linear)
    ]
    alpha = match.group(4)
    if alpha is None:
        return f"#{red:02x}{green:02x}{blue:02x}"
    alpha_value = alpha.strip()
    if alpha_value.endswith("%"):
        alpha_value = str(float(alpha_value.removesuffix("%")) / 100)
    return f"rgba({red}, {green}, {blue}, {alpha_value})"


def _css_color(value: str) -> str | None:
    hex_color = _lower_hex(value)
    if hex_color is not None:
        return hex_color
    rgb_match = re.fullmatch(
        r"rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})(?:\s*,\s*([0-9.]+))?\s*\)",
        value.strip(),
        flags=re.I,
    )
    if rgb_match is not None:
        red, green, blue = [max(0, min(255, int(rgb_match.group(index)))) for index in range(1, 4)]
        alpha = rgb_match.group(4)
        if alpha is None:
            return f"#{red:02x}{green:02x}{blue:02x}"
        return f"rgba({red}, {green}, {blue}, {alpha})"
    hsl_match = re.fullmatch(
        r"hsla?\(\s*([0-9.]+)(?:deg)?\s*,\s*([0-9.]+)%\s*,\s*([0-9.]+)%(?:\s*,\s*([0-9.]+))?\s*\)",
        value.strip(),
        flags=re.I,
    )
    if hsl_match is not None:
        hue = (float(hsl_match.group(1)) % 360) / 360
        saturation = max(0.0, min(1.0, float(hsl_match.group(2)) / 100))
        lightness = max(0.0, min(1.0, float(hsl_match.group(3)) / 100))
        red_float, green_float, blue_float = hls_to_rgb(hue, lightness, saturation)
        red, green, blue = [round(channel * 255) for channel in (red_float, green_float, blue_float)]
        alpha = hsl_match.group(4)
        if alpha is None:
            return f"#{red:02x}{green:02x}{blue:02x}"
        return f"rgba({red}, {green}, {blue}, {alpha})"
    lab_color = _lab_to_css_color(value)
    if lab_color is not None:
        return lab_color
    oklab_color = _oklab_to_css_color(value)
    if oklab_color is not None:
        return oklab_color
    return None


def _has_top_level_comma(value: str) -> bool:
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            return True
    return False


def _background_color(value: str) -> str | None:
    if _has_top_level_comma(value):
        return None
    return _css_color(value)


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

        color = _css_color(part)
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
    single_color = _css_color(value)
    if single_color is not None:
        return {"border_color": single_color}
    colors = [_css_color(part) for part in value.split()]
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


def _text_line_height(value: str, font_size_px: float | None) -> float | None:
    numeric = _css_number(value)
    if numeric is not None:
        return _round_metric(numeric)
    pixel = _pixel_float(value)
    if pixel is not None and font_size_px and font_size_px > 0:
        return _round_metric(pixel / font_size_px)
    percent_match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)%\s*", value)
    if percent_match is not None:
        return _round_metric(float(percent_match.group(1)) / 100)
    return None


def _text_letter_spacing(value: str, font_size_px: float | None) -> float | None:
    lowered = value.strip().lower()
    if lowered == "normal":
        return 0
    numeric = _css_number(lowered)
    if numeric is not None:
        return _round_metric(numeric)
    em_match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)em\s*", lowered)
    if em_match is not None:
        return _round_metric(float(em_match.group(1)))
    pixel = _pixel_float(lowered)
    if pixel is not None:
        if font_size_px and font_size_px > 0:
            return _round_metric(pixel / font_size_px)
        return _round_metric(pixel)
    return None


def _selector_label(selector: str, element_type: str) -> str:
    cleaned = selector.strip().lstrip(".#")
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", cleaned) if part]
    if parts and parts[0].lower() in {element_type.lower(), "btn"}:
        parts = parts[1:]
    return " ".join(part.capitalize() for part in parts) or "Imported"


def _map_declarations(declarations: dict[str, str]) -> tuple[dict[str, object], list[dict[str, str]]]:
    mapped: dict[str, object] = {}
    unsupported: list[dict[str, str]] = []
    font_size_px = _pixel_float(declarations.get("font-size", ""))

    for property_name, raw_value in declarations.items():
        value = raw_value.strip()

        if property_name == "background-color":
            color = _background_color(value)
            if color is not None:
                mapped["bg_color"] = color
                continue
        elif property_name == "background":
            color = _background_color(value)
            if color is not None:
                mapped["bg_color"] = color
                continue
            if _has_top_level_comma(value):
                unsupported.append({"property": property_name, "value": value, "reason": "multiple_backgrounds"})
                continue
            if "gradient(" in value.lower():
                unsupported.append({"property": property_name, "value": value, "reason": "gradient_not_mapped"})
                continue
        elif property_name == "color":
            color = _css_color(value)
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
            color = _css_color(value)
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
        elif property_name == "line-height":
            line_height = _text_line_height(value, font_size_px)
            if line_height is not None:
                mapped["line_height"] = line_height
                continue
        elif property_name == "letter-spacing":
            letter_spacing = _text_letter_spacing(value, font_size_px)
            if letter_spacing is not None:
                mapped["letter_spacing"] = letter_spacing
                continue
        elif property_name in {"bubble-tag", "tag", "html-tag"}:
            tag = value.lower()
            if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                mapped["tag"] = tag
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
