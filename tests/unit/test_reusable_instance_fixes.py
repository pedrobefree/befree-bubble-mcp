"""Bugs from the 2026-08-24 the client report: create_reusable_instance payload fidelity.

1. custom_id must be the definition's inner .id, not the element_definitions dict key.
2. Created elements must carry %nm (name) and %p.order like editor-created instances.
3. reusable_name must be optional-with-clear-error and aliased from `source`.
"""

from __future__ import annotations



def _discovery_with_definitions(defs):
    from bubble_mcp.aria_runtime.bubble_sdk import PathDiscovery

    discovery = PathDiscovery(app_json_path=None, consolelog_json_path=None, crawler_index_path=None)
    discovery._data = {"element_definitions": defs}
    discovery._data_source = "test"
    return discovery


def test_find_reusable_definition_returns_key_and_inner_id() -> None:
    defs = {
        "bTYLW0": {"id": "bTYKr0", "name": "Payment Message"},
        "delete_class_confirmation": {"id": "bplykvps", "%nm": "Delete Class Confirmation"},
    }
    discovery = _discovery_with_definitions(defs)

    key, definition = discovery.find_reusable_definition("Payment Message")
    assert key == "bTYLW0"
    assert definition["id"] == "bTYKr0"

    key2, definition2 = discovery.find_reusable_definition("delete class confirmation")
    assert key2 == "delete_class_confirmation"
    assert definition2["id"] == "bplykvps"

    assert discovery.find_reusable_definition("nope") is None


def test_next_child_order_is_max_sibling_order_plus_one() -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    cli = object.__new__(BubbleCLI)
    parent_result = {
        "id": "parent1",
        "element": {
            "id": "parent1",
            "%el": {
                "a": {"id": "a", "%p": {"order": 3}},
                "b": {"id": "b", "properties": {"order": 13}},
                "c": {"id": "c", "%p": {}},
                "length": 3,
            },
        },
    }
    assert BubbleCLI._next_child_order(cli, "ctx", "page", parent_result) == 14

    empty_parent = {"id": "parent2", "element": {"id": "parent2", "%el": {}}}
    assert BubbleCLI._next_child_order(cli, "ctx", "page", empty_parent) == 0


def test_queue_create_writes_element_name_when_given() -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
    from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
    from bubble_mcp.aria_runtime.visual_mutations import VisualMutationService

    cli = object.__new__(BubbleCLI)
    # Path canonicalization consults discovery/profile caches; identity-stub it so the
    # test exercises only the payload the helper emits.
    cli._canonicalize_context_prefix_on_path = lambda path, context_id, context_type: path
    cli._visual_mutations = VisualMutationService(cli)
    pb = PayloadBuilder(appname="test-app")
    parent_result = {"id": "page1", "element": {"id": "page1", "%el": {}}}
    BubbleCLI._queue_create_element_with_index_updates(
        cli,
        pb=pb,
        context_id="page1",
        context_type="page",
        parent_result=parent_result,
        create_path=["%p3", "page1", "%el", "newkey"],
        create_body={"id": "newid1", "%x": "CustomElement", "%dn": "Payment Message A", "%p": {"custom_id": "bTYKr0"}},
        full_path_str="%p3.page1.%el.newkey",
        name_value="Payment Message A",
    )
    changes = pb.build()["changes"]
    name_writes = [c for c in changes if c.get("path_array", [])[-1:] == ["%nm"]]
    assert name_writes, "expected a %nm write for the element name"
    assert name_writes[0]["body"] == "Payment Message A"
    assert name_writes[0]["path_array"][:4] == ["%p3", "page1", "%el", "newkey"]


def test_create_reusable_instance_without_reusable_name_fails_clearly() -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    cli = object.__new__(BubbleCLI)
    ok = BubbleCLI.create_reusable_instance(cli, "dashboard", "root", None, name="Payment Message A")
    assert ok is False  # structured failure, not a TypeError


def test_reusable_name_schema_and_alias() -> None:
    from bubble_mcp.aria_dispatch import ARG_ALIASES
    from bubble_mcp.server.agent_catalog import _legacy_fields_for_name

    assert "source" in ARG_ALIASES.get("reusable_name", ())
    fields = _legacy_fields_for_name("create_reusable_instance")
    assert fields is not None
    required, optional = fields
    assert "source" in required or "reusable_name" in required
