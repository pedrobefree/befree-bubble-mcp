"""Authenticated Bubble editor metadata endpoints."""

from __future__ import annotations

import json
from typing import Any

from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.execution.client import (
    EDITOR_WRITE_TIMEOUT_SEC,
    HttpTransport,
    build_editor_write_headers,
    default_http_transport,
    parse_response_body,
)
from bubble_mcp.sessions.store import BubbleSessionData, load_session


BUBBLE_EDITOR_BASE_URL = "https://bubble.io"


class BubbleEditorApiClient:
    """Posts authenticated non-write Bubble editor API requests."""

    def __init__(
        self,
        *,
        transport: HttpTransport = default_http_transport,
        timeout: float = EDITOR_WRITE_TIMEOUT_SEC,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
        session: BubbleSessionData,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if not endpoint.startswith("/appeditor/"):
            raise ValueError("Bubble editor endpoint must start with /appeditor/.")
        url = f"{BUBBLE_EDITOR_BASE_URL}{endpoint}"
        headers = build_editor_write_headers(session, payload)
        safe_request = {
            "url": url,
            "payload": payload,
            "headers": redact_sensitive(headers),
        }
        if dry_run:
            return {"ok": True, "dry_run": True, "request": safe_request}

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        response = self._transport(url, body, headers, self._timeout)
        data = parse_response_body(response.body)

        if response.status in (401, 403):
            return {
                "ok": False,
                "dry_run": False,
                "status": response.status,
                "error": f"Bubble blocked the editor request ({response.status}).",
                "reason": "auth_blocked",
                "response": data,
                "request": safe_request,
            }
        if isinstance(data, str) and data.lstrip().startswith("<"):
            raise RuntimeError("Bubble session expired: received HTML instead of JSON.")

        return {
            "ok": 200 <= response.status < 300,
            "dry_run": False,
            "status": response.status,
            "response": data,
            "request": safe_request,
        }


def _load_session_for_profile(profile: str) -> BubbleSessionData:
    profile_name = str(profile or "").strip()
    if not profile_name:
        raise ValueError("A Bubble MCP profile is required.")
    session = load_session(profile_name)
    if session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile_name}'.")
    return session


def _resolve_app_id(profile: str, session: BubbleSessionData, app_id: str | None = None) -> str:
    explicit = str(app_id or "").strip()
    if explicit:
        return explicit
    settings = load_settings()
    configured_profile = resolve_profile(settings, profile)
    resolved = str((configured_profile.app_id if configured_profile else "") or session.app_id or "").strip()
    if not resolved:
        raise ValueError("Unable to resolve Bubble app id from arguments, profile, or session.")
    return resolved


def _resolve_app_version(profile: str, session: BubbleSessionData, app_version: str | None = None) -> str:
    explicit = str(app_version or "").strip()
    if explicit:
        return explicit
    settings = load_settings()
    configured_profile = resolve_profile(settings, profile)
    return str((configured_profile.app_version if configured_profile else "") or session.app_version or "test").strip()


def _client(client: BubbleEditorApiClient | None) -> BubbleEditorApiClient:
    return client or BubbleEditorApiClient()


def list_bubble_branches(
    *,
    profile: str,
    app_id: str | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    payload = {"appname": appname}
    result = _client(client).post("/appeditor/get_versions", payload, session)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, **result}


def list_branch_contributors(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    payload = {"appname": appname, "app_version": version}
    result = _client(client).post("/appeditor/fetch_contributors_to_branch", payload, session)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "app_version": version, **result}


def fetch_changelog_entries(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str | None = None,
    start_index: int = 0,
    num_fetch: int = 50,
    filters: dict[str, Any] | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    payload = {
        "appname": appname,
        "app_version": version,
        "start_index": max(0, int(start_index)),
        "num_fetch": min(max(1, int(num_fetch)), 200),
        "filters": filters or {},
    }
    result = _client(client).post("/appeditor/fetch_changelog_entries", payload, session)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "app_version": version, **result}


def create_bubble_branch(
    *,
    profile: str,
    name: str,
    app_id: str | None = None,
    from_app_version: str | None = None,
    description: str = "",
    execute: bool = False,
    version_control_api_version: int = 7,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    branch_name = str(name or "").strip()
    if not branch_name:
        raise ValueError("bubble_branch_create requires a branch name.")
    payload = {
        "appname": appname,
        "from_app_version": str(from_app_version or _resolve_app_version(profile, session)).strip(),
        "app_version": branch_name,
        "description": str(description or ""),
        "version_control_api_version": int(version_control_api_version),
    }
    result = _client(client).post("/appeditor/create_new_app_version", payload, session, dry_run=not execute)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "executed": execute, **result}


def delete_bubble_branch(
    *,
    profile: str,
    app_version: str,
    app_id: str | None = None,
    soft_delete: bool = True,
    execute: bool = False,
    confirm: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    branch_version = str(app_version or "").strip()
    if not branch_version:
        raise ValueError("bubble_branch_delete requires app_version for the branch to delete.")
    if execute and not confirm:
        raise ValueError("bubble_branch_delete requires confirm=true when execute=true.")
    payload = {"appname": appname, "app_version": branch_version, "soft_delete": bool(soft_delete)}
    result = _client(client).post("/appeditor/delete_app_version", payload, session, dry_run=not execute)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "executed": execute, **result}
