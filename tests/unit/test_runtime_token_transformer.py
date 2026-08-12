import json
import sys
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.figma_bridge import transform_tokens
from bubble_mcp.aria_runtime.figma_bridge.transform_tokens import TokenTransformer


def _transformer(tmp_path: Path, **overrides: object) -> TokenTransformer:
    config = {
        "naming": {"separator": " ", "case": "title"},
        "filters": {},
        "default_color_mapping": {"primary": "color.brand.500", "surface": ["a", "b"]},
        **overrides,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return TokenTransformer(str(path))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        (600, "600"),
        ({"value": "Semi Bold"}, "600"),
        ("0700", "700"),
        ("Extra_Bold Italic", "800"),
        ("unmapped", "unmapped"),
    ],
)
def test_normalize_font_weight(tmp_path: Path, raw: object, expected: str | None) -> None:
    assert _transformer(tmp_path).normalize_font_weight(raw) == expected


def test_color_normalization_and_naming(tmp_path: Path) -> None:
    transformer = _transformer(
        tmp_path,
        color_mapping={"color.brand.500": "Brand Primary"},
    )

    assert transformer.hex_to_rgba("#112233") == "rgba(17, 34, 51, 1)"
    assert transformer.hex_to_rgba("#11223380") == "rgba(17, 34, 51, 0.5)"
    assert transformer.hex_to_rgba("#GGGGGG") == "#GGGGGG"
    assert transformer.hex_to_rgba("rgb(1,2,3)") == "rgba(1, 2, 3, 1)"
    assert transformer.normalize_rgba("invalid") == "invalid"
    assert transformer.format_name(["color", "color", "brand", "500"]) == "Brand Primary"
    assert transformer._normalize_token_parts([], "color") == []

    camel = _transformer(tmp_path, naming={"separator": "-", "case": "camel"})
    assert camel.format_name(["typography", "body", "large"], "font") == "bodyLarge"


def test_flatten_filter_groups_and_defaults(tmp_path: Path) -> None:
    transformer = _transformer(tmp_path)
    tokens = transformer.flatten_tokens(
        {
            "color": {"color": {"brand": {"500": {"type": "color", "value": "#112233"}}}},
            "typography": {
                "body": {
                    "regular": {
                        "fontFamily": "Inter",
                        "fontSize": "16px",
                        "fontWeight": "Regular",
                    }
                }
            },
            "button": {"primary": {"hover": {"bg": {"type": "color", "value": "#000000"}}}},
            "extensions": {"ignored": {"type": "color", "value": "#ffffff"}},
        }
    )
    filtered = transformer.filter_tokens(tokens)

    assert {token["path"] for token in filtered["color"]} == {"color.brand.500"}
    assert len(filtered["font"]) == 1
    assert len(filtered["style"]) == 1
    assert len(filtered["button"]) == 1
    assert transformer.get_available_groups(tokens) == {"color": ["brand"], "style": ["body"]}
    assert transformer.get_default_color_mappings() == {
        "primary": ["color.brand.500"],
        "surface": ["a", "b"],
    }


def test_aggregates_themes_and_generates_commands(tmp_path: Path) -> None:
    transformer = _transformer(tmp_path)
    button_tokens = [
        {"parts": ["button", "primary", "bg"], "type": "color", "value": "#112233"},
        {"parts": ["button", "primary", "hover", "radius"], "type": "number", "value": 8},
        {"parts": ["other"], "type": "color", "value": "#ffffff"},
    ]
    typography_tokens = [
        {
            "parts": ["typography", "body", "regular"],
            "value": {
                "fontFamily": {"value": "Inter"},
                "fontSize": {"value": "16px"},
                "fontWeight": {"value": "Semi Bold"},
                "lineHeight": "24px",
                "letterSpacing": "10%",
            },
        }
    ]

    assert transformer.aggregate_button_themes(button_tokens) == {
        "primary": {
            "base": {"bg_color": "rgba(17, 34, 51, 1)"},
            "hover": {"border_radius": 8},
        }
    }
    assert transformer.aggregate_typography_themes(typography_tokens) == {
        "Body Regular": {
            "base": {
                "font_family": "Inter",
                "font_size": 16,
                "font_weight": "600",
                "line_height": 1.5,
                "letter_spacing": 1.6,
            }
        }
    }

    commands = transformer.generate_commands(
        {
            "color": [{"parts": ["color", "brand"], "value": "#112233"}],
            "font": typography_tokens,
            "button": button_tokens,
            "style": typography_tokens,
        },
        profile="local",
    )
    assert any('create-color "Brand"' in command for command in commands)
    assert any('create-font "Inter"' in command for command in commands)
    assert any('create-button-style "primary"' in command for command in commands)
    assert any('create-style "Body Regular" Text' in command for command in commands)


def test_main_supports_dry_run_and_output_file(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    input_path = tmp_path / "tokens.json"
    input_path.write_text(
        json.dumps({"color": {"brand": {"type": "color", "value": "#112233"}}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(Path(transform_tokens.__file__).resolve().parents[1])
    monkeypatch.setattr(sys, "argv", ["transform_tokens", "--input", str(input_path), "--dry-run"])
    transform_tokens.main()
    assert "Generated Commands (Dry Run)" in capsys.readouterr().out

    output_path = tmp_path / "commands.sh"
    monkeypatch.setattr(
        sys,
        "argv",
        ["transform_tokens", "--input", str(input_path), "--output", str(output_path)],
    )
    transform_tokens.main()
    assert output_path.read_text(encoding="utf-8").startswith("#!/bin/bash")
