from typing import Any

import pytest

from bubble_mcp.aria_runtime import bubble_sdk
from bubble_mcp.aria_runtime.bubble_sdk import ElementBuilder


class FixedIds:
    def element_id(self) -> str:
        return "bELEMENT"


@pytest.fixture
def builder() -> ElementBuilder:
    return ElementBuilder(FixedIds())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "column"),
        ("align parent", "align_to_parent"),
        ("align-to-parent", "align_to_parent"),
        ("relative", "relative"),
        ("fixed", "fixed"),
        ("row", "row"),
        ("unsupported", "column"),
    ],
)
def test_container_layout_normalization(value: Any, expected: str) -> None:
    assert ElementBuilder._normalize_container_layout(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (12, "12px"),
        (12.5, "12.5px"),
        ("", None),
        (" 25% ", "25%"),
        ("18", "18px"),
        ("calc(100% - 2rem)", "calc(100% - 2rem)"),
    ],
)
def test_css_length_normalization(value: Any, expected: str | None) -> None:
    assert ElementBuilder._normalize_css_length(value) == expected


def test_dimension_helpers_apply_explicit_constraints_and_width_unset() -> None:
    props = {"%w": 100, "min_width_css": "default", "max_width_css": "default"}
    returned = ElementBuilder._apply_dimensions(
        props,
        {
            "min_width": 120,
            "max_width": "80%",
            "fit_width": True,
            "fixed_width": True,
            "min_height": "40",
            "max_height": "90px",
            "fit_height": True,
            "fixed_height": True,
        },
    )
    assert returned is props
    assert props == {
        "%w": 100,
        "min_width_css": "120px",
        "max_width_css": "80%",
        "fit_width": False,
        "fixed_width": True,
        "single_width": True,
        "min_height_css": "40px",
        "max_height_css": "90px",
        "fit_height": False,
        "fixed_height": True,
        "single_height": True,
        "__explicit_dims": [
            "min_width",
            "max_width",
            "fit_width",
            "fixed_width",
            "min_height",
            "max_height",
            "fit_height",
            "fixed_height",
        ],
    }
    assert ElementBuilder._apply_width_unset(props) is props
    assert "%w" not in props
    assert props["min_width_css"] == "120px"
    assert props["max_width_css"] == "80%"

    defaults = {"%w": 100, "min_width_css": "1px", "max_width_css": "2px"}
    ElementBuilder._apply_width_unset(defaults)
    assert defaults == {}
    assert ElementBuilder._apply_width_unset("invalid") == "invalid"  # type: ignore[arg-type]


