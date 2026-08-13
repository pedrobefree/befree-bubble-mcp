from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.aria_runtime.context_alias_registry import ContextAliasRegistry


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_path(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(token).strip() for token in value if str(token).strip()]


def _registry(
    state: dict[str, Any],
    *,
    profile: str = "alpha",
    reload_calls: list[str] | None = None,
    save_calls: list[str] | None = None,
) -> ContextAliasRegistry:
    def reload() -> None:
        if reload_calls is not None:
            reload_calls.append("reload")

    def save() -> None:
        if save_calls is not None:
            save_calls.append("save")

    return ContextAliasRegistry(
        cache=lambda: state["cache"],
        profile_key=lambda: profile,
        normalize=_normalize,
        normalize_path=_normalize_path,
        reload=reload,
        save=save,
        clock_ms=lambda: 1_700_000_000_123,
    )


def test_profile_cache_repairs_buckets_without_cross_profile_leakage() -> None:
    state: dict[str, Any] = {
        "cache": {
            "schema": {
                "profiles": {
                    "alpha": {
                        "option_sets": [],
                        "contexts": {"page": [], "future": {"keep": True}},
                        "extension": {"keep": True},
                    },
                    "beta": {"contexts": {"page": {"beta": {"context_id": "pg_beta"}}}},
                }
            }
        }
    }

    profile = _registry(state).profile_cache()

    assert profile == {
        "option_sets": {},
        "user_types": {},
        "app_texts": {},
        "events": {},
        "workflow_refs": {},
        "element_refs": {},
        "components": {},
        "contexts": {"page": {}, "reusable": {}, "future": {"keep": True}},
        "extension": {"keep": True},
    }
    assert state["cache"]["schema"]["profiles"]["beta"] == {
        "contexts": {"page": {"beta": {"context_id": "pg_beta"}}}
    }


def test_profile_cache_repairs_invalid_schema_and_profile_payloads() -> None:
    state: dict[str, Any] = {"cache": {"schema": []}}

    assert _registry(state).bucket("element_refs") == {}
    assert state["cache"]["schema"]["profiles"]["alpha"]["contexts"] == {
        "page": {},
        "reusable": {},
    }


def test_bucket_rejects_unknown_profile_bucket() -> None:
    state: dict[str, Any] = {"cache": {}}

    with pytest.raises(ValueError, match="Unknown profile cache bucket"):
        _registry(state).bucket("unknown")


def test_cache_context_indexes_name_key_and_object_id_once() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)

    assert registry.cache_context("page", "Home Page", "pg_home", "obj_home") is True
    assert registry.cache_context("page", "Home Page", "pg_home", "obj_home") is False
    bucket = registry.bucket("contexts")["page"]
    expected = {"name": "Home Page", "context_id": "pg_home", "object_id": "obj_home"}
    assert bucket == {
        "home page": expected,
        "pg_home": expected,
        "obj_home": expected,
    }
    assert saves == ["save"]


def test_cache_context_rejects_empty_context_id_without_saving() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []

    assert _registry(state, save_calls=saves).cache_context("reusable", "Card", "") is False
    assert saves == []


def test_lookup_context_prefers_reusable_before_page_for_ambiguous_alias() -> None:
    state: dict[str, Any] = {"cache": {}}
    registry = _registry(state)
    registry.cache_context("page", "Shared", "pg_shared")
    registry.cache_context("reusable", "Shared", "re_shared")

    assert registry.lookup_context(" SHARED ") == ("re_shared", "reusable")
    assert registry.lookup_context("missing") == (None, None)
    assert registry.lookup_context("") == (None, None)


def test_context_key_preserves_context_scope() -> None:
    assert ContextAliasRegistry.context_key("pg_home", "page") == "page:pg_home"
