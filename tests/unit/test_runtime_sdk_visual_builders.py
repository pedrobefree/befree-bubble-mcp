from bubble_mcp.aria_runtime.bubble_sdk import ElementBuilder


class FixedIds:
    def element_id(self) -> str:
        return "bVISUAL"


def builder() -> ElementBuilder:
    return ElementBuilder(FixedIds())


def test_popup_covers_default_and_explicit_style_contracts() -> None:
    default = builder().popup("Default")["%p"]
    assert default["%bgc"] == "#FFFFFF"
    assert default["%bas"] == "bgcolor"
    assert default["%br"] == 12
    assert default["%bs"] == "none"
    assert default["padding_top"] == default["padding_right"] == 32

    data_source = {"%x": "CurrentUser"}
    styled = builder().popup(
        "Styled",
        min_width="420px",
        max_width="90%",
        min_height="300px",
        max_height="90%",
        fit_width=True,
        fit_height=True,
        layout="row",
        style="Popup_custom",
        bg_color="red",
        background_style="gradient",
        border_radius=8,
        shadow_style="outset",
        padding_top=1,
        padding_bottom=2,
        padding_left=3,
        padding_right=4,
        close_by_esc=False,
        grayout_color="rgba(0,0,0,.5)",
        grayout_blur="auto",
        column_gap="12",
        nonant_alignment="center",
        container_horiz_alignment="stretch",
        container_vert_alignment="center",
        data_class="custom.user",
        data_source=data_source,
    )
    props = styled["%p"]
    assert styled["%s1"] == "Popup_custom"
    assert props["container_layout"] == "row"
    assert props["prevent_user_from_closing_through_esc"] is True
    assert props["greyout_color"] == "rgba(0,0,0,.5)"
    assert props["greyout_blur"] == "auto"
    assert props["column_gap"] == 12
    assert props["align_to_parent_pos"] == "center"
    assert props["%gt"] == "custom.user"
    assert props["%ds"] is data_source


def test_popup_accepts_canonical_close_and_greyout_fields() -> None:
    props = builder().popup(
        "Canonical",
        prevent_user_from_closing_through_esc=False,
        greyout_color="black",
        greyout_blur="4",
    )["%p"]
    assert props["prevent_user_from_closing_through_esc"] is False
    assert props["greyout_color"] == "black"
    assert props["greyout_blur"] == 4


def test_file_uploader_normalizes_dimensions_sources_and_attachment_aliases() -> None:
    upload = builder().file_uploader(
        "Document",
        width="320px",
        height=64.8,
        dynamic_link='{"%x": "CurrentUser"}',
        attach_to={"value": "@current_user"},
        max_size="invalid",
        private=True,
        required=True,
        disabled=True,
        fit_width=True,
        style="File_custom",
    )
    props = upload["%p"]
    assert upload["%s1"] == "File_custom"
    assert props["%w"] == 320
    assert props["%h"] == 64
    assert props["src"] == {"%x": "CurrentUser"}
    assert props["attach_to"]["%x"] == "CurrentUser"
    assert props["max_size"] == 10
    assert props["max_file_size"] == 10 * 1024 * 1024
    assert props["private"] is True

    url = builder().file_uploader(
        "Remote",
        width="fluid",
        height="48",
        src="https://example.com/file.pdf",
        attach_to="@current_page",
        max_file_size_mb="5",
        private_file=False,
    )["%p"]
    assert url["%w"] == 250
    assert url["%h"] == 48
    assert url["src"]["%e"]["0"] == "https://example.com/file.pdf"
    assert url["attach_to"] == {"%x": "CurrentPageItem", "is_slidable": False}
    assert url["max_size"] == 5
    assert url["private"] is False


def test_file_uploader_preserves_jsonish_edge_values() -> None:
    invalid = builder().file_uploader(
        "Invalid JSON",
        dynamic_link="{invalid",
        attach_to={"expression": '[{"%x": "CurrentUser"}]'},
    )["%p"]
    assert invalid["src"]["%e"]["0"] == "{invalid"
    assert invalid["attach_to"] == [{"%x": "CurrentUser"}]

    empty = builder().file_uploader("Empty", dynamic_link="   ")["%p"]
    assert "src" not in empty


def test_picture_uploader_emits_inline_states_only_without_style() -> None:
    picture = builder().picture_uploader(
        "Avatar",
        width="180px",
        height="180",
        dynamic_link="https://example.com/avatar.png",
        attach_to={"attach_to": "current_page"},
        private_file=True,
        limit_image_size_before_upload=True,
        font_size=14,
    )
    props = picture["%p"]
    assert picture["%x"] == "PictureInput"
    assert "%s1" not in picture
    assert set(picture["%s"]) == {"0", "1"}
    assert props["%w"] == props["%h"] == 180
    assert props["src"]["%e"]["0"] == "https://example.com/avatar.png"
    assert props["attach_to"]["%x"] == "CurrentPageItem"
    assert props["private"] is True
    assert props["limit_image_width"] is True
    assert props["bold"] is False

    styled = builder().picture_uploader(
        "Styled Avatar",
        style="Picture_custom",
        limit_image_width=False,
    )
    assert styled["%s1"] == "Picture_custom"
    assert "%s" not in styled
    assert styled["%p"]["limit_image_width"] is False


