"""Lint /appeditor/write payloads for decoded-key node bodies.

Bubble's internal app tree uses encoded keys (``%x`` = type, ``%p`` = properties,
``%nm`` = name, ``%dn`` = default_name). The .bubble export is the DECODED form
(``type``/``properties``/``name``/``default_name``). A body written with decoded
keys at a node position (under ``%el``, ``%wf``, or ``actions``) is accepted by the
server with HTTP 200 and even round-trips through the exporter — but the editor
cannot interpret the node and renders it as ``[missing: null]``.

This lint flags exactly that case so agents copy serialization from the live app
tree (encoded), not from the export (decoded).
"""

from __future__ import annotations

from typing import Any

_NODE_MARKERS = {"%el", "%wf", "actions"}
_DECODED_TO_ENCODED = {
    "type": "%x",
    "properties": "%p",
    "default_name": "%dn",
}
_EXPRESSION_DECODED_TO_ENCODED = {
    **_DECODED_TO_ENCODED,
    "next": "%n",
    "name": "%nm",
    "entries": "%e",
    "arguments": "%a",
    "args": "%a",
}
_EXPRESSION_NODE_TYPES = {
    "APIEventParameter",
    "CurrentPageItem",
    "CurrentUser",
    "ElementParent",
    "Empty",
    "GetElement",
    "Message",
    "OneOptionValue",
    "PageData",
    "PreviousStep",
    "Search",
    "State",
    "TextExpression",
    "ThisElement",
}


def _nested_decoded_expression(value: Any, path: tuple[str, ...] = ()) -> tuple[tuple[str, ...], list[str]] | None:
    if isinstance(value, dict):
        node_type = str(value.get("%x") or value.get("type") or "")
        if node_type in _EXPRESSION_NODE_TYPES:
            decoded = [key for key in _EXPRESSION_DECODED_TO_ENCODED if key in value]
            if decoded:
                return path, decoded
        for key, child in value.items():
            found = _nested_decoded_expression(child, (*path, str(key)))
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _nested_decoded_expression(child, (*path, str(index)))
            if found is not None:
                return found
    return None


def _is_node_position(path_array: Any) -> bool:
    if not isinstance(path_array, list):
        return False
    parts = [str(part) for part in path_array]
    for index, part in enumerate(parts):
        if part in _NODE_MARKERS and index < len(parts) - 1:
            return True
    return False


def _body_issues(path_str: str, body: Any) -> list[str]:
    if not isinstance(body, dict):
        return []
    decoded_present = [key for key in _DECODED_TO_ENCODED if key in body]
    encoded_present = any(key in body for key in ("%x", "%p"))
    if decoded_present and not encoded_present:
        mapping = ", ".join(f"'{key}' -> '{_DECODED_TO_ENCODED[key]}'" for key in decoded_present)
        return [
            f"{path_str}: node body uses decoded export keys ({mapping}). The editor stores nodes with "
            + "encoded keys (%x=type, %p=properties, %nm=name, %dn=default_name); decoded keys are "
            + "accepted by the server but render as '[missing: null]' in the editor. Copy the "
            + "serialization from a sibling node in the live app tree, not from the .bubble export."
        ]

    node_type = str(body.get("%x") or "")
    properties = body.get("%p")
    if not isinstance(properties, dict):
        return []
    if node_type == "CustomElement" and "custom_id" in properties:
        return [
            f"{path_str}: CustomElement uses normalized property 'custom_id'; editor writes require "
            + "the canonical wire key '%ci'. HTTP 200 does not prove this reference resolved."
        ]
    if node_type == "ChangePage" and "element_id" in properties:
        return [
            f"{path_str}: ChangePage uses normalized property 'element_id'; editor writes require "
            + "the canonical wire key '%ei'. HTTP 200 does not prove this destination resolved."
        ]
    nested = _nested_decoded_expression(properties, ("%p",))
    if nested is not None:
        nested_path, decoded_keys = nested
        mapping = ", ".join(
            f"'{key}' -> '{_EXPRESSION_DECODED_TO_ENCODED[key]}'" for key in decoded_keys
        )
        return [
            f"{path_str}/{'/'.join(nested_path)}: nested expression uses decoded export keys "
            f"({mapping}). Serialize the complete expression tree to canonical wire keys before writing."
        ]
    return []


def lint_editor_write_changes(changes: Any) -> list[str]:
    """Return human-readable issues for decoded-key node bodies in a changes list."""

    issues: list[str] = []
    if not isinstance(changes, list):
        return issues
    for change in changes:
        if not isinstance(change, dict):
            continue
        path_array = change.get("path_array")
        if not _is_node_position(path_array):
            continue
        path_str = "/".join(str(part) for part in path_array) if isinstance(path_array, list) else "?"
        issues.extend(_body_issues(path_str, change.get("body")))
    return issues


_ACTION_MARKER = "actions"


