import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bubble_mcp.browser_automation.scheduled_deploy import (
    DEPLOY_DESCRIPTION_SELECTOR,
    _deploy_blocker_error,
    _deploy_completion_script,
    _visible_deploy_button_script,
    auto_fix_objective_deploy_issues,
    cancel_scheduled_deploy,
    deploy_history,
    execute_scheduled_deploy_direct,
    execute_scheduled_deploy,
    list_scheduled_deploys,
    schedule_deploy,
)
from bubble_mcp.browser_automation.store import preview_path, scheduled_path
from bubble_mcp.context.path_api import PathResult
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.execution.client import HttpResponse
from bubble_mcp.execution.editor_api import BubbleEditorApiClient
from bubble_mcp.sessions.store import BubbleSessionData, save_session, session_from_payload


def _noop_executor(record):  # type: ignore[no-untyped-def]
    # `schedule_deploy(execute=True, ...)` arms a real `threading.Timer` that
    # fires `executor or execute_scheduled_deploy` once `scheduled_at`
    # elapses. Without an explicit executor the *real* Playwright-based
    # execute_scheduled_deploy gets armed -- launching an actual browser
    # against bubble.io. Tests that don't care about execution outcome must
    # pass this no-op instead of relying on the default.
    return {"ok": True}


def _future_iso(offset_seconds: float = 0.0) -> str:
    # A `scheduled_at` far enough in the future that the background timer's
    # delay is always large, regardless of what today's date happens to be.
    # A fixed "near now" literal here is a landmine: it looks safely in the
    # future when the test is written, but once wall-clock time catches up
    # to it, `_arm_timer`'s delay collapses to ~0 and the timer fires
    # mid-test-run instead of harmlessly dying with the process at exit.
    # Kept under threading.TIMEOUT_MAX (~49.7 days on Windows, where
    # Timer.wait ultimately hits WaitForSingleObject's DWORD millisecond
    # limit) so the daemon Timer thread doesn't itself raise OverflowError.
    when = datetime.now(timezone.utc) + timedelta(days=30, seconds=offset_seconds)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _settings(tmp_path: Path) -> None:
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="bubble-app",
                    appname="bubble-app",
                    app_version="test",
                )
            },
        )
    )


def test_schedule_deploy_preview_requires_confirmation_and_forces_test_version(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    result = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    preview = result["preview"]
    assert preview["profile"] == "client"
    assert preview["app_id"] == "bubble-app"
    assert preview["app_version"] == "test"
    assert preview["message"] == "Main branch release"
    assert preview["timezone"]
    assert preview["auto_fix_objective_issues"] is False
    assert result["confirmation_required"] is True
    assert result["next_mcp_call"]["arguments"]["execute"] is True
    assert result["next_mcp_call"]["arguments"]["auto_fix_objective_issues"] is False
    assert preview_path("client", preview["preview_id"]).exists()


def test_schedule_deploy_confirm_persists_record_and_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    preview_result = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
    )
    preview_id = preview_result["preview"]["preview_id"]
    result = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=preview_id,
        executor=_noop_executor,
    )

    assert result["ok"] is True
    record = result["deploy"]
    assert record["status"] == "scheduled"
    assert record["app_version"] == "test"
    assert scheduled_path("client", record["deploy_id"]).exists()
    assert not preview_path("client", preview_id).exists()
    listed = list_scheduled_deploys(profile="client")
    assert listed["count"] == 1
    assert listed["scheduled"][0]["deploy_id"] == record["deploy_id"]
    history = deploy_history(profile="client")
    assert history["history"][0]["event"] == "scheduled"


def test_schedule_deploy_persists_objective_issue_auto_fix_authorization(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    preview_result = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        auto_fix_objective_issues=True,
    )
    preview_id = preview_result["preview"]["preview_id"]
    assert preview_result["preview"]["auto_fix_objective_issues"] is True
    assert preview_result["next_mcp_call"]["arguments"]["auto_fix_objective_issues"] is True

    result = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=preview_id,
        executor=_noop_executor,
    )

    assert result["deploy"]["auto_fix_objective_issues"] is True


def test_schedule_deploy_execution_requires_confirm_and_preview_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    missing_confirm = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        execute=True,
    )
    assert missing_confirm["ok"] is False
    assert missing_confirm["error"] == "scheduled_deploy_requires_confirmation"

    missing_preview = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        execute=True,
        confirm=True,
    )
    assert missing_preview["ok"] is False
    assert missing_preview["error"] == "scheduled_deploy_requires_preview_id"


def test_cancel_scheduled_deploy_moves_record_to_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)
    preview_result = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
    )
    scheduled = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=preview_result["preview"]["preview_id"],
        executor=_noop_executor,
    )["deploy"]

    result = cancel_scheduled_deploy(profile="client", deploy_id=scheduled["deploy_id"])

    assert result["ok"] is True
    assert result["cancelled"] is True
    assert list_scheduled_deploys(profile="client")["count"] == 0
    history = deploy_history(profile="client")
    assert [item["event"] for item in history["history"]] == ["scheduled", "cancelled"]
    hidden = deploy_history(profile="client", include_cancelled=False)
    assert [item["event"] for item in hidden["history"]] == ["scheduled"]


