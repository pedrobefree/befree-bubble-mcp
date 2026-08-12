import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime import bubble_sdk
from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder


class SequentialIds:
    def __init__(self) -> None:
        self.counter = 0

    def element_id(self) -> str:
        self.counter += 1
        return f"bNEW{self.counter}"

    def session_id(self) -> str:
        return "session-next"


@pytest.fixture
def builder() -> PayloadBuilder:
    result = PayloadBuilder(appname="app", app_version="development")
    result.id_gen = SequentialIds()
    result.session_id = "session-fixed"
    return result


def change_names(builder: PayloadBuilder) -> list[str]:
    return [change["intent"]["name"] for change in builder.changes]


def test_collect_ids_shares_aliases_and_walks_nested_lists(builder: PayloadBuilder) -> None:
    source = {
        "id": "root-old",
        "param_id": "parameter-old",
        "elements": {
            "child-key": {"id": "child-old"},
            "alias-key": {"id": "root-old"},
            "orphan-key": {},
        },
        "workflows": {"workflow-key": "not-a-dict"},
        "items": [{"id": "nested-old"}],
    }
    mapping: dict[str, str] = {}

    builder.collect_ids(source, mapping)

    assert mapping["root-old"] == "bNEW1"
    assert mapping["parameter-old"] == "bNEW2"
    assert mapping["child-key"] == mapping["child-old"] == "bNEW3"
    assert mapping["alias-key"] == mapping["root-old"]
    assert mapping["orphan-key"] == "bNEW4"
    assert mapping["workflow-key"] == "bNEW5"
    assert mapping["nested-old"] == "bNEW6"


def test_resolve_type_supports_direct_case_insensitive_and_passthrough() -> None:
    plain = PayloadBuilder()
    assert plain._resolve_type("User") == "User"

    mapped = PayloadBuilder(metadata={"User": "custom.user"})
    assert mapped._resolve_type("User") == "custom.user"
    assert mapped._resolve_type("user") == "custom.user"
    assert mapped._resolve_type("custom.order") == "custom.order"


def test_string_conversion_remaps_ids_parameters_names_and_reusable_aliases(
    builder: PayloadBuilder,
) -> None:
    assert builder.convert_to_api_format(
        "param_child-old", id_mapping={"child-old": "bNEW1"}
    ) == "param_bNEW1"
    assert builder.convert_to_api_format(
        "prefix-root-old-child-old",
        id_mapping={"root-old": "bROOT", "child-old": "bCHILD"},
    ) == "prefix-bROOT-bCHILD"
    assert builder.convert_to_api_format(
        "Original / Original-child / xOriginal",
        name_mapping={"Original": "Clone"},
    ) == "Clone / Original-child / xOriginal"
    assert builder.convert_to_api_format(
        "custom.settings_nav_", is_reusable=True
    ) == "custom.profile_nav_"


def test_conversion_maps_structures_properties_and_references(builder: PayloadBuilder) -> None:
    source = {
        "type": "Group",
        "properties": {"width": 320, "background_color": "red"},
        "elements": {"child-old": {"id": "child-old", "type": "Text"}},
        "workflows": {"workflow-old": {"id": "workflow-old", "actions": {}}},
        "values": ["child-old", 2, True, None],
    }
    converted = builder.convert_to_api_format(
        source,
        id_mapping={"child-old": "bCHILD", "workflow-old": "bWORKFLOW"},
    )

    assert converted["%x"] == "Group"
    assert converted["%p"] == {"%w": 320, "%bgc": "red"}
    assert converted["%el"]["bCHILD"]["id"] == "bCHILD"
    assert converted["%wf"]["bWORKFLOW"]["id"] == "bWORKFLOW"
    assert converted["values"] == ["bCHILD", 2, True, None]


@pytest.mark.parametrize("expression_type", ["ElementParent", "Breakpoint", "PageData", "State"])
def test_conversion_adds_required_empty_expression_slots(
    builder: PayloadBuilder,
    expression_type: str,
) -> None:
    assert builder.convert_to_api_format({"type": expression_type}) == {
        "%x": expression_type,
        "%p": None,
        "%n": None,
    }