def _contains_expression_node(value: Any) -> bool:
    if isinstance(value, dict):
        if str(value.get("%x") or value.get("type") or "") in _EXPRESSION_NODE_TYPES:
            return True
        return any(_contains_expression_node(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_expression_node(child) for child in value)
    return False


_API_EVENT_PARAMETER_REQUIRED = ("btype_id", "event_id", "param_id", "param_name")


def _incomplete_api_event_parameters(value: Any, found: list[str]) -> None:
    if isinstance(value, dict):
        type_name = str(value.get("type") or value.get("%x") or "")
        if type_name == "APIEventParameter":
            raw_properties = value.get("properties")
            raw_legacy_properties = value.get("%p")
            if isinstance(raw_properties, dict):
                props = raw_properties
            elif isinstance(raw_legacy_properties, dict):
                props = raw_legacy_properties
            else:
                props = {}
            missing = [key for key in _API_EVENT_PARAMETER_REQUIRED if not str(props.get(key) or "").strip()]
            if missing:
                found.append(", ".join(missing))
        for child in value.values():
            _incomplete_api_event_parameters(child, found)
    elif isinstance(value, list):
        for child in value:
            _incomplete_api_event_parameters(child, found)


def lint_expression_warnings(changes: Any) -> list[str]:
    """Warn (never block) on hand-composed expression nodes inside workflow actions.

    The raw encoding of expressions (APIEventParameter, Message chains, param ids) is
    NOT derivable from the .bubble export — the export decodes node keys, humanizes
    param ids, and renames message tokens. /appeditor/write returns HTTP 200 for any
    body, so a "successful" write can still render as broken in the editor.
    """

    warnings: list[str] = []
    if not isinstance(changes, list):
        return warnings
    for change in changes:
        if not isinstance(change, dict):
            continue
        path_array = change.get("path_array")
        if not isinstance(path_array, list) or _ACTION_MARKER not in [str(p) for p in path_array]:
            continue
        body = change.get("body")
        if not isinstance(body, dict):
            continue
        props = body.get("%p")
        if not isinstance(props, dict):
            continue
        path_str = "/".join(str(part) for part in path_array)
        incomplete: list[str] = []
        _incomplete_api_event_parameters(props, incomplete)
        if incomplete:
            warnings.append(
                f"{path_str}: APIEventParameter node is missing required context fields ({'; '.join(incomplete)}). "
                "Confirmed against live editor memory: the parameter only resolves with btype_id + event_id + "
                "param_id + param_name together (param_id is the parameter KEY, e.g. 'Client'), plus "
                "is_slidable: false on every expression node. Without the type context the editor renders an "
                "unresolved parameter and '[not found: ...]' messages."
            )
        if not _contains_expression_node(props):
            continue
        expression_types = sorted(
            {t for t in _EXPRESSION_NODE_TYPES if f'"{t}"' in str(props) or f"'{t}'" in str(props)}
        )
        warnings.append(
            f"{path_str}: action body contains hand-composed expression nodes "
            f"({', '.join(expression_types) or 'expression'}). The raw expression encoding is NOT derivable "
            "from the .bubble export (it decodes node keys, param ids, and message tokens), and the server "
            "returns HTTP 200 for any body — a 200 is not success; verify the render in the editor. Prefer "
            "add_action for supported action types, or compose from a payload captured from real editor "
            "traffic (bubble_tool_wizard_start), or configure one action by hand and Copy/Paste it."
        )
    return warnings


# Property values the editor stores as a closed enum. The MCP catalog exposes
# friendlier labels for some of them (bg_style: none|color|image|gradient), and a
# label written verbatim is accepted by /appeditor/write with HTTP 200 while the
# Issue Checker reports "<element> - is not a possible option".
_ENUM_WIRE_VALUES: dict[str, dict[str, str]] = {
    "%bas": {
        "color": "bgcolor",
        "flat color": "bgcolor",
        "flat": "bgcolor",
        "flatcolor": "bgcolor",
        "background color": "bgcolor",
    },
}
_ENUM_ALLOWED_VALUES: dict[str, set[str]] = {
    "%bas": {"none", "bgcolor", "image", "gradient"},
}


def _enum_issue(wire_key: str, value: Any, path_str: str) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().lower().replace("_", " ").replace("-", " ")
    allowed = _ENUM_ALLOWED_VALUES.get(wire_key, set())
    if raw in allowed:
        return None
    suggestion = _ENUM_WIRE_VALUES.get(wire_key, {}).get(raw)
    expected = ", ".join(sorted(allowed))
    hint = f" Use '{suggestion}'." if suggestion else ""
    return (
        f"{path_str}: '{wire_key}' = '{value}' is not a Bubble wire value (expected one of: {expected})."
        f"{hint} The server accepts it with HTTP 200, but the Issue Checker reports "
        "'<element> - is not a possible option'."
    )


def lint_enum_warnings(changes: Any) -> list[str]:
    """Warn (never block) on property values outside a known Bubble wire enum."""

    warnings: list[str] = []
    if not isinstance(changes, list):
        return warnings
    for change in changes:
        if not isinstance(change, dict):
            continue
        path_array = change.get("path_array")
        parts = [str(part) for part in path_array] if isinstance(path_array, list) else []
        path_str = "/".join(parts) if parts else "?"
        body = change.get("body")
        if parts and parts[-1] in _ENUM_WIRE_VALUES:
            issue = _enum_issue(parts[-1], body, path_str)
            if issue:
                warnings.append(issue)
            continue
        props = body.get("%p") if isinstance(body, dict) else None
        if not isinstance(props, dict):
            continue
        for wire_key in _ENUM_WIRE_VALUES:
            if wire_key in props:
                issue = _enum_issue(wire_key, props[wire_key], path_str)
                if issue:
                    warnings.append(issue)
    return warnings
