from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.compiler import (
    compile_api_connector_actions_to_payloads,
    compile_collection_actions_to_payloads,
    compile_inventory_to_target_payloads,
)
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


def test_compile_collection_actions_creates_data_type_and_fields() -> None:
    target_context = BubbleProjectContext(app_id="target-app", source="test", nodes=[], edges=[])

    payloads = compile_collection_actions_to_payloads(
        actions=[
            {"action": "create_data_type", "data_type": "testimonial", "label": "Testimonial"},
            {
                "action": "create_data_field",
                "data_type": "testimonial",
                "field_key": "quote_text",
                "field_type": "text",
            },
        ],
        target_context=target_context,
        target_app_id="target-app",
        target_app_version="test",
    )

    assert [payload["changes"][0]["intent"]["name"] for payload in payloads] == ["SetData", "SetData"]
    assert payloads[0]["changes"][0]["path_array"] == ["data_types", "testimonial"]
    assert payloads[1]["changes"][0]["path_array"] == ["data_types", "testimonial", "fields", "quote_text"]
    assert payloads[1]["changes"][0]["body"]["type"] == "text"


def test_compile_collection_actions_creates_options_and_privacy_rules() -> None:
    target_context = BubbleProjectContext(app_id="target-app", source="test", nodes=[], edges=[])

    payloads = compile_collection_actions_to_payloads(
        actions=[
            {"action": "create_option_set", "option_set": "status", "label": "Status"},
            {
                "action": "create_option_value",
                "option_set": "status",
                "value_key": "active",
                "label": "Active",
                "db_value": "active",
            },
            {
                "action": "ensure_privacy_rule",
                "data_type": "testimonial",
                "rule_key": "public_rule",
                "label": "public_testimonial",
                "payload": {"%d": "public_testimonial", "permissions": {"view_all": True}},
            },
        ],
        target_context=target_context,
        target_app_id="target-app",
        target_app_version="test",
    )

    paths = [payload["changes"][0]["path_array"] for payload in payloads]
    intents = [payload["changes"][0]["intent"]["name"] for payload in payloads]

    assert paths == [
        ["option_sets", "status"],
        ["option_sets", "status", "values", "active"],
        ["user_types", "testimonial", "privacy_role", "public_rule"],
    ]
    assert intents == ["SetData", "SetData", "ChangeAppSetting"]
    assert payloads[2]["changes"][0]["body"]["%d"] == "public_testimonial"


def test_compile_api_connector_actions_creates_structure_only_payloads() -> None:
    payloads = compile_api_connector_actions_to_payloads(
        actions=[
            {"action": "create_api_connector", "api_id": "stripe", "name": "Stripe"},
            {
                "action": "create_api_connector_call",
                "api_id": "stripe",
                "call_id": "create_customer",
                "name": "Create customer",
                "method": "POST",
                "url": "https://api.stripe.com/v1/customers",
            },
        ],
        target_app_id="target-app",
        target_app_version="test",
    )

    assert payloads[0]["changes"][0]["path_array"] == ["settings", "client_safe", "apiconnector2", "stripe"]
    assert payloads[0]["changes"][0]["body"] == {"human": "Stripe", "calls": {}}
    call_payload = payloads[1]
    assert call_payload["changes"][0]["intent"]["name"] == "CreateApiCall"
    assert call_payload["changes"][0]["path_array"] == [
        "settings",
        "client_safe",
        "apiconnector2",
        "stripe",
        "calls",
        "create_customer",
    ]
    assert call_payload["changes"][1]["body"] == "https://api.stripe.com/v1/customers"
    assert call_payload["changes"][2]["body"] == "post"
