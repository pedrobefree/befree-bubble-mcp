"""Profile readiness resolution for Bubble cross-project transfers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bubble_mcp.context.detector import default_context_path
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, load_settings, resolve_profile
from bubble_mcp.sessions.store import editor_write_session_status, load_session


@dataclass(frozen=True)
class ResolvedTransferProfiles:
    source: BubbleProfile
    target: BubbleProfile
    source_context_path: Path | None
    target_context_path: Path | None
    target_has_session: bool
    target_write_ready: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "source": {
                "profile": self.source.name,
                "app_id": self.source.app_id,
                "app_version": self.source.app_version,
                "context_path": str(self.source_context_path) if self.source_context_path else None,
            },
            "target": {
                "profile": self.target.name,
                "app_id": self.target.app_id,
                "app_version": self.target.app_version,
                "context_path": str(self.target_context_path) if self.target_context_path else None,
                "has_session": self.target_has_session,
                "write_ready": self.target_write_ready,
            },
        }


def _candidate_configured_context_path(settings: BubbleMcpSettings, profile: BubbleProfile) -> Path | None:
    configured = str(profile.app_json_path or "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = settings.config_dir / path
    if path.exists() and path.name.endswith("-context.json"):
        return path
    return None


def _profile_context_path(settings: BubbleMcpSettings, profile: BubbleProfile) -> Path | None:
    configured = _candidate_configured_context_path(settings, profile)
    if configured is not None:
        return configured
    candidate = default_context_path(profile.name, profile.app_id)
    return candidate if candidate.exists() else None


def resolve_transfer_profiles(source_profile: str, target_profile: str) -> ResolvedTransferProfiles:
    """Resolve source/target profiles and local readiness signals without exposing secrets."""

    normalized_source = str(source_profile or "").strip()
    normalized_target = str(target_profile or "").strip()
    if not normalized_source:
        raise ValueError("source_profile is required.")
    if not normalized_target:
        raise ValueError("target_profile is required.")
    if normalized_source == normalized_target:
        raise ValueError("source_profile and target_profile must be different for cross-project transfer.")

    settings = load_settings()
    source = resolve_profile(settings, normalized_source)
    target = resolve_profile(settings, normalized_target)
    if source is None:
        raise ValueError(f"source_profile not configured: {normalized_source}")
    if target is None:
        raise ValueError(f"target_profile not configured: {normalized_target}")

    target_session = load_session(target.name)
    target_status = editor_write_session_status(target_session)
    return ResolvedTransferProfiles(
        source=source,
        target=target,
        source_context_path=_profile_context_path(settings, source),
        target_context_path=_profile_context_path(settings, target),
        target_has_session=target_session is not None,
        target_write_ready=bool(target_status.get("write_ready")),
    )
