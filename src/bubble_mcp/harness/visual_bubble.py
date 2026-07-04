"""Bubble-aware visual snapshot capture helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.harness.visual_capture import capture_visual_snapshot


JsonObject = dict[str, Any]


def bubble_preview_version_segment(app_version: str | None) -> str:
    """Return the Bubble public preview URL segment for a branch/version."""

    version = str(app_version or "").strip().strip("/")
    if not version or version.lower() in {"live", "main", "production"}:
        return ""
    if version in {"test", "version-test"}:
        return "version-test"
    if version.startswith("version-"):
        return version
    return f"version-{version}"


def build_bubble_preview_url(
    *,
    app_id: str,
    app_version: str | None = "test",
    page: str = "index",
    public_base_url: str = "",
    query: dict[str, str] | None = None,
) -> str:
    """Build a Bubble app public/preview URL from profile-style fields."""

    app = str(app_id or "").strip()
    if not app and not public_base_url:
        raise ValueError("app_id or public_base_url is required.")
    base = str(public_base_url or "").strip().rstrip("/")
    if not base:
        base = f"https://{app}.bubbleapps.io"
    version_segment = bubble_preview_version_segment(app_version)
    page_segment = str(page or "index").strip().strip("/")
    parts = [base]
    if version_segment:
        parts.append(quote(version_segment, safe="-_"))
    if page_segment and page_segment != "index":
        parts.append(quote(page_segment, safe="/-_"))
    url = "/".join(parts)
    clean_query = {key: value for key, value in (query or {}).items() if key and value}
    if clean_query:
        url = f"{url}?{urlencode(clean_query)}"
    return url


def capture_bubble_visual_snapshot(
    *,
    profile: str = "",
    app_id: str = "",
    app_version: str = "test",
    page: str = "index",
    selector: str = "",
    public_base_url: str = "",
    url: str = "",
    query: dict[str, str] | None = None,
    viewport_width: int = 1365,
    viewport_height: int = 768,
    wait_ms: int = 1000,
    selector_timeout_ms: int = 10000,
    max_nodes: int = 250,
    output: Path | None = None,
) -> JsonObject:
    """Capture the actual rendered Bubble preview/app output as a visual snapshot."""

    settings = load_settings()
    configured_profile = resolve_profile(settings, profile or None) if profile else None
    resolved_app_id = str(app_id or (configured_profile.appname if configured_profile else "")).strip()
    resolved_version = str(
        app_version
        or (configured_profile.app_version if configured_profile and configured_profile.app_version else "")
        or "test"
    ).strip()
    target_url = str(url or "").strip() or build_bubble_preview_url(
        app_id=resolved_app_id,
        app_version=resolved_version,
        page=page,
        public_base_url=public_base_url,
        query=query,
    )
    snapshot = capture_visual_snapshot(
        target_url,
        selector=selector,
        rendered_html=True,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        wait_ms=wait_ms,
        selector_timeout_ms=selector_timeout_ms,
        max_nodes=max_nodes,
        allow_raw_fallback=False,
        output=output,
    )
    snapshot["bubble"] = {
        "profile": configured_profile.name if configured_profile else (profile or None),
        "app_id": resolved_app_id or None,
        "app_version": resolved_version,
        "page": page,
        "url": target_url,
    }
    return snapshot
