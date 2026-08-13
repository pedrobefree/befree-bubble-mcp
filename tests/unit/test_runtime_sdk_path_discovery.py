import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import PathDiscovery


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def discovery_with(data: dict[str, Any]) -> PathDiscovery:
    discovery = PathDiscovery()
    discovery._data = data
    return discovery


def test_alias_mapping_readers_resolve_precedence() -> None:
    discovery = PathDiscovery()
    assert discovery._read_alias_mapping([], "elements", "%el") == {}
    assert discovery._read_alias_mapping({}, "elements", "%el") == {}

    shared: dict[str, Any] = {}
    assert discovery._read_alias_mapping(
        {"elements": shared, "%el": shared}, "elements", "%el"
    ) is shared

    target = {
        "elements": {"same": {"id": "readable"}},
        "%el": {"same": {"id": "wire"}, "wire": {"id": "wire"}},
    }

    resolved = discovery._read_alias_mapping(target, "elements", "%el")

    assert resolved == {
        "same": {"id": "readable"},
        "wire": {"id": "wire"},
    }


def test_alias_mapping_reader_keeps_preferred_collision_order() -> None:
    discovery = PathDiscovery()
    target = {
        "elements": {
            "same": {"id": "readable"},
            "preferred-only": {"id": "preferred-only"},
        },
        "%el": {
            "same": {"id": "wire"},
            "alternate-only": {"id": "alternate-only"},
        },
    }

    resolved = discovery._read_alias_mapping(target, "elements", "%el")

    assert list(resolved) == ["alternate-only", "same", "preferred-only"]
    assert resolved["same"] == {"id": "readable"}


def test_alias_mapping_readers_fall_back_from_empty_preferred_mapping() -> None:
    discovery = PathDiscovery()

    assert discovery._read_nonempty_alias_mapping(
        {"properties": {}, "%p": {"%dn": "wire"}}, "properties", "%p"
    ) == {"%dn": "wire"}
    assert discovery._read_nonempty_alias_mapping(
        {"properties": {"name": "readable"}, "%p": {"%dn": "wire"}},
        "properties",
        "%p",
    ) == {"name": "readable"}


def test_sync_alias_mapping_unifies_divergent_buckets() -> None:
    discovery = PathDiscovery()
    target = {
        "elements": {"readable": {"id": "readable"}},
        "%el": {"wire": {"id": "wire"}},
    }

    synchronized = discovery._sync_alias_mapping(target, "elements", "%el")

    assert target["elements"] is synchronized
    assert target["%el"] is synchronized


def test_load_crawler_index_rejects_missing_invalid_and_empty_sources(tmp_path: Path) -> None:
    discovery = PathDiscovery()
    missing = tmp_path / "missing.json"
    corrupt = tmp_path / "corrupt.json"
    list_payload = tmp_path / "list.json"
    empty = tmp_path / "empty.json"
    corrupt.write_text("{", encoding="utf-8")
    write_json(list_payload, [])
    write_json(empty, {"pages": [None], "reusables": ["invalid"]})

    assert discovery._load_crawler_index(None) is None
    assert discovery._load_crawler_index(str(missing)) is None
    assert discovery._load_crawler_index(str(corrupt)) is None
    assert discovery._load_crawler_index(str(list_payload)) is None
    assert discovery._load_crawler_index(str(empty)) is None


def test_load_crawler_index_normalizes_all_supported_collections(tmp_path: Path) -> None:
    crawler_path = tmp_path / "crawler.json"
    write_json(
        crawler_path,
        {
            "pages": [
                {"id": "index", "name": "Home"},
                {"name": "settings"},
                {"title": "ignored"},
                None,
            ],
            "reusables": [
                {"id": "header", "name": "Header"},
                {"name": "footer"},
                None,
            ],
            "backendWorkflows": [
                {"id": "api-save", "name": "save"},
                {"name": "refresh"},
                None,
            ],
            "apiConnectorCalls": [
                {
                    "collectionId": "stripe",
                    "collectionName": "Stripe",
                    "callId": "create",
                    "callName": "Create customer",
                },
                {"collectionId": "stripe", "callId": "list"},
                {"collectionId": "stripe"},
                None,
            ],
        },
    )

    result = PathDiscovery()._load_crawler_index(str(crawler_path))

    assert result is not None
    assert set(result["pages"]) == {"index", "settings"}
    assert set(result["element_definitions"]) == {"header", "footer"}
    assert set(result["backend_workflows"]) == {"api-save", "refresh"}
    stripe = result["api_connector_collections"]["stripe"]
    assert stripe["%nm"] == "Stripe"
    assert stripe["calls"]["create"]["%nm"] == "Create customer"
    assert stripe["calls"]["list"]["%nm"] == "list"


