from pathlib import Path

from bubble_mcp.style_import.html import extract_style_rules_from_html
from bubble_mcp.style_import.mapper import map_rules_to_style_candidate


def test_map_rules_to_button_style_candidate_with_states() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")
    rules = extract_style_rules_from_html(html, selector=".btn-primary")

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Button",
        selector=".btn-primary",
    )

    assert candidate.name == "HTML Button Primary"
    assert candidate.element_type == "Button"
    assert candidate.selector == ".btn-primary"
    assert candidate.base["bg_color"] == "#155eef"
    assert candidate.base["font_color"] == "#ffffff"
    assert candidate.base["border_radius"] == 8
    assert candidate.base["border_width"] == 1
    assert candidate.base["border_style"] == "solid"
    assert candidate.base["border_color"] == "#155eef"
    assert candidate.base["font_size"] == 16
    assert candidate.base["font_weight"] == "600"
    assert candidate.base["padding_top"] == 12
    assert candidate.base["padding_bottom"] == 12
    assert candidate.base["padding_left"] == 18
    assert candidate.base["padding_right"] == 18
    assert candidate.states["hover"]["bg_color"] == "#004eeb"
    assert candidate.states["focus"]["border_color"] == "#84caff"
    assert candidate.states["focus"]["shadow_style"] == "outset"
    assert candidate.states["focus"]["shadow_h"] == 0
    assert candidate.states["focus"]["shadow_v"] == 0
    assert candidate.states["focus"]["shadow_blur"] == 0
    assert candidate.states["focus"]["shadow_spread"] == 4
    assert candidate.states["focus"]["shadow_color"] == "rgba(132, 202, 255, 0.35)"
    assert candidate.states["disabled"]["font_color"] == "#667085"
    assert candidate.states["pressed"]["bg_color"] == "#00359e"


def test_map_complex_css_colors_and_rejects_multiple_backgrounds() -> None:
    rules = extract_style_rules_from_html(
        """
        <style>
          .card {
            background-color: rgb(21, 94, 239);
            color: hsl(0, 0%, 100%);
            border-color: rgba(132, 202, 255, 0.35);
          }
          .card:hover {
            background: linear-gradient(red, blue), #ffffff;
          }
        </style>
        """,
        selector=".card",
    )

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Group",
        selector=".card",
    )

    assert candidate.base["bg_color"] == "#155eef"
    assert candidate.base["font_color"] == "#ffffff"
    assert candidate.base["border_color"] == "rgba(132, 202, 255, 0.35)"
    assert {
        "state": "hover",
        "property": "background",
        "value": "linear-gradient(red, blue), #ffffff",
        "reason": "multiple_backgrounds",
    } in candidate.unsupported


def test_map_independent_border_fields() -> None:
    rules = extract_style_rules_from_html(
        """
        <style>
          .card {
            border-top: 2px solid #111111;
            border-right-color: #222222;
            border-bottom-width: 3px;
            border-left-style: dashed;
            border-top-left-radius: 10px;
            border-bottom-right-radius: 14px;
            padding-left: 24px;
          }
        </style>
        """,
        selector=".card",
    )

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Group",
        selector=".card",
    )

    assert candidate.base["border_width_top"] == 2
    assert candidate.base["border_style_top"] == "solid"
    assert candidate.base["border_color_top"] == "#111111"
    assert candidate.base["border_color_right"] == "#222222"
    assert candidate.base["border_width_bottom"] == 3
    assert candidate.base["border_style_left"] == "dashed"
    assert candidate.base["radius_top_left"] == 10
    assert candidate.base["radius_bottom_right"] == 14
    assert candidate.base["padding_left"] == 24


def test_map_independent_border_shorthands() -> None:
    rules = extract_style_rules_from_html(
        """
        <style>
          .card {
            border-width: 1px 2px 3px 4px;
            border-style: solid dashed dotted none;
            border-color: #111111 #222222 #333333 #444444;
            border-radius: 8px 12px 16px 20px;
          }
        </style>
        """,
        selector=".card",
    )

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Group",
        selector=".card",
    )

    assert candidate.base["border_width_top"] == 1
    assert candidate.base["border_width_right"] == 2
    assert candidate.base["border_width_bottom"] == 3
    assert candidate.base["border_width_left"] == 4
    assert candidate.base["border_style_top"] == "solid"
    assert candidate.base["border_style_right"] == "dashed"
    assert candidate.base["border_style_bottom"] == "dotted"
    assert candidate.base["border_style_left"] == "none"
    assert candidate.base["border_color_top"] == "#111111"
    assert candidate.base["border_color_right"] == "#222222"
    assert candidate.base["border_color_bottom"] == "#333333"
    assert candidate.base["border_color_left"] == "#444444"
    assert candidate.base["radius_top_left"] == 8
    assert candidate.base["radius_top_right"] == 12
    assert candidate.base["radius_bottom_right"] == 16
    assert candidate.base["radius_bottom_left"] == 20


def test_partial_border_shorthand_records_unparsed_tokens() -> None:
    rules = extract_style_rules_from_html(
        """
        <style>
          .card { border: 1px solid rgba(132, 202, 255, 0.35); }
        </style>
        """,
        selector=".card",
    )

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Group",
        selector=".card",
    )

    assert candidate.base["border_width"] == 1
    assert candidate.base["border_style"] == "solid"
    assert {
        "state": "base",
        "property": "border",
        "value": "rgba(132, 202, 255, 0.35)",
    } in candidate.unsupported


def test_box_shadow_accepts_inset_after_color() -> None:
    rules = extract_style_rules_from_html(
        """
        <style>
          .card { box-shadow: 0 2px 6px 0 #000000 inset; }
        </style>
        """,
        selector=".card",
    )

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Group",
        selector=".card",
    )

    assert candidate.base["shadow_style"] == "inset"
    assert candidate.base["shadow_h"] == 0
    assert candidate.base["shadow_v"] == 2
    assert candidate.base["shadow_blur"] == 6
    assert candidate.base["shadow_spread"] == 0
    assert candidate.base["shadow_color"] == "#000000"
