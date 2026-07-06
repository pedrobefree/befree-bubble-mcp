from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from typing import Any

from bubble_mcp.extension_companion import (
    CAPTURE_KEY_HEADER,
    ExtensionCompanionConfig,
    create_extension_companion_server,
)
from bubble_mcp.tool_authoring.sessions import create_authoring_session, describe_authoring_session


def _base_url(server_address: tuple[str, int]) -> str:
    return f"http://{server_address[0]}:{server_address[1]}"


def _json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


def test_extension_companion_serves_health_and_records_structure_event(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    event_log = tmp_path / "events.jsonl"
    server = create_extension_companion_server(
        ExtensionCompanionConfig(port=0, capture_key="dev-key", event_log_path=event_log)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = _base_url(server.server_address)
    try:
        status, health = _json_request(base_url, "/health")
        assert status == HTTPStatus.OK
        assert health["ok"] is True
        assert health["service"] == "befree-bubble-mcp"
        assert health["component"] == "chrome-extension-companion"
        assert health["capture_key_required"] is True

        denied_status, denied = _json_request(
            base_url,
            "/v1/bubble/crawler/ingest",
            method="POST",
            body={"appId": "synthetic-app"},
        )
        assert denied_status == HTTPStatus.FORBIDDEN
        assert denied["error"] == "capture_key_rejected"

        accepted_status, accepted = _json_request(
            base_url,
            "/v1/bubble/crawler/ingest",
            method="POST",
            headers={CAPTURE_KEY_HEADER: "dev-key"},
            body={"endpoint": "__befree_bubble_mcp_page_catalog__", "appId": "synthetic-app"},
        )
        assert accepted_status == HTTPStatus.OK
        assert accepted["ok"] is True
        assert accepted["kind"] == "structure"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    saved = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
    assert saved[0]["kind"] == "structure"
    assert saved[0]["app_id"] == "synthetic-app"


def test_extension_companion_can_feed_write_captures_to_tool_wizard(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    session = create_authoring_session(
        intent="Create an API Connector call",
        target="api_connector",
        profile="client",
    )
    server = create_extension_companion_server(
        ExtensionCompanionConfig(
            port=0,
            tool_session_id=session.id,
            event_log_path=tmp_path / "events.jsonl",
        )
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = _base_url(server.server_address)
    try:
        status, payload = _json_request(
            base_url,
            "/v1/bubble/crawler/write-ingest",
            method="POST",
            body={
                "endpoint": "/appeditor/write",
                "appId": "synthetic-app",
                "version": "test",
                "requestBody": {
                    "appname": "synthetic-app",
                    "app_version": "test",
                    "changes": [
                        {
                            "intent": {"name": "CreateApiConnectorCall"},
                            "path_array": ["plugins", "api_connector", "calls", "call_123"],
                            "body": {"name": "Get Products", "method": "GET"},
                        }
                    ],
                },
                "responseData": {"ok": True},
            },
        )
        assert status == HTTPStatus.OK
        assert payload["ok"] is True
        assert payload["kind"] == "write"
        assert payload["tool_authoring"]["classification"]["change_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    described = describe_authoring_session(session.id)
    assert described["session"]["capture_files"] == ["0001_extension_write_capture.json"]
    assert described["classification"]["change_count"] == 1
