"""Read a node from the running Bubble editor's own memory.

The raw encoding of Bubble expressions is not derivable from the .bubble export - the export
is the decoded projection and the decoding happens server-side - so the only source of truth
is the tree the editor holds in the page. ``window.appquery`` exposes it, and exposes each node
in BOTH forms: ``raw()`` returns the DECODED form (``type``, ``properties``, ``entries``,
``next``, ``name``, ``element_id``, ...); ``_raw()`` returns the ENCODED form (``%x``, ``%p``,
``%e``, ``%n``, ``%nm``, ``%ei``, ...). This module deliberately reads with ``_raw()``, not
``raw()``: measured against live editor traffic, ``_raw()`` is byte-identical to the body the
editor itself POSTs to ``/appeditor/write`` (see ``docs/session-findings-2026-08-26.md``). That
is exactly the form the write endpoint wants, so the read and the write share one key space with
no translation step in between - not an oversight, the point. Everything here is built so the
page call is one injectable function: tests pass a fake and never open a browser.
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any, Callable, Sequence

from bubble_mcp.core.config import load_settings
from bubble_mcp.sessions.store import load_session


DEFAULT_READ_TIMEOUT_SEC = 90
EDITOR_EVALUATE_MAX_ATTEMPTS = 3
EDITOR_EVALUATE_RETRY_DELAY_SEC = 1
# Observed verbatim on the live editor, both AFTER window.appquery and the pointer-ready gate
# had already passed - the editor page reloads underneath the session (proven by two runs a
# minute apart reporting different run_js bundle hashes), so a single evaluate can land in a
# freshly-initialized context that regressed past both gates:
#   UnexpectedError: Missing Lib!
#       at Lib.or_throw (https://bubble.io/package/run_js/<hash>/xfalse/x30/run.js:50:5782)
#       at appquery.<computed> [as app] (.../run.js:136:134238)
#   Execution context was destroyed, most likely because of a navigation
TRANSIENT_EDITOR_ERROR_MARKERS = (
    "Missing Lib",
    "Execution context was destroyed",
    "NotReadyError",
    "not fully initialized",
    "navigated away",
)
EDITOR_URL_TEMPLATE = "https://bubble.io/page?name=index&id={app_id}&version={app_version}"
# window.appquery is a getter: it exists (typeof === 'function') well before it is usable, and
# calling through it while the editor is still initializing throws "The variable appquery is
# not fully initialized yet". A typeof check races that window and passes too early, so the
# very next page.evaluate throws. The functional probe below calls all the way through to
# .json inside a try/catch, which is both safe (never propagates the getter's exception, so
# wait_for_function keeps polling instead of failing) and only true once the editor is
# actually ready.
APPQUERY_READY_SCRIPT = """
() => {
  try {
    return Boolean(window.appquery && window.appquery.app && window.appquery.app().json);
  } catch (error) {
    return false;
  }
}
"""

Evaluator = Callable[[str], Any]


class PlaywrightMissing(RuntimeError):
    """Raised when the browser extra is not installed."""


class EditorNotReady(RuntimeError):
    """Raised when the editor page never exposes window.appquery."""


class BrowserProfileMissing(RuntimeError):
    """Raised when the profile has no persistent browser profile directory to drive."""


class NotLoggedIn(RuntimeError):
    """Raised when the browser profile exists but never logged in to Bubble.

    Chrome creates the profile directory shell on first launch, so ``exists()`` alone
    (``BrowserProfileMissing``'s check) is true even when no session cookie was ever stored.
    bubble.io then redirects the editor URL to its marketing or login page instead of the
    editor, and the app id disappears from the final URL.
    """


class PointerNotReady(RuntimeError):
    """Raised when a valid pointer's subtree never finishes loading within the timeout.

    The editor's tree loads lazily and per-subtree: window.appquery answering says nothing
    about whether *this* pointer's node has arrived yet. This is distinct from
    ``EditorNotReady`` (the editor itself never came up) and from a ``pointer_not_found``
    result (something was actually read and turned out absent) - here, nothing was ever read
    because the subtree kept throwing NotReadyError until the clock ran out.
    """


class EditorUnstable(RuntimeError):
    """Raised when the editor page kept reinitializing across every retry attempt.

    The editor page reloads underneath the session (proven by two runs a minute apart
    reporting different run_js bundle hashes), so passing both readiness gates once is not
    enough: the page can regress past them before the next evaluate runs. This is raised only
    after the bounded retry loop in ``_playwright_evaluator`` re-satisfied both gates and
    retried the read the configured number of times and every attempt still failed with a
    transient error (see ``is_transient_editor_error``).
    """

    def __init__(self, attempts: int, last_message: str) -> None:
        self.attempts = attempts
        self.last_message = last_message
        super().__init__(
            f"The editor page kept reinitializing across {attempts} attempts and never "
            f"stayed stable long enough to complete the read. Last error: {last_message}"
        )


class WrongApp(RuntimeError):
    """Raised when the tree read out of the editor belongs to a different app than requested.

    Measured on the live editor: the requested app loads first (``appname="mcp-test-app"``,
    ``version="test"``), but the editor page redirects to ``https://bubble.io/`` on a timer -
    by 3 seconds later, ``window.appquery`` there serves Bubble's own internal ``meta`` app
    (``version="live"``) instead. Both readiness gates (``APPQUERY_READY_SCRIPT`` and the
    pointer-ready probe) can be satisfied while the correct app is still loaded, so passing
    them is not proof the read that follows still belongs to that app - the redirect can land
    in the gap. This is why identity is asserted in the exact same evaluation as the node read
    (see ``build_appquery_script``), not by a separate check before or after it: two
    evaluations would still straddle the race the same way the two readiness gates do.
    """

    def __init__(
        self,
        *,
        expected_app_id: str,
        expected_app_version: str,
        actual_app_id: Any,
        actual_app_version: Any,
    ) -> None:
        self.expected_app_id = expected_app_id
        self.expected_app_version = expected_app_version
        self.actual_app_id = actual_app_id
        self.actual_app_version = actual_app_version
        meta_note = (
            " 'meta' specifically means the editor page navigated away to Bubble's own "
            "dashboard, not to the requested app."
            if actual_app_id == "meta"
            else ""
        )
        super().__init__(
            f"Requested app '{expected_app_id}' version '{expected_app_version}', but the "
            f"editor page had navigated away from it: the tree read back belonged to app "
            f"'{actual_app_id}' version '{actual_app_version}'.{meta_note}"
        )


def _validate_pointer(pointer: Sequence[str]) -> list[str]:
    segments = [str(part) for part in pointer]
    if not segments:
        raise ValueError(
            "pointer must name at least one child: app.raw() on the root is refused by Bubble "
            "'for performance reasons'"
        )
    if any(not part for part in segments):
        raise ValueError("pointer segments must be non-empty")
    return segments


def build_appquery_script(pointer: Sequence[str]) -> str:
    """Return the page script that reads the node at ``pointer`` AND the app it belongs to.

    Both are read in one atomic evaluation, on purpose: the editor page redirects to
    ``https://bubble.io/`` on a timer (measured: the requested app is still served at t=0s,
    but ``window.appquery`` there is already Bubble's own internal ``meta`` app by t=3s), so a
    separate identity check - run before or after this script, in a second ``page.evaluate``
    call - would still leave a window for the redirect to land in between the two calls and
    slip a wrong-app read past it undetected. Folding ``root.appname()`` and
    ``root.app_version()`` into the same expression that produces the node closes that race
    instead of narrowing it.
    """

    segments = _validate_pointer(pointer)
    chain = "".join(f"._child({json.dumps(part)})" for part in segments)
    return (
        "() => { "
        "const root = window.appquery.app().json; "
        f"const node = root{chain}; "
        "return {appname: root.appname(), app_version: root.app_version(), "
        "node: node ? node._raw() : node}; "
        "}"
    )


def build_pointer_ready_script(pointer: Sequence[str], app_id: str) -> str:
    """Return the page script that reports whether the node at ``pointer`` has finished loading.

    The editor's tree loads lazily, so ``window.appquery`` answering says nothing about whether
    this particular subtree has arrived. Only a NotReadyError means "keep waiting": any other
    failure is left for the read itself to report, so a genuinely broken pointer surfaces its
    real error instead of timing out here.

    The script also checks ``root.appname() === app_id`` before walking the pointer at all, and
    reports "not ready" (``false``) when it does not match. Without this, the retry loop would
    happily settle for a subtree that is ready in the WRONG app - the editor's post-load
    redirect to ``https://bubble.io/`` (see ``WrongApp``) makes ``window.appquery`` answer, and
    the ``meta`` app's own tree is perfectly "ready", just for a different app than the one
    asked for. Making the gate app-aware means the wait keeps polling instead of declaring
    victory on the wrong tree.

    Detecting NotReadyError is structural, not textual, because it is measured NOT to be a real
    ``Error`` in the live Bubble editor: ``error.name`` and ``error.message`` are both ``null``,
    ``String(error)`` is ``"[object Object]"``, and ``error instanceof Error`` is ``false``. A
    check against ``.name``/``.message``/``String(error)`` therefore can never match - that was
    the shape of the bug this function fixes, and it is exactly the kind of "obvious"
    simplification someone will be tempted to reintroduce. What the thrown object does carry is
    an own key ``not_ready_key`` (a data field the editor sets deliberately, checked first) and
    ``error.constructor.name === 'NotReadyError'`` (a class name, kept only as the fallback,
    since a future minifier pass is exactly what would rename that).
    """

    segments = _validate_pointer(pointer)
    walk = "\n".join(
        "    node = node._child(%s);\n"
        "    try { if (node && typeof node.ensure_loading === 'function') node.ensure_loading(); } "
        "catch (primeError) {}" % json.dumps(part)
        for part in segments
    )
    return f"""
() => {{
  try {{
    const root = window.appquery.app().json;
    if (root.appname() !== {json.dumps(app_id)}) return false;
    let node = root;
{walk}
    node._raw();
    return true;
  }} catch (error) {{
    // NotReadyError is not an Error instance here: name/message are null and stringifying it
    // yields "[object Object]", so a text match against those can never fire (that was the
    // bug). Detect it structurally: not_ready_key is an own data field the editor sets
    // deliberately (checked first, stable); constructor.name is a class name and only a
    // fallback, since a minifier pass could rename it.
    const isNotReady = Boolean(
      error && typeof error === 'object' && (
        'not_ready_key' in error ||
        (error.constructor && error.constructor.name === 'NotReadyError')
      )
    );
    return !isNotReady;
  }}
}}
"""


def is_transient_editor_error(message: str) -> bool:
    """True when a page evaluation failed because the editor was (re)initializing, not because the read was wrong."""

    lowered = message.lower()
    return any(marker.lower() in lowered for marker in TRANSIENT_EDITOR_ERROR_MARKERS)


def _resolve_app_id(profile: str, app_id: str | None) -> str:
    explicit = str(app_id or "").strip()
    if explicit:
        return explicit
    session = load_session(profile)
    from_session = str(getattr(session, "app_id", "") or "").strip()
    if from_session:
        return from_session
    raise ValueError(f"No app id for profile '{profile}'; pass app_id explicitly.")


def parse_cookie_header(raw: str) -> list[dict[str, str]]:
    """Parse a ``Cookie:`` header string into ``context.add_cookies`` entries.

    Root cause of the wrong-app read this module guards against: ``_playwright_evaluator``
    used to trust whatever cookies the browser-profile directory happened to hold, rather than
    the session ``bubble_session_login`` captured and validated. Measured on this machine, the
    profile directory's own cookies for bubble.io were only ``meta_live_u2main`` and friends -
    partially authenticated for Bubble's own ``meta`` app in ``live``, not for the requested
    app - which is exactly why the editor served a *working* ``meta`` app instead of a login
    page, and why the redirect looked like an editor quirk instead of an auth failure. Seeding
    the context from the stored session's cookies before navigating removes the redirect.

    Splits on ``;``, trims whitespace on both sides of each fragment, and skips any fragment
    with no ``=``. Each fragment is split on the FIRST ``=`` only, because signature cookies
    (e.g. ``meta_live_u2main.sig``) legitimately contain ``=`` inside the value.
    """

    cookies: list[dict[str, str]] = []
    for fragment in (raw or "").split(";"):
        fragment = fragment.strip()
        if not fragment or "=" not in fragment:
            continue
        name, _, value = fragment.partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value, "domain": ".bubble.io", "path": "/"})
    return cookies


def _session_cookie_header(session: Any) -> str:
    """Return the stored session's Cookie header, checked case-insensitively.

    This app's captures happen to spell it ``Cookie``, but nothing guarantees that casing, so
    the header dict is scanned rather than indexed. Falls back to the dedicated ``cookies``
    field ``session_from_payload`` also populates.
    """

    headers = getattr(session, "headers", None) or {}
    for key, value in headers.items():
        if str(key).lower() == "cookie" and value:
            return str(value)
    return str(getattr(session, "cookies", "") or "")


@contextlib.contextmanager
def _open_editor_page(
    *, profile: str, app_id: str, app_version: str, headless: bool, timeout_sec: int
):
    """Launch one persistent browser context for this app/profile and yield its page.

    This is the launch/cookie-seed/navigate/not-logged-in-check sequence every read needs,
    factored out so ``read_live_nodes`` can open it ONCE for a whole batch of pointers instead
    of once per pointer - opening a browser per pointer is what made verifying a write payload
    with a dozen changes far too slow (see ``write_verify.verify_changes``).
    ``PlaywrightMissing``/``BrowserProfileMissing``/``NotLoggedIn`` are raised here because they
    are session-wide setup failures, not per-pointer ones.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # noqa: BLE001 - re-raised as a typed, reportable failure
        raise PlaywrightMissing(
            "Playwright is required to read the live editor. Install with: "
            'python -m pip install "befree-bubble-mcp[browser]" '
            "&& python -m playwright install chromium"
        ) from exc

    settings = load_settings()
    user_data_dir = settings.config_dir / "browser-profiles" / profile
    if not user_data_dir.exists():
        # launch_persistent_context would happily create an empty profile, load a logged-out
        # bubble.io, and only fail 90s later as editor_not_ready. bubble_session_import stores
        # a valid session without ever populating this directory.
        raise BrowserProfileMissing(
            f"No browser profile at {user_data_dir}. The live editor read drives a real "
            f"browser session, which only bubble_session_login creates; run "
            f"bubble_session_login for profile '{profile}' first (an imported session is not "
            "enough)."
        )
    url = EDITOR_URL_TEMPLATE.format(app_id=app_id, app_version=app_version)
    timeout_ms = timeout_sec * 1000
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(user_data_dir), headless=headless)
        try:
            # Seed the context from the stored session rather than trusting whatever cookies
            # the browser-profile directory happens to hold. Root cause of the wrong-app read:
            # a profile directory can be partially authenticated (only for Bubble's own `meta`
            # app in `live`), which lands on a *working* `meta` editor instead of a login page -
            # looking like an editor quirk instead of an auth gap. If there is no session, or it
            # carries no cookies, do not raise here: the not_logged_in / wrong_app checks below
            # already report that, at the right layer, without a second competing message.
            session = load_session(profile)
            if session is not None:
                cookies = parse_cookie_header(_session_cookie_header(session))
                if cookies:
                    context.add_cookies(cookies)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            landed_url = page.url
            if app_id not in landed_url:
                # A logged-in editor load keeps the app id in the URL. A logged-out profile
                # (directory exists, but Chrome never got a session cookie written into it)
                # gets redirected by bubble.io to its marketing page or a /login-ish path
                # instead, and the app id drops out of the URL.
                raise NotLoggedIn(
                    f"Browser profile '{profile}' landed on {landed_url} instead of the "
                    f"editor for app '{app_id}'. The profile directory exists but appears "
                    f"never to have logged in to Bubble; run bubble_session_login for "
                    f"profile '{profile}', then retry."
                )
            yield page
        finally:
            context.close()


