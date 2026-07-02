"""Bubble editor path API client used by standalone context detection."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from bubble_mcp.execution.client import build_editor_write_headers
from bubble_mcp.sessions.store import BubbleSessionData


BUBBLE_BASE_URL = "https://bubble.io"
PATH_TOKEN_MAP = {
    "%p1": "pages",
    "%p2": "pages",
    "%p3": "pages",
    "%el": "elements",
    "%ed": "element_definitions",
    "%wf": "workflows",
    "%cd": "CustomDefinition",
}


@dataclass(frozen=True)
class PathResult:
    type: str
    data: Any = None
    hash: str = ""
    keys: list[str] | None = None
    message: str = ""


@dataclass(frozen=True)
class MultiPathResponse:
    last_change: int
    results: list[PathResult]


def decode_bubble_path(encoded: str) -> list[str]:
    return [PATH_TOKEN_MAP.get(part, part) for part in str(encoded or "").split(".") if part]


class BubblePathApiClient:
    """Small Python port of Aria's BubblePathAPI."""

    def __init__(
        self,
        *,
        app_id: str,
        app_version: str,
        session: BubbleSessionData,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.app_id = app_id
        self.app_version = app_version
        self.session = session
        self.timeout = timeout
        self.max_retries = max_retries

    def load_multiple_paths(self, path_arrays: list[list[str]]) -> MultiPathResponse:
        url = f"{BUBBLE_BASE_URL}/appeditor/load_multiple_paths/{self.app_id}/{self.app_version}"
        raw = self._request_json("POST", url, {"path_arrays": path_arrays})
        data = raw.get("data") if isinstance(raw, dict) else []
        return MultiPathResponse(
            last_change=int(raw.get("last_change") or 0) if isinstance(raw, dict) else 0,
            results=[self._parse_path_entry(item) for item in data] if isinstance(data, list) else [],
        )

    def load_single_path(self, path_hash: str, *segments: str) -> PathResult:
        suffix = "/".join(parse.quote(str(part), safe="") for part in (path_hash, *segments))
        url = (
            f"{BUBBLE_BASE_URL}/appeditor/load_single_path/"
            f"{self.app_id}/{self.app_version}/{suffix}"
        )
        raw = self._request_json("GET", url)
        return self._parse_path_entry(raw)

    def resolve_path(self, path_array: list[str]) -> PathResult:
        response = self.load_multiple_paths([path_array])
        first = response.results[0] if response.results else PathResult(type="error", message="empty response")
        return self.auto_resolve(first)

    def resolve_multiple(self, path_arrays: list[list[str]]) -> tuple[int, list[PathResult]]:
        response = self.load_multiple_paths(path_arrays)
        return response.last_change, [self.auto_resolve(result) for result in response.results]

    def auto_resolve(self, result: PathResult, *extra_segments: str, max_depth: int = 8) -> PathResult:
        if result.type != "hash":
            return result
        current = result
        try:
            for _depth in range(max_depth):
                resolved = self.load_single_path(current.hash, *extra_segments)
                if resolved.type != "hash":
                    return resolved
                if resolved.hash == current.hash:
                    break
                current = resolved
            return PathResult(type="error", message=f"Unresolved Bubble path hash after {max_depth} hops.")
        except Exception as exc:
            return PathResult(type="error", message=str(exc))

    def get_last_change(self) -> int:
        return self.load_multiple_paths([["_index", "page_name_to_id"]]).last_change

    def get_id_to_path(self) -> dict[str, str]:
        result = self.resolve_path(["_index", "id_to_path"])
        return {str(key): str(value) for key, value in _obj(result.data).items()} if result.type == "data" else {}

    def list_backend_workflow_ids(self) -> list[str]:
        result = self.resolve_path(["api"])
        if result.type == "keys":
            return [str(item) for item in result.keys or []]
        if result.type == "data":
            return list(_obj(result.data).keys())
        return []

    def _request_json(self, method: str, url: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        headers = self._build_headers(method, body or {})
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = request.Request(url, data=data, headers=headers, method=method)
                with request.urlopen(req, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8", errors="replace"))
            except error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise RuntimeError(
                        f"Bubble blocked context API request ({exc.code}). Capture/import session again."
                    ) from exc
                last_error = exc
                if exc.code < 500 or attempt >= self.max_retries:
                    break
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
            time.sleep(0.3 * (attempt + 1))
        raise RuntimeError(f"Bubble context API request failed for {url}: {last_error}")

    def _build_headers(self, method: str, payload: dict[str, Any]) -> dict[str, str]:
        headers = build_editor_write_headers(
            self.session,
            {
                "appname": self.app_id,
                "app_version": self.app_version,
                "changes": [],
                **payload,
            },
        )
        if method.upper() == "GET":
            headers.pop("content-type", None)
            headers.pop("origin", None)
        return headers

    def _parse_path_entry(self, entry: Any) -> PathResult:
        if not isinstance(entry, dict):
            return PathResult(type="data", data=entry)
        if isinstance(entry.get("path_version_hash"), str):
            return PathResult(type="hash", hash=str(entry["path_version_hash"]))
        if isinstance(entry.get("keys"), list):
            return PathResult(type="keys", keys=[str(item) for item in entry["keys"]])
        if "data" in entry:
            return PathResult(type="data", data=entry.get("data"))
        return PathResult(type="data", data=entry)


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
