"""Bubble version control over HTTP: create a savepoint, list them, restore one.

Payload shapes are pinned to real editor traffic captured 2026-08-27
(docs/capture-version-control-*.json), the same way the clone work was pinned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.execution.client import HttpResponse
from bubble_mcp.execution.editor_api import BubbleEditorApiClient
from bubble_mcp.execution.version_control import (
    create_savepoint,
    list_restore_history,
    restore_to_timestamp,
)
from bubble_mcp.sessions.store import save_session, session_from_payload


def _captured(name: str) -> dict[str, Any]:
    return json.loads(
        Path(f"docs/capture-version-control-{name}.json").read_text(encoding="utf-8")
    )["parsed"]


def _store_profile_and_session(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="dev",
            profiles={
                "dev": BubbleProfile(
                    name="dev",
                    app_id="mcp-test-app",
                    appname="mcp-test-app",
                    app_version="test",
                )
            },
        )
    )
    save_session(
        "dev",
        session_from_payload(
            {
                "appId": "mcp-test-app",
                "appVersion": "test",
                "url": "https://bubble.io/page?id=mcp-test-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "pytest"},
            }
        ),
    )


def _client_with_calls(calls: list[dict[str, Any]]) -> BubbleEditorApiClient:
    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append({"url": url, "payload": json.loads(body.decode("utf-8"))})
        return HttpResponse(status=200, body='{"status":"success"}', headers={})

    return BubbleEditorApiClient(transport=fake_transport)


def test_create_savepoint_posts_the_payload_the_editor_posts(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    create_savepoint(
        profile="dev",
        message="test save point",
        session_id="1787834691376x48",
        execute=True,
        client=_client_with_calls(calls),
    )

    assert calls[0]["url"].endswith("/appeditor/commit_test_version")
    assert calls[0]["payload"] == _captured("commit-test-version")


def test_create_savepoint_previews_without_calling_bubble(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = create_savepoint(
        profile="dev",
        message="test save point",
        execute=False,
        client=_client_with_calls(calls),
    )

    assert calls == []
    assert result["executed"] is False


def test_create_savepoint_refuses_an_empty_message(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)

    try:
        create_savepoint(profile="dev", message="   ", execute=True, client=_client_with_calls([]))
    except ValueError as error:
        assert "message" in str(error)
    else:
        raise AssertionError("a savepoint with no message is unfindable in the restore history")


def test_list_restore_history_posts_the_payload_the_editor_posts(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    list_restore_history(profile="dev", client=_client_with_calls(calls))

    assert calls[0]["url"].endswith("/appeditor/get_restore_history")
    assert calls[0]["payload"] == _captured("get-restore-history")


def test_restore_posts_the_payload_the_editor_posts(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    restore_to_timestamp(
        profile="dev",
        timestamp=1787834752581,
        execute=True,
        confirm=True,
        client=_client_with_calls(calls),
    )

    assert calls[0]["url"].endswith("/appeditor/restore_to")
    assert calls[0]["payload"] == _captured("restore-to")


def test_restore_refuses_to_execute_without_confirmation(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    try:
        restore_to_timestamp(
            profile="dev",
            timestamp=1787834752581,
            execute=True,
            confirm=False,
            client=_client_with_calls(calls),
        )
    except ValueError as error:
        assert "confirm" in str(error)
    else:
        raise AssertionError("reverting the whole version must not happen on execute alone")

    assert calls == []


def test_restore_refuses_a_timestamp_that_is_not_a_positive_instant(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)

    try:
        restore_to_timestamp(
            profile="dev",
            timestamp=0,
            execute=True,
            confirm=True,
            client=_client_with_calls([]),
        )
    except ValueError as error:
        assert "timestamp" in str(error)
    else:
        raise AssertionError("restoring to instant zero would wipe the version")
