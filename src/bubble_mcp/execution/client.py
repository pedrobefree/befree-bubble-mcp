"""Authenticated Bubble editor write client."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error, request

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.sessions.store import BubbleSessionData


EDITOR_WRITE_URL = "https://bubble.io/appeditor/write"
EDITOR_WRITE_TIMEOUT_SEC = 80.0


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: dict[str, str]


HttpTransport = Callable[[str, bytes, dict[str, str], float], HttpResponse]


def default_http_transport(
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float,
) -> HttpResponse:
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status=int(response.status),
                body=response_body,
                headers={str(key): str(value) for key, value in response.headers.items()},
            )
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        return HttpResponse(
            status=int(exc.code),
            body=response_body,
            headers={str(key): str(value) for key, value in exc.headers.items()},
        )


def normalize_write_payload(payload: dict[str, Any], session: BubbleSessionData) -> dict[str, Any]:
    candidate = payload.get("body") if isinstance(payload.get("body"), dict) else payload
    normalized = json.loads(json.dumps(candidate))
    if not isinstance(normalized, dict):
        raise ValueError("Bubble write payload must be a JSON object.")

    app_id = str(
        normalized.get("appname")
        or payload.get("appname")
        or payload.get("app_id")
        or payload.get("appId")
        or session.app_id
        or ""
    ).strip()
    if not app_id:
        raise ValueError("Bubble write payload is missing appname/app_id.")
    normalized["appname"] = app_id

    if not isinstance(normalized.get("changes"), list):
        raise ValueError("Bubble write payload must include a changes array.")
    if "app_version" not in normalized:
        normalized["app_version"] = session.app_version or "test"
    return normalized


def build_editor_write_headers(session: BubbleSessionData, payload: dict[str, Any]) -> dict[str, str]:
    captured = {str(key).lower(): str(value) for key, value in session.headers.items()}
    cookie = str(session.cookies or captured.get("cookie") or "").strip()
    bubble_request_id = f"{int(time.time() * 1000)}x{random.randint(10, 99)}"
    bubble_fiber_id = f"{int(time.time() * 1000)}x{random.randint(100000000000000000, 999999999999999999)}"
    appname = str(payload.get("appname") or session.app_id or "").strip()

    headers: dict[str, str] = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json",
        "referer": session.url or f"https://bubble.io/page?name={payload.get('appname', '')}",
        "user-agent": captured.get("user-agent") or "befree-bubble-mcp",
        "x-bubble-appname": captured.get("x-bubble-appname") or appname,
        "x-bubble-fiber-id": captured.get("x-bubble-fiber-id") or bubble_fiber_id,
        "x-bubble-pl": captured.get("x-bubble-pl") or bubble_request_id,
        "x-requested-with": captured.get("x-requested-with") or "XMLHttpRequest",
        "x-bubble-platform": captured.get("x-bubble-platform") or "web",
        "x-bubble-breaking-revision": captured.get("x-bubble-breaking-revision") or "5",
    }
    for key in (
        "authorization",
        "x-csrf-token",
        "x-xsrf-token",
        "x-bubble-csrf-token",
        "bubble-csrf-token",
    ):
        if captured.get(key):
            headers[key] = captured[key]
    if cookie:
        headers["cookie"] = cookie
    return {key: value for key, value in headers.items() if str(value).strip()}


def parse_response_body(body: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def has_expected_write_shape(data: Any) -> bool:
    return isinstance(data, dict) and ("last_change" in data or "id_counter" in data)


class BubbleEditorClient:
    """Posts authenticated Bubble editor mutations."""

    def __init__(
        self,
        *,
        transport: HttpTransport = default_http_transport,
        timeout: float = EDITOR_WRITE_TIMEOUT_SEC,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    def write(
        self,
        payload: dict[str, Any],
        session: BubbleSessionData,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_write_payload(payload, session)
        headers = build_editor_write_headers(session, normalized)
        safe_request = {
            "url": EDITOR_WRITE_URL,
            "payload": normalized,
            "headers": redact_sensitive(headers),
        }
        if dry_run:
            return {"ok": True, "dry_run": True, "request": safe_request}

        body = json.dumps(normalized, separators=(",", ":")).encode("utf-8")
        response = self._transport(EDITOR_WRITE_URL, body, headers, self._timeout)
        data = parse_response_body(response.body)

        if response.status in (401, 403):
            return {
                "ok": False,
                "dry_run": False,
                "status": response.status,
                "error": f"Bubble blocked the editor write ({response.status}).",
                "reason": "auth_blocked",
                "response": data,
                "request": safe_request,
            }
        if isinstance(data, str) and data.lstrip().startswith("<"):
            raise RuntimeError("Bubble session expired: received HTML instead of JSON.")

        valid_shape = has_expected_write_shape(data)
        return {
            "ok": 200 <= response.status < 300 and valid_shape,
            "dry_run": False,
            "status": response.status,
            "response": data,
            "valid_shape": valid_shape,
            "request": safe_request,
        }
