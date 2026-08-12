from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import ActionBuilder


class FixedIds:
    def element_id(self) -> str:
        return "bACTION"


@pytest.fixture
def builder() -> ActionBuilder:
    return ActionBuilder(FixedIds())


def unwrap(action: dict[str, Any], index: int = 0) -> dict[str, Any]:
    payload = action[str(index)]
    assert payload["id"] == "bACTION"
    return payload


@pytest.mark.parametrize(
    ("method", "action_type", "properties"),
    [
        ("refresh_page", "RefreshPage", None),
        ("go_previous", "GoPrevious", None),
        ("terminate_workflow", "TerminateWorkflow", None),
        ("log_out_user", "LogOut", {}),
    ],
)
def test_parameterless_actions_preserve_wire_contract(
    builder: ActionBuilder,
    method: str,
    action_type: str,
    properties: Any,
) -> None:
    action = unwrap(getattr(builder, method)(index=3), 3)
    assert action["%x"] == action_type
    assert action["%p"] == properties


def test_reset_and_pause_actions_cover_minimal_and_scoped_variants(
    builder: ActionBuilder,
) -> None:
    assert unwrap(builder.reset_inputs())["%p"] is None
    assert unwrap(builder.reset_inputs(element_id="group"))["%p"] == {"%ei": "group"}
    assert unwrap(builder.pause_workflow_client())["%p"] is None
    assert unwrap(builder.pause_workflow_client(length="250", hide_status_bar=1))["%p"] == {
        "length": 250,
        "hide_status_bar": True,
    }


def test_navigation_actions_normalize_optional_properties(builder: ActionBuilder) -> None:
    assert unwrap(builder.open_url(url="https://example.com", open_in_new_tab=False))["%p"] == {
        "url": {"%x": "TextExpression", "%e": {"0": "https://example.com"}},
        "%o9": False,
    }

    minimal = unwrap(builder.navigate_to_page(page_name="index"))["%p"]
    assert minimal == {"element_id": "index", "%ei": "index"}

    data = {"%x": "CurrentUser"}
    parameters = {"source": "campaign"}
    complete = unwrap(
        builder.navigate_to_page(
            page_name="dashboard",
            send_data=data,
            open_in_new_tab=1,
            keep_current_page_params=0,
            add_parameters=True,
            url_parameters=parameters,
        )
    )["%p"]
    assert complete == {
        "element_id": "dashboard",
        "%ei": "dashboard",
        "data_to_send": data,
        "%o9": True,
        "keep_current_page_params": False,
        "add_parameters": True,
        "url_parameters": parameters,
    }


@pytest.mark.parametrize(
    ("method", "action_type"),
    [
        ("show_element", "ShowElement"),
        ("hide_element", "HideElement"),
        ("toggle_element", "ToggleElement"),
        ("set_focus_to_element", "SetFocusToElement"),
    ],
)
def test_element_actions_target_the_requested_element(
    builder: ActionBuilder,
    method: str,
    action_type: str,
) -> None:
    action = unwrap(getattr(builder, method)(element_id="element"))
    assert action["%x"] == action_type
    assert action["%p"] == {"%ei": "element"}


def test_richer_element_actions_include_only_supplied_options(builder: ActionBuilder) -> None:
    assert unwrap(builder.animate_element(element_id="card"))["%p"] == {"%ei": "card"}
    assert unwrap(
        builder.animate_element(
            element_id="card",
            animation="fadeIn",
            duration="400",
            customize_duration=1,
        )
    )["%p"] == {
        "%ei": "card",
        "animation": "fadeIn",
        "duration": 400,
        "customize_duration": True,
    }
    assert unwrap(builder.scroll_to_element(element_id="footer"))["%p"] == {"%ei": "footer"}
    assert unwrap(builder.scroll_to_element(element_id="footer", offset="24"))["%p"] == {
        "%ei": "footer",
        "offset": 24,
    }
    assert unwrap(builder.display_group_data(element_id="group"))["%p"] == {"%ei": "group"}
    assert unwrap(
        builder.display_group_data(element_id="group", data_source={"%x": "CurrentUser"})
    )["%p"]["%ds"] == {"%x": "CurrentUser"}
    assert unwrap(builder.set_custom_state(element_id="group"))["%p"] == {"%ei": "group"}
    assert unwrap(
        builder.set_custom_state(element_id="group", custom_state="active", value=False)
    )["%p"] == {"%ei": "group", "custom_state": "active", "%v": False}


def test_change_thing_normalizes_all_supported_field_value_kinds(
    builder: ActionBuilder,
) -> None:
    expression = {"%x": "CurrentPageThing"}
    values = {
        "dynamic": expression,
        "enabled": False,
        "count": 3,
        "ratio": 1.5,
        "tags": ["one"],
        "name": "Ada",
        "fallback": None,
    }
    action = unwrap(builder.make_changes_to_thing(field_values=values))
    props = action["%p"]
    assert props["%tc"] == {"%x": "CurrentUser", "%p": None, "%n": None}
    fields = props["%cs"]
    assert fields["0"]["%v"] is expression
    assert fields["1"]["%v"] is False
    assert fields["2"]["%v"] == 3
    assert fields["3"]["%v"] == 1.5
    assert fields["4"]["%v"] == ["one"]
    assert fields["5"]["%v"]["%e"]["0"] == "Ada"
    assert fields["6"]["%v"]["%e"]["0"] == "None"
    assert unwrap(builder.make_changes_to_thing(thing_expr=expression, field_values={}))["%p"] == {
        "%tc": expression,
        "%cs": {},
    }


