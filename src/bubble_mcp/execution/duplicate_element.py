"""Duplicate live elements - a button, a popup, a whole group - together with their workflows.

The editor's own duplication deep-copies the raw node and remints its ids; nothing is
recomposed (docs/capture-duplicate-workflow.md). This does the same for an element subtree:

- every element in the subtree gets a new id and a new slot key (the two are kept apart, as the
  editor keeps them apart);
- workflows triggered by any copied element are copied too, and one id mapping covers elements
  and workflows together, so a copied "show popup" step opens the copied popup and a copied
  GetElement reads the copied input;
- ``_index`` is maintained here - ``id_to_path`` for every new id, ``issues_list`` for every new
  element, ``issues_sub`` read-modify-written for the parents and mirrored for nested
  containers - so an agent never assembles index entries by hand.

Several roots can be copied in one call (a button and the popup it opens); they share the
mapping. A workflow outside the copy that points at a copied element (another button opening
the same popup) is reported, not copied: copying it would add a second trigger on an element
that was never duplicated.

The source is read from the live editor (``_raw()``), never from the export, and the index is
read whole before anything is minted, so a new id cannot land on one the app already uses.
"""

from __future__ import annotations

import copy
import json
import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from bubble_mcp.aria_runtime.bubble_sdk import BubbleIDGenerator
from bubble_mcp.compiler.payload import bubble_session_id
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.live_node_read import read_live_nodes
from bubble_mcp.execution.node_edit import DEFAULT_APP_VERSION, _minter_avoiding
from bubble_mcp.execution.raw_node_edit import (
    CHANGE_ENVELOPE_API_VERSION,
    ID_BEARING_KEYS,
    remap_node_ids_with_report,
    workflow_id_mapping,
)
from bubble_mcp.execution.write_verify import verify_changes
from bubble_mcp.sessions.store import load_session

# The element reference key. Added to the id-bearing keys because the mapping here holds element
# ids: a copied workflow's trigger, a copied "show element" step and a copied GetElement all
# name their element through %ei.
ELEMENT_REF_KEY = "%ei"
REMAP_KEYS = (*ID_BEARING_KEYS, ELEMENT_REF_KEY)
ID_TO_PATH = ("_index", "id_to_path")
ISSUES_SUB = ("_index", "issues_sub")
COPY_SUFFIX = " copy"
VERIFIED_MEANING = (
    "verified=true means every copied node and every index entry was read back from the target "
    "version and matched what was sent. It does NOT mean the editor renders the copy: "
    "render_unverified stays true until a human opens the editor and checks it."
)

BatchReader = Callable[..., Mapping[tuple[str, ...], dict[str, Any]]]
Writer = Callable[..., dict[str, Any]]
Verifier = Callable[..., dict[str, Any]]


