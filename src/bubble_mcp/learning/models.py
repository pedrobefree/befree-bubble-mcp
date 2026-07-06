"""Models for local consultative learning records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    """Return a UTC ISO timestamp with a trailing Z."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LearningRecord:
    """Append-only consultative learning record."""

    id: str
    scope: str
    key: str
    value: dict[str, Any]
    source: str
    confidence: str
    created_at: str
    profile: str | None = None
    project: str | None = None
    extension_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        scope: str,
        key: str,
        value: dict[str, Any] | None = None,
        source: str,
        confidence: str,
        profile: str | None = None,
        project: str | None = None,
        extension_id: str | None = None,
    ) -> "LearningRecord":
        return cls(
            id=str(uuid4()),
            scope=scope,
            key=key,
            value=value or {},
            source=source,
            confidence=confidence,
            created_at=utc_now_iso(),
            profile=profile,
            project=project,
            extension_id=extension_id,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearningRecord":
        value = payload.get("value")
        return cls(
            id=str(payload.get("id") or ""),
            scope=str(payload.get("scope") or ""),
            key=str(payload.get("key") or ""),
            value=value if isinstance(value, dict) else {},
            source=str(payload.get("source") or ""),
            confidence=str(payload.get("confidence") or ""),
            created_at=str(payload.get("created_at") or ""),
            profile=str(payload.get("profile") or "") or None,
            project=str(payload.get("project") or "") or None,
            extension_id=str(payload.get("extension_id") or "") or None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "scope": self.scope,
            "key": self.key,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }
        if self.profile:
            payload["profile"] = self.profile
        if self.project:
            payload["project"] = self.project
        if self.extension_id:
            payload["extension_id"] = self.extension_id
        return payload
