"""Duplicating live elements with their workflows: remint ids, keep the index whole, verify.

No browser and no Bubble. The fake editor holds the whole app tree, including ``_index``, reads
any pointer out of it the way ``read_live_nodes`` does, and applies an executed write back into
the tree, so verification reads what the write actually left behind.
"""

from __future__ import annotations

import copy
import itertools
import json
from typing import Any

from bubble_mcp.execution.duplicate_element import duplicate_live_element


def _app() -> dict[str, Any]:
    """A page with a button that opens a popup, whose OK button hides it.

    bBtn opens bPop (workflow bE1). Inside the popup, bOk reads bIn and hides bPop (bE2).
    bOther opens the same popup (bE3): it references the popup but is not triggered by it.
    """

    return {
        "_index": {
            "id_to_path": {
                "bPage": "%p3.pg1",
                "bBtn": "%p3.pg1.%el.s1",
                "bPop": "%p3.pg1.%el.s2",
                "bIn": "%p3.pg1.%el.s2.%el.s3",
                "bOk": "%p3.pg1.%el.s2.%el.s4",
                "bOther": "%p3.pg1.%el.s5",
                "bGrp": "%p3.pg1.%el.s6",
                "bE1": "%p3.pg1.%wf.w1",
                "bA1": "%p3.pg1.%wf.w1.actions.0",
                "bE2": "%p3.pg1.%wf.w2",
                "bA2": "%p3.pg1.%wf.w2.actions.0",
                "bA3": "%p3.pg1.%wf.w2.actions.1",
                "bE3": "%p3.pg1.%wf.w3",
                "bA4": "%p3.pg1.%wf.w3.actions.0",
                "bRp": "%ed.bRp",
            },
            "issues_sub": {
                "bPage": json.dumps(["bBtn", "bPop", "bOther", "bGrp", "bE1", "bE2", "bE3"]),
                "bPop": json.dumps(["bIn", "bOk"]),
            },
        },
        "%p3": {
            "pg1": {
                "id": "bPage",
                "%x": "Page",
                "%nm": "index",
                "%el": {
                    "s1": {"id": "bBtn", "%x": "Button", "%nm": "Open", "%p": {"%3": "Open"}},
                    "s2": {
                        "id": "bPop",
                        "%x": "Popup",
                        "%nm": "Confirm popup",
                        "%p": {"%h": 200},
                        "%el": {
                            "s3": {"id": "bIn", "%x": "Input", "%nm": "Reason", "%p": {}},
                            # Text typed by a user that happens to equal an id must survive.
                            "s4": {"id": "bOk", "%x": "Button", "%nm": "OK", "%p": {"%3": "bPop"}},
                        },
                    },
                    "s5": {"id": "bOther", "%x": "Button", "%nm": "Other", "%p": {}},
                    "s6": {"id": "bGrp", "%x": "Group", "%nm": "Holder", "%p": {}},
                },
                "%wf": {
                    "w1": {
                        "id": "bE1",
                        "%x": "ButtonClicked",
                        "%p": {"%ei": "bBtn"},
                        "actions": {"0": {"id": "bA1", "%x": "ShowElement", "%p": {"%ei": "bPop"}}},
                    },
                    "w2": {
                        "id": "bE2",
                        "%x": "ButtonClicked",
                        "%p": {"%ei": "bOk"},
                        "actions": {
                            "0": {
                                "id": "bA2",
                                "%x": "ChangeThing",
                                "%p": {
                                    "%v": {
                                        "%x": "GetElement",
                                        "%p": {"%ei": "bIn"},
                                        "%n": {"%x": "Message", "%nm": "value"},
                                    }
                                },
                            },
                            "1": {"id": "bA3", "%x": "HideElement", "%p": {"%ei": "bPop"}},
                        },
                    },
                    "w3": {
                        "id": "bE3",
                        "%x": "ButtonClicked",
                        "%p": {"%ei": "bOther"},
                        "actions": {"0": {"id": "bA4", "%x": "ShowElement", "%p": {"%ei": "bPop"}}},
                    },
                },
            }
        },
        "%ed": {"bRp": {"id": "bRp", "%x": "CustomDefinition", "%el": {}}},
    }


