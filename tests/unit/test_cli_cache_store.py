from __future__ import annotations

import json
import multiprocessing
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.cli_cache import (
    BubbleCLICacheStore,
    apply_cache_delta,
    default_cache_payload,
    merge_cache_payloads,
)
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.context_alias_registry import ContextAliasRegistry


def _build_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[BubbleCLI, Path]:
    app_path = tmp_path / "app.json"
    app_path.write_text("{}", encoding="utf-8")
    cache_path = tmp_path / ".bubble_cli_cache.json"
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(cache_path))
    cli = BubbleCLI(
        app_json_path=str(app_path),
        appname="cache-store-test",
        profile_name=f"stage41-{tmp_path.name}",
    )
    return cli, cache_path


def _registry_transaction_worker(
    cache_path: str,
    action: str,
    alias: str,
    attempted: Any,
    entered: Any,
    release: Any,
    hold_lock: bool,
    results: Any,
) -> None:
    store = BubbleCLICacheStore(cache_path)
    state: dict[str, Any] = {"cache": store.load()}

    def transaction(operation: Any) -> bool:
        def mutate(latest: dict[str, Any]) -> bool:
            state["cache"] = latest
            if hold_lock:
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Timed out waiting to release cache transaction")
            return bool(operation())

        updated, changed = store.transaction(state["cache"], mutate)
        state["cache"] = updated
        return changed

    registry = ContextAliasRegistry(
        cache=lambda: state["cache"],
        profile_key=lambda: "concurrent",
        normalize=lambda value: str(value or "").strip().lower(),
        normalize_path=lambda value: list(value) if isinstance(value, list) else [],
        reload=lambda: None,
        save=lambda: None,
        transaction=transaction,
    )
    attempted.set()
    if action == "workflow_write":
        result = registry.cache_workflow("pg", "page", alias, f"wf_{alias.lower()}")
    elif action == "element_write":
        result = registry.cache_element("pg", "page", alias, f"id_{alias.lower()}")
    elif action == "element_remove":
        result = registry.remove_element_aliases("pg", "page", element_id=alias) == 1
    else:
        raise ValueError(f"Unknown worker action: {action}")
    results.put(result)


def _join_process(process: multiprocessing.Process) -> None:
    process.join(timeout=15)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("Concurrent cache worker did not finish")
    assert process.exitcode == 0


def test_default_cache_payload_returns_independent_canonical_buckets() -> None:
    first = default_cache_payload()
    second = default_cache_payload()

    first["colors"]["primary"] = {"rgba": "#155eef"}
    first["schema"]["profiles"]["app"] = {"contexts": {}}

    assert second == {
        "colors": {},
        "fonts": {},
        "styles": {},
        "components": {},
        "schema": {"profiles": {}},
    }


def test_merge_cache_payloads_recurses_and_prefers_canonical_incoming_values() -> None:
    legacy = {
        "colors": {
            "shared": {"rgba": "#000000", "legacy_name": "Old"},
            "legacy_only": {"rgba": "#ffffff"},
        },
        "version": ["legacy"],
        "nullable": "legacy-value",
    }
    canonical = {
        "colors": {"shared": {"rgba": "#155eef"}},
        "version": ["canonical"],
        "nullable": None,
    }

    assert merge_cache_payloads(legacy, canonical) == {
        "colors": {
            "shared": {"rgba": "#155eef", "legacy_name": "Old"},
            "legacy_only": {"rgba": "#ffffff"},
        },
        "version": ["canonical"],
        "nullable": None,
    }


def test_apply_cache_delta_preserves_concurrent_siblings_and_local_deletions() -> None:
    base = {
        "schema": {
            "profiles": {
                "app": {
                    "workflow_refs": {"page:pg": {"remove": {"key": "wf_old"}}},
                    "events": {"unchanged": {"id": "old"}},
                }
            }
        }
    }
    pending = {
        "schema": {
            "profiles": {
                "app": {
                    "workflow_refs": {"page:pg": {}},
                    "events": {"unchanged": {"id": "old"}, "local": {"id": "event_local"}},
                }
            }
        }
    }

    latest = {
        "schema": {
            "profiles": {
                "app": {
                    "workflow_refs": {
                        "page:pg": {
                            "remove": {"key": "wf_old"},
                            "concurrent": {"key": "wf_concurrent"},
                        }
                    },
                    "events": {"unchanged": {"id": "newer"}},
                }
            }
        }
    }

    assert apply_cache_delta(base, pending, latest) == {
        "schema": {
            "profiles": {
                "app": {
                    "workflow_refs": {
                        "page:pg": {"concurrent": {"key": "wf_concurrent"}}
                    },
                    "events": {
                        "unchanged": {"id": "newer"},
                        "local": {"id": "event_local"},
                    },
                }
            }
        }
    }


