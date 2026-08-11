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


def _node_merge_key(node: BubbleContextNode) -> tuple[str, str, str]:
    bubble_id = str(node.metadata.get("bubble_id") or "").strip()
    if bubble_id:
        return ("bubble_id", node.type, bubble_id)
    return ("node_id", node.type, node.id)


def _unique_node_id(node: BubbleContextNode, used_ids: set[str]) -> str:
    if node.id not in used_ids:
        return node.id
    bubble_id = str(node.metadata.get("bubble_id") or "").strip()
    base = f"{node.id}:{bubble_id}" if bubble_id else f"{node.id}:{node.type}"
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}:{suffix}"
        suffix += 1
    return candidate


def _with_node_id(node: BubbleContextNode, node_id: str) -> BubbleContextNode:
    if node.id == node_id:
        return node
    return BubbleContextNode(
        id=node_id,
        label=node.label,
        type=node.type,
        metadata=node.metadata,
    )


def _remap_node_context(
    node: BubbleContextNode,
    node_id_remap: dict[str, str],
) -> BubbleContextNode:
    context = node.metadata.get("context")
    if not isinstance(context, str) or context not in node_id_remap:
        return node
    metadata = deepcopy(node.metadata)
    metadata["context"] = node_id_remap[context]
    return BubbleContextNode(
        id=node.id,
        label=node.label,
        type=node.type,
        metadata=metadata,
    )


def merge_project_contexts(
    primary: BubbleProjectContext,
    complement: BubbleProjectContext,
    *,
    source: str,
    complement_is_topology: bool = False,
) -> BubbleProjectContext:
    """Merge a lower-priority context into a primary context by stable Bubble id."""

    nodes_by_key = {_node_merge_key(node): node for node in primary.nodes}
    node_order = [_node_merge_key(node) for node in primary.nodes]
    used_ids = {node.id for node in primary.nodes}
    complement_id_remap: dict[str, str] = {}
    remap_context_keys: set[tuple[str, str, str]] = set()
    for node in complement.nodes:
        key = _node_merge_key(node)
        existing = nodes_by_key.get(key)
        if existing is None:
            node_id = _unique_node_id(node, used_ids)
            complement_id_remap[node.id] = node_id
            remap_context_keys.add(key)
            used_ids.add(node_id)
            nodes_by_key[key] = _with_node_id(node, node_id)
            node_order.append(key)
            continue
        complement_id_remap[node.id] = existing.id
        complement_context = node.metadata.get("context")
        if _has_value(complement_context) and (
            complement_is_topology or not _has_value(existing.metadata.get("context"))
        ):
            remap_context_keys.add(key)
        nodes_by_key[key] = _merge_nodes(
            existing,
            node,
            complement_is_topology=complement_is_topology,
        )

    nodes = [
        _remap_node_context(nodes_by_key[key], complement_id_remap)
        if key in remap_context_keys
        else nodes_by_key[key]
        for key in node_order
    ]
    edges: list[BubbleContextEdge] = []
    edge_keys: set[tuple[str, str, str]] = set()
    remapped_complement_edges = [
        BubbleContextEdge(
            source=complement_id_remap.get(edge.source, edge.source),
            target=complement_id_remap.get(edge.target, edge.target),
            type=edge.type,
        )
        for edge in complement.edges
    ]
    for edge in [*primary.edges, *remapped_complement_edges]:
        key = (edge.source, edge.target, edge.type)
        if key in edge_keys:
            continue
        edge_keys.add(key)
        edges.append(edge)

    return BubbleProjectContext(
        app_id=primary.app_id if primary.app_id != "unknown" else complement.app_id,
        source=source,
        nodes=nodes,
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
