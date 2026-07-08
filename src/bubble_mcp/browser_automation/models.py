"""Data models for browser-assisted deploy scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScheduledDeployPreview:
    preview_id: str
    profile: str
    app_id: str
    app_version: str
    scheduled_at: str
    timezone: str
    message: str
    retry_count: int
    headless: bool
    wait_seconds: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id,
            "profile": self.profile,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "scheduled_at": self.scheduled_at,
            "timezone": self.timezone,
            "message": self.message,
            "retry_count": self.retry_count,
            "headless": self.headless,
            "wait_seconds": self.wait_seconds,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ScheduledDeployRecord:
    deploy_id: str
    profile: str
    app_id: str
    app_version: str
    scheduled_at: str
    timezone: str
    message: str
    retry_count: int
    headless: bool
    wait_seconds: int
    status: str
    created_at: str
    updated_at: str
    preview_id: str | None = None
    executed_at: str | None = None
    cancelled_at: str | None = None
    error: str | None = None
    evidence_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "deploy_id": self.deploy_id,
            "profile": self.profile,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "scheduled_at": self.scheduled_at,
            "timezone": self.timezone,
            "message": self.message,
            "retry_count": self.retry_count,
            "headless": self.headless,
            "wait_seconds": self.wait_seconds,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            **({"preview_id": self.preview_id} if self.preview_id else {}),
            **({"executed_at": self.executed_at} if self.executed_at else {}),
            **({"cancelled_at": self.cancelled_at} if self.cancelled_at else {}),
            **({"error": self.error} if self.error else {}),
            **({"evidence_dir": self.evidence_dir} if self.evidence_dir else {}),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScheduledDeployRecord":
        return cls(
            deploy_id=str(payload.get("deploy_id") or ""),
            profile=str(payload.get("profile") or ""),
            app_id=str(payload.get("app_id") or ""),
            app_version=str(payload.get("app_version") or "test"),
            scheduled_at=str(payload.get("scheduled_at") or ""),
            timezone=str(payload.get("timezone") or ""),
            message=str(payload.get("message") or ""),
            retry_count=int(payload.get("retry_count") or 0),
            headless=bool(payload.get("headless")),
            wait_seconds=int(payload.get("wait_seconds") or 120),
            status=str(payload.get("status") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            preview_id=str(payload.get("preview_id") or "") or None,
            executed_at=str(payload.get("executed_at") or "") or None,
            cancelled_at=str(payload.get("cancelled_at") or "") or None,
            error=str(payload.get("error") or "") or None,
            evidence_dir=str(payload.get("evidence_dir") or "") or None,
        )
