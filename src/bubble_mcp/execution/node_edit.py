"""One in-place edit of a live editor node: read, change one part, write back, prove it landed.

/appeditor/write answers HTTP 200 for any body and performs no semantic validation, so a
successful response is not evidence. The only evidence is reading the node back and comparing
it to what was intended, which is what this module does on every executed edit.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Sequence

from bubble_mcp.compiler.payload import bubble_session_id
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.live_node_read import read_live_node
from bubble_mcp.execution.raw_node_edit import (
    first_divergence,
    patch_expression_leaf,
    reorder_actions,
)
from bubble_mcp.sessions.store import load_session


SUPPORTED_OPS = ("patch", "reorder")
DEFAULT_APP_VERSION = "test"
VERIFIED_MEANING = (
    "verified=true means the node was read back after the write and its bytes matched the "
    "intent. It does NOT mean the Bubble editor renders the node: a wrongly assembled interior "
    "round-trips byte-identically through /appeditor/write and ._raw(), so render_unverified "
    "stays true until a human opens the editor and confirms the step displays correctly."
)

Reader = Callable[..., dict[str, Any]]
Writer = Callable[..., dict[str, Any]]


def _change(
    path_array: Sequence[str], body: Any, *, session_id: str, intent: str = "SetData"
) -> dict[str, Any]:
    """Return one /appeditor/write change entry in the shape PayloadBuilder already produces."""

    intent_obj: dict[str, Any] = {"name": intent}
    if intent == "SetData":
        intent_obj["id"] = random.randint(2, 999)
        intent_obj["source_appname"] = ""
    return {
        "intent": intent_obj,
        "path_array": [str(part) for part in path_array],
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


# Keys whose values hold further nodes. The guard descends through these and nothing else:
# everything under a node's own %p is the expression interior, which is legitimately spelled
# with decoded-looking keys ("type": "Message") and must never be inspected or rewritten.
_CONTAINER_KEYS = ("actions", "%el", "%wf")


def _is_decoded_node_root(value: dict[str, Any]) -> bool:
    """True when ``value`` looks like a node written with export keys instead of write keys."""

    return ("type" in value or "properties" in value) and not ("%x" in value or "%p" in value)


def _assert_encoded_node_roots(value: Any, path: tuple[str, ...] = ()) -> None:
    """Refuse a change body carrying a node root that is not in encoded (write) form.

    As of 2026-08-26 this module no longer translates anything: the node comes off
    ``read_live_node`` already encoded (``_raw()``, not ``raw()`` - see
    ``docs/session-findings-2026-08-26.md`` and the module docstring on ``live_node_read``),
    is patched in place, and is written back byte-for-byte. This guard used to exist to prove
    that translation had run; now it is a pure safety net against a body that somehow arrived
    decoded anyway - most plausibly a caller who built ``patch``/``node`` from a ``.bubble``
    export, which only ever carries the decoded (``type``/``properties``) form. A decoded root
    accepted by /appeditor/write gets HTTP 200 and renders "[missing: null]".
    ``lint_editor_write_changes`` cannot catch it: it is path-shaped and only inspects the body
    at a path that already looks like a node position.
    """

    if not isinstance(value, dict):
        return
    if _is_decoded_node_root(value) or "%x" in value or "%p" in value:
        _assert_encoded_node(value, path)
        return
    _assert_encoded_container(value, path)


def _assert_encoded_node(node: dict[str, Any], path: tuple[str, ...]) -> None:
    if _is_decoded_node_root(node):
        where = ".".join(path) or "<root>"
        raise ValueError(
            f"change body at '{where}' carries a decoded node root "
            f"({', '.join(sorted(key for key in ('type', 'properties') if key in node))}); "
            "every node in a written body must have its root encoded (%x/%p). Point this edit "
            "at a single action node instead of a container."
        )
    for key in _CONTAINER_KEYS:
        if key not in node:
            continue
        child = node[key]
        if isinstance(child, list):
            # actions/%el/%wf are maps of nodes keyed by index or id, never a bare list; a list
            # here cannot be walked the way a map's items can, and silently skipping it is
            # exactly how a decoded node smuggled in this shape bypassed the guard before.
            where = ".".join((*path, key))
            raise ValueError(
                f"change body at '{where}' carries a list where a map of nodes was expected "
                f"(container key '{key}'); actions/%el/%wf must be keyed maps, not lists."
            )
        if isinstance(child, dict):
            _assert_encoded_container(child, (*path, key))


def _assert_encoded_container(container: dict[str, Any], path: tuple[str, ...]) -> None:
    for key, child in container.items():
        _assert_encoded_container_value(child, (*path, str(key)))


def _assert_encoded_container_value(value: Any, path: tuple[str, ...]) -> None:
    """Walk one container entry, which may be a node, or a list wrapping one or more nodes.

    A decoded node root must be caught wherever it sits, not only when it is the immediate
    dict value of a container key - `actions.0` on some action shapes is itself a list of
    sub-actions, and a decoded node one level inside that list must not be able to hide behind
    the list the way it used to (the guard only ever checked `isinstance(child, dict)`).
    """

    if isinstance(value, dict):
        _assert_encoded_node(value, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_encoded_container_value(item, (*path, str(index)))


def _guard_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Walk every assembled change body and refuse any untranslated node root inside it."""

    for change in changes:
        _assert_encoded_node_roots(change.get("body"))
    return changes


