"""Read-only source inventory for Bubble cross-project transfers."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.dependencies import extract_node_dependencies
from bubble_mcp.transfer.models import SourceType, TransferInventory, TransferObjectRef


_CHILD_EDGE_TYPES = {"contains", "has_workflow"}


def _node_matches_ref(node: BubbleContextNode, source_ref: str) -> bool:
    normalized = source_ref.strip().lower()
    if not normalized:
        return False
    candidates: list[str] = [node.id, node.label]
    for key in ("bubble_id", "context", "path", "path_array"):
        value = node.metadata.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(str(item) for item in value)
            candidates.append("/".join(str(item) for item in value))
    return any(normalized == candidate.strip().lower() for candidate in candidates if candidate)


def _node_matches_context(node: BubbleContextNode, source_context: str | None) -> bool:
    normalized = str(source_context or "").strip().lower()
    if not normalized:
        return True
    context_value = str(node.metadata.get("context") or "").strip().lower()
    if context_value and normalized in {context_value, context_value.removeprefix("page:"), context_value.removeprefix("reusable:")}:
        return True
    path = node.metadata.get("path") or node.metadata.get("path_array")
    if isinstance(path, list):
        return any(normalized == str(item).strip().lower() for item in path)
    return False


def _resolve_source_node(
    context: BubbleProjectContext,
    *,
    source_type: SourceType,
    source_ref: str,
    source_context: str | None,
) -> BubbleContextNode:
    matches = [
        node
        for node in context.nodes
        if node.type == source_type
        and _node_matches_ref(node, source_ref)
        and _node_matches_context(node, source_context)
    ]
    if not matches and source_context:
        matches = [
            node
            for node in context.nodes
            if node.type == source_type and _node_matches_ref(node, source_ref)
        ]
    if not matches:
        raise ValueError(f"No {source_type} found for source_ref: {source_ref}")
    return matches[0]


def _subtree_nodes(context: BubbleProjectContext, root: BubbleContextNode) -> list[BubbleContextNode]:
    root_path = root.metadata.get("path") or root.metadata.get("path_array")
    if root.type in {"page", "reusable"} and isinstance(root_path, list) and root_path:
        prefix = [str(item) for item in root_path]
        related_ids = {
            edge.target
            for edge in context.edges
            if edge.source == root.id and edge.type in _CHILD_EDGE_TYPES
        }
        scoped = [root]
        for node in context.nodes:
            if node.id == root.id:
                continue
            node_path = node.metadata.get("path") or node.metadata.get("path_array")
            normalized = [str(item) for item in node_path] if isinstance(node_path, list) else []
            if normalized[: len(prefix)] == prefix or (not normalized and node.id in related_ids):
                scoped.append(node)
        return scoped

    nodes_by_id = {node.id: node for node in context.nodes}
    children_by_source: dict[str, list[str]] = defaultdict(list)
    for edge in context.edges:
        if edge.type in _CHILD_EDGE_TYPES:
            children_by_source[edge.source].append(edge.target)

    visited: set[str] = set()
    ordered: list[BubbleContextNode] = []
    queue: deque[str] = deque([root.id])
    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        ordered.append(node)
        queue.extend(children_by_source.get(node_id, []))
    return ordered


def _node_to_dict(node: BubbleContextNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "label": node.label,
        "type": node.type,
        "metadata": dict(node.metadata),
    }


def inventory_source_object(
    *,
    context: BubbleProjectContext,
    profile: str,
    app_version: str,
    source_type: str,
    source_ref: str,
    source_context: str | None = None,
) -> TransferInventory:
    """Build a serializable read-only transfer inventory for one source object."""

    if source_type not in {"page", "reusable", "element"}:
        raise ValueError("source_type must be one of: page, reusable, element.")
    root = _resolve_source_node(
        context,
        source_type=source_type,  # type: ignore[arg-type]
        source_ref=source_ref,
        source_context=source_context,
    )
    nodes = _subtree_nodes(context, root)
    return TransferInventory(
        source=TransferObjectRef(
            profile=profile,
            app_id=context.app_id,
            app_version=app_version,
            source_type=source_type,  # type: ignore[arg-type]
            ref=source_ref,
            context=source_context,
            bubble_id=str(root.metadata.get("bubble_id") or "").strip() or None,
            path=[str(item) for item in root.metadata.get("path", [])]
            if isinstance(root.metadata.get("path"), list)
            else [],
        ),
        root=_node_to_dict(root),
        nodes=[_node_to_dict(node) for node in nodes],
        dependencies=extract_node_dependencies(nodes),
    )
