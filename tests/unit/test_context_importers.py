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


def test_bubble_export_recovers_scalar_reusable_index_names(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "scalar-reusable-index.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "_id": "synthetic-app",
                "_index": {
                    "custom_name_to_id": {
                        "Visible empty reusable": "reEmpty",
                        "Stale reusable alias": "reStale",
                    },
                    "id_to_path": {"rootEmpty": "%ed.reEmpty"},
                },
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)
    reusables = [node for node in context.nodes if node.type == "reusable"]
    reusable = reusables[0]

    assert len(reusables) == 1
    assert reusable.label == "Visible empty reusable"
    assert reusable.metadata["bubble_id"] == "reEmpty"
    assert reusable.metadata["inferred_from_index"] is True
    assert reusable.metadata["root_id"] == "rootEmpty"
    assert reusable.metadata["deleted"] is None


def test_bubble_export_prefers_index_display_and_bubble_display_token(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "display-priority.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "_id": "synthetic-app",
                "pages": {
                    "pgIndex": {
                        "%d": "Visible page",
                        "%p": {"%nm": "internal_page"},
                    }
                },
                "element_definitions": {
                    "reDialog": {
                        "%p": {"%nm": "internal_reusable"},
                    }
                },
                "_index": {
                    "custom_name_to_id": {
                        "internal_reusable": {
                            "custom_id": "reDialog",
                            "display": "Visible reusable",
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)
    page = next(node for node in context.nodes if node.type == "page")
    reusable = next(node for node in context.nodes if node.type == "reusable")

    assert page.label == "Visible page"
    assert reusable.label == "Visible reusable"


def test_bubble_export_deep_merges_reusable_aliases(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "merged-reusable-aliases.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "_id": "synthetic-app",
                "element_definitions": {
                    "reDialog": {
                        "%p": {"%nm": "internal_reusable"},
                        "%el": {"elTitle": {"%x": "Text"}},
                    }
                },
                "%ed": {
                    "reDialog": {
                        "properties": {"display": "Visible reusable", "%del": True},
                        "elements": {"elButton": {"%x": "Button"}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)
    reusable = next(node for node in context.nodes if node.type == "reusable")

    assert reusable.label == "Visible reusable"
    assert reusable.metadata["children"] == ["elTitle", "elButton"]
    assert reusable.metadata["deleted"] is True


def test_bubble_export_materializes_reusable_element_paths_and_root_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bubble_file = tmp_path / "indexed-reusable-elements.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "_id": "synthetic-app",
                "_index": {
                    "custom_name_to_id": {"Dialog": "reDialog"},
                    "id_to_path": {
                        "rootDialog": "%ed.reDialog",
                        "pathParent": "%ed.reDialog.%el.elParent",
                        "pathChild": "%ed.reDialog.%el.elParent.%el.elChild",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    context = context_from_bubble_export(bubble_file)
    reusable = next(node for node in context.nodes if node.type == "reusable")
    elements = {node.metadata["bubble_id"]: node for node in context.nodes if node.type == "element"}

    assert reusable.metadata["root_id"] == "rootDialog"
    assert reusable.metadata["children"] == ["elParent"]
    assert set(elements) == {"elParent", "elChild"}
    assert elements["elParent"].metadata["path_array"] == ["%ed", "reDialog", "%el", "elParent"]
    assert elements["elChild"].metadata["path_array"] == [
        "%ed",
        "reDialog",
        "%el",
        "elParent",
        "%el",
        "elChild",
    ]


def test_crawler_context_disambiguates_duplicate_context_labels(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context = context_from_crawler_payload(
        {
            "appId": "synthetic-app",
            "pages": [
                {"id": "pgOne", "display": "Same context"},
                {"id": "pgTwo", "display": "Same context"},
            ],
            "reusables": [
                {"id": "reOne", "display": "Same reusable"},
                {"id": "reTwo", "display": "Same reusable"},
            ],
        },
        tmp_path / "crawler.json",
    )

    pages = [node for node in context.nodes if node.type == "page"]
    reusables = [node for node in context.nodes if node.type == "reusable"]

    assert {node.id for node in pages} == {
        "page:Same context:pgOne",
        "page:Same context:pgTwo",
    }
    assert {node.id for node in reusables} == {
        "reusable:Same reusable:reOne",
        "reusable:Same reusable:reTwo",
    }


def test_crawler_context_page_key_from_path_differs_from_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Regression for the login_page defect: the node lives at %p3.bVVl3 but its body
    # carries id bG4Jl. The crawled page now records the real "path" it was fetched
    # from (see detector._crawl_page); the importer must key/path elements off that,
    # not off the id.
    context = context_from_crawler_payload(
        {
            "appId": "synthetic-app",
            "pages": [
                {
                    "id": "bG4Jl",
                    "name": "login_page",
                    "path": "%p3.bVVl3",
                    "key": "bVVl3",
                    "elements": {
                        "elChild": {
                            "name": "Child",
                            "elements": {
                                "elGrandchild": {"name": "Grandchild"},
                            },
                        },
                    },
                }
            ],
        },
        tmp_path / "crawler.json",
    )

    page = next(node for node in context.nodes if node.type == "page")
    assert page.metadata["bubble_id"] == "bG4Jl"
    assert page.metadata["key"] == "bVVl3"
    assert page.metadata["path_array"] == ["%p3", "bVVl3"]

    elements = {node.metadata["bubble_id"]: node for node in context.nodes if node.type == "element"}
    assert elements["elChild"].metadata["path_array"] == ["%p3", "bVVl3", "%el", "elChild"]
    assert elements["elGrandchild"].metadata["path_array"] == [
        "%p3",
        "bVVl3",
        "%el",
        "elChild",
        "%el",
        "elGrandchild",
    ]


def test_crawler_context_page_without_path_field_falls_back_to_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # On-disk crawler indexes cached before "path" existed have no such field and must
    # keep importing exactly as before: keyed by id.
    context = context_from_crawler_payload(
        {
            "appId": "synthetic-app",
            "pages": [
                {
                    "id": "AAX",
                    "name": "index",
                    "elements": {
                        "elChild": {"name": "Child"},
                    },
                }
            ],
        },
        tmp_path / "crawler.json",
    )

    page = next(node for node in context.nodes if node.type == "page")
    assert page.metadata["bubble_id"] == "AAX"
    assert page.metadata["key"] == "AAX"
    assert page.metadata["path_array"] == ["%p3", "AAX"]

    element = next(node for node in context.nodes if node.type == "element")
    assert element.metadata["path_array"] == ["%p3", "AAX", "%el", "elChild"]


def test_crawler_context_page_key_equal_to_id_is_unchanged(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Older pages have key == id. Whether "path" is present or absent, key/path_array
    # must land the same.
    with_path = context_from_crawler_payload(
        {
            "appId": "synthetic-app",
            "pages": [{"id": "AAL", "name": "index", "path": "%p3.AAL", "key": "AAL"}],
        },
        tmp_path / "crawler-with-path.json",
    )
    without_path = context_from_crawler_payload(
        {
            "appId": "synthetic-app",
            "pages": [{"id": "AAL", "name": "index"}],
        },
        tmp_path / "crawler-without-path.json",
    )

    page_with_path = next(node for node in with_path.nodes if node.type == "page")
    page_without_path = next(node for node in without_path.nodes if node.type == "page")

    assert page_with_path.metadata["key"] == "AAL"
    assert page_with_path.metadata["path_array"] == ["%p3", "AAL"]
    assert page_without_path.metadata["key"] == "AAL"
    assert page_without_path.metadata["path_array"] == ["%p3", "AAL"]
