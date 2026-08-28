from __future__ import annotations

import json
from typing import Any

from bubble_mcp.aria_runtime.global_expressions import GlobalExpressionService


class _FixedIds:
    def element_id(self, length: int = 5) -> str:
        return "bGEX0"

    def session_id(self) -> str:
        return "1787859849554x48"


class _Host:
    appname = "global-expression-test"

    def __init__(
        self,
        expressions: dict[str, Any] | None = None,
        folders: dict[str, Any] | None = None,
    ) -> None:
        self.id_gen = _FixedIds()
        self.discovery: dict[str, Any] = {
            "global_expressions": expressions or {},
            "global_expression_folders": folders or {},
        }
        self.dispatched: list[dict[str, Any]] = []

    def global_expression_snapshot(self) -> dict[str, Any]:
        return self.discovery["global_expressions"]

    def global_expression_folder_snapshot(self) -> dict[str, Any]:
        return self.discovery["global_expression_folders"]

    def dispatch_global_expression_payload(self, payload: Any) -> None:
        self.dispatched.append(payload.build())


def _changes_by_path(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {"/".join(change["path_array"]): change for change in payload["changes"]}


def test_create_global_expression_registers_node_and_index() -> None:
    host = _Host()
    service = GlobalExpressionService(host)

    assert service.create_global_expression("User email") is True

    assert len(host.dispatched) == 1
    changes = _changes_by_path(host.dispatched[0])

    node = changes["global_expressions/bGEX0"]
    assert node["intent"]["name"] == "CreateGlobalExpression"
    assert node["body"] == {
        "%nm": "User email",
        "btype_id": "text",
        "id": "bGEX0",
        "is_list": False,
    }

    id_to_path = changes["_index/id_to_path/bGEX0"]
    assert id_to_path["intent"]["name"] == "Update index"
    assert id_to_path["body"] == "global_expressions.bGEX0"

    issues = changes["_index/issues_list/bGEX0"]
    assert issues["intent"]["name"] == "Update index"
    assert json.loads(issues["body"])[0]["node"]["constructor_name"] == "GlobalExpression"


def test_set_parameter_targets_existing_expression_by_name() -> None:
    host = _Host(
        {
            "bTGOw0": {
                "id": "bTGOw0",
                "%nm": "User email",
                "btype_id": "text",
                "is_list": False,
            }
        }
    )
    service = GlobalExpressionService(host)

    assert service.set_global_expression_parameter("User email", "user", parameter_type="user") is True

    changes = _changes_by_path(host.dispatched[0])
    parameter = changes["global_expressions/bTGOw0/parameters/bGEX0"]
    assert parameter["intent"]["name"] == "ModifyGlobalExpression"
    assert parameter["body"] == {
        "btype_id": "user",
        "is_list": False,
        "param_id": "bGEX0",
        "param_name": "user",
    }


def test_set_parameter_refuses_unknown_expression() -> None:
    host = _Host()
    service = GlobalExpressionService(host)

    assert service.set_global_expression_parameter("Missing", "user") is False
    assert host.dispatched == []


def _expression_with_parameter() -> _Host:
    return _Host(
        {
            "bTGOw0": {
                "id": "bTGOw0",
                "%nm": "User email",
                "btype_id": "text",
                "is_list": False,
                "parameters": {
                    "bTGPA0": {
                        "param_id": "bTGPA0",
                        "param_name": "user",
                        "btype_id": "user",
                        "is_list": False,
                    }
                },
            }
        }
    )


def test_set_expression_roots_on_a_parameter_reference() -> None:
    host = _expression_with_parameter()
    service = GlobalExpressionService(host)

    assert service.set_global_expression_expression("User email", parameter="user") is True

    changes = _changes_by_path(host.dispatched[0])
    expression = changes["global_expressions/bTGOw0/expression"]
    assert expression["intent"]["name"] == "ModifyGlobalExpression"
    assert expression["body"] == {
        "%x": "GlobalExpressionParameter",
        "%p": {"global_expression_id": "bTGOw0", "param_id": "bTGPA0"},
        "%n": None,
        "is_slidable": False,
    }


def test_set_expression_chains_a_field_onto_the_parameter() -> None:
    host = _expression_with_parameter()
    service = GlobalExpressionService(host)

    assert service.set_global_expression_expression("User email", parameter="user", field="email") is True

    expression = _changes_by_path(host.dispatched[0])["global_expressions/bTGOw0/expression"]
    assert expression["body"]["%n"] == {"%x": "Message", "%nm": "email", "is_slidable": False}


def test_set_expression_refuses_unknown_parameter() -> None:
    host = _expression_with_parameter()
    service = GlobalExpressionService(host)

    assert service.set_global_expression_expression("User email", parameter="missing") is False
    assert host.dispatched == []


def test_expression_resolves_by_its_decoded_export_name() -> None:
    """The .bubble export decodes ``%nm`` to ``name``; both forms must resolve."""
    host = _Host(
        {
            "bTGOu0": {
                "id": "bTGOu0",
                "name": "zz-expr-1",
                "btype_id": "text",
                "is_list": False,
            }
        }
    )
    service = GlobalExpressionService(host)

    assert service.set_global_expression_parameter("zz-expr-1", "user") is True

    changes = _changes_by_path(host.dispatched[0])
    assert "global_expressions/bTGOu0/parameters/bGEX0" in changes


FOLDER_PATH = "settings/client_safe/global_expression_folder_list"


def _named_expression(folder_id: str | None = None) -> _Host:
    definition: dict[str, Any] = {
        "id": "bTGOw0",
        "%nm": "User email",
        "btype_id": "text",
        "is_list": False,
    }
    if folder_id is not None:
        definition["folder_id"] = folder_id
    return _Host({"bTGOw0": definition})


def test_delete_global_expression_clears_the_node_and_both_index_entries() -> None:
    host = _named_expression()
    service = GlobalExpressionService(host)

    assert service.delete_global_expression("User email") is True

    changes = _changes_by_path(host.dispatched[0])
    assert changes["global_expressions/bTGOw0"]["intent"]["name"] == "DeleteGlobalExpression"
    assert changes["global_expressions/bTGOw0"]["body"] is None
    assert changes["_index/id_to_path/bTGOw0"]["intent"]["name"] == "IdToPathFixer"
    assert changes["_index/id_to_path/bTGOw0"]["body"] is None
    assert changes["_index/issues_list/bTGOw0"]["body"] is None


def test_delete_refuses_an_unknown_expression() -> None:
    host = _Host()
    service = GlobalExpressionService(host)

    assert service.delete_global_expression("Missing") is False
    assert host.dispatched == []


def test_create_folder_stores_the_folder_name_as_the_setting_value() -> None:
    host = _Host()
    service = GlobalExpressionService(host)

    assert service.create_global_expression_folder("probe folder") is True

    change = _changes_by_path(host.dispatched[0])[f"{FOLDER_PATH}/bGEX0"]
    assert change["intent"]["name"] == "ChangeAppSetting"
    assert change["body"] == "probe folder"


def test_rename_folder_resolves_the_folder_by_its_current_name() -> None:
    host = _Host(folders={"bTGPN": "folder test"})
    service = GlobalExpressionService(host)

    assert service.rename_global_expression_folder("folder test", "renamed folder") is True

    change = _changes_by_path(host.dispatched[0])[f"{FOLDER_PATH}/bTGPN"]
    assert change["body"] == "renamed folder"


def test_delete_folder_also_clears_folder_id_on_its_members() -> None:
    host = _named_expression(folder_id="bTGPN")
    host.discovery["global_expression_folders"] = {"bTGPN": "folder test"}
    service = GlobalExpressionService(host)

    assert service.delete_global_expression_folder("folder test") is True

    changes = _changes_by_path(host.dispatched[0])
    assert changes[f"{FOLDER_PATH}/bTGPN"]["body"] is None
    orphan = changes["global_expressions/bTGOw0/folder_id"]
    assert orphan["intent"]["name"] == "ModifyGlobalExpression"
    assert orphan["body"] is None


def test_delete_folder_leaves_expressions_in_other_folders_alone() -> None:
    host = _named_expression(folder_id="bOTHER")
    host.discovery["global_expression_folders"] = {"bTGPN": "folder test", "bOTHER": "other"}
    service = GlobalExpressionService(host)

    assert service.delete_global_expression_folder("folder test") is True

    assert "global_expressions/bTGOw0/folder_id" not in _changes_by_path(host.dispatched[0])


def test_move_expression_into_a_folder_writes_only_folder_id() -> None:
    host = _named_expression()
    host.discovery["global_expression_folders"] = {"bTGPN": "folder test"}
    service = GlobalExpressionService(host)

    assert service.set_global_expression_folder("User email", "folder test") is True

    changes = _changes_by_path(host.dispatched[0])
    assert list(changes) == ["global_expressions/bTGOw0/folder_id"]
    assert changes["global_expressions/bTGOw0/folder_id"]["body"] == "bTGPN"


def test_move_expression_out_of_every_folder_clears_folder_id() -> None:
    host = _named_expression(folder_id="bTGPN")
    host.discovery["global_expression_folders"] = {"bTGPN": "folder test"}
    service = GlobalExpressionService(host)

    assert service.set_global_expression_folder("User email", None) is True

    assert _changes_by_path(host.dispatched[0])["global_expressions/bTGOw0/folder_id"]["body"] is None


def test_move_refuses_an_unknown_folder() -> None:
    host = _named_expression()
    service = GlobalExpressionService(host)

    assert service.set_global_expression_folder("User email", "no such folder") is False
    assert host.dispatched == []


def test_folder_listing_reports_each_folder_with_its_members() -> None:
    host = _named_expression(folder_id="bTGPN")
    host.discovery["global_expression_folders"] = {"bTGPN": "folder test", "bEMPTY": "empty one"}
    service = GlobalExpressionService(host)

    assert service.list_global_expression_folders() == [
        {"id": "bTGPN", "name": "folder test", "expression_ids": ["bTGOw0"]},
        {"id": "bEMPTY", "name": "empty one", "expression_ids": []},
    ]


def test_a_deleted_folder_is_neither_listed_nor_resolvable() -> None:
    """The overlay keeps the null a delete wrote; that folder is gone, not renamed to its id."""
    host = _named_expression()
    host.discovery["global_expression_folders"] = {"bALIVE": "still here", "bDEAD": None}
    service = GlobalExpressionService(host)

    assert service.list_global_expression_folders() == [
        {"id": "bALIVE", "name": "still here", "expression_ids": []}
    ]
    assert service.set_global_expression_folder("User email", "bDEAD") is False
    assert host.dispatched == []
