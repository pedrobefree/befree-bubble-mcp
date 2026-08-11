"""Compose compact Bubble contexts while preserving source precedence."""

from __future__ import annotations

from copy import deepcopy

from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext

COMPLETE = "complete"
PARTIAL = "partial"

_TOPOLOGY_KEYS = {
    "bubble_id",
    "children",
    "context",
    "key",
    "path_array",
    "root_id",
}


def _has_value(value: object) -> bool:
    return value not in (None, "", [], {})


def _merge_missing(primary: dict[str, object], complement: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(primary)
    for key, value in complement.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_missing(current, value)
        elif key not in merged or not _has_value(current):
            merged[key] = deepcopy(value)
    return merged


def _merge_node_metadata(
    primary: dict[str, object],
    complement: dict[str, object],
    *,
    complement_is_topology: bool,
) -> dict[str, object]:
    merged = _merge_missing(primary, complement)
    if complement_is_topology:
        for key in _TOPOLOGY_KEYS:
            value = complement.get(key)
            if _has_value(value):
                merged[key] = deepcopy(value)
    return merged


def _merge_nodes(
    primary: BubbleContextNode,
    complement: BubbleContextNode,
    *,
    complement_is_topology: bool,
) -> BubbleContextNode:
    primary_bubble_id = str(primary.metadata.get("bubble_id") or "")
    label = primary.label
    if (not label or label == primary_bubble_id) and complement.label:
        label = complement.label
    return BubbleContextNode(
        id=primary.id,
        label=label,
        type=primary.type or complement.type,
        metadata=_merge_node_metadata(
            primary.metadata,
            complement.metadata,
            complement_is_topology=complement_is_topology,
        ),
    )


def merge_project_contexts(
    primary: BubbleProjectContext,
    complement: BubbleProjectContext,
    *,
    source: str,
    complement_is_topology: bool = False,
) -> BubbleProjectContext:
    """Merge a lower-priority context into a primary context by stable node id."""

    nodes_by_id = {node.id: node for node in primary.nodes}
    node_order = [node.id for node in primary.nodes]
    for node in complement.nodes:
        existing = nodes_by_id.get(node.id)
        if existing is None:
            nodes_by_id[node.id] = node
            node_order.append(node.id)
            continue
        nodes_by_id[node.id] = _merge_nodes(
            existing,
            node,
            complement_is_topology=complement_is_topology,
        )

    edges: list[BubbleContextEdge] = []
    edge_keys: set[tuple[str, str, str]] = set()
    for edge in [*primary.edges, *complement.edges]:
        key = (edge.source, edge.target, edge.type)
        if key in edge_keys:
            continue
        edge_keys.add(key)
        edges.append(edge)

    return BubbleProjectContext(
        app_id=primary.app_id if primary.app_id != "unknown" else complement.app_id,
        source=source,
        nodes=[nodes_by_id[node_id] for node_id in node_order],
        edges=edges,
        metadata=_merge_missing(primary.metadata, complement.metadata),
    )


def with_provenance(
    context: BubbleProjectContext,
    *,
    primary_source: str,
    sources: list[str],
    completeness: str,
    bubble_export_available: bool,
) -> BubbleProjectContext:
    """Attach safe source provenance to a compact context."""

    if completeness not in {COMPLETE, PARTIAL}:
        raise ValueError(f"Unsupported context completeness: {completeness}")
    metadata = deepcopy(context.metadata)
    metadata["provenance"] = {
        "primary_source": primary_source,
        "sources": list(dict.fromkeys(sources)),
        "completeness": completeness,
        "bubble_export_available": bubble_export_available,
    }
    return BubbleProjectContext(
        app_id=context.app_id,
        source=context.source,
        nodes=context.nodes,
        edges=context.edges,
        metadata=metadata,
    )
