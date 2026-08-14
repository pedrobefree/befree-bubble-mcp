from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime import context_reference_resolver as resolver_module
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

    def list_styles(self) -> list[dict[str, Any]]:
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
        self.workflow_rows: list[dict[str, Any]] = []
        self.style_rows: list[dict[str, Any]] = []
        self.parent_matches: dict[str, dict[str, Any]] = {}
        self.cached_aliases: dict[str, dict[str, Any]] = {}
        self.id_path_aliases: dict[str, dict[str, Any]] = {}
        self.workflow_matches: dict[str, dict[str, Any]] = {}
        self.style_matches: dict[str, str] = {}
        self.data_type_matches: dict[tuple[str, str], str] = {}
        self.user_types: dict[str, dict[str, Any]] = {}
        self.option_set_matches: dict[str, str] = {}
        self.option_sets: dict[str, dict[str, Any]] = {}
        self.option_value_matches: dict[tuple[str, str], str] = {}
        self.option_values: dict[str, dict[str, dict[str, Any]]] = {}

        def list_elements(_context_id: str, context_type: str) -> list[dict[str, Any]]:
            return [row for row in self.discovery_rows if row.get("context_type") == context_type]

        self.discovery.list_elements = list_elements  # type: ignore[method-assign]
        self.discovery.list_styles = lambda: self.style_rows  # type: ignore[method-assign]

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

    def _list_context_workflows(self, _context_id: str, _context_type: str) -> list[dict[str, Any]]:
        return self.workflow_rows

    def _resolve_parent_element(
        self,
        _context_id: str,
        _context_type: str,
        _context_name: str,
        parent_ref: str,
    ) -> dict[str, Any] | None:
        return self.parent_matches.get(parent_ref)

    def _resolve_element_alias_from_id_to_path(
        self,
        _context_id: str,
        _context_type: str,
        element_ref: str,
    ) -> dict[str, Any] | None:
        return self.id_path_aliases.get(element_ref)

    def _resolve_cached_element_alias(
        self,
        _context_id: str,
        _context_type: str,
        element_ref: str,
    ) -> dict[str, Any] | None:
        return self.cached_aliases.get(element_ref)

    def _resolve_workflow_ref(
        self,
        _context_id: str,
        _context_type: str,
        event_ref: str,
        ref_kind: str = "auto",
    ) -> dict[str, Any] | None:
        return self.workflow_matches.get(f"{ref_kind}:{event_ref}")

    def find_style_id(self, style_ref: str, element_type: str | None = None) -> str | None:
        return self.style_matches.get(f"{element_type or ''}:{style_ref}")

    def _resolve_data_type_key(self, data_type_ref: str, ref_kind: str = "key") -> str | None:
        return self.data_type_matches.get((ref_kind, data_type_ref))

    def _get_user_types(self, include_cache: bool = True) -> dict[str, dict[str, Any]]:
        return self.user_types

    def _resolve_option_set_key(self, option_set_ref: str, ref_kind: str = "auto") -> str | None:
        return self.option_set_matches.get(f"{ref_kind}:{option_set_ref}")

    def _get_option_sets(self, include_cache: bool = True) -> dict[str, dict[str, Any]]:
        return self.option_sets

    def _resolve_option_value_key(
        self,
        option_set_key: str,
        value_ref: str,
        ref_kind: str = "key",
    ) -> str | None:
        return self.option_value_matches.get((option_set_key, value_ref))

    def _get_option_set_values(self, option_set_key: str) -> dict[str, dict[str, Any]]:
        return self.option_values.get(option_set_key, {})

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


