import json

import pytest

from bubble_mcp.execution.client import BubbleEditorClient, HttpResponse, build_editor_write_headers
from bubble_mcp.execution.executor import execute_plan
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


def test_editor_client_uses_aria_editor_write_headers() -> None:
    headers = build_editor_write_headers(synthetic_session(), write_payload())

    assert headers["accept"] == "application/json, text/javascript, */*; q=0.01"
    assert headers["accept-language"]
    assert headers["cache-control"] == "no-cache"
    assert headers["content-type"] == "application/json"
    assert headers["origin"] == "https://bubble.io"
    assert headers["referer"] == "https://bubble.io/"
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
    assert result["request"]["headers"]["cookie"] == "[REDACTED]"
    assert result["request"]["headers"]["x-bubble-appname"] == "synthetic-app"


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
