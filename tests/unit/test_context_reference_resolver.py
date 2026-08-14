from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.context_alias_registry import ContextAliasRegistry
from bubble_mcp.aria_runtime.context_reference_resolver import ContextReferenceResolver


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_path(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    token_map = {
        "pages": "%p3",
        "element_definitions": "%ed",
        "elements": "%el",
        "properties": "%p",
        "name": "%nm",
        "default_name": "%dn",
    }
    return [token_map.get(str(token), str(token)) for token in value if str(token).strip()]


class _Discovery:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def _get_context_root(self, context_id: str, context_type: str) -> dict[str, Any] | None:
        readable_key = "element_definitions" if context_type == "reusable" else "pages"
        raw_key = "%ed" if context_type == "reusable" else "%p3"
        for key in (readable_key, raw_key):
            bucket = self.data.get(key)
            if isinstance(bucket, dict) and isinstance(bucket.get(context_id), dict):
                return bucket[context_id]
        return None


class _Host:
    def __init__(self, data: dict[str, Any]) -> None:
        self.discovery = _Discovery(data)
        self.cache: dict[str, Any] = {}
        self._alias_registry = ContextAliasRegistry(
            cache=lambda: self.cache,
            profile_key=lambda: "resolver-test",
            normalize=_normalize,
            normalize_path=_normalize_path,
            reload=lambda: None,
            save=lambda: None,
        )

    @staticmethod
    def _normalize_payload_path(path_parts: Any) -> list[str]:
        return _normalize_path(path_parts)

    @staticmethod
    def _parse_path_array(raw_path: Any) -> list[str]:
        if isinstance(raw_path, list):
            parts = [str(part) for part in raw_path if str(part).strip()]
            if not parts:
                raise ValueError("Path cannot be empty.")
            return parts
        path_text = str(raw_path or "").strip()
        if not path_text:
            raise ValueError("Path cannot be empty.")
        if path_text.startswith("["):
            parsed = json.loads(path_text)
            if not isinstance(parsed, list) or not parsed:
                raise ValueError("Path JSON must be a non-empty array.")
            return [str(part) for part in parsed]
        separator = "." if "." in path_text else "/"
        return [part.strip() for part in path_text.split(separator) if part.strip()]

    @staticmethod
    def _norm_lookup(value: Any) -> str:
        return _normalize(value)

    @staticmethod
    def _workflow_prefix(context_type: str) -> str:
        return "%ed" if context_type == "reusable" else "%p3"

    def _get_value_at_path(self, path_parts: list[str]) -> Any:
        node: Any = self.discovery.data
        token_map = {"%p3": "pages", "%ed": "element_definitions", "%el": "elements"}
        for part in path_parts:
            if not isinstance(node, dict):
                return None
            node = node.get(part, node.get(token_map.get(part, "")))
        return node

    @staticmethod
    def _collect_alias_ids_for_element_path(
        context_id: str,
        context_type: str,
        element_path: list[str],
    ) -> list[str]:
        return []


def _resolver(data: dict[str, Any]) -> tuple[_Host, ContextReferenceResolver]:
    host = _Host(data)
    return host, ContextReferenceResolver(host)


def test_materialize_cached_stub_preserves_existing_siblings() -> None:
    host, resolver = _resolver(
        {
            "pages": {
                "pg_home": {
                    "id": "pg_home",
                    "elements": {"existing": {"id": "existing", "name": "Existing"}},
                }
            }
        }
    )

    result = resolver.materialize_cached_element_stub(
        "pg_home",
        "page",
        {"id": "hero_id", "key": "hero", "path": ["%el", "group", "%el", "hero"]},
        alias_name="Hero",
    )

    assert result is not None
    assert result["element"]["id"] == "hero_id"
    elements = host.discovery.data["pages"]["pg_home"]["elements"]
    assert elements["existing"] == {"id": "existing", "name": "Existing"}
    assert elements["group"]["elements"]["hero"]["name"] == "Hero"


@pytest.mark.parametrize(
    ("root_key", "context_type"),
    [("pages", "page"), ("%p3", "page"), ("element_definitions", "reusable"), ("%ed", "reusable")],
)
def test_materialize_cached_stub_supports_readable_and_raw_roots(
    root_key: str,
    context_type: str,
) -> None:
    host, resolver = _resolver({root_key: {}})

    result = resolver.materialize_cached_element_stub(
        "ctx_1",
        context_type,
        {"id": "save_id", "key": "save", "path": ["%el", "save"]},
        alias_name="Save",
    )

    assert result is not None
    assert result["element"]["id"] == "save_id"
    assert host.discovery.data[root_key]["ctx_1"]["elements"]["save"]["name"] == "Save"


@pytest.mark.parametrize(
    "path",
    [None, "pages.pg_home.elements.hero", ["%el"], ["%p3", "pg_home", "%el", "hero"]],
)
def test_materialize_cached_stub_leaves_malformed_paths_unchanged(path: Any) -> None:
    _, resolver = _resolver({"pages": {}})
    payload = {"id": "hero_id", "key": "hero", "path": path}

    assert resolver.materialize_cached_element_stub("pg_home", "page", payload, alias_name="Hero") is payload


def test_sync_element_ref_cache_keeps_valid_mappings_when_capture_rows_are_malformed(tmp_path: Path) -> None:
    host, resolver = _resolver({"pages": {}})
    capture_path = tmp_path / "page_payloads.json"
    capture_path.write_text(
        json.dumps(
            [
                {"path": ["%p3", "pg_home", "%el", "hero", "%nm"], "body": "Hero"},
                {"path": ["%p3", "pg_home", "%el"], "body": "Broken"},
                {"path": "[not json", "body": "Broken JSON"},
                {"path": ["%p3", "pg_home", "%el", "save"], "intent": {"name": "CreateElement"}, "body": {"%dn": "Save"}},
                {"path": ["%p3", "pg_home", "%el", "ignored", "%nm"], "body": 42},
            ]
        ),
        encoding="utf-8",
    )

    assert resolver.sync_element_ref_cache(str(capture_path), quiet=True) is True
    assert host._alias_registry.lookup_element_id("pg_home", "page", "Hero") == "hero"
    assert host._alias_registry.lookup_element_id("pg_home", "page", "Save") == "save"


def test_bubble_cli_facades_delegate_cached_stub_materialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_path = tmp_path / "app.json"
    app_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / ".bubble_cli_cache.json"))
    cli = BubbleCLI(app_json_path=str(app_path), profile_name="resolver-facade")
    cli.discovery._data = {"pages": {"pg_home": {"id": "pg_home", "elements": {}}}}

    result = cli._materialize_cached_element_stub(
        "pg_home",
        "page",
        {"id": "hero_id", "key": "hero", "path": ["%el", "hero"]},
        alias_name="Hero",
    )

    assert result is not None
    assert result["element"]["name"] == "Hero"
    assert cli._normalize_capture_path("pages.pg_home.elements.hero") == ["%p3", "pg_home", "%el", "hero"]
