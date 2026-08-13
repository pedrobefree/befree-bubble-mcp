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
