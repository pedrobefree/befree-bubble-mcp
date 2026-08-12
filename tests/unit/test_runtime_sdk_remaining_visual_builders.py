from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import ElementBuilder


class FixedIds:
    def element_id(self) -> str:
        return "bREMAINING"


def builder() -> ElementBuilder:
    return ElementBuilder(FixedIds())


def props(element: dict[str, Any]) -> dict[str, Any]:
    return element["%p"]


def test_group_covers_layout_data_gap_alignment_and_animation_contracts() -> None:
    default_props = props(builder().group("Default"))
    assert default_props["%bas"] == "none"

    current_cell = builder().group(
        "Cell",
        layout="align to parent",
        width=320,
        height=180,
        row_gap="8",  # type: ignore[arg-type]
        column_gap="12",  # type: ignore[arg-type]
        data_class="custom.user",
        data_source="current_cell",
        fixed_width=True,
        fixed_height=True,
        background_style="bgcolor",
        collapse_animation=1,
        animation_type=" FADE ",
        container_horiz_alignment="stretch",
        container_vert_alignment="center",
        horiz_alignment="flex-start",
        vert_alignment="flex-end",
        nonant_alignment="bottom_right",
        top=10,
        left=20,
    )
    group_props = props(current_cell)
    assert current_cell["%x"] == current_cell["type"] == "Group"
    assert group_props["container_layout"] == "relative"
    assert group_props["%t"] == 10
    assert group_props["%l"] == 20
    assert group_props["row_gap"] == 8
    assert group_props["column_gap"] == 12
    assert group_props["%ds"]["%x"] == "ElementParent"
    assert group_props["min_width_css"] == "320px"
    assert group_props["min_height_css"] == "180px"
    assert group_props["animation_type"] == "fade"
    assert group_props["align_to_parent_pos"] == "bottom_right"

    data_source = {"%x": "Search", "%p": {"%t5": "custom.order"}}
    fit = builder().group(
        "Fit",
        layout="fixed",
        max_width="90%",
        max_height="640px",
        fit_width=True,
        fit_height=True,
        data_source=data_source,  # type: ignore[arg-type]
        use_gap=True,
        style="Group_custom",
        width_unset=True,
    )
    fit_props = props(fit)
    assert fit["%s1"] == "Group_custom"
    assert fit_props["%ds"] is data_source
    assert fit_props["%t"] == fit_props["%l"] == 0
    assert fit_props["use_gap"] is True
    assert "%bas" not in fit_props
    assert "%w" not in fit_props
    assert "single_width" not in fit_props
    assert "single_height" not in fit_props


def test_button_validates_type_supplies_icon_and_supports_width_unset() -> None:
    with pytest.raises(ValueError, match="Invalid button_type"):
        builder().button("Invalid", "Save", button_type="cta")

    icon = builder().button(
        "Icon",
        "Favorite",
        button_type="icon",
        width_unset=True,
    )
    assert props(icon)["%9i"] == "feather star"
    assert "%w" not in props(icon)


@pytest.mark.parametrize(
    ("initial_content", "entries"),
    [
        ({"%x": "TextExpression", "%e": {"0": "wire"}}, {"0": "wire"}),
        ({"type": "TextExpression", "entries": {"0": "canonical"}}, {"0": "canonical"}),
        ({"%x": "CurrentUser", "%n": "name"}, {"0": "", "1": {"%x": "CurrentUser", "%n": "name"}, "2": ""}),
        ("literal", {"0": "literal"}),
    ],
)
def test_input_normalizes_initial_content_forms(
    initial_content: Any,
    entries: dict[str, Any],
) -> None:
    input_props = props(builder().input("Input", initial_content=initial_content))
    assert input_props["%c1"]["%e"] == entries
    assert input_props["initial_content"]["entries"] == entries


def test_input_normalizes_dimensions_limits_bindings_and_empty_content() -> None:
    input_props = props(
        builder().input(
            "Amount",
            placeholder=None,  # type: ignore[arg-type]
            initial_content=None,
            width="320",  # type: ignore[arg-type]
            height="48",  # type: ignore[arg-type]
            required=True,
            auto_binding=True,
            bind_field="amount_number",
            currency_symbol="$",
            not_submit_on_enter=True,
            limit_characters=True,
            character_limit="120",
            fixed_height=True,
            width_unset=True,
        )
    )
    assert input_props["placeholder"]["entries"] == {"0": ""}
    assert "%c1" not in input_props
    assert "initial_content" not in input_props
    assert input_props["%h"] == 48
    assert "%w" not in input_props
    assert input_props["character_limit"] == 120
    assert input_props["single_height"] is True
    assert input_props["min_height_css"] == "48px"

    invalid_limit = props(builder().input("Input", character_limit="unlimited"))
    assert invalid_limit["character_limit"] == "unlimited"


