"""verify_changes: generic post-write verification, with a fake reader and no browser."""

from __future__ import annotations

from typing import Any

from bubble_mcp.execution import write_verify as write_verify_module
from bubble_mcp.execution.write_verify import verify_changes
from bubble_mcp.server.tools import _attach_write_verification


def _set_data(path_array: list[str], body: Any) -> dict[str, Any]:
    return {
        "intent": {"name": "SetData", "id": 7, "source_appname": ""},
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": "sess-1",
    }


def _create_action(path_array: list[str], body: Any) -> dict[str, Any]:
    return {
        "intent": {"name": "CreateAction"},
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": "sess-1",
    }


def _delete(path_array: list[str]) -> dict[str, Any]:
    return {
        "intent": {"name": "Delete"},
        "path_array": path_array,
        "body": None,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": "sess-1",
    }


def _update_index(path_array: list[str], body: Any) -> dict[str, Any]:
    return {
        "intent": {"name": "Update index"},
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": "sess-1",
    }


class FakeReader:
    """A reader with the read_live_nodes signature, backed by a fixed pointer -> result map.

    Records every call so tests can assert pointers are read exactly once each.
    """

    def __init__(self, table: dict[tuple[str, ...], dict[str, Any]]) -> None:
        self.table = table
        self.calls: list[list[tuple[str, ...]]] = []

    def __call__(
        self,
        profile: str,
        pointers: list[tuple[str, ...]],
        *,
        app_id: str | None = None,
        app_version: str = "test",
    ) -> dict[tuple[str, ...], dict[str, Any]]:
        self.calls.append(list(pointers))
        return {pointer: self.table[pointer] for pointer in pointers}


def _ok(node: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "pointer": [], "node": node, "app_id": "mcp-test-app"}


def _not_found(pointer: tuple[str, ...]) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "pointer_not_found",
        "pointer": list(pointer),
        "message": "gone",
    }


