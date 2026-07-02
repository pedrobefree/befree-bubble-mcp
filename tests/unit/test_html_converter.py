from pathlib import Path

from bubble_mcp.aria_runtime.html_to_bubble import HTMLParser, HTMLToBubbleMapper
from bubble_mcp.aria_runtime.bubble_sdk import PathDiscovery
from bubble_mcp.converters.html.converter import html_to_plan
from bubble_mcp.html_runtime import _render_config_from_profile
from bubble_mcp.validators.semantic import validate_plan


def test_html_to_plan_creates_groups_and_text() -> None:
    html = Path("tests/fixtures/html/login-card.html").read_text(encoding="utf-8")

    plan = html_to_plan(html)
    payload = plan.to_dict()

    assert [step["tool_name"] for step in payload["steps"]] == [
        "create_group",
        "create_text",
        "create_text",
        "create_text",
    ]
    assert payload["steps"][1]["args"]["content"] == "Welcome back"
    assert validate_plan(payload)["ok"] is True


def test_aria_runtime_html_parser_is_self_contained() -> None:
    parsed = HTMLParser().parse("<section style='display:flex;background:#fff'><h1>Hello</h1></section>")
    mapped = HTMLToBubbleMapper().map_tree(parsed)

    assert parsed["children"][0]["type"] == "section"
    assert mapped is not None
    assert mapped["bubble_type"] == "__fragment__"
    assert mapped["children"][0]["bubble_type"] == "Text"
    assert mapped["children"][0]["properties"]["content"] == "Hello"


def test_aria_runtime_mapper_preserves_gradient_container_and_pseudo_layer() -> None:
    element = {
        "type": "header",
        "attributes": {"class": "header-area v2 angle-1"},
        "computed_styles": {
            "display": "block",
            "position": "relative",
            "width": "1440px",
            "height": "1014px",
            "padding-top": "250px",
            "padding-bottom": "250px",
            "background-image": "linear-gradient(to right, rgb(80, 64, 244) 0%, rgb(49, 180, 254) 100%)",
        },
        "rect": {"width": 1440, "height": 1014},
        "pseudo": {
            "after": {
                "position": "absolute",
                "left": "0px",
                "bottom": "-1px",
                "width": "1440px",
                "height": "144px",
                "background-image": 'url("data:image/svg+xml,%3Csvg%3E%3C/svg%3E")',
                "opacity": "1",
            }
        },
        "children": [
            {
                "type": "div",
                "attributes": {"class": "container"},
                "computed_styles": {
                    "display": "block",
                    "width": "1170px",
                    "height": "514px",
                    "margin-left": "135px",
                    "margin-right": "135px",
                },
                "rect": {"width": 1170, "height": 514},
                "children": [],
            }
        ],
    }

    mapped = HTMLToBubbleMapper().map_tree(element)

    assert mapped is not None
    props = mapped["properties"]
    assert props["layout"] == "relative"
    assert props["gradient_direction"] == "right"
    assert props["gradient_start_color"] == "rgb(49, 180, 254)"
    assert props["gradient_end_color"] == "rgb(80, 64, 244)"
    container = mapped["children"][0]
    assert container["properties"]["horiz_alignment"] == "center"
    assert container["properties"]["max_width_css"] == "1170px"
    pseudo = mapped["children"][-1]
    assert pseudo["properties"]["__pseudo_background"] is True
    assert pseudo["properties"]["nonant_alignment"] == "ac"
    assert pseudo["properties"]["height"] == 144


def test_aria_runtime_render_config_is_preserved_from_profile() -> None:
    render_config = _render_config_from_profile(
        {
            "app_id": "demo",
            "rendered_html_default": True,
            "renderer_mode": "local",
            "render_cache_dir": "/tmp/bubble-render-cache",
            "render": {
                "render_timeout_ms": 42000,
                "auto_install_local_renderer": False,
            },
        }
    )

    assert render_config == {
        "rendered_html_default": True,
        "renderer_mode": "local",
        "render_cache_dir": "/tmp/bubble-render-cache",
        "render_timeout_ms": 42000,
        "auto_install_local_renderer": False,
    }


def test_aria_runtime_path_discovery_applies_mutation_overlay(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app_path = tmp_path / "app.bubble"
    overlay_path = tmp_path / "mutation-overlay.json"
    app_path.write_text('{"pages": {}, "%p3": {}}', encoding="utf-8")
    overlay_path.write_text(
        """
{
  "entries": [
    {
      "changes": [
        {
          "intent": {"name": "CreatePage"},
          "path_array": ["%p3", "mcp01"],
          "body": {"id": "mcp01", "%nm": "mcp-01"}
        }
      ]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    discovery = PathDiscovery(str(app_path), mutation_overlay_path=str(overlay_path))

    assert discovery.find_page("mcp-01") == "mcp01"