def test_message_and_get_element_expression_defaults_are_surgical(
    builder: PayloadBuilder,
) -> None:
    function = builder.convert_to_api_format({"type": "Message", "args": {"0": "value"}})
    assert function["%a"] == {"0": "value"}
    assert function["%p"] is None
    assert function["%n"] is None

    terminal = builder.convert_to_api_format({"type": "Message", "name": "value_text"})
    assert "%p" not in terminal
    assert "%n" not in terminal

    get_element = builder.convert_to_api_format({"type": "GetElement"})
    assert get_element == {"%x": "GetElement"}


def test_custom_state_conversion_infers_and_resolves_types() -> None:
    builder = PayloadBuilder(metadata={"User": "custom.user"})
    declarations = builder.convert_to_api_format(
        {
            "custom_states": {
                "selected_user_": {"name": "Selected User", "type": "User"},
                "inferred_": {"value": "custom.order"},
                "primitive_": "text",
            }
        }
    )["%s"]

    assert declarations["selected_user_"] == {
        "%nm": "Selected User",
        "%gt": "custom.user",
    }
    assert declarations["inferred_"] == {"%v": "custom.order", "%gt": "custom.order"}
    assert declarations["primitive_"] == "text"


def test_reusable_conditionals_use_numeric_state_keys_and_state_type(
    builder: PayloadBuilder,
) -> None:
    converted = builder.convert_to_api_format(
        {"states": {"hover": {"value": "yes", "properties": {"color": "red"}}}},
        is_reusable=True,
    )
    state = converted["%s"]["0"]
    assert state["%x"] == "State"
    assert state["%v"] == "yes"
    assert state["%p"] == {"%fc": "red"}


def test_uncompressed_custom_state_uses_modular_keys(builder: PayloadBuilder) -> None:
    converted = builder.convert_to_api_format(
        {"custom_states": {"selected_": {"type": "custom.user", "name": "Selected"}}},
        compressed=False,
    )
    assert converted["custom_states"]["selected_"] == {
        "value": "custom.user",
        "name": "Selected",
    }


def test_custom_state_and_element_conditional_changes(builder: PayloadBuilder) -> None:
    assert builder.add_custom_state(
        "element",
        "Selected User",
        {"type": "custom.user", "rank": 3, "default_val": "first"},
    ) is builder
    custom_state = builder.changes[-1]
    assert custom_state["path_array"] == [
        "%ed",
        "element",
        "custom_states",
        "selected_user_",
    ]
    assert custom_state["body"] == {
        "%d": "Selected User",
        "%v": "custom.user",
        "make_static": True,
        "rank": 3,
        "default_val": "first",
    }

    builder.add_custom_state("element", "Ready_", {})
    assert builder.changes[-1]["body"]["%v"] == "text"
    assert "default_val" not in builder.changes[-1]["body"]

    condition = {"type": "CurrentUser"}
    builder.add_element_conditional("element", 2, condition, {"is_visible": False})
    assert builder.changes[-1]["path_array"] == ["%ed", "element", "%c"]
    assert builder.changes[-1]["body"]["2"]["%p"] == {"%iv": False}

    builder.add_element_conditional(
        "element",
        0,
        condition,
        {"width": 100},
        child_id="child",
    )
    assert builder.changes[-1]["path_array"] == ["%ed", "element", "%el", "child", "%c"]


def test_create_element_rejects_invalid_paths_and_builds_valid_change(
    builder: PayloadBuilder,
) -> None:
    with pytest.raises(ValueError, match="Path inválido"):
        builder.add_create_element(["invalid"], {"id": "element"})

    assert builder.add_create_element(["%ed", "element"], {"id": "element"}) is builder
    change = builder.changes[-1]
    assert change["intent"]["name"] == "CreateElement"
    assert change["path_array"] == ["%ed", "element"]
    assert change["session_id"] == "session-fixed"


