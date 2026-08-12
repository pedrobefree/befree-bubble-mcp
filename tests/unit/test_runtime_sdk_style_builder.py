from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import StyleBuilder


class FixedIds:
    def element_id(self) -> str:
        return "bSTYLE"


@pytest.fixture
def builder() -> StyleBuilder:
    return StyleBuilder(FixedIds())


def property_changes(changes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        change["path"][3]: change["body"]
        for change in changes
        if len(change.get("path", [])) >= 4 and change["path"][2] == "%p"
    }


@pytest.mark.parametrize(
    ("element_type", "internal_type"),
    [
        ("SearchBox", "AutocompleteDropdown"),
        ("Popup", "Popup"),
        ("DateInput", "DateInput"),
        ("Button", "Button"),
    ],
)
def test_create_style_normalizes_element_types(
    builder: StyleBuilder,
    element_type: str,
    internal_type: str,
) -> None:
    style = builder.create_style("Primary", element_type=element_type)
    assert style["id"] == f"{internal_type}_bSTYLE"
    assert style["%d"] == "Primary"
    assert style["%x"] == internal_type
    assert style["%s"] == {}
    assert style["%p"]["%fc"] == "#000000"
    assert style["%p"]["%fs"] == 14
    assert style["%p"]["font_family"] == "Inter"


def test_create_style_applies_padding_aliases_background_alias_and_transitions(
    builder: StyleBuilder,
) -> None:
    transition = {"duration": 180, "fn": "ease-out"}
    style = builder.create_style(
        "Card",
        padding=12,
        padding_left=20,
        background_color="red",
        transitions={"bg_color": transition, "custom_property": {"duration": 50}},
        custom_literal="value",
    )
    props = style["%p"]
    assert props["padding_top"] == 12
    assert props["padding_bottom"] == 12
    assert props["padding_left"] == 20
    assert props["padding_right"] == 12
    assert props["%bgc"] == "red"
    assert "%bas" not in props
    assert props["custom_literal"] == "value"
    assert style["transitions"] == {
        "%bas": transition,
        "custom_property": {"duration": 50},
    }


def test_update_style_returns_no_changes_without_values(builder: StyleBuilder) -> None:
    assert builder.update_style("style") == []


def test_update_style_covers_background_layout_and_specialized_properties(
    builder: StyleBuilder,
) -> None:
    changes = builder.update_style(
        "style",
        background_color="red",
        gradient_start_color="one",
        gradient_end_color="two",
        gradient_mid_color="middle",
        gradient_direction="left",
        gradient_angle=45,
        background_image="image",
        background_repeat="repeat",
        background_color_if_empty_image="white",
        crop_responsive=1,
        background_size_cover=0,
        center_background=1,
        repeat_background_vertical=0,
        repeat_background_horizontal=1,
        separator_style="solid",
        separator_width=2,
        separator_color="gray",
        container_layout="row",
        fit_width=True,
        fit_height=False,
        min_width_css="100px",
        max_width_css="90%",
        min_height_css="20px",
        max_height_css="80%",
        single_width=True,
        single_height=False,
        use_gap=True,
        row_gap=8,
        column_gap=12,
        nonant_alignment="center",
        date_format="yyyy-mm-dd",
        custom_format="YYYY",
        range_type=" RANGE ",
        slider_background_color="track",
        handle_color="handle",
        range_area_color="area",
        center_text_vertically=True,
    )
    props = property_changes(changes)
    assert props["%bas"] == "bgcolor"
    assert props["%bgc"] == "red"
    assert props["%bgf"] == "one"
    assert props["%bgt"] == "two"
    assert props["background_gradient_mid"] == "middle"
    assert props["%bgd"] == "left"
    assert props["%b4"] == "left"
    assert props["%bga"] == 45
    assert props["background_gradient_custom_angle"] == 45
    assert props["crop_responsive"] is True
    assert props["background_size_cover"] is False
    assert props["%cb"] is True
    assert props["%rbv"] is False
    assert props["%rbh"] is True
    assert props["%ss"] == "solid"
    assert props["%sw"] == 2
    assert props["%sc"] == "gray"
    assert props["container_layout"] == "row"
    assert props["fit_width"] is True
    assert props["fit_height"] is False
    assert props["column_gap"] == 12
    assert props["range_type"] == "range"
    assert props["background_color"] == "track"
    assert props["%vc"] is True


