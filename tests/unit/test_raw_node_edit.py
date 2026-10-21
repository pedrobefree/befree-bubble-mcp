import copy

from bubble_mcp.execution.raw_node_edit import (
    first_divergence,
    patch_expression_leaf,
    reorder_actions,
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
