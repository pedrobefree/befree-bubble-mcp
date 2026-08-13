from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.html_to_bubble import HTMLParser, HTMLToBubbleMapper


FIXTURE = Path("tests/fixtures/html/import-pipeline-contracts.html")
GOLDEN = Path("tests/fixtures/golden/html-import-pipeline.json")

def _map_html(html: str, *, base_url: str = "https://example.test/pages/") -> dict[str, Any] | None:
    parsed = HTMLParser(base_url=base_url).parse(html)
    return HTMLToBubbleMapper(base_url=base_url).map_tree(parsed)


def test_html_import_pipeline_matches_reviewed_golden_payload() -> None:
    mapped = _map_html(FIXTURE.read_text(encoding="utf-8"))

    assert mapped is not None
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert mapped == expected


def test_golden_fixture_covers_required_mapper_families() -> None:
    mapped = _map_html(FIXTURE.read_text(encoding="utf-8"))
    assert mapped is not None
    payload = json.dumps(mapped, sort_keys=True)

    assert '"layout": "row"' in payload
    assert '"content": "Reliable [b][color=#84caff]imports[/color][/b]"' in payload
    assert '"max_width_css": "912px"' in payload
    assert '"image_url": "https://example.test/assets/preview.png"' in payload
    assert '"bubble_type": "Input"' in payload
    assert '"bubble_type": "Button"' in payload
    assert "Do not import" not in payload
    assert "must never execute" not in payload


@pytest.mark.parametrize(
    ("html", "expected_type", "expected_property", "expected_value"),
    [
        ("<h2>Heading</h2>", "Text", "content", "Heading"),
        ("<p>Paragraph</p>", "Text", "content", "Paragraph"),
        ("<button>Continue</button>", "Button", "label", "Continue"),
        ('<a href="/next">Next</a>', "Text", "content", "Next"),
        ('<input type="email" placeholder="Email">', "Input", "placeholder", "Email"),
        ('<textarea placeholder="Notes"></textarea>', "Input", "placeholder", "Notes"),
        ('<select><option>One</option></select>', "Input", "content_format", "text"),
        ('<img src="/asset.png" alt="Asset">', "Image", "alt_text", "Asset"),
        ('<svg viewBox="0 0 10 10"><path d="M0 0h10v10z"></path></svg>', "Image", "name", "SVG svg"),
    ],
)
def test_leaf_element_family_contracts(
    html: str,
    expected_type: str,
    expected_property: str,
    expected_value: object,
) -> None:
    mapped = _map_html(html)
    assert mapped is not None
    leaf = mapped["children"][0]
    assert leaf["bubble_type"] == expected_type
    assert leaf["properties"][expected_property] == expected_value


def test_map_tree_rejects_empty_hidden_and_skipped_source_without_exceptions() -> None:
    mapper = HTMLToBubbleMapper()

    assert mapper.map_tree({}) is None
    assert mapper.map_tree({"type": "script", "children": []}) is None
    assert mapper.map_tree({"type": "div", "computed_styles": {"display": "none"}}) is None
    assert mapper.map_tree({"type": "div", "computed_styles": {"visibility": "hidden"}}) is None
    assert mapper.map_tree({"type": "img", "attributes": {"src": "javascript:alert(1)"}}) is None


@pytest.mark.parametrize(
    "source",
    [
        "vbscript:msgbox(1)",
        "file:///tmp/private.png",
        "ftp://example.test/image.png",
        "data:text/html,<script>alert(1)</script>",
        "data:image/svg+xml,<svg onload='alert(1)'></svg>",
        "https://example.test/image.png\njavascript:alert(1)",
    ],
)
def test_image_mapping_rejects_active_or_unsupported_urls(source: str) -> None:
    assert HTMLToBubbleMapper().map_tree({"type": "img", "attributes": {"src": source}}) is None


