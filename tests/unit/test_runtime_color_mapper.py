from bubble_mcp.aria_runtime.color_mapper import ColorMapper


def _app_colors() -> dict:
    return {
        "_id": "app",
        "settings": {
            "client_safe": {
                "color_tokens": {
                    "primary": {"%d1": "rgba(10, 20, 30, 1)"},
                    "%3": "#ffffff",
                    "ignored": {"%d1": "not-a-color"},
                },
                "color_tokens_user": {
                    "%d1": {
                        "gray50": {"rgba": "#0b141e", "%nm": "Gray 50"},
                        "deleted": {"rgba": "#000000", "%del": True},
                    }
                },
            }
        },
    }


def test_builds_system_and_custom_maps_with_name_aliases() -> None:
    mapper = ColorMapper(_app_colors())

    assert mapper.find_variable_by_name("primary") == "var(--color_primary_default)"
    assert mapper.find_variable_by_name("TEXT") == "var(--color_text_default)"
    assert mapper.find_variable_by_name("grey-50") == "var(--color_gray50_default)"
    assert mapper.find_variable_by_name(" ") is None


def test_parses_supported_colors_and_rejects_malformed_hex() -> None:
    mapper = ColorMapper({})

    assert mapper._parse_rgba("rgba(1, 2, 3, 0.5)") == (1, 2, 3, 0.5)
    assert mapper._parse_rgba("rgb(1,2,3)") == (1, 2, 3, 1.0)
    assert mapper._parse_rgba("#abc") == (170, 187, 204, 1.0)
    assert mapper._parse_rgba("#GGGGGG") is None
    assert mapper._parse_rgba("invalid") is None


def test_matching_respects_alpha_distance_sorting_and_preference() -> None:
    mapper = ColorMapper(_app_colors())

    assert mapper.find_all_matching_tokens(10, 20, 30, 0.5) == []
    matches = mapper.find_all_matching_tokens(10, 20, 30, 1.0, tolerance=3)
    assert matches == ["var(--color_primary_default)", "var(--color_gray50_default)"]
    assert mapper.find_closest_token(10, 20, 30, 1.0) == "var(--color_primary_default)"
    assert mapper.find_closest_token_rgb(10, 20, 30, preferred_key="gray 50") == (
        "var(--color_gray50_default)",
        (11, 20, 30, 1.0),
    )
    assert mapper.find_closest_token_rgb(200, 200, 200, tolerance=1) is None


def test_dynamic_tokens_are_available_by_color_and_name() -> None:
    mapper = ColorMapper({})

    mapper.add_token("brand", "#123456", friendly_name="Brand Main")
    mapper.add_token("short", "#abc")
    mapper.add_token("bad", "#GGGGGG")
    mapper.add_token("also-bad", "transparent")

    assert mapper.find_variable_by_name("brand-main") == "var(--color_brand_default)"
    assert mapper.find_closest_token(18, 52, 86, 1.0) == "var(--color_brand_default)"
    assert mapper.find_variable_by_name("bad") is None


def test_invalid_application_shape_fails_closed(capsys) -> None:  # type: ignore[no-untyped-def]
    mapper = ColorMapper({"settings": "invalid"})

    assert mapper.color_map == []
    assert "Error building map" in capsys.readouterr().out