def test_sync_element_ref_cache_isolates_deep_and_hybrid_rows_and_persists_valid_siblings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "app.json"
    app_path.write_text("{}", encoding="utf-8")
    cache_path = tmp_path / ".bubble_cli_cache.json"
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(cache_path))
    cli = BubbleCLI(app_json_path=str(app_path), profile_name="resolver-capture-recursion")
    deep_path = "[" * 1100 + '"nested"' + "]" * 1100
    capture_path = tmp_path / "page_payloads.json"
    capture_path.write_text(
        json.dumps(
            [
                {"path": ["%p3", "pg", "%el", "hero", "%nm"], "body": "Hero"},
                {"path": deep_path, "body": "Deep"},
                {
                    "path": [
                        "%p3",
                        "pg",
                        "unexpected",
                        "value",
                        "%el",
                        "bogus",
                        "%nm",
                    ],
                    "body": "Bogus",
                },
                {
                    "path": ["%p3", "pg", "%el", "save"],
                    "intent": {"name": "CreateElement"},
                    "body": {"%dn": "Save"},
                },
            ]
        ),
        encoding="utf-8",
    )
    real_parse_path_array = cli._parse_path_array

    def parse_path_array_with_platform_independent_recursion(raw_path: Any) -> list[str]:
        if raw_path == deep_path:
            raise RecursionError("deep JSON array")
        return real_parse_path_array(raw_path)

    monkeypatch.setattr(cli, "_parse_path_array", parse_path_array_with_platform_independent_recursion)

    assert cli.sync_element_ref_cache(str(capture_path), quiet=True) is True
    reloaded = BubbleCLI(
        app_json_path=str(app_path),
        profile_name="resolver-capture-recursion",
    )
    assert reloaded._lookup_cached_element_ref_alias("pg", "page", "Hero") == "hero"
    assert reloaded._lookup_cached_element_ref_alias("pg", "page", "Save") == "save"
    assert reloaded._lookup_cached_element_ref_alias("pg", "page", "Bogus") is None


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


