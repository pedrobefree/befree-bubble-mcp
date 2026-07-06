"""Local HTTP companion server for the Chrome extension."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.tool_authoring.sessions import (
    active_authoring_session_id,
    append_capture_payload_to_authoring_session,
)


DEFAULT_COMPANION_HOST = "127.0.0.1"
DEFAULT_COMPANION_PORT = 3847
MAX_REQUEST_BYTES = 10 * 1024 * 1024
CAPTURE_KEY_HEADER = "X-Bubble-MCP-Capture-Key"


@dataclass(frozen=True)
class ExtensionCompanionConfig:
    host: str = DEFAULT_COMPANION_HOST
    port: int = DEFAULT_COMPANION_PORT
    capture_key: str = ""
    tool_session_id: str | None = None
    event_log_path: Path | None = None


class ExtensionCompanionHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server carrying immutable companion config."""

    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], config: ExtensionCompanionConfig) -> None:
        self.config = config
        super().__init__(server_address, ExtensionCompanionRequestHandler)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extension_companion_dir() -> Path:
    return get_config_dir() / "extension-companion"


def default_event_log_path() -> Path:
    return extension_companion_dir() / "events.jsonl"


def _event_log_path(config: ExtensionCompanionConfig) -> Path:
    return config.event_log_path or default_event_log_path()


def _server_host(server: ExtensionCompanionHTTPServer) -> str:
    host = server.server_address[0]
    return host.decode("utf-8") if isinstance(host, bytes) else str(host)


def _extract_app_id(payload: dict[str, Any]) -> str | None:
    request_body = payload.get("requestBody")
    request = request_body if isinstance(request_body, dict) else {}
    value = payload.get("appId") or payload.get("app_id") or request.get("appname") or request.get("appId")
    text = str(value or "").strip()
    return text or None


def _extract_version(payload: dict[str, Any]) -> str | None:
    request_body = payload.get("requestBody")
    request = request_body if isinstance(request_body, dict) else {}
    value = (
        payload.get("version")
        or payload.get("appVersion")
        or request.get("app_version")
        or request.get("appVersion")
    )
    text = str(value or "").strip()
    return text or None


def _write_change_count(payload: dict[str, Any]) -> int:
    request_body = payload.get("requestBody")
    request = request_body if isinstance(request_body, dict) else {}
    changes = request.get("changes")
    return len(changes) if isinstance(changes, list) else 0


def _resolve_tool_session_id(config: ExtensionCompanionConfig) -> str | None:
    if config.tool_session_id:
        return config.tool_session_id
    return active_authoring_session_id()


def record_extension_companion_event(
    kind: str,
    payload: dict[str, Any],
    config: ExtensionCompanionConfig,
) -> dict[str, Any]:
    if kind not in {"structure", "write"}:
        raise ValueError(f"Unsupported extension companion event kind: {kind}")

    tool_result: dict[str, Any] | None = None
    tool_skip_reason: str | None = None
    tool_session_id = _resolve_tool_session_id(config)
    if kind == "write" and tool_session_id and _write_change_count(payload) > 0:
        tool_result = append_capture_payload_to_authoring_session(
            tool_session_id,
            cast(dict[str, object], payload),
            source_label="extension-write-capture",
        )
    elif kind == "write" and tool_session_id:
        tool_skip_reason = "write_without_changes"

    event = {
        "received_at": _utc_now_iso(),
        "kind": kind,
        "app_id": _extract_app_id(payload),
        "version": _extract_version(payload),
        "endpoint": str(payload.get("endpoint") or "").strip() or None,
        "tool_session_id": tool_session_id,
        "tool_authoring": tool_result,
        "tool_authoring_skip_reason": tool_skip_reason,
        "payload": payload,
    }
    log_path = _event_log_path(config)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


