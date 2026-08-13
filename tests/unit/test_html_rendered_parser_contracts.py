from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.aria_runtime.html_to_bubble.parser import HTMLParser


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12px", 12.0),
        ("-2.5px", -2.5),
        ("42", 42.0),
        (0, None),
        ("auto", None),
        ("1rem", None),
        ("", None),
    ],
)
def test_parse_px_contract(raw: object, expected: float | None) -> None:
    assert HTMLParser()._parse_px(raw) == expected


def test_parse_hydrates_each_raw_html_node_once(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = HTMLParser()
    calls: list[str] = []
    original = parser._hydrate_rendered_inline_geometry

    def counted(node: dict[str, Any] | None) -> None:
        if isinstance(node, dict):
            calls.append(str(node.get("type")))
        original(node)

    monkeypatch.setattr(parser, "_hydrate_rendered_inline_geometry", counted)

    parsed = parser.parse(
        '<section style="width:640px;height:480px;left:12px;top:7px">'
        '<div style="width:320px"><h1 style="height:40px">Title</h1></div>'
        "</section>"
    )

    section = parsed["children"][0]
    assert section["rect"] == {
        "width": 640.0,
        "height": 480.0,
        "left": 12.0,
        "x": 12.0,
        "top": 7.0,
        "y": 7.0,
    }
    assert section["children"][0]["rect"] == {"width": 320.0}
    assert section["children"][0]["children"][0]["rect"] == {"height": 40.0}
    assert calls == ["h1", "div", "section"]


def test_parse_snapshot_hydrates_missing_geometry_without_overwriting_renderer_rect() -> None:
    parsed = HTMLParser().parse_snapshot(
        {
            "type": "element",
            "tag": "div",
            "attributes": {"style": "width: 200px; height: 100px; left: 5px; top: 9px"},
            "computedStyle": {"display": "block"},
            "rect": {"width": 180, "height": 0},
            "children": [],
        }
    )

    assert parsed["computed_styles"] == {
        "display": "block",
        "width": "200px",
        "height": "100px",
        "left": "5px",
        "top": "9px",
    }
    assert parsed["rect"] == {
        "width": 180,
        "height": 100.0,
        "left": 5.0,
        "x": 5.0,
        "top": 9.0,
        "y": 9.0,
    }


def test_snapshot_computed_style_is_not_overwritten_by_inline_declarations() -> None:
    parsed = HTMLParser().parse_snapshot(
        {
            "type": "element",
            "tag": "p",
            "attributes": {"style": "color: #222222 !important; width: 320px"},
            "computedStyle": {"color": "#111111", "width": "300px"},
            "rect": {},
            "children": [],
        }
    )

    assert parsed["computed_styles"] == {"color": "#111111", "width": "300px"}
    assert parsed["styles"] == {}
    assert parsed["rect"] == {"width": 300.0}


def test_progressbar_snapshot_uses_normalized_renderer_classes() -> None:
    parsed = HTMLParser().parse_snapshot(
        {
            "type": "element",
            "tag": "div",
            "attributes": {"class": "cs_progressbar"},
            "children": [
                {
                    "type": "element",
                    "tag": "div",
                    "attributes": {"class": "cs_progressbar_head"},
                    "computedStyle": {"font-size": "16px"},
                    "children": [{"type": "text", "text": "Old"}],
                },
                {
                    "type": "element",
                    "tag": "div",
                    "attributes": {"data-progress": "82"},
                    "children": [],
                },
            ],
        }
    )

    head = parsed["children"][0]
    assert head["text"] == "82%"
    assert head["text_segments"] == [
        {
            "text": "82%",
            "styles": {"font-size": "16px"},
            "raw_text": "82%",
            "leading_space": False,
            "trailing_space": False,
        }
    ]


def test_progressbar_and_interactive_normalizers_ignore_incomplete_nodes() -> None:
    parser = HTMLParser()
    cases: list[dict[str, Any] | None] = [
        None,
        {},
        {"type": "div", "attributes": {"class": []}},
        {"type": "div", "attributes": {"class": ["cs_progressbar"]}, "children": []},
        {
            "type": "div",
            "attributes": {"class": ["cs_progressbar"]},
            "children": [{"type": "span", "attributes": {"data-progress": ""}}],
        },
    ]
    for node in cases:
        parser._normalize_progressbar_node(node)

    untouched = {"type": "a", "text": "Keep", "children": []}
    parser._normalize_interactive_container_text(untouched)
    assert untouched["text"] == "Keep"


def test_interactive_container_drops_duplicate_text_for_mixed_media_structure() -> None:
    parser = HTMLParser()
    mixed = {
        "type": "button",
        "text": "Play Video",
        "text_segments": [{"text": "Play Video"}],
        "children": [
            {"type": "div", "children": [{"type": "span", "children": [{"type": "svg", "children": []}]}]},
            {"type": "span", "text": "Play Video", "children": []},
        ],
    }
    parser._normalize_interactive_container_text(mixed)
    assert mixed["text"] == ""
    assert mixed["text_segments"] == []

    inline_only = {
        "type": "label",
        "text": "Avatar",
        "children": [{"type": "span", "children": [{"type": "img", "children": []}]}],
    }
    parser._normalize_interactive_container_text(inline_only)
    assert inline_only["text"] == "Avatar"

    non_interactive = {"type": "div", "text": "Keep", "children": [{"type": "img", "children": []}]}
    parser._normalize_interactive_container_text(non_interactive)
    assert non_interactive["text"] == "Keep"


def test_geometry_hydration_ignores_invalid_nodes_and_preserves_existing_values() -> None:
    parser = HTMLParser()
    parser._hydrate_rendered_inline_geometry(None)
    node = {
        "type": "div",
        "styles": {"": "ignored", "width": "500px", "height": "bad", "left": "10px", "top": "20px"},
        "computed_styles": {"width": "400px"},
        "rect": {"width": 300, "left": 4, "top": ""},
    }
    parser._hydrate_rendered_inline_geometry(node)

    assert node["computed_styles"]["width"] == "400px"
    assert node["rect"] == {"width": 300, "left": 4, "top": 20.0, "y": 20.0}
