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
