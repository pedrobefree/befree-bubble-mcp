from pathlib import Path

import pytest

from bubble_mcp.tool_authoring.sessions import (
    append_capture_to_authoring_session,
    create_authoring_session,
    describe_authoring_session,
)


def test_authoring_session_groups_captured_write(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )
    result = append_capture_to_authoring_session(
        session.id,
        Path("tests/fixtures/tool-authoring/api-connector-write-capture.json"),
    )
    described = describe_authoring_session(session.id)

    assert result["ok"] is True
    assert described["session"]["intent"] == "Create an API Connector call"
    assert described["classification"]["change_count"] >= 1


def test_authoring_session_rejects_unsafe_session_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="safe path segment"):
        describe_authoring_session("../outside")


def test_authoring_session_rejects_symlink_capture(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    capture = Path("tests/fixtures/tool-authoring/api-connector-write-capture.json").resolve()
    symlink = tmp_path / "capture-link.json"
    symlink.symlink_to(capture)
    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )

    with pytest.raises(ValueError, match="symlink"):
        append_capture_to_authoring_session(session.id, symlink)


def test_authoring_session_rejects_home_expanded_symlink_capture(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    capture = Path("tests/fixtures/tool-authoring/api-connector-write-capture.json").resolve()
    symlink = home / "capture-link.json"
    symlink.symlink_to(capture)
    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )

    with pytest.raises(ValueError, match="symlink"):
        append_capture_to_authoring_session(session.id, Path("~/capture-link.json"))


def test_authoring_session_rejects_malformed_capture_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )

    with pytest.raises(ValueError, match="Expecting property name"):
        append_capture_to_authoring_session(session.id, malformed)


def test_authoring_session_rejects_capture_without_write_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    no_payload = tmp_path / "no-payload.json"
    no_payload.write_text("{}", encoding="utf-8")
    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )

    with pytest.raises(ValueError, match="does not contain a Bubble editor write body"):
        append_capture_to_authoring_session(session.id, no_payload)