class ExtensionCompanionRequestHandler(BaseHTTPRequestHandler):
    server_version = "BefreeBubbleMCPCompanion/0.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    @property
    def companion_server(self) -> ExtensionCompanionHTTPServer:
        return cast(ExtensionCompanionHTTPServer, self.server)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {CAPTURE_KEY_HEADER}")
        super().end_headers()

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT.value)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        config = self.companion_server.config
        tool_session_id = _resolve_tool_session_id(config)
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "service": "befree-bubble-mcp",
                "component": "chrome-extension-companion",
                "host": _server_host(self.companion_server),
                "port": self.companion_server.server_address[1],
                "capture_key_required": bool(config.capture_key),
                "tool_session_id": tool_session_id,
                "configured_tool_session_id": config.tool_session_id,
            },
        )

    def _authorized(self) -> bool:
        expected = self.companion_server.config.capture_key
        if not expected:
            return True
        return self.headers.get(CAPTURE_KEY_HEADER, "") == expected

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc
        if length <= 0:
            raise ValueError("Request body is required.")
        if length > MAX_REQUEST_BYTES:
            raise ValueError("Request body exceeds maximum accepted size.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Expected JSON object request body.")
        return payload

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/v1/bubble/crawler/ingest", "/v1/bubble/crawler/write-ingest"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self._authorized():
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "capture_key_rejected"})
            return
        try:
            payload = self._read_json_body()
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        if payload.get("_ping") is True:
            self._send_json(HTTPStatus.OK, {"ok": True, "ping": True})
            return
        kind = "write" if path.endswith("/write-ingest") else "structure"
        try:
            event = record_extension_companion_event(kind, payload, self.companion_server.config)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(exc), "error_class": exc.__class__.__name__},
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "kind": kind,
                "event_log": str(_event_log_path(self.companion_server.config)),
                "tool_authoring": event.get("tool_authoring"),
            },
        )


def create_extension_companion_server(config: ExtensionCompanionConfig) -> ExtensionCompanionHTTPServer:
    return ExtensionCompanionHTTPServer((config.host, config.port), config)


def companion_status_payload(server: ExtensionCompanionHTTPServer | None) -> dict[str, Any]:
    if server is None:
        return {"ok": True, "running": False}
    config = server.config
    return {
        "ok": True,
        "running": True,
        "host": _server_host(server),
        "port": server.server_address[1],
        "capture_key_required": bool(config.capture_key),
        "tool_session_id": _resolve_tool_session_id(config),
        "configured_tool_session_id": config.tool_session_id,
        "event_log": str(_event_log_path(config)),
    }


_background_lock = threading.Lock()
_background_server: ExtensionCompanionHTTPServer | None = None
_background_thread: threading.Thread | None = None


def start_extension_companion_background(config: ExtensionCompanionConfig) -> dict[str, Any]:
    global _background_server, _background_thread
    with _background_lock:
        if _background_server is not None:
            return {**companion_status_payload(_background_server), "already_running": True}
        server = create_extension_companion_server(config)
        thread = threading.Thread(target=server.serve_forever, name="bubble-mcp-extension-companion", daemon=True)
        thread.start()
        _background_server = server
        _background_thread = thread
        return {**companion_status_payload(server), "already_running": False}


def stop_extension_companion_background() -> dict[str, Any]:
    global _background_server, _background_thread
    with _background_lock:
        server = _background_server
        thread = _background_thread
        if server is None:
            return {"ok": True, "running": False, "stopped": False}
        _background_server = None
        _background_thread = None
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=2)
    return {"ok": True, "running": False, "stopped": True}


def extension_companion_background_status() -> dict[str, Any]:
    with _background_lock:
        return companion_status_payload(_background_server)


def serve_extension_companion(config: ExtensionCompanionConfig) -> int:
    server = create_extension_companion_server(config)
    print(
        f"Befree Bubble MCP Chrome extension companion listening on "
        f"http://{_server_host(server)}:{server.server_address[1]}",
        file=sys.stderr,
    )
    print(f"Event log: {_event_log_path(config)}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