def test_visual_properties_cover_full_wire_vocabulary(builder: ElementBuilder, capsys) -> None:  # type: ignore[no-untyped-def]
    expression = {"%x": "TextExpression", "%e": {"0": "hero"}}
    props: dict[str, Any] = {}
    kwargs = {
        "margin_top": 1,
        "margin_bottom": 2,
        "margin_left": 3,
        "margin_right": 4,
        "top": 5,
        "left": 6,
        "bottom": 7,
        "right": 8,
        "visible": 0,
        "collapse_when_hidden": 1,
        "title_attribute": "Title",
        "button_disabled": 1,
        "spin_icon": 0,
        "rotation_angle": "45",
        "zindex": "12",
        "html_id": expression,
        "padding_top": 9,
        "padding_bottom": 10,
        "padding_left": 11,
        "padding_right": 12,
        "four_border_style": False,
        "all_4_borders": True,
        "border_type": "independent",
        "border_style": "solid",
        "border_width": 2,
        "border_color": "black",
        "border_radius": 6,
        "border_style_top": "dashed",
        "border_style_bottom": "dotted",
        "border_style_left": "solid",
        "border_style_right": "none",
        "border_width_top": 1,
        "border_width_bottom": 2,
        "border_width_left": 3,
        "border_width_right": 4,
        "border_color_top": "one",
        "border_color_bottom": "two",
        "border_color_left": "three",
        "border_color_right": "four",
        "border_roundness_top": 1,
        "border_roundness_bottom": 2,
        "border_roundness_left": 3,
        "border_roundness_right": 4,
        "border_roundness_top_left": 5,
        "border_roundness_top_right": 6,
        "border_roundness_bottom_left": 7,
        "border_roundness_bottom_right": 8,
        "shadow_style": "outset",
        "shadow_h": 1,
        "shadow_v": 2,
        "shadow_blur": 3,
        "shadow_spread": 4,
        "shadow_color": "gray",
        "bg_color": "white",
        "gradient_start_color": "red",
        "gradient_end_color": "blue",
        "gradient_mid_color": "purple",
        "gradient_style": "radial",
        "gradient_shape": "circle",
        "gradient_size": "closest-side",
        "gradient_xpos": 25,
        "gradient_ypos": 75,
        "background_image": expression,
        "background_color_if_empty_image": "white",
        "crop_responsive": 1,
        "background_size_cover": 0,
        "center_background": 1,
        "repeat_background_vertical": 0,
        "repeat_background_horizontal": 1,
        "text_color": "initial",
        "font_color": "navy",
        "placeholder_color": "silver",
        "font_family": "Inter",
        "font_weight": 600,
        "font_size": 18,
        "font_face": "normal",
        "font_alignment": "center",
        "letter_spacing": 0.2,
        "line_height": 1.4,
        "word_spacing": 1,
        "bold": True,
        "italic": False,
        "underline": True,
        "vertical_centering": True,
        "no_bbcode": True,
        "recognize_links": True,
        "link_color": "teal",
        "nofollow": False,
        "text_shadow": True,
        "text_shadow_h": 1,
        "text_shadow_v": 2,
        "text_shadow_blur": 3,
        "text_shadow_color": "black",
        "icon_color": "green",
        "icon_size": 20,
        "icon_placement": "left",
        "gap": 6,
        "display_as_iframe": True,
        "wait_until_visible": False,
        "min_width_css": "10px",
        "max_width_css": "20px",
        "min_height_css": "30px",
        "max_height_css": "40px",
        "single_width": False,
        "single_height": True,
        "fit_width": False,
        "fit_height": True,
        "opacity": 0.5,
        "overflow_scroll": True,
        "horiz_alignment": "center",
        "vert_alignment": "stretch",
        "nonant_alignment": "bottom_right",
        "container_horiz_alignment": "center",
        "container_vert_alignment": "top",
        "order": "7",
        "ignored_null": None,
    }

    builder._add_visual_props(props, kwargs)

    assert "Applied margins" in capsys.readouterr().out
    assert props["%iv"] is False
    assert props["rotation_angle"] == 45
    assert props["%z"] == 12
    assert props["unique_id"] is expression
    assert props["four_border_style"] is True
    assert props["%br"] == props["border_roundness"] == 6
    assert props["%bgd"] == "radial"
    assert props["background_radial_gradient_shape"] == "circle"
    assert props["%bas"] == "gradient"
    assert props["%bgi"] is expression
    assert props["%fc"] == "navy"
    assert props["font_weight"] == "600"
    assert props["%ic"] == props["icon_color"] == "green"
    assert props["button_gap"] == 6
    assert props["defer_drawing"] is False
    assert props["align_to_parent_pos"] == "bottom_right"
    assert props["order"] == 7
    assert "ignored_null" not in props


