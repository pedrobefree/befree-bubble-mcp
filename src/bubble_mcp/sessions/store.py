"""Volatile local session store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bubble_mcp.core.redaction import redact_sensitive


@dataclass(frozen=True)
class BubbleSessionData:
    app_id: str
    headers: dict[str, str]
    captured_at: str
    source: str

    def metadata(self) -> dict[str, str]:
        return {
            "app_id": self.app_id,
            "captured_at": self.captured_at,
            "source": self.source,
        }


class VolatileSessionStore:
    """Process-local session store. This intentionally does not persist secrets."""

    def __init__(self) -> None:
        self._sessions: dict[str, BubbleSessionData] = {}

    def set_session(self, app_id: str, headers: dict[str, str], source: str = "manual") -> BubbleSessionData:
        session = BubbleSessionData(
            app_id=app_id,
            headers=headers,
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
