from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pytest

from bubble_mcp.aria_runtime.style_lifecycle.references import StyleReferenceResolver


@dataclass
class ReferenceHost:
    discovery: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=lambda: {"styles": {}})
    readable_styles: list[dict[str, Any]] = field(default_factory=list)
    elements: list[dict[str, Any]] = field(default_factory=list)
    revision: int = 0

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.discovery, self.cache

    def style_reference_revision(self) -> int:
        return self.revision

    def list_style_references(self) -> list[dict[str, Any]]:
        return list(self.readable_styles)

    def list_style_reference_elements(self) -> list[dict[str, Any]]:
        return list(self.elements)

    def normalize_style_reference(self, value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def compact_style_reference(self, value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", self.normalize_style_reference(value))

    def plain_style_reference_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if not isinstance(value, dict):
            return ""
        entries = value.get("entries") or value.get("%e") or {}
        if not isinstance(entries, dict):
            return ""
        return "".join(str(entries[key]) for key in sorted(entries) if isinstance(entries[key], str))


def test_raw_and_readable_discovery_entries_resolve_with_literal_properties() -> None:
    host = ReferenceHost(
        discovery={
            "styles": {
                "Button_primary_": {
                    "%d": "Primary Action",
                    "%x": "Button",
                    "%p": {"%bgc": "#155eef", "%br": 8},
                },
                "Text_caption_": {
                    "display": "Caption",
                    "type": "Text",
                    "%p": {"%fs": 12},
                },
            }
        },
        readable_styles=[
            {"id": "Button_primary_", "name": "Primary Action", "type": "Button", "is_default": False},
            {"id": "Text_caption_", "name": "Caption", "type": "Text", "is_default": False},
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.find_style_id("primary action", element_type="button") == "Button_primary_"
    assert resolver.find_style_id("CAPTION", element_type="Text") == "Text_caption_"
    assert resolver.infer_element_type("Button_primary_") == "Button"
    assert resolver.base_properties("Button_primary_") == {"%bgc": "#155eef", "%br": 8}


def test_discovery_wins_name_and_id_collisions_while_valid_cache_only_entries_supplement_it() -> None:
    host = ReferenceHost(
        discovery={
            "styles": {
                "Button_live_": {"name": "Primary", "%x": "Button", "%p": {"%bgc": "live"}},
            }
        },
        cache={
            "styles": {
                "Primary": {"id": "Button_cached_", "type": "Button", "%p": {"%bgc": "stale"}},
                "Live alias": {"id": "Button_live_", "type": "Button", "%p": {"%bgc": "cached"}},
                "Card": {"id": "Group_card_", "%x": "Group", "%p": {"%bgc": "cache-only"}},
                "Malformed": {"type": "Group"},
            }
        },
        readable_styles=[
            {"id": "Button_live_", "name": "Primary", "type": "Button", "is_default": False},
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.find_style_id("Primary", element_type="Button") == "Button_live_"
    assert resolver.find_style_id("Live alias", element_type="Button") == "Button_live_"
    assert resolver.find_style_id("Card", element_type="Group") == "Group_card_"
    assert resolver.base_properties("Button_live_") == {"%bgc": "live"}
    assert resolver.base_properties("Group_card_") == {"%bgc": "cache-only"}
    assert resolver.find_style_id("Malformed", element_type="Group") is None


def test_type_filtering_rejects_cross_type_matches_and_accepts_default_key_aliases() -> None:
    host = ReferenceHost(
        discovery={
            "styles": {
                "Button_shared_": {"name": "Shared", "%x": "Button"},
                "Text_shared_": {"name": "Shared", "%x": "Text"},
                "AutocompleteDropdown_search_": {"name": "Search", "%x": "AutocompleteDropdown"},
            }
        },
        readable_styles=[
            {"id": "Button_shared_", "name": "Shared", "type": "Button", "is_default": False},
            {"id": "Text_shared_", "name": "Shared", "type": "Text", "is_default": False},
            {
                "id": "AutocompleteDropdown_search_",
                "name": "Search",
                "type": "AutocompleteDropdown",
                "is_default": False,
            },
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.find_style_id("Shared", element_type="text") == "Text_shared_"
    assert resolver.find_style_id("Shared", element_type="Group") is None
    assert resolver.find_style_id("Search", element_type="SearchBox") == "AutocompleteDropdown_search_"


def test_configured_and_inferred_defaults_resolve_from_generic_friendly_labels() -> None:
    host = ReferenceHost(
        discovery={
            "settings": {
                "client_safe": {
                    "default_styles": {
                        "Input": "Input_configured_",
                        "AutocompleteDropdown": "AutocompleteDropdown_configured_",
                    }
                }
            },
            "styles": {
                "Input_configured_": {"%x": "Input"},
                "AutocompleteDropdown_configured_": {"%x": "AutocompleteDropdown"},
                "Slider_fallback_": {"name": "Slider base", "%x": "SliderInput"},
            },
        },
        readable_styles=[
            {"id": "Input_configured_", "name": "Input (default)", "type": "Input", "is_default": True},
            {
                "id": "AutocompleteDropdown_configured_",
                "name": "AutocompleteDropdown (default)",
                "type": "AutocompleteDropdown",
                "is_default": True,
            },
            {
                "id": "Slider_fallback_",
                "name": "Slider base",
                "type": "SliderInput",
                "is_default": True,
            },
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.normalize_element_type("picture uploader") == "PictureInput"
    assert resolver.default_style_settings_key("search box") == "AutocompleteDropdown"
    assert resolver.configured_default_style_id("input") == "Input_configured_"
    assert resolver.first_available_style_id("slider") == "Slider_fallback_"
    assert resolver.find_style_id("input", element_type="Input") == "Input_configured_"
    assert resolver.find_style_id("standard slider", element_type="SliderInput") == "Slider_fallback_"
    assert resolver.resolve("default search box", element_type="SearchBox") == "AutocompleteDropdown_configured_"


@pytest.mark.parametrize("strict", [False, True])
def test_known_explicit_ids_resolve_in_both_modes(strict: bool) -> None:
    resolver = StyleReferenceResolver(
        ReferenceHost(
            discovery={"styles": {"Button_known_": {"%x": "Button"}}},
            readable_styles=[
                {"id": "Button_known_", "name": "Known", "type": "Button", "is_default": False},
            ],
        )
    )

    assert resolver.resolve("Button_known_", element_type="Button", strict=strict) == "Button_known_"


@pytest.mark.parametrize(
    ("known_ids_populated", "strict", "expected"),
    [
        (False, False, "Button_unknown_"),
        (False, True, "Button_unknown_"),
        (True, False, None),
        (True, True, None),
    ],
)
def test_unknown_explicit_id_preserves_legacy_empty_populated_strict_permissive_matrix(
    known_ids_populated: bool,
    strict: bool,
    expected: str | None,
) -> None:
    discovery = {"styles": {"Button_known_": {"%x": "Button"}}} if known_ids_populated else {}
    readable_styles = (
        [{"id": "Button_known_", "name": "Known", "type": "Button", "is_default": False}]
        if known_ids_populated
        else []
    )
    resolver = StyleReferenceResolver(
        ReferenceHost(discovery=discovery, readable_styles=readable_styles)
    )

    assert resolver.resolve("Button_unknown_", element_type="Button", strict=strict) == expected


def test_semantic_button_labels_resolve_to_a_defined_gallery_style() -> None:
    host = ReferenceHost(
        discovery={
            "styles": {
                "Button_bLive1": {
                    "%x": "Button",
                    "%s": {"hover": {"%p": {"%bgc": "#004eeb"}}},
                },
                "Button_button__primary__md_": {"%x": "Button"},
            }
        },
        readable_styles=[
            {"id": "Button_bLive1", "name": "Generated", "type": "Button", "is_default": False},
            {
                "id": "Button_button__primary__md_",
                "name": "Primary md",
                "type": "Button",
                "is_default": False,
            },
        ],
        elements=[
            {
                "id": "gallery-button",
                "element": {
                    "%x": "Button",
                    "%nm": "Buttons/Button (Size=md, Hierarchy=Primary, Icon=false)",
                    "%s1": "Button_bLive1",
                },
            },
            {
                "id": "canonical-button",
                "element": {
                    "%x": "Button",
                    "%dn": "Button Primary Md",
                    "%s1": "Button_button__primary__md_",
                },
            },
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.resolve("Button / Primary / Md", element_type="Button") == "Button_bLive1"


def test_replacing_discovery_or_cache_snapshots_invalidates_the_normalized_index() -> None:
    host = ReferenceHost(
        discovery={"styles": {"Text_old_": {"name": "Body", "%x": "Text"}}},
        readable_styles=[
            {"id": "Text_old_", "name": "Body", "type": "Text", "is_default": False},
        ],
    )
    resolver = StyleReferenceResolver(host)
    assert resolver.find_style_id("Body", element_type="Text") == "Text_old_"

    host.discovery = {"styles": {"Text_new_": {"name": "Body", "%x": "Text"}}}
    host.readable_styles = [
        {"id": "Text_new_", "name": "Body", "type": "Text", "is_default": False},
    ]
    assert resolver.find_style_id("Body", element_type="Text") == "Text_new_"

    host.cache = {"styles": {"Cache body": {"id": "Text_cache_", "type": "Text"}}}
    assert resolver.find_style_id("Cache body", element_type="Text") == "Text_cache_"


def test_revision_invalidates_index_after_in_place_cache_mutation() -> None:
    host = ReferenceHost(discovery={"styles": {}}, cache={"styles": {}})
    resolver = StyleReferenceResolver(host)
    assert resolver.find_style_id("Cached card", element_type="Group") is None

    host.cache["styles"]["Cached card"] = {
        "id": "Group_cached_",
        "type": "Group",
        "%p": {"%bgc": "#ffffff"},
    }
    host.revision += 1

    assert resolver.find_style_id("Cached card", element_type="Group") == "Group_cached_"
    assert resolver.base_properties("Group_cached_") == {"%bgc": "#ffffff"}


def test_matching_cache_fills_missing_discovery_type_and_properties_without_overwriting_present_values() -> None:
    host = ReferenceHost(
        discovery={
            "styles": {
                "Button_missing_fields_": {"%d": "Missing fields"},
                "Button_discovery_wins_": {
                    "%d": "Discovery wins",
                    "%x": "Button",
                    "%p": {"%bgc": "discovery"},
                },
            }
        },
        cache={
            "styles": {
                "Cached missing fields": {
                    "id": "Button_missing_fields_",
                    "type": "Button",
                    "%p": {"%bgc": "cache", "%br": 6},
                },
                "Cached discovery wins": {
                    "id": "Button_discovery_wins_",
                    "type": "Text",
                    "%p": {"%bgc": "cache"},
                },
            }
        },
        readable_styles=[
            {
                "id": "Button_missing_fields_",
                "name": "Missing fields",
                "type": "Unknown",
                "is_default": False,
            },
            {
                "id": "Button_discovery_wins_",
                "name": "Discovery wins",
                "type": "Button",
                "is_default": False,
            },
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.infer_element_type("Button_missing_fields_") == "Button"
    assert resolver.base_properties("Button_missing_fields_") == {"%bgc": "cache", "%br": 6}
    assert resolver.infer_element_type("Button_discovery_wins_") == "Button"
    assert resolver.base_properties("Button_discovery_wins_") == {"%bgc": "discovery"}


def test_empty_malformed_and_unknown_snapshots_fail_closed_without_mutating_inputs() -> None:
    host = ReferenceHost(
        discovery={
            "settings": "malformed",
            "styles": {
                "": {"%x": "Text"},
                "Button_inferred_": "malformed",
            },
        },
        cache={
            "styles": {
                "deleted": {"id": "Button_deleted_", "type": "Button", "%del": True},
                "malformed": "value",
                "missing id": {"type": "Button"},
            }
        },
        readable_styles=["malformed", {"name": "missing id"}],  # type: ignore[list-item]
        elements=[{"element": "malformed"}],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.normalize_element_type(None) == ""
    assert resolver.normalize_element_type("PluginWidget") == "PluginWidget"
    assert resolver.configured_default_style_id(None) is None
    assert resolver.configured_default_style_id("Button") is None
    assert resolver.first_available_style_id(None) is None
    assert resolver.first_available_style_id("Text") is None
    assert resolver.canonical_style_id("", "Button") is None
    assert resolver.canonical_style_id("!!!", "Button") is None
    assert resolver.canonical_style_id("Button_explicit_", "Button") == "Button_explicit_"
    assert resolver.looks_like_style_id("plain label") is False
    assert resolver.looks_like_style_id("Button_style_") is True
    assert resolver.find_style_id("") is None
    assert resolver.resolve(None) is None
    assert resolver.resolve("  ") is None
    assert resolver.infer_element_type(None) is None
    assert resolver.infer_element_type("missing") is None
    assert resolver.base_properties("missing") == {}
    assert resolver.known_style_ids() == {"Button_inferred_"}
    assert resolver.known_non_default_style_ids("Button") == {"Button_inferred_"}
    assert resolver.current_snapshot_style_ids("Button") == {"Button_inferred_"}

    resolver.invalidate()
    assert resolver.find_style_id("missing") is None


@pytest.mark.parametrize(
    "discovery",
    [
        {"settings": {"client_safe": "malformed"}},
        {"settings": {"client_safe": {"default_styles": "malformed"}}},
    ],
)
def test_malformed_default_style_layers_are_ignored(discovery: dict[str, Any]) -> None:
    resolver = StyleReferenceResolver(ReferenceHost(discovery=discovery))

    assert resolver.configured_default_style_id("Button") is None


def test_catalog_canonical_token_and_prefix_lookup_strategies_have_literal_results() -> None:
    host = ReferenceHost(
        discovery={
            "styles": {
                "Text_catalog_": {"%d": "Opaque", "%x": "Text"},
                "Text_class_title_": {"%d": "Opaque title", "%x": "Text"},
                "Alert_success_": {"%d": "Success state", "%x": "Alert"},
                "Text_prefix_hero_title_suffix_": {"%d": "Opaque hero", "%x": "Text"},
                "PluginWidget_plain_": {},
            }
        },
        readable_styles=[
            {"id": "Text_catalog_", "name": "Opaque", "type": "Text", "is_default": False},
            {"id": "Text_class_title_", "name": "Opaque title", "type": "Text", "is_default": False},
            {"id": "Alert_success_", "name": "Success state", "type": "Alert", "is_default": False},
            {
                "id": "Text_prefix_hero_title_suffix_",
                "name": "Opaque hero",
                "type": "Text",
                "is_default": False,
            },
            {"id": "PluginWidget_plain_", "name": "Plugin", "type": "", "is_default": False},
        ],
        elements=[
            {"element": {"%x": "Text", "%p": {"text": "Catalog Label", "%s1": "Text_catalog_"}}},
            {"element": {"%x": "Text", "%p": {"text": "Catalog Label", "%s1": "Alert_success_"}}},
            {"element": {"%x": "Text", "%p": {"text": "Unknown", "%s1": "Text_missing_"}}},
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.find_style_id("Catalog Label", element_type="Text") == "Text_catalog_"
    assert resolver.find_style_id("class title", element_type="Text") == "Text_class_title_"
    assert resolver.find_style_id("success alert", element_type="Alert") == "Alert_success_"
    assert resolver.find_style_id("Plugin", element_type="PluginWidget") == "PluginWidget_plain_"
    assert resolver.find_style_id("Catalog Label", element_type="Button") is None
    assert resolver.known_style_ids() == {
        "Text_catalog_",
        "Text_class_title_",
        "Alert_success_",
        "Text_prefix_hero_title_suffix_",
        "PluginWidget_plain_",
    }


def test_resolution_distinguishes_empty_known_default_and_non_default_indexes() -> None:
    empty = StyleReferenceResolver(ReferenceHost())
    assert empty.resolve("Hero", element_type="Text", strict=True) == "Text_hero_"

    defaults_only = StyleReferenceResolver(
        ReferenceHost(
            discovery={"styles": {"Text_default_": {"%x": "Text"}}},
            readable_styles=[
                {"id": "Text_default_", "name": "Text default", "type": "Text", "is_default": True}
            ],
        )
    )
    assert defaults_only.resolve("Hero", element_type="Text", strict=True) == "Text_hero_"

    non_default = StyleReferenceResolver(
        ReferenceHost(
            discovery={"styles": {"Text_body_": {"%x": "Text"}}},
            readable_styles=[
                {"id": "Text_body_", "name": "Body", "type": "Text", "is_default": False}
            ],
        )
    )
    assert non_default.resolve("Hero", element_type="Text", strict=True) is None
    assert non_default.resolve("Hero", element_type="Text", strict=False) is None


def test_semantic_button_scan_ignores_invalid_or_nonmatching_gallery_rows() -> None:
    host = ReferenceHost(
        discovery={"styles": {"Button_known_": {"%x": "Button"}}},
        readable_styles=[
            {"id": "Button_known_", "name": "Known", "type": "Button", "is_default": False}
        ],
        elements=[
            {"element": "malformed"},
            {"element": {"%x": "Text", "%nm": "Button Primary Md", "%s1": "Button_known_"}},
            {"element": {"%x": "Button", "%nm": "Button Primary Md"}},
            {"element": {"%x": "Button", "%nm": "Button Primary Md", "%s1": "Button_missing_"}},
            {"element": {"%x": "Button", "%nm": "Button Secondary Lg", "%s1": "Button_known_"}},
        ],
    )
    resolver = StyleReferenceResolver(host)

    assert resolver.resolve("Button / Primary / Md", element_type="Button", strict=True) is None
    assert resolver.resolve("Button_known_", element_type="Button", strict=True) == "Button_known_"
