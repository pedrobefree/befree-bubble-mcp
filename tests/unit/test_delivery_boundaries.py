"""Offline regressions for delivery integration boundaries found in independent review."""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile
from bubble_mcp.e2e.flow import _session_for, run_e2e_flow
from bubble_mcp.e2e.suite import E2ESuite
from bubble_mcp.e2e.target import check_run_as_session, resolve_target
from bubble_mcp.execution.run_as import storage_state_path


def _suite(**kwargs):  # type: ignore[no-untyped-def]
    return E2ESuite(name="boundary", profile="p", app_id="demo", cases=(), base_url="https://demo.bubbleapps.io", **kwargs)


@pytest.mark.parametrize("source", ["call", "suite", "profile"])
def test_live_target_is_refused_from_every_source(source):  # type: ignore[no-untyped-def]
    suite = _suite(branch="live" if source == "suite" else "")
    settings = BubbleMcpSettings(Path(), "p", {"p": BubbleProfile("p", "demo", "demo", app_version="live" if source == "profile" else "test")})
    with pytest.raises(ValueError, match="production"):
        resolve_target(suite, branch="live" if source == "call" else "", settings=settings)


@pytest.mark.parametrize("path", ["../admin", "%2e%2e/admin", "https://demo.bubbleapps.io/admin", "https://demo.bubbleapps.io/version-other/admin", "https://elsewhere.example/version-test/admin", "//elsewhere.example/admin", r"..\admin"])
def test_navigation_cannot_leave_selected_version(path):  # type: ignore[no-untyped-def]
    target = resolve_target(_suite(), settings=BubbleMcpSettings(Path(), None, {}))
    with pytest.raises(ValueError):
        target.url(path)


def test_absolute_url_inside_selected_version_is_allowed():
    target = resolve_target(_suite(), settings=BubbleMcpSettings(Path(), None, {}))
    url = "https://demo.bubbleapps.io/version-test/admin?tab=1"
    assert target.url(url) == url


def test_flow_refuses_unsafe_navigation_before_impersonation(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr("bubble_mcp.e2e.target.load_settings", lambda: BubbleMcpSettings(Path(), "p", {"p": BubbleProfile("p", "demo", "demo")}))
    result = run_e2e_flow(profile="p", steps=[{"goto": "https://demo.bubbleapps.io/admin"}], versions=["test"], user_id="u", base_url="https://demo.bubbleapps.io")
    assert result["ok"] is False


def test_run_as_storage_is_distinct_by_version_and_full_identity():
    assert storage_state_path("p", "demo", "user", app_version="branch-a") != storage_state_path("p", "demo", "user", app_version="branch-b")
    assert storage_state_path("p", "demo", "a/b") != storage_state_path("p", "demo", "a-b")


def test_session_refuses_cookies_for_another_version(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    path = storage_state_path("p", "demo", "u")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cookies": [{"name": "demo_live_u2main", "value": "x"}], "origins": []}))
    status = check_run_as_session("p", "demo", "u")
    assert status.ok is False
    assert status.reason == "version_mismatch"
    assert status.next_action["arguments"]["app_version"] == "test"


def test_flow_session_copy_stays_private(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    path = storage_state_path("p", "demo", "u")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cookies": [{"name": "demo_test_u2main", "value": "x"}], "origins": []}))
    path.chmod(0o600)
    directory = tmp_path / "run"
    directory.mkdir()
    status = _session_for("p", "demo", "test", "u", "", directory, lambda *a, **k: {"ok": True, "user_id": "u", "storage_state_path": str(path)})
    assert status.ok
    assert stat.S_IMODE(status.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_browser_guard_blocks_navigation_and_closes_redirected_pages():
    from types import SimpleNamespace
    from bubble_mcp.e2e.target import install_navigation_guard
    callbacks = {}
    context = SimpleNamespace(route=lambda pattern, cb: callbacks.update(route=cb), on=lambda event, cb: callbacks.update(page=cb))
    target = resolve_target(_suite(), settings=BubbleMcpSettings(Path(), None, {}))
    blocked = install_navigation_guard(context, target)
    calls = []
    request = SimpleNamespace(is_navigation_request=lambda: True, frame=SimpleNamespace(parent_frame=None), url="https://demo.bubbleapps.io/admin")
    route = SimpleNamespace(request=request, abort=lambda: calls.append("abort"), continue_=lambda: calls.append("continue"))
    callbacks["route"](route)
    assert calls == ["abort"]
    request.url = "https://demo.bubbleapps.io/version-test/index"
    callbacks["route"](route)
    assert calls[-1] == "continue"
    frame = SimpleNamespace(url="https://demo.bubbleapps.io/admin")
    page = SimpleNamespace(main_frame=frame, on=lambda event, cb: callbacks.update(navigated=cb), close=lambda: calls.append("close"))
    callbacks["page"](page)
    callbacks["navigated"](frame)
    assert calls[-1] == "close"
    assert len(blocked) == 2