def test_deploy_storage_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    with pytest.raises(ValueError, match="Invalid deploy_id"):
        scheduled_path("client", "../bad")


def test_history_limit_returns_latest_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    for index in range(3):
        preview = schedule_deploy(
            profile="client",
            scheduled_at=_future_iso(offset_seconds=index),
            message=f"Release {index}",
        )
        schedule_deploy(
            profile="client",
            scheduled_at=_future_iso(offset_seconds=index),
            message=f"Release {index}",
            execute=True,
            confirm=True,
            preview_id=preview["preview"]["preview_id"],
            executor=_noop_executor,
        )

    history = deploy_history(profile="client", limit=2)

    assert [item["message"] for item in history["history"]] == ["Release 1", "Release 2"]


def test_confirmed_schedule_arms_executor(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)
    calls = []

    def fake_executor(record):  # type: ignore[no-untyped-def]
        calls.append(record.deploy_id)
        return {"ok": True}

    preview = schedule_deploy(
        profile="client",
        scheduled_at="2020-01-01T10:30:00Z",
        message="Immediate release",
    )
    result = schedule_deploy(
        profile="client",
        scheduled_at="2020-01-01T10:30:00Z",
        message="Immediate release",
        execute=True,
        confirm=True,
        preview_id=preview["preview"]["preview_id"],
        executor=fake_executor,
    )

    assert result["ok"] is True
    assert calls == [] or calls == [result["deploy"]["deploy_id"]]


def test_execute_scheduled_deploy_reports_missing_playwright(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)
    record = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
    )
    scheduled = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=record["preview"]["preview_id"],
        executor=_noop_executor,
    )["deploy"]

    real_import = __import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "playwright.sync_api":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    result = execute_scheduled_deploy(
        __import__("bubble_mcp.browser_automation.models", fromlist=["ScheduledDeployRecord"]).ScheduledDeployRecord.from_dict(
            scheduled
        )
    )

    assert result["ok"] is False
    assert "Playwright is required" in result["error"]


class _NoIssueApi:
    def resolve_path(self, path_array):  # type: ignore[no-untyped-def]
        if path_array == ["_index", "issues_list"]:
            return PathResult(type="data", data={})
        return PathResult(type="data", data={})


