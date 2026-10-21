"""The read -> patch -> write -> re-read -> compare cycle, with no browser and no Bubble."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.execution.node_edit import (
    build_patch_changes,
    build_reorder_changes,
    edit_live_node,
)

# Decoded/encoded pair for one real Bubble action, captured 2026-08-26 from live editor
# traffic: docs/session-findings-2026-08-26.md. `_raw()` is what read_live_node now reads with,
# so every happy-path fixture below is spelled in that ENCODED key space (%x/%p/%e/%n/%nm/%ei);
# a body still spelled in the decoded (export) key space is what `_assert_encoded_node_roots`
# must refuse, exercised directly against this same golden pair further down.
GOLDEN_ACTION_PAIR = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "expressions"
    / "action-encoding-pair-golden.json"
)


def _golden_action_pair() -> dict[str, Any]:
    return json.loads(GOLDEN_ACTION_PAIR.read_text(encoding="utf-8"))


def _action() -> dict[str, Any]:
    """A node as ``read_live_node`` returns it: encoded (``_raw()``), root and interior alike."""

    return {
        "id": "act-1",
        "%x": "ChangeThing",
        "%p": {
            "to_change": {
                "%x": "APIEventParameter",
                "is_slidable": False,
                "%p": {
                    "btype_id": "custom.client",
                    "event_id": "ev-1",
                    "param_id": "Client",
                    "param_name": "Client",
                },
            }
        },
    }


class _Reader:
    """Returns a fresh copy of whatever the fake editor currently holds."""

    def __init__(self, node: dict[str, Any]) -> None:
        self.node = node
        self.calls = 0
        self.app_versions: list[Any] = []

    def __call__(self, profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        self.app_versions.append(kwargs.get("app_version"))
        return {
            "ok": True,
            "pointer": list(pointer),
            "node": copy.deepcopy(self.node),
            "app_id": "mcp-test-app",
        }


def _writer_that_applies(reader: _Reader, *, drop_key: str | None = None):  # type: ignore[no-untyped-def]
    """A fake write endpoint that stores the body, optionally losing one key on the way.

    The body arrives already encoded (nothing in this module translates it any more), so it is
    stored back exactly as written - no decode-on-the-way-in either.
    """

    def write(payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        if not dry_run:
            body = copy.deepcopy(payload["changes"][0]["body"])
            if drop_key is not None:
                body["%p"]["to_change"]["%p"].pop(drop_key, None)
            reader.node = body
        return {"ok": True, "dry_run": dry_run, "request": {"payload": payload}}

    return write


def test_patch_previews_without_writing_when_execute_is_false() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is True
    assert result["execute"] is False
    assert "verified" not in result
    assert reader.calls == 1
    change = result["write"]["request"]["payload"]["changes"][0]
    assert change["path_array"] == ["api", "wf-1", "actions", "0"]
    assert change["body"]["%x"] == "ChangeThing"
    assert change["body"]["%p"]["to_change"]["%p"]["param_id"] == "Order"


def test_patch_verifies_the_write_by_reading_the_node_back() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=True,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["verified"] is True
    assert result["divergence"] is None
    assert reader.calls == 2


def test_patch_names_the_path_where_a_lossy_write_diverged() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=True,
        reader=reader,
        writer=_writer_that_applies(reader, drop_key="btype_id"),
    )

    assert result["verified"] is False
    assert result["divergence"] == "%p.to_change.%p.btype_id"


def test_patch_refuses_a_leaf_pointer_that_does_not_exist() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "nope"],
        patch={"param_id": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "pointer_not_resolved"
    assert "nope" in result["message"]


def test_patch_propagates_a_failed_read_untouched() -> None:
    def failing_reader(profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        return {"ok": False, "error": "pointer_not_found", "pointer": list(pointer)}

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "nope"],
        op="patch",
        leaf_pointer=["properties"],
        patch={"a": 1},
        reader=failing_reader,
        writer=lambda *a, **k: None,
    )

    assert result == {"ok": False, "error": "pointer_not_found", "pointer": ["api", "nope"]}


def test_unknown_op_is_refused_before_anything_is_read() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="rewrite",
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "unknown_op"
    assert reader.calls == 0


def _actions_map() -> dict[str, Any]:
    """Actions as ``read_live_node`` returns them: each entry already encoded at its root."""

    return {
        "0": {"id": "act-a", "%x": "SetCustomState", "%p": {"value": 1}},
        "1": {"id": "act-b", "%x": "SetCustomState", "%p": {"value": 2}},
        "2": {"id": "act-c", "%x": "SetCustomState", "%p": {"value": 3}},
    }


def _map_writer(reader: _Reader):  # type: ignore[no-untyped-def]
    def write(payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        if not dry_run:
            reader.node = copy.deepcopy(payload["changes"][0]["body"])
        return {"ok": True, "dry_run": dry_run, "request": {"payload": payload}}

    return write


def test_reorder_renumbers_the_map_and_leaves_each_encoded_action_root_untouched() -> None:
    """No encode step runs any more: every entry arrives from the read already encoded, and

    reorder only renumbers keys - it must never touch %x/%p.
    """

    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    body = result["write"]["request"]["payload"]["changes"][0]["body"]
    assert list(body) == ["0", "1", "2"]
    assert [entry["id"] for entry in body.values()] == ["act-c", "act-a", "act-b"]
    assert all("%x" in entry and "%p" in entry for entry in body.values())


def test_reorder_repoints_the_index_at_every_moved_action() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    changes = result["write"]["request"]["payload"]["changes"]
    index_changes = [change for change in changes if change["intent"]["name"] == "Update index"]
    assert [(change["path_array"], change["body"]) for change in index_changes] == [
        (["_index", "id_to_path", "act-c"], "api.wf-1.actions.0"),
        (["_index", "id_to_path", "act-a"], "api.wf-1.actions.1"),
        (["_index", "id_to_path", "act-b"], "api.wf-1.actions.2"),
    ]


def test_reorder_verifies_by_reading_the_map_back() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=True,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["verified"] is True
    assert result["divergence"] is None


def test_reorder_refuses_an_order_that_would_drop_a_step() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert "1" in result["message"]


def test_patch_change_carries_a_session_id_and_a_setdata_intent() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    change = result["write"]["request"]["payload"]["changes"][0]
    assert change["session_id"]
    assert change["intent"]["name"] == "SetData"
    assert change["intent"]["source_appname"] == ""
    assert isinstance(change["intent"]["id"], int)


def test_reorder_changes_all_share_one_session_id() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    changes = result["write"]["request"]["payload"]["changes"]
    session_ids = {change["session_id"] for change in changes}
    assert len(session_ids) == 1
    assert all(session_id for session_id in session_ids)


def test_reorder_update_index_intent_carries_only_a_name() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    changes = result["write"]["request"]["payload"]["changes"]
    index_changes = [change for change in changes if change["intent"]["name"] == "Update index"]
    assert index_changes
    for change in index_changes:
        assert change["session_id"]
        assert change["intent"] == {"name": "Update index"}


def test_patch_refuses_a_pointer_that_addresses_a_container_of_actions() -> None:
    """leaf_pointer resolves against a single node's own fields, not a keyed collection."""

    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="patch",
        leaf_pointer=["1", "%p"],
        patch={"value": 99},
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert "container" in result["message"]


