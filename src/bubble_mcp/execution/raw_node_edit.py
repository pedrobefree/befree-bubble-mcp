"""Edits applied to raw editor nodes without re-encoding them.

Every function here moves or replaces a subtree and leaves the rest of the node exactly as
it was received. That is the whole safety argument: the raw encoding of Bubble expressions
(APIEventParameter, Message chains, param ids) cannot be derived from the .bubble export, so
anything these functions did not explicitly touch must reach the editor untouched.
"""

from __future__ import annotations

import copy
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
