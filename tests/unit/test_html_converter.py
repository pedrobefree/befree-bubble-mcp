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
