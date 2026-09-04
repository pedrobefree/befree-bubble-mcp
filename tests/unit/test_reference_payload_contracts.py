"""Regression coverage for structural keys versus Bubble object/root ids."""

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from types import MethodType
from typing import Any

import pytest

from bubble_mcp.aria_dispatch import _method_kwargs
from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.bubble_sdk import PathDiscovery
from bubble_mcp.server.schemas import list_tool_schemas


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def _reference_app() -> dict[str, Any]:
    return {
        "pages": {
            "bTHGO": {"id": "bTHGI", "name": "login", "elements": {}},
            "bpfznz": {
                "id": "bpnlwp",
                "name": "salon-certification",
                "elements": {"existing-slot": {"id": "bpuvww"}},
            },
        },
        "element_definitions": {
            "bTQwO0": {
                "id": "bTQwN0",
                "name": "redirect-rules",
                "elements": {},
                "workflows": {
                    "bPAwH": {
                        "id": "bypGn",
                        "type": "UserLoggedOut",
                        "properties": {"%en": "User is logged out"},
                        "actions": {
                            "0": {"id": "existing-action", "%x": "LogOut", "%p": None}
                        },
                    }
                },
            }
        },
        "_index": {
            "id_to_path": {
                "bTHGI": "%p3.bTHGO",
                "bpnlwp": "%p3.bpfznz",
                "bTQwN0": "%ed.bTQwO0",
                "bypGn": "%ed.bTQwO0.%wf.bPAwH",
            },
            "issues_sub": {
                "bpnlwp": json.dumps(["bpuvww"]),
                "bypGn": json.dumps(["existing-action"]),
            },
            "issues_list": {"bypGn": "[]"},
        },
    }


def _reference_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "reference-app.bubble"
    _write_json(app_path, _reference_app())
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    monkeypatch.setenv("BUBBLE_CLI_DISCOVERY_CACHE", "0")
    return BubbleCLI(app_json_path=str(app_path), appname="cms-portal", app_version="test")


def test_public_reusable_source_is_required_and_dispatches_to_runtime_name() -> None:
    schemas = {tool["name"]: tool["inputSchema"] for tool in list_tool_schemas()}
    reusable_schema = schemas["create_reusable_instance"]

    assert "source" in reusable_schema["required"]
    assert "source" in reusable_schema["properties"]

    kwargs = _method_kwargs(
        BubbleCLI.create_reusable_instance,
        {
            "context": "salon-certification",
            "parent": "root",
            "source": "redirect-rules",
        },
        execute=False,
    )
    assert kwargs["context_name"] == "salon-certification"
    assert kwargs["parent_name"] == "root"
    assert kwargs["reusable_name"] == "redirect-rules"
    assert kwargs["dry_run"] is True


