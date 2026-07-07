import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.compiler.payload import CREATE_DEFAULT_ARGS, compile_plan_to_write_payloads
from bubble_mcp.context.models import BubbleProjectContext


GOLDEN_DEFAULTS = Path("tests/fixtures/golden/create-defaults.json")


def create_body(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    context: BubbleProjectContext | None = None,
) -> dict[str, Any]:
    step_args = {"context": "index", "parent": "root", **(args or {})}
    payload = compile_plan_to_write_payloads(
        {"steps": [{"id": "s1", "tool_name": tool_name, "args": step_args}]},
        app_id="synthetic-app",
        context=context,
    )["steps"][0]["args"]["write_payload"]
    return next(
        change for change in payload["changes"] if change.get("intent", {}).get("name") == "CreateElement"
    )["body"]


def create_properties(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    context: BubbleProjectContext | None = None,
) -> dict[str, Any]:
    body = create_body(tool_name, args, context=context)
    properties = body["%p"]
    step_args = {"context": "index", "parent": "root", **(args or {})}
    payload = compile_plan_to_write_payloads(
        {"steps": [{"id": "s1", "tool_name": tool_name, "args": step_args}]},
        app_id="synthetic-app",
        context=context,
    )["steps"][0]["args"]["write_payload"]
    for change in payload["changes"]:
        if change.get("intent", {}).get("name") == "SetData":
            path = change.get("path_array") or []
            if path[-2:-1] == ["%p"]:
                properties[path[-1]] = change.get("body")
    return properties


def test_create_defaults_match_golden_fixture() -> None:
    expected = json.loads(GOLDEN_DEFAULTS.read_text(encoding="utf-8"))

    assert CREATE_DEFAULT_ARGS == expected


@pytest.mark.parametrize(
    ("tool_name", "args", "expected"),
    [
        ("create_text", {"content": "Hello"}, {"fit_height": True}),
        ("create_button", {}, {"fit_width": True, "fit_height": True, "single_width": False, "single_height": False}),
        ("create_group", {"name": "Group"}, {"container_layout": "column", "min_width_css": "40px", "min_height_css": "40px", "fit_height": True}),
        ("create_input", {}, {"%h": 44, "fixed_height": True, "single_height": True, "min_width_css": "0px", "max_width_css": "240px", "min_height_css": "44px", "max_height_css": "44px"}),
        ("create_icon", {}, {"%w": 20, "%h": 20, "fixed_width": True, "fixed_height": True, "min_width_css": "20px", "max_width_css": "20px", "min_height_css": "20px", "max_height_css": "20px"}),
        ("create_repeating_group", {}, {"%gt": "text", "stable_pagination": True, "cell_min_height_css": "32px", "cell_min_width_css": "32px"}),
        ("create_video", {}, {"video_id": "id", "use_aspect_ratio": True, "aspect_ratio_width": 16, "aspect_ratio_height": 9, "%w": 360}),
        ("create_html", {}, {"fit_height": True, "fixed_width": True, "min_height_css": "120px", "%w": 240, "min_width_css": "240px", "max_width_css": "240px"}),
    ],
)
def test_compiled_create_defaults_materialize_in_payload(
    tool_name: str,
    args: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    properties = create_properties(tool_name, args)

    for key, value in expected.items():
        assert properties.get(key) == value


def test_fixed_dimensions_set_matching_min_and_max_constraints() -> None:
    properties = create_properties(
        "create_group",
        {
            "name": "Fixed Card",
            "width": 320,
            "height": 180,
            "fixed_width": True,
            "fixed_height": True,
        },
    )

    assert properties["%w"] == 320
    assert properties["min_width_css"] == "320px"
    assert properties["max_width_css"] == "320px"
    assert properties["%h"] == 180
    assert properties["min_height_css"] == "180px"
    assert properties["max_height_css"] == "180px"


def test_button_uses_project_default_style_from_context() -> None:
    context = BubbleProjectContext(
        app_id="synthetic-app",
        source="test",
        nodes=[],
        edges=[],
        metadata={
            "settings": {
                "client_safe": {
                    "default_styles": {
                        "Button": "Button_project_default",
                    }
                }
            }
        },
    )

    body = create_body("create_button", {"label": "Continue"}, context=context)

    assert body["%s1"] == "Button_project_default"


def test_button_preserves_explicit_style() -> None:
    body = create_body("create_button", {"label": "Continue", "style": "Button_explicit"})

    assert body["%s1"] == "Button_explicit"


@pytest.mark.parametrize(
    ("tool_name", "element_type", "style_id"),
    [
        ("create_text", "Text", "Text_project_default"),
        ("create_icon", "Icon", "Icon_project_default"),
        ("create_link", "Link", "Link_project_default"),
        ("create_image", "Image", "Image_project_default"),
        ("create_shape", "Shape", "Shape_project_default"),
        ("create_alert", "Alert", "Alert_project_default"),
        ("create_video", "VideoPlayer", "Video_project_default"),
        ("create_html", "HTML", "Html_project_default"),
        ("create_map", "Map", "Map_project_default"),
        ("create_group", "Group", "Group_project_default"),
        ("create_repeating_group", "RepeatingGroup", "Repeating_project_default"),
        ("create_popup", "Popup", "Popup_project_default"),
        ("create_floating_group", "FloatingGroup", "Floating_project_default"),
        ("create_group_focus", "GroupFocus", "Focus_project_default"),
        ("create_table", "Table", "Table_project_default"),
        ("create_button", "Button", "Button_project_default"),
        ("create_input", "Input", "Input_project_default"),
        ("create_multiline_input", "MultiLineInput", "MultiLine_project_default"),
        ("create_dropdown", "Dropdown", "Dropdown_project_default"),
        ("create_searchbox", "AutocompleteDropdown", "Search_project_default"),
        ("create_checkbox", "Checkbox", "Checkbox_project_default"),
        ("create_radio", "RadioButtons", "Radio_project_default"),
        ("create_slider", "SliderInput", "Slider_project_default"),
        ("create_datepicker", "DateInput", "Date_project_default"),
        ("create_file_uploader", "FileInput", "File_project_default"),
        ("create_picture_uploader", "PictureInput", "Picture_project_default"),
    ],
)
def test_creates_use_project_default_styles_from_context(tool_name: str, element_type: str, style_id: str) -> None:
    context = BubbleProjectContext(
        app_id="synthetic-app",
        source="test",
        nodes=[],
        edges=[],
        metadata={
            "settings": {
                "client_safe": {
                    "default_styles": {
                        element_type: style_id,
                    }
                }
            }
        },
    )

    args = {"content": "Hello"} if tool_name == "create_text" else {}
    body = create_body(tool_name, args, context=context)

    assert body["%s1"] == style_id


def test_create_preserves_explicit_style() -> None:
    body = create_body("create_input", {"style": "Input_explicit"})

    assert body["%s1"] == "Input_explicit"
