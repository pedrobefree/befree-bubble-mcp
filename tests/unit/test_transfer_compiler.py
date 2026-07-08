from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.compiler import compile_inventory_to_target_payloads
from bubble_mcp.transfer.models import TransferInventory, TransferObjectRef


def test_compile_element_inventory_targets_target_app_and_parent_path() -> None:
    inventory = TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="element",
            ref="gp_Hero",
            context="index",
            bubble_id="bHero",
            path=["%p3", "bSourcePage", "%el", "bHero"],
        ),
        root={
            "id": "element:bHero",
            "label": "gp_Hero",
            "type": "element",
            "metadata": {"bubble_id": "bHero", "path": ["%p3", "bSourcePage", "%el", "bHero"]},
        },
        nodes=[
            {
                "id": "element:bHero",
                "label": "gp_Hero",
                "type": "element",
                "metadata": {
                    "bubble_id": "bHero",
                    "properties": {"%x": "Group", "%p": {"%nm": "gp_Hero", "container_layout": "column"}},
                },
            }
        ],
        dependencies=[],
    )
    target_context = BubbleProjectContext(
        app_id="target-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="page:index",
                label="index",
                type="page",
                metadata={"bubble_id": "bTargetPage", "path_array": ["%p3", "bTargetPage"]},
            )
        ],
        edges=[],
    )

    payloads = compile_inventory_to_target_payloads(
        inventory=inventory,
        target_context=target_context,
        target_app_id="target-app",
        target_app_version="test",
        target_context_ref="index",
        target_parent_ref="root",
        target_name="gp_Hero_Copy",
    )

    assert len(payloads) == 1
    assert payloads[0]["appname"] == "target-app"
    assert payloads[0]["app_version"] == "test"
    assert payloads[0]["appVersion"] == "test"
    change = payloads[0]["changes"][0]
    assert change["intent"]["name"] == "CreateElement"
    assert change["path_array"][:2] == ["%p3", "bTargetPage"]
    assert change["body"]["%p"]["%nm"] == "gp_Hero_Copy"
    assert change["body"]["%p"]["container_layout"] == "column"


def test_compile_inventory_preserves_child_parent_order() -> None:
    inventory = TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="element",
            ref="gp_Hero",
        ),
        root={"id": "element:bParent", "label": "gp_Parent", "type": "element", "metadata": {"bubble_id": "bParent"}},
        nodes=[
            {
                "id": "element:bParent",
                "label": "gp_Parent",
                "type": "element",
                "metadata": {"bubble_id": "bParent", "properties": {"%x": "Group", "%p": {"%nm": "gp_Parent"}}},
            },
            {
                "id": "element:bChild",
                "label": "tx_Child",
                "type": "element",
                "metadata": {
                    "bubble_id": "bChild",
                    "path": ["%p3", "bSourcePage", "%el", "bParent", "%el", "bChild"],
                    "properties": {"%x": "Text", "%p": {"%nm": "tx_Child", "%3": "Hello"}},
                },
            },
        ],
        dependencies=[],
    )
    target_context = BubbleProjectContext(
        app_id="target-app",
        source="test",
        nodes=[BubbleContextNode(id="page:index", label="index", type="page", metadata={"bubble_id": "bTargetPage"})],
        edges=[],
    )

    payload = compile_inventory_to_target_payloads(
        inventory=inventory,
        target_context=target_context,
        target_app_id="target-app",
        target_app_version="test",
        target_context_ref="index",
        target_parent_ref="root",
    )[0]

    parent_id = payload["changes"][0]["body"]["id"]
    assert payload["changes"][1]["path_array"] == ["%p3", "bTargetPage", "%el", parent_id]
