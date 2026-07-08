from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.compiler import (
    compile_api_connector_actions_to_payloads,
    compile_context_shell_payload,
    compile_collection_actions_to_payloads,
    compile_inventory_to_target_payloads,
    compile_reusable_inventory_to_payload,
)
from bubble_mcp.transfer.models import (
    TransferDependency,
    TransferInventory,
    TransferMappingDecision,
    TransferObjectRef,
)


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


def test_compile_inventory_remaps_dependencies_and_internal_element_refs() -> None:
    style_dependency = TransferDependency(
        kind="style",
        key="source_button",
        label="Source Button",
        source_id="sty_source",
        metadata={"key": "source_button", "name": "Source Button", "bubble_id": "sty_source"},
    )
    data_type_dependency = TransferDependency(
        kind="data_type",
        key="source_customer",
        label="Source Customer",
        metadata={"data_type": "source_customer"},
    )
    inventory = TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="element",
            ref="gp_Card",
        ),
        root={"id": "element:bParent", "label": "gp_Card", "type": "element", "metadata": {"bubble_id": "bParent"}},
        nodes=[
            {
                "id": "element:bParent",
                "label": "gp_Card",
                "type": "element",
                "metadata": {
                    "bubble_id": "bParent",
                    "properties": {
                        "%x": "Group",
                        "%p": {
                            "%nm": "gp_Card",
                            "button_style_key": "source_button",
                            "button_style_label": "Source Button",
                            "style_id": "sty_source",
                            "data_source_type": "source_customer",
                            "linked_element": "bChild",
                            "nested_refs": ["source_button", {"element": "bChild"}],
                        },
                    },
                },
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
        dependencies=[style_dependency, data_type_dependency],
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
        dependency_decisions=[
            TransferMappingDecision(
                dependency=style_dependency,
                action="map_existing",
                target_id="style:target_button",
                target_label="Target Button",
                metadata={
                    "target_reference": {
                        "id": "style:target_button",
                        "key": "target_button",
                        "label": "Target Button",
                        "name": "Target Button",
                        "bubble_id": "sty_target",
                    }
                },
            ),
            TransferMappingDecision(
                dependency=data_type_dependency,
                action="map_existing",
                target_id="datatype:target_customer",
                target_label="Target Customer",
                metadata={
                    "target_reference": {
                        "id": "datatype:target_customer",
                        "data_type": "target_customer",
                        "label": "Target Customer",
                    }
                },
            ),
        ],
    )[0]

    parent_body = payload["changes"][0]["body"]
    child_body = payload["changes"][1]["body"]
    parent_props = parent_body["%p"]
    child_id = child_body["id"]
    assert parent_props["button_style_key"] == "target_button"
    assert parent_props["button_style_label"] == "Target Button"
    assert parent_props["style_id"] == "sty_target"
    assert parent_props["data_source_type"] == "target_customer"
    assert parent_props["linked_element"] == child_id
    assert parent_props["nested_refs"] == ["target_button", {"element": child_id}]


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


def test_compile_context_shell_payload_creates_page_or_reusable_root() -> None:
    page_shell = compile_context_shell_payload(
        source_type="page",
        source_root={"metadata": {"properties": {"%p": {"container_layout": "column"}}}},
        target_app_id="target-app",
        target_app_version="test",
        target_name="mcp-copy",
    )
    reusable_shell = compile_context_shell_payload(
        source_type="reusable",
        source_root={"metadata": {"properties": {"%p": {"container_layout": "row"}}}},
        target_app_id="target-app",
        target_app_version="test",
        target_name="Reusable Copy",
    )

    assert page_shell is not None
    page_payload, page_ref, page_type = page_shell
    assert page_type == "page"
    assert page_payload["changes"][0]["path_array"][:2] == ["_index", "id_to_path"]
    assert page_payload["changes"][1]["path_array"] == ["%p3", page_ref]
    assert page_payload["changes"][1]["body"]["%x"] == "Page"

    assert reusable_shell is not None
    reusable_payload, reusable_ref, reusable_type = reusable_shell
    assert reusable_type == "reusable"
    assert reusable_payload["changes"][1]["path_array"] == ["%ed", reusable_ref]
    assert reusable_payload["changes"][1]["body"]["%x"] == "CustomDefinition"


def test_compile_reusable_inventory_payload_nests_children_under_custom_definition() -> None:
    inventory = TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="reusable",
            ref="fileUploader",
            bubble_id="bSourceReusable",
        ),
        root={
            "id": "reusable:bSourceReusable",
            "label": "fileUploader",
            "type": "reusable",
            "metadata": {
                "bubble_id": "bSourceReusable",
                "properties": {
                    "name": "fileUploader",
                    "container_layout": "relative",
                    "default_width": 480,
                },
            },
        },
        nodes=[
            {
                "id": "reusable:bSourceReusable",
                "label": "fileUploader",
                "type": "reusable",
                "metadata": {"bubble_id": "bSourceReusable"},
            },
            {
                "id": "element:bParent",
                "label": "gp_File",
                "type": "element",
                "metadata": {
                    "bubble_id": "bParent",
                    "path": ["%ed", "bSourceReusable", "%el", "bParent"],
                    "properties": {"%x": "Group", "%p": {"%nm": "gp_File"}},
                },
            },
            {
                "id": "element:bChild",
                "label": "tx_File",
                "type": "element",
                "metadata": {
                    "bubble_id": "bChild",
                    "path": ["%ed", "bSourceReusable", "%el", "bParent", "%el", "bChild"],
                    "properties": {"%x": "Text", "%p": {"%nm": "tx_File", "%3": "File"}},
                },
            },
        ],
        dependencies=[],
    )

    compiled = compile_reusable_inventory_to_payload(
        inventory=inventory,
        target_app_id="target-app",
        target_app_version="test",
        target_name="fileUploader",
    )

    assert compiled is not None
    payload, reusable_ref = compiled
    root_change = payload["changes"][1]
    root_body = root_change["body"]
    assert root_change["path_array"] == ["%ed", reusable_ref]
    assert root_body["%x"] == "CustomDefinition"
    assert root_body["%nm"] == "fileUploader"
    assert len(root_body["%el"]) == 1
    parent_id = next(iter(root_body["%el"]))
    parent_body = root_body["%el"][parent_id]
    assert parent_body["%x"] == "Group"
    assert len(parent_body["%el"]) == 1
    child_id = next(iter(parent_body["%el"]))
    assert parent_body["%el"][child_id]["%x"] == "Text"
    id_to_path_updates = {
        tuple(change["path_array"]): change["body"]
        for change in payload["changes"]
        if change["path_array"][:2] == ["_index", "id_to_path"]
    }
    assert id_to_path_updates[("_index", "id_to_path", root_body["id"])] == f"%ed.{reusable_ref}"
    assert id_to_path_updates[("_index", "id_to_path", parent_id)] == f"%ed.{reusable_ref}.%el.{parent_id}"
    assert id_to_path_updates[("_index", "id_to_path", child_id)] == (
        f"%ed.{reusable_ref}.%el.{parent_id}.%el.{child_id}"
    )


