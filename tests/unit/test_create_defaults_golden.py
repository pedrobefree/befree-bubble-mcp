import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.compiler.payload import CREATE_DEFAULT_ARGS, compile_plan_to_write_payloads


GOLDEN_DEFAULTS = Path("tests/fixtures/golden/create-defaults.json")


def create_properties(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    step_args = {"context": "index", "parent": "root", **(args or {})}
    payload = compile_plan_to_write_payloads(
        {"steps": [{"id": "s1", "tool_name": tool_name, "args": step_args}]},
        app_id="synthetic-app",
    )["steps"][0]["args"]["write_payload"]
    create_change = next(
        change for change in payload["changes"] if change.get("intent", {}).get("name") == "CreateElement"
    )
    properties = create_change["body"]["%p"]
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
