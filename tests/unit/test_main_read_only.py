"""Main (test and live) is read-only, and a raw write lands on the version it names.

Team server, 2026-09-25: bubble_editor_write was called with "app_version": "93k8b" in the
payload body on a profile whose version was test. The profile default was injected into the
arguments and then written over the body, so the change went to main.
"""

from __future__ import annotations

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.core.versions import (
    MainVersionReadOnlyError,
    editor_url_for_version,
    ensure_branch_version,
    is_main_version,
)
from bubble_mcp.execution.client import BubbleEditorClient, HttpResponse, build_editor_write_headers
from bubble_mcp.server import tools as tools_module
from bubble_mcp.sessions.store import BubbleSessionData, save_session

MAIN_SESSION = BubbleSessionData(
    app_id="kaimia-app",
    url="https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=test",
    method="POST",
    headers={
        "cookie": "sid=secret",
        "referer": "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=test",
        "x-bubble-r": "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=test",
    },
    cookies="sid=secret",
    app_version="test",
    captured_at="2026-09-25T00:00:00+00:00",
    source="test",
)


def _payload(version: str | None) -> dict:
    payload: dict = {
        "appname": "kaimia-app",
        "changes": [
            {
                "intent": {"name": "SetData"},
                "path_array": ["%p3", "bTiEc0", "%el", "bTrZt0", "%p", "%3"],
                "body": "Mark Client as Inactive",
            }
        ],
    }
    if version is not None:
        payload["app_version"] = version
    return payload


@pytest.fixture
def main_profile(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="team",
            profiles={
                "team": BubbleProfile(
                    name="team", app_id="kaimia-app", appname="kaimia-app", app_version="test"
                )
            },
        )
    )
    save_session("team", MAIN_SESSION)
    sent: list[dict] = []

    def fake_write(self, payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        sent.append({"payload": payload, "dry_run": dry_run})
        return {"ok": True, "dry_run": dry_run, "response": {"last_change": "1"}, "request": {"payload": payload}}

    monkeypatch.setattr("bubble_mcp.server.tools.BubbleEditorClient.write", fake_write)
    verified: list[dict] = []

    def fake_verify(profile, changes, *, app_id=None, app_version="test", reader=None):  # type: ignore[no-untyped-def]
        verified.append({"app_version": app_version})
        return {"ok": True, "checked": 1, "verified": True, "divergences": [], "unverified": []}

    monkeypatch.setattr("bubble_mcp.server.tools.verify_changes", fake_verify)
    return {"sent": sent, "verified": verified}


def test_main_versions_are_test_and_live_and_the_empty_default() -> None:
    assert is_main_version("test")
    assert is_main_version("LIVE")
    assert is_main_version("")
    assert is_main_version(None)
    assert not is_main_version("93k8b")
    assert ensure_branch_version("93k8b") == "93k8b"
    with pytest.raises(MainVersionReadOnlyError, match="main"):
        ensure_branch_version("test")


def test_editor_url_is_rebuilt_for_the_target_version() -> None:
    url = "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=test"
    assert editor_url_for_version(url, "93k8b") == (
        "https://bubble.io/page?id=kaimia-app&tab=Design&name=index&version=93k8b"
    )
    assert editor_url_for_version("https://bubble.io/page?id=kaimia-app", "93k8b").endswith("&version=93k8b")
    assert editor_url_for_version("https://bubble.io/appeditor/write", "93k8b") == "https://bubble.io/appeditor/write"


def test_write_headers_point_at_the_target_version_not_the_captured_one() -> None:
    headers = build_editor_write_headers(MAIN_SESSION, {"appname": "kaimia-app", "app_version": "93k8b"})

    assert headers["referer"].endswith("version=93k8b")
    assert headers["x-bubble-r"].endswith("version=93k8b")
    assert "version=test" not in headers["referer"]


def test_client_refuses_to_send_a_write_to_main() -> None:
    calls: list[str] = []

    def transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append(url)
        return HttpResponse(status=200, body='{"last_change": 1}', headers={})

    client = BubbleEditorClient(transport=transport)
    with pytest.raises(MainVersionReadOnlyError):
        client.write(_payload("test"), MAIN_SESSION)
    with pytest.raises(MainVersionReadOnlyError):
        client.write(_payload(None), MAIN_SESSION)  # falls back to the session's version, test
    assert calls == []

    preview = client.write(_payload("test"), MAIN_SESSION, dry_run=True)
    assert preview["ok"] is True and calls == []

    result = client.write(_payload("93k8b"), MAIN_SESSION)
    assert result["ok"] is True
    assert calls == ["https://bubble.io/appeditor/write"]


def test_payload_body_version_is_the_target_on_a_profile_whose_version_is_main(main_profile) -> None:  # type: ignore[no-untyped-def]
    result = tools_module.call_tool(
        "bubble_editor_write", {"profile": "team", "execute": True, "payload": _payload("93k8b")}
    )

    assert result["ok"] is True
    assert main_profile["sent"][0]["payload"]["app_version"] == "93k8b"
    assert result["app_version"] == "93k8b"
    assert result["confirmed_app_version"] == "93k8b"
    assert main_profile["verified"] == [{"app_version": "93k8b"}]


def test_top_level_app_version_targets_the_branch(main_profile) -> None:  # type: ignore[no-untyped-def]
    result = tools_module.call_tool(
        "bubble_editor_write",
        {"profile": "team", "execute": True, "app_version": "93k8b", "payload": _payload(None)},
    )

    assert result["ok"] is True
    assert main_profile["sent"][0]["payload"]["app_version"] == "93k8b"


def test_a_top_level_version_that_disagrees_with_the_body_is_refused(main_profile) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="disagrees"):
        tools_module.call_tool(
            "bubble_editor_write",
            {"profile": "team", "execute": True, "app_version": "93k8b", "payload": _payload("7xq2p")},
        )
    assert main_profile["sent"] == []