def test_inspect_context_json_preserves_details_truncation_styles_and_workflows(
    capsys: pytest.CaptureFixture[str],
) -> None:
    host = _TraversalHost({"pages": {"pg_home": {"name": "Home"}}})
    host.context_matches["Homepage"] = ("pg_home", "page")
    host.discovery_rows = [
        {
            "context_type": "page",
            "path": ["%el", "alpha"],
            "id": "alpha-id",
            "key": "alpha",
            "element": {"id": "alpha-id", "%nm": "Alpha", "%x": "Text", "%s1": "style-z"},
        },
        {
            "context_type": "page",
            "path": ["%el", "beta"],
            "id": "beta-id",
            "key": "beta",
            "element": {"id": "beta-id", "%nm": "Beta", "%x": "Button", "%s1": "style-a"},
        },
    ]
    host.workflow_rows = [
        {
            "key": "wf-click",
            "id": "event-click",
            "type": "ButtonClicked",
            "name": "Click alpha",
            "workflow": {"%p": {"%ei": "alpha-id"}},
        },
        {
            "key": "wf-load",
            "id": "event-load",
            "workflow": {"%x": "PageLoaded", "properties": {"element_id": "beta-id"}},
        },
    ]
    host.style_rows = [
        {"id": "style-a", "name": "Primary button"},
        {"id": "style-z", "name": "Body copy"},
    ]
    resolver = ContextReferenceResolver(host)

    assert resolver.inspect_context(
        "Homepage",
        include_elements=True,
        include_workflows=True,
        include_styles=True,
        limit=1,
        as_json=True,
    ) is True
    assert capsys.readouterr().out == json.dumps(
        {
            "context": {"id": "pg_home", "type": "page", "name": "Home"},
            "counts": {"elements": 2, "workflows": 2, "styles_used": 2},
            "elements": [
                {
                    "id": "alpha-id",
                    "key": "alpha",
                    "name": "Alpha",
                    "type": "Text",
                    "style_id": "style-z",
                    "path": ["%el", "alpha"],
                }
            ],
            "elements_truncated": True,
            "workflows": [
                {
                    "key": "wf-click",
                    "id": "event-click",
                    "type": "ButtonClicked",
                    "name": "Click alpha",
                    "element_id": "alpha-id",
                }
            ],
            "workflows_truncated": True,
            "styles_used": [{"id": "style-a", "name": "Primary button"}],
            "styles_used_truncated": True,
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def test_inspect_context_listing_preserves_counts_and_human_log_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _TraversalHost({"pages": {"pg_home": {"name": "Home"}}})
    host.discovery_rows = [
        {
            "context_type": "page",
            "path": ["%el", "hero"],
            "id": "hero-id",
            "key": "hero",
            "element": {"id": "hero-id", "%nm": "Hero", "%x": "Text", "%s1": "style-body"},
        }
    ]
    host.workflow_rows = [{"key": "wf-load", "id": "event-load"}]
    messages: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "log", messages.append)
    resolver = ContextReferenceResolver(host)

    assert resolver.inspect_context(
        scope="page",
        include_elements=True,
        include_workflows=True,
        include_styles=True,
    ) is True
    assert messages == [
        "Contexts (1):",
        "- Home [page] id=pg_home (elements=1, workflows=1, styles=1)",
    ]


def test_resolve_refs_json_keeps_mixed_results_and_clamps_match_index(
    capsys: pytest.CaptureFixture[str],
) -> None:
    host = _TraversalHost(
        {
            "pages": {"pg_home": {"name": "Home"}},
            "styles": {"style-primary": {"%d": "Primary", "%x": "Button"}},
        }
    )
    host.context_matches["Homepage"] = ("pg_home", "page")
    host.parent_matches["Shell"] = {"id": "shell-id", "path": ["%el", "shell"]}
    host.discovery_rows = [
        {
            "context_type": "page",
            "path": ["%el", "first"],
            "id": "first-id",
            "key": "first",
            "element": {"id": "first-id", "%nm": "Hero", "%x": "Text"},
        },
        {
            "context_type": "page",
            "path": ["%el", "second"],
            "id": "second-id",
            "key": "second",
            "element": {"id": "second-id", "%nm": "Hero", "%x": "Group"},
        },
    ]
    host.workflow_matches["name:Submit"] = {
        "key": "wf-submit",
        "id": "event-submit",
        "type": "ButtonClicked",
        "name": "Submit",
        "workflow": {"%p": {"%ei": "first-id"}},
    }
    host.style_matches["Button:Primary"] = "style-primary"
    host.option_set_matches["label:Status"] = "status-key"
    host.option_sets["status-key"] = {"%d": "Status"}
    host.option_value_matches[("status-key", "active")] = "active-key"
    host.option_values["status-key"] = {
        "active-key": {"db_value": "active", "%d": "Active"}
    }
    resolver = ContextReferenceResolver(host)

    assert resolver.resolve_refs(
        context_name="Homepage",
        parent_ref="Shell",
        element_ref="Hero",
        element_ref_kind="name",
        match_index=0,
        event_ref="Submit",
        event_ref_kind="name",
        style_ref="Primary",
        style_element_type="Button",
        data_type_ref="Missing thing",
        option_set_ref="Status",
        option_set_ref_kind="label",
        option_value_ref="active",
        as_json=True,
    ) is True
    assert capsys.readouterr().out == json.dumps(
        {
            "context": {"name": "Homepage", "id": "pg_home", "type": "page"},
            "parent": {"ref": "Shell", "id": "shell-id", "path": ["%el", "shell"]},
            "element": {
                "ref": "Hero",
                "id": "first-id",
                "key": "first",
                "name": "Hero",
                "type": "Text",
                "path": ["%el", "first"],
            },
            "event": {
                "ref": "Submit",
                "key": "wf-submit",
                "id": "event-submit",
                "type": "ButtonClicked",
                "name": "Submit",
                "element_id": "first-id",
            },
            "style": {
                "ref": "Primary",
                "id": "style-primary",
                "name": "Primary",
                "type": "Button",
            },
            "option_set": {"ref": "Status", "key": "status-key", "display": "Status"},
            "option_value": {
                "ref": "active",
                "key": "active-key",
                "db_value": "active",
                "display": "Active",
            },
            "ok": False,
            "errors": ["Data type 'Missing thing' not found."],
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def test_resolve_refs_human_mode_reports_required_context_errors_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _TraversalHost({})
    errors: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "error", errors.append)
    resolver = ContextReferenceResolver(host)

    assert resolver.resolve_refs(
        parent_ref="Shell",
        element_ref="Hero",
        event_ref="Submit",
        option_value_ref="active",
    ) is False
    assert errors == [
        "parent_ref requires a resolvable context.",
        "element_ref requires a resolvable context.",
        "event_ref requires a resolvable context.",
        "option_value_ref requires a resolvable option_set_ref.",
    ]


def test_bubble_cli_inspection_and_resolution_facades_preserve_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "app.json"
    app_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / ".bubble_cli_cache.json"))
    cli = BubbleCLI(app_json_path=str(app_path), profile_name="resolver-orchestration-facade")
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def inspect(*args: Any, **kwargs: Any) -> bool:
        calls.append(("inspect", args, kwargs))
        return False

    def resolve(*args: Any, **kwargs: Any) -> bool:
        calls.append(("resolve", args, kwargs))
        return True

    monkeypatch.setattr(cli._context_reference_resolver, "inspect_context", inspect, raising=False)
    monkeypatch.setattr(cli._context_reference_resolver, "resolve_refs", resolve, raising=False)

    assert cli.inspect_context("Homepage", "page", True, True, True, 7, True) is False
    assert cli.resolve_refs(
        context_name="Homepage",
        parent_ref="Shell",
        parent_match_index=2,
        element_ref="Hero",
        element_ref_kind="name",
        match_index=3,
        event_ref="Submit",
        event_ref_kind="id",
        style_ref="Primary",
        style_element_type="Button",
        data_type_ref="Thing",
        data_type_ref_kind="label",
        option_set_ref="Status",
        option_set_ref_kind="key",
        option_value_ref="active",
        as_json=True,
    ) is True
    assert calls == [
        (
            "inspect",
            ("Homepage", "page", True, True, True, 7, True),
            {},
        ),
        (
            "resolve",
            (),
            {
                "context_name": "Homepage",
                "parent_ref": "Shell",
                "parent_match_index": 2,
                "element_ref": "Hero",
                "element_ref_kind": "name",
                "match_index": 3,
                "event_ref": "Submit",
                "event_ref_kind": "id",
                "style_ref": "Primary",
                "style_element_type": "Button",
                "data_type_ref": "Thing",
                "data_type_ref_kind": "label",
                "option_set_ref": "Status",
                "option_set_ref_kind": "key",
                "option_value_ref": "active",
                "as_json": True,
            },
        ),
    ]


