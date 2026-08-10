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


def test_bubble_export_recovers_reusables_from_path_index_when_definitions_are_partial(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "partial-reusables.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "_id": "synthetic-app",
                "element_definitions": {
                    "reKnown": {
                        "%p": {"%nm": "Known reusable"},
                        "%el": {"elTitle": {"%x": "Text"}},
                    }
                },
                "%ed": {
                    "reAlias": {
                        "%p": {"%nm": "Alias reusable"},
                    }
                },
                "_index": {
                    "custom_name_to_id": {
                        "known": {"custom_id": "reKnown", "name": "Known reusable"},
                        "indexed": {
                            "custom_id": "reIndexed",
                            "display": "Displayed indexed reusable",
                            "name": "Internal indexed reusable",
                        },
                    },
                    "id_to_path": {
                        "elTitle": "%ed.reKnown.%el.elTitle",
                        "indexedChild": "%ed.reIndexed.%el.indexedChild",
                        "aliasChild": "element_definitions.reAlias.%el.aliasChild",
                        "pageChild": "%p3.index.%el.pageChild",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)
    reusables = {node.metadata["bubble_id"]: node for node in context.nodes if node.type == "reusable"}

    assert set(reusables) == {"reKnown", "reAlias", "reIndexed"}
    assert reusables["reKnown"].label == "Known reusable"
    assert reusables["reKnown"].metadata["children"] == ["elTitle"]
    assert reusables["reKnown"].metadata["inferred_from_index"] is False
    assert reusables["reAlias"].label == "Alias reusable"
    assert reusables["reIndexed"].label == "Displayed indexed reusable"
    assert reusables["reIndexed"].metadata["path_array"] == ["%ed", "reIndexed"]
    assert reusables["reIndexed"].metadata["inferred_from_index"] is True


def test_bubble_export_prioritizes_display_and_preserves_deleted_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "display-and-deleted.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "_id": "synthetic-app",
                "pages": {
                    "pgIndex": {
                        "display": "Displayed page",
                        "name": "Internal page name",
                        "deleted": True,
                        "elements": {
                            "elText": {
                                "display": "Displayed text",
                                "name": "Internal text name",
                                "%x": "Text",
                                "%del": True,
                            }
                        },
                    }
                },
                "element_definitions": {
                    "reDialog": {
                        "display": "Displayed reusable",
                        "%nm": "Internal reusable name",
                        "deleted": True,
                    }
                },
                "user_types": {
                    "typeContract": {
                        "display": "Displayed data type",
                        "name": "Internal data type name",
                        "%del": True,
                    }
                },
                "option_sets": {
                    "status": {
                        "display": "Displayed option set",
                        "name": "Internal option set name",
                        "deleted": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)
    nodes = {node.type: node for node in context.nodes if node.type != "element"}
    element = next(node for node in context.nodes if node.type == "element")

    assert nodes["page"].label == "Displayed page"
    assert nodes["reusable"].label == "Displayed reusable"
    assert nodes["data_type"].label == "Displayed data type"
    assert nodes["option_set"].label == "Displayed option set"
    assert element.label == "Displayed text"
    assert all(node.metadata["deleted"] is True for node in [*nodes.values(), element])
