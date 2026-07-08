import json

import pytest

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.sessions.store import save_session, session_from_payload
from bubble_mcp.transfer.profiles import resolve_transfer_profiles


def _settings(tmp_path) -> None:  # type: ignore[no-untyped-def]
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile=None,
            profiles={
                "source": BubbleProfile(name="source", app_id="source-app", appname="source-app"),
                "target": BubbleProfile(name="target", app_id="target-app", appname="target-app"),
            },
        )
    )


def test_resolve_transfer_profiles_finds_contexts_and_target_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)
    source_context = tmp_path / "contexts" / "source" / "source-app-context.json"
    target_context = tmp_path / "contexts" / "target" / "target-app-context.json"
    source_context.parent.mkdir(parents=True)
    target_context.parent.mkdir(parents=True)
    source_context.write_text(json.dumps({"app_id": "source-app", "nodes": [], "edges": []}), encoding="utf-8")
    target_context.write_text(json.dumps({"app_id": "target-app", "nodes": [], "edges": []}), encoding="utf-8")
    save_session(
        "target",
        session_from_payload(
            {
                "appId": "target-app",
                "headers": {"cookie": "sid=secret", "x-bubble-client-version": "client-version"},
            }
        ),
    )

    resolved = resolve_transfer_profiles("source", "target")

    assert resolved.source.app_id == "source-app"
    assert resolved.target.app_id == "target-app"
    assert resolved.source_context_path == source_context
    assert resolved.target_context_path == target_context
    assert resolved.target_has_session is True
    assert resolved.target_write_ready is True


def test_resolve_transfer_profiles_uses_explicit_context_path_relative_to_config_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    explicit_context = tmp_path / "custom" / "source-context.json"
    explicit_context.parent.mkdir(parents=True)
    explicit_context.write_text(json.dumps({"app_id": "source-app", "nodes": [], "edges": []}), encoding="utf-8")
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile=None,
            profiles={
                "source": BubbleProfile(
                    name="source",
                    app_id="source-app",
                    appname="source-app",
                    app_json_path="custom/source-context.json",
                ),
                "target": BubbleProfile(name="target", app_id="target-app", appname="target-app"),
            },
        )
    )

    resolved = resolve_transfer_profiles("source", "target")

    assert resolved.source_context_path == explicit_context
    assert resolved.target_context_path is None
    assert resolved.target_has_session is False
    assert resolved.target_write_ready is False


def test_resolve_transfer_profiles_requires_distinct_configured_profiles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    with pytest.raises(ValueError, match="must be different"):
        resolve_transfer_profiles("source", "source")

    with pytest.raises(ValueError, match="source_profile not configured"):
        resolve_transfer_profiles("missing", "target")

    with pytest.raises(ValueError, match="target_profile not configured"):
        resolve_transfer_profiles("source", "missing")
