"""Models for local tool-authoring sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolAuthoringSession:
    """A local candidate tool-authoring session grouped from captured writes."""

    id: str
    intent: str
    target: str
    profile: str
    created_at: str
    capture_files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolAuthoringSession":
        capture_files = payload.get("capture_files")
        return cls(
            id=str(payload.get("id") or ""),
            intent=str(payload.get("intent") or ""),
            target=str(payload.get("target") or ""),
            profile=str(payload.get("profile") or ""),
            created_at=str(payload.get("created_at") or ""),
            capture_files=[str(item) for item in capture_files] if isinstance(capture_files, list) else [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "intent": self.intent,
            "target": self.target,
            "profile": self.profile,
            "created_at": self.created_at,
            "capture_files": self.capture_files,
        }
