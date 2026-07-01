"""Local Bubble editor session storage."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.core.redaction import redact_sensitive


@dataclass(frozen=True)
class BubbleSessionData:
    app_id: str
    url: str
    method: str
    headers: dict[str, str]
    cookies: str | None
    app_version: str | None
    captured_at: str
    source: str

    def metadata(self) -> dict[str, str]:
        metadata = {
            "app_id": self.app_id,
            "url": self.url,
            "method": self.method,
            "captured_at": self.captured_at,
            "source": self.source,
        }
        if self.app_version:
            metadata["app_version"] = self.app_version
        return metadata

    def to_dict(self, *, redact: bool = False) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "appId": self.app_id,
            "url": self.url,
            "method": self.method,
            "headers": redact_sensitive(self.headers) if redact else self.headers,
            "cookies": "[REDACTED]" if redact and self.cookies else self.cookies,
            "app_version": self.app_version,
            "appVersion": self.app_version,
            "captured_at": self.captured_at,
            "capturedAt": self.captured_at,
            "source": self.source,
        }


def session_storage_dir(config_dir: Path | None = None) -> Path:
    return (config_dir or get_config_dir()) / "sessions"


def session_path(profile: str, config_dir: Path | None = None) -> Path:
    safe_name = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in profile)
    if not safe_name:
        raise ValueError("Session profile name is required.")
    return session_storage_dir(config_dir) / f"{safe_name}.json"


def session_from_payload(payload: dict[str, Any], *, default_app_id: str | None = None) -> BubbleSessionData:
    app_id = str(payload.get("app_id") or payload.get("appId") or default_app_id or "").strip()
    if not app_id:
        raise ValueError("Session payload is missing app_id/appId.")

    raw_headers = payload.get("headers") or {}
    if not isinstance(raw_headers, dict):
        raise ValueError("Session payload headers must be an object.")
    headers = {str(key): str(value) for key, value in raw_headers.items() if value is not None}

    cookies = str(payload.get("cookies") or headers.get("cookie") or headers.get("Cookie") or "").strip() or None
    if cookies and not any(key.lower() == "cookie" for key in headers):
        headers["cookie"] = cookies

    url = str(payload.get("url") or "https://bubble.io/appeditor/write").strip()
    method = str(payload.get("method") or "POST").strip().upper()
    captured_at = str(payload.get("captured_at") or payload.get("capturedAt") or "").strip()
    if not captured_at:
        captured_at = datetime.now(timezone.utc).isoformat()

    app_version = str(payload.get("app_version") or payload.get("appVersion") or "").strip() or None
    source = str(payload.get("source") or "manual").strip() or "manual"

    return BubbleSessionData(
        app_id=app_id,
        url=url,
        method=method,
        headers=headers,
        cookies=cookies,
        app_version=app_version,
        captured_at=captured_at,
        source=source,
    )


def save_session(profile: str, session: BubbleSessionData, config_dir: Path | None = None) -> Path:
    path = session_path(profile, config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_session(profile: str, config_dir: Path | None = None) -> BubbleSessionData | None:
    path = session_path(profile, config_dir)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected session JSON object in {path}")
    return session_from_payload(payload)


def list_sessions(config_dir: Path | None = None) -> list[dict[str, str]]:
    directory = session_storage_dir(config_dir)
    if not directory.exists():
        return []
    sessions: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.json")):
        session = load_session(path.stem, config_dir)
        if session:
            sessions.append({"profile": path.stem, **session.metadata()})
    return sessions


class VolatileSessionStore:
    """Process-local session store for tests and ephemeral bridge integrations."""

    def __init__(self) -> None:
        self._sessions: dict[str, BubbleSessionData] = {}

    def set_session(
        self,
        app_id: str,
        headers: dict[str, str],
        source: str = "manual",
        *,
        url: str = "https://bubble.io/appeditor/write",
        cookies: str | None = None,
        app_version: str | None = None,
    ) -> BubbleSessionData:
        session = BubbleSessionData(
            app_id=app_id,
            url=url,
            method="POST",
            headers=headers,
            cookies=cookies or headers.get("cookie") or headers.get("Cookie"),
            app_version=app_version,
            captured_at=datetime.now(timezone.utc).isoformat(),
            source=source,
        )
        self._sessions[app_id] = session
        return session

    def get_session(self, app_id: str) -> BubbleSessionData | None:
        return self._sessions.get(app_id)

    def get_metadata(self, app_id: str) -> dict[str, str] | None:
        session = self.get_session(app_id)
        return session.metadata() if session else None

    def safe_debug_snapshot(self) -> dict[str, object]:
        return {
            app_id: {
                "metadata": session.metadata(),
                "headers": redact_sensitive(session.headers),
            }
            for app_id, session in self._sessions.items()
        }


SESSION_STORE = VolatileSessionStore()