class _Refusal(Exception):
    def __init__(self, error: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.payload = {"ok": False, "error": error, "message": message, **extra}


def duplicate_live_element(
    *,
    profile: str,
    element_ids: Sequence[str],
    target_parent: str | None = None,
    rename: str | Mapping[str, str] | None = None,
    include_workflows: bool = True,
    execute: bool = False,
    app_id: str | None = None,
    app_version: str = DEFAULT_APP_VERSION,
    reader: BatchReader | None = None,
    writer: Writer | None = None,
    mint_id: Callable[[], str] | None = None,
    verifier: Verifier | None = None,
) -> dict[str, Any]:
    """Copy the elements named by ``element_ids`` (and their workflows) beside them or into
    ``target_parent``. Preview unless ``execute``; an executed copy is read back and checked."""

    version = str(app_version or DEFAULT_APP_VERSION)
    read = reader or read_live_nodes
    try:
        plan = _plan(
            profile=profile,
            element_ids=element_ids,
            target_parent=target_parent,
            rename=rename,
            include_workflows=include_workflows,
            app_id=app_id,
            version=version,
            read=read,
            mint=mint_id or BubbleIDGenerator.element_id,
        )
    except _Refusal as refusal:
        return refusal.payload

    payload: dict[str, Any] = {"changes": plan["changes"], "app_version": version}
    appname = app_id or plan.get("app_id")
    if appname:
        payload["appname"] = str(appname)

    write = writer
    session = None
    if write is None:
        session = load_session(profile)
        if session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        write = BubbleEditorClient().write
    write_result = write(payload, session, dry_run=not execute)

    result: dict[str, Any] = {
        "ok": True,
        "execute": execute,
        "app_version": version,
        "roots": plan["roots"],
        "copied_workflows": plan["copied_workflows"],
        "referencing_workflows_not_copied": plan["referencing"],
        "id_mapping": plan["mapping"],
        "new_ids": plan["new_ids"],
        "index_entries": [
            {"path": ".".join(change["path_array"]), "value": change["body"]}
            for change in plan["changes"]
            if change["path_array"][0] == "_index"
        ],
        "unmapped_ids": plan["unmapped"],
        "write_payload": payload,
        "write": write_result,
    }
    if not execute:
        return result

    result["render_unverified"] = True
    result["verified_meaning"] = VERIFIED_MEANING
    if not write_result.get("ok"):
        return {**result, "ok": False, "verified": False, "confirmed_app_version": None}
    return {
        **result,
        **_verify(
            profile,
            plan["changes"],
            app_id=appname,
            app_version=version,
            read=read,
            verify=verifier or verify_changes,
        ),
    }


def _plan(
    *,
    profile: str,
    element_ids: Sequence[str],
    target_parent: str | None,
    rename: str | Mapping[str, str] | None,
    include_workflows: bool,
    app_id: str | None,
    version: str,
    read: BatchReader,
    mint: Callable[[], str],
) -> dict[str, Any]:
    sources = list(dict.fromkeys(str(value).strip() for value in element_ids if str(value).strip()))
    if not sources:
        raise _Refusal("invalid_duplicate", "element_ids needs at least one element id.")
    names = _root_names(sources, rename)

    index = read(profile, [ID_TO_PATH, ISSUES_SUB], app_id=app_id, app_version=version)
    id_to_path = _index_map(index, ID_TO_PATH)
    issues_sub = _index_map(index, ISSUES_SUB)
    app_name = next((r.get("app_id") for r in index.values() if isinstance(r, dict) and r.get("app_id")), None)
    id_by_path = {str(path): str(object_id) for object_id, path in id_to_path.items()}

    root_paths = {source: _element_path(source, id_to_path) for source in sources}
    context = root_paths[sources[0]][:2]
    for source, segments in root_paths.items():
        if segments[:2] != context:
            raise _Refusal(
                "mixed_contexts",
                f"'{source}' is on {'.'.join(segments[:2])}, not {'.'.join(context)}: every element "
                "copied together must be on the same page or reusable.",
            )
    for source, segments in root_paths.items():
        for other, other_segments in root_paths.items():
            if other != source and segments[: len(other_segments)] == other_segments:
                raise _Refusal(
                    "nested_roots",
                    f"'{source}' is inside '{other}', which is already copied with its whole "
                    "subtree. Name only the outer element.",
                )

    target = _target_container(target_parent, id_to_path, context) if target_parent else None

    pointers = [tuple(segments) for segments in root_paths.values()]
    workflows_pointer = (*context, "%wf")
    reads = read(profile, [*pointers, workflows_pointer], app_id=app_id, app_version=version)
    nodes: dict[str, dict[str, Any]] = {}
    for source, segments in root_paths.items():
        answer = reads.get(tuple(segments)) or {}
        if not answer.get("ok"):
            raise _Refusal(
                str(answer.get("error") or "read_failed"),
                str(answer.get("message") or f"Could not read '{source}' from the live editor."),
                pointer=segments,
            )
        node = answer.get("node")
        if not isinstance(node, dict):
            raise _Refusal("not_an_element", f"'{source}' does not hold an element node.")
        nodes[source] = node
    workflows_read = reads.get(workflows_pointer) or {}
    workflows = workflows_read.get("node") if workflows_read.get("ok") else None
    if not isinstance(workflows, dict):
        if include_workflows and workflows_read.get("error") != "pointer_not_found":
            raise _Refusal(
                str(workflows_read.get("error") or "read_failed"),
                "Could not read the workflows of "
                f"{'.'.join(context)}; pass include_workflows=false to copy the elements alone.",
            )
        workflows = {}

    taken = set(id_to_path) | set(issues_sub)
    for path in id_to_path.values():
        taken.update(str(path).split("."))
    minter = _minter_avoiding(mint, taken)

    # Pass 1: every element in every subtree, with a new id and a new slot.
    mapping: dict[str, str] = {}
    slots: dict[str, str] = {}
    elements: list[tuple[str, dict[str, Any]]] = []
    for source in sources:
        for element_id, node in _walk_elements(nodes[source]):
            mapping[element_id] = minter()
            slots[element_id] = minter()
            elements.append((element_id, node))
    copied_ids = set(mapping)

    # Pass 2: the workflows those elements trigger, and the ones that only point at them.
    selected: list[tuple[str, dict[str, Any]]] = []
    referencing: list[dict[str, Any]] = []
    for slot, workflow in workflows.items():
        if not isinstance(workflow, dict):
            continue
        trigger = (workflow.get("%p") or {}).get(ELEMENT_REF_KEY) if isinstance(workflow.get("%p"), dict) else None
        if include_workflows and trigger in copied_ids:
            selected.append((str(slot), workflow))
            continue
        refs = sorted(_element_refs(workflow) & copied_ids)
        if refs:
            referencing.append(
                {"id": workflow.get("id"), "pointer": [*workflows_pointer, str(slot)], "references": refs}
            )
    workflow_slots: dict[str, str] = {}
    for _, workflow in selected:
        try:
            mapping.update(workflow_id_mapping(workflow, minter))
        except ValueError as error:
            raise _Refusal("invalid_duplicate", str(error)) from error
        workflow_slots[str(workflow["id"])] = minter()

    # Pass 3: the bodies, remapped through the one mapping.
    unmapped: list[str] = []
    session_id = bubble_session_id()
    roots: list[dict[str, Any]] = []
    element_creates: list[dict[str, Any]] = []
    id_entries: list[dict[str, Any]] = []
    parents: dict[str, list[tuple[str, str]]] = {}
    for source in sources:
        old_segments = root_paths[source]
        container = target if target is not None else old_segments[:-2]
        new_segments = [*container, "%el", slots[source]]
        body = _rebuild(nodes[source], new_segments, mapping, slots, unmapped, id_entries, session_id, old_segments)
        name = names.get(source) or _copy_name(body.get("%nm"))
        if name is not None:
            body["%nm"] = name
        element_creates.append(_change("CreateElement", new_segments, body, session_id))
        roots.append(
            {
                "source_id": source,
                "source_pointer": old_segments,
                "new_id": mapping[source],
                "new_pointer": new_segments,
                "name": body.get("%nm"),
            }
        )
        parent_id = id_by_path.get(".".join(container))
        if parent_id is not None:
            parents.setdefault(parent_id, []).append((source, mapping[source]))

    workflow_creates: list[dict[str, Any]] = []
    copied_workflows: list[dict[str, Any]] = []
    context_id = id_by_path.get(".".join(context))
    for slot, workflow in selected:
        new_segments = [*workflows_pointer, workflow_slots[str(workflow["id"])]]
        body, seen = remap_node_ids_with_report(copy.deepcopy(workflow), mapping, REMAP_KEYS)
        unmapped.extend(f"{'.'.join([*workflows_pointer, slot])}.{path}" for path in seen)
        dotted = ".".join(new_segments)
        id_entries.append(_index_change(["_index", "id_to_path", body["id"]], dotted, session_id))
        for key, action in (body.get("actions") or {}).items():
            id_entries.append(
                _index_change(["_index", "id_to_path", action["id"]], f"{dotted}.actions.{key}", session_id)
            )
        workflow_creates.append(_change("CreateEvent", new_segments, body, session_id))
        copied_workflows.append(
            {
                "source_id": workflow["id"],
                "source_pointer": [*workflows_pointer, slot],
                "new_id": body["id"],
                "new_pointer": new_segments,
            }
        )
        if context_id is not None:
            parents.setdefault(context_id, []).append((str(workflow["id"]), str(body["id"])))

    issues_list = [
        _index_change(["_index", "issues_list", mapping[element_id]], "[]", session_id)
        for element_id, _ in elements
    ]
    issues_sub_changes = [
        _index_change(
            ["_index", "issues_sub", parent_id],
            json.dumps(_insert_after_sources(_parse_ids(issues_sub.get(parent_id)), pairs)),
            session_id,
        )
        for parent_id, pairs in parents.items()
    ]
    for element_id, node in elements:
        children = [child for _, child in _child_elements(node)]
        if not children:
            continue
        recorded = _parse_ids(issues_sub.get(element_id))
        order = recorded if recorded else [str(child["id"]) for child in children]
        issues_sub_changes.append(
            _index_change(
                ["_index", "issues_sub", mapping[element_id]],
                json.dumps([mapping[child] for child in order if child in mapping]),
                session_id,
            )
        )

    new_workflow_ids = {entry["new_id"] for entry in copied_workflows}
    return {
        "app_id": app_name,
        "changes": [*id_entries, *element_creates, *workflow_creates, *issues_list, *issues_sub_changes],
        "roots": roots,
        "copied_workflows": copied_workflows,
        "referencing": referencing,
        "mapping": mapping,
        "new_ids": {
            "elements": [mapping[element_id] for element_id, _ in elements],
            "workflows": sorted(new_workflow_ids),
            "actions": sorted(
                set(mapping.values()) - {mapping[element_id] for element_id, _ in elements} - new_workflow_ids
            ),
        },
        "unmapped": unmapped,
    }


def _root_names(sources: Sequence[str], rename: str | Mapping[str, str] | None) -> dict[str, str]:
    if rename is None or rename == "":
        return {}
    if isinstance(rename, str):
        if len(sources) != 1:
            raise _Refusal(
                "invalid_rename",
                "rename as a string names one copy; with several element_ids pass an object "
                "mapping each source element id to its copy's name.",
            )
        return {sources[0]: rename}
    if isinstance(rename, Mapping):
        unknown = sorted(set(map(str, rename)) - set(sources))
        if unknown:
            raise _Refusal("invalid_rename", f"rename names ids that are not copied: {', '.join(unknown)}.")
        return {str(key): str(value) for key, value in rename.items()}
    raise _Refusal("invalid_rename", "rename must be a string or an object.")


def _index_map(results: Mapping[tuple[str, ...], dict[str, Any]], pointer: tuple[str, ...]) -> dict[str, Any]:
    answer = results.get(pointer) or {}
    node = answer.get("node") if answer.get("ok") else None
    if not isinstance(node, dict):
        # Without the whole index a new id could collide, and without issues_sub a parent's
        # child list would be rewritten from nothing - which drops every sibling from the editor.
        raise _Refusal(
            "index_unreadable" if answer.get("error") in (None, "pointer_not_found") else str(answer["error"]),
            str(answer.get("message") or f"Could not read {'.'.join(pointer)} from the live editor."),
            pointer=list(pointer),
        )
    return node


def _element_path(element_id: str, id_to_path: Mapping[str, Any]) -> list[str]:
    path = id_to_path.get(element_id)
    if not isinstance(path, str) or not path:
        raise _Refusal(
            "element_not_found",
            f"'{element_id}' is not in _index.id_to_path on this version. Pass the element's id "
            "(not its name or slot key), as the version being copied holds it.",
        )
    segments = path.split(".")
    if len(segments) < 4 or segments[-2] != "%el":
        raise _Refusal(
            "not_an_element",
            f"'{element_id}' lives at {path}, which is not an element. Copy a workflow with "
            "bubble_clone_workflow.",
        )
    return segments


def _target_container(target_parent: str, id_to_path: Mapping[str, Any], context: list[str]) -> list[str]:
    path = id_to_path.get(target_parent)
    if not isinstance(path, str) or not path:
        raise _Refusal("target_not_found", f"target_parent '{target_parent}' is not in _index.id_to_path.")
    segments = path.split(".")
    if segments[:2] != context:
        raise _Refusal(
            "cross_context_target",
            f"target_parent '{target_parent}' is on {'.'.join(segments[:2])}, but the copy comes "
            f"from {'.'.join(context)}. Workflows and element references cannot follow a copy to "
            "another page or reusable.",
        )
    if segments != context and segments[-2] != "%el":
        raise _Refusal("not_a_container", f"target_parent '{target_parent}' lives at {path}, which is not an element.")
    return segments


def _child_elements(node: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    children = node.get("%el")
    if not isinstance(children, dict):
        return []
    return [(str(slot), child) for slot, child in children.items() if isinstance(child, dict)]


def _walk_elements(node: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    element_id = node.get("id")
    if not isinstance(element_id, str) or not element_id:
        raise _Refusal("invalid_duplicate", "an element in the subtree has no id to copy from.")
    found = [(element_id, node)]
    for _, child in _child_elements(node):
        found.extend(_walk_elements(child))
    return found


def _rebuild(
    node: dict[str, Any],
    new_segments: list[str],
    mapping: dict[str, str],
    slots: dict[str, str],
    unmapped: list[str],
    id_entries: list[dict[str, Any]],
    session_id: str,
    old_segments: list[str],
) -> dict[str, Any]:
    """The node's copy: own fields remapped, children rebuilt under their new slots."""

    new_id = mapping[str(node["id"])]
    id_entries.append(_index_change(["_index", "id_to_path", new_id], ".".join(new_segments), session_id))
    body: dict[str, Any] = {}
    for key, value in node.items():
        if key == "%el" and isinstance(value, dict):
            children: dict[str, Any] = {}
            for slot, child in value.items():
                if isinstance(child, dict):
                    new_slot = slots[str(child["id"])]
                    children[new_slot] = _rebuild(
                        child,
                        [*new_segments, "%el", new_slot],
                        mapping,
                        slots,
                        unmapped,
                        id_entries,
                        session_id,
                        [*old_segments, "%el", str(slot)],
                    )
                else:
                    children[slot] = copy.deepcopy(child)
            body[key] = children
            continue
        remapped, seen = remap_node_ids_with_report({key: copy.deepcopy(value)}, mapping, REMAP_KEYS)
        body[key] = remapped[key]
        unmapped.extend(f"{'.'.join(old_segments)}.{path}" for path in seen)
    return body


def _element_refs(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == ELEMENT_REF_KEY and isinstance(child, str):
                found.add(child)
            else:
                found |= _element_refs(child)
    elif isinstance(value, list):
        for item in value:
            found |= _element_refs(item)
    return found


def _copy_name(name: Any) -> str | None:
    return f"{name}{COPY_SUFFIX}" if isinstance(name, str) and name else None


def _parse_ids(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(value) for value in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
        except ValueError:
            return []
        if isinstance(decoded, list):
            return [str(value) for value in decoded]
    return []


def _insert_after_sources(current: list[str], pairs: Sequence[tuple[str, str]]) -> list[str]:
    """Place each copy right after its source, the way the editor's duplicate does; append
    when the source is not in this list (a copy moved into another container)."""

    result = list(current)
    inserted: set[str] = set()
    for source, new in pairs:
        if source in result:
            position = result.index(source) + 1
            while position < len(result) and result[position] in inserted:
                position += 1
            result.insert(position, new)
        else:
            result.append(new)
        inserted.add(new)
    return result


def _envelope(session_id: str) -> dict[str, Any]:
    return {
        "version_control_api_version": CHANGE_ENVELOPE_API_VERSION,
        "changelog_data": [],
        "session_id": session_id,
    }


def _change(intent: str, path: list[str], body: Any, session_id: str) -> dict[str, Any]:
    return {
        "body": body,
        "path_array": [str(part) for part in path],
        "intent": {"name": intent, "id": random.randint(2, 999), "source_appname": ""},
        **_envelope(session_id),
    }


def _index_change(path: list[str], body: Any, session_id: str) -> dict[str, Any]:
    return {
        "body": body,
        "path_array": [str(part) for part in path],
        "intent": {"name": "Update index"},
        **_envelope(session_id),
    }


def _verify(
    profile: str,
    changes: list[dict[str, Any]],
    *,
    app_id: str | None,
    app_version: str,
    read: BatchReader,
    verify: Verifier,
) -> dict[str, Any]:
    """Read the copied nodes and every index entry back from the version that was written."""

    nodes = verify(profile, changes, app_id=app_id, app_version=app_version, reader=read)
    divergences = list(nodes.get("divergences") or [])
    unverified = list(nodes.get("unverified") or [])

    index_changes = [change for change in changes if change["path_array"][0] == "_index"]
    pointers = [tuple(change["path_array"]) for change in index_changes]
    answers = read(profile, pointers, app_id=app_id, app_version=app_version) if pointers else {}
    for change, pointer in zip(index_changes, pointers):
        path = ".".join(pointer)
        answer = answers.get(pointer) or {}
        if not answer.get("ok"):
            if answer.get("error") == "pointer_not_found":
                divergences.append({"path": path, "expected": change["body"], "actual": "absent"})
            else:
                unverified.append(
                    {"path": path, "error": answer.get("error") or "unverified", "message": answer.get("message") or ""}
                )
            continue
        actual = answer.get("node")
        if not _same_index_value(change["body"], actual):
            divergences.append({"path": path, "expected": change["body"], "actual": actual})

    verified = not divergences and not unverified
    outcome: dict[str, Any] = {
        "verified": verified,
        "divergences": divergences,
        "unverified": unverified,
        "confirmed_app_version": app_version if verified else None,
    }
    if divergences:
        outcome["ok"] = False
        outcome["error"] = "write_not_verified"
        outcome["message"] = (
            f"The copy was sent to '{app_version}', but reading it back from '{app_version}' does "
            "not show it as sent (see divergences). Check the version before writing anything else."
        )
    return outcome


def _same_index_value(expected: Any, actual: Any) -> bool:
    if expected == actual:
        return True
    # issues_sub/issues_list are JSON strings on the wire; the editor may hand back the list.
    if isinstance(expected, str) and isinstance(actual, list):
        return _parse_ids(expected) == [str(value) for value in actual]
    return False
