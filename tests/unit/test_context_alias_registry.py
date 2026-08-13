from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.context_alias_registry import ContextAliasRegistry
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


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


def _bubble_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "app.json"
    if not app_path.exists():
        app_path.write_text("{}", encoding="utf-8")
    cache_path = tmp_path / ".bubble_cli_cache.json"
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(cache_path))
    return BubbleCLI(
        app_json_path=str(app_path),
        appname="context-alias-registry-test",
        profile_name=f"stage42-{tmp_path.name}",
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


def test_lookup_context_ignores_malformed_scopes_payloads_and_empty_ids() -> None:
    state: dict[str, Any] = {"cache": {}}
    registry = _registry(state)
    contexts = registry.bucket("contexts")
    contexts["reusable"] = []
    contexts["page"] = {
        "string": "pg",
        "empty": {"context_id": ""},
    }

    assert registry.lookup_context("string") == (None, None)
    assert registry.lookup_context("empty") == (None, None)


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


def test_cache_element_is_idempotent_and_minimal_payload_omits_optional_fields() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)

    assert registry.cache_element("pg", "page", "Hero", "hero_id") is True
    assert registry.cache_element("pg", "page", "Hero", "hero_id") is False
    assert registry.lookup_element_payload("pg", "page", "Hero", reload=False) == {
        "name": "Hero",
        "id": "hero_id",
        "context_id": "pg",
        "context_type": "page",
    }
    assert saves == ["save"]


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


def test_cache_created_elements_supports_key_only_and_rejects_missing_identity() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)

    assert registry.cache_created_elements("pg", "page", ["", "Hero"], "") == 0
    assert registry.cache_created_elements(
        "pg", "page", ["", "Hero"], "", element_key="el_hero"
    ) == 2
    assert registry.lookup_element_id("pg", "page", "Hero", reload=False) == "el_hero"
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


def test_element_lookups_and_removal_ignore_empty_missing_and_malformed_payloads() -> None:
    state: dict[str, Any] = {"cache": {}}
    registry = _registry(state)
    registry.bucket("element_refs")["page:pg"] = {
        "missing_id": {"name": "Missing"},
        "empty_legacy": "",
        "number": 123,
    }

    assert registry.lookup_element_id("pg", "page", "") is None
    assert registry.lookup_element_id("pg", "page", "missing_id", reload=False) is None
    assert registry.lookup_element_id("pg", "page", "empty_legacy", reload=False) is None
    assert registry.lookup_element_id("pg", "page", "number", reload=False) is None
    assert registry.lookup_element_payload("pg", "page", "") is None
    assert registry.lookup_element_payload("pg", "page", "number", reload=False) is None
    assert registry.remove_element_aliases("pg", "page") == 0


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


def test_remove_element_aliases_removes_legacy_string_by_element_id() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)
    registry.bucket("element_refs")["page:pg"] = {
        "legacy": "hero_id",
        "other": "other_id",
    }

    assert registry.remove_element_aliases("pg", "page", element_id="hero_id") == 1
    assert registry.lookup_element_id("pg", "page", "legacy", reload=False) is None
    assert registry.lookup_element_id("pg", "page", "other", reload=False) == "other_id"
    assert saves == ["save"]


