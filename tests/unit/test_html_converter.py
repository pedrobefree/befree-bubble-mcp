from pathlib import Path

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