class _Editor:
    """A fake editor holding the whole app tree; reads walk it, writes land in it."""

    def __init__(self, tree: dict[str, Any]) -> None:
        self.tree = tree
        self.reads: list[list[tuple[str, ...]]] = []
        self.writes: list[tuple[dict[str, Any], bool]] = []

    def _get(self, pointer: tuple[str, ...]) -> tuple[bool, Any]:
        node: Any = self.tree
        for part in pointer:
            if not isinstance(node, dict) or part not in node:
                return False, None
            node = node[part]
        return True, node

    def read(self, profile, pointers, **kwargs):  # type: ignore[no-untyped-def]
        keys = [tuple(str(part) for part in pointer) for pointer in pointers]
        self.reads.append(keys)
        results = {}
        for key in keys:
            found, node = self._get(key)
            if not found:
                results[key] = {"ok": False, "error": "pointer_not_found", "pointer": list(key)}
            else:
                results[key] = {
                    "ok": True,
                    "pointer": list(key),
                    "node": copy.deepcopy(node),
                    "app_id": "mcp-test-app",
                }
        return results

    def write(self, payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        self.writes.append((copy.deepcopy(payload), dry_run))
        if not dry_run:
            for change in payload["changes"]:
                path = change.get("path_array")
                if not path:
                    continue
                node = self.tree
                for part in path[:-1]:
                    node = node.setdefault(part, {})
                node[path[-1]] = copy.deepcopy(change["body"])
        return {"ok": True, "status": 200, "dry_run": dry_run}


def _minter(prefix: str = "bN"):  # type: ignore[no-untyped-def]
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter):03d}"


def _run(editor: _Editor, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "profile": "mcp-test",
        "element_ids": ["bBtn", "bPop"],
        "app_version": "93k8b",
        "reader": editor.read,
        "writer": editor.write,
        "mint_id": _minter(),
    }
    arguments.update(overrides)
    return duplicate_live_element(**arguments)


def _change_at(result: dict[str, Any], *path: str) -> dict[str, Any]:
    changes = result["write_payload"]["changes"]
    return next(change for change in changes if change.get("path_array") == list(path))


def test_preview_is_the_default_and_sends_nothing() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    assert result["ok"] is True
    assert result["execute"] is False
    assert [dry_run for _, dry_run in editor.writes] == [True]
    assert "verified" not in result


def test_every_element_in_the_subtree_gets_a_new_id_and_a_new_slot() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    mapping = result["id_mapping"]
    assert set(result["new_ids"]["elements"]) == {mapping[old] for old in ("bBtn", "bPop", "bIn", "bOk")}
    roots = {root["source_id"]: root for root in result["roots"]}
    popup = _change_at(result, *roots["bPop"]["new_pointer"])
    assert popup["intent"]["name"] == "CreateElement"
    assert popup["body"]["id"] == mapping["bPop"]
    children = popup["body"]["%el"]
    assert {child["id"] for child in children.values()} == {mapping["bIn"], mapping["bOk"]}
    # The slot key is not the element id; neither may reuse the source's.
    assert not set(children) & {"s3", "s4", mapping["bIn"], mapping["bOk"]}


def test_new_ids_never_collide_with_an_id_the_index_already_holds() -> None:
    editor = _Editor(_app())
    drawn = iter(["bBtn", "s1", "bE1", *[f"bN{n:03d}" for n in range(1, 100)]])

    result = _run(editor, mint_id=lambda: next(drawn))

    minted = set(result["id_mapping"].values())
    assert not minted & {"bBtn", "s1", "bE1"}


def test_workflows_triggered_by_the_copied_elements_are_copied_and_repointed() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    mapping = result["id_mapping"]
    copies = {entry["source_id"]: entry for entry in result["copied_workflows"]}
    assert set(copies) == {"bE1", "bE2"}

    opener = _change_at(result, *copies["bE1"]["new_pointer"])
    assert opener["intent"]["name"] == "CreateEvent"
    assert opener["body"]["id"] == mapping["bE1"]
    assert opener["body"]["%p"]["%ei"] == mapping["bBtn"]
    assert opener["body"]["actions"]["0"]["id"] == mapping["bA1"]
    assert opener["body"]["actions"]["0"]["%p"]["%ei"] == mapping["bPop"]

    confirm = _change_at(result, *copies["bE2"]["new_pointer"])
    assert confirm["body"]["%p"]["%ei"] == mapping["bOk"]
    assert confirm["body"]["actions"]["0"]["%p"]["%v"]["%p"]["%ei"] == mapping["bIn"]
    assert confirm["body"]["actions"]["1"]["%p"]["%ei"] == mapping["bPop"]


def test_a_workflow_outside_the_copy_that_references_it_is_reported_not_copied() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    referencing = result["referencing_workflows_not_copied"]
    assert [entry["id"] for entry in referencing] == ["bE3"]
    assert referencing[0]["references"] == ["bPop"]
    assert referencing[0]["pointer"] == ["%p3", "pg1", "%wf", "w3"]


def test_include_workflows_false_copies_no_workflow_and_reports_them_all() -> None:
    editor = _Editor(_app())

    result = _run(editor, include_workflows=False)

    assert result["copied_workflows"] == []
    assert not any(
        change.get("intent", {}).get("name") == "CreateEvent"
        for change in result["write_payload"]["changes"]
    )
    assert [entry["id"] for entry in result["referencing_workflows_not_copied"]] == ["bE1", "bE2", "bE3"]


