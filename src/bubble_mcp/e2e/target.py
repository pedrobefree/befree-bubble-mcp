"""Resolving what a run points at, and whether it can reach it.

Two questions the runner must answer before it opens a browser, both answerable offline and
therefore both testable without Playwright: which URL is this suite about, and is there still
a live impersonated session to load into the context.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bubble_mcp.context.detector import default_bubble_export_path
from bubble_mcp.core.config import BubbleMcpSettings, load_settings, resolve_profile
from bubble_mcp.e2e.suite import E2ESuite
from bubble_mcp.execution.run_as import storage_state_path

BUBBLEAPPS_TEMPLATE = "https://{app_id}.bubbleapps.io"
DEFAULT_CUSTOM_SUBDOMAIN = "app"


@dataclass(frozen=True)
class ResolvedTarget:
    """Where a run points, and how each part of that was decided."""

    profile: str
    app_id: str
    branch: str
    base_url: str
    base_url_origin: str
    branch_origin: str
    warnings: tuple[str, ...] = ()

    def url(self, path: str = "") -> str:
        suffix = str(path or "").strip()
        if not suffix:
            return self.base_url
        return f"{self.base_url}/{suffix.lstrip('/')}"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profile": self.profile,
            "app_id": self.app_id,
            "branch": self.branch,
            "base_url": self.base_url,
            "base_url_origin": self.base_url_origin,
            "branch_origin": self.branch_origin,
        }
        if self.warnings:
            payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class SessionStatus:
    """Whether the impersonated session on disk is usable, and what to do when it is not."""

    ok: bool
    path: Path
    user_id: str
    reason: str = ""
    message: str = ""
    expires_at: str | None = None
    next_action: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "storage_state_path": str(self.path),
            "user_id": self.user_id or None,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.message:
            payload["message"] = self.message
        if self.expires_at:
            payload["expires_at"] = self.expires_at
        if self.next_action:
            payload["next_action"] = self.next_action
        return {key: value for key, value in payload.items() if value is not None}


def playwright_available() -> bool:
    """Playwright is an optional extra, so its absence is a reportable state, not a crash."""

    return importlib.util.find_spec("playwright") is not None


def _client_safe_settings(profile: str, app_id: str) -> dict[str, Any]:
    if not profile or not app_id:
        return {}
    try:
        payload = json.loads(
            default_bubble_export_path(profile, app_id).read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError):
        return {}
    settings = payload.get("settings") if isinstance(payload, dict) else None
    client_safe = settings.get("client_safe") if isinstance(settings, dict) else None
    return client_safe if isinstance(client_safe, dict) else {}


def _domain_from_export(profile: str, app_id: str) -> tuple[str, str, tuple[str, ...]]:
    """Derive an app origin from the local export, saying how sure it is.

    An app with ``redirect_all_to_domain`` serves from its own hostname, and the export records
    the top domain but not the subdomain in front of it. The common Bubble setup is ``app.``,
    so that is the guess - flagged as a guess, because a suite that lands on the wrong host
    fails in a way that looks like a broken app rather than broken configuration.
    """

    client_safe = _client_safe_settings(profile, app_id)
    topdomain = str(client_safe.get("app_topdomain") or "").strip().strip("/")
    redirects = bool(client_safe.get("redirect_all_to_domain"))
    if redirects and topdomain:
        origin = f"https://{DEFAULT_CUSTOM_SUBDOMAIN}.{topdomain}"
        warning = (
            f"The app redirects to its own domain and the export only records the top domain "
            f"{topdomain!r}, so the host was guessed as {origin}. Set 'base_url' in the suite "
            "manifest to pin it."
        )
        return origin, "app_topdomain_guess", (warning,)
    if app_id:
        return BUBBLEAPPS_TEMPLATE.format(app_id=app_id), "bubbleapps", ()
    return "", "unresolved", ()


def resolve_target(
    suite: E2ESuite,
    *,
    branch: str = "",
    settings: BubbleMcpSettings | None = None,
) -> ResolvedTarget:
    """Work out app id, branch and base URL for a run, newest override winning each time."""

    profile = suite.profile
    resolved_settings = settings if settings is not None else load_settings()
    configured = resolve_profile(resolved_settings, profile)

    app_id = suite.app_id or (configured.app_id if configured else "")
    if not app_id:
        raise ValueError(
            f"Suite {suite.name!r} has no app_id and profile {profile!r} resolves to none. "
            "Add 'app_id' to the manifest or register the profile with bubble_project_bootstrap."
        )

    requested_branch = str(branch or "").strip()
    if requested_branch:
        resolved_branch, branch_origin = requested_branch, "call"
    elif suite.branch:
        resolved_branch, branch_origin = suite.branch, "suite"
    elif configured and configured.app_version:
        resolved_branch, branch_origin = configured.app_version, "profile"
    else:
        resolved_branch, branch_origin = "test", "default"

    warnings: tuple[str, ...] = ()
    if suite.base_url:
        origin, base_url_origin = suite.base_url, "suite"
    else:
        origin, base_url_origin, warnings = _domain_from_export(profile, app_id)
    if not origin:
        raise ValueError(
            f"Suite {suite.name!r} has no base_url and none could be derived for app "
            f"{app_id!r}. Add 'base_url' to the manifest."
        )

    return ResolvedTarget(
        profile=profile,
        app_id=app_id,
        branch=resolved_branch,
        base_url=f"{origin.rstrip('/')}/version-{resolved_branch}",
        base_url_origin=base_url_origin,
        branch_origin=branch_origin,
        warnings=warnings,
    )


def _earliest_expiry(cookies: list[Any]) -> float | None:
    stamps = [
        float(cookie["expires"])
        for cookie in cookies
        if isinstance(cookie, dict)
        and isinstance(cookie.get("expires"), int | float)
        and float(cookie["expires"]) > 0
    ]
    return min(stamps) if stamps else None


def check_run_as_session(
    profile: str,
    app_id: str,
    user_id: str,
    *,
    now: datetime | None = None,
) -> SessionStatus:
    """Report whether the run-as storage state is present and still in date.

    Cookie values are never read out of the file into anything this returns - only the path,
    the reason and the expiry stamp travel, so a failed check can be logged safely.
    """

    recapture = {
        "tool": "bubble_run_as",
        "arguments": {"profile": profile, "user_id": user_id},
        "why": "Captures a fresh impersonated session and rewrites the storage state file.",
    }
    if not user_id:
        return SessionStatus(
            ok=False,
            path=Path(),
            user_id="",
            reason="no_user",
            message=(
                "The suite declares no run_as.user_id, so there is no session to load. Add "
                "'run_as': {'user_id': '<bubble user unique id>'} to the manifest."
            ),
            next_action=recapture,
        )

    path = storage_state_path(profile, app_id, user_id)
    if not path.exists():
        return SessionStatus(
            ok=False,
            path=path,
            user_id=user_id,
            reason="missing",
            message=(
                f"No run-as session for user {user_id} of app {app_id} at {path}. "
                "Call bubble_run_as for that profile and user, then run again."
            ),
            next_action=recapture,
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return SessionStatus(
            ok=False,
            path=path,
            user_id=user_id,
            reason="unreadable",
            message=f"The run-as session at {path} could not be read ({error}). Recapture it.",
            next_action=recapture,
        )

    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    if not isinstance(cookies, list) or not cookies:
        return SessionStatus(
            ok=False,
            path=path,
            user_id=user_id,
            reason="empty",
            message=(
                f"The run-as session at {path} holds no cookies, so a page load would be "
                "anonymous. Recapture it with bubble_run_as."
            ),
            next_action=recapture,
        )

    earliest = _earliest_expiry(cookies)
    moment = now or datetime.now(UTC)
    expires_at = (
        datetime.fromtimestamp(earliest, UTC).isoformat().replace("+00:00", "Z")
        if earliest is not None
        else None
    )
    if earliest is not None and earliest <= moment.timestamp():
        return SessionStatus(
            ok=False,
            path=path,
            user_id=user_id,
            reason="expired",
            message=(
                f"The run-as session at {path} expired at {expires_at}. Recapture it with "
                "bubble_run_as before running the suite."
            ),
            expires_at=expires_at,
            next_action=recapture,
        )
    return SessionStatus(ok=True, path=path, user_id=user_id, expires_at=expires_at)
