"""Normalized knowledge record models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


@dataclass(frozen=True)
class KnowledgeRecord:
    """One local, source-attributed Bubble knowledge record."""

    id: str
    source: str
    source_url: str
    title: str
    section_path: list[str]
    content: str
    summary: str
    tags: list[str]
    retrieved_at: str
    content_hash: str
    ttl_seconds: int
    license_note: str
    confidence: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeRecord":
        ttl_value = payload.get("ttl_seconds", 0)
        try:
            ttl_seconds = int(ttl_value or 0)
        except (TypeError, ValueError):
            ttl_seconds = 0
        return cls(
            id=str(payload.get("id") or "").strip(),
            source=str(payload.get("source") or "").strip(),
            source_url=str(payload.get("source_url") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            section_path=_string_list(payload.get("section_path")),
            content=str(payload.get("content") or "").strip(),
            summary=str(payload.get("summary") or "").strip(),
            tags=_string_list(payload.get("tags")),
            retrieved_at=str(payload.get("retrieved_at") or "").strip(),
            content_hash=str(payload.get("content_hash") or "").strip(),
            ttl_seconds=ttl_seconds,
            license_note=str(payload.get("license_note") or "").strip(),
            confidence=str(payload.get("confidence") or "local_cached").strip() or "local_cached",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_url": self.source_url,
            "title": self.title,
            "section_path": list(self.section_path),
            "content": self.content,
            "summary": self.summary,
            "tags": list(self.tags),
            "retrieved_at": self.retrieved_at,
            "content_hash": self.content_hash,
            "ttl_seconds": self.ttl_seconds,
            "license_note": self.license_note,
            "confidence": self.confidence,
        }