def _read_error(pointer: tuple[str, ...], error: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": error, "pointer": list(pointer), "message": message}


def test_matching_node_change_verifies() -> None:
    pointer = ("api", "wf-1", "actions", "0")
    node = {"id": "act-1", "%x": "ChangeThing", "%p": {"a": "1"}}
    reader = FakeReader({pointer: _ok(node)})

    changes = [_create_action(list(pointer), node)]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["ok"] is True
    assert result["checked"] == 1
    assert result["verified"] is True
    assert result["divergences"] == []
    assert result["unverified"] == []
    assert result["render_unverified"] is True
    assert "verified_meaning" in result


def test_diverging_change_reports_the_exact_dotted_divergence_path() -> None:
    pointer = ("api", "wf-1", "actions", "0")
    written = {"id": "act-1", "%x": "ChangeThing", "%p": {"%ei": "bS35G"}}
    read_back = {"id": "act-1", "%x": "ChangeThing", "%p": {"%ei": "in_email"}}
    reader = FakeReader({pointer: _ok(read_back)})

    changes = [_create_action(list(pointer), written)]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["ok"] is True
    assert result["verified"] is False
    assert len(result["divergences"]) == 1
    divergence = result["divergences"][0]
    assert divergence["path"] == "api.wf-1.actions.0"
    assert divergence["divergence"] == "%p.%ei"
    assert divergence["expected"] == written
    assert divergence["actual"] == read_back


def test_index_changes_are_skipped_and_not_counted() -> None:
    leaf_path = ["api", "wf-1", "actions", "0", "%p", "%ei"]
    parent_pointer = ("api", "wf-1", "actions", "0", "%p")
    reader = FakeReader({parent_pointer: _ok({"%ei": "bS35G"})})

    changes = [
        _set_data(leaf_path, "bS35G"),
        _update_index(["_index", "id_to_path", "act-1"], "api.wf-1.actions.0"),
        _update_index(["_index", "issues_list", "wf-1"], {"anything": True}),
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1  # only the SetData counted; both _index changes skipped
    assert result["verified"] is True


def test_null_body_setdata_is_verified_against_a_matching_null_reread() -> None:
    """A None body on a non-delete intent (SetData writing a deliberate null - a real producer

    is scheduled_deploy.py:419) must remain comparable rather than skipped: classification as a
    delete depends on the intent name alone, never on the body being None. Here the re-read
    confirms the null landed, so the write verifies clean.
    """

    parent_pointer = ("api", "wf-1", "actions", "0", "%p")
    reader = FakeReader({parent_pointer: _ok({"%ei": None})})

    changes = [_set_data([*parent_pointer, "%ei"], None)]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1
    assert reader.calls == [[parent_pointer]]
    assert result["verified"] is True
    assert result["divergences"] == []


def test_null_setdata_body_catches_a_write_bubble_ignored() -> None:
    """Before the fix, `_plan_change` returned None for any non-delete change whose body was

    None, so a deliberate null write was invisible: nothing was read and the write was reported
    verified even if Bubble ignored it entirely. Here the re-read shows the old value is still
    there, so this must now be reported as a divergence, not silently verified.
    """

    parent_pointer = ("settings",)
    reader = FakeReader({parent_pointer: _ok({"some_property": "still-here"})})

    changes = [_set_data(["settings", "some_property"], None)]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1
    assert reader.calls == [[parent_pointer]]
    assert result["verified"] is False
    assert len(result["divergences"]) == 1
    assert result["divergences"][0]["expected"] is None
    assert result["divergences"][0]["actual"] == "still-here"


def test_delete_whose_path_still_reads_back_is_a_divergence() -> None:
    pointer = ("api", "wf-1", "actions", "0")
    reader = FakeReader({pointer: _ok({"id": "act-1", "%x": "ChangeThing"})})

    changes = [_delete(list(pointer))]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1
    assert result["verified"] is False
    assert len(result["divergences"]) == 1
    assert result["divergences"][0]["path"] == "api.wf-1.actions.0"
    assert result["divergences"][0]["expected"] == "absent"
    assert result["unverified"] == []


def test_delete_whose_path_reads_pointer_not_found_passes() -> None:
    pointer = ("api", "wf-1", "actions", "0")
    reader = FakeReader({pointer: _not_found(pointer)})

    changes = [_delete(list(pointer))]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1
    assert result["verified"] is True
    assert result["divergences"] == []
    assert result["unverified"] == []


def test_a_read_error_lands_in_unverified_not_divergences_and_ok_stays_true() -> None:
    pointer = ("api", "wf-1", "actions", "0")
    reader = FakeReader({pointer: _read_error(pointer, "editor_unstable", "kept reinitializing")})

    changes = [_create_action(list(pointer), {"id": "act-1", "%x": "ChangeThing"})]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["ok"] is True
    assert result["divergences"] == []
    assert len(result["unverified"]) == 1
    assert result["unverified"][0]["path"] == "api.wf-1.actions.0"
    assert result["unverified"][0]["error"] == "editor_unstable"
    assert result["unverified"][0]["message"] == "kept reinitializing"
    assert result["verified"] is False  # we don't know, so it cannot be claimed verified


def test_a_delete_whose_read_fails_for_an_unrelated_reason_lands_in_unverified() -> None:
    pointer = ("api", "wf-1", "actions", "0")
    reader = FakeReader({pointer: _read_error(pointer, "not_logged_in", "no session")})

    changes = [_delete(list(pointer))]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["divergences"] == []
    assert len(result["unverified"]) == 1
    assert result["unverified"][0]["error"] == "not_logged_in"


def test_duplicate_pointers_are_read_once() -> None:
    pointer = ("api", "wf-1", "actions", "0", "%p")
    node = {"%ei": "bS35G", "other": "x"}
    reader = FakeReader({pointer: _ok(node)})

    changes = [
        _set_data([*pointer, "%ei"], "bS35G"),
        _set_data([*pointer, "other"], "x"),
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 2
    assert result["verified"] is True
    assert reader.calls == [[pointer]]  # one read call, one distinct pointer


def test_leaf_setdata_compares_against_the_parent_nodes_value_at_the_final_key() -> None:
    """A SetData body is a bare scalar addressing a leaf under a parent node. The parent - not

    the leaf - is what gets read (see write_verify's docstring on why), so the comparison must
    reach through to the parent's value at the final path segment.
    """

    parent_pointer = ("api", "wf-1", "actions", "0", "%p")
    node = {"%ei": "bS35G"}
    reader = FakeReader({parent_pointer: _ok(node)})

    changes = [_set_data([*parent_pointer, "%ei"], "bS35G")]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["verified"] is True
    assert reader.calls == [[parent_pointer]]


def test_leaf_setdata_diverging_from_the_parents_value_is_reported() -> None:
    parent_pointer = ("api", "wf-1", "actions", "0", "%p")
    node = {"%ei": "in_email"}
    reader = FakeReader({parent_pointer: _ok(node)})

    changes = [_set_data([*parent_pointer, "%ei"], "bS35G")]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["verified"] is False
    assert len(result["divergences"]) == 1
    divergence = result["divergences"][0]
    assert divergence["expected"] == "bS35G"
    assert divergence["actual"] == "in_email"


def test_render_unverified_is_always_present() -> None:
    reader = FakeReader({})
    result = verify_changes("mcp-test", [], app_id="mcp-test-app", reader=reader)

    assert result["render_unverified"] is True
    assert result["checked"] == 0
    assert result["verified"] is True  # nothing to check, vacuously true


# --- C1: cumulative-effect verification for two-step (CreateAction + SetData) writes ---------


def test_two_step_create_action_then_set_data_verifies_clean_against_cumulative_state() -> None:
    """Mirrors bubble_cli._build_full_create_action_map: a CreateAction writes the whole actions
    map with the new action's "%p": None, and a same-payload SetData fills one property. Read
    back, the FINAL tree has "%p" populated - comparing the CreateAction change against its own
    stale ("%p": None) body would manufacture a divergence on every such write; this must not.
    """

    wf_path = ["%p3", "bVVl3", "%wf", "wf1", "actions"]
    node_pointer = tuple(wf_path)
    leaf_parent_pointer = (*node_pointer, "0", "%p")

    create_action_body = {"0": {"%x": "ShowElement", "%p": None, "id": "act1"}}
    final_action_node = {"0": {"%x": "ShowElement", "%p": {"%ei": "bTGyp0"}, "id": "act1"}}

    reader = FakeReader(
        {
            node_pointer: _ok(final_action_node),
            leaf_parent_pointer: _ok({"%ei": "bTGyp0"}),
        }
    )

    changes = [
        _create_action(wf_path, create_action_body),
        _set_data([*leaf_parent_pointer, "%ei"], "bTGyp0"),
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 2
    assert result["divergences"] == []
    assert result["unverified"] == []
    assert result["verified"] is True


def test_a_later_write_at_the_same_pointer_wins_over_an_earlier_one() -> None:
    pointer = ("api", "wf-1", "actions")
    first_body = {"0": {"id": "act-1", "%x": "First"}}
    second_body = {"0": {"id": "act-1", "%x": "Second"}}
    reader = FakeReader({pointer: _ok(second_body)})

    changes = [
        _create_action(list(pointer), first_body),
        _create_action(list(pointer), second_body),
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["verified"] is True
    assert result["divergences"] == []


# --- D1: a delete superseded by a later write in the same payload is not a false divergence ---


def test_a_delete_superseded_by_a_later_write_in_the_same_payload_is_not_a_divergence() -> None:
    """The replay already builds the right final state ({"child": {"value": 2}}), but the old

    delete branch ignored it and unconditionally demanded absence. Whichever operation governs
    a pointer at the END of the replay is what gets verified: here that is the SetData, not the
    RemoveElement it superseded.
    """

    create_pointer = ("root", "node")
    child_pointer = ("root", "node", "child")
    final_child_state = {"value": 2}
    reader = FakeReader(
        {
            create_pointer: _ok({"child": final_child_state}),
            child_pointer: _ok(final_child_state),
        }
    )

    changes = [
        _create_action(list(create_pointer), {"child": {"old": 1}}),
        {
            "intent": {"name": "RemoveElement"},
            "path_array": list(child_pointer),
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": "sess-1",
        },
        _set_data([*child_pointer, "value"], 2),
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 3
    assert result["divergences"] == []
    assert result["unverified"] == []
    assert result["verified"] is True


# --- I2: a missing node under a node-kind plan is a divergence, not "could not check" ---------


def test_pointer_not_found_for_a_node_kind_plan_is_a_divergence() -> None:
    pointer = ("%p3", "bG4Jl")
    reader = FakeReader({pointer: _not_found(pointer)})

    changes = [_create_action(list(pointer), {"id": "bG4Jl", "%x": "PageElement"})]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["unverified"] == []
    assert len(result["divergences"]) == 1
    assert result["divergences"][0]["expected"] == "present"
    assert result["divergences"][0]["actual"] == "absent"
    assert result["verified"] is False


def test_pointer_not_found_for_a_leaf_kind_plan_is_a_divergence() -> None:
    """Measured against the live editor: %p and its children ARE addressable through appquery's

    `_child()` walk (%p3.AAW.%wf.bTHDJ.actions.0.%p.new_password -> ok, dict), so
    pointer_not_found on a leaf's parent proves genuine absence, not "cannot address" - it must
    be a divergence, the same as it already is for a node-kind plan.
    """

    parent_pointer = ("api", "wf-1", "actions", "0", "%p")
    reader = FakeReader({parent_pointer: _not_found(parent_pointer)})

    changes = [_set_data([*parent_pointer, "%ei"], "bS35G")]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["unverified"] == []
    assert len(result["divergences"]) == 1
    assert result["divergences"][0]["expected"] == "bS35G"
    assert result["divergences"][0]["actual"] == "absent"
    assert result["verified"] is False


# --- I1: a redacted body is reported unverified, never a divergence against "[REDACTED]" ------


def test_redacted_body_is_unverified_with_reason_redacted_and_never_read() -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a redacted change has no pointer to read; the reader must not run")

    changes = [_create_action(["settings", "api_tokens", "0"], "[REDACTED]")]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=_boom)

    assert result["checked"] == 1
    assert result["divergences"] == []
    assert len(result["unverified"]) == 1
    assert result["unverified"][0]["error"] == "redacted"
    assert result["verified"] is False


# --- I3: a RemoveElement/DeleteStyle-shaped intent is treated as a delete ----------------------


def test_remove_prefixed_intent_is_treated_as_a_delete_and_counted() -> None:
    pointer = ("%p3", "bVVl3", "%e", "bXXyy")
    reader = FakeReader({pointer: _not_found(pointer)})

    changes = [
        {
            "intent": {"name": "RemoveElement"},
            "path_array": list(pointer),
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": "sess-1",
        }
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1
    assert result["verified"] is True
    assert result["divergences"] == []


def test_delete_style_intent_is_treated_as_a_delete() -> None:
    pointer = ("styles", "st-1")
    reader = FakeReader({pointer: _ok({"id": "st-1"})})

    changes = [
        {
            "intent": {"name": "DeleteStyle"},
            "path_array": list(pointer),
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": "sess-1",
        }
    ]
    result = verify_changes("mcp-test", changes, app_id="mcp-test-app", reader=reader)

    assert result["checked"] == 1
    assert result["verified"] is False
    assert result["divergences"][0]["expected"] == "absent"


# --- I7: the server/tools.py wiring seam ------------------------------------------------------


def _write_item(changes: list[dict[str, Any]], *, ok: bool = True, executed: bool = True) -> dict[str, Any]:
    return {
        "index": 1,
        "executed": executed,
        "ok": ok,
        "result": {"request": {"payload": {"changes": changes}}},
    }


def test_dry_run_result_attaches_no_verification(monkeypatch: Any) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a dry-run result must never trigger a read-back")

    monkeypatch.setattr(write_verify_module, "read_live_nodes", _boom)

    runtime_result = {
        "executed": False,
        "app_id": "mcp-test-app",
        "app_version": "test",
        "results": [_write_item([_create_action(["api", "wf-1", "actions"], {"0": {"id": "a"}})])],
    }
    out = _attach_write_verification(runtime_result, profile="mcp-test", args={})

    assert "write_verification" not in out
    assert "verification" not in out


def test_verify_false_attaches_no_verification(monkeypatch: Any) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("verify=false must never trigger a read-back")

    monkeypatch.setattr(write_verify_module, "read_live_nodes", _boom)

    runtime_result = {
        "executed": True,
        "app_id": "mcp-test-app",
        "app_version": "test",
        "results": [_write_item([_create_action(["api", "wf-1", "actions"], {"0": {"id": "a"}})])],
    }
    out = _attach_write_verification(runtime_result, profile="mcp-test", args={"verify": False})

    assert "write_verification" not in out
    assert "verification" not in out


def test_executed_result_attaches_write_verification_and_preserves_existing_verification_key(
    monkeypatch: Any,
) -> None:
    pointer = ("api", "wf-1", "actions")
    node = {"0": {"id": "a", "%x": "ChangeThing"}}
    reader = FakeReader({pointer: _ok(node)})
    monkeypatch.setattr(write_verify_module, "read_live_nodes", reader)

    tool_specific_verification = {
        "status": "verified",
        "data_type_key": "custom.thing",
        "absent_from_fresh_export": True,
        "source": "fresh-export.json",
    }
    runtime_result = {
        "executed": True,
        "app_id": "mcp-test-app",
        "app_version": "test",
        "verification": tool_specific_verification,
        "results": [_write_item([_create_action(list(pointer), node)])],
    }
    out = _attach_write_verification(runtime_result, profile="mcp-test", args={})

    assert out["verification"] == tool_specific_verification  # untouched
    assert out["write_verification"]["verified"] is True
    assert out["write_verification"]["checked"] == 1


def test_seam_two_step_create_action_then_set_data_verifies_clean(monkeypatch: Any) -> None:
    wf_path = ["%p3", "bVVl3", "%wf", "wf1", "actions"]
    node_pointer = tuple(wf_path)
    leaf_parent_pointer = (*node_pointer, "0", "%p")
    create_action_body = {"0": {"%x": "ShowElement", "%p": None, "id": "act1"}}
    final_action_node = {"0": {"%x": "ShowElement", "%p": {"%ei": "bTGyp0"}, "id": "act1"}}

    reader = FakeReader(
        {
            node_pointer: _ok(final_action_node),
            leaf_parent_pointer: _ok({"%ei": "bTGyp0"}),
        }
    )
    monkeypatch.setattr(write_verify_module, "read_live_nodes", reader)

    changes = [
        _create_action(wf_path, create_action_body),
        _set_data([*leaf_parent_pointer, "%ei"], "bTGyp0"),
    ]
    runtime_result = {
        "executed": True,
        "app_id": "mcp-test-app",
        "app_version": "test",
        "results": [_write_item(changes)],
    }
    out = _attach_write_verification(runtime_result, profile="mcp-test", args={})

    assert out["write_verification"]["verified"] is True
    assert out["write_verification"]["divergences"] == []


def test_seam_redacted_change_lands_in_unverified_with_reason_redacted(monkeypatch: Any) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a redacted change has no pointer to read; the reader must not run")

    monkeypatch.setattr(write_verify_module, "read_live_nodes", _boom)

    changes = [_create_action(["settings", "api_tokens", "0"], "[REDACTED]")]
    runtime_result = {
        "executed": True,
        "app_id": "mcp-test-app",
        "app_version": "test",
        "results": [_write_item(changes)],
    }
    out = _attach_write_verification(runtime_result, profile="mcp-test", args={})

    assert out["write_verification"]["verified"] is False
    assert out["write_verification"]["unverified"][0]["error"] == "redacted"
    assert out["write_verification"]["divergences"] == []


def test_seam_remove_element_change_is_counted_and_its_absence_verified(monkeypatch: Any) -> None:
    pointer = ("%p3", "bVVl3", "%e", "bXXyy")
    reader = FakeReader({pointer: _not_found(pointer)})
    monkeypatch.setattr(write_verify_module, "read_live_nodes", reader)

    changes = [
        {
            "intent": {"name": "RemoveElement"},
            "path_array": list(pointer),
            "body": None,
            "version_control_api_version": 4,
            "changelog_data": [],
            "session_id": "sess-1",
        }
    ]
    runtime_result = {
        "executed": True,
        "app_id": "mcp-test-app",
        "app_version": "test",
        "results": [_write_item(changes)],
    }
    out = _attach_write_verification(runtime_result, profile="mcp-test", args={})

    assert out["write_verification"]["checked"] == 1
    assert out["write_verification"]["verified"] is True
