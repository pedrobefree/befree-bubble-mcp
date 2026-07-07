import json

from bubble_mcp.context.importers import context_from_bubble_export, context_from_crawler_payload


def test_crawler_context_preserves_style_metadata(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context = context_from_crawler_payload(
        {
            "appId": "synthetic-app",
            "settings": {
                "client_safe": {
                    "default_styles": {
                        "Button": "Button_default",
                    }
                }
            },
            "styles": {
                "Button_default": {
                    "name": "Primary Button",
                    "type": "Button",
                }
            },
        },
        tmp_path / "crawler.json",
    )

    assert context.metadata["default_styles"]["Button"] == "Button_default"
    assert context.metadata["styles"]["Button_default"]["name"] == "Primary Button"


def test_bubble_export_context_preserves_style_metadata(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "app.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "app": {
                    "appname": "synthetic-app",
                    "settings": {
                        "client_safe": {
                            "default_styles": {
                                "Button": "Button_default",
                            }
                        }
                    },
                    "styles": {
                        "Button_default": {
                            "name": "Primary Button",
                            "type": "Button",
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)

    assert context.metadata["default_styles"]["Button"] == "Button_default"
    assert context.metadata["styles"]["Button_default"]["type"] == "Button"