def test_merge_crawler_enriches_contexts_without_mutating_source() -> None:
    existing_page_element = {"id": "page-existing", "type": "Text"}
    existing_reusable_element = {"id": "reuse-existing", "%dn": "Existing"}
    data = {
        "%p3": {
            "index": {
                "id": "index",
                "%el": {"page-existing": existing_page_element},
                "%wf": {"old-workflow": {"id": "old-workflow"}},
            }
        },
        "%ed": {
            "header": {
                "id": "header",
                "%el": {"reuse-existing": existing_reusable_element},
                "%wf": {},
            }
        },
        "api": {
            "save": {"id": "save", "type": "Existing", "actions": "invalid"},
            "blank": {"id": "blank", "type": ""},
        },
    }
    crawler = {
        "pages": {
            "index": {
                "elements": {
                    "length": 2,
                    "page-existing": {"id": "page-existing", "name": "Page name"},
                    "page-new": {"id": "page-new", "name": "New"},
                },
                "workflows": {
                    "old-workflow": {"id": "replacement"},
                    "new-workflow": {"id": "new-workflow"},
                },
            },
            "new-page": {"name": "New page", "elements": {}},
        },
        "element_definitions": {
            "header": {
                "elements": {
                    "length": 2,
                    "reuse-existing": {"id": "reuse-existing", "name": "Crawler name"},
                    "reuse-new": {"id": "reuse-new"},
                },
                "workflows": {"reuse-workflow": {"id": "reuse-workflow"}},
            },
            "footer": {"name": "Footer"},
        },
        "backend_workflows": {
            "save": {
                "name": "Save data",
                "trigger": "APIEvent",
                "actions": {"one": {"id": "one"}},
            },
            "refresh": {
                "name": "Refresh",
                "trigger": "RecurringEvent",
                "actions": {"two": {"id": "two"}},
            },
            "blank": {"name": "Blank", "trigger": "APIEvent"},
        },
        "api_connector_collections": {
            "stripe": {"%nm": "Stripe", "calls": {"create": {"%nm": "Create"}}}
        },
    }

    merged = PathDiscovery()._merge_crawler_into_data(data, crawler)

    assert data["%p3"]["index"]["%el"] == {"page-existing": existing_page_element}
    assert merged["pages"] is merged["%p3"]
    assert merged["element_definitions"] is merged["%ed"]
    page = merged["pages"]["index"]
    assert page["elements"] is page["%el"]
    assert page["%el"]["page-existing"]["name"] == "Page name"
    assert page["%el"]["page-new"]["id"] == "page-new"
    assert page["%wf"]["old-workflow"]["id"] == "old-workflow"
    assert page["%wf"]["new-workflow"]["id"] == "new-workflow"
    assert merged["pages"]["new-page"]["%nm"] == "New page"
    reusable = merged["element_definitions"]["header"]
    assert reusable["%el"]["reuse-existing"]["%dn"] == "Existing"
    assert reusable["%el"]["reuse-new"]["id"] == "reuse-new"
    assert merged["element_definitions"]["footer"]["%nm"] == "Footer"
    assert merged["api"]["save"]["type"] == "Existing"
    assert merged["api"]["save"]["actions"]["one"]["id"] == "one"
    assert merged["api"]["refresh"]["type"] == "RecurringEvent"
    assert merged["api"]["blank"]["type"] == "APIEvent"
    assert merged["plugin_special"] is merged["api_connector_collections"]