def test_change_list_and_create_thing_normalize_field_values(builder: ActionBuilder) -> None:
    expression = {"%x": "Search", "%p": {}}
    values = {
        "dynamic": expression,
        "enabled": True,
        "count": 2,
        "name": "Ada",
        "fallback": None,
    }
    changed = unwrap(
        builder.make_changes_to_list_of_things(
            type_name="custom.user",
            list_expr=expression,
            field_values=values,
        )
    )["%p"]
    assert changed["type_to_change"] == "custom.user"
    assert changed["%tc"] is expression
    assert [changed["%cs"][str(index)]["%v"] for index in range(3)] == [expression, True, 2]
    assert changed["%cs"]["3"]["%v"]["%e"]["0"] == "Ada"
    assert changed["%cs"]["4"]["%v"]["%e"]["0"] == "None"

    created = unwrap(builder.create_thing(data_type="custom.user", field_values=values))["%p"]
    assert created["%tt"] == "custom.user"
    assert created["%i2"]["0"]["%v"] is expression
    assert created["%i2"]["1"]["%v"] is True
    assert created["%i2"]["2"]["%v"] == 2
    assert created["%i2"]["3"]["%v"]["%e"]["0"] == "Ada"
    assert created["%i2"]["4"]["%v"]["%e"]["0"] == "None"
    assert unwrap(builder.create_thing(field_values=None))["%p"]["%i2"] == {}


@pytest.mark.parametrize("method", ["delete_list_of_things", "copy_list_of_things"])
def test_list_actions_supply_and_normalize_search_expressions(
    builder: ActionBuilder,
    method: str,
) -> None:
    default = unwrap(getattr(builder, method)(type_name="custom.user"))["%p"]
    assert default["to_delete" if method.startswith("delete") else "to_copy"] == {
        "%x": "Search",
        "%p": None,
        "%n": None,
    }

    supplied = {"%x": "Search", "%p": {"type": "custom.user"}}
    normalized = unwrap(getattr(builder, method)(list_expr=supplied))["%p"]
    key = "to_delete" if method.startswith("delete") else "to_copy"
    assert normalized[key]["%n"] is None
    assert "%n" not in supplied

    non_search = {"%x": "CurrentPageThing"}
    assert unwrap(getattr(builder, method)(list_expr=non_search))["%p"][key] is non_search


def test_delete_thing_and_set_slug_cover_default_and_explicit_expressions(
    builder: ActionBuilder,
) -> None:
    assert unwrap(builder.delete_thing())["%p"]["to_delete"]["%x"] == "CurrentUser"
    thing = {"%x": "CurrentPageThing"}
    assert unwrap(builder.delete_thing(thing_expr=thing))["%p"]["to_delete"] is thing

    assert unwrap(builder.set_slug())["%p"]["slug"]["%e"] == {"0": ""}
    assert unwrap(builder.set_slug(thing_expr=thing, slug_expr="profile"))["%p"] == {
        "%tc": thing,
        "slug": {"%x": "TextExpression", "%e": {"0": "profile"}},
    }
    dynamic = {"%x": "CurrentUser", "%n": {"%nm": "name_text"}}
    assert unwrap(builder.set_slug(slug_expr=dynamic))["%p"]["slug"]["%e"] == {"0": dynamic}
    text = {"%x": "TextExpression", "%e": {"0": "existing"}}
    normalized = unwrap(builder.set_slug(slug_expr=text))["%p"]["slug"]
    assert normalized == text
    assert normalized is not text


def test_message_and_auth_actions_preserve_expression_shapes(builder: ActionBuilder) -> None:
    email = unwrap(builder.send_email(to_email="a@b.com", subject="Hello", body="Body"))["%p"]
    assert email["to"]["%e"]["0"] == "a@b.com"
    assert email["subject"]["%e"]["0"] == "Hello"
    assert email["body"]["%e"]["0"] == "Body"

    assert "title" not in unwrap(builder.show_alert(message="Saved"))["%p"]
    alert = unwrap(builder.show_alert(message="Saved", title="Done"))["%p"]
    assert alert["message"]["%e"]["0"] == "Saved"
    assert alert["title"]["%e"]["0"] == "Done"

    signup = unwrap(builder.sign_up_user(email_id="email", password_id="password"))["%p"]
    assert signup["email"]["%e"]["0"]["%n"]["%e"] == "email"
    assert signup["password"]["%e"]["0"]["%n"]["%e"] == "password"

    login = unwrap(builder.log_in_user(email_id="email", password_id="password"))["%p"]
    assert login["email"]["%e"]["0"]["%n"]["%e"] == "email"
    assert login["password"]["%e"]["0"]["%n"]["%e"] == "password"
    assert login["stay_logged_in"] is True
