"""Search and summarize Bubble project context."""

from __future__ import annotations

import re
from typing import Any

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 2
    }


def search_context(context: BubbleProjectContext, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return simple lexical matches from the context graph."""

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[int, BubbleContextNode]] = []
    for node in context.nodes:
        haystack = " ".join(
            [
                node.label,
                node.type,
                " ".join(str(value) for value in node.metadata.values()),
            ]
        )
        node_tokens = tokenize(haystack)
        score = len(query_tokens & node_tokens)
        if score:
            scored.append((score, node))

    scored.sort(key=lambda item: (-item[0], item[1].type, item[1].label))
    return [
        {
            "id": node.id,
            "label": node.label,
            "type": node.type,
            "score": score,
            "metadata": node.metadata,
        }
        for score, node in scored[:limit]
    ]


def context_neighbors(context: BubbleProjectContext, node_id: str) -> dict[str, Any]:
    """Return direct neighbors for a context node."""

    nodes_by_id = {node.id: node for node in context.nodes}
    related_edges = [
        edge for edge in context.edges if edge.source == node_id or edge.target == node_id
    ]
    neighbor_ids = {
        edge.target if edge.source == node_id else edge.source
        for edge in related_edges
    }
    return {
        "node": nodes_by_id.get(node_id),
        "edges": related_edges,
        "neighbors": [nodes_by_id[item] for item in sorted(neighbor_ids) if item in nodes_by_id],
    }