def _evaluate_with_retries(
    page: Any,
    *,
    ready_script: str,
    script: str,
    expected_app_id: str,
    expected_app_version: str,
    timeout_sec: int,
) -> Any:
    """Run both readiness gates and one ``evaluate()`` against an ALREADY OPEN page.

    Factored out of the single-pointer evaluator so a whole batch of pointers can share ONE
    open page (``read_live_nodes``) instead of relaunching a browser per pointer. Behaviour is
    unchanged from the original inline loop: the editor page reloads underneath the session
    (proven by two runs a minute apart reporting different run_js bundle hashes), so passing
    both readiness gates once is not proof they still hold by the time ``page.evaluate`` runs -
    the page can regress past them in between. Retry the FULL sequence - both gates, then the
    evaluate - rather than just re-evaluating, because it is the gates that need to be
    re-satisfied against the (possibly new) page context.
    """

    url = EDITOR_URL_TEMPLATE.format(app_id=expected_app_id, app_version=expected_app_version)
    timeout_ms = timeout_sec * 1000
    last_message = ""
    for attempt in range(1, EDITOR_EVALUATE_MAX_ATTEMPTS + 1):
        try:
            try:
                page.wait_for_function(APPQUERY_READY_SCRIPT, timeout=timeout_ms)
            except Exception as exc:  # noqa: BLE001 - Playwright's own timeout type
                raise EditorNotReady(
                    f"window.appquery never appeared on {url} within {timeout_sec}s"
                ) from exc
            try:
                page.wait_for_function(ready_script, timeout=timeout_ms)
            except Exception as exc:  # noqa: BLE001 - Playwright's own timeout type
                raise PointerNotReady(
                    f"pointer subtree never finished loading on {url} within "
                    f"{timeout_sec}s"
                ) from exc
            envelope = page.evaluate(script)
            if isinstance(envelope, dict):
                actual_app_id = envelope.get("appname")
                actual_app_version = envelope.get("app_version")
                if actual_app_id != expected_app_id or actual_app_version != expected_app_version:
                    # Identity is checked here, immediately after the SAME evaluate() call
                    # that produced the node, not by a later, separate check - see WrongApp
                    # and build_appquery_script.
                    raise WrongApp(
                        expected_app_id=expected_app_id,
                        expected_app_version=expected_app_version,
                        actual_app_id=actual_app_id,
                        actual_app_version=actual_app_version,
                    )
            return envelope
        except Exception as exc:  # noqa: BLE001 - classified below, then re-raised
            cause = exc.__cause__
            raw_message = (
                f"{type(cause).__name__}: {cause}"
                if cause is not None
                else f"{type(exc).__name__}: {exc}"
            )
            last_message = raw_message
            if not is_transient_editor_error(raw_message):
                raise
            if attempt < EDITOR_EVALUATE_MAX_ATTEMPTS:
                time.sleep(EDITOR_EVALUATE_RETRY_DELAY_SEC)
                continue
            if isinstance(exc, WrongApp):
                # Exhausted retries specifically on a wrong-app identity mismatch: surface
                # that as the real problem, not as an undifferentiated editor_unstable.
                raise
            raise EditorUnstable(attempt, last_message) from exc