def test_visual_property_aliases_and_invalid_numeric_values(builder: ElementBuilder) -> None:
    scalar_image: dict[str, Any] = {}
    builder._add_visual_props(
        scalar_image,
        {
            "rotation_angle": "auto",
            "zindex": "front",
            "unique_id": "hero",
            "border_type": "shared",
            "bg_style": "image",
            "gradient_direction": "left",
            "gradient_angle": 30,
            "bg_image": "https://example.com/image.png",
            "%cb": True,
            "%rbv": True,
            "%rbh": False,
            "button_gap": 8,
            "defer_drawing": True,
        },
    )
    assert scalar_image["rotation_angle"] == "auto"
    assert scalar_image["%z"] == "front"
    assert scalar_image["unique_id"]["%e"]["0"] == "hero"
    assert scalar_image["four_border_style"] is False
    assert scalar_image["%bgd"] == "linear"
    assert scalar_image["%b4"] == "custom"
    assert scalar_image["%bga"] == 30
    assert scalar_image["%bgi"]["%e"]["0"] == "https://example.com/image.png"
    assert scalar_image["%cb"] is True
    assert scalar_image["%rbv"] is True
    assert scalar_image["%rbh"] is False

    dict_image: dict[str, Any] = {}
    image_expression = {"%x": "ImageExpression"}
    builder._add_visual_props(dict_image, {"bg_image": image_expression})
    assert dict_image["%bgi"] is image_expression

    directional: dict[str, Any] = {}
    builder._add_visual_props(directional, {"gradient_direction": "right"})
    assert directional["%bgd"] == "linear"
    assert directional["%b4"] == "right"

    radial_direction: dict[str, Any] = {}
    builder._add_visual_props(
        radial_direction,
        {"background_style": "gradient", "gradient_direction": "radial"},
    )
    assert radial_direction["%bas"] == "gradient"
    assert radial_direction["%bgd"] == "radial"


def test_style_resolution_and_default_style_guards(builder: ElementBuilder) -> None:
    assert builder._resolve_style_ref({"style": " custom-style "}) == "custom-style"
    assert builder._resolve_style_ref({"style": "none", "style_id": "fallback"}) == "fallback"
    assert builder._resolve_style_ref({"%s1": "undefined"}) is None
    assert builder._resolve_style_ref({"style": ""}) is None
    assert builder._resolve_style_ref({}, explicit_style=123) == "123"

    assert builder._has_non_default_text_visual_overrides({}, {}) is False
    assert builder._has_non_default_text_visual_overrides({"%fc": "red"}, {}) is True
    assert builder._has_non_default_text_visual_overrides({"%fs": 20}, {}) is True
    assert builder._has_non_default_text_visual_overrides({"font_weight": 700}, {}) is True
    assert builder._has_non_default_text_visual_overrides({"%fa": "center"}, {}) is True
    assert builder._has_non_default_text_visual_overrides(
        {"horiz_alignment": "center"}, {}
    ) is True
    assert builder._has_non_default_text_visual_overrides({"%bs": "outset"}, {}) is True
    assert builder._has_non_default_text_visual_overrides({}, {"gradient_angle": 20}) is True

    assert builder._has_button_visual_overrides({}, {}) is False
    assert builder._has_button_visual_overrides({"%bgc": "red"}, {}) is True
    assert builder._has_button_visual_overrides({}, {"padding_top": 4}) is True

    assert builder._resolve_default_text_style_ref({}, {}) == "Text_body_small_"
    assert builder._resolve_default_text_style_ref({}, {"style": "Text_custom"}) == "Text_custom"
    assert builder._resolve_default_text_style_ref({"%fc": "red"}, {}) is None
    assert builder._resolve_default_button_style_ref({}, {}) == "Button_primary_button_"
    assert builder._resolve_default_button_style_ref({}, {"style": "Button_custom"}) == "Button_custom"
    assert builder._resolve_default_button_style_ref({"%bgc": "red"}, {}) is None


def test_typography_pruning_respects_style_and_explicit_overrides(builder: ElementBuilder) -> None:
    untouched = {"%fs": 16}
    builder._prune_typography_overrides_for_style(untouched, {}, style_applied=False)
    assert untouched == {"%fs": 16}

    kept = {"%fs": 16}
    builder._prune_typography_overrides_for_style(
        kept,
        {"style": "Text_custom", "keep_overrides": True},
        style_applied=False,
    )
    assert kept == {"%fs": 16}

    explicit = {"%fs": 18}
    builder._prune_typography_overrides_for_style(
        explicit,
        {"style": "Text_custom", "font_size": 18},
        style_applied=True,
    )
    assert explicit == {"%fs": 18}

    pruned = {
        "%fs": 16,
        "font_size": 16,
        "%fc": "black",
        "font_color": "black",
        "unrelated": True,
    }
    builder._prune_typography_overrides_for_style(
        pruned,
        {"style_id": "Text_custom"},
        style_applied=False,
    )
    assert pruned == {"unrelated": True}