def test_update_style_preserves_explicit_background_and_disabled_defaults(
    builder: StyleBuilder,
) -> None:
    props = property_changes(
        builder.update_style(
            "style",
            bg_color="red",
            background_style="gradient",
            inject_defaults=False,
        )
    )
    assert props == {"%bas": "gradient", "%bgc": "red"}

    without_style = property_changes(
        builder.update_style("style", bg_color="red", inject_defaults=False)
    )
    assert without_style == {"%bgc": "red"}


def test_update_style_covers_shadow_branches(builder: StyleBuilder) -> None:
    enabled = property_changes(
        builder.update_style(
            "style",
            shadow_style="outset",
            shadow_h=1,
            shadow_v=2,
            shadow_blur=3,
            shadow_spread=4,
            shadow_color="black",
        )
    )
    assert enabled == {
        "%bs": "outset",
        "%bh": 1,
        "%bv": 2,
        "%bsb": 3,
        "%bsp": 4,
        "boxshadow_enable": True,
        "%bsc": "black",
    }

    disabled = property_changes(builder.update_style("style", shadow_style="none"))
    assert disabled == {"%bs": "none", "boxshadow_enable": False}

    spread = property_changes(builder.update_style("style", shadow_spread=7))
    assert spread == {"%bsp": 7}

    no_default = property_changes(
        builder.update_style("style", shadow_style="outset", inject_defaults=False)
    )
    assert no_default == {"%bs": "outset"}


def test_update_style_covers_typography_icon_and_layout(builder: StyleBuilder) -> None:
    props = property_changes(
        builder.update_style(
            "style",
            font_color="navy",
            placeholder_color="silver",
            icon_size=20,
            font_size=16,
            font_family="Inter",
            font_weight="600",
            font_face="normal",
            alignment="center",
            bold=True,
            italic=False,
            underline=True,
            word_spacing=1.5,
            line_height=1.4,
            letter_spacing="0.25",
            text_shadow=True,
            text_shadow_h=1,
            text_shadow_v=2,
            text_shadow_blur=3,
            text_shadow_color="gray",
            tag="h2",
            padding_top=1,
            padding_bottom=2,
            padding_left=3,
            padding_right=4,
            gap=8,
        )
    )
    assert props["%fc"] == "navy"
    assert props["%ic"] == "navy"
    assert props["placeholder_color"] == "silver"
    assert props["icon_size"] == 20
    assert props["%fs"] == 16
    assert props["%ls"] == 0.25
    assert props["%tes"] is True
    assert props["tag_type"] == "h2"
    assert props["button_gap"] == 8

    explicit_icon = property_changes(
        builder.update_style("style", font_color="navy", icon_color="red")
    )
    assert explicit_icon["%ic"] == "red"


@pytest.mark.parametrize(("border_type", "expected"), [("independent", True), ("shared", False)])
def test_update_style_covers_shared_and_independent_borders(
    builder: StyleBuilder,
    border_type: str,
    expected: bool,
) -> None:
    props = property_changes(
        builder.update_style(
            "style",
            border_color="black",
            border_width=2,
            border_radius=8,
            border_style="solid",
            border_type=border_type,
            border_style_top="dashed",
            border_style_bottom="dotted",
            border_style_left="solid",
            border_style_right="none",
            border_color_top="one",
            border_color_bottom="two",
            border_color_left="three",
            border_color_right="four",
            border_width_top=1,
            border_width_bottom=2,
            border_width_left=3,
            border_width_right=4,
            radius_top_left=5,
            radius_top_right=6,
            radius_bottom_right=7,
            radius_bottom_left=8,
        )
    )
    assert props["four_border_style"] is expected
    assert props["%bc"] == "black"
    assert props["border_style_top"] == "dashed"
    assert props["border_color_right"] == "four"
    assert props["border_width_left"] == 3
    assert props["border_roundness_top"] == 5
    assert props["border_roundness_right"] == 6
    assert props["border_roundness_bottom"] == 7
    assert props["border_roundness_left"] == 8


def test_transition_mapping_targets_wire_properties(builder: StyleBuilder) -> None:
    transition = {"duration": 200, "fn": "ease"}
    changes = builder.update_style(
        "style",
        transitions={
            "background_style": transition,
            "background_color": transition,
            "bg_color": transition,
            "font_color": transition,
            "box_shadow": transition,
            "custom": transition,
        },
    )
    paths = [change["path"] for change in changes]
    assert paths.count(["styles", "style", "transitions", "%bas"]) == 3
    assert ["styles", "style", "transitions", "%bgc"] not in paths
    assert ["styles", "style", "transitions", "%fc"] in paths
    assert ["styles", "style", "transitions", "%bs"] in paths
    assert ["styles", "style", "transitions", "custom"] in paths


