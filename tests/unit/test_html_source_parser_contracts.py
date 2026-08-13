from __future__ import annotations

import pytest

from bubble_mcp.aria_runtime.html_to_bubble.source_parser import HTMLParser


def test_parse_applies_supported_css_and_normalizes_semantic_text() -> None:
    parsed = HTMLParser().parse(
        """
        <style>
          /* ignored */
          *, .card.primary { box-sizing: border-box; }
          #hero { color: rgb(1, 2, 3); }
          button.cta:hover { font-weight: 700; }
          .parent .child, [data-kind] { opacity: 0.5; }
          .empty { ; }
        </style>
        <main id="hero" class="card primary flex flex-col gap-4 text-center font-bold text-2xl py-2 px-3 bg-white">
          Direct <span style="color: blue">inline</span>
          <h1><span>H</span><span>e</span><span>l</span><span>l</span><span>o</span><span>W</span><span>o</span><span>r</span><span>l</span><span>d</span></h1>
          <button class="cta"> Save <strong>now</strong> </button>
        </main>
        """
    )

    node = next(child for child in parsed["children"] if child["type"] == "main")
    assert node["attributes"]["class"][:3] == ["card", "primary", "flex"]
    assert node["computed_styles"] == {
        "display": "flex",
        "flex-direction": "column",
        "gap": "16px",
        "text-align": "center",
        "font-weight": "700",
        "font-size": "24px",
        "padding-top": "8px",
        "padding-bottom": "8px",
        "padding-left": "12px",
        "padding-right": "12px",
        "background-color": "#ffffff",
        "box-sizing": "border-box",
        "color": "rgb(1, 2, 3)",
    }
    assert node["text"] == "Direct inline"
    assert node["children"][1]["text"] == "Hello World"
    assert node["children"][2]["text"] == "Save now"
    assert node["children"][2]["computed_styles"]["font-weight"] == "700"


def test_parse_inline_segments_preserve_spacing_breaks_and_styles() -> None:
    node = HTMLParser().parse(
        '<p style="font-size: 16px">Hello <strong style="font-weight:700">world</strong><br> again</p>'
    )["children"][0]

    assert [segment["text"] for segment in node["text_segments"]] == [
        "Hello ",
        "world",
        "\n",
        " again",
    ]
    assert node["text_segments"][1]["styles"] == {
        "font-size": "16px",
        "font-weight": "700",
    }
    assert node["text_segments"][2]["raw_text"] == "\n"


def test_parse_snapshot_normalizes_renderer_attributes_and_media() -> None:
    parsed = HTMLParser(base_url="https://example.test/pages/index.html").parse_snapshot(
        {
            "type": "element",
            "tag": "IMG",
            "attributes": {
                "class": "hero-image  rounded",
                "src": "../assets/hero.png",
                "disabled": None,
                "style": "width: 320px; height: 180px",
            },
            "computedStyle": {"display": "block", "width": "320px"},
            "rect": {"width": 320, "height": 180},
            "intrinsic": {"width": 1280, "height": 720},
            "pseudo": {"after": {"content": "none"}},
            "children": [],
            "text": "",
        }
    )

    assert parsed["type"] == "img"
    assert parsed["attributes"]["class"] == ["hero-image", "rounded"]
    assert parsed["attributes"]["disabled"] == ""
    assert parsed["computed_styles"] == {"display": "block", "width": "320px"}
    assert parsed["media_url"] == "https://example.test/assets/hero.png"
    assert parsed["intrinsic"] == {"width": 1280, "height": 720}


