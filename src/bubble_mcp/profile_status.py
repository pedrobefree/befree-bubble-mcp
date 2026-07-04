"""Read-only readiness status for configured Bubble MCP profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bubble_mcp.context.detector import default_context_path
from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.core.config import BubbleProfile, get_settings_path, load_settings, resolve_profile
from bubble_mcp.sessions.store import load_session, session_path


def _resolve_profile_path(profile: BubbleProfile, raw_path: str | None, settings_dir: Path) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return settings_dir / path


def _path_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"configured": False, "exists": False, "path": None}
    return {"configured": True, "exists": path.exists(), "path": str(path)}


def _context_path_for_profile(profile: BubbleProfile, settings_dir: Path) -> tuple[Path | None, Path | None]:
    source_artifact = _resolve_profile_path(profile, profile.app_json_path, settings_dir)
    if source_artifact is None:
        return None, None
    if source_artifact.suffix.lower() == ".bubble":
        return source_artifact, default_context_path(profile.name, profile.app_id)
    return source_artifact, source_artifact


def _context_status(profile: BubbleProfile, *, settings_dir: Path, max_age_hours: int) -> dict[str, Any]:
    source_artifact, context_path = _context_path_for_profile(profile, settings_dir)
    status = _path_status(context_path)
    if context_path is None or not context_path.exists():
        return {
            **status,
            "source_artifact": _path_status(source_artifact),
            "loadable": False,
            "app_id_matches_profile": False,
            "summary": None,
            "freshness": {
                "status": "missing",
                "stale": True,
                "max_age_hours": max_age_hours,
            },
        }
    try:
        context = load_context_with_overlay(context_path, profile=profile.name, app_id=profile.app_id)
    except Exception as exc:
        return {
            **status,
            "source_artifact": _path_status(source_artifact),
            "loadable": False,
            "app_id_matches_profile": False,
            "summary": None,
            "freshness": {
                "status": "invalid",
                "stale": True,
                "max_age_hours": max_age_hours,
            },
            "error": str(exc),
        }
    return {
        **status,
        "source_artifact": _path_status(source_artifact),
        "loadable": True,
        "app_id_matches_profile": context.app_id == profile.app_id,
        "summary": context.summary(),
        "freshness": context_freshness(context, path=context_path, max_age_hours=max_age_hours),
    }


def _session_status(profile: BubbleProfile, *, settings_dir: Path) -> dict[str, Any]:
    path = session_path(profile.name, settings_dir)
    try:
        session = load_session(profile.name, settings_dir)
    except Exception as exc:
        return {
            "exists": path.exists(),
            "path": str(path),
            "metadata": None,
            "app_id_matches_profile": False,
            "error": str(exc),
        }
    if not session:
        return {"exists": False, "path": str(path), "metadata": None, "app_id_matches_profile": False}
    metadata = session.metadata()
    return {
        "exists": True,
        "path": str(path),
        "metadata": metadata,
        "app_id_matches_profile": session.app_id == profile.app_id,
        "app_version_matches_profile": bool(
            not profile.app_version or not session.app_version or session.app_version == profile.app_version
        ),
    }


def _next_actions(*, profile: BubbleProfile | None, session: dict[str, Any] | None, context: dict[str, Any] | None) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if profile is None:
        actions.append(
            {
                "tool": "bubble_profile_list",
                "reason": "Profile was not found. List profiles or create one with `bubble-mcp profile add`.",
            }
        )
        return actions
    if not session or not session.get("exists"):
        actions.append(
            {
                "tool": "bubble_session_login",
                "args": {"profile": profile.name, "app_id": profile.app_id, "wait_seconds": 180},
                "command": f"bubble-mcp session login --profile {profile.name} --app-id {profile.app_id}",
                "reason": "No captured Bubble editor session exists for this profile. Run interactive session login or import a captured session before real writes.",
            }
        )
    elif not session.get("app_id_matches_profile"):
        actions.append(
            {
                "tool": "bubble_session_login",
                "args": {"profile": profile.name, "app_id": profile.app_id, "wait_seconds": 180},
                "command": f"bubble-mcp session login --profile {profile.name} --app-id {profile.app_id}",
                "reason": "Stored session app_id does not match the configured profile app_id. Capture a new session for this profile.",
            }
        )
    if not context or not context.get("loadable"):
        actions.append(
            {
                "tool": "bubble_context_detect",
                "args": {"profile": profile.name, "app_id": profile.app_id, "force": True},
                "reason": "No loadable compact context is configured. Detect context before resolving pages/elements.",
            }
        )
    elif not context.get("app_id_matches_profile"):
        actions.append(
            {
                "tool": "bubble_context_detect",
                "args": {"profile": profile.name, "app_id": profile.app_id, "force": True},
                "reason": "Loaded context app_id does not match the configured profile app_id. Refresh context for this profile.",
            }
        )
    elif context.get("freshness", {}).get("stale"):
        actions.append(
            {
                "tool": "bubble_context_detect",
                "args": {"profile": profile.name, "app_id": profile.app_id, "force": True},
                "reason": "Context is stale. Refresh before mutations that depend on current pages/elements.",
            }
        )
    return actions


def profile_status(profile_name: str = "", *, max_age_hours: int = 24) -> dict[str, Any]:
    """Return read-only setup/readiness status for one local profile."""

    settings = load_settings()
    profile = resolve_profile(settings, profile_name or None)
    requested = profile_name or settings.default_profile
    settings_path = get_settings_path(settings.config_dir)
    if profile is None:
        return {
            "ok": False,
            "ready": False,
            "requested_profile": requested,
            "profile": None,
            "settings": {"config_dir": str(settings.config_dir), "settings_path": str(settings_path)},
            "session": None,
            "context": None,
            "next_actions": _next_actions(profile=None, session=None, context=None),
        }

    session = _session_status(profile, settings_dir=settings.config_dir)
    context = _context_status(profile, settings_dir=settings.config_dir, max_age_hours=max_age_hours)
    ready = bool(
        session.get("exists")
        and session.get("app_id_matches_profile")
        and context.get("loadable")
        and context.get("app_id_matches_profile")
        and not context.get("freshness", {}).get("stale")
    )
    return {
        "ok": True,
        "ready": ready,
        "requested_profile": requested,
        "profile": {
            "name": profile.name,
            "app_id": profile.app_id,
            "appname": profile.appname,
            "app_version": profile.app_version,
            "editor_url": profile.editor_url,
            "app_json_path": profile.app_json_path,
            "consolelog_json_path": profile.consolelog_json_path,
        },
        "settings": {"config_dir": str(settings.config_dir), "settings_path": str(settings_path)},
        "session": session,
        "context": context,
        "next_actions": _next_actions(profile=profile, session=session, context=context),
    }
