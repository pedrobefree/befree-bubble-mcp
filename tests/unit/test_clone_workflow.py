"""Duplicating a live workflow: read the source, remint its ids, write, prove it landed.

No browser and no Bubble. The fake editor below is keyed by dotted pointer so a test can tell
whether verification read the source back or the copy - reading the source back would pass
while the copy was never written, which is the failure this cycle exists to prevent.
"""

from __future__ import annotations

import copy
from typing import Any

from bubble_mcp.execution.node_edit import clone_live_workflow


def _source_workflow() -> dict[str, Any]:
    """Case D from docs/capture-duplicate-workflow.md, before the editor duplicated it."""

    return {
        "%x": "APIEvent",
        "%p": {
            "expose": False,
            "wf_name": "test custom",
            "parameters": {"0": {"%k": "Parameter 1", "%v": "custom.test", "param_id": "bTGOc"}},
        },
        "id": "bTGOQ",
        "actions": {
            "0": {
                "%x": "TriggerCustomEvent",
                "%p": {
                    "custom_event": "bTGNt",
                    "arguments": {
                        "0": {
                            "param_id": "bTGOA",
                            "arg_value": {
                                "%x": "APIEventParameter",
                                "%p": {
                                    "event_id": "bTGOQ",
                                    "param_id": "Parameter 1",
                                    "param_name": "Parameter 1",
                                },
                                "%n": None,
                                "is_slidable": False,
                            },
                        }
                    },
                },
                "id": "bTGOX",
            }
        },
    }


class _Editor:
    """A fake editor holding nodes by dotted pointer."""

    def __init__(self, nodes: dict[str, dict[str, Any]]) -> None:
        self.nodes = nodes
        self.read_pointers: list[list[str]] = []

    def read(self, profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        segments = [str(part) for part in pointer]
        self.read_pointers.append(segments)
        key = ".".join(segments)
        if key not in self.nodes:
            return {"ok": False, "error": "node_not_found", "pointer": segments}
        return {
            "ok": True,
            "pointer": segments,
            "node": copy.deepcopy(self.nodes[key]),
            "app_id": "mcp-test-app",
        }

    def write(self, payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        if not dry_run:
            for change in payload["changes"]:
                if change.get("intent", {}).get("name") != "CreateEvent":
                    continue
                key = ".".join(str(part) for part in change["path_array"])
                self.nodes[key] = copy.deepcopy(change["body"])
        return {"ok": True, "dry_run": dry_run, "request": {"payload": payload}}


def _minter(*ids: str):  # type: ignore[no-untyped-def]
    minted = iter(ids)
    return lambda: next(minted)


def test_clone_previews_without_writing_when_execute_is_false() -> None:
    editor = _Editor({"api.bTGOS": _source_workflow()})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=False,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert result["ok"] is True
    assert result["execute"] is False
    assert "verified" not in result
    assert "api.bTGOj" not in editor.nodes


def test_clone_remints_the_event_and_action_ids_and_the_self_reference() -> None:
    editor = _Editor({"api.bTGOS": _source_workflow()})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=False,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    intended = result["intended"]
    assert intended["id"] == "bTGOd"
    assert intended["actions"]["0"]["id"] == "bTGOi"
    argument = intended["actions"]["0"]["%p"]["arguments"]["0"]
    assert argument["arg_value"]["%p"]["event_id"] == "bTGOd"
    assert argument["param_id"] == "bTGOA"


def test_clone_writes_the_copy_to_a_new_slot_beside_the_source() -> None:
    editor = _Editor({"api.bTGOS": _source_workflow()})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=True,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert result["new_pointer"] == ["api", "bTGOj"]
    assert editor.nodes["api.bTGOj"]["id"] == "bTGOd"
    assert editor.nodes["api.bTGOS"]["id"] == "bTGOQ"


def test_clone_verifies_by_reading_the_copy_not_the_source() -> None:
    editor = _Editor({"api.bTGOS": _source_workflow()})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=True,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert result["verified"] is True
    assert result["divergence"] is None
    assert editor.read_pointers[-1] == ["api", "bTGOj"]


def test_clone_reports_the_divergence_when_the_editor_kept_something_else() -> None:
    editor = _Editor({"api.bTGOS": _source_workflow()})
    honest_write = editor.write

    def lossy_write(payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        result = honest_write(payload, session, dry_run=dry_run)
        if not dry_run:
            editor.nodes["api.bTGOj"]["%p"]["parameters"]["0"].pop("param_id", None)
        return result

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=True,
        reader=editor.read,
        writer=lossy_write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert result["verified"] is False
    assert result["divergence"] == "%p.parameters.0.param_id"


def test_clone_renames_a_backend_workflow_so_the_copy_does_not_collide() -> None:
    editor = _Editor({"api.bTGOS": _source_workflow()})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        wf_name="test custom_copy",
        execute=False,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert result["intended"]["%p"]["wf_name"] == "test custom_copy"


def test_clone_returns_the_failed_source_read_untouched() -> None:
    editor = _Editor({})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "missing"],
        execute=True,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd"),
    )

    assert result["ok"] is False
    assert result["error"] == "node_not_found"


def test_clone_refuses_a_pointer_that_does_not_address_a_workflow() -> None:
    editor = _Editor({"api.bTGOS.actions": {"0": {"%x": "ShowElement", "id": "bTGOX"}}})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS", "actions"],
        execute=True,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd"),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_clone"


def test_clone_reports_an_id_it_found_outside_a_known_id_field() -> None:
    """A self-reference in an unknown field must surface, not be silently left behind."""

    source = _source_workflow()
    source["%p"]["wf_name"] = "bTGOQ"
    editor = _Editor({"api.bTGOS": source})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=False,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert any("wf_name" in path for path in result["unmapped_ids"])


def test_clone_remints_an_id_the_app_already_uses() -> None:
    """element_id() is random over 62^4; a collision would overwrite an existing object."""

    editor = _Editor(
        {
            "api.bTGOS": _source_workflow(),
            "_index.id_to_path": {"bTAKEN": "api.bOther", "bTGOj": "api.bAlso"},
        }
    )

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=False,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTAKEN", "bFREE1", "bFREE2", "bFREE3"),
    )

    minted = {*result["id_mapping"].values(), result["new_pointer"][-1]}
    assert not minted & {"bTGOj", "bTAKEN"}


def test_clone_still_works_when_the_index_cannot_be_read() -> None:
    """Losing the collision check must not stop the clone; it must be reported instead."""

    editor = _Editor({"api.bTGOS": _source_workflow()})

    result = clone_live_workflow(
        profile="mcp-test",
        pointer=["api", "bTGOS"],
        execute=False,
        reader=editor.read,
        writer=editor.write,
        mint_id=_minter("bTGOj", "bTGOd", "bTGOi"),
    )

    assert result["ok"] is True
    assert result["id_collision_checked"] is False
