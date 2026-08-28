"""Edits applied to raw editor nodes without re-encoding them.

Every function here moves or replaces a subtree and leaves the rest of the node exactly as
it was received. That is the whole safety argument: the raw encoding of Bubble expressions
(APIEventParameter, Message chains, param ids) cannot be derived from the .bubble export, so
anything these functions did not explicitly touch must reach the editor untouched.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any


def first_divergence(
    intended: Any, actual: Any, _path: tuple[str, ...] = ()
) -> str | None:
    """Dotted path where `actual` first differs from `intended`, or None when they match.

    /appeditor/write answers HTTP 200 for any body, so the only evidence a write landed is
    reading the node back and comparing it. This names where the comparison broke.
    """

    if isinstance(intended, dict) and isinstance(actual, dict):
        for key in intended:
            if key not in actual:
                return ".".join((*_path, str(key)))
            found = first_divergence(intended[key], actual[key], (*_path, str(key)))
            if found is not None:
                return found
        for key in actual:
            if key not in intended:
                return ".".join((*_path, str(key)))
        return None
    if isinstance(intended, list) and isinstance(actual, list):
        if len(intended) != len(actual):
            return ".".join(_path) or "<root>"
        for index, (left, right) in enumerate(zip(intended, actual)):
            found = first_divergence(left, right, (*_path, str(index)))
            if found is not None:
                return found
        return None
    if intended != actual:
        return ".".join(_path) or "<root>"
    return None


def all_divergences(
    intended: Any, actual: Any, _path: tuple[str, ...] = ()
) -> list[str]:
    """Every dotted path where `actual` differs from `intended`.

    `first_divergence` answers "did this write land", where the first mismatch is enough to know
    the answer is no. A deploy report answers "what would change", where stopping at the first
    difference under-reports the whole thing: two edits in one page would be shown as one.
    """

    if isinstance(intended, dict) and isinstance(actual, dict):
        found: list[str] = []
        for key in intended:
            if key not in actual:
                found.append(".".join((*_path, str(key))))
                continue
            found.extend(all_divergences(intended[key], actual[key], (*_path, str(key))))
        for key in actual:
            if key not in intended:
                found.append(".".join((*_path, str(key))))
        return found
    if isinstance(intended, list) and isinstance(actual, list):
        if len(intended) != len(actual):
            return [".".join(_path) or "<root>"]
        found = []
        for index, (left, right) in enumerate(zip(intended, actual)):
            found.extend(all_divergences(left, right, (*_path, str(index))))
        return found
    if intended != actual:
        return [".".join(_path) or "<root>"]
    return []


def patch_expression_leaf(
    node: dict[str, Any], pointer: list[str], patch: dict[str, Any]
) -> dict[str, Any]:
    """Return a copy of `node` with `patch` applied to the dict `pointer` addresses.

    The pointer must resolve to an existing dict. Nothing is created along the way: a
    missing key means the caller is guessing at the shape, and guessing at the shape is
    what produces nodes the server accepts and the editor renders as "[missing: null]".
    """

    patched = copy.deepcopy(node)
    target: Any = patched
    for index, key in enumerate(pointer):
        if not isinstance(target, dict) or key not in target:
            resolved = ".".join(pointer[:index]) or "<root>"
            raise KeyError(f"pointer key '{key}' does not exist under {resolved}")
        target = target[key]
    if not isinstance(target, dict):
        raise TypeError(f"pointer {'.'.join(pointer)} does not address a node")
    target.update(patch)
    return patched


# A node without these is a body the editor cannot render - and /appeditor/write would accept it
# with HTTP 200, so nothing downstream would notice.
NODE_IDENTITY_KEYS = ("%x", "id", "type")


def remove_expression_keys(
    node: dict[str, Any], pointer: list[str], keys: list[str]
) -> dict[str, Any]:
    """Return a copy of `node` with `keys` dropped from the dict `pointer` addresses.

    `patch_expression_leaf` merges, so it can replace a search constraint but never delete one:
    the only way to shorten a `%co` map was to rewrite the whole thing, which means recomposing
    an expression from the export - the exact move this module exists to avoid.

    A key that is not there is refused rather than skipped. "Remove X" answering ok when X was
    never present reports a change that did not happen.
    """

    trimmed = copy.deepcopy(node)
    target: Any = trimmed
    for index, key in enumerate(pointer):
        if not isinstance(target, dict) or key not in target:
            resolved = ".".join(pointer[:index]) or "<root>"
            raise KeyError(f"pointer key '{key}' does not exist under {resolved}")
        target = target[key]
    if not isinstance(target, dict):
        raise TypeError(f"pointer {'.'.join(pointer)} does not address a node")

    doomed = [key for key in keys if key in NODE_IDENTITY_KEYS]
    if doomed:
        raise ValueError(
            f"refusing to remove {', '.join(doomed)}: a node without its type or id is a body "
            "the editor cannot render, and /appeditor/write would accept it with HTTP 200"
        )
    missing = [key for key in keys if key not in target]
    if missing:
        resolved = ".".join(pointer) or "<root>"
        raise KeyError(f"key(s) {', '.join(missing)} do not exist under {resolved}")
    for key in keys:
        del target[key]
    return trimmed


def reorder_actions(
    actions: dict[str, Any], order: list[str]
) -> dict[str, Any]:
    """Return the action map renumbered from "0" following `order`, bodies untouched.

    `order` must name every existing action exactly once: a reorder that drops a step is a
    deletion wearing a reorder's clothes, and the editor would accept it without complaint.
    """

    missing = [key for key in actions if key not in order]
    if missing:
        raise ValueError(
            f"reorder would drop action(s) {', '.join(sorted(missing))}; "
            "list every existing action key in order"
        )
    unknown = [key for key in order if key not in actions]
    if unknown:
        raise ValueError(f"unknown action key(s) in order: {', '.join(sorted(unknown))}")
    if len(set(order)) != len(order):
        raise ValueError("duplicate action key in order")
    return {str(index): actions[key] for index, key in enumerate(order)}


# Keys whose value IS an object id. The captures show exactly these carrying a workflow's own
# ids: `id` on the event and on each action, and `event_id` inside an APIEventParameter
# expression, which back-references the enclosing workflow. Substituting by value alone instead
# would rewrite anything that happens to read like an id - including text the user typed, which
# `ArbitraryText` carries as a raw string (docs/capture-duplicate-workflow-backend.json).
ID_BEARING_KEYS = ("id", "event_id")


def remap_node_ids_with_report(
    node: Any, mapping: dict[str, str]
) -> tuple[Any, list[str]]:
    """Remap ids and also report where an old id was seen in a field that was NOT rewritten.

    The report is the safety valve for the narrow key list above. If Bubble carries a
    self-reference in some field these captures never showed, it lands in `unmapped` instead of
    being silently left pointing at the source workflow - visible, rather than a clone that looks
    right and behaves wrong.
    """

    unmapped: list[str] = []

    def walk(value: Any, path: tuple[str, ...], key: str | None) -> Any:
        if isinstance(value, dict):
            return {k: walk(v, (*path, str(k)), str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(item, (*path, str(index)), None) for index, item in enumerate(value)]
        if isinstance(value, str) and value in mapping:
            if key in ID_BEARING_KEYS:
                return mapping[value]
            unmapped.append(".".join(path))
        return value

    return walk(node, (), None), unmapped


def remap_node_ids(node: Any, mapping: dict[str, str]) -> Any:
    """Return a copy of `node` with the node's own ids replaced wherever they are held.

    The editor's own duplication does exactly this and nothing more: the mapping holds the node's
    own ids (the event and each action), and everything else - element refs, the target custom
    event, the target's parameter ids - is a reference to an object outside the node and survives
    untouched because it is not in the mapping.

    Substitution has to reach inside expression subtrees. An APIEventParameter argument carries
    `event_id`, a back-reference to the enclosing workflow, and a clone that copied expressions
    verbatim would leave it pointing at the original workflow - a break the editor renders without
    complaint. See docs/capture-duplicate-workflow.md.

    It must NOT reach every string: user-typed text is carried raw, so matching by value alone
    would silently edit someone's content. Use `remap_node_ids_with_report` when you need to know
    about an id seen outside a known id field.
    """

    remapped, _ = remap_node_ids_with_report(node, mapping)
    return remapped


CHANGE_ENVELOPE_API_VERSION = 4


def clone_workflow_changes(
    *,
    node: dict[str, Any],
    node_path: list[str],
    new_slot: str,
    mapping: dict[str, str],
    wf_name: str | None,
    session_id: str,
    intent_id: int,
    id_counter: int | None,
) -> list[dict[str, Any]]:
    """Build the /appeditor/write change list that duplicates `node` into `new_slot`.

    Shaped after real editor traffic (docs/capture-duplicate-workflow.md): the `id_to_path`
    entries come first, then the node itself, then the app-wide id counter. One index entry
    per regenerated id, keyed by the id and valued with the dotted path of the new slot -
    the slot key and the node id are different values and the editor keeps them apart.

    `wf_name` renames the copy for a backend workflow, where the name lives in the body and
    would otherwise collide; pass None for a page workflow, which has no name.
    """

    new_path = [*node_path[:-1], new_slot]
    dotted_path = ".".join(new_path)
    body = remap_node_ids(node, mapping)
    if wf_name is not None:
        body["%p"] = {**body.get("%p", {}), "wf_name": wf_name}

    envelope = {
        "version_control_api_version": CHANGE_ENVELOPE_API_VERSION,
        "changelog_data": [],
        "session_id": session_id,
    }
    changes: list[dict[str, Any]] = [
        {
            "body": dotted_path,
            "path_array": ["_index", "id_to_path", body["id"]],
            "intent": {"name": "Update index"},
            **envelope,
        }
    ]
    for key, action in (body.get("actions") or {}).items():
        changes.append(
            {
                "body": f"{dotted_path}.actions.{key}",
                "path_array": ["_index", "id_to_path", action["id"]],
                "intent": {"name": "Update index"},
                **envelope,
            }
        )
    changes.append(
        {
            "body": body,
            "path_array": new_path,
            "intent": {"name": "CreateEvent", "id": intent_id, "source_appname": ""},
            **envelope,
        }
    )
    if id_counter is not None:
        # The counter is app-wide and the editor echoes whatever it currently holds; a clone
        # that has not read it must leave it alone rather than invent a value.
        changes.append({"type": "id_counter", "value": id_counter})
    return changes


def workflow_id_mapping(
    node: dict[str, Any], mint_id: Callable[[], str]
) -> dict[str, str]:
    """Map the node's own ids - the event and each action - to freshly minted ones.

    Deliberately narrow. Everything else the node mentions (element refs, the target custom
    event, that event's parameter ids, the workflow's own parameter definition ids) belongs
    to an object the clone shares with its source, and the editor leaves all of them alone.
    """

    event_id = node.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("the node has no id to clone from")
    mapping = {event_id: mint_id()}
    for action in (node.get("actions") or {}).values():
        action_id = action.get("id") if isinstance(action, dict) else None
        if not isinstance(action_id, str) or not action_id:
            raise ValueError("an action has no id to clone from")
        mapping[action_id] = mint_id()
    return mapping