def build_patch_changes(
    pointer: Sequence[str], node: dict[str, Any], session_id: str
) -> list[dict[str, Any]]:
    """Return the single change that writes the whole edited node back at ``pointer``.

    ``node`` is already encoded - it came from ``read_live_node`` (``_raw()``) and was patched
    without touching its key spelling - so it is written back as-is. No encode step here; see
    ``docs/session-findings-2026-08-26.md``.
    """

    return _guard_changes([_change(pointer, node, session_id=session_id)])


def build_reorder_changes(
    pointer: Sequence[str], actions: dict[str, Any], session_id: str
) -> list[dict[str, Any]]:
    """Return the map write plus one index repoint per action.

    Renumbering moves every action to a new path while ``_index.id_to_path`` still points at
    the old one, so the map write alone would leave the editor's index disagreeing with its
    tree. This mirrors the SetData + "Update index" pairing bubble_cli already uses. Every
    change in this list shares one ``session_id``, exactly as ``PayloadBuilder`` does with
    ``self.session_id`` across a batch of changes.

    ``actions`` is already encoded - it came from ``read_live_node`` - so each entry is written
    back exactly as read, just renumbered by key; no encode step here.
    """

    changes = [_change(pointer, dict(actions), session_id=session_id)]
    prefix = ".".join(str(part) for part in pointer)
    for key, value in actions.items():
        action_id = value.get("id")
        if not action_id:
            raise ValueError(
                f"action at position '{key}' has no id, so its index entry cannot be repointed; "
                "a reorder that renumbers a step without moving its index leaves the editor's "
                "_index.id_to_path pointing at another action"
            )
        changes.append(
            _change(
                ["_index", "id_to_path", str(action_id)],
                f"{prefix}.{key}",
                session_id=session_id,
                intent="Update index",
            )
        )
    return _guard_changes(changes)