@pytest.mark.parametrize(
    ("condition_type", "message"),
    [
        ("hover", "is_hovered"),
        ("focus", "is_focused"),
        ("pressed", "is_pressed"),
        ("hidden", "isnt_visible"),
        ("invalid", "isnt_valid"),
        ("disabled", "isnt_clickable"),
        ("custom", "custom"),
    ],
)
def test_condition_node_aliases(condition_type: str, message: str) -> None:
    assert StyleBuilder._build_condition_node(condition_type) == {
        "%x": "Message",
        "%nm": message,
        "is_slidable": False,
    }


def test_complex_condition_builds_recursive_operator_tree() -> None:
    assert StyleBuilder._build_complex_condition([]) == {}

    condition = StyleBuilder._build_complex_condition(
        [("hover", "and_"), ("focus", "invalid"), ("disabled", None)]
    )
    assert condition["%n"]["%nm"] == "is_hovered"
    first_operator = condition["%n"]["%n"]
    assert first_operator["%nm"] == "and_"
    focus = first_operator["%a"]["%n"]
    assert focus["%nm"] == "is_focused"
    fallback_operator = focus["%n"]
    assert fallback_operator["%nm"] == "or_"
    assert fallback_operator["%a"]["%n"]["%nm"] == "isnt_clickable"


def test_add_style_condition_normalizes_string_and_padding() -> None:
    properties = {"padding": 12, "padding_left": 20, "bg_color": "red"}
    changes = StyleBuilder.add_style_condition(
        "style",
        "state",
        "hover, focus",
        properties,
    )
    assert properties == {"padding": 12, "padding_left": 20, "bg_color": "red"}
    assert changes[0]["intent"] == "NewStyleState"
    assert changes[1]["body"]["%x"] == "ThisElement"
    assert changes[2]["body"]["%n"]["%nm"] == "is_hovered"
    assert changes[2]["body"]["%n"]["%n"]["%nm"] == "or_"

    writes = {
        tuple(change["path"]): change["body"]
        for change in changes
        if change["intent"] == "SetStyleStateData"
        and change["body"] != {"%x": "Empty"}
    }
    assert writes[("styles", "style", "%s", "state", "%p", "padding_top")] == 12
    assert writes[("styles", "style", "%s", "state", "%p", "padding_left")] == 20
    assert writes[("styles", "style", "%s", "state", "%p", "%bgc")] == "red"


@pytest.mark.parametrize(
    "condition_type",
    [
        ["hover", "focus"],
        [("hover", "and_"), ("focus", None)],
        [],
    ],
)
def test_add_style_condition_accepts_list_forms_without_creating_state(
    condition_type: list[Any],
) -> None:
    changes = StyleBuilder.add_style_condition(
        "style",
        "state",
        condition_type,
        {"font_color": "red"},
        is_new=False,
    )
    assert all(change["intent"] != "NewStyleState" for change in changes)
    assert changes[0]["intent"] == "SetStyleStateCondition"
    assert changes[1]["intent"] == "SetStyleStateCondition"


def test_apply_theme_maps_states_and_auto_injects_transitions(builder: StyleBuilder) -> None:
    changes = builder.apply_theme(
        "style",
        {
            "base": {"font_size": 16},
            "hover": {"bg_color": "red", "font_color": "white"},
            "focused": {"border_color": "blue"},
            "disabled": {"opacity": 0.5},
            "active": {"shadow_style": "outset"},
            "pressed": {},
            "unknown": {"font_color": "ignored"},
        },
    )
    new_states = [change for change in changes if change.get("intent") == "NewStyleState"]
    assert [change["path"][3] for change in new_states] == [
        "sthove",
        "stfocu",
        "stnotc",
        "stpres",
    ]

    transition_paths = {
        tuple(change["path"])
        for change in changes
        if change.get("intent") == "AddTransition"
    }
    assert transition_paths == {
        ("styles", "style", "transitions", "%bas"),
        ("styles", "style", "transitions", "%fc"),
        ("styles", "style", "transitions", "%bc"),
        ("styles", "style", "transitions", "opacity"),
        ("styles", "style", "transitions", "%bs"),
    }

    assert builder.apply_theme("style", {}) == []


def test_reorder_states_emits_canonical_and_compatibility_intents() -> None:
    states = {"0": {"%x": "State"}}
    assert StyleBuilder.reorder_states("style", states) == [
        {
            "intent": "SetStyleData",
            "path": ["styles", "style", "%s"],
            "body": states,
        },
        {
            "intent": "ReorderState",
            "path": ["styles", "style", "%s"],
            "body": states,
        },
    ]
