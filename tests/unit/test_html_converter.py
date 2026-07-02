from pathlib import Path

from bubble_mcp.aria_runtime.html_to_bubble import HTMLParser, HTMLToBubbleMapper
from bubble_mcp.converters.html.converter import html_to_plan
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