def test_dropdown_covers_static_option_set_search_and_expression_sources() -> None:
    static = builder().dropdown(
        "Static",
        choice_style="static",
        choices="One,Two",
        width="240px",
        height="52",
        fixed_width=True,
        fixed_height=True,
    )["%p"]
    assert static["%ch"] == "One,Two"
    assert static["%w"] == 240
    assert static["%h"] == 52
    assert static["single_width"] is True
    assert static["single_height"] is True
    assert static["min_width_css"] == "240px"
    assert static["min_height_css"] == "52px"

    option_set = builder().dropdown(
        "Roles",
        choice_type="OS:Role",
        option_caption_field="display_text",
    )["%p"]
    assert option_set["dynamic_type"] == "option.os_role"
    assert option_set["%ds"]["%x"] == "AllOptionValue"
    assert option_set["option_display_expression"]["%e"]["1"]["%n"]["%nm"] == "display_text"

    search = builder().dropdown(
        "Users",
        choice_type="custom.user",
        sort_field="name_text",
        sort_direction="descending",
    )["%p"]
    assert search["%ds"]["%p"] == {
        "%t5": "custom.user",
        "%sf": "name_text",
        "%sd": "descending",
    }

    expression = {"%x": "Search", "%p": {"%t5": "custom.order"}}
    dynamic = builder().dropdown("Orders", choice_type="custom.order", choices=expression)["%p"]
    assert dynamic["%ds"] is expression


def test_radio_button_covers_static_and_dynamic_choice_contracts() -> None:
    static = builder().radio_button(
        "Static",
        choices="One,Two",
        selected=True,
        default_value="One",
        columns="2",
        use_dynamic_columns=True,
        min_column_width_px="120",
        color=" RED ",
        width="320px",
        height=90.5,
        style="Radio_custom",
    )
    props = static["%p"]
    assert static["%s1"] == "Radio_custom"
    assert props["%ch"] == "One,Two"
    assert props["selected"] is True
    assert props["%d1"] == "One"
    assert props["%c5"] == 2
    assert props["min_column_width_px"] == 120
    assert props["color"] == "red"

    option_set = builder().radio_button(
        "Options",
        choice_style="dynamic",
        choice_type="OS:Role",
        option_caption_field="display_text",
    )["%p"]
    assert option_set["dynamic_type"] == "option.os_role"
    assert option_set["%ds"]["%x"] == "AllOptionValue"
    assert option_set["option_display_expression"]["%e"]["1"]["%n"]["%nm"] == "display_text"

    expression = {"%x": "Search", "%p": {"%t5": "custom.user"}}
    dynamic = builder().radio_button(
        "Users",
        choice_style="dynamic",
        choice_type="custom.user",
        choices=expression,
        group_name="",
        label="",
    )["%p"]
    assert dynamic["%ds"] is expression
    assert "radio_group" not in dynamic
    assert "%lab" not in dynamic

    fallback = builder().radio_button(
        "Fallback",
        choice_style="dynamic",
        choice_type="custom.order",
    )["%p"]
    assert fallback["%ds"]["%p"] == {"%t5": "custom.order"}


def test_image_normalizes_aspect_ratio_dimensions_and_metadata() -> None:
    image = builder().image(
        "Hero",
        "https://example.com/hero.png",
        width="640px",
        height="360",
        aspect_ratio_width="16",
        aspect_ratio_height="9",
        alt_tag="Hero image",
        title_attribute="Hero",
        button_disabled=True,
        rotation_angle="15",
        single_width=True,
        single_height=True,
        style="Image_custom",
    )
    props = image["%p"]
    assert image["%s1"] == "Image_custom"
    assert props["%w"] == 640
    assert "%h" not in props
    assert props["use_aspect_ratio"] is True
    assert props["aspect_ratio_width"] == 16
    assert props["aspect_ratio_height"] == 9
    assert props["alt_tag"] == "Hero image"
    assert props["rotation_angle"] == 15

    inferred = builder().image(
        "Inferred",
        "image.png",
        width=200,
        height=100,
        use_aspect_ratio=True,
    )["%p"]
    assert inferred["aspect_ratio_width"] == 200
    assert inferred["aspect_ratio_height"] == 100

    fixed = builder().image("Fixed", "image.png", width="invalid", height=None)["%p"]
    assert fixed["%w"] == fixed["%h"] == 48