def test_a_write_without_a_version_on_a_main_profile_is_refused(main_profile) -> None:  # type: ignore[no-untyped-def]
    result = tools_module.call_tool(
        "bubble_editor_write", {"profile": "team", "execute": True, "payload": _payload(None)}
    )

    assert result["ok"] is False
    assert result["error"] == "main_is_read_only"
    assert result["app_version"] == "test"
    assert main_profile["sent"] == []


def test_a_write_that_names_main_is_refused_whatever_else_it_says(main_profile) -> None:  # type: ignore[no-untyped-def]
    for version in ("test", "live"):
        result = tools_module.call_tool(
            "bubble_editor_write",
            {"profile": "team", "execute": True, "allow_main": True, "payload": _payload(version)},
        )
        assert result["error"] == "main_is_read_only"
    assert main_profile["sent"] == []


def test_a_preview_on_main_still_runs(main_profile) -> None:  # type: ignore[no-untyped-def]
    result = tools_module.call_tool(
        "bubble_editor_write", {"profile": "team", "execute": False, "payload": _payload(None)}
    )

    assert result["ok"] is True
    assert main_profile["sent"][0]["dry_run"] is True


def test_catalog_mutations_on_main_are_refused_before_any_work(main_profile) -> None:  # type: ignore[no-untyped-def]
    result = tools_module.call_tool(
        "delete_event",
        {"profile": "team", "execute": True, "context": "R Gen Client Overview", "event": "bTraB0"},
    )

    assert result["error"] == "main_is_read_only"
    assert "session_savepoint" not in result


def test_a_read_back_that_diverges_fails_the_write_loudly(main_profile, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def diverging_verify(profile, changes, *, app_id=None, app_version="test", reader=None):  # type: ignore[no-untyped-def]
        return {
            "ok": True,
            "verified": False,
            "divergences": [{"path": "%p3.bTiEc0", "divergence": "<root>", "expected": "present", "actual": "absent"}],
            "unverified": [],
        }

    monkeypatch.setattr("bubble_mcp.server.tools.verify_changes", diverging_verify)
    result = tools_module.call_tool(
        "bubble_editor_write", {"profile": "team", "execute": True, "payload": _payload("93k8b")}
    )

    assert result["ok"] is False
    assert result["error"] == "write_not_verified"
    assert result["confirmed_app_version"] is None


def test_a_read_back_that_cannot_run_leaves_the_write_ok_but_unconfirmed(main_profile, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def unverified(profile, changes, *, app_id=None, app_version="test", reader=None):  # type: ignore[no-untyped-def]
        return {"ok": True, "verified": False, "divergences": [], "unverified": [{"error": "playwright_missing"}]}

    monkeypatch.setattr("bubble_mcp.server.tools.verify_changes", unverified)
    result = tools_module.call_tool(
        "bubble_editor_write", {"profile": "team", "execute": True, "payload": _payload("93k8b")}
    )

    assert result["ok"] is True
    assert result["confirmed_app_version"] is None
