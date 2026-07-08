"""Typed models for the dynamic Bubble MCP language registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


DetailLevel = Literal["index", "compact", "full"]
ToolSource = Literal["native", "extension"]
RiskLevel = Literal["read_only", "mutating", "destructive"]


@dataclass(frozen=True)
class LanguageToolEntry:
    name: str
    family: str
    source: ToolSource
    description: str
    risk: RiskLevel
    read_only: bool
    destructive: bool
    required: tuple[str, ...]
    properties: tuple[str, ...]
    coverage: str | None = None
    extension_id: str | None = None
    schema_hash: str | None = None

    def to_index(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "family": self.family,
            "source": self.source,
            "risk": self.risk,
            "read_only": self.read_only,
            "destructive": self.destructive,
        }
        if self.coverage:
            payload["coverage"] = self.coverage
        if self.extension_id:
            payload["extension_id"] = self.extension_id
        return payload

    def to_compact(self) -> dict[str, Any]:
        return {
            **self.to_index(),
            "description": self.description,
            "required": list(self.required),
            "properties": list(self.properties),
            "schema_hash": self.schema_hash,
        }
