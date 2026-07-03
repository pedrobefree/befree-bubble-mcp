"""Small deterministic planner for common Bubble requests."""

from __future__ import annotations

import re

from bubble_mcp.planner.example_matcher import match_example
from bubble_mcp.planner.models import BubblePlan, PlanStep


def _extract_quoted_or_after_saying(message: str) -> str:
    quoted = re.search(r"['\"]([^'\"]+)['\"]", message)
    if quoted:
        return quoted.group(1).strip()
    saying = re.search(r"\b(?:saying|with text|texto|dizendo)\s+(.+)$", message, re.IGNORECASE)
    if saying:
        return saying.group(1).strip().strip(".")
    return "New text"


def plan_message(message: str, context: str = "index", parent: str = "index") -> BubblePlan:
    """Plan a common Bubble request without calling an LLM."""

    normalized = message.lower()
    warnings: list[str] = []
    if re.search(r"\b(delete|remove|apagar|deletar)\b", normalized):
        return BubblePlan(
            message=message,
            steps=[],
            risk="destructive_mutation",
            requires_approval=True,
            warnings=["Destructive requests are recognized but not planned by the bootstrap planner."],
        )
    example_match = match_example(message, context=context, parent=parent)
    if example_match is not None:
        return BubblePlan(
            message=message,
            risk=example_match.entry.risk,
            requires_approval=False,
            warnings=warnings,
            metadata={
                "routing": {
                    "parser": "example_match",
                    "corpus_entry": example_match.entry.id,
                    "score": example_match.score,
                    "utterance": example_match.utterance,
                }
            },
            steps=[
                PlanStep(
                    id="step_1",
                    tool_name=example_match.tool_name,
                    args=example_match.args,
                )
            ],
        )
    if re.search(r"\b(text|texto)\b", normalized):
        content = _extract_quoted_or_after_saying(message)
        return BubblePlan(
            message=message,
            risk="routine_visual_mutation",
            requires_approval=False,
            warnings=warnings,
            metadata={"routing": {"parser": "regex", "rule": "create_text"}},
            steps=[
                PlanStep(
                    id="step_1",
                    tool_name="create_text",
                    args={
                        "context": context,
                        "parent": parent,
                        "content": content,
                    },
                )
            ],
        )
    if re.search(r"\b(group|container|section|card|grupo)\b", normalized):
        return BubblePlan(
            message=message,
            risk="routine_visual_mutation",
            requires_approval=False,
            warnings=warnings,
            metadata={"routing": {"parser": "regex", "rule": "create_group"}},
            steps=[
                PlanStep(
                    id="step_1",
                    tool_name="create_group",
                    args={
                        "context": context,
                        "parent": parent,
                        "name": "Generated group",
                    },
                )
            ],
        )
    return BubblePlan(
        message=message,
        steps=[],
        risk="unknown",
        requires_approval=False,
        metadata={"routing": {"parser": "none"}},
        warnings=["No deterministic Bubble plan matched this request."],
    )
