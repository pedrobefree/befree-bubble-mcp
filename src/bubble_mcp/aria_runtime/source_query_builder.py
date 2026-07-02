#!/usr/bin/env python3
"""
Reusable builder for Bubble source query JSON expressions.

Used by CLI/MCP to avoid duplicating `%ds` construction logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_message_chain(field_path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Build nested Message nodes for relation mapping (supports dot paths)."""
    raw = str(field_path or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(".") if p.strip()]
    if not parts:
        return None
    head: Optional[Dict[str, Any]] = None
    cursor: Optional[Dict[str, Any]] = None
    for part in parts:
        node: Dict[str, Any] = {
            "%x": "Message",
            "%nm": part,
            "is_slidable": False,
        }
        if head is None:
            head = node
        if cursor is not None:
            cursor["%n"] = node
        cursor = node
    return head


def _to_constraint_item(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Each constraint must be an object.")

    if "%k" in item:
        key = item.get("%k")
        op = item.get("%c2", "equals")
        value = item.get("%v")
    else:
        key = item.get("field") or item.get("key")
        op = (
            item.get("operator")
            or item.get("op")
            or item.get("constraint")
            or item.get("constraint_type")
            or "equals"
        )
        if "value_expr" in item:
            value = item.get("value_expr")
        elif "value_expression" in item:
            value = item.get("value_expression")
        elif "value" in item:
            value = item.get("value")
        else:
            value = None

    key_text = str(key or "").strip()
    if not key_text:
        raise ValueError("Constraint is missing field key (`%k` or `field`).")

    op_text = str(op or "").strip() or "equals"
    return {"%k": key_text, "%c2": op_text, "%v": value}


def normalize_constraints(constraints: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Normalize constraints into Bubble `%co` map with string indexes.

    Accepted forms:
    - list of Bubble constraints (`%k/%c2/%v`)
    - list of friendly constraints (`field/operator/value`)
    - dict map with numeric keys -> constraint objects
    - single constraint object
    """
    if constraints is None:
        return None

    if isinstance(constraints, list):
        result: Dict[str, Dict[str, Any]] = {}
        for idx, item in enumerate(constraints):
            result[str(idx)] = _to_constraint_item(item)
        return result or None

    if isinstance(constraints, dict):
        if "%k" in constraints or "field" in constraints or "key" in constraints:
            return {"0": _to_constraint_item(constraints)}

        result: Dict[str, Dict[str, Any]] = {}
        ordered_keys: List[str] = sorted(constraints.keys(), key=lambda x: str(x))
        for idx, key in enumerate(ordered_keys):
            result[str(idx)] = _to_constraint_item(constraints[key])
        return result or None

    raise ValueError("Constraints must be JSON object or JSON array.")


def build_search_source_expression(
    query_source_type: str,
    constraints: Any = None,
    ignore_empty_constraints: Optional[bool] = None,
    sort_field: Optional[str] = None,
    sort_desc: Optional[bool] = None,
    dynamic_sort_field: Any = None,
    geo_reference: Any = None,
    result_from_field: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a Bubble source JSON expression for search-based dynamic sources.
    """
    source_type = str(query_source_type or "").strip()
    if not source_type:
        raise ValueError("query_source_type is required.")

    payload: Dict[str, Any] = {
        "%x": "Search",
        "%p": {
            "%t5": source_type,
        },
    }

    co = normalize_constraints(constraints)
    if co:
        payload["%p"]["%co"] = co

    if ignore_empty_constraints is True:
        payload["%p"]["ignore_empty_constraints"] = True

    if sort_field:
        payload["%p"]["%sf"] = str(sort_field).strip()
        if sort_desc is not None:
            payload["%p"]["%d2"] = bool(sort_desc)
        # Bubble often includes this key; keep null default for compatibility.
        payload["%p"]["dynamic_sort_field"] = dynamic_sort_field
        if geo_reference is not None:
            payload["%p"]["geo_reference"] = geo_reference

    rel = build_message_chain(result_from_field)
    if rel:
        payload["%n"] = rel

    return payload
