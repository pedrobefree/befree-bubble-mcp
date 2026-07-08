from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from bubble_mcp.style_import.html import extract_style_rules_from_html
from bubble_mcp.style_import.mapper import map_rules_to_style_candidate
from bubble_mcp.style_import.models import BubbleStyleCandidate
from bubble_mcp.style_import.planner import build_style_operations
from bubble_mcp.style_import.render import fetch_url_html, render_url_to_html


DEFAULT_ELEMENT_TYPE = "Group"
DEFAULT_STYLE_NAME_PREFIX = "HTML"
StyleOperationExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]
StylePostExecutionVerifier = Callable[[dict[str, Any]], dict[str, Any]]


def _read_html_source(*, html: str | None, html_file: str | None, file: str | None) -> str:
    if html is not None:
        return html

    path_value = html_file or file
    if path_value is not None:
        return Path(path_value).read_text(encoding="utf-8")

    raise ValueError("build_style_import_plan requires html, html_file, or file.")


def _selector_for_element(element: Any) -> str | None:
    element_id = element.get("id")
    if isinstance(element_id, str) and element_id.strip():
        return f"#{element_id.strip()}"

    classes = element.get("class")
    if isinstance(classes, list) and classes:
        first_class = next((str(class_name).strip() for class_name in classes if class_name), "")
        if first_class:
            return f".{first_class}"

    return None


def _infer_selector(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(True):
        selector = _selector_for_element(element)
        if selector is not None:
            return selector

    raise ValueError("selector is required when no id or class selector can be inferred from HTML.")


def _summary(
    *,
    candidates: list[BubbleStyleCandidate],
    operations: list[dict[str, Any]],
    unsupported: list[dict[str, str]],
) -> dict[str, Any]:
    state_count = sum(len(candidate.states) for candidate in candidates)
    return {
        "candidate_count": len(candidates),
        "style_count": len(candidates),
        "operation_count": len(operations),
        "state_count": state_count,
        "unsupported_count": len(unsupported),
    }


def build_style_import_plan(
    html: str,
    *,
    profile: str,
    selector: str | None = None,
    style_name: str | None = None,
    style_name_prefix: str | None = None,
    element_type: str = "",
    execute: bool = False,
    extra_css: list[str] | None = None,
    include_states: bool = True,
    states: list[str] | None = None,
) -> dict[str, Any]:
    resolved_style_name = str(style_name or "").strip()
    if not resolved_style_name:
        raise ValueError("build_style_import_plan requires style_name.")
    resolved_element_type = str(element_type or "").strip()
    if not resolved_element_type:
        raise ValueError("build_style_import_plan requires element_type.")
    resolved_selector = selector or _infer_selector(html)
    rules = extract_style_rules_from_html(
        html,
        resolved_selector,
        extra_css=extra_css or (),
    )

    if not include_states:
        rules = [rule for rule in rules if rule.state == "base"]
    elif states is not None:
        allowed_states = {"base", *normalize_state_names(states)}
        rules = [rule for rule in rules if rule.state in allowed_states]

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix=style_name_prefix or DEFAULT_STYLE_NAME_PREFIX,
        element_type=resolved_element_type,
        selector=resolved_selector,
    )
    candidate = replace(candidate, name=resolved_style_name)
    candidates = [candidate]
    operations = build_style_operations(profile, candidates, execute)
    unsupported = [item for candidate_item in candidates for item in candidate_item.unsupported]

    summary = _summary(candidates=candidates, operations=operations, unsupported=unsupported)
    candidate_dicts = [candidate_item.to_dict() for candidate_item in candidates]

    return {
        "ok": True,
        "profile": profile,
        "execute": execute,
        "selector": resolved_selector,
        "style_name": resolved_style_name,
        "element_type": resolved_element_type,
        "identity": {
            "style_name": resolved_style_name,
            "element_type": resolved_element_type,
            "match": "name_and_element_type",
            "mode": "upsert",
        },
        "candidates": candidate_dicts,
        "styles": candidate_dicts,
        "operations": operations,
        "unsupported": unsupported,
        "summary": summary,
        "style_count": summary["style_count"],
        "operation_count": summary["operation_count"],
    }


def _execute_style_operations(
    operations: list[dict[str, Any]],
    executor: StyleOperationExecutor,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        tool = str(operation.get("tool") or "").strip()
        arguments = operation.get("arguments")
        if not tool or not isinstance(arguments, dict):
            raise ValueError(f"Invalid style operation at index {index}.")
        result = executor(tool, arguments)
        results.append({"tool": tool, "ok": bool(result.get("ok", True)), "result": result})
        if result.get("ok") is False:
            break
    return results


def create_styles_from_html_runtime(
    *,
    profile: str,
    selector: str | None = None,
    style_name: str | None = None,
    style_prefix: str | None = None,
    style_name_prefix: str | None = None,
    element_type: str = "",
    html: str | None = None,
    html_file: str | None = None,
    file: str | None = None,
    url: str | None = None,
    rendered_html: bool | None = None,
    render_timeout_ms: int = 35000,
    execute: bool = False,
    include_states: bool = True,
    states: list[str] | None = None,
    extra_css: list[str] | None = None,
    executor: StyleOperationExecutor | None = None,
    verifier: StylePostExecutionVerifier | None = None,
    **_: Any,
) -> dict[str, Any]:
    source: dict[str, Any]
    if url is not None:
        resolved_url = str(url or "").strip()
        if not resolved_url:
            raise ValueError("create_styles_from_html_runtime requires a non-empty url.")
        if not str(selector or "").strip():
            raise ValueError("create_styles_from_html_runtime requires selector when url is provided.")
        use_rendered_html = True if rendered_html is None else bool(rendered_html)
        source_html = (
            render_url_to_html(url=resolved_url, selector=str(selector), timeout_ms=render_timeout_ms)
            if use_rendered_html
            else fetch_url_html(url=resolved_url, timeout_ms=render_timeout_ms)
        )
        source = {
            "type": "url",
            "url": resolved_url,
            "rendered_html": use_rendered_html,
            "selector": selector,
        }
    else:
        source_html = _read_html_source(html=html, html_file=html_file, file=file)
        source = {
            "type": "html" if html is not None else "file",
            "html_file": html_file or file,
            "rendered_html": False,
        }
    result = build_style_import_plan(
        source_html,
        profile=profile,
        selector=selector,
        style_name=style_name,
        style_name_prefix=style_name_prefix or style_prefix,
        element_type=element_type,
        execute=execute,
        extra_css=extra_css,
        include_states=include_states,
        states=states,
    )
    result["source"] = source
    result["executed"] = False
    if execute:
        if executor is None:
            raise ValueError("create_styles_from_html_runtime requires an executor when execute=true.")
        if verifier is None:
            raise ValueError("create_styles_from_html_runtime requires a verifier when execute=true.")
        execution_results = _execute_style_operations(result["operations"], executor)
        result["execution_results"] = execution_results
        result["executed"] = all(item["ok"] for item in execution_results)
        result["ok"] = result["executed"]
        verification = verifier(result["candidates"][0])
        result["verification"] = verification
        result["verified"] = bool(verification.get("ok"))
        result["ok"] = bool(result["ok"] and result["verified"])
    return result


def normalize_state_names(states: list[str] | None) -> list[str] | None:
    if states is None:
        return None
    return [re.sub(r"^:", "", state).lower() for state in states]
