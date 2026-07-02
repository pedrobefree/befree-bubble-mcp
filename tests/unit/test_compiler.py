from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.sessions.store import session_from_payload


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def test_compile_create_text_step_to_write_payload() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {"context": "index", "parent": "index", "content": "Hello", "name": "tx_hello"},
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["appname"] == "synthetic-app"
    assert payload["changes"][0]["intent"]["name"] == "Update index"
    assert payload["changes"][1]["intent"]["name"] == "CreateElement"
    assert payload["changes"][1]["path_array"][:2] == ["%p3", "index"]
    assert payload["changes"][1]["path_array"][-2] == "%el"
    assert payload["changes"][1]["body"]["%x"] == "Text"
    assert payload["changes"][1]["body"]["%p"]["%3"] == "Hello"
    assert payload["changes"][2]["path_array"][:2] == ["_index", "issues_list"]


def test_compile_create_group_step_to_write_payload() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_group",
                "args": {"context": "index", "parent": "index", "name": "Card", "layout": "row"},
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["changes"][1]["body"]["%x"] == "Group"
    assert payload["changes"][1]["body"]["%p"]["container_layout"] == "row"


def test_compile_create_text_with_real_bubble_context_indices() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {
                    "context": "index",
                    "context_key": "bTKhs",
                    "root_id": "bTKhr",
                    "existing_children": ["bTilt", "bTKiP"],
                    "content": "Hello",
                    "name": "Text A",
                    "slot_key": "bcFhj0",
                    "id_counter": 11263917,
                },
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["changes"][0]["path_array"] == ["_index", "id_to_path", payload["changes"][1]["body"]["id"]]
    assert payload["changes"][0]["body"] == "%p3.bTKhs.%el.bcFhj0"
    assert payload["changes"][1]["intent"]["name"] == "CreateElement"
    assert payload["changes"][1]["path_array"] == ["%p3", "bTKhs", "%el", "bcFhj0"]
    assert payload["changes"][2]["path_array"] == ["_index", "issues_list", payload["changes"][1]["body"]["id"]]
    assert payload["changes"][3]["path_array"] == ["_index", "issues_sub", "bTKhr"]
    assert payload["changes"][4]["type"] == "id_counter"


def test_compile_create_text_inside_reusable_context() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {
                    "context": "mcp_card",
                    "context_key": "bReusableSlot",
                    "context_type": "reusable",
                    "parent": "root",
                    "parent_id": "bReusableRoot",
                    "existing_children": [],
                    "content": "Reusable text",
                    "name": "Reusable Text",
                    "slot_key": "bTextSlot",
                },
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["changes"][0]["body"] == "%ed.bReusableSlot.%el.bTextSlot"
    assert payload["changes"][1]["path_array"] == ["%ed", "bReusableSlot", "%el", "bTextSlot"]
    assert payload["changes"][3]["path_array"] == ["_index", "issues_sub", "bReusableRoot"]


def test_execute_plan_can_compile_missing_payload_before_execution() -> None:
    class FakeClient:
        def write(self, payload, session, *, dry_run=False):  # type: ignore[no-untyped-def]
            return {"ok": True, "payload": payload, "dry_run": dry_run}

    session = session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}})
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {"context": "index", "content": "Hello"},
            }
        ]
    }

    result = execute_plan(
        plan,
        profile="dev",
        execute=True,
        compile_missing=True,
        session=session,
        client=FakeClient(),  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert first_change(result["results"][0]["result"]["payload"], "CreateElement")["body"]["%x"] == "Text"


def test_compile_update_text_and_delete_element() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "update_text",
                "args": {"context": "index", "element_name": "Title", "content": "Updated"},
            },
            {
                "id": "s2",
                "tool_name": "delete_element",
                "args": {"context": "index", "element_name": "Old"},
            },
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")

    assert compiled["steps"][0]["args"]["write_payload"]["changes"][0]["intent"]["name"] == "SetData"
    assert compiled["steps"][0]["args"]["write_payload"]["changes"][0]["path_array"][-2:] == ["%p", "%3"]
    assert compiled["steps"][1]["args"]["write_payload"]["changes"][0]["intent"]["name"] == "Delete"


def test_compile_schema_option_theme_and_workflow_tools() -> None:
    plan = {
        "steps": [
            {"id": "s1", "tool_name": "create_data_type", "args": {"name": "Audit Log"}},
            {
                "id": "s2",
                "tool_name": "create_data_field",
                "args": {"data_type_key": "audit_log", "field_name": "Severity", "field_type": "text"},
            },
            {"id": "s3", "tool_name": "create_option_set", "args": {"name": "Status"}},
            {"id": "s4", "tool_name": "create_option_value", "args": {"option_set_key": "os_status", "label": "Open"}},
            {"id": "s5", "tool_name": "create_color", "args": {"name": "Brand", "rgba": "rgba(1,2,3,1)"}},
            {"id": "s6", "tool_name": "create_style", "args": {"name": "Primary", "element_type": "Button"}},
            {"id": "s7", "tool_name": "create_workflow", "args": {"context": "index", "event": "click", "element_name": "Button"}},
            {"id": "s8", "tool_name": "add_action", "args": {"context": "index", "workflow_id": "wf1", "action_type": "navigate"}},
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")

    payloads = [step["args"]["write_payload"] for step in compiled["steps"]]
    assert all(payload["changes"] for payload in payloads)
    assert payloads[0]["changes"][0]["path_array"][:2] == ["data_types", "audit_log"]
    assert payloads[2]["changes"][0]["path_array"][:2] == ["option_sets", "os_status"]
    assert payloads[6]["changes"][0]["path_array"][:3] == ["%p3", "index", "%wf"]


def test_compile_generic_visual_catalog_tools() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_button",
                "args": {"context": "index", "parent": "index", "name": "CTA", "label": "Continue"},
            },
            {
                "id": "s2",
                "tool_name": "update_input",
                "args": {"context": "index", "element_name": "email_input", "placeholder": "Email"},
            },
            {
                "id": "s3",
                "tool_name": "delete_button",
                "args": {"context": "index", "element_name": "old_button"},
            },
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")

    create_payload = compiled["steps"][0]["args"]["write_payload"]
    update_payload = compiled["steps"][1]["args"]["write_payload"]
    delete_payload = compiled["steps"][2]["args"]["write_payload"]

    create_change = first_change(create_payload, "CreateElement")
    assert create_change["body"]["%x"] == "Button"
    assert create_change["body"]["%p"]["%3"] == "Continue"
    assert update_payload["changes"][0]["intent"]["name"] == "SetData"
    assert update_payload["changes"][0]["body"]["placeholder"] == "Email"
    assert delete_payload["changes"][0]["intent"]["name"] == "Delete"