def test_date_picker_maps_aliases_and_supports_width_unset() -> None:
    date = builder().date_picker(
        "Appointment",
        show_time=True,
        required=True,
        disabled=True,
        initial_content={"%x": "CurrentDateTime"},
        auto_binding=True,
        bind_field="scheduled_date",
        content_format="date",
        date_format="custom",
        custom_format="DD/MM/YYYY",
        start_week_monday=True,
        show_month_year_picker=True,
        time_format="24h",
        time_interval=15,
        minimum_date="today",
        maximum_date="next year",
        minimum_hour=8,
        maximum_hour=18,
        width_unset=True,
    )
    date_props = props(date)
    assert date["%x"] == "DateInput"
    assert date_props["input_type"] == "date_time"
    assert date_props["binding_content_format"] == "date"
    assert date_props["start_monday"] is True
    assert date_props["min_date"] == "today"
    assert date_props["max_date"] == "next year"
    assert date_props["min_hour"] == 8
    assert date_props["max_hour"] == 18
    assert "%w" not in date_props


def test_slider_normalizes_dimensions_range_visuals_and_style() -> None:
    defaults = props(builder().slider("Defaults"))
    assert defaults["%w"] == 200
    assert defaults["%h"] == 45

    numeric_strings = props(builder().slider("Numeric", width="200", height="45"))
    assert numeric_strings["%w"] == 200
    assert numeric_strings["%h"] == 45

    slider = builder().slider(
        "Price",
        initial_value=25,
        range_initial_value={"min": 10, "max": 50},
        width="320px",
        height=64.8,
        range_type=" RANGE ",
        orientation=" VERTICAL ",
        background_color="track",
        handle_color="handle",
        range_area_color="range",
        auto_binding=True,
        bind_field="price_number",
        disabled=False,
        style="Slider_custom",
    )
    slider_props = props(slider)
    assert slider["%s1"] == "Slider_custom"
    assert slider_props["%w"] == 320
    assert slider_props["%h"] == 64
    assert slider_props["%c1"] == {"min": 10, "max": 50}
    assert "%v" not in slider_props
    assert slider_props["range_type"] == "range"
    assert slider_props["orientation"] == "vertical"
    assert slider_props["background_color"] == "track"
    assert slider_props["handle_color"] == "handle"
    assert slider_props["range_area_color"] == "range"

    fallback = props(
        builder().slider(
            "Fallback",
            initial_value=5,
            width="fluid",
            height="auto",
            width_unset=True,
        )
    )
    assert fallback["%c1"] == fallback["%v"] == 5
    assert "%w" not in fallback
    assert fallback["%h"] == 45


def test_html_and_shape_cover_visual_style_and_width_contracts() -> None:
    html = builder().html(
        "Embed",
        "<strong>Content</strong>",
        width_unset=True,
        style="HTML_custom",
    )
    assert html["%s1"] == "HTML_custom"
    assert html["%p"]["%ht"]["%e"]["0"] == "<strong>Content</strong>"
    assert "%w" not in props(html)

    shape = builder().shape(
        "Card",
        bg_color="red",
        border_radius=12,
        style="Shape_custom",
        width_unset=True,
    )
    shape_props = props(shape)
    assert shape["%s1"] == "Shape_custom"
    assert shape_props["%bgc"] == "red"
    assert shape_props["%bas"] == "bgcolor"
    assert shape_props["%br"] == 12
    assert "%w" not in shape_props

    explicit = props(builder().shape("Gradient", background_style="gradient"))
    assert explicit["%bas"] == "gradient"


def test_video_player_normalizes_provider_source_dimensions_and_options() -> None:
    defaults = props(builder().video_player("Defaults"))
    assert defaults["%w"] == 560
    assert defaults["%h"] == 315

    numeric_strings = props(builder().video_player("Numeric", width="560", height="315"))
    assert numeric_strings["%w"] == 560
    assert numeric_strings["%h"] == 315

    video = builder().video_player(
        "Demo",
        video_id="abc123",
        video_origin=" VIMEO ",
        vimeo_control_color="#00FF00",
        width="640px",
        height=360.9,
        autoplay=1,
        controls=0,
        loop=True,
        use_aspect_ratio=True,
        aspect_ratio_width="16",
        aspect_ratio_height="9",
        style="Video_custom",
    )
    video_props = props(video)
    assert video["%s1"] == "Video_custom"
    assert video_props["video_source"] == "vimeo"
    assert video_props["video_origin"] == "vimeo"
    assert video_props["video_id"]["%e"]["0"] == "abc123"
    assert video_props["%w"] == 640
    assert video_props["%h"] == 360
    assert video_props["autoplay"] is True
    assert video_props["controls"] is False
    assert video_props["aspect_ratio_width"] == 16
    assert video_props["control_color_vimeo"] == "#00FF00"

    url = props(
        builder().video_player(
            "Remote",
            video_url="https://example.com/video.mp4",
            video_origin="",
            width="fluid",
            height="auto",
            vimeo_control_color_alias="ignored",
            width_unset=True,
        )
    )
    assert url["video_source"]["%e"]["0"] == "https://example.com/video.mp4"
    assert url["video_origin"] == "youtube"
    assert "%w" not in url
    assert url["%h"] == 315


