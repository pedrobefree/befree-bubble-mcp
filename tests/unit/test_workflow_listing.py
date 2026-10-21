import copy
import json

import pytest

from bubble_mcp.aria_runtime import bubble_cli as runtime
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


def make_cli(
    tmp_path,
    monkeypatch,
    context_type,
    body,
    suffix=(),
    intent=None,
    wire_context_id="ctx1",
    workflow=None,
    source="overlay",
    index_id="ctx1",
):
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    bucket, prefix = ("pages", "%p3") if context_type == "page" else ("element_definitions", "%ed")
    old = (
        workflow
        if workflow is not None
        else {
            "id": "wf1",
            "%x": "ButtonClicked",
            "%p": {"%ei": "btn1"},
            "actions": {"0": {"id": "action1", "%x": "OldAction"}},
        }
    )
    app = {
        bucket: {"ctx1": {"id": index_id, "name": "Context", "workflows": {"wf1": old}}},
        "_index": {"id_to_path": {index_id: f"{prefix}.{wire_context_id}"}},
    }
    app_path = tmp_path / "app.json"
    app_path.write_text(json.dumps(app))
    change = {"path_array": [prefix, wire_context_id, "%wf", "wf1", *suffix], "body": body}
    if intent:
        change["intent"] = {"name": intent}
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps({"entries": [{"changes": [change]}]}))
    cli = BubbleCLI(
        app_json_path=str(app_path),
        mutation_overlay_path=str(overlay_path) if source == "overlay" else None,
        appname="review",
    )
    if source == "runtime":
        cli._apply_changes_to_discovery_cache([change])
    return cli


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("wire_context_id", ["ctx1", "wireCtx"])
def test_overlay_actions_remain_authoritative(tmp_path, monkeypatch, context_type, wire_context_id):
    new = {"0": {"id": "action1", "%x": "NewAction"}}
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        new,
        suffix=("actions",),
        wire_context_id=wire_context_id,
    )
    rows = cli._list_context_workflows("ctx1", context_type)
    assert rows[0]["workflow"]["actions"] == new


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("wire_context_id", ["ctx1", "wireCtx"])
def test_listing_does_not_mutate_overlay(tmp_path, monkeypatch, context_type, wire_context_id):
    new = {"0": {"id": "action1", "%x": "NewAction"}}
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        new,
        suffix=("actions",),
        wire_context_id=wire_context_id,
    )
    before = copy.deepcopy(cli.discovery.data)
    cli._list_context_workflows("ctx1", context_type)
    assert cli.discovery.data == before


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("wire_context_id", ["ctx1", "wireCtx"])
def test_removed_event_stays_removed_after_overlay_reload(
    tmp_path, monkeypatch, context_type, wire_context_id
):
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        None,
        intent="RemoveEvent",
        wire_context_id=wire_context_id,
    )
    assert cli._list_context_workflows("ctx1", context_type) == []


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("wire_context_id", ["ctx1", "wireCtx"])
def test_removed_actions_stay_removed(tmp_path, monkeypatch, context_type, wire_context_id):
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        {},
        suffix=("actions",),
        wire_context_id=wire_context_id,
    )
    rows = cli._list_context_workflows("ctx1", context_type)
    assert rows[0]["workflow"]["actions"] == {}


@pytest.mark.parametrize("context_type", ["page", "reusable"])
def test_cached_event_cannot_resurrect_overlay_tombstone(tmp_path, monkeypatch, context_type):
    cli = make_cli(tmp_path, monkeypatch, context_type, None, intent="RemoveEvent")
    cli._cache_workflow_event(
        "ctx1",
        context_type,
        "wf1",
        {"id": "wf1", "%x": "ButtonClicked", "actions": {}, "%p": {"%ei": "btn1"}},
    )
    assert cli._list_context_workflows("ctx1", context_type) == []


