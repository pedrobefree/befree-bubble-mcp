"""Which Bubble app versions are main, and the error raised when a write may not go there.

Bubble names main's editable version ``test`` and the deployed one ``live``; every other version
id is a branch. Whether main takes a write depends on the app (``execution/version_policy.py``):
an app with branches keeps main read-only - one missing or ignored version field once sent an
agent's unreviewed change to the shared main (team server, 2026-09-25) - while an app with only
test and live develops on test. ``live`` is never written.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAIN_VERSIONS = frozenset({"test", "live"})


class MainVersionReadOnlyError(ValueError):
    """Raised before any request is sent when a write targets main."""

    def __init__(self, app_version: str, *, tool: str | None = None, advice: str = "") -> None:
        self.app_version = app_version
        self.tool = tool
        subject = f"{tool} would write" if tool else "This write would go"
        super().__init__(
            f"{subject} to '{app_version}', which is main. "
            + (
                advice
                or "Main is read-only for this MCP here: write to a branch (pass its version id as "
                "app_version, e.g. from bubble_branch_list) and merge it through a reviewed branch merge."
            )
        )


def is_main_version(app_version: str | None) -> bool:
    """True when ``app_version`` names main, including when it is empty (Bubble's default)."""

    return str(app_version or "test").strip().lower() in MAIN_VERSIONS


def ensure_branch_version(app_version: str | None, *, tool: str | None = None) -> str:
    """Return the version when it is a branch, otherwise raise MainVersionReadOnlyError."""

    version = str(app_version or "").strip()
    if is_main_version(version):
        raise MainVersionReadOnlyError(version or "test", tool=tool)
    return version


def editor_url_for_version(url: str, app_version: str) -> str:
    """Point a bubble.io editor URL (``/page?id=...``) at ``app_version``.

    The editor puts the version it is showing in the ``version`` query parameter, and its
    requests carry that URL in ``referer`` and ``x-bubble-r``. A session captured on main would
    otherwise tag every later write with main's URL. Other URLs are returned unchanged.
    """

    version = str(app_version or "").strip()
    if not url or not version:
        return url
    parts = urlsplit(url)
    if not parts.netloc.endswith("bubble.io") or parts.path.rstrip("/") != "/page":
        return url
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "version"]
    query.append(("version", version))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
