from pathlib import Path

import pytest

from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.tool_authoring.sessions import (
    active_authoring_session_id,
    append_capture_to_authoring_session,
    create_authoring_session,
    describe_authoring_session,
    finalize_authoring_session,
    generate_authoring_extension_pack,
    set_active_authoring_session,
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
    assert described["active"] is True
    assert active_authoring_session_id() == session.id
    assert described["classification"]["change_count"] >= 1


def test_authoring_session_finalize_returns_learned_patterns(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )
    append_capture_to_authoring_session(
        session.id,
        Path("tests/fixtures/tool-authoring/api-connector-write-capture.json"),
    )

    result = finalize_authoring_session(session.id)

    assert result["ok"] is True
    assert result["status"] == "ready_for_review"
    assert result["active"] is True
    assert result["capture_summary"]["capture_count"] == 1
    assert result["capture_summary"]["intents"] == ["CreateApiConnectorCall"]
    assert result["capture_summary"]["api_connector_ids"]["collections"] == []
    assert result["capture_summary"]["api_connector_ids"]["calls"] == ["call_123"]
    assert any("CreateApiConnectorCall" in item for item in result["understanding"]["learned"])
    assert any("autenticacao" in question for question in result["questions"])
    assert any("execute=false" in step for step in result["testing_guidance"])


def test_authoring_session_finalize_without_captures_requests_capture(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )

    result = finalize_authoring_session(session.id)

    assert result["ok"] is False
    assert result["status"] == "needs_captures"
    assert result["capture_summary"]["capture_count"] == 0
    assert result["understanding"]["learned"] == ["Nenhuma captura valida foi adicionada a sessao ainda."]


def test_authoring_session_generate_creates_valid_extension_pack(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )
    append_capture_to_authoring_session(
        session.id,
        Path("tests/fixtures/tool-authoring/api-connector-write-capture.json"),
    )

    result = generate_authoring_extension_pack(session.id)

    assert result["ok"] is True
    assert result["extension_id"].startswith("local.toolwiz.api_connector.")
    assert result["tool_name"].endswith(".create_an_api_connector_call")
    pack_path = Path(str(result["pack_path"]))
    assert (pack_path / "extension.json").exists()
    assert Path(str(result["tool_path"])).exists()
    assert Path(str(result["evidence_path"])).exists()
    assert validate_extension_pack(pack_path).ok is True
    assert result["next_mcp_calls"][0]["tool"] == "bubble_extension_validate"
    assert result["next_mcp_calls"][3]["tool"] == "bubble_extension_call"


def test_authoring_session_generate_without_captures_returns_guidance(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )

    result = generate_authoring_extension_pack(session.id)

    assert result["ok"] is False
    assert result["status"] == "needs_captures"
    assert result["error"] == "tool_authoring_session_has_no_captures"


def test_authoring_session_can_activate_existing_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    first = create_authoring_session(intent="First", target="api_connector", profile="client")
    second = create_authoring_session(intent="Second", target="workflow", profile="client")

    assert active_authoring_session_id() == second.id
    result = set_active_authoring_session(first.id)

    assert result["ok"] is True
    assert active_authoring_session_id() == first.id
    assert describe_authoring_session(first.id)["active"] is True
    assert describe_authoring_session(second.id)["active"] is False


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