def test_the_index_gets_an_entry_for_every_new_id() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    mapping = result["id_mapping"]
    id_to_path = {
        entry["path"].split(".", 2)[2]: entry["value"]
        for entry in result["index_entries"]
        if entry["path"].startswith("_index.id_to_path.")
    }
    assert set(id_to_path) == set(mapping.values())
    roots = {root["source_id"]: root for root in result["roots"]}
    assert id_to_path[mapping["bPop"]] == ".".join(roots["bPop"]["new_pointer"])
    popup_children = _change_at(result, *roots["bPop"]["new_pointer"])["body"]["%el"]
    ok_slot = next(slot for slot, child in popup_children.items() if child["id"] == mapping["bOk"])
    assert id_to_path[mapping["bOk"]] == f"{id_to_path[mapping['bPop']]}.%el.{ok_slot}"
    wf = {entry["source_id"]: entry for entry in result["copied_workflows"]}["bE2"]
    assert id_to_path[mapping["bA3"]] == ".".join([*wf["new_pointer"], "actions", "1"])

    issues_list = {
        entry["path"].split(".", 2)[2]: entry["value"]
        for entry in result["index_entries"]
        if entry["path"].startswith("_index.issues_list.")
    }
    assert issues_list == {mapping[old]: "[]" for old in ("bBtn", "bPop", "bIn", "bOk")}


def test_issues_sub_inserts_each_copy_after_its_source_and_mirrors_nested_children() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    mapping = result["id_mapping"]
    page_children = json.loads(_change_at(result, "_index", "issues_sub", "bPage")["body"])
    assert page_children == [
        "bBtn",
        mapping["bBtn"],
        "bPop",
        mapping["bPop"],
        "bOther",
        "bGrp",
        "bE1",
        mapping["bE1"],
        "bE2",
        mapping["bE2"],
        "bE3",
    ]
    popup_children = json.loads(_change_at(result, "_index", "issues_sub", mapping["bPop"])["body"])
    assert popup_children == [mapping["bIn"], mapping["bOk"]]


def test_changes_follow_the_editor_order_index_first() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    kinds = []
    for change in result["write_payload"]["changes"]:
        name = change["intent"]["name"]
        path = change["path_array"]
        kinds.append(f"{name}:{path[1]}" if path[0] == "_index" else name)
    first_create = kinds.index("CreateElement")
    assert set(kinds[:first_create]) == {"Update index:id_to_path"}
    assert kinds.index("CreateEvent") > first_create
    assert kinds[-1] == "Update index:issues_sub"


def test_user_text_equal_to_an_id_is_left_alone_and_reported() -> None:
    editor = _Editor(_app())

    result = _run(editor)

    roots = {root["source_id"]: root for root in result["roots"]}
    popup = _change_at(result, *roots["bPop"]["new_pointer"])["body"]
    ok = next(child for child in popup["%el"].values() if child["%nm"] == "OK")
    assert ok["%p"]["%3"] == "bPop"
    assert any(path.endswith("%p.%3") for path in result["unmapped_ids"])


def test_roots_are_renamed_with_a_copy_suffix_unless_a_name_is_given() -> None:
    editor = _Editor(_app())

    default = _run(editor)
    named = _run(_Editor(_app()), rename={"bBtn": "Mark inactive", "bPop": "Inactive popup"})
    single = _run(_Editor(_app()), element_ids=["bBtn"], rename="Mark inactive")

    assert [root["name"] for root in default["roots"]] == ["Open copy", "Confirm popup copy"]
    assert [root["name"] for root in named["roots"]] == ["Mark inactive", "Inactive popup"]
    assert [root["name"] for root in single["roots"]] == ["Mark inactive"]


def test_target_parent_places_the_copy_inside_that_container() -> None:
    editor = _Editor(_app())

    result = _run(editor, element_ids=["bBtn"], target_parent="bGrp")

    root = result["roots"][0]
    assert root["new_pointer"][:5] == ["%p3", "pg1", "%el", "s6", "%el"]
    holder = json.loads(_change_at(result, "_index", "issues_sub", "bGrp")["body"])
    assert holder == [result["id_mapping"]["bBtn"]]


def test_a_target_parent_in_another_page_or_reusable_is_refused() -> None:
    editor = _Editor(_app())

    result = _run(editor, element_ids=["bBtn"], target_parent="bRp")

    assert result["ok"] is False
    assert result["error"] == "cross_context_target"
    assert editor.writes == []


def test_an_unknown_id_or_a_non_element_is_refused_before_writing() -> None:
    missing = _run(_Editor(_app()), element_ids=["bNope"])
    workflow = _run(_Editor(_app()), element_ids=["bE1"])

    assert missing["error"] == "element_not_found"
    assert workflow["error"] == "not_an_element"