def test_materialization_defensively_handles_missing_roots_and_updates_existing_raw_leaf() -> None:
    invalid_host, invalid_resolver = _resolver({})
    invalid_host.discovery.data = None  # type: ignore[assignment]
    invalid_host.discovery._get_context_root = lambda *_args: None  # type: ignore[method-assign]
    payload = {"id": "hero-id", "key": "hero", "path": ["%el", "hero"]}
    assert invalid_resolver.materialize_cached_element_stub("pg", "page", None) is None
    assert invalid_resolver.materialize_cached_element_stub("pg", "page", payload) is payload

    host, resolver = _resolver(
        {
            "%p3": {
                "pg": {
                    "%x": "Page",
                    "%el": {"hero": {"id": "old-id", "%x": "Text", "%el": None}},
                }
            }
        }
    )
    result = resolver.materialize_cached_element_stub(
        "pg",
        "page",
        {"id": "hero-id", "key": "hero", "name": "Hero", "path": ["%el", "hero"]},
    )
    assert result is not None
    assert result["element"]["id"] == "hero-id"
    assert result["element"]["default_name"] == "Hero"
    assert result["element"]["name"] == "Hero"

    nested = resolver.materialize_cached_element_stub(
        "pg",
        "page",
        {"key": "copy", "path": ["%el", "hero", "%el", "copy"]},
    )
    assert nested is not None
    assert nested["element"]["id"] == "copy"
    assert host.discovery.data["%p3"]["pg"]["%el"]["hero"]["%el"]["copy"]["name"] == "copy"


def test_capture_helpers_cover_empty_unknown_and_reusable_paths() -> None:
    _, resolver = _resolver({})
    assert resolver.normalize_capture_path([]) == []
    assert resolver.normalize_capture_path("[not-json") == []
    assert resolver._context_type_from_prefix("pages") == "page"
    assert resolver._context_type_from_prefix("%ed") == "reusable"
    assert resolver._context_type_from_prefix("unknown") is None
    assert resolver._find_last_element_token(["%p3", "pg"]) == (None, None)
    assert resolver._find_last_element_token(["%el", "parent", "%el", "child"]) == (3, "child")