@pytest.mark.parametrize("context_type", ["page", "reusable"])
def test_cached_actions_cannot_restore_replaced_action_map(tmp_path, monkeypatch, context_type):
    cli = make_cli(tmp_path, monkeypatch, context_type, {}, suffix=("actions",))
    cli._cache_workflow_event(
        "ctx1",
        context_type,
        "wf1",
        {
            "id": "wf1",
            "%x": "ButtonClicked",
            "actions": {"0": {"id": "action1", "%x": "OldAction"}},
            "%p": {"%ei": "btn1"},
        },
    )
    before = copy.deepcopy(cli.discovery.data)
    rows = cli._list_context_workflows("ctx1", context_type)
    assert rows[0]["workflow"]["actions"] == {}
    assert cli.discovery.data == before


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("map_key", ["parameters", "return_types"])
def test_cached_structural_maps_cannot_restore_removed_entries(
    tmp_path, monkeypatch, context_type, map_key
):
    cli = make_cli(tmp_path, monkeypatch, context_type, {}, suffix=("%p", map_key))
    cli._cache_workflow_event(
        "ctx1",
        context_type,
        "wf1",
        {"id": "wf1", "%x": "ButtonClicked", "%p": {map_key: {"removed": {"name": "old"}}}},
    )
    rows = cli._list_context_workflows("ctx1", context_type)
    assert rows[0]["workflow"]["%p"][map_key] == {}


@pytest.mark.parametrize("context_type", ["page", "reusable"])
def test_explicitly_cleared_binding_is_not_filled_from_older_root(
    tmp_path, monkeypatch, context_type
):
    cli = make_cli(
        tmp_path, monkeypatch, context_type, None, suffix=("%p", "%ei"), wire_context_id="wireCtx"
    )
    rows = cli._list_context_workflows("ctx1", context_type)
    assert rows[0]["workflow"]["%p"]["%ei"] is None


@pytest.mark.parametrize("context_type", ["page", "reusable"])
def test_newer_workflow_wins_over_older_tombstone(tmp_path, monkeypatch, context_type):
    new = {"id": "wf1", "%x": "PageLoaded", "actions": {}}
    cli = make_cli(tmp_path, monkeypatch, context_type, new, wire_context_id="wireCtx")
    # Model independently sourced roots, rather than deleting the canonical
    # workflow that now also receives index-proven overlay writes.
    bucket = "pages" if context_type == "page" else "element_definitions"
    prefix = "%p3" if context_type == "page" else "%ed"
    cli.discovery.data[prefix]["wireCtx"] = {"%wf": {"wf1": new}}
    cli.discovery.data[bucket]["ctx1"]["%wf"]["wf1"] = None
    rows = cli._list_context_workflows("ctx1", context_type)
    assert len(rows) == 1
    assert rows[0]["type"] == "PageLoaded"


@pytest.mark.parametrize("context_type", ["page", "reusable"])
def test_listing_result_is_detached_from_sources_and_cache(tmp_path, monkeypatch, context_type):
    cli = make_cli(tmp_path, monkeypatch, context_type, {}, suffix=("actions",))
    cli._cache_workflow_event(
        "ctx1", context_type, "wf1", {"id": "wf1", "%p": {"%en": "cached name"}}
    )
    before_data = copy.deepcopy(cli.discovery.data)
    before_cache = copy.deepcopy(cli._schema_events_cache())
    row = cli._list_context_workflows("ctx1", context_type)[0]
    row["workflow"]["%p"]["%en"] = "caller edit"
    row["workflow"]["actions"]["0"] = {"%x": "CallerAction"}
    assert cli.discovery.data == before_data
    assert cli._schema_events_cache() == before_cache