def test_parse_snapshot_handles_text_segments_breaks_and_invalid_roots() -> None:
    parser = HTMLParser()
    node = parser.parse_snapshot(
        {
            "type": "element",
            "tag": "p",
            "attributes": {},
            "computedStyle": {"color": "#111111"},
            "text": "Hello world",
            "children": [
                {"type": "text", "rawText": " Hello ", "leadingSpace": True, "trailingSpace": True},
                {
                    "type": "element",
                    "tag": "strong",
                    "computedStyle": {"font-weight": "700"},
                    "children": [{"type": "text", "text": "world"}],
                },
                {"type": "element", "tag": "br", "children": []},
                {"type": "comment", "text": "ignored"},
            ],
        }
    )

    assert [segment["text"] for segment in node["text_segments"]] == [" Hello ", "world", "\n"]
    assert node["text_segments"][1]["styles"] == {"color": "#111111", "font-weight": "700"}
    assert parser.parse_snapshot({"type": "document", "children": []})["children"] == []
    assert parser.parse_snapshot(None)["children"] == []  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("classes", "expected"),
    [
        (["grid", "grid-cols-3", "gap-2", "text-end", "font-semibold", "text-lg"], {"display": "grid", "grid-template-columns": "3", "gap": "8px", "text-align": "right", "font-weight": "600", "font-size": "18px"}),
        (["d-inline-flex", "flex-row", "g-3", "text-start", "font-medium", "text-base"], {"display": "flex", "flex-direction": "row", "gap": "12px", "text-align": "left", "font-weight": "500", "font-size": "16px"}),
        (["md:flex", "flex-column", "text-sm", "px-0.5", "py-1.5"], {"display": "flex", "flex-direction": "column", "font-size": "14px", "padding-left": "2px", "padding-right": "2px", "padding-top": "6px", "padding-bottom": "6px"}),
    ],
)
def test_infer_from_framework_classes(classes: list[str], expected: dict[str, str]) -> None:
    assert HTMLParser()._infer_from_classes(classes) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://cdn.test/a.png", "https://cdn.test/a.png"),
        ("data:image/png;base64,AA", "data:image/png;base64,AA"),
        ("/image.png", "https://example.test/image.png"),
        ("'asset.png'", "https://example.test/base/asset.png"),
        ("javascript:alert(1)", ""),
        ("#fragment", ""),
        (None, ""),
    ],
)
def test_absolutize_url_contract(raw: object, expected: str) -> None:
    parser = HTMLParser(base_url="https://example.test/base/page.html")
    assert parser._absolutize_url(raw) == expected


def test_media_candidates_and_css_url_are_selected_safely() -> None:
    parser = HTMLParser(base_url="https://example.test/base/")
    cases = [
        ({"attributes": {"data-src": "lazy.png"}, "styles": {}}, "https://example.test/base/lazy.png"),
        ({"attributes": {"data-lottie-url": "/anim.json"}, "styles": {}}, "https://example.test/anim.json"),
        ({"attributes": {"poster": "poster.jpg"}, "styles": {}}, "https://example.test/base/poster.jpg"),
        ({"attributes": {}, "styles": {"background-image": 'url("bg.png")'}}, "https://example.test/base/bg.png"),
    ]
    for node, expected in cases:
        parser._inject_media_url(node)
        assert node["media_url"] == expected

    unsafe = {"attributes": {"src": "javascript:alert(1)"}, "styles": {}}
    parser._inject_media_url(unsafe)
    assert "media_url" not in unsafe
    assert parser._extract_media_from_style({"background": "red"}) == ""


def test_private_parsing_boundaries_reject_noise() -> None:
    parser = HTMLParser()

    assert parser.parse("")["children"] == []
    assert parser.parse_element("not-a-tag") is None
    assert parser._parse_inline_styles("invalid; color: red; :bad; width: ; padding: 2px:3px") == {
        "color": "red",
        "padding": "2px:3px",
    }
    assert parser._parse_css_rules("bad; .empty{} .ok { color: red } trailing") == [
        {"selector": ".ok", "styles": {"color": "red"}}
    ]
    assert parser._selector_matches("div", "hero", ["card", "primary"], "*") is True
    assert parser._selector_matches("div", "hero", ["card", "primary"], "#hero") is True
    assert parser._selector_matches("div", "hero", ["card", "primary"], ".card.primary") is True
    assert parser._selector_matches("div", "hero", ["card", "primary"], "div.card") is True
    assert parser._selector_matches("span", "hero", ["card"], "div.card") is False
    assert parser._selector_matches("div", "hero", ["card"], ".missing") is False
    assert parser._selector_matches("div", "hero", ["card"], ".card:hover") is True
    assert parser._selector_matches("div", "hero", ["card"], ".parent .card") is False
    assert parser._selector_matches("div", "hero", ["card"], "") is False
    assert parser._selector_matches("div", "hero", ["card"], ":hover") is False
    assert parser._normalize_segment_raw_text("   ") == " "
    assert parser._normalize_segment_raw_text("") == ""
    assert parser._normalize_segment_raw_text(" hello ", leading=True, trailing=True) == " hello "
    assert parser._compact_fragmented_text("short text") == "short text"