def test_cache_workflow_reloads_preserves_siblings_and_uses_injected_clock() -> None:
    disk_cache: dict[str, Any] = {
        "schema": {
            "profiles": {
                "alpha": {
                    "workflow_refs": {
                        "page:pg": {
                            "existing": {"name": "Existing", "key": "wf_existing"}
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

    assert registry.cache_workflow("pg", "page", "On Load", "wf_load", "event_id") is True
    scoped = registry.bucket("workflow_refs")["page:pg"]
    assert scoped["existing"] == {"name": "Existing", "key": "wf_existing"}
    assert scoped["on load"] == {
        "name": "On Load",
        "key": "wf_load",
        "id": "event_id",
        "context_id": "pg",
        "context_type": "page",
        "updated_at": 1_700_000_000_123,
    }
    assert reloads == ["reload"]
    assert saves == ["save"]


def test_cache_workflow_rejects_invalid_and_is_idempotent_without_optional_id() -> None:
    state: dict[str, Any] = {"cache": {}}
    reloads: list[str] = []
    saves: list[str] = []
    registry = _registry(state, reload_calls=reloads, save_calls=saves)

    assert registry.cache_workflow("pg", "page", "", "wf") is False
    assert registry.cache_workflow("pg", "page", "Load", "") is False
    assert registry.cache_workflow("pg", "page", "Load", "wf_load") is True
    assert registry.cache_workflow("pg", "page", "Load", "wf_load") is False
    assert registry.lookup_workflow("pg", "page", "Load", reload=False) == {
        "name": "Load",
        "key": "wf_load",
        "context_id": "pg",
        "context_type": "page",
        "updated_at": 1_700_000_000_123,
    }
    assert reloads == ["reload", "reload"]
    assert saves == ["save"]


def test_cache_workflow_is_idempotent_when_clock_advances() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    clock_values = iter((100, 200))
    registry = ContextAliasRegistry(
        cache=lambda: state["cache"],
        profile_key=lambda: "alpha",
        normalize=_normalize,
        normalize_path=_normalize_path,
        reload=lambda: None,
        save=lambda: saves.append("save"),
        clock_ms=lambda: next(clock_values),
    )

    assert registry.cache_workflow("pg", "page", "Load", "wf_load") is True
    assert registry.cache_workflow("pg", "page", "Load", "wf_load") is False
    assert registry.lookup_workflow("pg", "page", "Load", reload=False)["updated_at"] == 100
    assert saves == ["save"]


def test_workflow_lookup_rejects_invalid_payload_and_returns_defensive_copy() -> None:
    state: dict[str, Any] = {"cache": {}}
    registry = _registry(state)
    refs = registry.bucket("workflow_refs")
    refs["page:pg"] = {
        "invalid": {"name": "Invalid", "key": ""},
        "valid": {"name": "Valid", "key": "wf_valid"},
    }

    assert registry.lookup_workflow("pg", "page", "invalid", reload=False) is None
    payload = registry.lookup_workflow("pg", "page", "valid", reload=False)
    assert payload == {"name": "Valid", "key": "wf_valid"}
    assert payload is not None
    payload["key"] = "mutated"
    assert registry.lookup_workflow("pg", "page", "valid", reload=False)["key"] == "wf_valid"


def test_workflow_lookup_handles_empty_alias_missing_scope_and_malformed_scope() -> None:
    state: dict[str, Any] = {"cache": {}}
    registry = _registry(state)

    assert registry.lookup_workflow("pg", "page", "") is None
    assert registry.lookup_workflow("pg", "page", "missing", reload=False) is None
    registry.bucket("workflow_refs")["page:pg"] = []
    assert registry.lookup_workflow("pg", "page", "missing", reload=False) is None


@pytest.mark.parametrize(
    ("selector", "value"),
    [
        ("workflow_key", "wf_load"),
        ("workflow_id", "event_id"),
        ("workflow_name", "ON LOAD"),
    ],
)
def test_remove_workflow_aliases_supports_each_stable_selector(selector: str, value: str) -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)
    registry.cache_workflow("pg", "page", "On Load", "wf_load", "event_id")
    saves.clear()

    assert registry.remove_workflow_aliases("pg", "page", **{selector: value}) == 1
    assert registry.lookup_workflow("pg", "page", "On Load", reload=False) is None
    assert saves == ["save"]


@pytest.mark.parametrize(
    ("selector", "value"),
    [
        ("context_id", "pg_home"),
        ("object_id", "obj_home"),
        ("context_name", "HOME PAGE"),
    ],
)
def test_remove_context_aliases_removes_all_fanout_tokens(selector: str, value: str) -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)
    registry.cache_context("page", "Home Page", "pg_home", "obj_home")
    saves.clear()

    assert registry.remove_context_aliases("page", **{selector: value}) == 3
    assert registry.lookup_context("Home Page") == (None, None)
    assert saves == ["save"]


def test_remove_context_scope_cleans_modern_and_legacy_keys_without_touching_siblings() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)
    profile = registry.profile_cache()
    profile["element_refs"] = {
        "page:pg": {"hero": {"id": "hero_id"}},
        "page:other": {"keep": {"id": "keep_id"}},
    }
    profile["workflow_refs"] = {
        "page:pg": {"load": {"key": "wf_load"}},
        "page:pg:wf_legacy": {"name": "legacy"},
        "page:other": {"keep": {"key": "wf_keep"}},
    }
    profile["events"] = {
        "page:pg:wf_load": {"id": "event_load"},
        "page:other:wf_keep": {"id": "event_keep"},
    }

    assert registry.remove_context_scope("pg", "page") is True
    assert profile["element_refs"] == {"page:other": {"keep": {"id": "keep_id"}}}
    assert profile["workflow_refs"] == {"page:other": {"keep": {"key": "wf_keep"}}}
    assert profile["events"] == {"page:other:wf_keep": {"id": "event_keep"}}
    assert saves == ["save"]
    saves.clear()
    assert registry.remove_context_scope("pg", "page") is False
    assert saves == []


def test_removals_ignore_malformed_payloads_and_unmatched_selectors() -> None:
    state: dict[str, Any] = {"cache": {}}
    saves: list[str] = []
    registry = _registry(state, save_calls=saves)
    registry.bucket("contexts")["page"] = {"legacy": "pg"}
    registry.bucket("workflow_refs")["page:pg"] = {"legacy": "wf"}

    assert registry.remove_context_aliases("page", context_id="missing") == 0
    assert registry.remove_workflow_aliases("pg", "page", workflow_key="missing") == 0
    assert saves == []


def test_bubble_cli_workflow_alias_writes_preserve_other_process_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _bubble_cli(tmp_path, monkeypatch)
    stale_second = _bubble_cli(tmp_path, monkeypatch)

    first._cache_workflow_ref_alias("pg", "page", "First", "wf_first", "event_first")
    stale_second._cache_workflow_ref_alias("pg", "page", "Second", "wf_second", "event_second")

    reloaded = _bubble_cli(tmp_path, monkeypatch)
    assert reloaded._lookup_cached_workflow_ref_alias("pg", "page", "First")["key"] == "wf_first"
    assert reloaded._lookup_cached_workflow_ref_alias("pg", "page", "Second")["key"] == "wf_second"


def test_bubble_cli_stale_context_writer_preserves_workflow_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = _bubble_cli(tmp_path, monkeypatch)
    stale_context_writer = _bubble_cli(tmp_path, monkeypatch)

    workflow_writer._cache_workflow_ref_alias("pg", "page", "Load", "wf_load")
    stale_context_writer._cache_context_alias("page", "Home", "pg")

    reloaded = _bubble_cli(tmp_path, monkeypatch)
    assert reloaded._lookup_cached_workflow_ref_alias("pg", "page", "Load")["key"] == "wf_load"
    assert reloaded._lookup_cached_context("Home") == ("pg", "page")


def test_bubble_cli_stale_event_writer_preserves_transactional_workflow_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias_writer = _bubble_cli(tmp_path, monkeypatch)
    stale_event_writer = _bubble_cli(tmp_path, monkeypatch)

    alias_writer._cache_workflow_ref_alias("pg", "page", "Load", "wf_load")
    stale_event_writer._cache_workflow_event("pg", "page", "wf_event")

    reloaded = _bubble_cli(tmp_path, monkeypatch)
    assert reloaded._lookup_cached_workflow_ref_alias("pg", "page", "Load")["key"] == "wf_load"
    assert "page:pg:wf_event" in reloaded._schema_events_cache()


def test_bubble_cli_element_lookup_sees_another_process_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _bubble_cli(tmp_path, monkeypatch)
    writer = _bubble_cli(tmp_path, monkeypatch)

    writer._cache_element_ref_alias("pg", "page", "Hero", "hero_id")

    assert reader._lookup_cached_element_ref_alias("pg", "page", "Hero") == "hero_id"


def test_bubble_cli_context_lookup_preserves_reusable_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _bubble_cli(tmp_path, monkeypatch)
    cli._cache_context_alias("page", "Shared", "pg_shared")
    cli._cache_context_alias("reusable", "Shared", "re_shared")

    assert cli._lookup_cached_context("Shared") == ("re_shared", "reusable")


def test_bubble_cli_element_recache_preserves_key_and_path_enrichment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _bubble_cli(tmp_path, monkeypatch)
    cli._cache_element_ref_alias(
        "pg",
        "page",
        "Hero",
        "hero_id",
        element_key="el_hero",
        element_path=["%el", "el_hero"],
    )

    cli._cache_element_ref_alias("pg", "page", "Hero", "hero_id")

    assert cli._lookup_cached_element_ref_payload("pg", "page", "Hero") == {
        "name": "Hero",
        "id": "hero_id",
        "context_id": "pg",
        "context_type": "page",
        "key": "el_hero",
        "path": ["%el", "el_hero"],
    }


def test_bubble_cli_element_payload_lookup_cannot_mutate_cached_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _bubble_cli(tmp_path, monkeypatch)
    cli._cache_element_ref_alias(
        "pg",
        "page",
        "Hero",
        "hero_id",
        element_key="el_hero",
        element_path=["%el", "el_hero"],
    )

    payload = cli._lookup_cached_element_ref_payload("pg", "page", "Hero")
    assert payload is not None
    payload["id"] = "mutated"

    assert cli._lookup_cached_element_ref_payload("pg", "page", "Hero")["id"] == "hero_id"


def test_bubble_cli_element_removal_cleans_legacy_string_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _bubble_cli(tmp_path, monkeypatch)
    cli._schema_element_refs_cache()["page:pg"] = {
        "legacy": "hero_id",
        "other": "other_id",
    }
    cli._save_cli_cache()

    cli._remove_cached_element_aliases("pg", "page", element_id="hero_id")

    reloaded = _bubble_cli(tmp_path, monkeypatch)
    assert reloaded._lookup_cached_element_ref_alias("pg", "page", "legacy") is None
    assert reloaded._lookup_cached_element_ref_alias("pg", "page", "other") == "other_id"


def test_bubble_cli_context_scope_removal_cleans_modern_workflow_bucket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _bubble_cli(tmp_path, monkeypatch)
    profile = cli._schema_profile_cache()
    profile["element_refs"] = {"page:pg": {"hero": {"id": "hero_id"}}}
    profile["workflow_refs"] = {
        "page:pg": {"load": {"key": "wf_load"}},
        "page:other": {"keep": {"key": "wf_keep"}},
    }
    profile["events"] = {"page:pg:wf_load": {}, "page:other:wf_keep": {}}
    cli._save_cli_cache()

    cli._remove_context_scoped_cache_entries("pg", "page")

    profile = cli._schema_profile_cache()
    assert profile["element_refs"] == {}
    assert profile["workflow_refs"] == {"page:other": {"keep": {"key": "wf_keep"}}}
    assert profile["events"] == {"page:other:wf_keep": {}}