@pytest.mark.parametrize(
    ("base", "pending"),
    [
        ({"value": 1}, {"value": True}),
        ({"value": 0}, {"value": False}),
        ({"value": [1, {"nested": 0}]}, {"value": [True, {"nested": False}]}),
    ],
)
def test_apply_cache_delta_distinguishes_booleans_from_numbers(
    base: dict[str, Any],
    pending: dict[str, Any],
) -> None:
    result = apply_cache_delta(base, pending, base)
    assert json.dumps(result, sort_keys=True) == json.dumps(pending, sort_keys=True)


def test_apply_cache_delta_merges_repaired_mapping_with_concurrent_children() -> None:
    base = {"workflow_refs": []}
    pending = {"workflow_refs": {}}
    latest = {"workflow_refs": {"page:pg": {"load": {"key": "wf_load"}}}}

    assert apply_cache_delta(base, pending, latest) == latest


@pytest.mark.parametrize("raw", ["{broken", "[]", "null", '"text"'])
def test_load_repairs_missing_malformed_or_non_object_payloads(tmp_path: Path, raw: str) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    cache_path.write_text(raw, encoding="utf-8")

    assert BubbleCLICacheStore(cache_path).load() == default_cache_payload()


def test_load_returns_defaults_when_cache_is_missing(tmp_path: Path) -> None:
    assert BubbleCLICacheStore(tmp_path / "missing.json").load() == default_cache_payload()


def test_load_normalizes_invalid_buckets_without_discarding_unrelated_data(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "colors": ["invalid"],
                "fonts": {"Inter": {"id": "font_inter"}},
                "styles": None,
                "components": "invalid",
                "schema": {"profiles": [], "future": {"flag": True}},
                "extension_data": {"keep": True},
            }
        ),
        encoding="utf-8",
    )

    assert BubbleCLICacheStore(cache_path).load() == {
        "colors": {},
        "fonts": {"Inter": {"id": "font_inter"}},
        "styles": {},
        "components": {},
        "schema": {"profiles": {}, "future": {"flag": True}},
        "extension_data": {"keep": True},
    }


def test_save_writes_normalized_payload_and_load_round_trips(tmp_path: Path) -> None:
    cache_path = tmp_path / "nested" / ".bubble_cli_cache.json"
    store = BubbleCLICacheStore(cache_path)

    assert store.save({"colors": {"primary": {"rgba": "#155eef"}}, "styles": []}) is True
    assert store.load() == {
        "colors": {"primary": {"rgba": "#155eef"}},
        "fonts": {},
        "styles": {},
        "components": {},
        "schema": {"profiles": {}},
    }
    assert json.loads(cache_path.read_text(encoding="utf-8")) == store.load()
    assert list(cache_path.parent.glob(f".{cache_path.name}.*.tmp")) == []