def test_partial_wire_overlay_preserves_canonical_page_metadata_and_typed_resolution(
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "app.bubble"
    overlay_path = tmp_path / "overlay.json"
    _write_json(app_path, _reference_app())
    _write_json(
        overlay_path,
        {
            "entries": [
                {
                    "changes": [
                        {
                            "intent": {"name": "SetData"},
                            "path_array": ["%p3", "bTHGO", "%p", "title"],
                            "body": "Login overlay title",
                        }
                    ]
                }
            ]
        },
    )

    discovery = PathDiscovery(str(app_path), mutation_overlay_path=str(overlay_path))
    resolved = discovery.resolve_page_reference("login")

    assert resolved is not None
    assert resolved.key == "bTHGO"
    assert resolved.object_id == "bTHGI"
    assert resolved.root_id == "bTHGI"
    assert resolved.path_array == ("%p3", "bTHGO")
    assert discovery.data["%p3"]["bTHGO"]["id"] == "bTHGI"
    assert discovery.data["pages"] is discovery.data["%p3"]


def test_unproved_page_reference_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _reference_cli(tmp_path, monkeypatch)

    assert cli._resolve_page_ref_to_object_id("not-in-the-context") is None


def test_structural_page_slot_without_internal_id_is_not_a_navigation_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_path = tmp_path / "slot-only.bubble"
    _write_json(app_path, {"pages": {"bTHGO": {"name": "login"}}})
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    monkeypatch.setenv("BUBBLE_CLI_DISCOVERY_CACHE", "0")
    cli = BubbleCLI(app_json_path=str(app_path), appname="cms-portal", app_version="test")

    resolved = cli.discovery.resolve_page_reference("login")
    assert resolved is not None and resolved.key == "bTHGO" and resolved.root_id is None
    assert cli._resolve_page_ref_to_object_id("login") is None


def test_reusable_resolution_keeps_definition_slot_and_root_id_distinct(
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, _reference_app())

    resolved = PathDiscovery(str(app_path)).resolve_reusable_reference("redirect-rules")

    assert resolved is not None
    assert resolved.key == "bTQwO0"
    assert resolved.object_id == "bTQwN0"
    assert resolved.root_id == "bTQwN0"
    assert resolved.path_array == ("%ed", "bTQwO0")


def test_legacy_parsed_cache_without_contract_version_is_invalidated(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    _write_json(app_path, {"marker": "source"})
    stat = app_path.stat()
    cache_path = Path(f"{app_path}.parsed-cache.pkl")
    with cache_path.open("wb") as handle:
        pickle.dump(
            {
                "__meta__": {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size},
                "data": {"marker": "contaminated-cache"},
            },
            handle,
        )

    discovery = PathDiscovery(str(app_path))

    assert discovery.data["marker"] == "source"


def test_persisted_parsed_cache_excludes_mutation_overlay(tmp_path: Path) -> None:
    app_path = tmp_path / "app.bubble"
    overlay_path = tmp_path / "overlay.json"
    _write_json(app_path, _reference_app())
    _write_json(
        overlay_path,
        {
            "entries": [
                {
                    "changes": [
                        {
                            "intent": {"name": "SetData"},
                            "path_array": ["%p3", "bTHGO", "%p", "overlay_only"],
                            "body": True,
                        }
                    ]
                }
            ]
        },
    )
    discovery = PathDiscovery(str(app_path), mutation_overlay_path=str(overlay_path))
    assert discovery.data["%p3"]["bTHGO"]["%p"]["overlay_only"] is True

    assert discovery.persist_disk_cache() is True
    with Path(f"{app_path}.parsed-cache.pkl").open("rb") as handle:
        cache_payload = pickle.load(handle)

    cached_page = cache_payload["data"]["%p3"]["bTHGO"]
    assert "overlay_only" not in cached_page.get("%p", {})


def test_create_reusable_instance_uses_structural_slots_and_internal_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _reference_cli(tmp_path, monkeypatch)
    generated_ids = iter(("bTQwT1", "bTQwV1"))
    monkeypatch.setattr(
        bubble_cli_module.BubbleIDGenerator,
        "element_id",
        staticmethod(lambda length=5: next(generated_ids)),
    )
    captured: dict[str, Any] = {}

    def capture_finish(_service: Any, payload: Any, **kwargs: Any) -> bool:
        captured["payload"] = payload.build()
        captured["finish"] = kwargs
        return True

    cli._visual_mutations.creations.finish = MethodType(
        capture_finish,
        cli._visual_mutations.creations,
    )

    assert cli.create_reusable_instance(
        "salon-certification",
        "root",
        "redirect-rules",
        name="redirect-rules diagnostic dry-run",
        dry_run=True,
    )

    changes = captured["payload"]["changes"]
    create = next(change for change in changes if change["intent"]["name"] == "CreateElement")
    assert create["path_array"] == ["%p3", "bpfznz", "%el", "bTQwV1"]
    assert create["body"]["id"] == "bTQwT1"
    assert create["body"]["%p"]["%ci"] == "bTQwN0"
    assert "custom_id" not in create["body"]["%p"]

    id_path = next(
        change
        for change in changes
        if change["path_array"] == ["_index", "id_to_path", "bTQwT1"]
    )
    assert id_path["body"] == "%p3.bpfznz.%el.bTQwV1"
    issues_sub = next(
        change
        for change in changes
        if change["path_array"] == ["_index", "issues_sub", "bpnlwp"]
    )
    assert json.loads(issues_sub["body"]) == ["bpuvww", "bTQwT1"]


@pytest.mark.parametrize(
    ("event_ref", "ref_kind"),
    [
        ("bPAwH", "key"),
        ("bypGn", "id"),
        ("User is logged out", "name"),
        ("logout-alias", "auto"),
    ],
)
def test_add_event_go_to_page_emits_canonical_payload_without_dry_run_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    event_ref: str,
    ref_kind: str,
) -> None:
    cli = _reference_cli(tmp_path, monkeypatch)
    cli._cache_workflow_ref_alias("bTQwO0", "reusable", "logout-alias", "bPAwH", "bypGn")
    captured: dict[str, Any] = {}

    def capture_send(_cli: BubbleCLI, payload: Any, dry_run: bool, message: str) -> bool:
        assert dry_run is True
        captured["payload"] = payload.build()
        captured["message"] = message
        return True

    cli._send_schema_payload = MethodType(capture_send, cli)
    discovery_before = copy.deepcopy(cli.discovery.data)

    assert cli.add_event_go_to_page_action(
        "redirect-rules",
        event_ref,
        "login",
        ref_kind=ref_kind,
        action_id="b1DTm",
        dry_run=True,
    )

    assert cli.discovery.data == discovery_before
    changes = captured["payload"]["changes"]
    create = next(change for change in changes if change["intent"]["name"] == "CreateAction")
    assert list(create["body"]) == ["0", "1"]
    assert create["body"]["0"]["id"] == "existing-action"
    assert create["body"]["1"] == {"%x": "ChangePage", "%p": None, "id": "b1DTm"}
    assert any(
        change["path_array"]
        == ["%ed", "bTQwO0", "%wf", "bPAwH", "actions", "1", "%p", "%ei"]
        and change["body"] == "bTHGI"
        for change in changes
    )
    assert not any(
        change["path_array"][-1:] == ["element_id"]
        for change in changes
    )
    assert any(
        change["path_array"] == ["_index", "id_to_path", "b1DTm"]
        and change["body"] == "%ed.bTQwO0.%wf.bPAwH.actions.1"
        for change in changes
    )
    assert any(
        change["path_array"] == ["_index", "issues_sub", "bypGn"]
        and json.loads(change["body"]) == ["existing-action", "b1DTm"]
        for change in changes
    )
    assert any(
        change["path_array"] == ["_index", "issues_list", "bypGn"]
        and json.loads(change["body"]) == [{"cross_page": "b1DTm"}]
        for change in changes
    )


@pytest.mark.parametrize("entrypoint", ["add_event_action", "add_action"])
def test_generic_navigation_entrypoints_resolve_page_id_and_emit_only_wire_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    cli = _reference_cli(tmp_path, monkeypatch)
    captured: list[dict[str, Any]] = []

    def capture_json(builder: Any) -> str:
        captured.append(builder.build())
        return "{}"

    monkeypatch.setattr(bubble_cli_module.PayloadBuilder, "to_json", capture_json)
    discovery_before = copy.deepcopy(cli.discovery.data)

    if entrypoint == "add_event_action":
        ok = cli.add_event_action(
            "redirect-rules",
            "navigate",
            "login",
            event_ref="bypGn",
            ref_kind="id",
            dry_run=True,
        )
    else:
        ok = cli.add_action(
            "redirect-rules",
            action_type="navigate",
            action_param="login",
            event_ref="bypGn",
            ref_kind="id",
            dry_run=True,
        )

    assert ok is True
    assert cli.discovery.data == discovery_before
    changes = [change for payload in captured for change in payload["changes"]]
    property_writes = [
        change
        for change in changes
        if change.get("path_array", [])[-2:] == ["%p", "%ei"]
    ]
    assert property_writes
    assert {change["body"] for change in property_writes} == {"bTHGI"}
    assert not any(
        change.get("path_array", [])[-2:] == ["%p", "element_id"]
        for change in changes
    )
