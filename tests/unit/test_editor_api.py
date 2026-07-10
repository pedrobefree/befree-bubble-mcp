import json
from typing import Any

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.execution.client import BubbleEditorClient, HttpResponse

from bubble_mcp.execution.editor_api import (
    BubbleEditorApiClient,
    confirm_bubble_branch_merge,
    create_bubble_branch,
    delete_bubble_branch,
    describe_bubble_branch_merge_conflicts,
    deploy_app_test_and_hotfix,
    finalize_bubble_branch_merge,
    fetch_jetstream_logs,
    fetch_changelog_entries,
    fetch_storage_usage,
    fetch_workflow_runs,
    fetch_workload_usage_breakdown,
    fetch_workload_usage_by_date,
    list_branch_contributors,
    list_bubble_branches,
    performance_audit,
    read_time_series,
    resolve_bubble_branch_merge_conflicts,
    start_bubble_branch_merge,
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


def _metrics_client_with_calls(calls: list[dict[str, Any]]) -> BubbleEditorApiClient:
    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        payload = json.loads(body.decode("utf-8"))
        calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if url.endswith("/get_workload_usage_by_date"):
            body_text = json.dumps(
                [
                    {
                        "date": "2026-04-11T00:00:00.000Z",
                        "live_workload_used": 10,
                        "test_workload_used": 2,
                        "total_workload_used": 12,
                    }
                ]
            )
        elif url.endswith("/get_workload_usage_breakdown"):
            body_text = json.dumps(
                [
                    {"tag": "workflow", "workload_used": 20, "activity_count": 4},
                    {"tag": "elasticsearch", "workload_used": 5, "activity_count": 1},
                ]
            )
        elif url.endswith("/get_jetstream_logs"):
            body_text = json.dumps(
                {
                    "data": {
                        "rows": [
                            {"message": "running event", "timestamp": 1783000000000},
                            {"message": "running action", "timestamp": 1783000001000},
                        ]
                    }
                }
            )
        elif url.endswith("/get_workflow_runs"):
            body_text = json.dumps({"current": {"web": 15}, "history": []})
        elif url.endswith("/get_current_app_plan_usage"):
            body_text = json.dumps({"workload": {"current": 20}})
        elif url.endswith("/get_storage_size"):
            body_text = json.dumps({"current": 123, "allowance": 1000})
        elif url.endswith("/read_time_series"):
            body_text = json.dumps({"series": [[1783000000000, 7]]})
        else:
            body_text = "{}"
        return HttpResponse(status=200, body=body_text, headers={})

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


def test_branch_merge_start_posts_sync_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = start_bubble_branch_merge(
        profile="dev",
        ours_version_id="53ffs",
        theirs_version_id="23347",
        savepoint_message="sync:Started merging changes from staging",
        session_id="1783611043308x32",
        execute=True,
        client=_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert result["executed"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/sync"
    assert calls[0]["payload"] == {
        "appname": "synthetic-app",
        "ours_version_id": "53ffs",
        "theirs_version_id": "23347",
        "session_id": "1783611043308x32",
        "savepoint_message": "sync:Started merging changes from staging",
    }


def test_branch_merge_confirm_builds_non_conflicting_write_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append({"url": url, "payload": json.loads(body.decode("utf-8")), "headers": headers})
        return HttpResponse(status=200, body='{"last_change":"1"}', headers={})

    result = confirm_bubble_branch_merge(
        profile="dev",
        merge_app_version="73ftr",
        session_id="1783611260020x32",
        execute=True,
        client=BubbleEditorClient(transport=fake_transport),
    )

    assert result["ok"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/write"
    assert calls[0]["payload"] == {
        "v": 1,
        "appname": "synthetic-app",
        "app_version": "73ftr",
        "changes": [
            {
                "body": True,
                "path_array": ["merge_changes_complete"],
                "version_control_api_version": 4,
                "changelog_data": [],
                "session_id": "1783611260020x32",
            }
        ],
        "appVersion": "73ftr",
    }


def test_branch_merge_confirm_builds_conflict_resolved_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append({"url": url, "payload": json.loads(body.decode("utf-8")), "headers": headers})
        return HttpResponse(status=200, body='{"last_change":"1"}', headers={})

    result = confirm_bubble_branch_merge(
        profile="dev",
        merge_app_version="73ftr",
        session_id="1783611260020x32",
        conflicts_resolved=True,
        execute=True,
        client=BubbleEditorClient(transport=fake_transport),
    )

    assert result["ok"] is True
    assert calls[0]["payload"]["changes"] == [
        {
            "body": None,
            "path_array": ["merge_changes_complete"],
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": "1783611260020x32",
        },
        {
            "body": None,
            "path_array": ["merge_changes"],
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": "1783611260020x32",
            "intent": {"name": "ResolveMergeChanges"},
        },
    ]


def test_branch_merge_conflicts_describe_summarizes_manual_decisions() -> None:
    payload = {
        "v": 1,
        "appname": "bovichain-g3",
        "app_version": "73ftr",
        "changes": [
            {
                "body": {
                    "0": {"%p": {"custom_event": "bbNyt3"}, "%x": "TriggerCustomEvent", "id": "bbQPT7"},
                    "1": {"%p": {"AAo": {"%e": {"0": "code"}}}, "%x": "PluginAction", "id": "baNDW1"},
                },
                "path_array": ["%ed", "bYRba8", "%wf", "baNDc1", "actions"],
                "intent": {"name": "MergeConflict"},
                "version_control_api_version": 4,
                "changelog_data": [],
                "session_id": "1783611260020x32",
            },
            {
                "body": '["bYReP8"]',
                "path_array": ["_index", "issues_sub", "bYRbZ8"],
                "intent": {"name": "Update index"},
                "version_control_api_version": 4,
                "changelog_data": [],
                "session_id": "1783611260020x32",
            },
        ],
    }

    described = describe_bubble_branch_merge_conflicts(payload=payload)

    assert described["ok"] is True
    assert described["conflict_count"] == 1
    assert described["decision_policy"] == "manual_user_selection_required"
    conflict = described["conflicts"][0]
    assert conflict["decision_required"] is True
    assert conflict["context"]["category"] == "workflow_actions"
    assert conflict["context"]["element_or_event_id"] == "bYRba8"
    assert conflict["context"]["workflow_id"] == "baNDc1"
    assert conflict["body_summary"]["action_count"] == 2
    assert conflict["body_summary"]["actions"][0]["type"] == "TriggerCustomEvent"
    assert described["auxiliary_change_count"] == 1
    assert described["auxiliary_changes"][0]["context"]["category"] == "auxiliary_index"


def test_branch_merge_resolve_conflicts_builds_observed_write_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append({"url": url, "payload": json.loads(body.decode("utf-8")), "headers": headers})
        return HttpResponse(status=200, body='{"last_change":"1"}', headers={})

    result = resolve_bubble_branch_merge_conflicts(
        profile="dev",
        merge_app_version="73ftr",
        session_id="1783613153432x33",
        changelog_data=[{"change_identifier": "baNDV1"}],
        execute=True,
        client=BubbleEditorClient(transport=fake_transport),
    )

    assert result["ok"] is True
    assert calls[0]["payload"]["changes"] == [
        {
            "body": None,
            "path_array": ["conflicts"],
            "version_control_api_version": 7,
            "changelog_data": [{"change_identifier": "baNDV1"}],
            "session_id": "1783613153432x33",
            "intent": {"name": "ResolveConflicts"},
        },
        {
            "body": None,
            "path_array": ["conflicts_theirs_version_name"],
            "version_control_api_version": 7,
            "changelog_data": [],
            "session_id": "1783613153432x33",
            "intent": {"name": "CleanupConflicts"},
        },
        {
            "body": None,
            "path_array": ["conflicts_undo_snapshot_id"],
            "version_control_api_version": 7,
            "changelog_data": [],
            "session_id": "1783613153432x33",
            "intent": {"name": "CleanupConflicts"},
        },
    ]


def test_branch_merge_finalize_posts_finalize_merge_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = finalize_bubble_branch_merge(
        profile="dev",
        merge_app_version="73ftr",
        target_version_id="53ffs",
        source_version_id="23347",
        source_branch_name="staging",
        user_id="1754998774520x493530240122586500",
        execute=True,
        client=_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert result["executed"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/finalize_merge"
    assert calls[0]["payload"] == {
        "appname": "synthetic-app",
        "temporary_merge_branch_id": "73ftr",
        "savepoint_message": "finalize_merge:Completed merging changes from staging",
        "version_control_api_version": 7,
        "changelog_data": [
            {
                "appname": "synthetic-app",
                "app_version": "53ffs",
                "user_id": "1754998774520x493530240122586500",
                "change_identifier": "73ftr",
                "display_name": "staging",
                "operation": "merge",
                "before_value": '"23347"',
                "inner_node_count": 1,
            }
        ],
    }


def test_deploy_app_test_and_hotfix_posts_captured_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = deploy_app_test_and_hotfix(
        profile="dev",
        message="Release from test",
        execute=True,
        client=_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert result["executed"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/deploy_app_test_and_hotfix"
    assert calls[0]["payload"] == {
        "appname": "synthetic-app",
        "from_app_version": "test",
        "force_deploy": False,
        "message": "Release from test",
        "deploy_mobile": False,
    }


def test_deploy_app_test_and_hotfix_previews_without_execute(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)

    result = deploy_app_test_and_hotfix(profile="dev", message="Release preview")

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["executed"] is False
    assert result["request"]["payload"]["from_app_version"] == "test"


def test_workload_usage_by_date_posts_editor_metrics_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = fetch_workload_usage_by_date(
        profile="dev",
        start="2026-04-11T00:00:00Z",
        end="2026-05-10T00:00:00Z",
        granularity="day",
        client=_metrics_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/get_workload_usage_by_date"
    assert calls[0]["payload"] == {
        "appname": "synthetic-app",
        "start_date_in_iso_format": "2026-04-11T00:00:00.000Z",
        "end_date_in_iso_format": "2026-05-10T00:00:00.000Z",
        "granularity": "day",
    }
    assert result["summary"]["live_workload_used"] == 10


def test_workload_breakdown_supports_tags_and_platform(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = fetch_workload_usage_breakdown(
        profile="dev",
        start="2026-04-11T00:00:00.000Z",
        end="2026-05-10T00:00:00.000Z",
        tag1="workflow",
        tag2=None,
        platform="web_and_mobile",
        client=_metrics_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/get_workload_usage_breakdown"
    assert calls[0]["payload"]["tag1"] == "workflow"
    assert calls[0]["payload"]["tag2"] is None
    assert calls[0]["payload"]["platformToggleValue"] == "web_and_mobile"
    assert result["summary"]["top_breakdown"][0]["tag"] == "workflow"


def test_logs_default_to_live_app_version(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = fetch_jetstream_logs(
        profile="dev",
        start="2026-04-11T00:00:00.000Z",
        end="2026-04-11T01:00:00.000Z",
        client=_metrics_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert result["app_version"] == "live"
    assert result["defaulted_to_live"] is True
    assert calls[0]["url"] == "https://bubble.io/appeditor/get_jetstream_logs"
    assert calls[0]["payload"]["tags"]["app_version"] == "live"
    assert calls[0]["payload"]["tags"]["appname"] == "synthetic-app"
    assert "running action" in calls[0]["payload"]["tags"]["message"]
    assert len(result["items"]) == 2


def test_secondary_metrics_endpoints_post_expected_payloads(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []
    client = _metrics_client_with_calls(calls)

    fetch_workflow_runs(profile="dev", platform="web_and_mobile", client=client)
    fetch_storage_usage(profile="dev", refresh=True, client=client)
    read_time_series(
        profile="dev",
        start=1783000000000,
        end=1783003600000,
        metric="page_views",
        resolution=60,
        client=client,
    )

    assert calls[0]["url"] == "https://bubble.io/appeditor/get_workflow_runs"
    assert calls[0]["payload"] == {"appname": "synthetic-app", "platform": "web_and_mobile"}
    assert calls[1]["url"] == "https://bubble.io/appeditor/get_storage_size"
    assert calls[1]["payload"] == {"appname": "synthetic-app", "refresh": True}
    assert calls[2]["url"] == "https://bubble.io/appeditor/read_time_series"
    assert calls[2]["payload"]["metric"] == "page_views"
    assert calls[2]["payload"]["use_observe"] is True


def test_performance_audit_combines_direct_editor_sources(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _store_profile_and_session(tmp_path, monkeypatch)
    calls: list[dict[str, Any]] = []

    result = performance_audit(
        profile="dev",
        start="2026-04-11T00:00:00.000Z",
        end="2026-05-10T00:00:00.000Z",
        client=_metrics_client_with_calls(calls),
    )

    assert result["ok"] is True
    assert result["app_version"] == "live"
    assert result["defaulted_to_live"] is True
    assert result["summary"]["recommendation_count"] >= 1
    assert result["recommendations"][0]["area"] == "workflow"
    assert [call["url"].removeprefix("https://bubble.io") for call in calls] == [
        "/appeditor/get_workload_usage_by_date",
        "/appeditor/get_workload_usage_breakdown",
        "/appeditor/get_workflow_runs",
        "/appeditor/get_current_app_plan_usage",
        "/appeditor/get_storage_size",
        "/appeditor/get_jetstream_logs",
    ]