def test_merge_crawler_repairs_invalid_containers_and_preserves_plugin_special() -> None:
    plugin_special = {"existing": True}
    merged = PathDiscovery()._merge_crawler_into_data(
        {
            "pages": "invalid",
            "element_definitions": "invalid",
            "api": "invalid",
            "plugin_special": plugin_special,
        },
        {
            "pages": {
                "index": {
                    "elements": {"one": {"id": "one"}},
                    "workflows": {"wf": {"id": "wf"}},
                }
            },
            "element_definitions": {
                "header": {
                    "elements": {"one": {"id": "one"}},
                    "workflows": {"wf": {"id": "wf"}},
                }
            },
            "backend_workflows": {},
            "api_connector_collections": {"stripe": {"calls": {}}},
        },
    )

    assert merged["pages"]["index"]["elements"]["one"]["id"] == "one"
    assert merged["element_definitions"]["header"]["workflows"]["wf"]["id"] == "wf"
    assert merged["api"] == {}
    assert merged["plugin_special"] == plugin_special


def test_normalize_api_connector_collections_handles_existing_and_nested_shapes() -> None:
    discovery = PathDiscovery()
    existing = {"stripe": {"calls": {}}}
    existing_data = {"api_connector_collections": existing}
    assert discovery._normalize_api_connector_collections(existing_data) is existing_data
    assert existing_data["plugin_special"] is existing

    nested = {
        "settings": {
            "client_safe": {
                "apiconnector2": {
                    "stripe": {
                        "human": "Stripe API",
                        "calls": {
                            "create": {"name": "Create customer", "method": "post"},
                            "invalid": "value",
                        },
                    },
                    "fallback": {"%d": "Fallback", "calls": None},
                    "invalid": "value",
                }
            }
        }
    }
    result = discovery._normalize_api_connector_collections(nested)
    stripe = result["api_connector_collections"]["stripe"]
    assert stripe["%nm"] == stripe["%d"] == "Stripe API"
    assert stripe["calls"]["create"]["%nm"] == "Create customer"
    assert "invalid" not in stripe["calls"]
    assert result["api_connector_collections"]["fallback"]["calls"] == {}
    assert result["plugin_special"] is result["api_connector_collections"]


def test_normalize_api_connector_collections_supports_top_level_and_noop_shapes() -> None:
    discovery = PathDiscovery()
    assert discovery._normalize_api_connector_collections([]) == []  # type: ignore[arg-type,return-value]
    assert discovery._normalize_api_connector_collections({}) == {}
    assert discovery._normalize_api_connector_collections({"settings": []}) == {"settings": []}

    top_level = {"apiconnector2": {"plain": {"calls": {"ping": {}}}}}
    result = discovery._normalize_api_connector_collections(top_level)
    assert result["api_connector_collections"]["plain"]["%nm"] == "plain"
    assert result["api_connector_collections"]["plain"]["calls"]["ping"]["%nm"] == "ping"


def sample_discovery() -> PathDiscovery:
    return discovery_with(
        {
            "element_definitions": {
                "reuse": {
                    "id": "reuse",
                    "name": "Header",
                    "elements": {
                        "first-slot": {
                            "id": "first",
                            "type": "Text",
                            "name": "Title",
                            "properties": {
                                "text": {"entries": {"0": "Hello ", "1": {"dynamic": True}, "2": "World"}}
                            },
                            "elements": {},
                        },
                        "group-slot": {
                            "id": "group",
                            "type": "Group",
                            "default_name": "Content",
                            "elements": {
                                "last-slot": {
                                    "id": "last",
                                    "type": "Button",
                                    "name": "Title",
                                    "properties": {
                                        "text": {"%e": {"0": "Save"}},
                                        "icon": "feather check",
                                    },
                                },
                                "image-slot": {
                                    "id": "image",
                                    "type": "Image",
                                    "properties": {"src": {"%e": {"0": "hero.png"}}},
                                },
                            },
                        },
                    },
                }
            },
            "%ed": {
                "raw-reuse": {
                    "id": "raw-reuse",
                    "%nm": "Raw reusable",
                    "%el": {
                        "raw-title": {
                            "id": "raw-title",
                            "%x": "Text",
                            "%dn": "Raw title",
                            "%p": {
                                "text": {"%e": {"0": "Readable copy"}},
                                "%3": {"%e": {"0": "Raw copy"}},
                            },
                        }
                    },
                }
            },
            "pages": {"index": {"id": "index", "name": "Home", "elements": {}}},
            "%p3": {"raw-page": {"id": "raw-page", "%nm": "Raw page", "%el": {}}},
        }
    )


