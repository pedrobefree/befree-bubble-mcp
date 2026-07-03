from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.sessions.store import session_from_payload


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def created_body(payload: dict) -> dict:  # type: ignore[type-arg]
    return first_change(payload, "CreateElement")["body"]


def set_data_value(payload: dict, property_name: str):  # type: ignore[no-untyped-def,type-arg]
    return next(
        change["body"]
        for change in payload["changes"]
        if change.get("intent", {}).get("name") == "SetData" and change.get("path_array", [])[-1:] == [property_name]
    )


def text_expression_value(value):  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        entries = value.get("%e") or value.get("entries") or {}
        if isinstance(entries, dict):
            return "".join(str(entries[key]) for key in sorted(entries, key=lambda item: int(item) if str(item).isdigit() else 9999))
    return value


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
    assert text_expression_value(payload["changes"][1]["body"]["%p"]["%3"]) == "Hello"
    assert payload["changes"][1]["body"]["%p"]["fit_height"] is True
    assert set_data_value(payload, "fit_height") is True
    assert any(change["path_array"][:2] == ["_index", "issues_list"] for change in payload["changes"])


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
    assert ["_index", "issues_list", payload["changes"][1]["body"]["id"]] in [
        change.get("path_array") for change in payload["changes"]
    ]
    assert ["_index", "issues_sub", "bTKhr"] in [change.get("path_array") for change in payload["changes"]]
    assert payload["changes"][-1]["type"] == "id_counter"


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
    assert ["_index", "issues_sub", "bReusableRoot"] in [change.get("path_array") for change in payload["changes"]]


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
    payload = result["results"][0]["result"]["payload"]
    assert first_change(payload, "CreateElement")["body"]["%x"] == "Text"
    assert set_data_value(payload, "fit_height") is True


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
    assert text_expression_value(compiled["steps"][0]["args"]["write_payload"]["changes"][0]["body"]) == "Updated"
    assert compiled["steps"][1]["args"]["write_payload"]["changes"][0]["intent"]["name"] == "Delete"


def test_compile_update_visual_uses_aria_property_shapes() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "update_checkbox",
                "args": {"context": "index", "element_name": "terms", "label": "Accept terms"},
            },
            {
                "id": "s2",
                "tool_name": "update_html",
                "args": {"context": "index", "element_name": "embed", "content": "<div>ok</div>"},
            },
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    checkbox_body = compiled["steps"][0]["args"]["write_payload"]["changes"][0]["body"]
    html_body = compiled["steps"][1]["args"]["write_payload"]["changes"][0]["body"]

    assert "%lab" in checkbox_body
    assert text_expression_value(checkbox_body["%lab"]) == "Accept terms"
    assert "%3" not in checkbox_body
    assert "%ht" in html_body
    assert text_expression_value(html_body["%ht"]) == "<div>ok</div>"


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
    assert text_expression_value(create_change["body"]["%p"]["%3"]) == "Continue"
    assert create_change["body"]["%p"]["%nm"] == "bt_cta"
    assert set_data_value(create_payload, "fit_height") is True
    assert set_data_value(create_payload, "fit_width") is True
    assert update_payload["changes"][0]["intent"]["name"] == "SetData"
    assert update_payload["changes"][0]["body"]["placeholder"] == "Email"
    assert delete_payload["changes"][0]["intent"]["name"] == "Delete"