def test_patch_refuses_a_workflow_root_read_in_the_decoded_form() -> None:
    """A caller who hands in a decoded node - e.g. built from a ``.bubble`` export rather than

    read live - must be refused, not silently written. ``read_live_node`` itself never
    produces this shape any more (it reads with ``_raw()``); this is the guard's own defense
    against a caller that bypasses the read.
    """

    workflow = {
        "type": "APIEvent",
        "properties": {"name": "wf"},
        "actions": {"0": {"id": "act-a", "type": "SetCustomState", "properties": {"v": 1}}},
    }
    reader = _Reader(workflow)

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1"],
        op="patch",
        leaf_pointer=["properties"],
        patch={"name": "renamed"},
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert "decoded node root" in result["message"]


def test_the_guard_refuses_the_golden_actions_decoded_form_directly() -> None:
    """The exact real action this design used to mis-translate - decoded, as ``raw()`` (not

    ``_raw()``) returns it - must still be refused by the safety net, using the actual golden
    fixture rather than a synthetic one: docs/session-findings-2026-08-26.md,
    tests/fixtures/expressions/action-encoding-pair-golden.json.
    """

    decoded = _golden_action_pair()["appquery_raw_decoded"]

    with pytest.raises(ValueError, match="decoded node root"):
        build_patch_changes(["api", "wf-1", "actions", "0"], decoded, "sid-1")


