from __future__ import annotations

import copy
from collections.abc import Callable
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
    reload_action: Callable[[], None] | None = None,
) -> ContextAliasRegistry:
    def reload() -> None:
        if reload_calls is not None:
            reload_calls.append("reload")
        if reload_action is not None:
            reload_action()

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


def test_cache_element_reloads_and_preserves_existing_key_and_path() -> None:
    disk_cache: dict[str, Any] = {
        "schema": {
            "profiles": {
                "alpha": {
                    "element_refs": {
                        "page:pg_home": {
                            "hero": {
                                "name": "Hero",
                                "id": "old_id",
                                "key": "el_hero",
                                "path": ["%el", "el_hero"],
                                "context_id": "pg_home",
                                "context_type": "page",
                            }
                        }
                    }
                }
            }
        }
    }
    state: dict[str, Any] = {"cache": {}}
    reloads: list[str] = []
    saves: list[str] = []

    def replace_from_disk() -> None:
        state["cache"] = copy.deepcopy(disk_cache)

    registry = _registry(
        state,
        reload_calls=reloads,
        save_calls=saves,
        reload_action=replace_from_disk,
    )

    assert registry.cache_element("pg_home", "page", "Hero", "new_id", element_type="Text") is True
    assert registry.lookup_element_payload("pg_home", "page", "hero", reload=False) == {
        "name": "Hero",
        "id": "new_id",
        "key": "el_hero",
        "path": ["%el", "el_hero"],
        "type": "Text",
        "context_id": "pg_home",
        "context_type": "page",
    }
    assert reloads == ["reload"]
    assert saves == ["save"]


def test_cache_element_rejects_empty_alias_or_element_without_io() -> None:
    state: dict[str, Any] = {"cache": {}}
    reloads: list[str] = []
    saves: list[str] = []
    registry = _registry(state, reload_calls=reloads, save_calls=saves)

    assert registry.cache_element("pg", "page", "", "el") is False
    assert registry.cache_element("pg", "page", "Hero", "") is False
    assert reloads == []
    assert saves == []


def test_cache_created_elements_deduplicates_aliases_and_saves_once() -> None:
    state: dict[str, Any] = {"cache": {}}
    reloads: list[str] = []
    saves: list[str] = []
    registry = _registry(state, reload_calls=reloads, save_calls=saves)

    changed = registry.cache_created_elements(
        "pg_home",
        "page",
        ["Hero", " hero ", "Primary Hero"],
        "obj_hero",
        element_key="el_hero",
        parent_path=["%el", "group_main"],
        element_type="Image",
    )

    scoped = registry.bucket("element_refs")["page:pg_home"]
    assert changed == 4
    assert set(scoped) == {"hero", "primary hero", "el_hero", "obj_hero"}
    assert scoped["hero"]["path"] == ["%el", "group_main", "%el", "el_hero"]
    assert all(payload["id"] == "obj_hero" for payload in scoped.values())
    assert reloads == ["reload"]
    assert saves == ["save"]


def test_element_lookups_reload_support_legacy_strings_and_return_defensive_copies() -> None:
    state: dict[str, Any] = {
        "cache": {
            "schema": {
                "profiles": {
                    "alpha": {
                        "element_refs": {
                            "page:pg": {
                                "legacy": "legacy_id",
                                "hero": {"name": "Hero", "id": "hero_id", "path": ["%el", "hero"]},
                            }
                        }
                    }
                }
            }
        }
    }
    reloads: list[str] = []
    registry = _registry(state, reload_calls=reloads)

    assert registry.lookup_element_id("pg", "page", "legacy") == "legacy_id"
    payload = registry.lookup_element_payload("pg", "page", "hero")
    assert payload == {"name": "Hero", "id": "hero_id", "path": ["%el", "hero"]}
    assert payload is not None
    payload["id"] = "mutated"
    assert registry.lookup_element_payload("pg", "page", "hero", reload=False)["id"] == "hero_id"
    assert reloads == ["reload", "reload"]


@pytest.mark.parametrize(
    ("selector", "value"),
    [
        ("element_id", "hero_id"),
        ("element_key", "el_hero"),
        ("element_path", ["%el", "group", "%el", "el_hero"]),
    ],
)
def test_remove_element_aliases_supports_each_stable_selector(selector: str, value: Any) -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)
    registry.cache_element(
        "pg",
        "page",
        "Hero",
        "hero_id",
        element_key="el_hero",
        element_path=["%el", "group", "%el", "el_hero"],
    )
    saves.clear()

    assert registry.remove_element_aliases("pg", "page", **{selector: value}) == 1
    assert registry.lookup_element_payload("pg", "page", "hero", reload=False) is None
    assert saves == ["save"]
