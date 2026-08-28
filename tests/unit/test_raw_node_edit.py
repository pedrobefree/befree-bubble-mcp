import copy
import json
from pathlib import Path

from bubble_mcp.execution.raw_node_edit import (
    all_divergences,
    clone_workflow_changes,
    first_divergence,
    patch_expression_leaf,
    remap_node_ids,
    remap_node_ids_with_report,
    remove_expression_keys,
    reorder_actions,
    workflow_id_mapping,
)


def _action(action_id: str) -> dict:  # type: ignore[type-arg]
    return {
        "id": action_id,
        "%x": "SetCustomState",
        "%p": {"element_id": f"el-{action_id}", "value": True},
    }


def test_reorder_actions_renumbers_keys_and_keeps_every_body_verbatim() -> None:
    actions = {"0": _action("a"), "1": _action("b"), "2": _action("c")}
    original = copy.deepcopy(actions)

    reordered = reorder_actions(actions, ["2", "0", "1"])

    assert reordered == {"0": original["2"], "1": original["0"], "2": original["1"]}
    assert actions == original


def test_reorder_actions_refuses_an_order_that_would_drop_a_step() -> None:
    actions = {"0": _action("a"), "1": _action("b"), "2": _action("c")}

    try:
        reorder_actions(actions, ["2", "0"])
    except ValueError as error:
        assert "1" in str(error)
    else:
        raise AssertionError("dropping an action must not be silent")


def _chain_action() -> dict:  # type: ignore[type-arg]
    """A ChangeThing whose value walks a Message chain, shaped like the golden fixture."""

    return {
        "id": "act-1",
        "%x": "ChangeThing",
        "%p": {
            "to_change": {
                "type": "APIEventParameter",
                "is_slidable": False,
                "properties": {
                    "btype_id": "custom.client",
                    "event_id": "evt-1",
                    "param_id": "Client",
                    "param_name": "Client",
                },
            },
            "value": {
                "type": "SearchForThings",
                "is_slidable": False,
                "next": {"type": "Message", "is_slidable": False, "name": "last_item"},
            },
        },
    }


def test_patch_expression_leaf_swaps_a_message_token_and_leaves_the_rest_verbatim() -> None:
    action = _chain_action()
    original = copy.deepcopy(action)
    expected = copy.deepcopy(action)
    expected["%p"]["value"]["next"]["name"] = "first_item"

    patched = patch_expression_leaf(action, ["%p", "value", "next"], {"name": "first_item"})

    assert patched == expected
    assert action == original


def test_patch_expression_leaf_refuses_a_pointer_that_does_not_resolve() -> None:
    action = _chain_action()

    try:
        patch_expression_leaf(action, ["%p", "value", "next", "next"], {"name": "first_item"})
    except KeyError as error:
        assert "next" in str(error)
    else:
        raise AssertionError("a pointer must never create the node it fails to find")


def test_first_divergence_names_the_path_where_a_written_node_came_back_different() -> None:
    intended = _chain_action()
    written_back = copy.deepcopy(intended)
    written_back["%p"]["value"]["next"]["name"] = "last_item_"

    assert first_divergence(intended, written_back) == "%p.value.next.name"


def test_first_divergence_reports_none_when_the_editor_kept_the_node() -> None:
    intended = _chain_action()

    assert first_divergence(intended, copy.deepcopy(intended)) is None


def test_first_divergence_reports_a_key_the_editor_dropped() -> None:
    intended = _chain_action()
    written_back = copy.deepcopy(intended)
    del written_back["%p"]["to_change"]["properties"]["btype_id"]

    assert first_divergence(intended, written_back) == "%p.to_change.properties.btype_id"