def test_patch_leaves_the_deep_encoding_of_a_real_action_untouched() -> None:
    """Realistic encoded fixture, not synthetic: a real ResetPassword action captured from

    live editor traffic, with %e/%n/%nm/%ei encoding well past the root (the whole reason the
    old root-only ``encode_node_root`` design broke). Patching one leaf must leave the rest of
    that deep encoding - including the sibling ``new_password_again`` chain - byte-identical.
    """

    golden_action = _golden_action_pair()["appquery_underscore_raw_encoded"]
    reader = _Reader(golden_action)

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "new_password", "%e", "0", "%p"],
        patch={"%ei": "bNEW00"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is True
    body = result["write"]["request"]["payload"]["changes"][0]["body"]
    assert body["%p"]["new_password"]["%e"]["0"]["%p"]["%ei"] == "bNEW00"
    assert (
        body["%p"]["new_password"]["%e"]["0"]["%n"]
        == golden_action["%p"]["new_password"]["%e"]["0"]["%n"]
    )
    assert body["%p"]["new_password_again"] == golden_action["%p"]["new_password_again"]


def test_the_guard_refuses_a_decoded_action_nested_under_an_encoded_node() -> None:
    """The node root is encoded (as a live read now always returns), but a decoded action

    smuggled into its actions container must still be caught by the recursive descent.
    """

    node = {
        "id": "act-a",
        "%x": "CustomEvent",
        "%p": {"to_change": {"%x": "APIEventParameter"}},
        "actions": {"0": {"id": "act-b", "type": "SetCustomState", "properties": {"v": 1}}},
    }

    with pytest.raises(ValueError, match="decoded node root"):
        build_patch_changes(["api", "wf-1", "actions", "0"], node, "sid-1")


def test_the_guard_refuses_a_decoded_action_nested_inside_a_reordered_map() -> None:
    actions = {
        "0": {
            "id": "act-a",
            "%x": "CustomEvent",
            "%p": {},
            "actions": {"0": {"id": "act-b", "type": "SetCustomState", "properties": {}}},
        }
    }

    with pytest.raises(ValueError, match="decoded node root"):
        build_reorder_changes(["api", "wf-1", "actions"], actions, "sid-1")


def test_the_guard_leaves_the_expression_interior_alone() -> None:
    """The guard never descends into a node's own %p; only node roots are inspected, so an

    interior spelled with a decoded-looking key passes through untouched.
    """

    node = {
        "id": "act-1",
        "%x": "ChangeThing",
        "%p": {"to_change": {"type": "APIEventParameter", "is_slidable": False}},
    }

    changes = build_patch_changes(["api", "wf-1", "actions", "0"], node, "sid-1")

    assert changes[0]["body"]["%p"]["to_change"]["type"] == "APIEventParameter"


def test_the_guard_refuses_a_decoded_node_wrapped_inside_a_list() -> None:
    """`_assert_encoded_container` used to recurse only when the immediate child was a dict, so

    a list - and any decoded node inside it - was skipped entirely. The control case (the same
    decoded node NOT wrapped in a list) was already correctly refused before this fix; both must
    be refused.
    """

    bypassed = {
        "%x": "CustomEvent",
        "%p": {},
        "actions": {"0": [{"type": "SetCustomState", "properties": {"value": 1}}]},
    }
    with pytest.raises(ValueError, match="decoded node root"):
        build_patch_changes(["api", "wf"], bypassed, "sid")

    control = {
        "%x": "CustomEvent",
        "%p": {},
        "actions": {"0": {"type": "SetCustomState", "properties": {}}},
    }
    with pytest.raises(ValueError, match="decoded node root"):
        build_patch_changes(["api", "wf"], control, "sid")


def test_the_guard_refuses_a_list_found_directly_at_a_container_key() -> None:
    """actions/%el/%wf are maps of nodes keyed by index or id, never a bare list; a list found

    directly at one of those keys must be refused with a clear error rather than silently
    walked (and therefore silently skipped, the same failure mode as the list-wrapped-node
    bypass, just one level shallower).
    """

    node = {
        "%x": "CustomEvent",
        "%p": {},
        "actions": [{"type": "SetCustomState", "properties": {"value": 1}}],
    }
    with pytest.raises(ValueError, match="list"):
        build_patch_changes(["api", "wf"], node, "sid")


def test_reorder_refuses_an_action_with_no_id_instead_of_skipping_its_index() -> None:
    reader = _Reader(
        {
            "0": {"id": "act-a", "%x": "SetCustomState", "%p": {"value": 1}},
            "1": {"%x": "SetCustomState", "%p": {"value": 2}},
        }
    )

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["1", "0"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert "no id" in result["message"]


def test_app_version_reaches_both_reads_and_the_write_payload() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=True,
        app_version="my-branch",
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert reader.app_versions == ["my-branch", "my-branch"]
    assert result["write"]["request"]["payload"]["app_version"] == "my-branch"


def test_app_version_defaults_to_test_when_the_caller_omits_it() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert reader.app_versions == ["test"]
    assert result["write"]["request"]["payload"]["app_version"] == "test"


def test_an_executed_result_says_a_matching_re_read_is_not_a_render_check() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order"},
        execute=True,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["verified"] is True
    assert result["render_unverified"] is True
    assert "renders" in result["verified_meaning"]


def test_a_preview_claims_neither_verification_nor_a_render_check() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["%p", "to_change", "%p"],
        patch={"param_id": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert "verified" not in result
    assert "render_unverified" not in result


def test_a_missing_leaf_pointer_is_refused_before_the_browser_is_launched() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        patch={"param_id": "Order"},
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert reader.calls == 0


def test_a_missing_order_is_refused_before_the_browser_is_launched() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert reader.calls == 0
