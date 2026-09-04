"""Impersonate a Bubble app user the way the editor's "Run as" button does.

The editor's Run as is not a browser trick: clicking it fires two plain GETs, and everything
that matters happens in their headers.

1. ``GET bubble.io/appeditor/authenticate_as/<app>/<version>/<user_id>/true/<page>`` carrying
   the editor session. It answers ``302``, and the ``Location`` it hands back has a fresh
   ``access_token`` in the query string. The token is minted per call and short-lived.
2. Following that ``Location`` - ``<app>.bubbleapps.io/version-<version>/api/1.1/u/redirect``
   with the token - lands on the requested page and, on the way, sets the app-domain session
   cookies for the impersonated user: ``<app>_<version>_u2main`` and its ``.sig``.

So the whole thing is reproducible without a browser, which is what this module does. That
matters for more than tidiness: driving the editor's UI instead would pin the capability to
Bubble's own markup - the recorded version of this flow depended on ``get_by_text("Run as →")``
and on a per-row element id that is regenerated for every data row, so it could not run twice.

What the caller gets back is a Playwright ``storage_state``: the cookie jar, in the shape
``browser.new_context(storage_state=...)`` accepts. That is what turns one impersonation into
a whole test run - the session is established once, here, and every later page load reuses it
headlessly, with no editor open.

Two constraints worth knowing before relying on this:

* The app-domain cookie carries its own expiry (about a day in practice, but Bubble sets it,
  not us). A stored state outlives this process but not indefinitely.
* A version with preview password protection answers HTTP Basic on the app domain, so step 2
  needs those credentials.

About that password protection, because it decides what to do on a 401: apps on Bubble's
AGENCY plan have it on by default, and any plan's owner may switch it on to keep strangers off
a work-in-progress version. Bubble seeds it with the literal pair ``username`` / ``password``,
and owners frequently leave it that way - it is a wall against passers-by, not a secret. So a
401 here is usually configuration rather than a real credential problem: this module retries
once with those defaults before giving up, and says in the result when that is what worked.
Explicit values, and then the environment, always take precedence over the defaults.
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, urlparse

from bubble_mcp.context.detector import default_bubble_export_path
from bubble_mcp.core.config import get_config_dir
from bubble_mcp.sessions.store import load_session


AUTHENTICATE_AS_URL = "https://bubble.io/appeditor/authenticate_as/{app_id}/{app_version}/{user_id}/true/{page}"

PREVIEW_USER_ENV = "BUBBLE_PREVIEW_USER"
PREVIEW_PASSWORD_ENV = "BUBBLE_PREVIEW_PW"

# What Bubble seeds preview password protection with. Not a secret and not treated as one: it
# is the pair an owner gets before choosing anything, and it is tried only as a last resort,
# after explicit arguments and the environment have both come up empty.
DEFAULT_PREVIEW_CREDENTIALS = ("username", "password")

DEFAULT_TIMEOUT_SEC = 45


@dataclass(frozen=True)
class HttpReply:
    """Just the parts of a response this flow reads."""

    status: int
    location: str = ""
    final_url: str = ""
    body: str = ""


@dataclass
class CookieRecord:
    """One cookie, kept separately from the jar so it can be reported without its value."""

    name: str
    value: str
    domain: str
    path: str = "/"
    expires: float | None = None
    http_only: bool = False
    secure: bool = True

    def redacted(self) -> dict[str, Any]:
        """The cookie WITHOUT its value, for anything that gets shown or logged."""

        return {
            "name": self.name,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
            "http_only": self.http_only,
            "value_length": len(self.value or ""),
        }


class Transport(Protocol):
    """A GET that reports redirects instead of following them, and collects cookies."""

    def get(self, url: str, headers: dict[str, str], *, follow_redirects: bool) -> HttpReply: ...

    @property
    def cookies(self) -> list[CookieRecord]: ...


@dataclass
class UrllibTransport:
    """The real transport: one cookie jar shared by both steps, as a browser would."""

    timeout: int = DEFAULT_TIMEOUT_SEC
    _jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)

    def get(self, url: str, headers: dict[str, str], *, follow_redirects: bool) -> HttpReply:
        handlers: list[Any] = [urllib.request.HTTPCookieProcessor(self._jar)]
        if not follow_redirects:
            handlers.append(_NoRedirect())
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with opener.open(request, timeout=self.timeout) as response:
                return HttpReply(
                    status=int(response.status),
                    location=str(response.headers.get("Location", "") or ""),
                    final_url=str(response.url),
                    body=response.read(4096).decode("utf-8", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            # A 302 with redirects disabled arrives here rather than as a response, and it is
            # the successful case for step 1 - the token lives in this Location header.
            return HttpReply(
                status=int(exc.code),
                location=str(exc.headers.get("Location", "") or ""),
                final_url=str(exc.url or url),
                body=exc.read(4096).decode("utf-8", errors="replace"),
            )

    @property
    def cookies(self) -> list[CookieRecord]:
        return [
            CookieRecord(
                name=cookie.name,
                value=cookie.value or "",
                domain=cookie.domain,
                path=cookie.path or "/",
                expires=float(cookie.expires) if cookie.expires else None,
                secure=bool(cookie.secure),
            )
            for cookie in self._jar
        ]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"authorization": f"Basic {encoded}"}


def preview_credentials_from_export(profile: str, app_id: str) -> tuple[str, str] | None:
    """Read the preview password pair out of the profile's cached ``.bubble`` export.

    Bubble keeps it at ``settings.secure.username`` / ``settings.secure.password``, and the
    export the profile already downloads carries it. That makes the pair discoverable rather
    than something to ask a human for - and unlike the seeded defaults it stays correct for an
    owner who changed it.

    The cache can be stale or absent, so this is a source to try, not a guarantee.
    """

    export = _load_json(default_bubble_export_path(profile, app_id))
    if not isinstance(export, dict):
        return None
    secure = (export.get("settings") or {}).get("secure")
    if not isinstance(secure, dict):
        return None
    user = str(secure.get("username") or "").strip()
    secret = str(secure.get("password") or "").strip()
    return (user, secret) if user and secret else None


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _resolve_preview_credentials(
    username: str | None, password: str | None, profile: str, app_id: str
) -> tuple[tuple[str, str], str] | None:
    """Return the pair to use and where it came from.

    Order matters and is deliberate: what the caller passed beats the environment, the
    environment beats the app's own export, and the seeded defaults are not here at all - they
    are a last resort tried only after a real 401, so a stale export cannot silently mask a
    changed password.
    """

    explicit_user = (username or "").strip()
    explicit_secret = (password or "").strip()
    if explicit_user and explicit_secret:
        return (explicit_user, explicit_secret), "argument"

    env_user = os.environ.get(PREVIEW_USER_ENV, "").strip()
    env_secret = os.environ.get(PREVIEW_PASSWORD_ENV, "").strip()
    if env_user and env_secret:
        return (env_user, env_secret), "environment"

    from_export = preview_credentials_from_export(profile, app_id)
    if from_export:
        return from_export, "app_export"
    return None


def _app_domain(app_id: str) -> str:
    return f"https://{app_id}.bubbleapps.io"


def storage_state_path(profile: str, app_id: str, user_id: str) -> Path:
    """Where an impersonated session is parked.

    Under the MCP's config directory rather than the repository: the file holds live session
    cookies for a real app user, so it must not be somewhere a commit can pick it up.
    """

    safe_user = "".join(char if char.isalnum() else "-" for char in user_id)[:64]
    return get_config_dir() / "run-as" / f"{profile}-{app_id}-{safe_user}.json"


def build_storage_state(cookies: list[CookieRecord]) -> dict[str, Any]:
    """Shape the jar the way ``browser.new_context(storage_state=...)`` expects it."""

    return {
        "cookies": [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires if cookie.expires is not None else -1,
                "httpOnly": cookie.http_only,
                "secure": cookie.secure,
                "sameSite": "Lax",
            }
            for cookie in cookies
        ],
        "origins": [],
    }


def _user_id_from_email(email: str, app_id: str, data_api_dir: str | None) -> dict[str, Any]:
    """Turn an email into a Bubble unique id through the app's Data API.

    Imported lazily so the impersonation path - which needs no Data API at all - does not pay
    for it, and so a machine with no bubble-cli project still uses ``bubble_run_as`` normally
    with an explicit user_id.
    """

    from bubble_mcp.execution.data_api import find_data_api_config, find_user_id

    folder = Path(data_api_dir).expanduser() if data_api_dir else None
    config = find_data_api_config(app_id, folder=folder)
    if config is None:
        return {
            "ok": False,
            "error": "no_data_api_config",
            "message": (
                f"No Data API token available for app '{app_id}', so an email cannot be resolved "
                "to a user id. Either set BUBBLE_DATA_API_TOKEN in this server's environment, or "
                "point data_api_dir at a folder holding a bubble.json with that app's app_id and "
                "api_key (the format the bubble-cli project writes, if you use it). Passing "
                "user_id directly needs no token at all."
            ),
        }
    result = find_user_id(config, email)
    if result.get("ok"):
        result["data_api"] = config.describe()
    return result


def run_as_user(
    profile: str,
    user_id: str = "",
    *,
    email: str | None = None,
    data_api_dir: str | None = None,
    page: str = "index",
    app_id: str | None = None,
    app_version: str = "test",
    preview_username: str | None = None,
    preview_password: str | None = None,
    transport: Transport | None = None,
    write_storage_state: bool = True,
) -> dict[str, Any]:
    """Establish an impersonated app session for ``user_id`` and report where it landed.

    ``user_id`` is the Bubble unique id of the row in the app's User type - the same id the
    editor's Data tab addresses.

    Resolving one from an email is deliberately NOT done here, because it needs the app's Data
    API and a Data API token, and a tool that already does that exists: the ``bubble-cli``
    project mirrors a Bubble app into SQLite over the Data API and exposes it over MCP. There,
    ``bubble(["pull", "--types", "User"])`` fills the mirror and
    ``query("SELECT _id, email FROM User WHERE email = '...'")`` hands back the id this
    function wants - the mirror's ``_id`` primary key IS the Bubble unique id. Duplicating a
    Data API client here would mean a second token to register and a second thing to keep
    correct.

    Cookie VALUES never appear in the returned dictionary. They go to the storage-state file,
    whose path is returned instead, so a result can be logged or shown without leaking a live
    session.
    """

    resolved_user_id = str(user_id or "").strip()
    email_lookup: dict[str, Any] | None = None

    session = load_session(profile)
    if session is None:
        return {
            "ok": False,
            "error": "not_logged_in",
            "message": (
                f"No stored Bubble editor session for profile '{profile}'. "
                "Run bubble_session_login for it and retry."
            ),
        }

    resolved_app_id = (app_id or session.app_id or "").strip()
    if not resolved_app_id:
        return {
            "ok": False,
            "error": "missing_app_id",
            "message": "No app id on the profile or in the call; pass app_id.",
        }

    if not resolved_user_id:
        if not (email or "").strip():
            return {
                "ok": False,
                "error": "missing_user",
                "message": "Pass user_id (a Bubble unique id) or email.",
            }
        email_lookup = _user_id_from_email(str(email), resolved_app_id, data_api_dir)
        if not email_lookup.get("ok"):
            return email_lookup
        resolved_user_id = str(email_lookup["user_id"])

    http = transport if transport is not None else UrllibTransport()

    editor_headers = {
        key: value for key, value in (session.headers or {}).items() if key.lower() != "cookie"
    }
    editor_headers["cookie"] = session.cookies or ""

    auth_url = AUTHENTICATE_AS_URL.format(
        app_id=resolved_app_id, app_version=app_version, user_id=resolved_user_id, page=page
    )
    first = http.get(auth_url, editor_headers, follow_redirects=False)

    token = ""
    if first.location:
        token = (parse_qs(urlparse(first.location).query).get("access_token") or [""])[0]
    if not token:
        return {
            "ok": False,
            "error": "no_access_token",
            "status": first.status,
            "message": (
                "authenticate_as did not answer with a redirect carrying an access_token "
                f"(status {first.status}). An expired editor session answers this way, and so "
                f"does a user_id that does not exist in '{resolved_app_id}'."
            ),
        }

    base_headers = {"user-agent": editor_headers.get("user-agent", "befree-bubble-mcp")}
    resolved = _resolve_preview_credentials(
        preview_username, preview_password, profile, resolved_app_id
    )
    credentials = resolved[0] if resolved else None
    credential_source = resolved[1] if resolved else "none"
    app_headers = dict(base_headers)
    if credentials:
        app_headers.update(_basic_auth_header(*credentials))
    second = http.get(first.location, app_headers, follow_redirects=True)

    used_default_credentials = False
    if second.status == 401 and credentials is None:
        # Agency-plan apps have preview password protection on by default, seeded with this
        # literal pair, and owners routinely leave it. Trying it costs one request and turns
        # the common case from an error the caller has to interpret into a working session.
        # Only when nothing was supplied: a 401 despite real credentials means those are wrong,
        # and quietly succeeding with the defaults would hide that.
        used_default_credentials = True
        second = http.get(
            first.location,
            {**base_headers, **_basic_auth_header(*DEFAULT_PREVIEW_CREDENTIALS)},
            follow_redirects=True,
        )

    if second.status == 401:
        tried = (
            "The Bubble default pair (username/password) was tried and rejected."
            if used_default_credentials
            else "The credentials supplied were rejected."
        )
        return {
            "ok": False,
            "error": "preview_password_required",
            "status": 401,
            "message": (
                f"The app answered 401 for {resolved_app_id}: this version has preview password "
                f"protection, which is on by default for apps on Bubble's agency plan. {tried} "
                f"Set {PREVIEW_USER_ENV} and {PREVIEW_PASSWORD_ENV} in the environment of the "
                "MCP server, or pass them to this call. Ask the app owner for the pair - it "
                "gates the preview version, not the app's own user accounts."
            ),
        }
    if second.status >= 400:
        return {
            "ok": False,
            "error": "impersonation_failed",
            "status": second.status,
            "message": f"Following the Run as redirect answered {second.status}.",
        }

    session_cookies = [
        cookie for cookie in http.cookies if resolved_app_id in cookie.domain
    ]
    if not session_cookies:
        return {
            "ok": False,
            "error": "no_session_cookie",
            "status": second.status,
            "message": (
                "The redirect succeeded but set no cookie on the app domain, so nothing is "
                "impersonated. Without a session cookie a later page load is anonymous."
            ),
        }

    result: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "used_default_preview_credentials": used_default_credentials,
        "preview_credential_source": "bubble_default" if used_default_credentials else credential_source,
        "app_id": resolved_app_id,
        "app_version": app_version,
        "user_id": resolved_user_id,
        "landing_url": second.final_url or f"{_app_domain(resolved_app_id)}/version-{app_version}/{page}",
        "cookies": [cookie.redacted() for cookie in session_cookies],
    }

    if write_storage_state:
        target = storage_state_path(profile, resolved_app_id, resolved_user_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(build_storage_state(session_cookies), indent=2), encoding="utf-8"
        )
        result["storage_state_path"] = str(target)
        result["storage_state_note"] = (
            "This file holds live session cookies for the impersonated user. Pass it to "
            "Playwright as browser.new_context(storage_state=<path>). Keep it out of version "
            "control; it expires when the Bubble cookie does."
        )

    return result
