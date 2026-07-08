"""Persist successful editor mutations as a local discovery overlay."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext
from bubble_mcp.context.detector import context_cache_dir


def _safe_name(value: str) -> str:
    text = str(value or "").strip()
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in text) or "default"


def mutation_overlay_path(profile: str, app_id: str) -> Path:
    return context_cache_dir() / _safe_name(profile) / f"{_safe_name(app_id)}-mutation-overlay.json"


def read_mutation_overlay(profile: str, app_id: str) -> dict[str, Any]:
    path = mutation_overlay_path(profile, app_id)
    if not path.exists():
        return {"version": 1, "profile": profile, "app_id": app_id, "entries": []}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {"entries": []}
    except Exception:
        return {"version": 1, "profile": profile, "app_id": app_id, "entries": []}


def record_mutation_overlay(
    *,
    profile: str,
    app_id: str,
    payload: dict[str, Any],
    source: str,
    response: Any | None = None,
) -> Path | None:
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        return None

    path = mutation_overlay_path(profile, app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = parsed
        except Exception:
            existing = {}

    entries = existing.get("entries")
    if not isinstance(entries, list):
        entries = []

    entries.append(
        {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile,
            "app_id": app_id,
            "source": source,
            "response": response if isinstance(response, dict) else None,
            "changes": json.loads(json.dumps(changes)),
        }
    )
    existing.update(
        {
            "version": 1,
            "profile": profile,
            "app_id": app_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
        }
    )
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _intent_name(change: dict[str, Any]) -> str:
    intent = _obj(change.get("intent"))
    return str(intent.get("name") or change.get("intent_name") or "")


def _path_array(change: dict[str, Any]) -> list[str]:
    raw = change.get("path_array") or change.get("path")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    return []


def _context_node_id(path_array: list[str]) -> str:
    if len(path_array) < 2:
        return "page:index"
    root = path_array[0]
    context = path_array[1]
    return f"reusable:{context}" if root == "%ed" else f"page:{context}"


def _node_key_from_path(path_array: list[str]) -> str:
    if path_array:
        return path_array[-1]
    return ""


def _page_node_from_change(change: dict[str, Any]) -> BubbleContextNode | None:
    body = _obj(change.get("body"))
    path_array = _path_array(change)
    key = str(body.get("id") or _node_key_from_path(path_array) or body.get("%nm") or "").strip()
    label = str(body.get("%nm") or body.get("name") or key).strip()
    if not key or not label:
        return None
    return BubbleContextNode(
        id=f"page:{label}",
        label=label,
        type="page",
        metadata={
            "bubble_id": key,
            "key": key,
            "path_array": ["%p3", key],
            "properties": body,
            "overlay": True,
        },
    )


def _element_node_from_change(change: dict[str, Any]) -> tuple[BubbleContextNode, BubbleContextEdge] | None:
    body = _obj(change.get("body"))
    props = _obj(body.get("%p") or body.get("properties"))
    path_array = _path_array(change)
    element_id = str(body.get("id") or _node_key_from_path(path_array) or "").strip()
    if not element_id:
        return None
    label = str(props.get("%nm") or props.get("name") or body.get("name") or element_id)
    element_type = str(body.get("%x") or body.get("type") or props.get("%x") or "element")
    parent_node = _context_node_id(path_array)
    if "%el" in path_array:
        last_el_index = len(path_array) - 1 - path_array[::-1].index("%el")
        if last_el_index >= 3:
            parent_key = path_array[last_el_index - 1]
            parent_node = f"element:{parent_key}"
    node = BubbleContextNode(
        id=f"element:{element_id}",
        label=label,
        type="element",
        metadata={
            "bubble_id": element_id,
            "element_type": element_type,
            "context": _context_node_id(path_array),
            "path_array": path_array,
            "properties": props,
            "children": [],
            "overlay": True,
        },
    )
    return node, BubbleContextEdge(source=parent_node, target=node.id, type="contains")


def overlay_summary(profile: str, app_id: str) -> dict[str, Any]:
    overlay = read_mutation_overlay(profile, app_id)
    entries = overlay.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {
        "path": str(mutation_overlay_path(profile, app_id)),
        "entries": len(entries),
        "updated_at": overlay.get("updated_at"),
    }


def _node_identity(node: BubbleContextNode) -> tuple[str, str, str, str]:
    path = node.metadata.get("path") or node.metadata.get("path_array")
    path_key = ".".join(str(item) for item in path) if isinstance(path, list) else ""
    context = str(node.metadata.get("context") or "")
    return (node.type, node.id, context, path_key)


def apply_mutation_overlay(
    context: BubbleProjectContext,
    *,
    profile: str,
    app_id: str | None = None,
) -> BubbleProjectContext:
    """Merge successful local MCP mutations into a compact context idempotently."""

    target_app_id = str(app_id or context.app_id or "").strip()
    if not profile or not target_app_id:
        return context

    overlay = read_mutation_overlay(profile, target_app_id)
    entries = overlay.get("entries")
    if not isinstance(entries, list) or not entries:
        return BubbleProjectContext(
            app_id=context.app_id,
            source=context.source,
            nodes=context.nodes,
            edges=context.edges,
            metadata={
                **context.metadata,
                "mutation_overlay": overlay_summary(profile, target_app_id),
            },
        )

    nodes_by_key = {_node_identity(node): node for node in context.nodes}
    edges_by_key = {(edge.source, edge.target, edge.type): edge for edge in context.edges}
    added_nodes = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            intent_name = _intent_name(change)
            if intent_name in {"CreatePage", "Create page"}:
                page_node = _page_node_from_change(change)
                if page_node is not None and _node_identity(page_node) not in nodes_by_key:
                    nodes_by_key[_node_identity(page_node)] = page_node
                    added_nodes += 1
            elif intent_name == "CreateElement":
                element = _element_node_from_change(change)
                if element is None:
                    continue
                node, edge = element
                if _node_identity(node) not in nodes_by_key:
                    nodes_by_key[_node_identity(node)] = node
                    added_nodes += 1
                edges_by_key.setdefault((edge.source, edge.target, edge.type), edge)

    return BubbleProjectContext(
        app_id=context.app_id,
        source=f"{context.source}+mutation_overlay",
        nodes=list(nodes_by_key.values()),
        edges=list(edges_by_key.values()),
        metadata={
            **context.metadata,
            "mutation_overlay": {
                **overlay_summary(profile, target_app_id),
                "applied": True,
                "nodes_added": added_nodes,
            },
        },
    )