def test_sync_element_ref_cache_reports_file_errors_and_supports_json_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, resolver = _resolver(
        {
            "element_definitions": {
                "nav": {
                    "elements": {
                        "group": {
                            "elements": {"save": {"default_name": "Saved node"}}
                        }
                    }
                }
            }
        }
    )
    errors: list[str] = []
    logs: list[str] = []
    infos: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "error", errors.append)
    monkeypatch.setattr(resolver_module.logger, "log", logs.append)
    monkeypatch.setattr(resolver_module.logger, "info", infos.append)

    assert resolver.sync_element_ref_cache(str(tmp_path / "missing.json")) is False
    assert errors[-1].startswith("Capture file not found:")
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    assert resolver.sync_element_ref_cache(str(invalid_json)) is False
    assert errors[-1].startswith("Could not read capture file:")
    object_json = tmp_path / "object.json"
    object_json.write_text("{}", encoding="utf-8")
    assert resolver.sync_element_ref_cache(str(object_json)) is False
    assert errors[-1] == "Capture file must be a JSON array."

    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            [
                None,
                {"path": None, "body": "ignored"},
                {"path": ["%p3", "", "%el", "bad"], "intent": "CreateElement", "body": {}},
                {"path": ["unknown", "ctx", "%el", "bad", "%nm"], "body": "Unknown"},
                {"path": ["%ed", "nav", "%el", "group", "%el", "save"]},
                {
                    "path": ["%ed", "nav", "%el", "group", "%el", "save"],
                    "intent": "CreateElement",
                    "body": {"name": "Explicit"},
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    host._collect_alias_ids_for_element_path = lambda *_args: ["save", "save-alias"]  # type: ignore[method-assign]
    assert resolver.sync_element_ref_cache("capture.json", as_json=True, dry_run=True) is True
    rows = json.loads(logs[-1])
    assert rows == [
        {"context_type": "reusable", "context_id": "nav", "name": "Explicit", "id": "save"},
        {"context_type": "reusable", "context_id": "nav", "name": "Explicit", "id": "save-alias"},
        {"context_type": "reusable", "context_id": "nav", "name": "Saved node", "id": "save"},
        {"context_type": "reusable", "context_id": "nav", "name": "Saved node", "id": "save-alias"},
    ]
    assert host._alias_registry.lookup_element_id("nav", "reusable", "Explicit") is None
    assert resolver.sync_element_ref_cache("capture.json", dry_run=True) is True
    assert infos[-1].startswith("[DRY RUN] Imported 4 element alias mappings")


def test_iter_contexts_skips_malformed_duplicates_and_raw_reusable_pages() -> None:
    host = _TraversalHost(
        {
            "pages": {
                "bad": None,
                "same": {"name": "Readable"},
            },
            "%p3": {
                "bad-raw": None,
                "same": {"%nm": "Raw duplicate"},
                "reusable-in-pages": {"%x": "ReusableElement", "%nm": "Skip me"},
                "raw": {"name": "Raw page"},
            },
            "element_definitions": "malformed",
            "%ed": {"raw-reusable": {"name": "Raw reusable"}},
        }
    )
    host.module_indexes["page"] = {"same": "Module duplicate", "module": ""}
    host.cached_contexts = {  # type: ignore[assignment]
        "page": "malformed",
        "reusable": {
            "bad": None,
            "empty": {"context_id": ""},
            "duplicate": {"context_id": "raw-reusable", "name": "Duplicate"},
            "cached": {"context_id": "cached", "name": "Cached"},
        },
    }
    resolver = ContextReferenceResolver(host)

    assert resolver.iter_contexts("all") == [
        {"id": "module", "type": "page", "name": "module"},
        {"id": "raw", "type": "page", "name": "Raw page"},
        {"id": "same", "type": "page", "name": "Readable"},
        {"id": "cached", "type": "reusable", "name": "Cached"},
        {"id": "raw-reusable", "type": "reusable", "name": "Raw reusable"},
    ]
    host.discovery.data = None  # type: ignore[assignment]
    host.cached_contexts = {}  # type: ignore[assignment]
    assert resolver.iter_contexts("unknown") == []


@pytest.mark.parametrize(
    ("element", "ref", "kind", "key", "score"),
    [
        (None, "x", "auto", None, -1),
        ({"id": "id"}, "id", "id", None, 400),
        ({"id": "id"}, "other", "id", "other", 400),
        ({}, "key", "key", "key", 390),
        ({"name": "Save button"}, "save", "name", None, 200),
        ({"properties": {"text": "Welcome home"}}, "welcome home", "text", None, 280),
        ({"properties": {"%3": "Welcome home"}}, "welcome", "text", None, 180),
        ({"default_name": "Exact"}, "exact", "auto", None, 300),
        ({"properties": {"text": "Exact text"}}, "exact text", "auto", None, 280),
        ({"name": "Partial name"}, "partial", "auto", None, 200),
        ({"properties": {"text": "Partial text"}}, "partial", "auto", None, 180),
        ({"name": "Nope"}, "missing", "weird", None, -1),
    ],
)
def test_match_scoring_covers_supported_kinds_and_payload_shapes(
    element: Any,
    ref: str,
    kind: str,
    key: str | None,
    score: int,
) -> None:
    resolver = ContextReferenceResolver(_TraversalHost({}))
    assert resolver._score_raw_element_match(element, ref, kind, key) == score
    assert resolver._match_raw_element(element, ref, kind, key) is (score >= 0)


@pytest.mark.parametrize(
    ("element", "expected"),
    [
        ({"%p": {"%3": "Raw text"}}, "Raw text"),
        ({"properties": {"text": "Readable text"}}, "Readable text"),
        ({"properties": {"%3": {"%e": {"0": "Rich", "1": " text"}}}}, {"%e": {"0": "Rich", "1": " text"}}),
        ({"properties": {}}, None),
        ({"properties": "malformed"}, None),
        (None, None),
    ],
)
def test_extract_element_text_payload_returns_literal_mapping_variants(
    element: Any,
    expected: Any,
) -> None:
    assert ContextReferenceResolver._extract_element_text_payload(element) == expected


def test_find_elements_defensively_skips_malformed_sources_and_covers_index_routes() -> None:
    host = _TraversalHost({})
    host.raw_rows = [
        None,
        {"path": ["%el", "duplicate"], "id": "same", "element": {"id": "same", "name": "Same"}},
        {"path": ["%el", "duplicate"], "id": "same", "element": {"id": "same", "name": "Same"}},
        {"path": [], "id": "pathless", "key": "pathless-key", "element": {"id": "pathless", "name": "Pathless"}},
    ]  # type: ignore[list-item]
    host.module_rows = [{"id": "no-match", "element": {"name": "Other"}}]
    host.index_rows = [
        None,
        {"id": "alias-id", "key": "alias-key", "element": {}},
        {"id": "named-id", "key": "named-key", "element": {"name": "Named"}},
    ]  # type: ignore[list-item]
    resolver = ContextReferenceResolver(host)

    assert [row["id"] for row in resolver.find_elements_by_ref("pg", "page", "same", "auto")] == ["same"]
    assert [row["id"] for row in resolver.find_elements_by_ref("pg", "page", "pathless-key", "key")] == ["pathless"]
    assert [row["id"] for row in resolver.find_elements_by_ref("pg", "page", "alias-id", "id")] == ["alias-id"]
    assert [row["id"] for row in resolver.find_elements_by_ref("pg", "page", "alias-key", "key")] == ["alias-id"]
    assert [row["id"] for row in resolver.find_elements_by_ref("pg", "page", "Named", "name")] == ["named-id"]
    assert [row["id"] for row in resolver.find_elements_by_ref("pg", "page", "alias-key", "unexpected")] == ["alias-id"]
    assert resolver.find_element_by_ref("pg", "page", "missing") is None


def test_find_elements_consumes_real_index_aliases_and_upgrades_duplicate_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "pages": {
                    "pg": {
                        "id": "pg",
                        "name": "Home",
                        "elements": {
                            "target-key": {
                                "id": "target-id",
                                "name": "index-alias",
                            },
                            "index-alias": {
                                "id": "key-candidate",
                                "name": "Other candidate",
                            },
                        },
                    }
                },
                "_index": {
                    "id_to_path": {
                        "index-alias": "%p3.pg.%el.target-key",
                        "direct-id-alias": "%p3.pg.%el.target-key",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / ".bubble_cli_cache.json"))
    cli = BubbleCLI(app_json_path=str(app_path), profile_name="resolver-index-contract")

    assert [
        (row["id"], row["alias_id"])
        for row in cli._list_index_context_elements("pg", "page")
    ] == [
        ("target-id", "index-alias"),
        ("target-id", "direct-id-alias"),
    ]
    assert [
        row["id"]
        for row in cli._find_elements_by_ref("pg", "page", "index-alias", "auto")
    ] == ["target-id", "key-candidate"]
    assert [
        row["id"]
        for row in cli._find_elements_by_ref("pg", "page", "direct-id-alias", "id")
    ] == ["target-id"]
    assert [
        row["id"]
        for row in cli._find_elements_by_ref("pg", "page", "target-id", "id")
    ] == ["target-id"]


def test_select_element_match_reports_missing_ambiguous_and_out_of_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _TraversalHost({})
    resolver = ContextReferenceResolver(host)
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "error", errors.append)
    monkeypatch.setattr(resolver_module.logger, "warning", warnings.append)
    monkeypatch.setattr(resolver_module.logger, "info", infos.append)
    assert resolver.select_element_match("Missing", "Hero") == (None, None, None)

    host.context_matches["Home"] = ("pg", None)
    assert resolver.select_element_match("Home", "Missing", "id") == (None, None, None)
    host.discovery_rows = [
        {"context_type": "page", "id": "one", "path": ["%el", "one"], "element": {"name": "Hero"}},
        {"context_type": "page", "id": "two", "path": ["%el", "two"], "element": {"name": "Hero copy"}},
    ]
    assert resolver.select_element_match("Home", "Hero", "name", match_index=5) == (None, None, None)
    assert warnings == [
        "Multiple matches found (2) for 'Hero' in 'Home'. Using match #5. Use --match-index or --ref-kind id/key to target explicitly."
    ]
    assert len(infos) == 2
    assert errors[-1] == "match-index 5 out of range; found 2 matches."
    assert resolver.select_element_match("Home", "Hero", "name")[-1]["id"] == "two"  # type: ignore[index]


def test_collect_context_elements_skips_invalid_rows_and_prefers_richer_duplicate() -> None:
    host = _TraversalHost({})
    host.raw_rows = [
        None,
        {"id": "", "path": [], "element": {}},
        {"id": "bad", "path": ["%el", "[truncated_max_depth]"], "element": {"id": "bad"}},
        {"id": "abc", "key": "hero", "path": ["%el", "hero"], "element": {"id": "abc", "name": "abc", "type": "Unknown"}},
    ]  # type: ignore[list-item]
    host.module_rows = [
        {"id": "abc", "key": "hero", "path": ["%el", "hero"], "element": {"id": "abc", "name": "Hero banner", "type": "Group", "%s1": "style"}},
        {"id": "readable-id", "key": "copy", "path": [], "element": {"id": "readable-id", "default_name": "Copy", "type": "Text"}},
    ]
    rows = ContextReferenceResolver(host).collect_context_elements("pg", "page")
    assert rows == [
        {"id": "readable-id", "key": "copy", "name": "Copy", "type": "Text", "style_id": None, "path": []},
        {"id": "abc", "key": "hero", "name": "Hero banner", "type": "Group", "style_id": "style", "path": ["%el", "hero"]},
    ]


def test_inspect_context_covers_missing_and_human_detail_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _TraversalHost({"pages": {"pg": {"name": "Home"}}})
    resolver = ContextReferenceResolver(host)
    errors: list[str] = []
    messages: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "error", errors.append)
    monkeypatch.setattr(resolver_module.logger, "log", messages.append)
    assert resolver.inspect_context("Missing") is False
    assert errors == ["Context 'Missing' not found."]

    host.context_matches["Home"] = ("pg", "page")
    host.discovery_rows = [
        {"context_type": "page", "path": ["%el", "unknown"], "element": {"name": "", "type": "", "id": "opaque"}},
    ]
    host.workflow_rows = [
        {"key": "wf", "id": "event", "workflow": {"%x": "Loaded", "properties": "bad"}},
    ]
    assert resolver.inspect_context(
        "Home", include_elements=True, include_workflows=True, include_styles=True, limit=0
    ) is True
    assert messages == [
        "Context: Home (page, pg)",
        "Counts: elements=1 workflows=1",
        "Styles used: 0",
        "Elements (showing up to 1):",
        "  - <unnamed> [unknown] id=opaque",
        "Workflows (showing up to 1):",
        "  - key=wf id=event type=Loaded element=-",
    ]


