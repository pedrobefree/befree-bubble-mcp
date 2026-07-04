"""Extension pack contracts for local Bubble MCP capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


@dataclass(frozen=True)
class ExtensionExports:
    tools: list[str] = field(default_factory=list)
    recipes: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    evals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "ExtensionExports":
        if not isinstance(payload, Mapping):
            return cls()
        return cls(
            tools=_string_list(payload.get("tools", [])),
            recipes=_string_list(payload.get("recipes", [])),
            skills=_string_list(payload.get("skills", [])),
            evals=_string_list(payload.get("evals", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": self.tools,
            "recipes": self.recipes,
            "skills": self.skills,
            "evals": self.evals,
        }


@dataclass(frozen=True)
class ExtensionManifest:
    id: str
    name: str
    version: str
    bubble_mcp_version: str
    capabilities: list[str]
    risk: str
    author: str
    exports: ExtensionExports

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExtensionManifest":
        return cls(
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            version=str(payload.get("version") or "").strip(),
            bubble_mcp_version=str(payload.get("bubbleMcpVersion") or "").strip(),
            capabilities=_string_list(payload.get("capabilities", [])),
            risk=str(payload.get("risk") or "read_only").strip(),
            author=str(payload.get("author") or "").strip(),
            exports=ExtensionExports.from_dict(payload.get("exports", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "bubbleMcpVersion": self.bubble_mcp_version,
            "capabilities": self.capabilities,
            "risk": self.risk,
            "author": self.author,
            "exports": self.exports.to_dict(),
        }


@dataclass(frozen=True)
class InstalledExtension:
    extension_id: str
    state: str
    path: Path
    manifest: ExtensionManifest

    def to_dict(self) -> dict[str, Any]:
        return {
            "extension_id": self.extension_id,
            "state": self.state,
            "path": str(self.path),
            "manifest": self.manifest.to_dict(),
        }


@dataclass(frozen=True)
class ExtensionOperationReport:
    ok: bool
    extension_id: str
    state: str
    path: Path | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "extension_id": self.extension_id,
            "state": self.state,
            "path": str(self.path) if self.path else None,
            "errors": self.errors,
        }