def _custom_event_workflow() -> dict:  # type: ignore[type-arg]
    """Case D from docs/capture-duplicate-workflow.md: the SOURCE node, before duplication.

    The APIEventParameter argument carries `event_id`, a back-reference to the workflow's own
    event id, which is why a clone cannot copy expression subtrees verbatim.

    WHY THIS FIXTURE IS HAND-BUILT AND CANNOT BE FETCHED
    ---------------------------------------------------
    The obvious way to remove any circularity here would be to read the real source node and use
    it verbatim. That does not work: the path API DROPS null-valued keys (measured 2026-08-27 -
    the copy was written with `%n`, `optional` and `in_url` all null and reads back without
    them), so a fetched fixture would be missing exactly the fields the captured payload carries,
    and the golden comparison below would fail for a reason that has nothing to do with cloning.

    So the null-valued keys here are taken from the captured payload rather than observed in the
    source. Everything else is verified against
    docs/capture-duplicate-workflow-custom-event-source.json.
    """

    return {
        "%x": "APIEvent",
        "%p": {
            "expose": False,
            "wf_name": "test custom",
            "parameters": {"0": {"%k": "Parameter 1", "%v": "custom.test", "param_id": "bTGOc"}},
        },
        "id": "bTGOQ",
        "actions": {
            "0": {
                "%x": "TriggerCustomEvent",
                "%p": {
                    "custom_event": "bTGNt",
                    "arguments": {
                        "0": {
                            "param_id": "bTGOA",
                            "arg_value": {
                                "%x": "APIEventParameter",
                                "%p": {
                                    "event_id": "bTGOQ",
                                    "param_id": "Parameter 1",
                                    "param_name": "Parameter 1",
                                    "optional": None,
                                    "btype_id": "custom.test",
                                    "in_url": None,
                                },
                                "%n": None,
                                "is_slidable": False,
                            },
                        }
                    },
                },
                "id": "bTGOX",
            }
        },
    }


def test_remap_node_ids_rewrites_a_self_reference_buried_in_an_expression() -> None:
    node = _custom_event_workflow()

    remapped = remap_node_ids(node, {"bTGOQ": "bTGOd", "bTGOX": "bTGOi"})

    assert remapped["id"] == "bTGOd"
    assert remapped["actions"]["0"]["id"] == "bTGOi"
    argument = remapped["actions"]["0"]["%p"]["arguments"]["0"]
    assert argument["arg_value"]["%p"]["event_id"] == "bTGOd"


def test_remap_node_ids_leaves_references_to_objects_outside_the_node_alone() -> None:
    node = _custom_event_workflow()

    remapped = remap_node_ids(node, {"bTGOQ": "bTGOd", "bTGOX": "bTGOi"})

    argument = remapped["actions"]["0"]["%p"]["arguments"]["0"]
    assert remapped["actions"]["0"]["%p"]["custom_event"] == "bTGNt"
    assert argument["param_id"] == "bTGOA"
    assert remapped["%p"]["parameters"]["0"]["param_id"] == "bTGOc"


def test_remap_node_ids_does_not_mutate_the_node_it_was_given() -> None:
    node = _custom_event_workflow()
    original = copy.deepcopy(node)

    remap_node_ids(node, {"bTGOQ": "bTGOd", "bTGOX": "bTGOi"})

    assert node == original


def test_clone_workflow_changes_matches_the_change_list_the_editor_sent() -> None:
    """Golden test against real editor traffic: docs/capture-duplicate-workflow-custom-event.json."""

    captured = json.loads(
        Path("docs/capture-duplicate-workflow-custom-event.json").read_text(encoding="utf-8")
    )["parsed"]["changes"]

    changes = clone_workflow_changes(
        node=_custom_event_workflow(),
        node_path=["api", "bTGOS"],
        new_slot="bTGOj",
        mapping={"bTGOQ": "bTGOd", "bTGOX": "bTGOi"},
        wf_name="test custom_copy",
        session_id="1787832360734x48",
        intent_id=35,
        id_counter=10000156,
    )

    assert changes == captured


def test_clone_workflow_changes_indexes_a_page_workflow_under_its_page_path() -> None:
    node = {"%x": "ButtonClicked", "%p": {"%ei": "bVoQt"}, "id": "old-event", "actions": {}}

    changes = clone_workflow_changes(
        node=node,
        node_path=["%p3", "bVVl3", "%wf", "bTGNM"],
        new_slot="bTGNO",
        mapping={"old-event": "new-event"},
        wf_name=None,
        session_id="s1",
        intent_id=1,
        id_counter=5,
    )

    assert changes[0]["path_array"] == ["_index", "id_to_path", "new-event"]
    assert changes[0]["body"] == "%p3.bVVl3.%wf.bTGNO"
    assert changes[1]["path_array"] == ["%p3", "bVVl3", "%wf", "bTGNO"]