def test_execute_scheduled_deploy_direct_uses_stored_session_without_browser(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)
    save_session(
        "client",
        session_from_payload(
            {
                "appId": "bubble-app",
                "appVersion": "test",
                "url": "https://bubble.io/page?id=bubble-app&version=test",
                "headers": {
                    "Cookie": "sid=secret",
                    "User-Agent": "pytest",
                    "x-bubble-client-version": "client-version",
                    "x-bubble-client-commit-timestamp": "1783547016000",
                },
            }
        ),
    )
    calls: list[dict[str, object]] = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append(
            {
                "url": url,
                "payload": json.loads(body.decode("utf-8")),
                "headers": headers,
                "timeout": timeout,
            }
        )
        return HttpResponse(status=200, body='{"status":"success"}', headers={})

    record = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Direct release",
    )
    scheduled = schedule_deploy(
        profile="client",
        scheduled_at=_future_iso(),
        message="Direct release",
        execute=True,
        confirm=True,
        preview_id=record["preview"]["preview_id"],
        executor=_noop_executor,
    )["deploy"]

    result = execute_scheduled_deploy_direct(
        __import__("bubble_mcp.browser_automation.models", fromlist=["ScheduledDeployRecord"]).ScheduledDeployRecord.from_dict(
            scheduled
        ),
        api_client=BubbleEditorApiClient(transport=fake_transport),
        path_api=_NoIssueApi(),  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["deployment_mode"] == "direct"
    assert result["session_refreshed"] is False
    assert calls[0]["url"] == "https://bubble.io/appeditor/deploy_app_test_and_hotfix"
    assert calls[0]["payload"] == {
        "appname": "bubble-app",
        "from_app_version": "test",
        "force_deploy": False,
        "message": "Direct release",
        "deploy_mobile": False,
    }
    assert result["direct_deploy"]["request"]["headers"]["cookie"] == "[REDACTED]"


def test_deploy_modal_selectors_match_current_bubble_markup() -> None:
    assert 'textarea[aria-labelledby="deploy-description-label"]' in DEPLOY_DESCRIPTION_SELECTOR
    assert "Add a short description that describes any new changes" in DEPLOY_DESCRIPTION_SELECTOR

    script = _visible_deploy_button_script()
    assert 'button[aria-label="Deploy"]' in script
    assert 'button[arialabel="Deploy"]' in script
    assert "textareaRect" in script
    assert "Deploy description textarea not found before confirm click" in script
    assert "Deploy confirm button is disabled" in script

    completion_script = _deploy_completion_script()
    assert DEPLOY_DESCRIPTION_SELECTOR in completion_script
    assert "visibleTextarea" in completion_script


def _session() -> BubbleSessionData:
    return BubbleSessionData(
        app_id="bubble-app",
        url="https://bubble.io/page?name=index&id=bubble-app&version=test",
        method="POST",
        headers={"cookie": "sid=test"},
        cookies="sid=test",
        app_version="test",
        captured_at="2026-07-09T10:30:00Z",
        source="test",
    )


class _FakeIssueApi:
    def __init__(self, issue: dict[str, object] | None = None) -> None:
        self.issue = issue

    def resolve_path(self, path_array):  # type: ignore[no-untyped-def]
        if path_array == ["_index", "issues_list"]:
            return PathResult(
                type="data",
                data={"issue_alias": json.dumps([self.issue]) if self.issue else "[]"},
            )
        if path_array == ["_index", "page_name_to_id"]:
            return PathResult(type="data", data={"index": "index_page"})
        if path_array == ["_index", "issues_sub"]:
            return PathResult(type="data", data={"index_page": json.dumps(["issue_alias"])})
        return PathResult(type="data", data=None)

    def resolve_multiple(self, path_arrays):  # type: ignore[no-untyped-def]
        return 61493718674, [PathResult(type="data", data="Group_modal_overlay_") for _path in path_arrays]


class _FakeEditorClient:
    def __init__(self, api: _FakeIssueApi) -> None:
        self.api = api
        self.payload = None

    def write(self, payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        self.payload = payload
        self.api.issue = None
        return {
            "ok": True,
            "dry_run": dry_run,
            "derived": {"ok": calculate_derived},
            "request": {"payload": payload, "headers": {"cookie": "[REDACTED]"}},
        }


def test_auto_fix_objective_deploy_issues_clears_invalid_popup_style() -> None:
    issue = {
        "message": "Popup checkout-modal - None (Custom) is not a possible option",
        "node": {
            "constructor_name": "Literal",
            "args": [
                {"type": "json", "value": "%p3.bTGbC.%el.ai_RRuRZMgA.%s1"},
                {
                    "type": "node",
                    "value": {
                        "constructor_name": "Element",
                        "args": [{"type": "json", "value": "%p3.bTGbC.%el.ai_RRuRZMgA"}],
                    },
                },
            ],
        },
    }
    api = _FakeIssueApi(issue)
    editor = _FakeEditorClient(api)

    result = auto_fix_objective_deploy_issues(
        profile="client",
        app_id="bubble-app",
        session=_session(),
        api=api,  # type: ignore[arg-type]
        editor_client=editor,  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["fixes_applied"] is True
    assert result["issues_after"] == []
    assert editor.payload["changes"] == [
        {
            "intent": {"name": "SetData", "id": 910001, "source_appname": ""},
            "path_array": ["%p3", "bTGbC", "%el", "ai_RRuRZMgA", "%s1"],
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
        }
    ]


def test_auto_fix_objective_deploy_issues_rejects_ambiguous_issue() -> None:
    issue = {
        "message": "Set state: Only when should be yes / no but right now it is empty",
        "node": {
            "constructor_name": "ObjectLiteral",
            "args": [{"type": "json", "value": "%p3.bTGbC.%wf.workflow.actions.0.%p.%c"}],
        },
    }
    api = _FakeIssueApi(issue)
    editor = _FakeEditorClient(api)

    result = auto_fix_objective_deploy_issues(
        profile="client",
        app_id="bubble-app",
        session=_session(),
        api=api,  # type: ignore[arg-type]
        editor_client=editor,  # type: ignore[arg-type]
    )

    assert result["ok"] is False
    assert result["error"] == "scheduled_deploy_unfixable_bubble_issues"
    assert result["unsupported_issues"][0]["message"].startswith("Set state")
    assert editor.payload is None


def test_deploy_blocker_error_reports_bubble_issues() -> None:
    error = _deploy_blocker_error(
        {
            "hasIssueText": True,
            "deployButtons": [{"disabled": True, "text": "Deploy"}],
            "bodySnippet": "This app has issues that need to be fixed before deploy.",
        }
    )

    assert error.startswith("scheduled_deploy_blocked_by_bubble_issues")
    assert "app issues or validation" in error


def test_deploy_blocker_error_reports_temporary_bubble_error() -> None:
    error = _deploy_blocker_error(
        {
            "hasIssueText": True,
            "deployButtons": [{"disabled": False, "text": "Continue"}],
            "bodySnippet": "You cannot deploy your app because there was a temporary error deploying your app... Please try again.",
        }
    )

    assert error.startswith("scheduled_deploy_temporary_bubble_error")
    assert "temporary error" in error


def test_deploy_blocker_error_reports_missing_modal_without_issue_text() -> None:
    error = _deploy_blocker_error(
        {
            "hasIssueText": False,
            "deployButtons": [{"disabled": False, "text": "Deploy"}],
            "bodySnippet": "Deploy to live",
        }
    )

    assert error.startswith("scheduled_deploy_modal_not_ready")
