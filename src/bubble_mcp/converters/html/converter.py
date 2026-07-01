"""Convert simple HTML documents into Bubble plans."""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag

from bubble_mcp.planner.models import BubblePlan, PlanStep


TEXT_TAGS = {"h1", "h2", "h3", "p", "span", "label", "button", "a"}
GROUP_TAGS = {"div", "section", "main", "article", "header", "footer", "nav", "form"}


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def html_to_plan(html: str, context: str = "index", parent: str = "index") -> BubblePlan:
    """Build a conservative Bubble plan from HTML."""

    soup = BeautifulSoup(html, "html.parser")
    steps: list[PlanStep] = []
    group_count = 0
    text_count = 0

    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        tag = element.name.lower()
        if tag in GROUP_TAGS:
            group_count += 1
            classes = element.get("class")
            class_name = classes[0] if isinstance(classes, list) and classes else None
            element_name = element.get("id") if isinstance(element.get("id"), str) else None
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    tool_name="create_group",
                    args={
                        "context": context,
                        "parent": parent,
                        "name": element_name or class_name or f"html_group_{group_count}",
                    },
                )
            )
            continue
        if tag in TEXT_TAGS:
            text = _clean_text(element.get_text(" ", strip=True))
            if not text:
                continue
            text_count += 1
            steps.append(
                PlanStep(
                    id=f"step_{len(steps) + 1}",
                    tool_name="create_text",
                    args={
                        "context": context,
                        "parent": parent,
                        "content": text,
                        "name": f"html_text_{text_count}",
                    },
                )
            )

    return BubblePlan(
        message="Import HTML as Bubble plan",
        steps=steps,
        risk="routine_visual_mutation" if steps else "unknown",
        requires_approval=False,
        warnings=[] if steps else ["No supported HTML elements were found."],
    )