def complete_workflow():
    return {
        "id": "wf1",
        "%x": "PageLoaded",
        "actions": {
            "0": {"id": "a0", "%x": "First"},
            "1": {"id": "a1", "%x": "Second", "%p": {"message": "old", "keep": True}},
        },
        "%p": {
            "parameters": {"0": {"name": "first"}, "1": {"name": "second"}},
            "return_types": {"0": {"name": "first"}, "1": {"name": "second"}},
        },
    }


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("source", ["overlay", "runtime"])
@pytest.mark.parametrize("leaf", [False, True])
@pytest.mark.parametrize("index_id", ["ctx1", "rootId"])
def test_partial_action_write_keeps_siblings_and_metadata(
    tmp_path, monkeypatch, context_type, source, leaf, index_id
):
    old = complete_workflow()
    suffix = ("actions", "1", "%p", "message") if leaf else ("actions", "1")
    body = "new" if leaf else {"id": "a1", "%x": "Updated"}
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        body,
        suffix=suffix,
        wire_context_id="wireCtx",
        workflow=old,
        source=source,
        index_id=index_id,
    )
    before = copy.deepcopy(cli.discovery.data)
    workflow = cli._list_context_workflows("ctx1", context_type)[0]["workflow"]
    expected = copy.deepcopy(old["actions"])
    if leaf:
        expected["1"]["%p"]["message"] = "new"
    else:
        expected["1"] = {"id": "a1", "%x": "Updated"}
    assert workflow["actions"] == expected
    assert workflow["%x"] == "PageLoaded"
    assert cli.discovery.data == before


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("source", ["overlay", "runtime"])
@pytest.mark.parametrize("map_key", ["parameters", "return_types"])
def test_partial_structural_map_write_keeps_other_entries(
    tmp_path, monkeypatch, context_type, source, map_key
):
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        {"name": "updated"},
        suffix=("%p", map_key, "1"),
        wire_context_id="wireCtx",
        workflow=complete_workflow(),
        source=source,
    )
    workflow = cli._list_context_workflows("ctx1", context_type)[0]["workflow"]
    assert workflow["%p"][map_key] == {"0": {"name": "first"}, "1": {"name": "updated"}}


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("source", ["overlay", "runtime"])
@pytest.mark.parametrize("index_id", ["ctx1", "rootId"])
def test_delete_action_after_partial_write_preserves_other_actions(
    tmp_path, monkeypatch, context_type, source, index_id
):
    old = complete_workflow()
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        {"id": "a1", "%x": "Updated"},
        suffix=("actions", "1"),
        wire_context_id="wireCtx",
        workflow=old,
        source=source,
        index_id=index_id,
    )
    cli._cache_workflow_event("ctx1", context_type, "wf1", old)
    before = copy.deepcopy(cli.discovery.data)
    snapshots = []
    monkeypatch.setattr(runtime.logger, "log", snapshots.append)
    assert cli.delete_action(
        "Context", "1", event_ref="wf1", ref_kind="key", action_ref_kind="index", dry_run=True
    )
    payload = json.loads(snapshots[-1])
    rewrite = next(c for c in payload["changes"] if c.get("path_array", [])[-1:] == ["actions"])
    prefix = "%p3" if context_type == "page" else "%ed"
    assert rewrite["body"] == {"0": {"id": "a0", "%x": "First"}}
    assert rewrite["path_array"] == [prefix, "wireCtx", "%wf", "wf1", "actions"]
    index_update = next(
        c for c in payload["changes"] if c.get("path_array") == ["_index", "id_to_path", "a0"]
    )
    assert index_update["body"] == f"{prefix}.wireCtx.%wf.wf1.actions.0"
    assert cli.discovery.data == before


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("map_key", ["actions", "parameters", "return_types"])
def test_whole_map_replacement_after_partial_write_does_not_restore_old_entries(
    tmp_path, monkeypatch, context_type, map_key
):
    suffix = ("actions",) if map_key == "actions" else ("%p", map_key)
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        {"name": "new"},
        suffix=(*suffix, "1"),
        wire_context_id="wireCtx",
        workflow=complete_workflow(),
    )
    cli._cache_workflow_event("ctx1", context_type, "wf1", complete_workflow())
    prefix = "%p3" if context_type == "page" else "%ed"
    cli._apply_changes_to_discovery_cache(
        [
            {"path_array": [prefix, "wireCtx", "%wf", "wf1", *suffix], "body": {}},
            {
                "path_array": [prefix, "wireCtx", "%wf", "wf1", *suffix, "2"],
                "body": {"name": "only"},
            },
        ]
    )
    workflow = cli._list_context_workflows("ctx1", context_type)[0]["workflow"]
    actual = workflow["actions"] if map_key == "actions" else workflow["%p"][map_key]
    assert actual == {"2": {"name": "only"}}


@pytest.mark.parametrize("context_type", ["page", "reusable"])
@pytest.mark.parametrize("source", ["overlay", "runtime"])
def test_partial_write_preserves_normalized_workflow_properties(
    tmp_path, monkeypatch, context_type, source
):
    workflow = complete_workflow()
    workflow["properties"] = workflow.pop("%p")
    cli = make_cli(
        tmp_path,
        monkeypatch,
        context_type,
        {"name": "updated"},
        suffix=("%p", "parameters", "1"),
        wire_context_id="wireCtx",
        workflow=workflow,
        source=source,
    )
    row = cli._list_context_workflows("ctx1", context_type)[0]
    assert row["workflow"]["properties"]["parameters"] == {
        "0": {"name": "first"},
        "1": {"name": "updated"},
    }
    assert "%p" not in row["workflow"]