def test_context_and_name_lookup_support_standard_and_raw_aliases() -> None:
    discovery = sample_discovery()
    assert discovery._get_context_root("reuse", "reusable")["id"] == "reuse"
    assert discovery._get_context_root("raw-reuse", "reusable")["id"] == "raw-reuse"
    assert discovery._get_context_root("index", "page")["id"] == "index"
    assert discovery._get_context_root("raw-page", "page")["id"] == "raw-page"
    assert discovery._get_context_root("missing", "reusable") is None
    assert discovery._get_context_root("missing", "page") is None
    assert discovery.find_reusable("header") == "reuse"
    assert discovery.find_reusable("raw reusable") == "raw-reuse"
    assert discovery.find_page("HOME") == "index"
    assert discovery.find_page("raw page") == "raw-page"

    discovery._data = {"element_definitions": [], "pages": []}
    assert discovery.find_reusable("missing") is None
    assert discovery.find_page("missing") is None


def test_context_name_lookup_prefers_readable_aliases_for_duplicate_names() -> None:
    discovery = discovery_with(
        {
            "element_definitions": {
                "readable-reusable": {"id": "readable-reusable", "name": "Duplicate"},
            },
            "%ed": {
                "raw-reusable": {"id": "raw-reusable", "%nm": "Duplicate"},
            },
            "pages": {
                "readable-page": {"id": "readable-page", "name": "Duplicate"},
            },
            "%p3": {
                "raw-page": {"id": "raw-page", "%nm": "Duplicate"},
            },
        }
    )

    assert discovery.find_reusable("duplicate") == "readable-reusable"
    assert discovery.find_page("duplicate") == "readable-page"


@pytest.mark.parametrize(
    ("context_type", "preferred_key", "alternate_key"),
    [
        ("reusable", "element_definitions", "%ed"),
        ("page", "pages", "%p3"),
    ],
)
def test_context_root_prefers_present_empty_readable_record(
    context_type: str,
    preferred_key: str,
    alternate_key: str,
) -> None:
    preferred_root: dict[str, Any] = {}
    raw_root = {"id": "shared", "%x": "Group", "%dn": "Raw"}
    discovery = discovery_with(
        {
            preferred_key: {"shared": preferred_root},
            alternate_key: {"shared": raw_root},
        }
    )

    assert discovery._get_context_root("shared", context_type) is preferred_root


@pytest.mark.parametrize(
    ("context_type", "preferred_key", "alternate_key"),
    [
        ("reusable", "element_definitions", "%ed"),
        ("page", "pages", "%p3"),
    ],
)
def test_inject_element_mutates_present_empty_preferred_context_root(
    context_type: str,
    preferred_key: str,
    alternate_key: str,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    preferred_root: dict[str, Any] = {}
    raw_root = {"id": "shared", "%x": "Group", "%dn": "Raw"}
    discovery = discovery_with(
        {
            preferred_key: {"shared": preferred_root},
            alternate_key: {"shared": raw_root},
        }
    )
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: True)

    discovery.inject_element(
        "shared",
        context_type,
        None,
        {"id": "child", "%x": "Text", "%dn": "Child"},
        "child-slot",
    )

    assert discovery.data[preferred_key]["shared"] is preferred_root
    assert preferred_root["%el"]["child-slot"]["id"] == "child"
    assert discovery.data[alternate_key]["shared"] is raw_root
    assert "%el" not in raw_root


