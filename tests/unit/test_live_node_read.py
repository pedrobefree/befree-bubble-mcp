"""Reading a node out of the running editor, with the browser replaced by a fake."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from bubble_mcp.execution.live_node_read import (
    APPQUERY_READY_SCRIPT,
    EditorUnstable,
    NotLoggedIn,
    PointerNotReady,
    WrongApp,
    build_appquery_script,
    build_pointer_ready_script,
    diagnose_stuck_gate,
    editor_urls_for_pointers,
    is_transient_editor_error,
    navigate_editor_page,
    parse_cookie_header,
    read_live_node,
    read_live_nodes,
)


def test_build_appquery_script_chains_one_child_per_pointer_segment() -> None:
    script = build_appquery_script(["api", "wf-1", "actions", "3"])

    assert '._child("api")' in script
    assert '._child("wf-1")' in script
    assert '._child("actions")' in script
    assert '._child("3")' in script
    assert "._raw()" in script


def test_build_appquery_script_requests_appname_and_app_version_alongside_the_node() -> None:
    """Regression pin: identity must be read in the SAME evaluation as the node, to close the

    redirect race (the editor loads the requested app, then redirects to https://bubble.io/ on
    a timer, where window.appquery serves Bubble's own internal `meta` app instead). A separate
    identity check, in a second page.evaluate call, would still straddle that redirect.
    """

    script = build_appquery_script(["api", "wf-1"])

    assert script.count("=>") == 1
    assert "root.appname()" in script
    assert "root.app_version()" in script


def test_build_appquery_script_refuses_an_empty_pointer() -> None:
    with pytest.raises(ValueError, match="at least one child"):
        build_appquery_script([])


def test_build_appquery_script_refuses_an_empty_segment() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_appquery_script(["api", ""])


def test_build_appquery_script_escapes_a_segment_with_a_quote() -> None:
    script = build_appquery_script(['we"ird'])

    assert '._child("we\\"ird")' in script


def test_appquery_ready_script_is_a_functional_probe_not_a_typeof_race() -> None:
    """Regression pin: window.appquery is a getter that exists before it works.

    A bare `typeof window.appquery !== 'undefined'` check passes the instant the getter is
    defined, well before the editor can actually serve `.app().json`, so the very next
    page.evaluate throws "The variable appquery is not fully initialized yet". The probe must
    call all the way through to something usable, inside a try/catch so the getter's exception
    never propagates out of wait_for_function (which would fail the wait instead of polling).
    """

    assert "typeof window.appquery !== 'undefined'" not in APPQUERY_READY_SCRIPT
    assert "try" in APPQUERY_READY_SCRIPT
    assert "catch" in APPQUERY_READY_SCRIPT
    assert "window.appquery" in APPQUERY_READY_SCRIPT


def test_build_pointer_ready_script_chains_one_child_per_segment_and_calls_raw() -> None:
    script = build_pointer_ready_script(["api", "wf-1", "actions", "3"], "mcp-test-app")

    assert '._child("api")' in script
    assert '._child("wf-1")' in script
    assert '._child("actions")' in script
    assert '._child("3")' in script
    assert "node._raw();" in script


def test_build_pointer_ready_script_emits_the_appname_comparison() -> None:
    """Regression pin: the readiness gate must be app-aware, not just tree-aware.

    Otherwise the retry loop happily settles for a subtree that is ready in the WRONG app -
    the editor's post-redirect `meta` app is perfectly "ready", just not the app that was
    asked for.
    """

    script = build_pointer_ready_script(["api"], "mcp-test-app")

    assert "root.appname()" in script
    assert '"mcp-test-app"' in script
    assert "return false" in script


def test_build_pointer_ready_script_primes_the_walk_with_ensure_loading() -> None:
    script = build_pointer_ready_script(["api", "wf-1"], "mcp-test-app")

    # Each segment's walk step both checks for and calls ensure_loading.
    assert script.count("ensure_loading") == 2 * 2


def test_build_pointer_ready_script_returns_false_only_for_not_ready() -> None:
    """Regression pin: any other error must return true, or a broken pointer hangs to timeout."""

    script = build_pointer_ready_script(["api"], "mcp-test-app")

    assert "NotReady" in script
    assert "isNotReady" in script
    assert "return !isNotReady;" in script


def test_build_pointer_ready_script_detects_not_ready_via_not_ready_key() -> None:
    """Regression pin: the live NotReadyError is not an Error - .name/.message are null and

    String(error) is "[object Object]" - but it does carry an own `not_ready_key` field that
    the editor sets deliberately. That must be checked (and checked first, since it is a
    stable data field rather than a class name a minifier could rename).
    """

    script = build_pointer_ready_script(["api"], "mcp-test-app")

    assert "'not_ready_key' in error" in script


def test_build_pointer_ready_script_detects_not_ready_via_constructor_name() -> None:
    """Regression pin: constructor.name === 'NotReadyError' is the fallback check."""

    script = build_pointer_ready_script(["api"], "mcp-test-app")

    assert "error.constructor" in script
    assert "'NotReadyError'" in script


def test_build_pointer_ready_script_does_not_rely_on_name_message_or_string_matching() -> None:
    """Regression pin: the previous version matched error.name/.message/String(error) against

    'NotReady', which can never fire because the live NotReadyError is not an Error instance
    (name and message are null, String(error) is "[object Object]"). Assert the text-matching
    form is entirely absent so this defect cannot come back via a "simplification".
    """

    script = build_pointer_ready_script(["api"], "mcp-test-app")

    assert "error.name" not in script
    assert "error.message" not in script
    assert "String(error" not in script
    assert "indexOf('NotReady')" not in script


def test_build_pointer_ready_script_refuses_an_empty_pointer() -> None:
    with pytest.raises(ValueError, match="at least one child"):
        build_pointer_ready_script([], "mcp-test-app")


def test_build_pointer_ready_script_refuses_an_empty_segment() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_pointer_ready_script(["api", ""], "mcp-test-app")


def test_read_live_node_returns_the_node_the_page_produced() -> None:
    captured: dict[str, Any] = {}

    def fake_evaluator(script: str) -> Any:
        captured["script"] = script
        return {
            "appname": "mcp-test-app",
            "app_version": "test",
            "node": {"id": "act-1", "type": "ChangeThing", "properties": {}},
        }

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=fake_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is True
    assert result["node"]["id"] == "act-1"
    assert result["pointer"] == ["api", "wf-1"]
    assert result["app_id"] == "mcp-test-app"
    assert captured["script"] == build_appquery_script(["api", "wf-1"])


def test_read_live_node_reports_a_mismatched_appname_as_wrong_app() -> None:
    """The editor page redirects to https://bubble.io/ on a timer after loading the requested

    app; the tree then belongs to whatever app window.appquery serves there. A read whose
    envelope names a different app than requested must be refused, not unwrapped.
    """

    def fake_evaluator(_script: str) -> Any:
        return {
            "appname": "some-other-app",
            "app_version": "test",
            "node": {"id": "act-1", "type": "ChangeThing", "properties": {}},
        }

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=fake_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "wrong_app"
    assert result["pointer"] == ["api", "wf-1"]
    assert "mcp-test-app" in result["message"]
    assert "some-other-app" in result["message"]


def test_read_live_node_reports_a_mismatched_app_version_as_wrong_app() -> None:
    def fake_evaluator(_script: str) -> Any:
        return {
            "appname": "mcp-test-app",
            "app_version": "live",
            "node": {"id": "act-1", "type": "ChangeThing", "properties": {}},
        }

    result = read_live_node(
        "mcp-test",
        ["api", "wf-1"],
        evaluator=fake_evaluator,
        app_id="mcp-test-app",
        app_version="test",
    )

    assert result["ok"] is False
    assert result["error"] == "wrong_app"
    assert "test" in result["message"]
    assert "live" in result["message"]


def test_read_live_node_names_meta_as_the_observed_real_world_wrong_app() -> None:
    """Regression pin: measured on the live editor, the app the editor redirects to is

    Bubble's own internal `meta` app in `live` - not a made-up placeholder. This is just the
    mismatch case, but pin the real value so a future reader recognizes it on sight.
    """

    def fake_evaluator(_script: str) -> Any:
        return {
            "appname": "meta",
            "app_version": "live",
            "node": {"id": "act-1", "type": "ChangeThing", "properties": {}},
        }

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=fake_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "wrong_app"
    assert "meta" in result["message"]
    assert "mcp-test-app" in result["message"]


def test_read_live_node_reports_a_pointer_that_did_not_resolve() -> None:
    result = read_live_node(
        "mcp-test", ["api", "nope"], evaluator=lambda _script: None, app_id="mcp-test-app"
    )

    assert result == {
        "ok": False,
        "error": "pointer_not_found",
        "pointer": ["api", "nope"],
        "message": (
            "window.appquery returned nothing for pointer 'api.nope'. Check the pointer against "
            "the app tree; a wrong segment reads as an absent node, not as an error."
        ),
    }


def test_read_live_node_rejects_a_page_value_that_is_not_a_node() -> None:
    result = read_live_node(
        "mcp-test", ["api"], evaluator=lambda _script: "a string", app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "unexpected_node_shape"


def test_read_live_node_reports_an_evaluator_failure_as_a_structured_result() -> None:
    def raising_evaluator(_script: str) -> Any:
        raise RuntimeError("page closed")

    result = read_live_node(
        "mcp-test", ["api", "nope", "x"], evaluator=raising_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "evaluator_failed"
    assert result["pointer"] == ["api", "nope", "x"]
    assert result["message"] == "RuntimeError: page closed"


def test_read_live_node_reports_a_raised_wrong_app_as_a_structured_result() -> None:
    """_playwright_evaluator raises WrongApp directly when the retry loop exhausts every

    attempt still reading the wrong app's identity - this must surface as wrong_app, not get
    folded into the generic evaluator_failed catch-all.
    """

    def raising_evaluator(_script: str) -> Any:
        raise WrongApp(
            expected_app_id="mcp-test-app",
            expected_app_version="test",
            actual_app_id="meta",
            actual_app_version="live",
        )

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=raising_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "wrong_app"
    assert "mcp-test-app" in result["message"]
    assert "meta" in result["message"]


def test_read_live_node_reports_a_logged_out_profile_as_a_structured_result() -> None:
    """A profile directory can exist but never have logged in (Chrome creates the shell on

    first launch). That case must not surface as a bare evaluator_failed or a getter
    exception from https://bubble.io/ - it needs its own actionable error.
    """

    def raising_evaluator(_script: str) -> Any:
        raise NotLoggedIn(
            "Browser profile 'stale' landed on https://bubble.io/ instead of the editor for "
            "app 'mcp-test-app'. The profile directory exists but appears never to have "
            "logged in to Bubble; run bubble_session_login for profile 'stale', then retry."
        )

    result = read_live_node(
        "stale", ["api", "wf-1"], evaluator=raising_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "not_logged_in"
    assert result["pointer"] == ["api", "wf-1"]
    assert "bubble_session_login" in result["message"]
    assert "stale" in result["message"]


def test_read_live_node_reports_a_pointer_that_never_became_ready_as_a_structured_result() -> None:
    """A NotReadyError that never clears is neither editor_not_ready (editor is up) nor

    pointer_not_found (nothing was read) - it needs its own actionable error.
    """

    def raising_evaluator(_script: str) -> Any:
        raise PointerNotReady(
            "pointer subtree never finished loading on https://bubble.io/page?... within 90s"
        )

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=raising_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "pointer_not_ready"
    assert result["pointer"] == ["api", "wf-1"]
    assert "api.wf-1" in result["message"]
    assert "90" in result["message"]


def _fake_playwright(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Install an importable playwright whose launcher fails the test if it is ever called."""

    package = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")

    def _must_not_launch():  # type: ignore[no-untyped-def]
        raise AssertionError("no browser may be launched without a browser profile")

    sync_api.sync_playwright = _must_not_launch  # type: ignore[attr-defined]
    package.sync_api = sync_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_read_live_node_refuses_a_profile_with_no_browser_profile_directory(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """bubble_session_import stores a session without ever creating this directory."""

    _fake_playwright(monkeypatch)
    monkeypatch.setattr(
        "bubble_mcp.execution.live_node_read.load_settings",
        lambda: SimpleNamespace(config_dir=tmp_path),
    )

    result = read_live_node("imported-only", ["api", "wf-1"], app_id="mcp-test-app")

    assert result["ok"] is False
    assert result["error"] == "browser_profile_missing"
    assert "bubble_session_login" in result["message"]
    assert result["pointer"] == ["api", "wf-1"]


def test_read_live_node_gets_past_the_browser_profile_guard_once_it_exists(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _fake_playwright(monkeypatch)
    (tmp_path / "browser-profiles" / "logged-in").mkdir(parents=True)
    monkeypatch.setattr(
        "bubble_mcp.execution.live_node_read.load_settings",
        lambda: SimpleNamespace(config_dir=tmp_path),
    )

    result = read_live_node("logged-in", ["api", "wf-1"], app_id="mcp-test-app")

    # The guard passed, so the launcher was reached and refused: a different, later failure.
    assert result["ok"] is False
    assert result["error"] == "evaluator_failed"


@pytest.mark.parametrize(
    "marker",
    ["Missing Lib", "Execution context was destroyed", "NotReadyError", "not fully initialized"],
)
def test_is_transient_editor_error_matches_each_observed_marker(marker: str) -> None:
    assert is_transient_editor_error(marker) is True


def test_is_transient_editor_error_matches_case_insensitively() -> None:
    assert is_transient_editor_error("MISSING LIB!") is True
    assert is_transient_editor_error("execution context was destroyed") is True
    assert is_transient_editor_error("NOTREADYERROR") is True
    assert is_transient_editor_error("NOT FULLY INITIALIZED") is True


def test_is_transient_editor_error_matches_a_realistic_multiline_stack_trace() -> None:
    """Regression pin: the actual shape observed on the live editor, verbatim."""

    message = (
        "UnexpectedError: Missing Lib!\n"
        "    at Lib.or_throw (https://bubble.io/package/run_js/<hash>/xfalse/x30/run.js:50:5782)\n"
        "    at appquery.<computed> [as app] (.../run.js:136:134238)"
    )

    assert is_transient_editor_error(message) is True

    message = "Execution context was destroyed, most likely because of a navigation"

    assert is_transient_editor_error(message) is True


@pytest.mark.parametrize(
    "message",
    ["TypeError: x is not a function", "", "something unrelated went wrong"],
)
def test_is_transient_editor_error_returns_false_for_ordinary_failures(message: str) -> None:
    assert is_transient_editor_error(message) is False


def test_read_live_node_reports_an_unstable_editor_as_a_structured_result() -> None:
    """Mirrors test_read_live_node_reports_a_pointer_that_never_became_ready_as_a_structured_result:

    when the retry loop in _playwright_evaluator exhausts its attempts because the editor page
    kept reinitializing (transient errors like "Missing Lib" or a destroyed execution context),
    it raises EditorUnstable instead of letting the raw error surface as evaluator_failed.
    """

    def raising_evaluator(_script: str) -> Any:
        raise EditorUnstable(3, "UnexpectedError: Missing Lib!")

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=raising_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "editor_unstable"
    assert result["pointer"] == ["api", "wf-1"]
    assert "kept reinitializing" in result["message"]
    assert "3" in result["message"]


def test_is_transient_editor_error_matches_navigated_away() -> None:
    """A wrong-app identity mismatch is treated as transient for retry purposes, so the

    3-attempt loop gets another chance at the window before giving up.
    """

    assert is_transient_editor_error("WrongApp: ... the editor page had navigated away ...") is True


def test_wrong_app_message_is_classified_as_a_transient_editor_error() -> None:
    """Regression pin: WrongApp's own message text must match the transient marker used to

    retry it, or the retry loop would never give it another chance.
    """

    exc = WrongApp(
        expected_app_id="mcp-test-app",
        expected_app_version="test",
        actual_app_id="meta",
        actual_app_version="live",
    )

    assert is_transient_editor_error(str(exc)) is True


def test_parse_cookie_header_splits_and_trims_multiple_pairs() -> None:
    cookies = parse_cookie_header(" a=1 ; b=2 ")

    assert {"name": "a", "value": "1", "domain": ".bubble.io", "path": "/"} in cookies
    assert {"name": "b", "value": "2", "domain": ".bubble.io", "path": "/"} in cookies
    assert len(cookies) == 2


def test_parse_cookie_header_ignores_a_fragment_without_equals() -> None:
    cookies = parse_cookie_header("a=1; garbage; b=2")

    names = [cookie["name"] for cookie in cookies]
    assert names == ["a", "b"]


def test_parse_cookie_header_splits_on_the_first_equals_only() -> None:
    """Regression pin: signature cookies like `meta_live_u2main.sig` legitimately contain '='

    inside the value, so splitting on every '=' would truncate them.
    """

    cookies = parse_cookie_header("meta_live_u2main.sig=abc=def==")

    assert cookies == [
        {
            "name": "meta_live_u2main.sig",
            "value": "abc=def==",
            "domain": ".bubble.io",
            "path": "/",
        }
    ]


def test_parse_cookie_header_returns_bubble_io_domain_and_root_path() -> None:
    cookies = parse_cookie_header("a=1")

    assert cookies[0]["domain"] == ".bubble.io"
    assert cookies[0]["path"] == "/"


@pytest.mark.parametrize("raw", ["", "   "])
def test_parse_cookie_header_returns_empty_list_for_blank_input(raw: str) -> None:
    assert parse_cookie_header(raw) == []


def test_read_live_nodes_reads_several_pointers_through_a_single_evaluator() -> None:
    """read_live_nodes exists so verifying a dozen-change payload does not open a dozen

    browsers: one evaluator (in the real path, one opened browser context/page) must serve
    every pointer in the batch. Asserting the SAME fake instance is used for every pointer -
    not a fresh one built per pointer - is the observable stand-in for "the browser opened
    once", since a test may never open a real browser.
    """

    calls: list[str] = []

    class FakeEvaluator:
        def __init__(self) -> None:
            self.constructions = 1  # this test builds exactly one instance, see below

        def __call__(self, script: str) -> Any:
            calls.append(script)
            return {
                "appname": "mcp-test-app",
                "app_version": "test",
                "node": {"id": f"node-{len(calls)}", "type": "Thing", "properties": {}},
            }

    fake = FakeEvaluator()  # constructed exactly once for the whole batch

    pointers = [["api", "wf-1", "actions", "0"], ["api", "wf-1", "actions", "1"], ["_index"]]
    results = read_live_nodes(
        "mcp-test", pointers, evaluator=fake, app_id="mcp-test-app", app_version="test"
    )

    assert fake.constructions == 1
    assert len(calls) == 3  # the one fake was used once per pointer, not reconstructed per pointer
    assert set(results.keys()) == {
        ("api", "wf-1", "actions", "0"),
        ("api", "wf-1", "actions", "1"),
        ("_index",),
    }
    for key, expected_script in zip(results, calls):
        assert results[key]["ok"] is True
        assert calls[list(results.keys()).index(key)] == build_appquery_script(list(key))


def test_read_live_nodes_reports_each_pointers_own_outcome() -> None:
    """Different pointers can fail independently within the same batch (e.g. a stale pointer

    next to a valid one); each key gets its own structured result rather than one batch-wide
    verdict.
    """

    def fake_evaluator(script: str) -> Any:
        if "missing" in script:
            return None
        return {
            "appname": "mcp-test-app",
            "app_version": "test",
            "node": {"id": "act-1", "type": "Thing", "properties": {}},
        }

    results = read_live_nodes(
        "mcp-test",
        [["api", "wf-1"], ["api", "missing"]],
        evaluator=fake_evaluator,
        app_id="mcp-test-app",
    )

    assert results[("api", "wf-1")]["ok"] is True
    assert results[("api", "missing")]["ok"] is False
    assert results[("api", "missing")]["error"] == "pointer_not_found"


def test_read_live_node_delegates_to_read_live_nodes_for_one_pointer() -> None:
    """read_live_node is the one-pointer case of read_live_nodes: same result shape, unwrapped."""

    def fake_evaluator(_script: str) -> Any:
        return {
            "appname": "mcp-test-app",
            "app_version": "test",
            "node": {"id": "act-1", "type": "ChangeThing", "properties": {}},
        }

    single = read_live_node("mcp-test", ["api", "wf-1"], evaluator=fake_evaluator, app_id="mcp-test-app")
    batch = read_live_nodes(
        "mcp-test", [["api", "wf-1"]], evaluator=fake_evaluator, app_id="mcp-test-app"
    )

    assert single == batch[("api", "wf-1")]


# --- The editor page a pointer needs open -------------------------------------------------
#
# The module used to hardcode `page?name=index`, which primes the index page and everything
# app-wide and nothing else. A pointer into a reusable (`%ed.<key>`) therefore addressed a
# subtree the editor had never started loading, and the ready gate - correctly - kept waiting
# until the timeout. The page is a function of the pointer; these pin that it is treated as one.


class _FakePage:
    """The two things this module uses a Playwright page for: navigating and evaluating."""

    def __init__(self, *, landed: str | None = None, identity: Any = None) -> None:
        self.gotos: list[str] = []
        self.url = ""
        self._landed = landed
        self._identity = identity

    def goto(self, url: str, **_kwargs: Any) -> None:
        self.gotos.append(url)
        self.url = self._landed if self._landed is not None else url

    def evaluate(self, _script: str) -> Any:
        return self._identity


def test_editor_urls_for_pointers_sends_a_reusable_pointer_to_its_own_reusable_page() -> None:
    urls = editor_urls_for_pointers(
        "mcp-test",
        [("%ed", "bTZyj", "%el", "bTaCn"), ("api", "wf-1")],
        app_id="mcp-test-app",
        app_version="test",
        resolver=lambda profile, app_id, kind, key: "New Client Form",
    )

    assert "type=reusable" in urls[("%ed", "bTZyj", "%el", "bTaCn")]
    assert "name=New%20Client%20Form" in urls[("%ed", "bTZyj", "%el", "bTaCn")]
    assert urls[("api", "wf-1")].endswith("page?name=index&id=mcp-test-app&version=test")


def test_navigate_editor_page_goes_to_the_url_it_was_given() -> None:
    page = _FakePage()

    navigate_editor_page(page, "https://bubble.io/page?type=reusable&name=X&id=a&version=test", app_id="a", timeout_ms=1000)

    assert page.gotos == ["https://bubble.io/page?type=reusable&name=X&id=a&version=test"]


def test_navigate_editor_page_reports_a_logged_out_profile() -> None:
    page = _FakePage(landed="https://bubble.io/login")

    with pytest.raises(NotLoggedIn, match="bubble_session_login"):
        navigate_editor_page(page, "https://bubble.io/page?name=index&id=a&version=test", app_id="a", timeout_ms=1000)


def test_diagnose_stuck_gate_calls_an_expired_session_by_its_name() -> None:
    """Measured on this machine: the editor serves the requested app for ~1s, then the page

    bounces to https://bubble.io/ and window.appquery there answers for Bubble's own `meta`
    app. The bounce is what a logged-out browser profile looks like from inside the editor, and
    it lands AFTER the post-navigation URL check, so the only symptom left was every pointer
    timing out as pointer_not_ready - which reads as a broken pointer, not an expired session.
    """

    page = _FakePage(identity={"url": "https://bubble.io/", "appname": "meta", "app_version": "live"})
    page.url = "https://bubble.io/"

    failure = diagnose_stuck_gate(page, expected_app_id="mcp-test-app", expected_app_version="test")

    assert isinstance(failure, NotLoggedIn)
    assert "bubble_session_login" in str(failure)


def test_diagnose_stuck_gate_reports_a_wrong_app_that_kept_the_app_id_in_the_url() -> None:
    page = _FakePage(identity={"url": "https://bubble.io/page?name=index&id=mcp-test-app&version=live", "appname": "mcp-test-app", "app_version": "live"})
    page.url = "https://bubble.io/page?name=index&id=mcp-test-app&version=live"

    failure = diagnose_stuck_gate(page, expected_app_id="mcp-test-app", expected_app_version="test")

    assert isinstance(failure, WrongApp)


def test_diagnose_stuck_gate_stays_silent_when_the_right_app_is_still_loaded() -> None:
    """Then the gate really was waiting on a lazy subtree, and pointer_not_ready is the truth."""

    page = _FakePage(identity={"url": "https://bubble.io/page?name=index&id=mcp-test-app&version=test", "appname": "mcp-test-app", "app_version": "test"})
    page.url = "https://bubble.io/page?name=index&id=mcp-test-app&version=test"

    assert diagnose_stuck_gate(page, expected_app_id="mcp-test-app", expected_app_version="test") is None


def test_lazy_session_navigates_only_when_the_needed_page_changes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Two pointers into the same reusable share one navigation; the third needs its own.

    Navigating the SAME page is what keeps a batch to one browser - a context per page would
    reopen Chrome and pay the editor's whole boot again for every reusable in the batch.
    """

    import contextlib as _contextlib

    import bubble_mcp.execution.live_node_read as module

    page = _FakePage()

    @_contextlib.contextmanager
    def fake_open(**_kwargs: Any):  # type: ignore[no-untyped-def]
        yield page

    monkeypatch.setattr(module, "_open_editor_page", fake_open)
    session = module._LazySession(
        profile="mcp-test",
        app_id="mcp-test-app",
        app_version="test",
        headless=True,
        timeout_sec=1,
    )
    reusable_url = "https://bubble.io/page?type=reusable&name=R&id=mcp-test-app&tab=elements&version=test"
    index_url = "https://bubble.io/page?name=index&id=mcp-test-app&version=test"

    session.page_at(reusable_url)
    session.page_at(reusable_url)
    session.page_at(index_url)
    session.close()

    assert page.gotos == [reusable_url, index_url]


def test_read_live_nodes_hands_each_pointer_the_editor_page_that_primes_it() -> None:
    """The page is a function of the pointer, and every pointer in a batch may need its own."""

    seen: list[tuple[tuple[str, ...], str]] = []

    class RecordingSession:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def evaluator_for(
            self,
            ready_script: str,
            expected_app_id: str,
            expected_app_version: str,
            timeout_sec: int,
            url: str | None = None,
        ):  # type: ignore[no-untyped-def]
            def run(script: str) -> Any:
                seen.append((tuple(current[0]), str(url)))
                return {
                    "appname": "mcp-test-app",
                    "app_version": "test",
                    "node": {"id": "n", "type": "Thing", "properties": {}},
                }

            return run

        def close(self) -> None:
            pass

    import bubble_mcp.execution.live_node_read as module

    pointers = [["%ed", "r1", "%el", "a"], ["%p3", "p1"], ["api", "wf-1"]]
    current: list[list[str]] = [[]]

    original_run_pointer = module._run_pointer

    def tracking_run_pointer(run, segments, *args, **kwargs):  # type: ignore[no-untyped-def]
        current[0] = segments
        return original_run_pointer(run, segments, *args, **kwargs)

    original_session = module._LazySession
    module._LazySession = RecordingSession  # type: ignore[assignment]
    module._run_pointer = tracking_run_pointer  # type: ignore[assignment]
    try:
        results = read_live_nodes(
            "mcp-test",
            pointers,
            app_id="mcp-test-app",
            app_version="test",
            name_resolver=lambda profile, app_id, kind, key: {"r1": "Reusable One", "p1": "dashboard"}[key],
        )
    finally:
        module._LazySession = original_session  # type: ignore[assignment]
        module._run_pointer = original_run_pointer  # type: ignore[assignment]

    assert all(result["ok"] for result in results.values())
    by_pointer = dict(seen)
    assert "type=reusable" in by_pointer[("%ed", "r1", "%el", "a")]
    assert "name=Reusable%20One" in by_pointer[("%ed", "r1", "%el", "a")]
    assert "name=dashboard" in by_pointer[("%p3", "p1")]
    assert "type=reusable" not in by_pointer[("%p3", "p1")]
    assert "name=index" in by_pointer[("api", "wf-1")]
