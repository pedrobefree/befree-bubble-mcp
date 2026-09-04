"""The one Data API read this server needs: turning something human into a Bubble unique id.

``bubble_run_as`` wants ``1700000000000x000000000000000001``; a person has an email. Closing
that gap needs the app's Data API, which needs a token, and a project that already does all of
this exists - ``bubble-cli`` mirrors a Bubble app into SQLite over the Data API and exposes
``query(sql)`` over MCP. For exploring data, that is the better tool and this module is not a
replacement for it.

What this is, is the single lookup that would otherwise force a two-server round trip in the
middle of one impersonation. It is deliberately small:

* No new HTTP stack. ``bubble-cli`` uses httpx; this server already carries ``requests`` and
  urllib, and a third client in one process is a cost with nothing to show for it here.
* No retry/backoff/pagination. Those exist in ``bubble-cli`` because mirroring a whole table
  needs them. One constrained lookup returns one page or nothing.
* **No token store of its own.** A key comes from ``BUBBLE_DATA_API_TOKEN`` in the
  environment, or from a ``bubble.json`` - the format ``bubble-cli`` already writes and
  manages, so anyone using both tools registers a key once rather than twice. Nothing here
  ever writes a key, and nothing ever returns or logs one. This server does not require
  ``bubble-cli`` to be installed: the environment variable stands on its own.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

CONFIG_FILENAME = "bubble.json"

TOKEN_ENV = "BUBBLE_DATA_API_TOKEN"
TOKEN_APP_ENV = "BUBBLE_DATA_API_APP"
TOKEN_VERSION_ENV = "BUBBLE_DATA_API_VERSION"

PROJECT_DIR_ENV = "BUBBLE_CLI_PROJECT_DIR"
ROOT_ENV = "BUBBLE_CLI_ROOT"

# How deep to look for a bubble.json under a search root. The CLI's projects sit one folder
# down in practice; going deeper turns a miss into a filesystem crawl.
MAX_SEARCH_DEPTH = 3

DEFAULT_TIMEOUT_SEC = 30


class DataApiError(Exception):
    """A Data API call that cannot be interpreted as a result."""


@dataclass(frozen=True)
class DataApiConfig:
    """A bubble-cli project's connection details. ``api_key`` never leaves this object."""

    app_id: str
    api_key: str
    version: str = "live"
    source_path: Path | None = None

    @property
    def base_url(self) -> str:
        # bubble-cli's own rule: "live" has no version segment, anything else is version-test.
        # Kept identical on purpose - two tools disagreeing about which version they read would
        # be a confusing bug to chase.
        segment = "" if self.version == "live" else "/version-test"
        return f"https://{self.app_id}.bubbleapps.io{segment}/api/1.1"

    def describe(self) -> dict[str, Any]:
        """Safe to log: says where the config came from, never what is in it."""

        return {
            "app_id": self.app_id,
            "version": self.version,
            "source_path": str(self.source_path) if self.source_path else None,
        }


def _read_config(path: Path) -> DataApiConfig | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    app_id = str(data.get("app_id") or "").strip()
    api_key = str(data.get("api_key") or "").strip()
    if not app_id or not api_key:
        return None
    return DataApiConfig(
        app_id=app_id,
        api_key=api_key,
        version=str(data.get("version") or "live").strip() or "live",
        source_path=path,
    )


def _search_roots(extra: Path | None) -> list[Path]:
    roots: list[Path] = []
    if extra:
        roots.append(extra)
    configured = os.environ.get(PROJECT_DIR_ENV, "").strip()
    if configured:
        roots.append(Path(configured).expanduser())
    for entry in os.environ.get(ROOT_ENV, "").split(os.pathsep):
        cleaned = entry.strip()
        if cleaned:
            roots.append(Path(cleaned).expanduser())
    return roots


def _config_from_environment(app_id: str) -> DataApiConfig | None:
    """A Data API token straight from the environment, for anyone with no bubble-cli project.

    This is checked FIRST so that this server never requires another tool to be installed to
    resolve an email. ``BUBBLE_DATA_API_APP`` may be omitted when the token is meant for
    whatever app is being addressed, which is the single-app case most people are in.
    """

    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        return None
    scoped_app = os.environ.get(TOKEN_APP_ENV, "").strip()
    if scoped_app and scoped_app != app_id:
        return None
    return DataApiConfig(
        app_id=app_id,
        api_key=token,
        version=os.environ.get(TOKEN_VERSION_ENV, "").strip() or "live",
        source_path=None,
    )


