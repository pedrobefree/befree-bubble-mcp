from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    snapshot_path = tmp_path / "app.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "settings": {
                    "client_safe": {
                        "default_styles": {
                            "Input": "Input_default_",
                            "AutocompleteDropdown": "AutocompleteDropdown_default_",
                        }
                    }
                },
                "styles": {
                    "Input_default_": {"%d": "Input base", "%x": "Input", "%p": {"%bw": 1}},
                    "AutocompleteDropdown_default_": {"%x": "AutocompleteDropdown"},
                    "Button_primary_": {
                        "%d": "Primary action",
                        "%x": "Button",
                        "%p": {"%bgc": "#155eef", "%br": 8},
                    },
                    "Text_body_": {"display": "Body", "%x": "Text", "%p": {"%fs": 16}},
                },
                "pages": {
                    "index": {
                        "id": "index",
                        "name": "index",
                        "elements": {
                            "gallery": {
                                "id": "gallery-button",
                                "%x": "Button",
                                "%nm": "Buttons/Button (Size=md, Hierarchy=Primary)",
                                "%s1": "Button_primary_",
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    instance = BubbleCLI(app_json_path=str(snapshot_path), appname="fixture-app")
    instance._cli_cache = {
        **instance._cli_cache,
        "styles": {
            "Cached card": {
                "id": "Group_cached_",
                "type": "Group",
                "%p": {"%bgc": "#ffffff"},
            }
        },
    }
    return instance


def test_real_bubble_cli_style_reference_facades_preserve_literal_results(cli: BubbleCLI) -> None:
    assert cli.find_style_id("Primary action", element_type="button") == "Button_primary_"
    assert cli.find_style_id_by_name("Body", element_type="Text") == "Text_body_"
    assert cli.find_style_id("Cached card", element_type="Group") == "Group_cached_"
    assert cli._resolve_style_reference("Button_primary_", element_type="Button", strict=True) == "Button_primary_"
    assert cli._resolve_style_reference("Button_unknown_", element_type="Button", strict=True) is None
    assert cli._infer_element_type_from_style_id("Text_body_") == "Text"
    assert cli._normalize_style_element_type("picture uploader") == "PictureInput"
    assert cli._default_style_settings_key("search box") == "AutocompleteDropdown"
    assert cli._configured_default_style_id_for_element_type("Input") == "Input_default_"
    assert cli._first_available_style_id_for_element_type("Input") == "Input_default_"
    assert cli._get_base_style_props("Button_primary_") == {"%bgc": "#155eef", "%br": 8}


class _SentinelReferences:
    def find_style_id(self, name: str, element_type: str | None = None) -> str:
        return f"find:{name}:{element_type}"

    def resolve(self, value: str | None, element_type: str | None = None, strict: bool = False) -> str:
        return f"resolve:{value}:{element_type}:{strict}"

    def infer_element_type(self, style_id: str | None) -> str:
        return f"infer:{style_id}"

    def normalize_element_type(self, element_type: str | None) -> str:
        return f"normalize:{element_type}"

    def default_style_settings_key(self, element_type: str | None) -> str:
        return f"default-key:{element_type}"

    def configured_default_style_id(self, element_type: str | None) -> str:
        return f"configured:{element_type}"

    def first_available_style_id(self, element_type: str | None) -> str:
        return f"first:{element_type}"

    def base_properties(self, style_id: str) -> dict[str, Any]:
        return {"delegated": style_id}


def test_bubble_cli_compatibility_methods_delegate_to_the_composed_resolver(cli: BubbleCLI) -> None:
    cli._style_lifecycle.references = _SentinelReferences()  # type: ignore[assignment]

    assert cli.find_style_id("Primary", element_type="Button") == "find:Primary:Button"
    assert cli.find_style_id_by_name("Body", element_type="Text") == "find:Body:Text"
    assert cli._resolve_style_reference("Button_id_", element_type="Button", strict=True) == (
        "resolve:Button_id_:Button:True"
    )
    assert cli._infer_element_type_from_style_id("Text_body_") == "infer:Text_body_"
    assert cli._normalize_style_element_type("button") == "normalize:button"
    assert cli._default_style_settings_key("SearchBox") == "default-key:SearchBox"
    assert cli._configured_default_style_id_for_element_type("Input") == "configured:Input"
    assert cli._first_available_style_id_for_element_type("SliderInput") == "first:SliderInput"
    assert cli._get_base_style_props("Button_primary_") == {"delegated": "Button_primary_"}