@pytest.mark.parametrize(
    "source",
    [
        "https://example.test/image.png",
        "/relative/image.webp",
        "data:image/png;base64,iVBORw0KGgo=",
        "data:image/svg+xml,%3Csvg%20viewBox='0%200%201%201'%3E%3C/svg%3E",
    ],
)
def test_image_mapping_accepts_safe_web_and_image_sources(source: str) -> None:
    mapped = HTMLToBubbleMapper(base_url="https://example.test/base/").map_tree(
        {"type": "img", "attributes": {"src": source}}
    )
    assert mapped is not None
    assert mapped["bubble_type"] == "Image"


def test_unknown_source_tag_falls_back_to_a_container() -> None:
    mapped = HTMLToBubbleMapper().map_tree(
        {
            "type": "custom-card",
            "text": "",
            "attributes": {"class": ["account-card"]},
            "computed_styles": {"display": "flex", "flex-direction": "column"},
            "children": [{"type": "span", "text": "Account", "attributes": {}, "children": []}],
        }
    )

    assert mapped is not None
    assert mapped["bubble_type"] == "__fragment__"
    assert mapped["children"][0]["properties"]["content"] == "Account"


@pytest.mark.parametrize(
    ("raw", "fallback", "expected"),
    [
        ("12px", None, 12),
        ("12.6", None, 13),
        (12, None, 12),
        ("auto", 7, 7),
        (None, None, None),
    ],
)
def test_integer_dimension_contract(raw: object, fallback: int | None, expected: int | None) -> None:
    assert HTMLToBubbleMapper()._to_int(raw, fallback) == expected


@pytest.mark.parametrize(
    ("raw", "dimension", "margin"),
    [
        ("14px", 14, 14),
        ("-8.4px", None, -8),
        ("20%", None, None),
        ("20vw", None, None),
        ("20junk", None, None),
        ("none", None, None),
        ("", None, None),
    ],
)
def test_css_dimension_contract(raw: object, dimension: int | None, margin: int | None) -> None:
    mapper = HTMLToBubbleMapper()
    assert mapper._parse_dimension(raw) == dimension
    assert mapper._parse_margin_value(raw) == margin


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12px", 12.0), ("-2.25", -2.25), (3, 3.0), ("bad", None), (None, None)],
)
def test_float_contract(raw: object, expected: float | None) -> None:
    assert HTMLToBubbleMapper()._to_float(raw) == expected


def test_layout_numeric_helpers_handle_valid_and_malformed_values() -> None:
    mapper = HTMLToBubbleMapper()

    assert mapper._percent_value("37.5%") == 37.5
    assert mapper._percent_value("37px") is None
    assert mapper._grid_column_count("repeat(4, minmax(0, 1fr))") == 4
    assert mapper._grid_column_count("1fr 2fr 1fr") == 3
    assert mapper._grid_column_count("") == 1
    assert mapper._parse_gap("16px 24px") == 16
    assert mapper._parse_gap("normal") == 0
    assert mapper._parse_z_index("12") == 12
    assert mapper._parse_z_index("auto") is None
    assert mapper._normalize_opacity_percent("0.42") == 42
    assert mapper._normalize_opacity_percent("42") == 42
    assert mapper._normalize_opacity_percent("bad") is None


def test_typography_helpers_normalize_css_contracts() -> None:
    mapper = HTMLToBubbleMapper()

    assert mapper._font_weight_num("bold") == 700
    assert mapper._font_weight_num("semibold") == 600
    assert mapper._font_weight_num("525") == 525
    assert mapper._font_weight_num("invalid") == 400
    assert mapper._parse_font_family({"font-family": '"Inter", Arial, sans-serif'}) == "Inter"
    assert mapper._parse_font_family({}) is None
    assert mapper._parse_letter_spacing("0.1em", 20) == 2.0
    assert mapper._parse_letter_spacing("2px", 16) == 2.0
    assert mapper._parse_letter_spacing("normal", 16) is None
    assert mapper._parse_line_height("24px", 16, False) == 1.5
    assert mapper._parse_line_height("1.25", 16, False) == 1.25
    assert mapper._parse_line_height("normal", 16, True) == 1.1
    assert mapper._apply_text_transform("hello world", "uppercase") == "HELLO WORLD"
    assert mapper._apply_text_transform("HELLO", "lowercase") == "hello"
    assert mapper._apply_text_transform("hello world", "capitalize") == "Hello World"
    assert mapper._apply_text_transform("same", "none") == "same"