@pytest.mark.parametrize(
    ("width", "height", "expected_width", "expected_height"),
    [
        ("180px", "40px", 180, 40),
        ("180", "40", 180, 40),
        (180.5, 40.5, 180.5, 40.5),
    ],
)
def test_checkbox_normalizes_dimensions(
    width: Any,
    height: Any,
    expected_width: Any,
    expected_height: Any,
) -> None:
    checkbox_props = props(builder().checkbox("Terms", width=width, height=height))
    assert checkbox_props["%w"] == expected_width
    assert checkbox_props["%h"] == expected_height


def test_checkbox_covers_dynamic_state_style_and_width_unset() -> None:
    expression = {"%x": "CurrentUser", "%n": "accepted_terms"}
    checkbox = builder().checkbox(
        "Terms",
        preset_status="dynamic",
        dynamic_status_expression=expression,
        required=True,
        disabled=True,
        style="Checkbox_custom",
        width_unset=True,
    )
    checkbox_props = props(checkbox)
    assert checkbox["%s1"] == "Checkbox_custom"
    assert checkbox_props["%ct"] == "dynamic_state"
    assert checkbox_props["dynamic"] is expression
    assert "%w" not in checkbox_props


def test_icon_derives_or_accepts_size_and_handles_invalid_dimensions() -> None:
    derived = builder().icon("Menu", "feather menu", width=20, height=24)
    assert props(derived)["icon_size"] == 24

    explicit = builder().icon(
        "Large",
        "feather star",
        width="fluid",  # type: ignore[arg-type]
        height="auto",  # type: ignore[arg-type]
        icon_size=32,
        style="Icon_custom",
        width_unset=True,
    )
    assert explicit["%s1"] == "Icon_custom"
    assert props(explicit)["icon_size"] == 32
    assert "%w" not in props(explicit)

    invalid = props(
        builder().icon(
            "Invalid",
            "feather x",
            width="fluid",  # type: ignore[arg-type]
            height="auto",  # type: ignore[arg-type]
        )
    )
    assert "icon_size" not in invalid


def test_alert_normalizes_content_dimensions_position_style_and_width() -> None:
    defaults = props(builder().alert("Default", "Saved"))
    assert defaults["%w"] == 280
    assert defaults["%h"] == 48

    numeric_strings = props(builder().alert("Numeric", "Saved", width="280", height="48"))
    assert numeric_strings["%w"] == 280
    assert numeric_strings["%h"] == 48

    expression = {"%x": "TextExpression", "%e": {"0": "Saved"}}
    alert = builder().alert(
        "Saved",
        expression,
        at_to_top=True,
        width="320px",
        height=60.9,
        top=12,
        left=24,
        zindex=20,
        order=5,
        style="Alert_custom",
    )
    alert_props = props(alert)
    assert alert["%s1"] == "Alert_custom"
    assert alert_props["%3"] is expression
    assert alert_props["%w"] == 320
    assert alert_props["%h"] == 60
    assert alert_props["%t"] == 12
    assert alert_props["%l"] == 24
    assert alert_props["at_to_top"] is True

    fallback = props(
        builder().alert(
            "Fallback",
            None,  # type: ignore[arg-type]
            width="fluid",
            height="auto",
            width_unset=True,
        )
    )
    assert fallback["%3"]["%e"]["0"] == ""
    assert "%w" not in fallback
    assert fallback["%h"] == 48


def test_repeating_group_covers_search_explicit_source_and_separator_contracts() -> None:
    search = builder().repeating_group(
        "Users",
        data_type=" custom.user ",
        width=320,
        height=480,
        constraints={"active": True},
        sort_field="name_text",
        sort_direction="ascending",
        layout="row",
        cell_height="96px",
        row_gap="12",
        horiz_alignment="stretch",
        vert_alignment="center",
        nonant_alignment="center",
        separator_style="solid",
        separator_width="2",
        separator_color="gray",
    )
    search_props = props(search)
    assert search_props["%gt"] == "custom.user"
    assert search_props["%ds"]["%p"] == {
        "%t5": "custom.user",
        "%co": {"active": True},
        "%sf": "name_text",
        "%sd": "ascending",
    }
    assert search_props["container_layout"] == "row"
    assert search_props["cell_min_height_css"] == "96px"
    assert search_props["use_gap"] is True
    assert search_props["row_gap"] == 12
    assert search_props["align_to_parent_pos"] == "center"
    assert search_props["%ss"] == "solid"
    assert search_props["%sw"] == 2
    assert search_props["%sc"] == "gray"

    source = {"%x": "Search", "%p": {"%t5": "custom.order"}}
    explicit = builder().repeating_group(
        "Orders",
        width=None,  # type: ignore[arg-type]
        height=None,  # type: ignore[arg-type]
        data_source=source,
        use_gap=False,
        style="RG_custom",
        width_unset=True,
    )
    explicit_props = props(explicit)
    assert explicit["%s1"] == "RG_custom"
    assert explicit_props["%ds"] is source
    assert explicit_props["cell_min_height_css"] == "80px"
    assert explicit_props["use_gap"] is False
    assert "%gt" not in explicit_props
    assert "%ss" not in explicit_props
    assert "%w" not in explicit_props

    empty = builder().repeating_group("Empty")
    assert empty["%s1"] is None
    assert props(empty)["%ss"] == "none"
