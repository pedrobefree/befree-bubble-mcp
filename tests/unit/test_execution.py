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
        "changes": [{"path": ["page", "index"], "value": {"caption": "Hello"}}],
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
    assert calls[0][1]["changes"][0]["value"]["caption"] == "Hello"
    assert calls[0][2]["cookie"] == "sid=secret"


def test_editor_client_uses_aria_editor_write_headers() -> None:
    headers = build_editor_write_headers(synthetic_session(), write_payload())

    assert headers["accept"] == "application/json, text/javascript, */*; q=0.01"
    assert headers["content-type"] == "application/json"
    assert headers["x-bubble-appname"] == "synthetic-app"
    assert headers["x-requested-with"] == "XMLHttpRequest"
    assert headers["x-bubble-platform"] == "web"
    assert headers["x-bubble-breaking-revision"] == "5"
    assert headers["cookie"] == "sid=secret"
    assert headers["x-bubble-fiber-id"]
    assert headers["x-bubble-pl"]


def test_editor_client_blocks_html_login_response() -> None:
    def fake_transport(url, body, headers, timeout):  # type: ignore[no-untyped-def]
        return HttpResponse(status=200, body="<html>login</html>", headers={})

    with pytest.raises(RuntimeError, match="session expired"):
        BubbleEditorClient(transport=fake_transport).write(write_payload(), synthetic_session())


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


def test_execute_plan_requires_write_payload_when_executing() -> None:
    result = execute_plan(
        {"steps": [{"id": "s1", "tool_name": "create_text", "args": {"content": "Hello"}}]},
        profile="dev",
        execute=True,
        session=synthetic_session(),
    )

    assert result["ok"] is False
    assert result["results"][0]["reason"] == "step_has_no_write_payload"