def test_create_visual_defaults_and_name_prefixes() -> None:
    cases = [
        ("create_button", {"label": "Continue"}, "bt_continue", {"fit_width": True, "fit_height": True}),
        ("create_text", {"content": "Hello"}, "tx_hello", {"fit_height": True}),
        ("create_icon", {}, "ic_icon", {"%w": 20, "%h": 20, "fixed_width": True, "fixed_height": True, "single_width": True, "single_height": True}),
        ("create_link", {}, "li_link_label", {"%3": "Link label"}),
        ("create_image", {}, "im_image", {"%w": 120, "fixed_width": True, "single_width": True, "min_height_css": "64px"}),
        ("create_shape", {}, "sh_shape", {"%w": 120, "%h": 120, "fixed_width": True, "fixed_height": True, "single_width": True, "single_height": True}),
        ("create_alert", {}, "al_alert_content", {"%3": "Alert content", "at_to_top": True, "fit_height": True}),
        (
            "create_video",
            {},
            "vd_id",
            {"video_id": "id", "use_aspect_ratio": True, "aspect_ratio_width": 16, "aspect_ratio_height": 9, "%w": 360, "fixed_width": True, "single_width": True},
        ),
        ("create_html", {}, "html_html", {"%ht": "<html>...</html>", "fit_height": True, "min_height_css": "120px", "%w": 240, "fixed_width": True, "single_width": True}),
        ("create_map", {}, "map_map", {"%w": 360, "%h": 240, "fixed_width": True, "fixed_height": True, "single_width": True, "single_height": True}),
        ("create_group", {}, "gp_group", {"container_layout": "column", "min_height_css": "40px", "fit_height": True, "min_width_css": "40px"}),
        (
            "create_repeating_group",
            {},
            "rg_repeatinggroup",
            {"%gt": "text", "cell_min_height": 32, "cell_min_width": 32, "stable_pagination": True, "min_width_css": "120px", "min_height_css": "120px", "fit_height": True},
        ),
        ("create_popup", {}, "pp_popup", {"min_width_css": "320px", "fit_width": True, "min_height_css": "320px", "fit_height": True}),
        (
            "create_floating_group",
            {},
            "fg_floatinggroup",
            {"float_v_relative": "top", "float_h_relative": "left", "float_zindex": "front", "min_width_css": "0px", "min_height_css": "64px", "fit_height": True},
        ),
        ("create_group_focus", {}, "gf_groupfocus", {"min_width_css": "0px", "min_height_css": "64px", "fit_height": True, "max_width_css": "320px"}),
        ("create_table", {}, "tb_table", {"table_direction": "vertical", "stable_pagination": True, "min_height_css": "120px", "min_width_css": "120px", "fit_height": True}),
        ("create_input", {}, "in_input", {"%h": 44, "fixed_height": True, "single_height": True, "min_width_css": "0px", "max_width_css": "240px"}),
        ("create_multiline_input", {}, "mli_multilineinput", {"min_height_css": "64px", "fit_height": True, "min_width_css": "0px", "max_width_css": "240px"}),
        ("create_checkbox", {}, "cb_checkbox_label", {"%lab": "Checkbox label", "min_height_css": "0px", "min_width_css": "0px", "fit_width": True, "fit_height": True}),
        ("create_dropdown", {}, "dd_dropdown", {"%h": 44, "fixed_height": True, "single_height": True, "min_width_css": "0px", "max_width_css": "240px"}),
        ("create_searchbox", {}, "sb_search", {"placeholder": "Search...", "%h": 44, "fixed_height": True, "single_height": True, "min_width_css": "0px", "max_width_css": "240px"}),
        ("create_radio", {}, "rb_radiobuttons", {"min_height_css": "0px", "min_width_css": "0px", "fit_width": True, "fit_height": True}),
        ("create_slider", {}, "sl_sliderinput", {"%h": 32, "fixed_height": True, "single_height": True, "min_width_css": "0px", "max_width_css": "240px"}),
        ("create_datepicker", {}, "dtp_dateinput", {"%h": 44, "fixed_height": True, "single_height": True, "min_width_css": "0px", "max_width_css": "240px"}),
        ("create_picture_uploader", {}, "pu_pictureinput", {"min_width_css": "0px", "max_width_css": "240px", "%h": 64, "fixed_height": True, "single_height": True}),
        ("create_file_uploader", {}, "fu_fileinput", {"min_width_css": "0px", "max_width_css": "240px", "%h": 64, "fixed_height": True, "single_height": True}),
    ]
    for tool_name, args, expected_name, expected_props in cases:
        plan = {"steps": [{"id": tool_name, "tool_name": tool_name, "args": {"context": "index", **args}}]}
        payload = compile_plan_to_write_payloads(plan, app_id="synthetic-app")["steps"][0]["args"]["write_payload"]
        props = created_body(payload)["%p"]
        assert props["%nm"] == expected_name
        for key, expected_value in expected_props.items():
            assert text_expression_value(props[key]) == expected_value, tool_name