def test_inspect_context_listing_json_without_optional_counts(capsys: pytest.CaptureFixture[str]) -> None:
    host = _TraversalHost({"pages": {"pg": {}}})
    resolver = ContextReferenceResolver(host)
    assert resolver.inspect_context(scope="page", as_json=True) is True
    assert json.loads(capsys.readouterr().out) == [{"id": "pg", "type": "page", "name": "pg"}]


def test_resolve_refs_covers_fallback_successes_and_human_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _TraversalHost({"pages": {"pg": {}}, "styles": {"style": "malformed"}})
    host.context_matches["Home"] = ("pg", None)
    host.id_path_aliases["element-id"] = {
        "id": "element-id",
        "path": ["%el", "element-key"],
        "element": {"default_name": "Fallback", "type": "Group"},
    }
    host.cached_aliases["cached"] = {
        "id": "cached-id",
        "key": "cached-key",
        "path": [],
        "element": "malformed",
    }
    host.workflow_matches["auto:Load"] = {
        "key": "wf",
        "id": "event",
        "workflow": {"type": "Loaded", "properties": {"element_id": "element-id"}},
    }
    host.style_matches[":Style"] = "style"
    host.data_type_matches[("label", "Thing")] = "thing"
    host.user_types["thing"] = {"%d": "Thing label"}
    host.option_set_matches["auto:Status"] = "status"
    host.option_sets["status"] = {"display": "Status display"}
    host.option_value_matches[("status", "active")] = "active"
    host.option_values["status"] = {"active": {"display": "Active display"}}
    resolver = ContextReferenceResolver(host)
    messages: list[str] = []
    errors: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "log", messages.append)
    monkeypatch.setattr(resolver_module.logger, "error", errors.append)

    assert resolver.resolve_refs(
        context_name="Home",
        element_ref="element-id",
        element_ref_kind="id",
        event_ref="Load",
        style_ref="Style",
        data_type_ref="Thing",
        data_type_ref_kind="display",
        option_set_ref="Status",
        option_set_ref_kind="unsupported",
        option_value_ref="active",
    ) is True
    assert errors == []
    assert messages[0] == "Context: Home -> None:pg"
    assert [message.split(":", 1)[0] for message in messages[1:]] == [
        "element", "event", "style", "data_type", "option_set", "option_value"
    ]

    messages.clear()
    assert resolver.resolve_refs(context_name="Home", element_ref="cached", element_ref_kind="name") is True
    assert '"key": "cached-key"' in messages[-1]


