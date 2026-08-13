from __future__ import annotations

import json
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.cli_cache import (
    BubbleCLICacheStore,
    default_cache_payload,
    merge_cache_payloads,
)


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
    }
    canonical = {
        "colors": {"shared": {"rgba": "#155eef"}},
        "version": ["canonical"],
    }

    assert merge_cache_payloads(legacy, canonical) == {
        "colors": {
            "shared": {"rgba": "#155eef", "legacy_name": "Old"},
            "legacy_only": {"rgba": "#ffffff"},
        },
        "version": ["canonical"],
    }


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