def test_transaction_serializes_concurrent_registry_writes(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    process_context = multiprocessing.get_context("spawn")
    first_attempted = process_context.Event()
    first_entered = process_context.Event()
    second_attempted = process_context.Event()
    unused_entered = process_context.Event()
    release = process_context.Event()
    results = process_context.Queue()
    first = process_context.Process(
        target=_registry_transaction_worker,
        args=(
            str(cache_path),
            "workflow_write",
            "First",
            first_attempted,
            first_entered,
            release,
            True,
            results,
        ),
    )
    second = process_context.Process(
        target=_registry_transaction_worker,
        args=(
            str(cache_path),
            "workflow_write",
            "Second",
            second_attempted,
            unused_entered,
            release,
            False,
            results,
        ),
    )

    first.start()
    assert first_attempted.wait(10)
    assert first_entered.wait(10)
    second.start()
    assert second_attempted.wait(10)
    release.set()
    _join_process(first)
    _join_process(second)

    assert results.get(timeout=2) is True
    assert results.get(timeout=2) is True
    scoped = BubbleCLICacheStore(cache_path).load()["schema"]["profiles"]["concurrent"][
        "workflow_refs"
    ]["page:pg"]
    assert set(scoped) == {"first", "second"}


def test_transaction_serializes_removal_against_concurrent_write(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    initial = default_cache_payload()
    initial["schema"]["profiles"]["concurrent"] = {
        "element_refs": {
            "page:pg": {
                "target": {"name": "Target", "id": "target_id"},
                "keep": {"name": "Keep", "id": "keep_id"},
            }
        }
    }
    assert BubbleCLICacheStore(cache_path).save(initial) is True

    process_context = multiprocessing.get_context("spawn")
    remove_attempted = process_context.Event()
    remove_entered = process_context.Event()
    write_attempted = process_context.Event()
    unused_entered = process_context.Event()
    release = process_context.Event()
    results = process_context.Queue()
    remover = process_context.Process(
        target=_registry_transaction_worker,
        args=(
            str(cache_path),
            "element_remove",
            "target_id",
            remove_attempted,
            remove_entered,
            release,
            True,
            results,
        ),
    )
    writer = process_context.Process(
        target=_registry_transaction_worker,
        args=(
            str(cache_path),
            "element_write",
            "New",
            write_attempted,
            unused_entered,
            release,
            False,
            results,
        ),
    )

    remover.start()
    assert remove_attempted.wait(10)
    assert remove_entered.wait(10)
    writer.start()
    assert write_attempted.wait(10)
    release.set()
    _join_process(remover)
    _join_process(writer)

    assert results.get(timeout=2) is True
    assert results.get(timeout=2) is True
    scoped = BubbleCLICacheStore(cache_path).load()["schema"]["profiles"]["concurrent"][
        "element_refs"
    ]["page:pg"]
    assert set(scoped) == {"keep", "new"}


def test_transaction_after_clear_starts_from_defaults_instead_of_stale_current(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    store = BubbleCLICacheStore(cache_path)
    stale = default_cache_payload()
    stale["schema"]["profiles"]["app"] = {
        "workflow_refs": {"page:pg": {"old": {"key": "wf_old"}}}
    }
    assert store.save(stale) is True
    stale = store.load()
    assert store.clear() is True

    def add_event(payload: dict[str, Any]) -> bool:
        profile = payload["schema"]["profiles"].setdefault("app", {})
        profile["events"] = {"page:pg:wf_new": {"id": "event_new"}}
        return True

    updated, changed = store.transaction(stale, add_event)

    assert changed is True
    assert updated["schema"]["profiles"]["app"] == {
        "events": {"page:pg:wf_new": {"id": "event_new"}}
    }
    assert store.load() == updated


def test_migrate_legacy_reads_merges_and_saves_while_lock_is_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    legacy_path = tmp_path / ".bubble_cli_cache_legacy.json"
    legacy_path.write_text('{"colors": {"legacy": {}}}', encoding="utf-8")
    cache_path.write_text('{"fonts": {"Inter": {}}}', encoding="utf-8")
    store = BubbleCLICacheStore(cache_path, legacy_path=legacy_path)
    lock_state = {"held": False}
    real_read = store._read_object

    @contextmanager
    def tracked_lock() -> Any:
        assert lock_state["held"] is False
        lock_state["held"] = True
        try:
            yield
        finally:
            lock_state["held"] = False

    def tracked_read(path: Path) -> dict[str, Any] | None:
        assert lock_state["held"] is True
        return real_read(path)

    def tracked_save(payload: dict[str, Any]) -> bool:
        assert lock_state["held"] is True
        return True

    monkeypatch.setattr(store, "_exclusive_lock", tracked_lock)
    monkeypatch.setattr(store, "_read_object", tracked_read)
    monkeypatch.setattr(store, "_save_unlocked", tracked_save)

    assert store.migrate_legacy() is True
    assert lock_state["held"] is False


def test_failed_serialization_preserves_previous_cache_and_cleans_temporary_file(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    original = '{"colors": {"primary": {"rgba": "#155eef"}}}\n'
    cache_path.write_text(original, encoding="utf-8")
    warnings: list[str] = []
    store = BubbleCLICacheStore(cache_path, warn=warnings.append)

    assert store.save({"extension_data": object()}) is False
    assert cache_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(f".{cache_path.name}.*.tmp")) == []
    assert len(warnings) == 1


def test_deeply_nested_serialization_failure_returns_false_and_preserves_cache(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    original = '{"colors": {}}\n'
    cache_path.write_text(original, encoding="utf-8")
    warnings: list[str] = []
    payload: dict[str, object] = {}
    cursor = payload
    for _ in range(sys.getrecursionlimit() + 100):
        child: dict[str, object] = {}
        cursor["nested"] = child
        cursor = child

    store = BubbleCLICacheStore(cache_path, warn=warnings.append)

    assert store.save(payload) is False
    assert cache_path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(f".{cache_path.name}.*.tmp")) == []
    assert len(warnings) == 1


def test_clear_is_idempotent_for_existing_and_missing_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    cache_path.write_text("{}", encoding="utf-8")
    store = BubbleCLICacheStore(cache_path)

    assert store.clear() is True
    assert cache_path.exists() is False
    assert store.clear() is True


def test_clear_reports_failure_when_cache_path_is_a_directory(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache-as-directory"
    cache_path.mkdir()
    warnings: list[str] = []

    assert BubbleCLICacheStore(cache_path, warn=warnings.append).clear() is False
    assert warnings and "Could not clear CLI cache" in warnings[0]
    assert cache_path.is_dir()


def test_migrate_legacy_ignores_absent_or_canonical_legacy_path(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"

    assert BubbleCLICacheStore(cache_path).migrate_legacy() is False
    assert BubbleCLICacheStore(cache_path, legacy_path=cache_path).migrate_legacy() is False


def test_migrate_legacy_rejects_malformed_or_non_object_payload(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    legacy_path = tmp_path / ".bubble_cli_cache_legacy.json"
    warnings: list[str] = []
    store = BubbleCLICacheStore(cache_path, legacy_path=legacy_path, warn=warnings.append)

    legacy_path.write_text("{broken", encoding="utf-8")
    assert store.migrate_legacy() is False
    legacy_path.write_text("[]", encoding="utf-8")
    assert store.migrate_legacy() is False
    assert cache_path.exists() is False
    assert len(warnings) == 2


def test_migrate_legacy_retains_legacy_only_data_and_prefers_canonical_conflicts(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    legacy_path = tmp_path / ".bubble_cli_cache_legacy.json"
    legacy_path.write_text(
        json.dumps(
            {
                "colors": {
                    "shared": {"rgba": "#000000", "legacy_name": "Old"},
                    "legacy_only": {"rgba": "#ffffff"},
                },
                "schema": {"profiles": {"legacy": {"contexts": {"page": "index"}}}},
                "version": ["legacy"],
            }
        ),
        encoding="utf-8",
    )
    cache_path.write_text(
        json.dumps(
            {
                "colors": {"shared": {"rgba": "#155eef"}},
                "schema": {"profiles": {"canonical": {"contexts": {}}}},
                "version": ["canonical"],
            }
        ),
        encoding="utf-8",
    )

    store = BubbleCLICacheStore(cache_path, legacy_path=legacy_path)

    assert store.migrate_legacy() is True
    migrated = store.load()
    assert migrated["colors"] == {
        "shared": {"rgba": "#155eef", "legacy_name": "Old"},
        "legacy_only": {"rgba": "#ffffff"},
    }
    assert migrated["schema"]["profiles"] == {
        "legacy": {"contexts": {"page": "index"}},
        "canonical": {"contexts": {}},
    }
    assert migrated["version"] == ["canonical"]
    assert legacy_path.exists() is True


def test_migrate_legacy_creates_missing_canonical_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    legacy_path = tmp_path / ".bubble_cli_cache_legacy.json"
    legacy_path.write_text('{"fonts": {"Inter": {"id": "font_inter"}}}', encoding="utf-8")

    store = BubbleCLICacheStore(cache_path, legacy_path=legacy_path)

    assert store.migrate_legacy() is True
    assert store.load()["fonts"] == {"Inter": {"id": "font_inter"}}


def test_migrate_legacy_runs_only_once_so_clear_survives_restart(tmp_path: Path) -> None:
    cache_path = tmp_path / ".bubble_cli_cache.json"
    legacy_path = tmp_path / ".bubble_cli_cache_legacy.json"
    legacy_path.write_text(
        '{"colors": {"legacy": {"rgba": "#ffffff"}}}',
        encoding="utf-8",
    )

    first_store = BubbleCLICacheStore(cache_path, legacy_path=legacy_path)
    assert first_store.migrate_legacy() is True
    assert first_store.clear() is True

    restarted_store = BubbleCLICacheStore(cache_path, legacy_path=legacy_path)
    assert restarted_store.migrate_legacy() is False
    assert restarted_store.load() == default_cache_payload()


def test_migrate_legacy_reports_atomic_save_failure(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache-as-directory"
    cache_path.mkdir()
    legacy_path = tmp_path / ".bubble_cli_cache_legacy.json"
    legacy_path.write_text('{"colors": {"primary": {"rgba": "#155eef"}}}', encoding="utf-8")
    warnings: list[str] = []

    assert (
        BubbleCLICacheStore(cache_path, legacy_path=legacy_path, warn=warnings.append).migrate_legacy()
        is False
    )
    assert cache_path.is_dir()
    assert any("Could not save CLI cache" in warning for warning in warnings)


def test_bubble_cli_failed_save_preserves_previous_canonical_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli, cache_path = _build_cli(tmp_path, monkeypatch)
    original = '{"colors": {"primary": {"rgba": "#155eef"}}}\n'
    cache_path.write_text(original, encoding="utf-8")
    cli._cli_cache = {"extension_data": object()}

    assert cli._save_cli_cache() is None
    assert cache_path.read_text(encoding="utf-8") == original


def test_bubble_cli_deep_delta_failure_preserves_previous_canonical_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli, cache_path = _build_cli(tmp_path, monkeypatch)
    original = '{"colors": {"primary": {"rgba": "#155eef"}}}\n'
    cache_path.write_text(original, encoding="utf-8")
    payload: dict[str, object] = {}
    cursor = payload
    for _ in range(sys.getrecursionlimit() + 100):
        child: dict[str, object] = {}
        cursor["nested"] = child
        cursor = child
    cli._cli_cache = {"extension_data": payload}

    assert cli._save_cli_cache() is None
    assert cache_path.read_text(encoding="utf-8") == original


def test_bubble_cli_reload_preserves_memory_when_disk_cache_is_malformed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli, cache_path = _build_cli(tmp_path, monkeypatch)
    in_memory = default_cache_payload()
    in_memory["extension_data"] = {"keep": True}
    cli._cli_cache = in_memory
    cache_path.write_text("{broken", encoding="utf-8")

    cli._reload_cli_cache_from_disk()

    assert cli._cli_cache == in_memory


def test_reload_preserves_current_mapping_exactly_when_disk_cache_is_missing(
    tmp_path: Path,
) -> None:
    current = {"extension_data": {"keep": True}}

    reloaded = BubbleCLICacheStore(tmp_path / "missing.json").reload(current)

    assert reloaded == current
    assert reloaded is not current
    assert reloaded["extension_data"] is not current["extension_data"]


def test_bubble_cli_clear_restores_complete_canonical_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli, cache_path = _build_cli(tmp_path, monkeypatch)
    cache_path.write_text('{"colors": {"primary": {}}}', encoding="utf-8")
    cli._cli_cache = {"colors": {"primary": {}}}

    assert cli.clear_cache() is True
    assert cli._cli_cache == default_cache_payload()
    assert cache_path.exists() is False


def test_bubble_cli_cache_add_remove_round_trips_through_existing_facade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli, _cache_path = _build_cli(tmp_path, monkeypatch)
    cli._add_to_cache("colors", "primary", {"rgba": "#155eef"})

    reloaded, _ = _build_cli(tmp_path, monkeypatch)
    assert reloaded._cli_cache["colors"]["primary"] == {"rgba": "#155eef"}

    reloaded._remove_from_cache("colors", "primary")
    after_remove, _ = _build_cli(tmp_path, monkeypatch)
    assert "primary" not in after_remove._cli_cache["colors"]


def test_bubble_cli_save_persists_boolean_correction_from_numeric_legacy_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initial, cache_path = _build_cli(tmp_path, monkeypatch)
    cache_path.write_text('{"extension_data": {"enabled": 1}}', encoding="utf-8")
    cli, _ = _build_cli(tmp_path, monkeypatch)
    cli._cli_cache["extension_data"]["enabled"] = True

    cli._save_cli_cache()

    persisted = json.loads(cache_path.read_text(encoding="utf-8"))
    assert persisted["extension_data"]["enabled"] is True
