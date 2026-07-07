import json

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.context.source import save_context
from bubble_mcp.context.detector import default_context_path
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.profile_status import profile_status
from bubble_mcp.sessions.store import BubbleSessionData, save_session


def test_profile_status_reports_ready_profile(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "contexts" / "client-app.json"
    save_context(
        BubbleProjectContext(
            app_id="client-app",
            source="test",
            nodes=[],
            edges=[],
            metadata={},
        ),
        context_path,
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="client-app",
                    appname="client-app",
                    app_version="test",
                    app_json_path="contexts/client-app.json",
                )
            },
        )
    )
    save_session(
        "client",
        BubbleSessionData(
            app_id="client-app",
            url="https://bubble.io/appeditor/write",
            method="POST",
            headers={"x-bubble-appname": "client-app", "x-bubble-client-version": "client-version"},
            cookies="sid=secret",
            app_version="test",
            captured_at="2026-07-04T00:00:00+00:00",
            source="test",
        ),
        tmp_path,
    )

    status = profile_status("client")

    assert status["ok"] is True
    assert status["ready"] is True
    assert status["session"]["exists"] is True
    assert status["session"]["app_id_matches_profile"] is True
    assert status["session"]["write_ready"] is True
    assert status["context"]["loadable"] is True
    assert status["context"]["freshness"]["stale"] is False
    assert status["next_actions"] == []


def test_profile_status_reports_missing_setup_next_actions(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="client-app",
                    appname="client-app",
                    app_json_path="contexts/missing.json",
                )
            },
        )
    )

    status = profile_status("client")

    assert status["ok"] is True
    assert status["ready"] is False
    assert status["session"]["exists"] is False
    assert status["context"]["loadable"] is False
    tools = [action["tool"] for action in status["next_actions"]]
    assert tools == ["bubble_session_login", "bubble_context_detect"]
    assert status["next_actions"][0]["args"]["wait_seconds"] == 180
    assert "session login" in status["next_actions"][0]["command"]


def test_profile_status_rejects_context_for_another_app(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "contexts" / "wrong-app.json"
    save_context(
        BubbleProjectContext(
            app_id="other-app",
            source="test",
            nodes=[],
            edges=[],
            metadata={},
        ),
        context_path,
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="client-app",
                    appname="client-app",
                    app_json_path="contexts/wrong-app.json",
                )
            },
        )
    )
    save_session(
        "client",
        BubbleSessionData(
            app_id="client-app",
            url="https://bubble.io/appeditor/write",
            method="POST",
            headers={"x-bubble-client-version": "client-version"},
            cookies="sid=secret",
            app_version="test",
            captured_at="2026-07-04T00:00:00+00:00",
            source="test",
        ),
        tmp_path,
    )

    status = profile_status("client")

    assert status["ready"] is False
    assert status["context"]["loadable"] is True
    assert status["context"]["app_id_matches_profile"] is False
    assert status["next_actions"] == [
        {
            "tool": "bubble_context_detect",
            "args": {"profile": "client", "app_id": "client-app", "force": True},
            "reason": "Loaded context app_id does not match the configured profile app_id. Refresh context for this profile.",
        }
    ]


def test_profile_status_requires_write_ready_session(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "contexts" / "client-app.json"
    save_context(
        BubbleProjectContext(
            app_id="client-app",
            source="test",
            nodes=[],
            edges=[],
            metadata={},
        ),
        context_path,
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="client-app",
                    appname="client-app",
                    app_version="test",
                    app_json_path="contexts/client-app.json",
                )
            },
        )
    )
    save_session(
        "client",
        BubbleSessionData(
            app_id="client-app",
            url="https://bubble.io/page?id=client-app",
            method="POST",
            headers={"cookie": "sid=secret"},
            cookies="sid=secret",
            app_version="test",
            captured_at="2026-07-04T00:00:00+00:00",
            source="test",
        ),
        tmp_path,
    )

    status = profile_status("client")

    assert status["ready"] is False
    assert status["session"]["write_ready"] is False
    assert status["session"]["write_diagnostics"]["missing"] == ["editor_request_headers"]
    assert status["next_actions"][0]["tool"] == "bubble_session_login"
    assert "editor request headers" in status["next_actions"][0]["reason"]


def test_profile_status_uses_compact_context_for_bubble_source_artifact(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    bubble_path = tmp_path / "contexts" / "client-app.bubble"
    bubble_path.parent.mkdir(parents=True)
    bubble_path.write_text("{}", encoding="utf-8")
    compact_context_path = default_context_path("client", "client-app")
    save_context(
        BubbleProjectContext(
            app_id="client-app",
            source=str(bubble_path),
            nodes=[],
            edges=[],
            metadata={},
        ),
        compact_context_path,
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="client-app",
                    appname="client-app",
                    app_json_path="contexts/client-app.bubble",
                )
            },
        )
    )
    save_session(
        "client",
        BubbleSessionData(
            app_id="client-app",
            url="https://bubble.io/appeditor/write",
            method="POST",
            headers={"x-bubble-client-version": "client-version"},
            cookies="sid=secret",
            app_version="test",
            captured_at="2026-07-04T00:00:00+00:00",
            source="test",
        ),
        tmp_path,
    )

    status = profile_status("client")

    assert status["ready"] is True
    assert status["session"]["write_ready"] is True
    assert status["context"]["path"] == str(compact_context_path)
    assert status["context"]["source_artifact"]["path"] == str(bubble_path)


def test_profile_status_returns_safe_context_summary(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    context_path = tmp_path / "contexts" / "client-app.json"
    save_context(
        BubbleProjectContext(
            app_id="client-app",
            source="test",
            nodes=[
                BubbleContextNode(
                    id="node-1",
                    label="Secret node",
                    type="page",
                    metadata={"private_property": "node-secret"},
                )
            ],
            edges=[],
            metadata={
                "saved_at": "2026-07-04T00:00:00+00:00",
                "client_safe": {"api_key": "client-secret"},
                "default_styles": {"Button": {"secret": "style-secret"}},
                "settings": {"secret": "settings-secret"},
            },
        ),
        context_path,
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={
                "client": BubbleProfile(
                    name="client",
                    app_id="client-app",
                    appname="client-app",
                    app_json_path="contexts/client-app.json",
                )
            },
        )
    )

    status = profile_status("client")
    encoded = json.dumps(status)

    assert status["context"]["summary"]["counts"] == {"page": 1}
    assert isinstance(status["context"]["summary"]["metadata"]["saved_at"], str)
    assert status["context"]["summary"]["metadata"]["default_styles"] == {"count": 1}
    assert "client_safe" not in encoded
    assert "client-secret" not in encoded
    assert "node-secret" not in encoded
    assert "style-secret" not in encoded
    assert "settings-secret" not in encoded


def test_profile_status_missing_profile(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(BubbleMcpSettings(config_dir=tmp_path, default_profile=None, profiles={}))

    status = profile_status("missing")

    assert status["ok"] is False
    assert status["ready"] is False
    assert status["profile"] is None
    assert status["next_actions"][0]["tool"] == "bubble_profile_list"


def test_profile_status_redacts_session_secret_material(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={"client": BubbleProfile(name="client", app_id="client-app", appname="client-app")},
        )
    )
    save_session(
        "client",
        BubbleSessionData(
            app_id="client-app",
            url="https://bubble.io/appeditor/write",
            method="POST",
            headers={"cookie": "secret"},
            cookies="secret",
            app_version="test",
            captured_at="2026-07-04T00:00:00+00:00",
            source="test",
        ),
        tmp_path,
    )

    encoded = json.dumps(profile_status("client"))

    assert "secret" not in encoded
