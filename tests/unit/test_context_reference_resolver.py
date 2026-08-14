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

    def list_elements(self, context_id: str, context_type: str) -> list[dict[str, Any]]:
        return []


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


class _TraversalHost(_Host):
    """Literal discovery-source fixture for resolver traversal behavior."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        self.discovery_rows: list[dict[str, Any]] = []
        self.raw_rows: list[dict[str, Any]] = []
        self.module_rows: list[dict[str, Any]] = []
        self.index_rows: list[dict[str, Any]] = []
        self.cached_rows: list[dict[str, Any]] = []
        self.module_indexes: dict[str, dict[str, str]] = {"page": {}, "reusable": {}}
        self.cached_contexts: dict[str, dict[str, dict[str, str]]] = {"page": {}, "reusable": {}}
        self.context_matches: dict[str, tuple[str | None, str | None]] = {}

        def list_elements(_context_id: str, context_type: str) -> list[dict[str, Any]]:
            return [row for row in self.discovery_rows if row.get("context_type") == context_type]

        self.discovery.list_elements = list_elements  # type: ignore[method-assign]

    def _list_raw_context_elements(self, _context_id: str, _context_type: str) -> list[dict[str, Any]]:
        return self.raw_rows

    def _list_module_context_elements(self, _context_id: str, _context_type: str) -> list[dict[str, Any]]:
        return self.module_rows

    def _list_index_context_elements(self, _context_id: str, _context_type: str) -> list[dict[str, Any]]:
        return self.index_rows

    def _list_cached_context_elements(self, _context_id: str, _context_type: str) -> list[dict[str, Any]]:
        return self.cached_rows

    def _load_modules_index(self, context_type: str) -> dict[str, str]:
        return self.module_indexes[context_type]

    def _schema_contexts_cache(self) -> dict[str, dict[str, dict[str, str]]]:
        return self.cached_contexts

    def _find_context(self, name: str) -> tuple[str | None, str | None]:
        return self.context_matches.get(name, (None, None))

    @staticmethod
    def _extract_plain_text_value(raw_value: Any) -> str:
        if isinstance(raw_value, str):
            return raw_value
        if isinstance(raw_value, dict):
            entries = raw_value.get("%e") or raw_value.get("entries")
            if isinstance(entries, dict):
                return "".join(str(entries[key]) for key in sorted(entries, key=str))
        return ""


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


def test_iter_contexts_filters_scope_and_keeps_reusable_and_page_name_ambiguity() -> None:
    host = _TraversalHost(
        {
            "pages": {"pg_home": {"name": "Shared"}},
            "%ed": {"reusable_nav": {"%nm": "Shared"}},
        }
    )
    host.module_indexes["page"] = {"pg_module": "Module page"}
    host.cached_contexts["reusable"] = {
        "created": {"context_id": "reusable_cached", "name": "Cached reusable"}
    }
    resolver = ContextReferenceResolver(host)

    assert resolver.iter_contexts("pages") == [
        {"id": "pg_module", "type": "page", "name": "Module page"},
        {"id": "pg_home", "type": "page", "name": "Shared"},
    ]
    assert resolver.iter_contexts("reusable") == [
        {"id": "reusable_cached", "type": "reusable", "name": "Cached reusable"},
        {"id": "reusable_nav", "type": "reusable", "name": "Shared"},
    ]


def test_collect_context_elements_deduplicates_sources_and_keeps_cached_only_row() -> None:
    host = _TraversalHost({"pages": {}})
    shared = {"id": "hero-id", "%nm": "Hero", "%x": "Text"}
    host.discovery_rows = [{"context_type": "page", "path": ["%el", "hero"], "id": "hero-id", "key": "hero", "element": shared}]
    host.raw_rows = [{"path": ["%el", "hero"], "id": "hero-id", "key": "hero", "element": shared}]
    host.module_rows = [{"path": ["%el", "hero"], "id": "hero-id", "key": "hero", "element": {"id": "hero-id", "%nm": "Hero", "%x": "Text"}}]
    host.index_rows = [{"path": ["%el", "hero"], "id": "hero-id", "key": "hero", "element": shared}]
    host.cached_rows = [{"path": ["%el", "cached"], "id": "cached-id", "key": "cached", "element": {"id": "cached-id", "%nm": "Cached", "%x": "Group"}}]
    resolver = ContextReferenceResolver(host)

    assert resolver.collect_context_elements("pg_home", "page") == [
        {"id": "cached-id", "key": "cached", "name": "Cached", "type": "Group", "style_id": None, "path": ["%el", "cached"]},
        {"id": "hero-id", "key": "hero", "name": "Hero", "type": "Text", "style_id": None, "path": ["%el", "hero"]},
    ]


@pytest.mark.parametrize(
    ("element_ref", "ref_kind", "expected_ids"),
    [
        ("save-key", "key", ["save-id"]),
        ("text-id", "id", ["text-id"]),
        ("Save button", "name", ["save-id"]),
        ("welcome home", "text", ["text-id"]),
    ],
)
def test_find_elements_by_ref_matches_key_id_name_and_text(
    element_ref: str,
    ref_kind: str,
    expected_ids: list[str],
) -> None:
    host = _TraversalHost({"pages": {}})
    host.discovery_rows = [
        {"context_type": "page", "path": ["%el", "save-key"], "id": "save-id", "key": "save-key", "element": {"id": "save-id", "%nm": "Save button", "%x": "Button"}},
        {"context_type": "page", "path": ["%el", "copy"], "id": "text-id", "key": "copy", "element": {"id": "text-id", "%x": "Text", "%p": {"%3": "Welcome home"}}},
    ]
    resolver = ContextReferenceResolver(host)

    assert [row["id"] for row in resolver.find_elements_by_ref("pg_home", "page", element_ref, ref_kind)] == expected_ids


def test_find_elements_by_ref_ranks_exact_name_before_partial_and_selects_one_based_match() -> None:
    host = _TraversalHost({"pages": {}})
    host.context_matches["Shared"] = ("reusable_shared", "reusable")
    host.discovery_rows = [
        {"context_type": "reusable", "path": ["%el", "partial"], "id": "partial-id", "key": "partial", "element": {"id": "partial-id", "%nm": "Primary action"}},
        {"context_type": "reusable", "path": ["%el", "exact"], "id": "exact-id", "key": "exact", "element": {"id": "exact-id", "%nm": "Primary"}},
    ]
    resolver = ContextReferenceResolver(host)

    assert [row["id"] for row in resolver.find_elements_by_ref("reusable_shared", "reusable", "primary", "name")] == ["exact-id", "partial-id"]
    assert resolver.find_element_by_ref("reusable_shared", "reusable", "primary", "name", match_index=2)["id"] == "partial-id"
    assert resolver.find_element_by_ref("reusable_shared", "reusable", "primary", "name", match_index=0)["id"] == "exact-id"
    assert resolver.select_element_match("Shared", "primary", "name", match_index=2) == (
        "reusable_shared",
        "reusable",
        {"context_type": "reusable", "path": ["%el", "partial"], "id": "partial-id", "key": "partial", "element": {"id": "partial-id", "%nm": "Primary action"}},
    )


def test_bubble_cli_traversal_facades_delegate_to_reference_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "app.json"
    app_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / ".bubble_cli_cache.json"))
    cli = BubbleCLI(app_json_path=str(app_path), profile_name="resolver-traversal-facade")
    sentinel = [{"id": "resolver-owned"}]
    selected = {"id": "resolver-selected"}
    monkeypatch.setattr(cli._context_reference_resolver, "find_elements_by_ref", lambda *_args, **_kwargs: sentinel)
    monkeypatch.setattr(cli._context_reference_resolver, "find_element_by_ref", lambda *_args, **_kwargs: selected)
    monkeypatch.setattr(
        cli._context_reference_resolver,
        "select_element_match",
        lambda *_args, **_kwargs: ("pg_home", "page", selected),
    )
    monkeypatch.setattr(cli._context_reference_resolver, "iter_contexts", lambda *_args, **_kwargs: [{"id": "page-owned", "type": "page", "name": "Owned"}])
    monkeypatch.setattr(cli._context_reference_resolver, "collect_context_elements", lambda *_args, **_kwargs: [{"id": "element-owned"}])

    assert cli._find_elements_by_ref("pg_home", "page", "hero") is sentinel
    assert cli._find_element_by_ref("pg_home", "page", "hero", match_index=2) is selected
    assert cli._select_element_match("Home", "hero", match_index=2) == ("pg_home", "page", selected)
    assert cli._iter_contexts("page") == [{"id": "page-owned", "type": "page", "name": "Owned"}]
    assert cli._collect_context_elements("pg_home", "page") == [{"id": "element-owned"}]
