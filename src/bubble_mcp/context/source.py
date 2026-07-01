"""Load compact Bubble project context from JSON fixtures or future crawler artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_context(path: Path) -> BubbleProjectContext:
    """Load a compact context JSON document."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Context document must be a JSON object")

    nodes = [
        BubbleContextNode(
            id=str(item.get("id") or ""),
            label=str(item.get("label") or ""),
            type=str(item.get("type") or "unknown"),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        )
        for item in _as_list(payload.get("nodes"))
        if isinstance(item, dict) and item.get("id") and item.get("label")
    ]
    edges = [
        BubbleContextEdge(
            source=str(item.get("source") or ""),
            target=str(item.get("target") or ""),
            type=str(item.get("type") or "related"),
        )
        for item in _as_list(payload.get("edges"))
        if isinstance(item, dict) and item.get("source") and item.get("target")
    ]
    return BubbleProjectContext(
        app_id=str(payload.get("app_id") or "unknown"),
        source=str(payload.get("source") or path.name),
        nodes=nodes,
        edges=edges,
    )


def save_context(context: BubbleProjectContext, path: Path) -> None:
    """Persist a compact context JSON document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "app_id": context.app_id,
        "source": context.source,
        "nodes": [
            {
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "metadata": node.metadata,
            }
            for node in context.nodes
        ],
        "edges": [
            {"source": edge.source, "target": edge.target, "type": edge.type}
            for edge in context.edges
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