def test_clone_reusable_remaps_names_ids_and_registers_non_dict_children(
    builder: PayloadBuilder,
) -> None:
    source = {
        "id": "source-root",
        "name": "Original",
        "type": "CustomDefinition",
        "properties": {"type_of_content": "custom.user"},
        "elements": {
            "child-text": "not-a-dict",
            "child-group": {"id": "child-group", "name": "CLONE_previous_v1"},
        },
        "notes": ["CLONE_previous_v1"],
    }

    returned, mapping = builder.add_clone_reusable(
        "source-root",
        "clone-root",
        "CLONE_current_v2",
        source,
    )

    assert returned is builder
    assert mapping["source-root"] == "clone-root"
    create = next(change for change in builder.changes if change["intent"]["name"] == "CreateElement")
    assert create["path_array"] == ["%ed", "clone-root"]
    assert create["body"]["%nm"] == "CLONE_current_v2"
    assert create["body"]["id"] == "clone-root"
    assert create["body"]["%x"] == "CustomDefinition"
    assert create["body"]["%gt"] == "custom.user"
    assert create["body"]["notes"] == ["CLONE_current_v2"]


def test_style_delete_and_generic_change_helpers(builder: PayloadBuilder) -> None:
    assert builder.add_create_style("style", {"%nm": "Primary"}) is builder
    assert builder.add_delete_style("style") is builder
    assert change_names(builder) == ["CreateStyle", "DeleteStyle", "IdToPathFixer"]
    assert builder.changes[-1]["path_array"] == ["_index", "id_to_path", "style"]

    builder.register_issues_sub("parent", ["child"])
    builder.add_set_style_data(["styles", "style", "%p", "%fc"], "red")
    builder.add_intent({"intent": "Custom", "path": ["path"], "body": {"ok": True}})
    builder.add_intent({})
    assert change_names(builder)[-4:] == ["SetData", "SetStyleData", "Custom", "SetData"]


def test_update_index_normalizes_shorthand_and_preserves_canonical_path(
    builder: PayloadBuilder,
) -> None:
    builder.add_update_index("element", "path")  # type: ignore[arg-type]
    assert builder.changes[-1]["path_array"] == ["_index", "id_to_path", "element"]
    assert builder.changes[-1]["session_id"] == "session-next"

    path = ["_index", "issues_list", "element"]
    builder.add_update_index(path, "[]")
    assert builder.changes[-1]["path_array"] is path


def test_workflow_and_app_setting_helpers_build_expected_paths(builder: PayloadBuilder) -> None:
    workflow = {"id": "workflow", "%x": "ButtonClicked"}
    action = {"id": "action", "%x": "ShowElement"}

    assert builder.add_create_workflow("page", workflow) is builder
    assert builder.changes[-1]["path_array"] == ["%p3", "page", "%wf", "workflow"]
    assert builder.add_workflow_action("page", "workflow", 4, action) is builder
    assert builder.changes[-1]["path_array"] == [
        "%p3",
        "page",
        "%wf",
        "workflow",
        "actions",
        "4",
    ]
    assert builder.add_create_event(["events", "workflow"], workflow) is builder
    assert builder.changes[-1]["intent"]["name"] == "CreateEvent"
    assert builder.add_create_action(["actions", "0"], action) is builder
    assert builder.changes[-1]["intent"]["name"] == "CreateAction"
    assert builder.add_change_app_setting(["settings", "colors"], {"primary": "red"}) is builder
    assert builder.changes[-1]["intent"]["name"] == "ChangeAppSetting"


def test_build_serialization_save_and_raw_change(builder: PayloadBuilder, tmp_path: Path) -> None:
    raw = {"intent": {"name": "Raw"}, "path_array": [], "body": None}
    assert builder.add_change_raw(raw) is builder
    assert builder.build() == {
        "v": 1,
        "appname": "app",
        "app_version": "development",
        "changes": [raw],
    }
    assert json.loads(builder.to_json(indent=0)) == builder.build()

    target = tmp_path / "payload.json"
    builder.save(str(target))
    assert json.loads(target.read_text()) == builder.build()


def test_send_to_webhook_passes_built_payload(monkeypatch, builder: PayloadBuilder) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, Any] = {}

    class FakeWebhookClient:
        def __init__(self, *, url: str, app_name: str) -> None:
            captured.update(url=url, app_name=app_name)

        def send(self, payload: dict[str, Any]) -> dict[str, Any]:
            captured["payload"] = payload
            return {"ok": True}

    monkeypatch.setattr(bubble_sdk, "WebhookClient", FakeWebhookClient)

    assert builder.send_to_webhook("local://test") == {"ok": True}
    assert captured == {
        "url": "local://test",
        "app_name": "app",
        "payload": builder.build(),
    }