class _LazySession:
    """Opens the editor page on first use and reuses it for every subsequent pointer.

    A setup failure (``PlaywrightMissing``/``BrowserProfileMissing``/``NotLoggedIn``) is
    session-wide: it is raised on the first pointer and re-raised verbatim on every later one,
    so each pointer's ``_run_pointer`` reports the SAME structured error instead of
    ``read_live_nodes`` silently stopping partway through a batch.
    """

    def __init__(
        self, *, profile: str, app_id: str, app_version: str, headless: bool, timeout_sec: int
    ) -> None:
        self._cm = _open_editor_page(
            profile=profile,
            app_id=app_id,
            app_version=app_version,
            headless=headless,
            timeout_sec=timeout_sec,
        )
        self._page: Any = None
        self._opened = False
        self._setup_error: BaseException | None = None

    def _ensure_open(self) -> Any:
        if self._setup_error is not None:
            raise self._setup_error
        if not self._opened:
            self._opened = True
            try:
                self._page = self._cm.__enter__()
            except BaseException as exc:  # noqa: BLE001 - recorded so later pointers see the same failure
                self._setup_error = exc
                raise
        return self._page

    def evaluator_for(
        self, ready_script: str, expected_app_id: str, expected_app_version: str, timeout_sec: int
    ) -> Evaluator:
        def run(script: str) -> Any:
            page = self._ensure_open()
            return _evaluate_with_retries(
                page,
                ready_script=ready_script,
                script=script,
                expected_app_id=expected_app_id,
                expected_app_version=expected_app_version,
                timeout_sec=timeout_sec,
            )

        return run

    def close(self) -> None:
        if self._opened and self._setup_error is None:
            self._cm.__exit__(None, None, None)