def test_resolve_refs_reports_each_lookup_failure_and_defensive_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _TraversalHost({})
    host.context_matches["Home"] = ("pg", "page")
    host.data_type_matches[("key", "Thing")] = "thing"
    host.user_types["thing"] = None  # type: ignore[assignment]
    host.option_set_matches["key:Status"] = "status"
    host.option_sets["status"] = None  # type: ignore[assignment]
    host.option_value_matches[("status", "active")] = "active"
    host.option_values["status"] = None  # type: ignore[assignment]
    resolver = ContextReferenceResolver(host)
    errors: list[str] = []
    monkeypatch.setattr(resolver_module.logger, "error", errors.append)

    assert resolver.resolve_refs(
        context_name="Home",
        parent_ref="Missing parent",
        element_ref="Missing element",
        element_ref_kind="name",
        event_ref="Missing event",
        style_ref="Missing style",
        data_type_ref="Thing",
        data_type_ref_kind="key",
        option_set_ref="Status",
        option_set_ref_kind="key",
        option_value_ref="active",
    ) is False
    assert errors == [
        "Parent 'Missing parent' not found.",
        "Element 'Missing element' not found in 'Home' by name.",
        "Workflow 'Missing event' not found in 'Home' by auto.",
        "Style 'Missing style' not found.",
    ]

    errors.clear()
    assert resolver.resolve_refs(
        context_name="Missing",
        data_type_ref="No type",
        option_set_ref="No set",
        option_value_ref="No value",
    ) is False
    assert errors == [
        "Context 'Missing' not found.",
        "Data type 'No type' not found.",
        "Option set 'No set' not found.",
        "option_value_ref requires a resolvable option_set_ref.",
    ]

    host.option_value_matches.clear()
    errors.clear()
    assert resolver.resolve_refs(option_set_ref="Status", option_set_ref_kind="key", option_value_ref="missing") is False
    assert errors == ["Option value 'missing' not found in option set 'status'."]
