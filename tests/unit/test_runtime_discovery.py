import json
import os
import pickle
from copy import deepcopy
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import PathDiscovery
from bubble_mcp import runtime_discovery
from bubble_mcp.runtime_discovery import DiscoveryDataBoundary


class RecordingLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warning(self, message: str) -> None:
        self.messages.append(message)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def test_path_discovery_prefers_bubble_export_over_consolelog(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    consolelog_path = tmp_path / "consolelog.json"
    _write_json(app_path, {"marker": "bubble"})
    _write_json(consolelog_path, {"marker": "consolelog"})

    discovery = PathDiscovery(str(app_path), str(consolelog_path))

    assert discovery.data["marker"] == "bubble"
    assert discovery.source_path == str(app_path)


def test_path_discovery_falls_back_from_corrupt_export_to_consolelog(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    consolelog_path = tmp_path / "consolelog.json"
    app_path.write_text("{", encoding="utf-8")
    _write_json(consolelog_path, {"marker": "consolelog"})

    discovery = PathDiscovery(str(app_path), str(consolelog_path))

    assert discovery.data["marker"] == "consolelog"
    assert discovery.source_path == str(consolelog_path)


def test_path_discovery_keeps_consolelog_source_after_enrichment(tmp_path: Path) -> None:
    consolelog_path = tmp_path / "consolelog.json"
    crawler_path = tmp_path / "crawler.json"
    overlay_path = tmp_path / "overlay.json"
    _write_json(consolelog_path, {"pages": {}})
    _write_json(crawler_path, {"pages": [{"id": "index", "name": "index"}]})
    _write_json(
        overlay_path,
        {
            "entries": [
                {
                    "changes": [
                        {
                            "intent": {"name": "CreatePage"},
                            "path_array": ["pages", "overlay-page"],
                            "body": {"id": "overlay-page", "%nm": "Overlay page"},
                        }
                    ]
                }
            ]
        },
    )

    discovery = PathDiscovery(
        None,
        str(consolelog_path),
        str(crawler_path),
        str(overlay_path),
    )

    assert discovery.data["pages"]["index"]["%nm"] == "index"
    assert discovery.data["pages"]["overlay-page"]["%nm"] == "Overlay page"
    assert discovery.source_path == str(consolelog_path)


def test_path_discovery_ignores_corrupt_disk_cache(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"marker": "source"})
    discovery = PathDiscovery(str(app_path))
    assert discovery.data["marker"] == "source"

    cache_path = Path(f"{app_path}.parsed-cache.pkl")
    cache_path.write_bytes(b"not a pickle")

    reloaded = PathDiscovery(str(app_path))
    assert reloaded.data["marker"] == "source"


def test_path_discovery_refresh_bypasses_unchanged_disk_cache_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_CLI_DISCOVERY_CACHE", "1")
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"marker": "first"})
    original_stat = app_path.stat()
    discovery = PathDiscovery(str(app_path))
    assert discovery.data["marker"] == "first"

    _write_json(app_path, {"marker": "other"})
    assert app_path.stat().st_size == original_stat.st_size
    os.utime(app_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert discovery.refresh()["marker"] == "other"


def test_path_discovery_overlay_deletes_aliased_page_records(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    overlay_path = tmp_path / "overlay.json"
    page = {"id": "page-id", "%nm": "Page name"}
    _write_json(app_path, {"pages": {"page-id": page}, "%p3": {"Page name": page}})
    _write_json(
        overlay_path,
        {
            "entries": [
                {
                    "changes": [
                        {
                            "intent": {"name": "DeletePage"},
                            "path_array": ["pages", "page-id", "%del"],
                            "body": True,
                        }
                    ]
                }
            ]
        },
    )

    discovery = PathDiscovery(str(app_path), mutation_overlay_path=str(overlay_path))

    assert discovery.data["pages"] == {}
    assert discovery.data["%p3"] == {}


def test_path_discovery_persists_enriched_consolelog_cache(tmp_path: Path) -> None:
    consolelog_path = tmp_path / "consolelog.json"
    crawler_path = tmp_path / "crawler.json"
    _write_json(consolelog_path, {"pages": {}})
    _write_json(crawler_path, {"pages": [{"id": "index", "name": "index"}]})
    discovery = PathDiscovery(None, str(consolelog_path), str(crawler_path))

    assert discovery.data["pages"]["index"]["%nm"] == "index"
    assert discovery.persist_disk_cache() is True
    assert Path(f"{consolelog_path}.parsed-cache.pkl").exists()


def test_path_discovery_persists_injected_workflow_across_instances(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"element_definitions": {"reuse": {"elements": {}}}})
    discovery = PathDiscovery(str(app_path))
    _ = discovery.data

    discovery.inject_workflow("reuse", "button", "click", "workflow", "reusable")

    reloaded = PathDiscovery(str(app_path))
    result = reloaded.find_workflow_for_element("reuse", "button", "click")
    assert result is not None
    assert result["id"] == "workflow"
    root = reloaded.data["element_definitions"]["reuse"]
    assert root["workflows"] is root["%wf"]


@pytest.mark.parametrize(
    ("context_type", "container_key"),
    [("reusable", "element_definitions"), ("page", "pages")],
)
def test_path_discovery_root_update_preserves_aliased_children_across_instances(
    tmp_path: Path,
    context_type: str,
    container_key: str,
) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(
        app_path,
        {
            container_key: {
                "root": {
                    "id": "root",
                    "elements": {"readable-child": {"id": "readable-child"}},
                    "%el": {"wire-child": {"id": "wire-child"}},
                }
            }
        },
    )
    discovery = PathDiscovery(str(app_path))
    _ = discovery.data

    discovery.inject_element("root", context_type, None, {"id": "root", "%x": "Group", "%dn": "Updated"})

    root = discovery.data[container_key]["root"]
    assert root["elements"] is root["%el"]
    assert set(root["elements"]) == {"readable-child", "wire-child"}

    reloaded = PathDiscovery(str(app_path))
    persisted_root = reloaded.data[container_key]["root"]
    assert persisted_root["elements"] is persisted_root["%el"]
    assert set(persisted_root["elements"]) == {"readable-child", "wire-child"}


def test_path_discovery_nested_injection_synchronizes_distinct_ancestor_aliases(
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(
        app_path,
        {
            "element_definitions": {
                "reuse": {
                    "id": "reuse",
                    "elements": {
                        "parent-slot": {"id": "parent", "elements": {"readable": {}}}
                    },
                    "%el": {
                        "parent-slot": {"id": "parent", "%el": {"wire": {}}}
                    },
                }
            }
        },
    )
    discovery = PathDiscovery(str(app_path))
    _ = discovery.data

    discovery.inject_element(
        "reuse",
        "reusable",
        "parent",
        {"id": "child", "%x": "Text", "%dn": "Child"},
        "child-slot",
    )

    reloaded = PathDiscovery(str(app_path))
    root = reloaded.data["element_definitions"]["reuse"]
    parent = root["%el"]["parent-slot"]
    assert parent["elements"] is parent["%el"]
    assert parent["%el"]["child-slot"]["id"] == "child"
    assert reloaded.list_elements("reuse")[-1]["path"] == [
        "%el",
        "parent-slot",
        "%el",
        "child-slot",
    ]


def test_path_discovery_injected_custom_workflow_isolated_from_caller_and_cache(
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"element_definitions": {"reuse": {"id": "reuse"}}})
    discovery = PathDiscovery(str(app_path))
    _ = discovery.data
    workflow_obj = {
        "%x": "ElementEvent",
        "%p": {"%ei": "button", "%et": "click"},
        "actions": {"first": {"id": "first"}},
    }

    discovery.inject_workflow(
        "reuse", "button", "click", "workflow", "reusable", workflow_obj
    )
    workflow_obj["%p"]["%ei"] = "mutated"
    workflow_obj["actions"]["first"]["id"] = "mutated"

    live = discovery.data["element_definitions"]["reuse"]["%wf"]["workflow"]
    reloaded = PathDiscovery(str(app_path))
    persisted = reloaded.data["element_definitions"]["reuse"]["%wf"]["workflow"]
    expected = {
        "%x": "ElementEvent",
        "%p": {"%ei": "button", "%et": "click"},
        "actions": {"first": {"id": "first"}},
        "id": "workflow",
    }
    assert live == expected
    assert persisted == expected


def test_path_discovery_nested_injection_leaves_unrelated_hybrid_siblings_untouched(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    sibling_readable = {"readable-child": {"id": "readable-child"}}
    sibling_wire = {"wire-child": {"id": "wire-child"}}
    sibling = {
        "id": "sibling",
        "elements": sibling_readable,
        "%el": sibling_wire,
    }
    discovery = PathDiscovery()
    discovery._data = {
        "element_definitions": {
            "reuse": {
                "id": "reuse",
                "elements": {
                    "sibling-slot": sibling,
                    "target-slot": {"id": "target", "elements": {}},
                },
            }
        }
    }
    persisted: list[bool] = []
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: persisted.append(True) or True)

    discovery.inject_element(
        "reuse",
        "reusable",
        "target",
        {"id": "child", "%x": "Text", "%dn": "Child"},
        "child-slot",
    )

    assert sibling["elements"] is sibling_readable
    assert sibling["%el"] is sibling_wire
    assert sibling["elements"] is not sibling["%el"]
    assert sibling["elements"] == {"readable-child": {"id": "readable-child"}}
    assert sibling["%el"] == {"wire-child": {"id": "wire-child"}}
    assert persisted == [True]


def test_path_discovery_missing_nested_parent_does_not_mutate_or_persist(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    discovery = PathDiscovery()
    discovery._data = {
        "element_definitions": {
            "reuse": {
                "id": "reuse",
                "elements": {"readable-slot": {"id": "readable"}},
                "%el": {"wire-slot": {"id": "wire"}},
            }
        }
    }
    before = deepcopy(discovery.data)
    root = discovery.data["element_definitions"]["reuse"]
    readable = root["elements"]
    wire = root["%el"]
    persisted: list[bool] = []
    monkeypatch.setattr(discovery, "persist_disk_cache", lambda: persisted.append(True) or True)

    discovery.inject_element(
        "reuse",
        "reusable",
        "missing-parent",
        {"id": "child", "%x": "Text", "%dn": "Child"},
        "child-slot",
    )

    assert discovery.data == before
    assert root["elements"] is readable
    assert root["%el"] is wire
    assert root["elements"] is not root["%el"]
    assert persisted == []


def test_path_discovery_cache_can_be_disabled(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_CLI_DISCOVERY_CACHE", "off")
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"marker": "source"})
    discovery = PathDiscovery(str(app_path))

    assert discovery.data["marker"] == "source"
    assert discovery.persist_disk_cache() is False
    assert not Path(f"{app_path}.parsed-cache.pkl").exists()


def test_path_discovery_handles_missing_sources() -> None:
    discovery = PathDiscovery()

    assert discovery.data == {}
    assert discovery.source_path is None
    assert discovery.persist_disk_cache() is False


def test_path_discovery_ignores_corrupt_overlay(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    overlay_path = tmp_path / "overlay.json"
    _write_json(app_path, {"marker": "source"})
    overlay_path.write_text("{", encoding="utf-8")

    discovery = PathDiscovery(str(app_path), mutation_overlay_path=str(overlay_path))

    assert discovery.data["marker"] == "source"


def test_path_discovery_overlay_creates_nested_values(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    overlay_path = tmp_path / "overlay.json"
    _write_json(app_path, {})
    _write_json(
        overlay_path,
        {
            "entries": [
                {
                    "changes": [
                        {
                            "intent": {"name": "SetData"},
                            "path_array": ["settings", "client_safe", "flag"],
                            "body": True,
                        }
                    ]
                }
            ]
        },
    )

    discovery = PathDiscovery(str(app_path), mutation_overlay_path=str(overlay_path))

    assert discovery.data["settings"]["client_safe"]["flag"] is True


def test_discovery_boundary_default_hooks_are_noops() -> None:
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    payload = {"marker": "source"}

    assert boundary._load_crawler_index(None) is None
    assert boundary._merge_crawler_into_data(payload, {"pages": {}}) is payload
    assert boundary._normalize_api_connector_collections(payload) is payload


def test_discovery_boundary_handles_missing_or_invalid_overlay_shapes(tmp_path: Path) -> None:
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    list_overlay = tmp_path / "list.json"
    invalid_entries = tmp_path / "invalid-entries.json"
    _write_json(list_overlay, [])
    _write_json(invalid_entries, {"entries": "invalid"})

    assert boundary._load_mutation_overlay(None) == []
    assert boundary._load_mutation_overlay(str(list_overlay)) == []
    assert boundary._load_mutation_overlay(str(invalid_entries)) == []


def test_discovery_boundary_overlay_helpers_ignore_malformed_changes() -> None:
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    target = {"nested": {"value": True}, "not-a-dict": "value"}

    assert boundary._normalize_overlay_path_array("invalid") == []
    assert boundary._normalize_overlay_path_array([None, "", 0, 1.5]) == ["0", "1.5"]
    boundary._set_nested_overlay_value(target, [], True)
    boundary._set_nested_overlay_value(target, ["not-a-dict", "created"], True)
    boundary._delete_nested_overlay_value(target, [])
    boundary._delete_nested_overlay_value(target, ["missing", "value"])
    boundary._delete_overlay_value(target, ["nested", "value"])

    result = boundary._apply_mutation_overlay(
        target,
        [
            {"changes": "invalid"},
            {
                "changes": [
                    None,
                    {"path_array": "invalid"},
                    {"path_array": ["untouched"], "intent": "invalid"},
                ]
            },
        ],
    )

    assert result["not-a-dict"] == {"created": True}
    assert "value" not in result["nested"]
    assert "untouched" not in result


def test_discovery_boundary_deletes_aliased_reusable_records() -> None:
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    reusable = {"id": "reusable-id", "%nm": "Reusable name"}
    target = {
        "element_definitions": {"reusable-id": reusable},
        "%ed": {"Reusable name": reusable},
    }

    boundary._delete_overlay_value(target, ["element_definitions", "reusable-id"])

    assert target["element_definitions"] == {}
    assert target["%ed"] == {}


def test_discovery_boundary_deletes_record_found_only_by_value_alias() -> None:
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    target = {
        "pages": {
            "unmatched": {"id": "other-id"},
            "different-key": {"id": "target-id", "%nm": "Target"},
        }
    }

    boundary._delete_aliased_overlay_record(target, ["pages"], "target-id")

    assert target["pages"] == {"unmatched": {"id": "other-id"}}


def test_discovery_boundary_rejects_non_object_sources(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    _write_json(source, [])

    with pytest.raises(ValueError, match="must contain a JSON object"):
        DiscoveryDataBoundary._read_json_object(str(source))


def test_discovery_boundary_cache_write_failure_is_best_effort(tmp_path: Path) -> None:
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    unavailable_cache = tmp_path / "missing" / "cache.pkl"

    assert (
        boundary._write_disk_cache(
            str(unavailable_cache),
            source_mtime_ns=0,
            source_size=0,
            data={"marker": "source"},
        )
        is False
    )


def test_discovery_boundary_removes_temporary_cache_after_replace_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    cache_path = tmp_path / "cache.pkl"

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(runtime_discovery.os, "replace", fail_replace)

    assert (
        boundary._write_disk_cache(
            str(cache_path),
            source_mtime_ns=0,
            source_size=0,
            data={"marker": "source"},
        )
        is False
    )
    assert list(tmp_path.iterdir()) == []


def test_discovery_boundary_ignores_cleanup_failure_after_cache_error(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())
    cache_path = tmp_path / "cache.pkl"

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    def fail_unlink(_path: Path) -> None:
        raise OSError("unlink failed")

    monkeypatch.setattr(runtime_discovery.os, "replace", fail_replace)
    monkeypatch.setattr(Path, "unlink", fail_unlink)

    assert (
        boundary._write_disk_cache(
            str(cache_path),
            source_mtime_ns=0,
            source_size=0,
            data={"marker": "source"},
        )
        is False
    )

    monkeypatch.undo()
    for temporary_file in tmp_path.iterdir():
        temporary_file.unlink()


def test_discovery_boundary_uses_valid_disk_cache(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.json"
    _write_json(source, {"marker": "cached"})
    first = DiscoveryDataBoundary(str(source), logger=RecordingLogger())
    assert first.data["marker"] == "cached"

    second = DiscoveryDataBoundary(str(source), logger=RecordingLogger())

    def unexpected_source_read(_source_path: str) -> dict[str, object]:
        raise AssertionError("valid cache should avoid reparsing the source")

    monkeypatch.setattr(second, "_read_json_object", unexpected_source_read)

    assert second.data["marker"] == "cached"


@pytest.mark.parametrize(
    "cache_payload",
    [
        [],
        {"__meta__": {}, "data": {"marker": "stale"}},
    ],
)
def test_discovery_boundary_ignores_structurally_stale_cache(
    tmp_path: Path,
    cache_payload: object,
) -> None:
    source = tmp_path / "source.json"
    _write_json(source, {"marker": "source"})
    cache_path = Path(f"{source}.parsed-cache.pkl")
    with cache_path.open("wb") as handle:
        pickle.dump(cache_payload, handle)

    boundary = DiscoveryDataBoundary(str(source), logger=RecordingLogger())

    assert boundary.data["marker"] == "source"


def test_discovery_boundary_reads_source_when_metadata_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.json"
    _write_json(source, {"marker": "source"})
    boundary = DiscoveryDataBoundary(logger=RecordingLogger())

    def unavailable_metadata(_source_path: str) -> tuple[int, int]:
        raise OSError("metadata unavailable")

    monkeypatch.setattr(boundary, "_source_metadata", unavailable_metadata)

    assert boundary._load_json_with_disk_cache(str(source))["marker"] == "source"


def test_discovery_boundary_lazy_source_and_persist_metadata_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "source.json"
    _write_json(source, {"marker": "source"})
    boundary = DiscoveryDataBoundary(str(source), logger=RecordingLogger())

    assert boundary.source_path == str(source)

    def unavailable_metadata(_source_path: str) -> tuple[int, int]:
        raise OSError("metadata unavailable")

    monkeypatch.setattr(boundary, "_source_metadata", unavailable_metadata)
    assert boundary.persist_disk_cache() is False


def test_discovery_boundary_ignores_empty_enrichment_hooks(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    crawler = tmp_path / "crawler.json"
    _write_json(source, {"marker": "source"})
    _write_json(crawler, {"pages": []})
    boundary = DiscoveryDataBoundary(
        str(source),
        crawler_index_path=str(crawler),
        logger=RecordingLogger(),
    )

    assert boundary._apply_mutation_overlay(boundary.data, []) is boundary.data
    assert boundary.data["marker"] == "source"
