import json
from typing import Any

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.execution.client import HttpResponse

from bubble_mcp.execution.editor_api import (
    BubbleEditorApiClient,
    create_bubble_branch,
    delete_bubble_branch,
    fetch_changelog_entries,
    list_branch_contributors,
    list_bubble_branches,
)
from bubble_mcp.sessions.store import save_session, session_from_payload


def _store_profile_and_session(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="dev",
            profiles={
                "dev": BubbleProfile(
                    name="dev",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="test",
                )
            },
        )
    )
    save_session(
        "dev",
        session_from_payload(
            {
                "appId": "synthetic-app",
                "appVersion": "test",
                "url": "https://bubble.io/page?id=synthetic-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "pytest"},
            }
        ),
    )


def _client_with_calls(calls: list[dict[str, Any]]) -> BubbleEditorApiClient:
    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append(
            {
                "url": url,
                "payload": json.loads(body.decode("utf-8")),
                "headers": headers,
                "timeout": timeout,
            }
        )
        return HttpResponse(status=200, body='{"status":"success","items":[]}', headers={})

    return BubbleEditorApiClient(transport=fake_transport)


def test_list_branches_posts_get_versions(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = list_bubble_branches(profile="dev", client=_client_with_calls(calls))

    assert result["ok"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/get_versions"
    assert calls[0]["payload"] == {"appname": "synthetic-app"}
    assert calls[0]["headers"]["cookie"] == "sid=secret"
    assert result["request"]["headers"]["cookie"] == "[REDACTED]"


def test_branch_contributors_defaults_to_profile_version(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = list_branch_contributors(profile="dev", client=_client_with_calls(calls))

    assert result["ok"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/fetch_contributors_to_branch"
    assert calls[0]["payload"] == {"appname": "synthetic-app", "app_version": "test"}


def test_changelog_fetch_builds_pagination_and_filters(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = fetch_changelog_entries(
        profile="dev",
        start_index=50,
        num_fetch=500,
        filters={"type": "Data", "user_id": ["user-1"]},
        client=_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/fetch_changelog_entries"
    assert calls[0]["payload"] == {
        "appname": "synthetic-app",
        "app_version": "test",
        "start_index": 50,
        "num_fetch": 200,
        "filters": {"type": "Data", "user_id": ["user-1"]},
    }


def test_branch_create_supports_sub_branch_source_and_dry_run(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)

    result = create_bubble_branch(
        profile="dev",
        name="feature-child",
        from_app_version="parent-branch",
        description="child branch",
        execute=False,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["request"]["url"] == "https://bubble.io/appeditor/create_new_app_version"
    assert result["request"]["payload"] == {
        "appname": "synthetic-app",
        "from_app_version": "parent-branch",
        "app_version": "feature-child",
        "description": "child branch",
        "version_control_api_version": 7,
    }


def test_branch_delete_requires_confirm_when_executing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="confirm=true"):
        delete_bubble_branch(profile="dev", app_version="feature-branch", execute=True, confirm=False)