def test_text_builder_handles_dynamic_parts_and_explicit_typography(
    builder: ElementBuilder,
) -> None:
    text = builder.text(
        "Greeting",
        "Hello Current user's name - Current date/time: extract year!",
        horiz_alignment="right",
        width=300,
        height=80,
        width_unset=False,
        font_size=18,
        font_weight=600,
        line_height="invalid",
        text_color="navy",
        font_alignment="right",
        extra_props={"custom": True},
    )
    props = text["%p"]
    entries = props["%3"]["%e"]
    assert entries["0"] == "Hello "
    assert entries["1"]["%x"] == "CurrentUser"
    assert entries["2"] == " - "
    assert entries["3"]["%x"] == "CurrentDateTime"
    assert entries["4"] == "!"
    assert props["%h"] == 80
    assert props["%fs"] == props["font_size"] == 18
    assert props["font_weight"] == "600"
    assert props["line_height"] == "invalid"
    assert props["%fc"] == props["font_color"] == "navy"
    assert props["font_alignment"] == props["%fa"] == "right"
    assert props["horiz_alignment"] == "right"
    assert props["custom"] is True

    numeric_line_height = builder.text(
        "Body",
        "Body",
        width_unset=False,
        line_height="1.5",
    )["%p"]
    assert numeric_line_height["line_height"] == "1.5"


def test_text_builder_centers_literal_and_dynamic_content(builder: ElementBuilder) -> None:
    literal = builder.text(
        "Centered",
        "Hello",
        horiz_alignment="center",
        width_unset=False,
    )
    assert literal["%p"]["%3"]["%e"] == {"0": "[center]Hello[/center]"}
    assert "horiz_alignment" not in literal["%p"]

    dynamic = builder.text(
        "Centered Dynamic",
        "Current user's name",
        horiz_alignment="center",
        width_unset=False,
    )
    assert dynamic["%p"]["%3"]["%e"]["0"] == "[center]"
    assert dynamic["%p"]["%3"]["%e"]["1"]["%x"] == "CurrentUser"
    assert dynamic["%p"]["%3"]["%e"]["2"] == "[/center]"


def test_text_builder_dynamic_fallback_and_centering_edge_cases(
    monkeypatch,
    builder: ElementBuilder,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        bubble_sdk.DynamicTextBuilder,
        "build",
        staticmethod(lambda _parts: {"%x": "TextExpression", "%e": {}}),
    )
    empty = builder.text(
        "Empty",
        "Current user's name",
        horiz_alignment="center",
        width_unset=False,
    )
    assert empty["%p"]["%3"]["%e"] == {"0": "[center][/center]"}

    monkeypatch.setattr(
        bubble_sdk.DynamicTextBuilder,
        "build",
        staticmethod(lambda _parts: {"unexpected": True}),
    )
    unexpected = builder.text(
        "Unexpected",
        "Current user's name",
        horiz_alignment="center",
        width_unset=False,
    )
    assert unexpected["%p"]["%3"] == {"unexpected": True}

    def fail(_parts: list[Any]) -> Any:
        raise ValueError("invalid dynamic expression")

    monkeypatch.setattr(bubble_sdk.DynamicTextBuilder, "build", staticmethod(fail))
    fallback = builder.text("Fallback", "Current user's name", width_unset=False)
    assert fallback["%p"]["%3"]["%e"] == {"0": "Current user's name"}


def test_text_builder_keeps_center_alignment_when_overrides_are_requested(
    builder: ElementBuilder,
) -> None:
    props = builder.text(
        "Centered Override",
        "Hello",
        horiz_alignment="center",
        width_unset=False,
        keep_overrides=True,
    )["%p"]
    assert props["horiz_alignment"] == "center"
    assert props["%fa"] == "center"