def test_element_lookup_handles_text_names_ids_and_match_priority() -> None:
    discovery = sample_discovery()
    assert discovery.find_element_by_text("reuse", "hello world")["id"] == "first"
    assert discovery.find_element_by_text("reuse", "hero.png")["id"] == "image"
    assert discovery.find_element_by_text("raw-reuse", "readable copy")["id"] == "raw-title"
    assert discovery.find_element_by_text("raw-reuse", "raw copy")["id"] == "raw-title"
    assert discovery.find_element_by_text("missing", "hello") is None
    assert discovery.find_element_by_text("reuse", "absent") is None

    first = discovery.find_element_by_name("reuse", "Title")
    last = discovery.find_element_by_name("reuse", "Title", prefer_last=True)
    fuzzy = discovery.find_element_by_name("reuse", "Content")
    fuzzy_prefix = discovery.find_element_by_name("reuse", "Cont")
    assert first["id"] == "first"
    assert last["id"] == "last"
    assert fuzzy["id"] == "group"
    assert fuzzy_prefix["id"] == "group"
    assert discovery.find_element_by_name("reuse", "absent") is None
    assert discovery.find_element_by_name("missing", "Title") is None
    assert discovery.find_element_by_name("raw-reuse", "Raw title")["id"] == "raw-title"

    assert discovery.find_element_by_id("reuse", "last")["path"] == [
        "elements",
        "group-slot",
        "elements",
        "last-slot",
    ]
    assert discovery.find_element_by_id("reuse", "absent") is None
    assert discovery.find_element_by_id("missing", "last") is None
    assert discovery.find_element_by_exact_name("reuse", "title")["id"] == "first"
    assert discovery.find_element_by_exact_name("reuse", "absent") is None
    assert discovery.find_element_by_exact_name("missing", "title") is None


def test_match_helpers_normalize_quotes_extract_literals_and_deduplicate() -> None:
    discovery = PathDiscovery()
    assert discovery._norm_lookup(None) == ""
    assert discovery._norm_lookup("  “Quoted” `Text`  ") == '"quoted" \'text\''
    assert discovery._plain_text_from_expr("invalid") == ""
    assert discovery._plain_text_from_expr({"entries": []}) == ""
    assert discovery._plain_text_from_expr({"entries": {"10": "!", "2": "B", "0": "A", "x": {}}}) == "AB!"
    assert discovery._element_match_candidates([]) == []  # type: ignore[arg-type]

    candidates = discovery._element_match_candidates(
        {
            "type": "Button",
            "name": "Save",
            "default_name": "save",
            "properties": {
                "element_name": "Primary",
                "text": {"entries": {"0": "Save"}},
                "%9i": "feather check",
                "src": {"entries": {"0": "button.png"}},
            },
        }
    )
    assert candidates.count("Save") == 1
    assert "Button Save" in candidates
    assert "Icon feather check" in candidates
    assert "Image button.png" in candidates


def test_list_styles_combines_defaults_custom_styles_and_filters() -> None:
    discovery = discovery_with(
        {
            "settings": {"client_safe": {"default_styles": {"Text": "Text_standard"}}},
            "styles": {
                "Button_custom": {"display": "Primary", "%x": "Button"},
                "Icon_generated": {"%d": "Generated"},
                "mystery": {"name": "Mystery"},
                "invalid": "value",
            },
        }
    )

    styles = discovery.list_styles()
    by_id = {style["id"]: style for style in styles}
    assert by_id["Text_standard"] == {
        "id": "Text_standard",
        "name": "Text (default)",
        "type": "Text",
        "is_default": True,
    }
    assert by_id["Button_custom"]["type"] == "Button"
    assert by_id["Icon_generated"]["type"] == "Icon"
    assert by_id["mystery"]["type"] == "Unknown"
    assert discovery.list_styles("primary") == [by_id["Button_custom"]]


