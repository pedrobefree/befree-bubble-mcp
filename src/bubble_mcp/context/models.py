"""Typed context models for synthetic and exported Bubble project data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BubbleContextNode:
    id: str
    label: str
    type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BubbleContextEdge:
    source: str
    target: str
    type: str


@dataclass(frozen=True)
class BubbleProjectContext:
    app_id: str
    source: str
    nodes: list[BubbleContextNode]
    edges: list[BubbleContextEdge]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for node in self.nodes:
            counts[node.type] = counts.get(node.type, 0) + 1
        return {
            "app_id": self.app_id,
            "source": self.source,
            "counts": counts,
            "nodes": len(self.nodes),
            "edges": len(self.edges),
        }
