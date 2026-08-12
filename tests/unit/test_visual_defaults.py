from bubble_mcp.visual_defaults import style_metadata_from_payload


def test_style_metadata_from_payload_supports_wrapped_bubble_export() -> None:
    metadata = style_metadata_from_payload(
        {
            "app": {
                "settings": {"client_safe": {"default_styles": {"Button": "Button_default"}}},
                "styles": {"Button_default": {"%nm": "Primary"}},
            }
        }
    )

    assert metadata["settings"]["client_safe"]["default_styles"]["Button"] == "Button_default"
    assert metadata["styles"]["Button_default"]["%nm"] == "Primary"
