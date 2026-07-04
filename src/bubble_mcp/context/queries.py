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


def _exact_candidates(node: BubbleContextNode) -> list[tuple[str, str]]:
    values = [("id", node.id), ("label", node.label)]
    for key in ("bubble_id", "context", "element_type", "path", "path_array"):
        value = node.metadata.get(key)
        if isinstance(value, str):
            values.append((key, value))
        elif isinstance(value, list):
            values.append((key, "/".join(str(item) for item in value)))
    return [(field, value.strip()) for field, value in values if value and value.strip()]


def _result_payload(
    node: BubbleContextNode,
    *,
    score: int,
    match: str | None,
    match_field: str | None = None,
    match_value: str | None = None,
    include_metadata: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node.id,
        "label": node.label,
        "type": node.type,
        "score": score,
    }
    if match:
        payload["match"] = match
    if match_field:
        payload["match_field"] = match_field
    if match_value:
        payload["match_value"] = match_value
    if include_metadata:
        payload["metadata"] = node.metadata
    return payload


def search_context(
    context: BubbleProjectContext,
    query: str,
    limit: int = 10,
    *,
    exact: bool = False,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """Return simple lexical matches from the context graph."""

    normalized_query = query.strip().lower()
    if exact:
        if not normalized_query:
            return []
        matches: list[tuple[BubbleContextNode, str, str]] = []
        for node in context.nodes:
            for field, value in _exact_candidates(node):
                if normalized_query == value.lower():
                    matches.append((node, field, value))
                    break
        return [
            _result_payload(
                node,
                score=1,
                match="exact",
                match_field=field,
                match_value=value,
                include_metadata=include_metadata,
            )
            for node, field, value in matches[:limit]
        ]

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
        _result_payload(node, score=score, match=None, include_metadata=include_metadata)
        for score, node in scored[:limit]
    ]


def context_find_payload(
    context: BubbleProjectContext,
    query: str,
    limit: int = 10,
    *,
    exact: bool = False,
    include_metadata: bool = True,
) -> dict[str, Any]:
    """Return context search results with an agent-friendly summary envelope."""

    safe_limit = max(0, limit)
    raw_limit = safe_limit + 1 if safe_limit else 1
    raw_results = search_context(
        context,
        query,
        raw_limit,
        exact=exact,
        include_metadata=include_metadata,
    )
    truncated = safe_limit > 0 and len(raw_results) > safe_limit
    results = raw_results[:safe_limit]
    return {
        "query": query,
        "limit": safe_limit,
        "count": len(results),
        "truncated": truncated,
        "exact": exact,
        "include_metadata": include_metadata,
        "results": results,
    }


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
