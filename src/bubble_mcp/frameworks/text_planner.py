"""Deterministic framework text to Bubble MCP program planner."""

from __future__ import annotations

import re
from typing import Any

from bubble_mcp.frameworks.adapters import get_adapter


_OBJECTIVE_RE = re.compile(r"^\s*(?:objective|story):\s*(?P<objective>.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_STEP_RE = re.compile(r"^\s*[-*]\s*(?P<step>.+?)\s*$", re.MULTILINE)
_FIND_PAGE_RE = re.compile(r"\b(?:find|verify)\s+page\s+(?P<query>.+?)(?:[.!?])?$", re.IGNORECASE)
_SECTION_RE = re.compile(
    r"\bcreate\s+a?\s*section\s+named\s+(?P<label>.+?)\s+inside\s+(?P<parent>.+?)(?:[.!?])?$",
    re.IGNORECASE,
)
_BUTTON_RE = re.compile(
    r"\b(?:add|create)\s+(?:a\s+)?button\s+labeled\s+(?P<text>.+?)\s+inside\s+(?P<parent>.+?)(?:[.!?])?$",
    re.IGNORECASE,
)
_BUTTON_DEFAULT_PARENT_RE = re.compile(
    r"\b(?:add|create)\s+(?:a\s+)?button\s+labeled\s+(?P<text>.+?)(?:[.!?])?$",
    re.IGNORECASE,
)
_VERIFY_RE = re.compile(r"\bverify\s+(?P<query>.+?)(?:[.!?])?$", re.IGNORECASE)


def _clean(value: str) -> str:
    return value.strip().strip(" .")


def _objective(text: str) -> str:
    match = _OBJECTIVE_RE.search(text)
    if match:
        objective = match.group("objective").strip()
        return objective or "Framework text program"

    for line in text.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith(("-", "*")):
            return candidate
    return "Framework text program"


def _line_steps(text: str) -> list[str]:
    return [_clean(match.group("step")) for match in _STEP_RE.finditer(text) if _clean(match.group("step"))]


def _clarification_result(*, framework: str, profile: str, questions: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "framework_text_requires_clarification",
        "framework": framework,
        "profile": profile,
        "questions": questions,
    }


def _parse_verify(line: str) -> dict[str, Any] | None:
    match = _VERIFY_RE.search(line)
    if not match:
        return None
    query = _clean(match.group("query")) or _clean(line)
    return {"intent": "verify_context", "query": query, "exact": False}


def _parse_step(line: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []

    find_page = _FIND_PAGE_RE.search(line)
    if find_page:
        steps.append({"intent": "verify_context", "query": _clean(find_page.group("query")), "exact": False})
        return steps

    section = _SECTION_RE.search(line)
    if section:
        steps.append(
            {
                "intent": "create_container",
                "context": "index",
                "parent": _clean(section.group("parent")) or "root",
                "label": _clean(section.group("label")),
            }
        )
        return steps

    button = _BUTTON_RE.search(line)
    if button:
        steps.append(
            {
                "intent": "create_button",
                "context": "index",
                "parent": _clean(button.group("parent")) or "root",
                "text": _clean(button.group("text")),
            }
        )
        return steps

    button_default_parent = _BUTTON_DEFAULT_PARENT_RE.search(line)
    if button_default_parent:
        steps.append(
            {
                "intent": "create_button",
                "context": "index",
                "parent": "root",
                "text": _clean(button_default_parent.group("text")),
            }
        )
        return steps

    lowered = line.lower()
    if "refresh" in lowered and "cache" in lowered:
        steps.append({"intent": "refresh_context"})

    verify = _parse_verify(line)
    if verify:
        steps.append(verify)

    return steps


def plan_framework_text(framework: str, profile: str, text: str) -> dict[str, Any]:
    """Convert simple framework instructions into a preview-first MCP program."""

    adapter = get_adapter(framework)
    framework_id = adapter.framework_id
    line_steps = _line_steps(text)
    steps = [parsed for line in line_steps for parsed in _parse_step(line)]

    missing_button_label = any(step.get("intent") == "create_button" and not step.get("text") for step in steps)
    if not steps or missing_button_label:
        return _clarification_result(
            framework=framework_id,
            profile=profile,
            questions=[
                "Which Bubble page, parent element, and element details should be changed?",
                "What exact text or label should be used for each button?",
            ],
        )

    return {
        "ok": True,
        "framework": framework_id,
        "profile": profile,
        "program": {
            "objective": _objective(text),
            "execution": {"mode": "preview", "approval": "required"},
            "steps": steps,
        },
    }
