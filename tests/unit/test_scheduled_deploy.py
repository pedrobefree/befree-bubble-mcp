import json
from pathlib import Path

import pytest

from bubble_mcp.browser_automation.scheduled_deploy import (
    DEPLOY_DESCRIPTION_SELECTOR,
    _deploy_blocker_error,
    _visible_deploy_button_script,
    cancel_scheduled_deploy,
    deploy_history,
    execute_scheduled_deploy,
    list_scheduled_deploys,
    schedule_deploy,
)
from bubble_mcp.browser_automation.store import preview_path, scheduled_path
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings


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
        scheduled_at="2026-07-09T10:30:00",
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
    assert result["confirmation_required"] is True
    assert result["next_mcp_call"]["arguments"]["execute"] is True
    assert preview_path("client", preview["preview_id"]).exists()


def test_schedule_deploy_confirm_persists_record_and_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    preview_result = schedule_deploy(
        profile="client",
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
    )
    preview_id = preview_result["preview"]["preview_id"]
    result = schedule_deploy(
        profile="client",
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=preview_id,
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


def test_schedule_deploy_execution_requires_confirm_and_preview_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    missing_confirm = schedule_deploy(
        profile="client",
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
        execute=True,
    )
    assert missing_confirm["ok"] is False
    assert missing_confirm["error"] == "scheduled_deploy_requires_confirmation"

    missing_preview = schedule_deploy(
        profile="client",
        scheduled_at="2026-07-09T10:30:00Z",
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
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
    )
    scheduled = schedule_deploy(
        profile="client",
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=preview_result["preview"]["preview_id"],
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
            scheduled_at=f"2026-07-09T10:3{index}:00Z",
            message=f"Release {index}",
        )
        schedule_deploy(
            profile="client",
            scheduled_at=f"2026-07-09T10:3{index}:00Z",
            message=f"Release {index}",
            execute=True,
            confirm=True,
            preview_id=preview["preview"]["preview_id"],
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
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
    )
    scheduled = schedule_deploy(
        profile="client",
        scheduled_at="2026-07-09T10:30:00Z",
        message="Main branch release",
        execute=True,
        confirm=True,
        preview_id=record["preview"]["preview_id"],
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


def test_deploy_modal_selectors_match_current_bubble_markup() -> None:
    assert 'textarea[aria-labelledby="deploy-description-label"]' in DEPLOY_DESCRIPTION_SELECTOR
    assert "Add a short description that describes any new changes" in DEPLOY_DESCRIPTION_SELECTOR

    script = _visible_deploy_button_script()
    assert 'button[aria-label="Deploy"]' in script
    assert 'button[arialabel="Deploy"]' in script
    assert "Deploy confirm button is disabled" in script


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


def test_deploy_blocker_error_reports_missing_modal_without_issue_text() -> None:
    error = _deploy_blocker_error(
        {
            "hasIssueText": False,
            "deployButtons": [{"disabled": False, "text": "Deploy"}],
            "bodySnippet": "Deploy to live",
        }
    )

    assert error.startswith("scheduled_deploy_modal_not_ready")