def test_clone_workflow_changes_leaves_a_page_workflow_body_unnamed() -> None:
    node = {"%x": "ButtonClicked", "%p": {"%ei": "bVoQt"}, "id": "old-event", "actions": {}}

    changes = clone_workflow_changes(
        node=node,
        node_path=["%p3", "bVVl3", "%wf", "bTGNM"],
        new_slot="bTGNO",
        mapping={"old-event": "new-event"},
        wf_name=None,
        session_id="s1",
        intent_id=1,
        id_counter=5,
    )

    assert "wf_name" not in changes[1]["body"]["%p"]


def test_workflow_id_mapping_covers_the_event_and_every_action() -> None:
    node = _custom_event_workflow()
    minted = iter(["new-event", "new-action-0"])

    mapping = workflow_id_mapping(node, lambda: next(minted))

    assert mapping == {"bTGOQ": "new-event", "bTGOX": "new-action-0"}


def test_workflow_id_mapping_covers_nothing_else() -> None:
    node = _custom_event_workflow()
    minted = iter(["new-event", "new-action-0", "surplus"])

    mapping = workflow_id_mapping(node, lambda: next(minted))

    assert "bTGOc" not in mapping
    assert "bTGOA" not in mapping
    assert "bTGNt" not in mapping


def test_workflow_id_mapping_refuses_a_node_with_no_id() -> None:
    minted = iter(["new-event"])

    try:
        workflow_id_mapping({"%x": "APIEvent", "actions": {}}, lambda: next(minted))
    except ValueError as error:
        assert "id" in str(error)
    else:
        raise AssertionError("a node without an id cannot be cloned")


def test_clone_workflow_changes_omits_the_counter_when_none_was_read() -> None:
    node = {"%x": "ButtonClicked", "%p": {"%ei": "bVoQt"}, "id": "old-event", "actions": {}}

    changes = clone_workflow_changes(
        node=node,
        node_path=["%p3", "bVVl3", "%wf", "bTGNM"],
        new_slot="bTGNO",
        mapping={"old-event": "new-event"},
        wf_name=None,
        session_id="s1",
        intent_id=1,
        id_counter=None,
    )

    assert not any("type" in change for change in changes)


def _workflow_with_user_text(text: str) -> dict:  # type: ignore[type-arg]
    """Case C's shape: ArbitraryText carries text the user typed, as a raw string."""

    return {
        "%x": "APIEvent",
        "%p": {"expose": False, "wf_name": "teste"},
        "id": "bTGNi",
        "actions": {
            "0": {
                "%x": "NewThing",
                "id": "bTGNn",
                "%p": {
                    "%tt": "custom.test",
                    "%i2": {
                        "0": {
                            "%k": "text_text",
                            "%ak": "=",
                            "%v": {
                                "%x": "TextExpression",
                                "%e": {
                                    "0": {
                                        "%x": "ArbitraryText",
                                        "%p": {
                                            "arbitrary_text": {
                                                "%x": "TextExpression",
                                                "%e": {"0": text},
                                            }
                                        },
                                    },
                                    "1": "",
                                },
                            },
                        }
                    },
                },
            }
        },
    }


def test_remap_node_ids_leaves_user_text_that_happens_to_read_like_an_id() -> None:
    """A user can type anything, including a string equal to the id being replaced."""

    node = _workflow_with_user_text("bTGNi")

    remapped = remap_node_ids(node, {"bTGNi": "bNEW1", "bTGNn": "bNEW2"})

    typed = remapped["actions"]["0"]["%p"]["%i2"]["0"]["%v"]["%e"]["0"]["%p"]["arbitrary_text"]
    assert typed["%e"]["0"] == "bTGNi"
    assert remapped["id"] == "bNEW1"


def test_remap_node_ids_reports_an_id_it_saw_somewhere_it_did_not_rewrite() -> None:
    """A self-reference in a field this does not know about must be visible, not silent."""

    node = _workflow_with_user_text("bTGNi")

    _, unmapped = remap_node_ids_with_report(node, {"bTGNi": "bNEW1", "bTGNn": "bNEW2"})

    assert any("arbitrary_text" in path for path in unmapped)