def test_css_variable_and_color_helpers_are_safe() -> None:
    mapper = HTMLToBubbleMapper()
    styles = {"--brand": "#155eef", "--nested": "var(--brand)", "color": "rgb(1, 2, 3)"}

    assert mapper._resolve_css_value("var(--brand)", styles) == "#155eef"
    assert mapper._resolve_css_value("var(--missing, #fff)", styles) == "#fff"
    assert mapper._resolve_css_value("var(--nested)", styles) == "#155eef"
    assert mapper._resolve_color("var(--brand)", styles) == "#155eef"
    assert mapper._normalize_color("rgba(1, 2, 3, 0.5)") == "rgba(1, 2, 3, 0.5)"
    assert mapper._normalize_color("transparent") is None
    assert mapper._text_color("", styles, default="#000000") == "#000000"
    assert mapper._is_default_link_blue("rgb(0, 0, 238)") is True
    assert mapper._is_default_link_blue("#155eef") is False
    assert mapper._color_with_opacity("#112233", 0.5) == "rgba(17, 34, 51, 0.5000)"
    assert mapper._color_with_opacity(None, 0.5) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "linear-gradient(to right, #000000 0%, rgba(255, 255, 255, 0.5) 100%)",
            {
                "background_style": "gradient",
                "gradient_style": "linear",
                "gradient_direction": "right",
                "gradient_start_color": "rgba(255, 255, 255, 0.5000)",
                "gradient_end_color": "#000000",
            },
        ),
        (
            "radial-gradient(circle, #ffffff 0%, #000000 100%)",
            {
                "background_style": "gradient",
                "gradient_style": "radial",
                "gradient_start_color": "#ffffff",
                "gradient_end_color": "#000000",
            },
        ),
        ("none", None),
    ],
)
def test_native_gradient_contract(raw: str, expected: dict[str, Any] | None) -> None:
    assert HTMLToBubbleMapper()._extract_native_gradient_props(raw) == expected


def test_gradient_and_background_helpers_handle_nested_css_functions() -> None:
    mapper = HTMLToBubbleMapper(base_url="https://example.test/base/")

    assert mapper._split_css_args("90deg, rgba(0, 0, 0, .5), var(--brand, #fff)") == [
        "90deg",
        "rgba(0, 0, 0, .5)",
        "var(--brand, #fff)",
    ]
    assert mapper._function_inner("linear-gradient(red, blue)", "linear-gradient") == "red, blue"
    assert mapper._function_inner("red", "linear-gradient") is None
    assert mapper._looks_like_gradient_direction("to bottom right") is True
    assert mapper._looks_like_gradient_direction("45deg") is True
    assert mapper._looks_like_gradient_direction("red") is False
    assert mapper._gradient_angle("to right") == 90.0
    assert mapper._gradient_angle("to bottom") == 180.0
    assert mapper._extract_background_image_url('url("asset.png")') == "https://example.test/base/asset.png"
    assert mapper._extract_background_image_url("none") is None
    placeholder = mapper._gradient_placeholder_image("linear-gradient(red, blue)")
    assert placeholder is not None and placeholder.startswith("data:image/svg+xml;utf8,")


def test_rich_text_mapping_preserves_nested_style_deltas_and_whitespace() -> None:
    mapped = _map_html(
        '<p style="font-size:16px;color:#101828">Hello '
        '<strong style="font-weight:700">bold</strong> '
        '<span style="color:#155eef">blue</span><br>next</p>'
    )
    assert mapped is not None
    content = mapped["children"][0]["properties"]["content"]

    assert content == "Hello [b]bold[/b] [color=#155eef]blue[/color]\nnext"