def test_a_root_nested_inside_another_root_is_refused() -> None:
    result = _run(_Editor(_app()), element_ids=["bPop", "bOk"])

    assert result["ok"] is False
    assert result["error"] == "nested_roots"


def test_an_unreadable_issues_sub_index_refuses_instead_of_overwriting_it() -> None:
    editor = _Editor(_app())
    del editor.tree["_index"]["issues_sub"]

    result = _run(editor)

    assert result["ok"] is False
    assert result["error"] == "index_unreadable"
    assert editor.writes == []


def test_execute_writes_to_the_named_version_and_verifies_nodes_and_index() -> None:
    editor = _Editor(_app())

    result = _run(editor, execute=True)

    assert result["ok"] is True
    assert result["verified"] is True
    assert result["confirmed_app_version"] == "93k8b"
    assert result["render_unverified"] is True
    payload, dry_run = editor.writes[0]
    assert dry_run is False
    assert payload["app_version"] == "93k8b"
    mapping = result["id_mapping"]
    assert editor.tree["_index"]["id_to_path"][mapping["bOk"]].startswith("%p3.pg1.%el.")


def test_execute_reports_a_write_that_did_not_land() -> None:
    editor = _Editor(_app())

    def lost_write(payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        editor.writes.append((payload, dry_run))
        return {"ok": True, "status": 200}

    result = _run(editor, execute=True, writer=lost_write)

    assert result["ok"] is False
    assert result["error"] == "write_not_verified"
    assert result["verified"] is False
    assert result["confirmed_app_version"] is None
    assert result["divergences"]


# --- the MCP tool -------------------------------------------------------------------------


def _schema(name: str) -> dict[str, Any]:
    from bubble_mcp.server.schemas import list_tool_schemas

    return {tool["name"]: tool for tool in list_tool_schemas()}[name]


def test_the_tool_is_exposed_previews_by_default_and_is_not_read_only() -> None:
    from bubble_mcp.server.agent_catalog import tool_annotations

    schema = _schema("bubble_duplicate_element")

    assert schema["inputSchema"]["required"] == ["profile", "element_ids"]
    assert schema["inputSchema"]["properties"]["execute"]["default"] is False
    assert schema["inputSchema"]["properties"]["include_workflows"]["default"] is True
    assert "default" not in schema["inputSchema"]["properties"]["target_parent"]
    assert tool_annotations("bubble_duplicate_element")["readOnlyHint"] is False


def test_the_tool_routes_to_duplicate_live_element(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from bubble_mcp.server.tools import call_tool

    seen: dict[str, Any] = {}

    def fake_duplicate(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("bubble_mcp.server.tools.duplicate_live_element", fake_duplicate)

    result = call_tool(
        "bubble_duplicate_element",
        {
            "profile": "nobody",
            "element_ids": "bBtn",
            "app_version": "93k8b",
            "rename": "Mark inactive",
            "include_workflows": False,
        },
    )

    assert result == {"ok": True}
    assert seen["element_ids"] == ["bBtn"]
    assert seen["app_version"] == "93k8b"
    assert seen["rename"] == "Mark inactive"
    assert seen["include_workflows"] is False
    assert seen["execute"] is False


def test_an_executed_duplicate_on_main_is_refused_before_anything_runs(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from bubble_mcp.server.tools import call_tool

    def must_not_run(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("a write aimed at main must be refused before the duplicate runs")

    monkeypatch.setattr("bubble_mcp.server.tools.duplicate_live_element", must_not_run)

    result = call_tool(
        "bubble_duplicate_element",
        {"profile": "nobody", "element_ids": ["bBtn"], "app_version": "test", "execute": True},
    )

    assert result["ok"] is False
    assert result["error"] == "main_is_read_only"


def test_tool_search_finds_it_with_the_words_the_agent_used() -> None:
    from bubble_mcp.server.agent_guide import search_tool_catalog

    for query in (
        "duplicate copy element with workflows paste",
        "clone element subtree remint ids",
        "duplicate popup",
    ):
        names = [match["name"] for match in search_tool_catalog(query, limit=5)["matches"]]
        assert "bubble_duplicate_element" in names, (query, names)


def test_an_element_entry_that_lists_its_workflows_is_mirrored_too() -> None:
    editor = _Editor(_app())
    # Live apps list the workflows an element triggers under the element (mcp-test-app).
    editor.tree["_index"]["issues_sub"]["bOk"] = json.dumps(["bE2", "bE3"])

    result = _run(editor)

    mapping = result["id_mapping"]
    ok_entry = json.loads(_change_at(result, "_index", "issues_sub", mapping["bOk"])["body"])
    assert ok_entry == [mapping["bE2"]]  # bE3 was not copied, so it stays with the source