def _run_pointer(
    run: Evaluator,
    segments: list[str],
    resolved_app_id: str,
    app_version: str,
    timeout_sec: int,
) -> dict[str, Any]:
    """Evaluate one pointer's script through ``run`` and turn the outcome into a structured result.

    Shared by ``read_live_node`` (one pointer) and ``read_live_nodes`` (many pointers, one open
    page): both funnel through this so every error type is classified identically regardless of
    how many pointers are being read in the same call.
    """

    script = build_appquery_script(segments)
    try:
        envelope = run(script)
    except WrongApp as exc:
        return {"ok": False, "error": "wrong_app", "pointer": segments, "message": str(exc)}
    except PlaywrightMissing as exc:
        return {"ok": False, "error": "playwright_missing", "pointer": segments, "message": str(exc)}
    except EditorNotReady as exc:
        return {"ok": False, "error": "editor_not_ready", "pointer": segments, "message": str(exc)}
    except PointerNotReady as exc:
        return {
            "ok": False,
            "error": "pointer_not_ready",
            "pointer": segments,
            "message": (
                f"Pointer '{'.'.join(segments)}' never finished loading within {timeout_sec}s: "
                f"its subtree kept reporting NotReadyError. {exc}"
            ),
        }
    except BrowserProfileMissing as exc:
        return {
            "ok": False,
            "error": "browser_profile_missing",
            "pointer": segments,
            "message": str(exc),
        }
    except NotLoggedIn as exc:
        return {
            "ok": False,
            "error": "not_logged_in",
            "pointer": segments,
            "message": str(exc),
        }
    except EditorUnstable as exc:
        return {
            "ok": False,
            "error": "editor_unstable",
            "pointer": segments,
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - any browser failure must reach the caller as a result
        return {
            "ok": False,
            "error": "evaluator_failed",
            "pointer": segments,
            "message": f"{type(exc).__name__}: {exc}",
        }

    if isinstance(envelope, dict) and "appname" in envelope:
        # Identity is checked in this same pass over the SAME envelope the node came from -
        # never a separate evaluator round trip - so a redirect that lands between two calls
        # cannot slip a wrong-app read through unnoticed. See WrongApp and
        # build_appquery_script for why a second, later check would not be enough.
        actual_app_id = envelope.get("appname")
        actual_app_version = envelope.get("app_version")
        if actual_app_id != resolved_app_id or actual_app_version != app_version:
            mismatch = WrongApp(
                expected_app_id=resolved_app_id,
                expected_app_version=app_version,
                actual_app_id=actual_app_id,
                actual_app_version=actual_app_version,
            )
            return {"ok": False, "error": "wrong_app", "pointer": segments, "message": str(mismatch)}
        node = envelope.get("node")
    else:
        # Not shaped like the {appname, app_version, node} envelope at all (e.g. a fake
        # evaluator returning some other, malformed value) - fall through to the ordinary
        # shape checks below rather than pretending it carried an identity we never saw.
        node = envelope

    if node is None:
        return {
            "ok": False,
            "error": "pointer_not_found",
            "pointer": segments,
            "message": (
                f"window.appquery returned nothing for pointer '{'.'.join(segments)}'. Check the "
                "pointer against the app tree; a wrong segment reads as an absent node, not as an "
                "error."
            ),
        }
    if not isinstance(node, dict):
        return {
            "ok": False,
            "error": "unexpected_node_shape",
            "pointer": segments,
            "message": f"Expected a node object at '{'.'.join(segments)}', got {type(node).__name__}.",
        }
    return {"ok": True, "pointer": segments, "node": node, "app_id": resolved_app_id}


def read_live_nodes(
    profile: str,
    pointers: Sequence[Sequence[str]],
    *,
    evaluator: Evaluator | None = None,
    app_id: str | None = None,
    app_version: str = "test",
    headless: bool = True,
    timeout_sec: int = DEFAULT_READ_TIMEOUT_SEC,
) -> dict[tuple[str, ...], dict[str, Any]]:
    """Read every pointer in ``pointers`` through ONE persistent browser context.

    ``read_live_node`` opens a browser per call, which is far too slow to verify a write
    payload with a dozen changes (see ``write_verify.verify_changes``). This opens the context
    once - via ``_open_editor_page`` / ``_LazySession`` - and walks every pointer through it
    with ``_evaluate_with_retries``, returning the SAME per-pointer result shape
    ``read_live_node`` already returns, keyed by the pointer tuple. ``read_live_node`` is now
    the one-pointer case of this function.
    """

    resolved_app_id = _resolve_app_id(profile, app_id)
    keys = [tuple(str(part) for part in pointer) for pointer in pointers]
    results: dict[tuple[str, ...], dict[str, Any]] = {}

    if evaluator is not None:
        # A caller-supplied evaluator (every test, and any caller that wants to bypass the
        # real browser) is shared across every pointer as-is: there is no browser session to
        # open once here, so each pointer is simply run through the SAME evaluator instance.
        for key in keys:
            results[key] = _run_pointer(evaluator, list(key), resolved_app_id, app_version, timeout_sec)
        return results

    session = _LazySession(
        profile=profile,
        app_id=resolved_app_id,
        app_version=app_version,
        headless=headless,
        timeout_sec=timeout_sec,
    )
    try:
        for key in keys:
            ready_script = build_pointer_ready_script(list(key), resolved_app_id)
            run = session.evaluator_for(ready_script, resolved_app_id, app_version, timeout_sec)
            results[key] = _run_pointer(run, list(key), resolved_app_id, app_version, timeout_sec)
    finally:
        session.close()
    return results


def read_live_node(
    profile: str,
    pointer: Sequence[str],
    *,
    evaluator: Evaluator | None = None,
    app_id: str | None = None,
    app_version: str = "test",
    headless: bool = True,
    timeout_sec: int = DEFAULT_READ_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Read the node at ``pointer`` from the live editor, as a structured result.

    The one-pointer case of ``read_live_nodes``: reads just this pointer and returns its result
    directly instead of the batch call's keyed mapping.
    """

    segments = [str(part) for part in pointer]
    results = read_live_nodes(
        profile,
        [segments],
        evaluator=evaluator,
        app_id=app_id,
        app_version=app_version,
        headless=headless,
        timeout_sec=timeout_sec,
    )
    return results[tuple(segments)]