def test_inject_element_handles_new_root_root_update_and_nested_parent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    discovery = discovery_with({})
    persisted: list[bool] = []
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: persisted.append(True) or True)

    discovery.inject_element(
        "new-reusable",
        "reusable",
        None,
        {"id": "child-id", "%x": "Text", "%dn": "Child", "%p": {"text": "value"}},
        "child-slot",
    )
    root = discovery.data["element_definitions"]["new-reusable"]
    assert root["elements"]["child-slot"]["id"] == "child-id"
    assert root["elements"] is root["%el"]
    root["elements"]["child-slot"]["elements"] = "invalid"

    discovery.inject_element(
        "new-reusable",
        "reusable",
        "child-id",
        {"id": "nested-id", "%x": "Icon", "%nm": "Nested"},
        "nested-slot",
    )
    assert root["elements"]["child-slot"]["elements"]["nested-slot"]["id"] == "nested-id"
    child = root["elements"]["child-slot"]
    assert child["elements"] is child["%el"]

    discovery.inject_element(
        "new-reusable",
        "reusable",
        None,
        {"id": "new-reusable", "%x": "Group", "%dn": "Renamed"},
    )
    assert discovery.data["element_definitions"]["new-reusable"]["name"] == "Renamed"
    assert len(persisted) == 3


@pytest.mark.parametrize(
    ("initial_data", "container_key"),
    [
        ({"element_definitions": {}}, "element_definitions"),
        ({"%ed": {}}, "%ed"),
    ],
)
def test_inject_element_uses_existing_empty_context_container(
    initial_data: dict[str, Any],
    container_key: str,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    discovery = discovery_with(initial_data)
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: True)

    discovery.inject_element(
        "new",
        "reusable",
        None,
        {"id": "child", "%x": "Text", "%dn": "Child"},
        "child-slot",
    )

    assert discovery.data[container_key]["new"]["elements"]["child-slot"]["id"] == "child"


@pytest.mark.parametrize(
    ("context_type", "preferred_key", "alternate_key", "preferred_value", "alternate_value"),
    [
        ("reusable", "element_definitions", "%ed", [], {}),
        ("page", "pages", "%p3", "invalid", {}),
        ("reusable", "element_definitions", "%ed", [], "invalid"),
        ("page", "pages", "%p3", "invalid", []),
    ],
)
def test_inject_element_repairs_invalid_top_level_context_aliases(
    context_type: str,
    preferred_key: str,
    alternate_key: str,
    preferred_value: object,
    alternate_value: object,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    discovery = discovery_with(
        {preferred_key: preferred_value, alternate_key: alternate_value}
    )
    alternate_mapping = alternate_value if isinstance(alternate_value, dict) else None
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: True)

    discovery.inject_element(
        "new",
        context_type,
        None,
        {"id": "child", "%x": "Text", "%dn": "Child"},
        "child-slot",
    )

    repaired = discovery.data[preferred_key]
    assert repaired is discovery.data[alternate_key]
    if alternate_mapping is not None:
        assert repaired is alternate_mapping
    assert repaired["new"]["%el"]["child-slot"]["id"] == "child"


def test_inject_element_supports_raw_roots_and_missing_parents(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    discovery = discovery_with({"%ed": {"raw": {"id": "raw", "%x": "Group"}}})
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: True)

    discovery.inject_element(
        "raw",
        "reusable",
        None,
        {"id": "raw-child", "%x": "Text", "%dn": "Raw child"},
        "raw-slot",
    )
    assert discovery.data["%ed"]["raw"]["%el"]["raw-slot"]["id"] == "raw-child"

    before = dict(discovery.data["%ed"]["raw"]["%el"])
    discovery.inject_element(
        "raw",
        "reusable",
        "missing-parent",
        {"id": "ignored", "%x": "Text", "%dn": "Ignored"},
    )
    assert discovery.data["%ed"]["raw"]["%el"] == before


@pytest.mark.parametrize(
    ("workflow_type", "event_type"),
    [
        ("ElementEvent", "click"),
        ("ButtonClicked", "clicked"),
        ("InputValueChanged", "input"),
        ("DropdownValueChanged", "value_changed"),
        ("PageLoaded", "page load"),
    ],
)
def test_find_workflow_for_element_supports_event_variants(
    workflow_type: str,
    event_type: str,
) -> None:
    props = {"element_id": "button", "event_type": event_type}
    if workflow_type == "PageLoaded":
        props = {}
    discovery = discovery_with(
        {
            "element_definitions": {
                "reuse": {
                    "workflows": {
                        "wf": {"id": "wf", "type": workflow_type, "properties": props}
                    }
                }
            }
        }
    )
    result = discovery.find_workflow_for_element("reuse", "button", event_type)
    assert result["id"] == "wf"
    assert result["path"] == ["workflows", "wf"]