def edit_live_node(
    *,
    profile: str,
    pointer: Sequence[str],
    op: str,
    leaf_pointer: Sequence[str] | None = None,
    patch: dict[str, Any] | None = None,
    order: Sequence[str] | None = None,
    execute: bool = False,
    app_id: str | None = None,
    app_version: str = DEFAULT_APP_VERSION,
    reader: Reader | None = None,
    writer: Writer | None = None,
) -> dict[str, Any]:
    """Run one read -> modify -> write -> re-read -> compare cycle over a live editor node."""

    segments = [str(part) for part in pointer]
    if op not in SUPPORTED_OPS:
        return {
            "ok": False,
            "error": "unknown_op",
            "message": f"op must be one of {', '.join(SUPPORTED_OPS)}; got '{op}'",
        }
    try:
        _check_op_arguments(op, leaf_pointer, patch, order)
    except (ValueError, TypeError) as error:
        # Checked before the read so a missing argument costs a typo, not a browser launch.
        return {"ok": False, "error": "invalid_edit", "message": str(error)}

    version = str(app_version or DEFAULT_APP_VERSION)
    read = reader or read_live_node
    before = read(profile, segments, app_id=app_id, app_version=version)
    if not before.get("ok"):
        return before
    current = before["node"]

    session_id = bubble_session_id()
    try:
        intended, changes = _apply(op, segments, current, leaf_pointer, patch, order, session_id)
    except KeyError as error:
        return {"ok": False, "error": "pointer_not_resolved", "message": str(error).strip("'\"")}
    except (ValueError, TypeError) as error:
        return {"ok": False, "error": "invalid_edit", "message": str(error)}

    payload: dict[str, Any] = {"changes": changes, "app_version": version}
    if app_id or before.get("app_id"):
        payload["appname"] = str(app_id or before.get("app_id"))

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
        "pointer": segments,
        "before": current,
        "intended": intended,
        "write": write_result,
    }
    if not execute:
        return result

    result["render_unverified"] = True
    result["verified_meaning"] = VERIFIED_MEANING
    if not write_result.get("ok"):
        return {**result, "ok": False, "verified": False, "divergence": None}

    after_read = read(profile, segments, app_id=app_id, app_version=version)
    if not after_read.get("ok"):
        # ``after`` is reserved for the node itself; a failed re-read is a different shape.
        return {
            **result,
            "ok": False,
            "verified": False,
            "divergence": None,
            "after_read": after_read,
        }
    result["after"] = after_read["node"]
    # `intended` and `after_read["node"]` are both encoded (read_live_node reads with _raw(),
    # and nothing in this module translates that away before or after). Comparing two things
    # in the same key space is NOT the self-confirming case the original design warned about
    # (comparing decoded-to-decoded when an encode step could have silently corrupted the
    # write and the comparison would never see it): here the write body IS the encoded node,
    # verbatim, with no transformation between "what was written" and "what is compared" for
    # an encoding bug to hide behind. See docs/session-findings-2026-08-26.md.
    result["divergence"] = first_divergence(intended, after_read["node"])
    result["verified"] = result["divergence"] is None
    return result


def _apply(
    op: str,
    pointer: Sequence[str],
    current: dict[str, Any],
    leaf_pointer: Sequence[str] | None,
    patch: dict[str, Any] | None,
    order: Sequence[str] | None,
    session_id: str,
) -> tuple[Any, list[dict[str, Any]]]:
    """Return (intended node in the encoded key space, changes to write)."""

    _check_op_arguments(op, leaf_pointer, patch, order)
    if op == "patch":
        if not isinstance(current, dict) or not ("type" in current or "%x" in current):
            raise ValueError(
                "patch requires a pointer to a node, not a container: a container (an actions "
                "map, a workflow root) holds several sibling nodes keyed by index or id, and "
                "leaf_pointer resolves against a single node's own fields. Point at one action, "
                f"e.g. {[*[str(part) for part in pointer], '0']}."
            )
        intended = patch_expression_leaf(current, [str(part) for part in leaf_pointer or []], patch or {})
        return intended, build_patch_changes(pointer, intended, session_id)
    intended = reorder_actions(current, [str(part) for part in order or []])
    return intended, build_reorder_changes(pointer, intended, session_id)


def _check_op_arguments(
    op: str,
    leaf_pointer: Sequence[str] | None,
    patch: dict[str, Any] | None,
    order: Sequence[str] | None,
) -> None:
    """Raise when the arguments the op needs are missing, before anything is read."""

    if op == "patch":
        if not leaf_pointer:
            raise ValueError("patch requires leaf_pointer")
        if not isinstance(patch, dict):
            raise ValueError("patch requires a patch object")
        return
    if not order:
        raise ValueError("reorder requires order")
