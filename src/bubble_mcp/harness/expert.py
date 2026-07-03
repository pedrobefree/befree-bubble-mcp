"""Export redacted expert captures into eval-friendly artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.core.redaction import redact_sensitive


ELEMENT_TOOL_MAP = {
    "text": "create_text",
    "group": "create_group",
    "button": "create_button",
    "image": "create_image",
    "html": "create_html",
    "input": "create_input",
    "dropdown": "create_dropdown",
    "checkbox": "create_checkbox",
    "repeatinggroup": "create_repeating_group",
    "floatinggroup": "create_floating_group",
    "popup": "create_popup",
}


def _truncate_strings(value: Any, *, max_chars: int = 2000) -> Any:
    if isinstance(value, dict):
        return {str(key): _truncate_strings(child, max_chars=max_chars) for key, child in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(item, max_chars=max_chars) for item in value]
    if isinstance(value, str) and len(value) > max_chars:
        return f"{value[:max_chars]}...[TRUNCATED:{len(value) - max_chars}]"
    return value


def sanitize_expert_artifact(value: Any) -> Any:
    """Redact secrets and cap very large strings in a capture artifact."""

    return _truncate_strings(redact_sensitive(value))


def _payload_from_capture(item: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        item.get("payload"),
        item.get("write_payload"),
        item.get("body"),
        item.get("request"),
    ]
    request = item.get("request")
    if isinstance(request, dict):
        candidates.extend([request.get("payload"), request.get("body")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            body = candidate.get("body") if isinstance(candidate.get("body"), dict) else candidate
            if isinstance(body, dict) and isinstance(body.get("changes"), list):
                return body
    return None


def _change_family(change: dict[str, Any]) -> str:
    intent = change.get("intent")
    intent_name = str(intent.get("name") or "") if isinstance(intent, dict) else ""
    path = change.get("path_array") or change.get("path") or []
    path_parts = [str(part) for part in path] if isinstance(path, list) else []
    if intent_name == "CreateElement":
        return "visual_element"
    if "CreatePage" in intent_name:
        return "page"
    if any(part in {"%wf", "workflows", "actions"} for part in path_parts):
        return "workflow"
    if any(part in {"data_types", "user_types"} for part in path_parts):
        return "data_schema"
    if "option_sets" in path_parts:
        return "option_set"
    if any(part in {"styles", "colors"} for part in path_parts):
        return "style"
    if "Delete" in intent_name:
        return "delete"
    return "editor_write"


def _tool_hint(change: dict[str, Any], family: str) -> str | None:
    if family == "visual_element":
        body = change.get("body")
        element_type = str(body.get("%x") or body.get("type") or "") if isinstance(body, dict) else ""
        return ELEMENT_TOOL_MAP.get(element_type.replace(" ", "").lower()) or "create_element"
    if family == "page":
        return "create_page"
    if family == "workflow":
        return "add_action"
    if family == "data_schema":
        return "create_data_type"
    if family == "option_set":
        return "create_option_set"
    if family == "style":
        return "create_style"
    if family == "delete":
        return "delete_element"
    return None


def classify_editor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    changes = payload.get("changes")
    if not isinstance(changes, list):
        return {"families": [], "tool_hints": [], "change_count": 0}
    families: list[str] = []
    tool_hints: list[str] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        family = _change_family(change)
        if family not in families:
            families.append(family)
        hint = _tool_hint(change, family)
        if hint and hint not in tool_hints:
            tool_hints.append(hint)
    return {
        "families": families,
        "tool_hints": tool_hints,
        "change_count": len([change for change in changes if isinstance(change, dict)]),
        "app_id": payload.get("appname") or payload.get("app_id") or payload.get("appId"),
        "app_version": payload.get("app_version") or payload.get("appVersion"),
    }


def _capture_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("entries", "captures", "requests", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def _case_message(item: dict[str, Any], classification: dict[str, Any]) -> str:
    explicit = str(item.get("message") or item.get("prompt") or "").strip()
    if explicit:
        return explicit
    tool_hints = classification.get("tool_hints")
    if isinstance(tool_hints, list) and tool_hints:
        return f"Create a Bubble mutation using {tool_hints[0]}"
    families = classification.get("families")
    if isinstance(families, list) and families:
        return f"Apply a Bubble {families[0]} mutation"
    return "Apply a captured Bubble editor mutation"


def export_expert_eval_cases(input_path: Path, output_path: Path, *, limit: int = 250) -> dict[str, Any]:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    skipped = 0
    for index, item in enumerate(_capture_items(raw)):
        if len(cases) >= limit:
            break
        payload = _payload_from_capture(item)
        if payload is None:
            skipped += 1
            continue
        classification = classify_editor_payload(payload)
        tool_hints = classification.get("tool_hints")
        expected_tool = str(tool_hints[0]) if isinstance(tool_hints, list) and tool_hints else ""
        case: dict[str, Any] = {
            "id": str(item.get("id") or f"expert_capture_{index + 1:04d}"),
            "message": _case_message(item, classification),
            "classification": classification,
            "capture": sanitize_expert_artifact(item),
        }
        if expected_tool:
            case["expectedTool"] = expected_tool
        cases.append(case)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "input": str(input_path),
        "output": str(output_path),
        "cases": len(cases),
        "skipped": skipped,
    }