def test_link_preserves_navigation_and_clickability_contracts() -> None:
    label = {"%x": "TextExpression", "%e": {"0": "Profile"}}
    destination_data = {"%x": "CurrentUser"}
    url_expression = {"%x": "TextExpression", "%e": {"0": "https://example.com"}}
    link = builder().link(
        "Profile",
        label,
        link_destination="page",
        destination_page="profile",
        url=url_expression,
        data_to_send=destination_data,
        open_in_new_tab=True,
        button_disabled=True,
        nofollow=True,
        keep_current_page_params=True,
        add_parameters=True,
        url_parameters={"tab": "details"},
        show_icon=True,
        icon="feather user",
        width="180px",
        height="24",
        style="Link_custom",
    )
    props = link["%p"]
    assert link["%s1"] == "Link_custom"
    assert props["%3"] is label
    assert props["%1l"] == "page"
    assert props["%pa"] == "profile"
    assert props["url"] is url_expression
    assert props["data_to_send"] is destination_data
    assert props["link_disabled"] is True
    assert "button_disabled" not in props
    assert props["%9i"] == "feather user"
    assert props["url_parameters"] == {"tab": "details"}

    external = builder().link(
        "External",
        "Docs",
        url="https://example.com/docs",
        width="invalid",
        height=None,
        link_disabled=False,
    )["%p"]
    assert external["%3"]["%e"]["0"] == "Docs"
    assert external["url"]["%e"]["0"] == "https://example.com/docs"
    assert external["%w"] == 150
    assert external["%h"] == 20
    assert external["link_disabled"] is False


def test_google_map_maps_canonical_options_and_legacy_aliases() -> None:
    source = {"%x": "Search", "%p": {"%t5": "custom.place"}}
    center = {"lat": -3.7, "lng": -38.5}
    caption = {"%x": "TextExpression", "%e": {"0": "Place"}}
    address = {"%x": "CurrentGeographicPosition"}
    map_element = builder().google_map(
        "Places",
        data_source=source,
        map_type="roadmap",
        map_style="custom",
        custom_style="[]",
        allow_zoom_drag=True,
        disable_zoom_scroll=False,
        initial_zoom="12",
        use_customized_marker_icon=True,
        custom_marker_icon="pin",
        marker_type="list",
        marker_data_type="custom.place",
        location_field="address_geographic_address",
        manual_setting=True,
        center=center,
        use_customized_marker_icon_for_list="yes",
        custom_marker_field="icon_image",
        custom_selected_icon="selected",
        custom_selected_icon_image="selected.png",
        show_info_window="on_click",
        autoclose=True,
        marker_caption_expression=caption,
        number_of_markers="25",
        marker_address=address,
        width="640px",
        height="360",
        style="Map_custom",
    )
    props = map_element["%p"]
    assert map_element["%s1"] == "Map_custom"
    assert props["%ds"] is source
    assert props["initial_zoom"] == 12
    assert props["center"] is center
    assert props["show_info_window"] == "on_click"
    assert props["autoclose"] is True
    assert props["marker_caption_expression"] is caption
    assert props["number_of_markers"] == 25
    assert props["marker_address"] is address

    legacy = builder().google_map(
        "Legacy",
        show_title_window=False,
        auto_close_window=False,
        width="invalid",
        height=None,
    )["%p"]
    assert legacy["show_info_window"] == "no"
    assert legacy["autoclose"] is False
    assert legacy["%w"] == 184
    assert legacy["%h"] == 140


def test_visual_builders_support_width_unset_consistently() -> None:
    visuals = [
        builder().popup("Popup", width_unset=True),
        builder().file_uploader("File", width_unset=True),
        builder().picture_uploader("Picture", width_unset=True),
        builder().dropdown("Dropdown", width_unset=True),
        builder().radio_button("Radio", width_unset=True),
        builder().image("Image", "image.png", width_unset=True),
        builder().link("Link", "Link", width_unset=True),
        builder().google_map("Map", width_unset=True),
    ]
    assert all("%w" not in visual["%p"] for visual in visuals)


def test_visual_builder_dimension_and_json_edge_branches() -> None:
    picture = builder().picture_uploader(
        "Picture",
        width=120.8,
        height="invalid",
        dynamic_link='{"%x": "CurrentUser"}',
        attach_to="current_user",
    )["%p"]
    assert picture["%w"] == 120
    assert picture["%h"] == 150
    assert picture["src"] == {"%x": "CurrentUser"}
    assert picture["attach_to"]["%x"] == "CurrentUser"

    invalid_json = builder().picture_uploader("Invalid", dynamic_link="{bad")["%p"]
    assert invalid_json["src"]["%e"]["0"] == "{bad"
    assert "src" not in builder().picture_uploader("Empty", dynamic_link=" ")["%p"]

    assert builder().dropdown("Numeric", width=200)["%p"]["%w"] == 200
    assert "%w" not in builder().dropdown("Invalid", width="fluid")["%p"]
    assert builder().radio_button("Numeric", width="200")["%p"]["%w"] == 200
    assert builder().radio_button("Invalid", width="fluid")["%p"]["%w"] == 200
    assert builder().link("Numeric", "Link", width=200)["%p"]["%w"] == 200
    assert builder().google_map("Numeric", width=400)["%p"]["%w"] == 400