def test_remap_node_ids_rewrites_every_id_field_the_captures_show() -> None:
    node = _custom_event_workflow()

    remapped = remap_node_ids(node, {"bTGOQ": "bTGOd", "bTGOX": "bTGOi"})

    assert remapped["id"] == "bTGOd"
    assert remapped["actions"]["0"]["id"] == "bTGOi"
    assert remapped["actions"]["0"]["%p"]["arguments"]["0"]["arg_value"]["%p"]["event_id"] == "bTGOd"


def test_all_divergences_names_every_path_that_differs_not_just_the_first() -> None:
    intended = {"a": {"p": 1, "q": 1}, "b": 2}
    actual = {"a": {"p": 9, "q": 9}, "b": 9}

    assert sorted(all_divergences(intended, actual)) == ["a.p", "a.q", "b"]


def test_all_divergences_reports_keys_added_and_dropped_separately() -> None:
    assert sorted(all_divergences({"a": 1}, {"b": 1})) == ["a", "b"]


def test_all_divergences_is_empty_for_identical_trees() -> None:
    assert all_divergences({"a": {"p": 1}}, {"a": {"p": 1}}) == []


def test_clone_workflow_changes_writes_no_issues_index_entry() -> None:
    """Duplication does not touch `issues_list`, even though creating an action does.

    A second app's capture shows the editor writing `_index/issues_list/<action_id>` = "[]" on
    every CreateAction (a second app's capture report, 2026-08-27, section 1.1), and copying
    that into the clone is the obvious generalisation. The captured duplications say otherwise:
    cases A, C and D write no issues entry at all, and case B writes one keyed by the EVENT id
    only because that copy carried a real cross_page issue.

    So the two flows differ, and this follows the one that was actually captured for duplication.
    Emitting "[]" per action here would write an index the editor did not ask for.
    """

    node = {
        "%x": "APIEvent",
        "%p": {"expose": False, "wf_name": "src"},
        "id": "bOLD1",
        "actions": {"0": {"%x": "ShowElement", "%p": {"%ei": "bEL01"}, "id": "bOLD2"}},
    }

    changes = clone_workflow_changes(
        node=node,
        node_path=["api", "bSLOT"],
        new_slot="bNEW0",
        mapping={"bOLD1": "bNEW1", "bOLD2": "bNEW2"},
        wf_name="src_copy",
        session_id="s1",
        intent_id=7,
        id_counter=None,
    )

    assert not any(
        change.get("path_array", [None, None])[1] == "issues_list" for change in changes
    )


def test_remove_expression_keys_drops_the_named_keys_and_leaves_the_rest() -> None:
    """`patch` merges, so it can replace a constraint but never delete one."""

    node = {
        "id": "act-1",
        "%x": "Search",
        "%p": {"%co": {"0": {"%k": "status"}, "1": {"%k": "owner"}}, "%t5": "custom.thing"},
    }
    original = copy.deepcopy(node)

    trimmed = remove_expression_keys(node, ["%p", "%co"], ["1"])

    assert trimmed["%p"]["%co"] == {"0": {"%k": "status"}}
    assert trimmed["%p"]["%t5"] == "custom.thing"
    assert node == original


def test_remove_expression_keys_refuses_a_key_that_is_not_there() -> None:
    """Silently succeeding would report a removal that never happened."""

    node = {"id": "act-1", "%x": "Search", "%p": {"%co": {"0": {"%k": "status"}}}}

    try:
        remove_expression_keys(node, ["%p", "%co"], ["7"])
    except KeyError as error:
        assert "7" in str(error)
    else:
        raise AssertionError("removing a key that does not exist must not look like success")


def test_remove_expression_keys_refuses_a_pointer_that_does_not_resolve() -> None:
    node = {"id": "act-1", "%x": "Search", "%p": {}}

    try:
        remove_expression_keys(node, ["%p", "%co"], ["0"])
    except KeyError as error:
        assert "%co" in str(error)
    else:
        raise AssertionError("a pointer must never create the node it fails to find")


def test_remove_expression_keys_refuses_to_empty_a_node_of_its_type() -> None:
    """Dropping %x or id leaves a body the editor cannot render, and /write answers 200."""

    node = {"id": "act-1", "%x": "Search", "%p": {"%t5": "custom.thing"}}

    try:
        remove_expression_keys(node, [], ["%x"])
    except ValueError as error:
        assert "%x" in str(error)
    else:
        raise AssertionError("removing the node's own type must be refused")