def test_find_workflow_prefers_latest_and_falls_back_to_raw_nested_tree() -> None:
    discovery = discovery_with(
        {
            "element_definitions": {
                "reuse": {
                    "workflows": {
                        "old": {
                            "id": "old",
                            "%x": "ElementEvent",
                            "%p": {"%ei": "button", "%et": "click"},
                        },
                        "new": {
                            "id": "new",
                            "%x": "ElementEvent",
                            "%p": {"%ei": "button", "%et": "click"},
                        },
                        "invalid-properties": {
                            "id": "invalid-properties",
                            "%x": "ElementEvent",
                            "properties": "invalid",
                        },
                    }
                },
                "mixed-properties": {
                    "workflows": {
                        "mixed": {
                            "id": "mixed",
                            "type": "ElementEvent",
                            "%p": {},
                            "properties": {"element_id": "mixed-button", "event_type": "click"},
                        }
                    }
                },
            },
            "%ed": {
                "raw": {
                    "id": "raw",
                    "%x": "Group",
                    "%el": {
                        "child": {
                            "id": "child",
                            "%x": "Group",
                            "%wf": {
                                "raw-wf": {
                                    "id": "raw-wf",
                                    "%x": "ButtonClicked",
                                    "%p": {"%ei": "raw-button"},
                                }
                            },
                        }
                    },
                }
            },
        }
    )

    assert discovery.find_workflow_for_element("reuse", "button")["id"] == "new"
    raw = discovery.find_workflow_for_element("raw", "raw-button", "click")
    assert raw["id"] == "raw-wf"
    assert raw["path"] == ["%el", "child", "%wf", "raw-wf"]
    assert discovery.find_workflow_for_element("reuse", "missing") is None
    assert discovery.find_workflow_for_element("missing", "button") is None
    assert discovery.find_workflow_for_element("mixed-properties", "mixed-button")["id"] == "mixed"


def test_find_workflow_prefers_newest_root_and_nested_workflows_with_raw_fallback() -> None:
    def workflow(workflow_id: str, element_id: str) -> dict[str, Any]:
        return {
            "id": workflow_id,
            "%x": "ElementEvent",
            "%p": {"%ei": element_id, "%et": "click"},
        }

    discovery = discovery_with(
        {
            "element_definitions": {
                "reuse": {
                    "workflows": {
                        "root-old": workflow("root-old", "root-button"),
                        "root-new": workflow("root-new", "root-button"),
                    },
                    "%wf": {"root-raw": workflow("root-raw", "root-raw-button")},
                    "elements": {
                        "parent": {
                            "id": "parent",
                            "workflows": {
                                "nested-old": workflow("nested-old", "nested-button"),
                                "nested-new": workflow("nested-new", "nested-button"),
                            },
                            "%wf": {
                                "nested-raw": workflow("nested-raw", "nested-raw-button")
                            },
                        }
                    },
                }
            }
        }
    )

    assert discovery.find_workflow_for_element("reuse", "root-button")["id"] == "root-new"
    assert discovery.find_workflow_for_element("reuse", "nested-button")["id"] == "nested-new"
    assert discovery.find_workflow_for_element("reuse", "root-raw-button")["id"] == "root-raw"
    assert discovery.find_workflow_for_element("reuse", "nested-raw-button")["id"] == "nested-raw"


def test_inject_workflow_synchronizes_hybrid_aliases(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    discovery = discovery_with(
        {
            "element_definitions": {
                "hybrid": {
                    "%x": "Group",
                    "workflows": {"existing": {"id": "existing"}},
                }
            }
        }
    )
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: True)

    discovery.inject_workflow("hybrid", "button", "click", "workflow", "reusable")
    root = discovery.data["element_definitions"]["hybrid"]

    assert root["workflows"] is root["%wf"]
    assert discovery.find_workflow_for_element("hybrid", "button")["id"] == "workflow"


