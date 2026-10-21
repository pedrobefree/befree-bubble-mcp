"""The editor and the write endpoint spell node keys differently; only the root translates."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bubble_mcp.execution.node_keys import decode_node_root, encode_node_root

GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "expressions"
    / "api-event-parameter-golden.json"
)


def test_encode_node_root_translates_the_root_and_nothing_else() -> None:
    node = {
        "id": "act-1",
        "type": "ChangeThing",
        "properties": {"to_change": {"type": "APIEventParameter", "is_slidable": False}},
    }

    encoded = encode_node_root(node)

    assert encoded == {
        "id": "act-1",
        "%x": "ChangeThing",
        "%p": {"to_change": {"type": "APIEventParameter", "is_slidable": False}},
    }


def test_encode_node_root_leaves_the_expression_interior_byte_identical() -> None:
    action = json.loads(GOLDEN.read_text(encoding="utf-8"))["action"]
    interior = copy.deepcopy(action["properties"])

    encoded = encode_node_root(action)

    assert encoded["%p"] == interior


def test_encode_node_root_does_not_mutate_its_argument() -> None:
    node = {"type": "ChangeThing", "properties": {"k": {"type": "Message"}}}
    original = copy.deepcopy(node)

    encode_node_root(node)

    assert node == original


def test_encode_node_root_refuses_a_root_that_carries_name() -> None:
    with pytest.raises(ValueError, match="name"):
        encode_node_root({"type": "Text", "name": "Header"})


def test_encode_node_root_passes_an_already_encoded_node_through_as_a_deep_copy() -> None:
    node = {"id": "a", "%x": "ChangeThing", "%p": {"k": {"type": "Message"}}}

    encoded = encode_node_root(node)

    assert encoded == node
    assert encoded is not node
    # The idempotency branch must copy as deeply as the translating branch does: a caller that
    # edits the returned body must not reach back into the node the editor handed us.
    encoded["%p"]["k"]["type"] = "mutated"
    assert node["%p"]["k"]["type"] == "Message"


def test_encode_node_root_refuses_a_root_that_mixes_decoded_and_encoded_keys() -> None:
    with pytest.raises(ValueError, match="mixes decoded"):
        encode_node_root(
            {"id": "a1", "%dn": "Step 1", "type": "ChangeThing", "properties": {"k": 1}}
        )


def test_encode_node_root_refuses_name_even_on_an_already_encoded_root() -> None:
    with pytest.raises(ValueError, match="name"):
        encode_node_root({"%x": "Element", "name": "Group A", "%p": {}})


def test_decode_node_root_refuses_a_root_that_mixes_decoded_and_encoded_keys() -> None:
    with pytest.raises(ValueError, match="mixes decoded"):
        decode_node_root({"id": "a1", "%x": "ChangeThing", "properties": {"k": 1}})


def test_decode_node_root_refuses_encoded_name_even_on_an_already_decoded_root() -> None:
    with pytest.raises(ValueError, match="%nm"):
        decode_node_root({"type": "Text", "%nm": "Header", "properties": {}})


def test_encode_node_root_rejects_a_non_node() -> None:
    with pytest.raises(TypeError):
        encode_node_root(["not", "a", "node"])  # type: ignore[arg-type]


def test_decode_node_root_closes_the_round_trip() -> None:
    node = {"id": "act-1", "type": "ChangeThing", "properties": {"k": {"type": "Message"}}}

    assert decode_node_root(encode_node_root(node)) == node


def test_decode_node_root_refuses_an_encoded_element_name() -> None:
    with pytest.raises(ValueError, match="%nm"):
        decode_node_root({"%x": "Text", "%nm": "Header"})
