import json

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.execution.client import (
    EDITOR_CALCULATE_DERIVED_URL,
    EDITOR_GET_PLUGIN_CONFLICTS_URL,
    EDITOR_NOTIFY_AI_CONTEXT_CHANGE_URL,
    EDITOR_WRITE_URL,
    BubbleEditorClient,
    HttpResponse,
    build_editor_write_headers,
)
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.execution.plugins import build_install_plugin_payload, install_plugin
from bubble_mcp.sessions.store import session_from_payload


def synthetic_session():
    return session_from_payload(
        {
            "appId": "synthetic-app",
            "url": "https://bubble.io/page?name=synthetic-app",
            "headers": {"Cookie": "sid=secret", "User-Agent": "pytest"},
            "appVersion": "test",
        }
    )


def write_payload():
    return {
        "appname": "synthetic-app",
        "app_version": "test",
        "changes": [
            {
                "intent": {"name": "CreateElement"},
                "path_array": ["%p3", "index", "%el", "bText"],
                "body": {"%x": "Text", "%p": {"%nm": "Title", "%3": "Hello"}},
            }
        ],
    }


def test_editor_client_dry_run_redacts_session_headers() -> None:
    result = BubbleEditorClient().write(write_payload(), synthetic_session(), dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["request"]["headers"]["cookie"] == "[REDACTED]"


def test_editor_client_posts_write_payload_with_fake_transport() -> None:
    calls = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append((url, json.loads(body.decode("utf-8")), headers, timeout))
        return HttpResponse(status=200, body='{"last_change":123}', headers={})

    result = BubbleEditorClient(transport=fake_transport).write(write_payload(), synthetic_session())

    assert result["ok"] is True
    assert result["valid_shape"] is True
    assert calls[0][1]["changes"][0]["body"]["%p"]["%3"] == "Hello"
    assert calls[0][1]["app_version"] == "test"
    assert calls[0][1]["appVersion"] == "test"
    assert calls[0][2]["cookie"] == "sid=secret"


def test_editor_client_can_run_calculate_derived_after_write() -> None:
    calls = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        calls.append((url, json.loads(body.decode("utf-8")), headers, timeout))
        if url == EDITOR_CALCULATE_DERIVED_URL:
            return HttpResponse(status=200, body='{"fingerprints":["abc123"]}', headers={})
        return HttpResponse(status=200, body='{"last_change":123}', headers={})

    result = BubbleEditorClient(transport=fake_transport).write(
        write_payload(),
        synthetic_session(),
        calculate_derived=True,
    )

    assert result["ok"] is True
    assert calls[0][0] == EDITOR_WRITE_URL
    assert calls[1][0] == EDITOR_CALCULATE_DERIVED_URL
    assert calls[1][1] == {
        "derived": [{"function_name": "ElementTypeToPath", "args": [], "verbose": False}],
        "appname": "synthetic-app",
        "app_version": "test",
    }
    assert result["derived"]["response"]["fingerprints"] == ["abc123"]


def test_editor_client_previews_calculate_derived_request_in_dry_run() -> None:
    result = BubbleEditorClient().write(
        write_payload(),
        synthetic_session(),
        dry_run=True,
        calculate_derived=True,
    )

    assert result["ok"] is True
    assert result["derived"]["dry_run"] is True
    assert result["derived"]["request"]["url"] == EDITOR_CALCULATE_DERIVED_URL
    assert result["derived"]["request"]["payload"]["derived"][0]["function_name"] == "ElementTypeToPath"


def test_build_install_plugin_payload_matches_progressbar_editor_shape() -> None:
    payload = build_install_plugin_payload(
        app_id="courselaunch",
        app_version="test",
        plugin_key="progressbar-ProgressBar",
        id_counter=20000330,
    )

    assert payload["appname"] == "courselaunch"
    assert payload["app_version"] == "test"
    assert payload["appVersion"] == "test"
    assert payload["changes"][0]["body"] is True
    assert payload["changes"][0]["path_array"] == ["settings", "client_safe", "plugins", "progressbar"]
    assert payload["changes"][0]["intent"]["name"] == "ChangeAppSetting"
    assert payload["changes"][1]["body"] == 1
    assert payload["changes"][1]["path_array"] == [
        "settings",
        "client_safe",
        "progressbar_installed_version",
    ]
    assert payload["changes"][2] == {"type": "id_counter", "value": 20000330}


def test_install_plugin_runs_editor_post_install_calls() -> None:
    calls = []

    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        payload = json.loads(body.decode("utf-8"))
        calls.append((url, payload))
        if url == EDITOR_WRITE_URL:
            return HttpResponse(status=200, body='{"last_change":123,"id_counter":"20000330"}', headers={})
        if url == EDITOR_CALCULATE_DERIVED_URL:
            return HttpResponse(status=200, body='{"fingerprints":["abc123"]}', headers={})
        return HttpResponse(status=200, body="{}", headers={})

    result = install_plugin(
        profile="cliente2",
        session=synthetic_session(),
        plugin_key="progressbar-ProgressBar",
        app_id="courselaunch",
        execute=True,
        client=BubbleEditorClient(transport=fake_transport),
    )

    assert result["ok"] is True
    assert result["plugin_key"] == "progressbar"
    assert [call[0] for call in calls] == [
        EDITOR_WRITE_URL,
        EDITOR_GET_PLUGIN_CONFLICTS_URL,
        EDITOR_CALCULATE_DERIVED_URL,
        EDITOR_NOTIFY_AI_CONTEXT_CHANGE_URL,
    ]
    assert calls[0][1]["changes"][0]["path_array"] == ["settings", "client_safe", "plugins", "progressbar"]
    assert calls[2][1]["derived"] == [
        {"function_name": "UserCalls", "args": [], "verbose": False},
        {"function_name": "ElementTypeToPath", "args": [], "verbose": False},
    ]
    assert calls[3][1]["globalContextChanged"] is True


def test_install_plugin_auto_skips_installed_version_for_version_string_plugins() -> None:
    result = install_plugin(
        profile="cliente2",
        session=synthetic_session(),
        plugin_key="1627152028063x152738721905770500-AAs",
        app_id="courselaunch",
        plugin_value="2.0.0",
        execute=False,
        post_check_conflicts=False,
        calculate_derived=False,
        notify_ai_context_change=False,
    )

    assert result["ok"] is True
    assert result["plugin_key"] == "1627152028063x152738721905770500"
    assert result["include_installed_version"] is False
    changes = result["write_payload"]["changes"]
    assert len(changes) == 1
    assert changes[0]["path_array"] == [
        "settings",
        "client_safe",
        "plugins",
        "1627152028063x152738721905770500",
    ]
    assert changes[0]["body"] == "2.0.0"


def test_editor_client_uses_aria_editor_write_headers() -> None:
    headers = build_editor_write_headers(synthetic_session(), write_payload())

    assert headers["accept"] == "application/json, text/javascript, */*; q=0.01"
    assert headers["accept-language"]
    assert headers["cache-control"] == "no-cache"
    assert headers["content-type"] == "application/json"
    assert headers["origin"] == "https://bubble.io"
    assert headers["referer"] == "https://bubble.io/page?name=synthetic-app"
    assert headers["sec-fetch-dest"] == "empty"
    assert headers["sec-fetch-mode"] == "cors"
    assert headers["sec-fetch-site"] == "same-origin"
    assert headers["x-bubble-appname"] == "synthetic-app"
    assert headers["x-requested-with"] == "XMLHttpRequest"
    assert headers["x-bubble-platform"] == "web"
    assert headers["x-bubble-breaking-revision"] == "5"
    assert headers["x-bubble-r"] == "https://bubble.io/page?name=synthetic-app"
    assert headers["x-bubble-utm-data"] == "{}"
    assert headers["cookie"] == "sid=secret"
    assert headers["x-bubble-fiber-id"]
    assert headers["x-bubble-pl"]


def test_editor_client_blocks_html_login_response() -> None:
    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        return HttpResponse(status=200, body="<html>login</html>", headers={})

    with pytest.raises(RuntimeError, match="session expired"):
        BubbleEditorClient(transport=fake_transport).write(write_payload(), synthetic_session())


def test_editor_client_returns_structured_auth_block() -> None:
    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        return HttpResponse(status=401, body='{"error":"unauthorized"}', headers={})

    result = BubbleEditorClient(transport=fake_transport).write(write_payload(), synthetic_session())

    assert result["ok"] is False
    assert result["status"] == 401
    assert result["reason"] == "auth_blocked"
    assert result["session_write_ready"] is False
    assert result["session_diagnostics"]["missing"] == ["editor_request_headers"]
    assert "editor request headers" in result["next_user_action"]
    assert result["request"]["headers"]["cookie"] == "[REDACTED]"
    assert result["request"]["headers"]["x-bubble-appname"] == "synthetic-app"


def test_editor_write_headers_use_session_url_as_referer() -> None:
    headers = build_editor_write_headers(synthetic_session(), write_payload())

    assert headers["referer"] == "https://bubble.io/page?name=synthetic-app"


def test_execute_plan_runs_write_payload_steps_with_fake_client() -> None:
    class FakeClient:
        def write(self, payload, session, *, dry_run=False):  # type: ignore[no-untyped-def]
            return {"ok": True, "payload": payload, "dry_run": dry_run}

    plan = {"steps": [{"id": "s1", "args": {"write_payload": write_payload()}}]}

    result = execute_plan(
        plan,
        profile="dev",
        execute=True,
        session=synthetic_session(),
        client=FakeClient(),  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["results"][0]["executed"] is True
    assert result["structural_validation"]["status"] == "executable"
    assert result["operation_snapshot"]["next_user_action"] == "inspect_editor_result"


def test_execute_plan_uses_profile_app_version_for_existing_write_payload(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="branch-profile",
            profiles={
                "branch-profile": BubbleProfile(
                    name="branch-profile",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="feature-branch",
                )
            },
        )
    )

    class FakeClient:
        def __init__(self) -> None:
            self.payloads = []

        def write(self, payload, session, *, dry_run=False):  # type: ignore[no-untyped-def]
            self.payloads.append(payload)
            return {"ok": True, "payload": payload, "dry_run": dry_run}

    fake_client = FakeClient()
    payload = write_payload()
    assert payload["app_version"] == "test"

    result = execute_plan(
        {"steps": [{"id": "s1", "args": {"write_payload": payload}}]},
        profile="branch-profile",
        execute=True,
        session=synthetic_session(),
        client=fake_client,  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert fake_client.payloads[0]["app_version"] == "feature-branch"


def test_execute_plan_requires_write_payload_when_executing() -> None:
    result = execute_plan(
        {"steps": [{"id": "s1", "tool_name": "create_text", "args": {"content": "Hello"}}]},
        profile="dev",
        execute=True,
        session=synthetic_session(),
    )

    assert result["ok"] is False
    assert result["structural_validation"]["status"] == "blocked"
    assert result["operation_snapshot"]["next_user_action"] == "compile_plan_before_execution"
    assert "no write_payload" in result["structural_validation"]["errors"][0]


def test_execute_plan_blocks_destructive_steps_without_confirmation() -> None:
    result = execute_plan(
        {
            "steps": [
                {
                    "id": "s1",
                    "tool_name": "delete_element",
                    "args": {"write_payload": write_payload()},
                }
            ]
        },
        profile="dev",
        execute=True,
        session=synthetic_session(),
    )

    assert result["ok"] is False
    assert result["structural_validation"]["status"] == "blocked"
    assert result["operation_snapshot"]["next_user_action"] == "request_user_confirmation"