def test_list_and_inject_workflows_support_standard_and_raw_contexts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    discovery = discovery_with(
        {
            "element_definitions": {
                "reuse": {
                    "elements": {
                        "one": {
                            "id": "one",
                            "elements": {"two": {"id": "two"}},
                        },
                        "invalid": "value",
                    }
                },
                "invalid-root": {"id": "invalid-root", "elements": "invalid"},
                "hybrid": {
                    "%x": "Group",
                    "elements": {
                        "standard": {
                            "id": "standard",
                            "elements": {"nested-standard": {"id": "nested-standard"}},
                            "%el": {"nested-wire": {"id": "nested-wire"}},
                        }
                    },
                    "%el": {"wire": {"id": "wire", "%x": "Text"}},
                    "workflows": {
                        "existing": {"id": "existing", "%x": "PageLoaded", "%p": {}}
                    },
                },
            },
            "%ed": {
                "raw": {
                    "id": "raw",
                    "%x": "Group",
                    "%el": {"raw-one": {"id": "raw-one", "%x": "Text"}},
                }
            },
            "pages": {"index": {"id": "index", "elements": {}}},
        }
    )
    persisted: list[bool] = []
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: persisted.append(True) or True)

    assert [item["id"] for item in discovery.list_elements("reuse")] == ["one", "two"]
    assert discovery.list_elements("missing") == []
    assert discovery.list_elements("invalid-root") == []
    assert discovery.list_elements("raw") == [
        {
            "path": ["%el", "raw-one"],
            "id": "raw-one",
            "element": {"id": "raw-one", "%x": "Text"},
        }
    ]
    assert [item["id"] for item in discovery.list_elements("hybrid")] == [
        "wire",
        "standard",
        "nested-wire",
        "nested-standard",
    ]

    discovery.inject_workflow("reuse", "one", "click", "wf", "reusable")
    assert discovery.data["element_definitions"]["reuse"]["workflows"]["wf"]["%p"] == {
        "%ei": "one",
        "%et": "click",
    }
    custom = {"%x": "PageLoaded"}
    discovery.inject_workflow("raw", "raw-one", "load", "raw-wf", "reusable", custom)
    assert discovery.data["%ed"]["raw"]["%wf"]["raw-wf"] == {
        "%x": "PageLoaded",
        "id": "raw-wf",
        "actions": {},
    }
    discovery.inject_workflow("hybrid", "standard", "click", "hybrid-wf", "reusable")
    hybrid = discovery.data["element_definitions"]["hybrid"]
    assert hybrid["workflows"] is hybrid["%wf"]
    assert discovery.find_workflow_for_element("hybrid", "standard")["id"] == "hybrid-wf"
    discovery.inject_workflow("missing", "one", "click", "ignored", "reusable")
    assert len(persisted) == 3


def test_path_and_element_accessors_normalize_wire_aliases() -> None:
    discovery = PathDiscovery()
    assert discovery.build_path_array(
        "reuse",
        ["elements", "slot", "properties", "text"],
    ) == ["%ed", "reuse", "%el", "slot", "%p", "%3"]
    assert discovery.build_path_array("index", ["workflows", 1, "name"], "page") == [
        "%p3",
        "index",
        "%wf",
        "1",
        "%nm",
    ]
    assert discovery.get_element_style({"style": "Style_readable", "%s1": "Style_wire"}) == "Style_readable"
    assert discovery.get_element_style({"%s1": "Style_wire"}) == "Style_wire"
    assert discovery.get_element_properties({"properties": {"name": "readable"}}) == {
        "name": "readable"
    }
    assert discovery.get_element_properties({"%p": {"%dn": "wire"}}) == {"%dn": "wire"}
    assert discovery.get_element_properties({"properties": {}, "%p": {"%dn": "wire"}}) == {
        "%dn": "wire"
    }
    assert discovery.get_element_properties(
        {"properties": {"name": "readable"}, "%p": {"%dn": "wire"}}
    ) == {"name": "readable"}
    assert discovery.get_element_properties([]) == {}  # type: ignore[arg-type]