def test_compile_reusable_inventory_uses_raw_definition_for_high_fidelity_clone() -> None:
    inventory = TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="reusable",
            ref="fileUploader",
            bubble_id="bSourceReusable",
        ),
        root={
            "id": "reusable:fileUploader",
            "label": "fileUploader",
            "type": "reusable",
            "metadata": {
                "bubble_id": "bSourceReusable",
                "raw_definition": {
                    "id": "bSourceRoot",
                    "name": "fileUploader",
                    "type": "CustomDefinition",
                    "properties": {"group_type": "file", "fit_height": True},
                    "custom_states": {"file_": {"display": "file", "value": "file", "make_static": True}},
                    "elements": {
                        "bGroupSlot": {
                            "id": "bGroupRoot",
                            "name": "gp file",
                            "type": "Group",
                            "properties": {"is_visible": False},
                            "states": {
                                "0": {
                                    "condition": {
                                        "type": "GetElement",
                                        "properties": {"element_id": "bSourceRoot"},
                                    },
                                    "properties": {"is_visible": True},
                                }
                            },
                        }
                    },
                    "workflows": {
                        "bWorkflowSlot": {
                            "id": "bWorkflowRoot",
                            "type": "InputChanged",
                            "properties": {"element_id": "bGroupRoot"},
                            "actions": {
                                "0": {
                                    "id": "bActionRoot",
                                    "type": "SetCustomState",
                                    "properties": {"element_id": "bSourceRoot", "custom_state": "custom.file_"},
                                }
                            },
                        }
                    },
                },
            },
        },
        nodes=[],
        dependencies=[],
    )

    compiled = compile_reusable_inventory_to_payload(
        inventory=inventory,
        target_app_id="target-app",
        target_app_version="test",
        target_name="fileUploaderCopy",
    )

    assert compiled is not None
    payload, reusable_ref = compiled
    root_change = next(change for change in payload["changes"] if change["intent"]["name"] == "CreateElement")
    root_body = root_change["body"]
    assert root_change["path_array"] == ["%ed", reusable_ref]
    assert root_body["%x"] == "CustomDefinition"
    assert root_body["%nm"] == "fileUploaderCopy"
    assert "%s" not in root_body
    assert root_body["%wf"]
    custom_state_changes = [
        change for change in payload["changes"] if change["intent"]["name"] == "CreateCustomState"
    ]
    assert len(custom_state_changes) == 1
    assert custom_state_changes[0]["path_array"] == ["%ed", reusable_ref, "custom_states", "file_"]
    assert custom_state_changes[0]["body"] == {
        "%d": "file",
        "%v": "file",
        "make_static": True,
        "rank": 0,
    }
    child_body = next(iter(root_body["%el"].values()))
    assert child_body["%nm"] == "gp file"
    assert child_body["%s"]
    serialized = str(root_body)
    assert "bSourceRoot" not in serialized
    assert "bGroupRoot" not in serialized
    assert "bWorkflowRoot" not in serialized
    assert "bActionRoot" not in serialized
