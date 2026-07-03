"""Post-write validation helpers for runtime smoke suites."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bubble_mcp.context.models import BubbleContextNode
from bubble_mcp.context.source import load_context


def _properties(node: BubbleContextNode) -> dict[str, Any]:
    raw = node.metadata.get("properties")
    return raw if isinstance(raw, dict) else {}


def _text_value(value: Any) -> str:
    if isinstance(value, dict):
        entries = value.get("entries") or value.get("%e")
        if isinstance(entries, dict):
            return "".join(str(entries[key]) for key in sorted(entries, key=lambda item: int(item) if str(item).isdigit() else 9999))
    return str(value or "")


def _element_type(node: BubbleContextNode) -> str:
    return str(node.metadata.get("element_type") or "")


def _node_by_id(nodes: list[BubbleContextNode], node_id: str) -> BubbleContextNode | None:
    return next((node for node in nodes if node.id == node_id), None)


def _nodes_for_context(nodes: list[BubbleContextNode], context_id: str) -> list[BubbleContextNode]:
    return [node for node in nodes if str(node.metadata.get("context") or "") == context_id]


def _check_page(page: BubbleContextNode | None, expected_children: set[str]) -> list[str]:
    errors: list[str] = []
    if page is None:
        return ["temporary smoke page was not found in refreshed context."]
    if page.type != "page":
        errors.append(f"temporary smoke page has type {page.type!r}, expected 'page'.")
    children = set(str(child) for child in page.metadata.get("children") or [])
    missing_children = expected_children - children
    if missing_children:
        errors.append(f"temporary smoke page missing child ids: {sorted(missing_children)}.")
    return errors


def validate_execute_write_context(context_file: Path, *, run_id: str) -> dict[str, Any]:
    """Validate that an execute-write smoke run materialized in a compact context."""

    context = load_context(context_file)
    page_name = f"mcp_smoke_{run_id}"
    page_id = f"page:{page_name}"
    page = _node_by_id(context.nodes, page_id)
    page_elements = _nodes_for_context(context.nodes, page_id)

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def add_check(name: str, ok: bool, detail: str, node: BubbleContextNode | None = None) -> None:
        checks.append(
            {
                "name": name,
                "ok": ok,
                "detail": detail,
                "node_id": node.id if node else None,
                "label": node.label if node else None,
            }
        )
        if not ok:
            errors.append(detail)

    group = next(
        (
            node
            for node in page_elements
            if _element_type(node) == "Group"
            and _properties(node).get("container_layout") == "column"
            and _properties(node).get("fit_height") is True
        ),
        None,
    )
    add_check(
        "group_defaults",
        group is not None,
        "expected Group with column layout and fit_height=true in temporary page.",
        group,
    )

    text = next(
        (
            node
            for node in page_elements
            if _element_type(node) == "Text"
            and _properties(node).get("fit_height") is True
            and f"Runtime smoke {run_id}" in _text_value(_properties(node).get("text"))
        ),
        None,
    )
    add_check(
        "text_defaults",
        text is not None,
        "expected Text with fit_height=true and smoke run text content.",
        text,
    )

    button = next(
        (
            node
            for node in page_elements
            if _element_type(node) == "Button"
            and _properties(node).get("fit_width") is True
            and _properties(node).get("fit_height") is True
            and "Runtime smoke" in _text_value(_properties(node).get("text"))
        ),
        None,
    )
    add_check(
        "button_defaults",
        button is not None,
        "expected Button with fit_width=true, fit_height=true, and smoke label.",
        button,
    )

    input_node = next(
        (
            node
            for node in page_elements
            if _element_type(node) == "Input"
            and _properties(node).get("fixed_height") is True
            and "Runtime smoke" in _text_value(_properties(node).get("placeholder"))
        ),
        None,
    )
    add_check(
        "input_defaults",
        input_node is not None,
        "expected Input with fixed_height=true and smoke placeholder.",
        input_node,
    )

    expected_children = {node.metadata.get("bubble_id") for node in [group, text, button, input_node] if node is not None}
    errors.extend(_check_page(page, set(str(child) for child in expected_children if child)))

    return {
        "ok": not errors,
        "context_file": str(context_file),
        "run_id": run_id,
        "page": page_name,
        "page_id": page_id,
        "summary": context.summary(),
        "checks": checks,
        "errors": errors,
    }