def find_data_api_config(app_id: str, *, folder: Path | None = None) -> DataApiConfig | None:
    """Locate the ``bubble.json`` that belongs to ``app_id``.

    A folder is checked directly; a search root is walked shallowly for any ``bubble.json``
    whose ``app_id`` matches. Matching on the app rather than taking the first file found is
    what keeps a machine with several mirrored apps from reading the wrong one - the failure
    that would produce is a lookup silently answering about a different app.
    """

    wanted = str(app_id or "").strip()
    if not wanted:
        return None

    from_env = _config_from_environment(wanted)
    if from_env is not None:
        return from_env

    for root in _search_roots(folder):
        if not root.exists():
            continue
        direct = _read_config(root / CONFIG_FILENAME)
        if direct and direct.app_id == wanted:
            return direct
        for depth in range(1, MAX_SEARCH_DEPTH + 1):
            for candidate in root.glob("/".join(["*"] * depth) + f"/{CONFIG_FILENAME}"):
                found = _read_config(candidate)
                if found and found.app_id == wanted:
                    return found
    return None


Fetch = Callable[[str, dict[str, str]], str]


def _urllib_fetch(url: str, headers: dict[str, str]) -> str:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SEC) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise DataApiError(f"Data API answered {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise DataApiError(f"Data API unreachable: {exc.reason}") from exc


def find_records(
    config: DataApiConfig,
    type_name: str,
    constraints: list[dict[str, Any]],
    *,
    limit: int = 5,
    fetch: Fetch = _urllib_fetch,
) -> list[dict[str, Any]]:
    """Return matching rows of ``type_name``, newest Bubble semantics aside.

    An empty list is a real answer, not an error: the Data API applies the app's privacy rules,
    so a row the token may not see is indistinguishable from a row that does not exist. The
    caller has to say so rather than claim the record is missing.
    """

    query = quote(json.dumps(constraints), safe="")
    url = f"{config.base_url}/obj/{quote(str(type_name).lower(), safe='')}?constraints={query}&limit={int(limit)}"
    raw = fetch(url, {"authorization": f"Bearer {config.api_key}"})
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise DataApiError("Data API returned a body that is not JSON.") from exc
    results = (payload.get("response") or {}).get("results")
    return [row for row in results if isinstance(row, dict)] if isinstance(results, list) else []


def find_user_id(
    config: DataApiConfig,
    email: str,
    *,
    fetch: Fetch = _urllib_fetch,
) -> dict[str, Any]:
    """Resolve one app user's Bubble unique id from their email.

    Returns a result dictionary rather than a bare id because every failure here has a
    different fix, and a caller that only got ``None`` would have to guess which.
    """

    wanted = str(email or "").strip()
    if not wanted:
        return {"ok": False, "error": "missing_email", "message": "Pass the user's email."}

    try:
        rows = find_records(
            config,
            "user",
            [{"key": "email", "constraint_type": "equals", "value": wanted}],
            fetch=fetch,
        )
    except DataApiError as exc:
        return {
            "ok": False,
            "error": "data_api_failed",
            "message": (
                f"{exc} Check that the Data API is on for the app (project setting "
                "'api-data-enabled'), that the User type is exposed "
                "(set_data_type_api_exposure), and that the token in "
                f"{config.source_path} is current."
            ),
        }

    if not rows:
        return {
            "ok": False,
            "error": "user_not_found",
            "message": (
                f"No User row with email {wanted!r} in app '{config.app_id}' "
                f"(version '{config.version}'). The Data API applies privacy rules, so a row "
                "this token cannot see looks exactly like a row that does not exist."
            ),
        }
    if len(rows) > 1:
        return {
            "ok": False,
            "error": "ambiguous_email",
            "message": f"{len(rows)} User rows share the email {wanted!r}; pass a user_id instead.",
        }

    user_id = str(rows[0].get("_id") or "").strip()
    if not user_id:
        return {
            "ok": False,
            "error": "no_id_in_row",
            "message": "The matching User row carried no _id, so there is nothing to impersonate.",
        }
    return {"ok": True, "user_id": user_id, "app_id": config.app_id, "version": config.version}
