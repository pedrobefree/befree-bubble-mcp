"""Universal post-write verification: re-read every path a change wrote and compare it to intent.

/appeditor/write answers HTTP 200 for any body and performs no semantic validation
(``docs/session-findings-2026-08-26.md``). ``bubble_node_edit`` (``node_edit.py``) already reads
its one hand-built change back and compares it - that pattern caught three real defects in one
session that a bare 200 hid completely (an action written to a path that did not exist, a page
NAME written where a node key belonged, an element NAME written where a resolved id belonged).
Every OTHER mutating tool only ever sees the 200.

The key fact that makes verification generic instead of per-tool: every change entry in a
compiled write payload is self-describing. It carries ``path_array`` (where it wrote) and
``body`` (what it wrote, already in the encoded key space ``read_live_node``/``read_live_nodes``
read with - see ``live_node_read``'s module docstring). So a generic verifier can re-read each
written path and diff it against the body that was sent, for any tool, without knowing anything
about what that tool does.

WHY THIS COMPARES CUMULATIVE EFFECT, NOT EACH CHANGE IN ISOLATION
-------------------------------------------------------------------
Comparing each change against the final tree independently is the obvious implementation, and it
is wrong. ``bubble_cli.add_action`` writes every shell action type (``navigate``,
``make_changes``, ``set_state``, ...) as a two-step payload in the SAME write: a ``CreateAction``
change that carries the WHOLE actions map with the new action's ``"%p": None``
(``_build_full_create_action_map``), followed by separate ``SetData`` changes that fill the
action's properties. Read back, the final tree has ``%p`` populated - the ``SetData`` changes
landed exactly as intended. But the ``CreateAction`` change's own recorded body still says
``"%p": None``, because that is what THAT change, alone, sent. Diffing the final tree against that
one change's stale body manufactures a divergence (``expected: null, actual: {...}``) on every
such write, which is the single most common shape `add_action` produces.

The fix is to simulate the payload's cumulative effect before comparing anything: replay every
change in order into a shared expected-state tree keyed by pointer, exactly the way the editor
itself applies them - a node-shaped write (``CreateAction``, ``ReorderActions``, ...) replaces the
whole subtree at its pointer, a leaf-shaped write (``SetData``) patches one key into whatever is
already at its parent pointer (creating that parent as a dict if the prior write left it
``None``), and a ``Delete``/``Remove*`` change clears its pointer. Because the tree is a shared,
mutable structure, a later write under an earlier write's pointer patches the value the earlier
write's own comparison will see: last write wins, and a deeper write patches its ancestor's
expectation instead of being compared against a stale sibling snapshot. Only after every change
has been replayed does verification look up, per distinct read pointer, what SHOULD be there and
diff that against what the read-back actually returned.

Do not restore the per-change comparison. It looks simpler and it is - it is also provably wrong
for the two-step CreateAction+SetData shape that ``add_action`` and ``add_event_go_to_page`` use
for every shell action type, which makes it wrong for the most common mutating call in the
catalog.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Sequence

from bubble_mcp.execution.live_node_read import read_live_nodes
from bubble_mcp.execution.raw_node_edit import first_divergence


VERIFIED_MEANING = (
    "verified=true means every written path was read back after the write and its bytes matched "
    "the intent. It does NOT mean the Bubble editor renders the change: a wrongly assembled "
    "interior can round-trip byte-identically through /appeditor/write and ._raw(), so "
    "render_unverified stays true until a human opens the editor and confirms the change "
    "displays correctly."
)

REDACTED_BODY = "[REDACTED]"

Reader = Callable[..., dict[tuple[str, ...], dict[str, Any]]]


def _intent_name(change: dict[str, Any]) -> str:
    intent = change.get("intent")
    if isinstance(intent, dict):
        return str(intent.get("name") or "").strip()
    return str(intent or "").strip()


def _is_delete_intent(change: dict[str, Any]) -> bool:
    # Aria-runtime deletes emit RemoveElement/RemoveEvent/DeleteStyle with body: None; the
    # compiler path's sole producer of an intent literally named "Delete" is not the only place
    # this shape appears. Same convention as harness/expert.py's family classifier: match on
    # "delete"/"remove" appearing anywhere in the intent name, not an exact "Delete" equality.
    name = _intent_name(change).lower()
    return "delete" in name or name.startswith("remove")


def _is_bookkeeping_path(segments: Sequence[str]) -> bool:
    # `_index` is the editor's own lookup/bookkeeping tree (id_to_path, issues_list, ...), not
    # the app tree: it is not readable through appquery the same way a normal node pointer is,
    # and it is not what an author intended to change.
    return bool(segments) and segments[0] == "_index"


def _plan_change(change: dict[str, Any]) -> dict[str, Any] | None:
    """Return a verification plan for one change, or None when the change should be skipped."""

    path_array = change.get("path_array")
    if not isinstance(path_array, list) or not path_array:
        return None
    segments = [str(part) for part in path_array]
    if _is_bookkeeping_path(segments):
        return None

    body = change.get("body")
    is_delete = _is_delete_intent(change)
    # Classification is intent-name-only, never body-shape: a non-delete change whose body is
    # None (a deliberate null write - scheduled_deploy.py:419, merge flows) must stay comparable
    # so a re-read that finds the old value still there (Bubble ignored the write) is caught,
    # not silently reported as verified against "nothing to compare".

    dotted = ".".join(segments)
    if is_delete:
        return {"kind": "delete", "path": dotted, "pointer": tuple(segments)}

    if body == REDACTED_BODY:
        # A sensitive write (create_api_token, regenerate_api_token, the sensitive settings
        # write) has its real body replaced with this literal before it ever reaches here
        # (aria_dispatch._sensitive_payload_copy). There is nothing left to compare against -
        # reporting a divergence would be reporting "[REDACTED]" != the real value on every
        # single sensitive write, which is not a defect, it is the redaction working.
        return {"kind": "redacted", "path": dotted}

    if isinstance(body, dict):
        # CreateAction/ReorderActions-shaped writes: body IS the whole node/container at
        # path_array, so the pointer to read is path_array itself and the comparison is a
        # straight dict diff.
        return {"kind": "node", "path": dotted, "pointer": tuple(segments), "expected": body}

    # SetData-shaped writes: body is a bare scalar ("bS35G", true, 48, ...) addressing a leaf
    # under the parent node, e.g. path_array [..., "actions", "0", "%p", "%ei"]. window.appquery's
    # `_child()` chain (see live_node_read.build_appquery_script) walks Bubble AST node
    # wrappers, and a bare scalar is not one, so the pointer walk cannot be trusted to resolve a
    # leaf directly the way it resolves a node. The reliable read is the PARENT node - which
    # `_child()` walks fine, since every path_array we see here was itself produced by walking
    # dict-shaped nodes down to a leaf key - with the comparison done against its value at the
    # final key. This is also exactly the shape `patch_expression_leaf` already writes against
    # (pointer to a dict, key to patch), so it costs nothing extra to reason about.
    if len(segments) < 2:
        return {
            "kind": "unreadable",
            "path": dotted,
            "message": (
                f"path '{dotted}' has no parent to read a leaf value from; cannot verify a "
                "scalar body written at the root."
            ),
        }
    return {
        "kind": "leaf",
        "path": dotted,
        "pointer": tuple(segments[:-1]),
        "leaf_key": segments[-1],
        "expected": body,
    }


def _set_expected(tree: dict[str, Any], pointer: tuple[str, ...], value: Any) -> None:
    """Replay one write into the shared expected-state tree at `pointer`, last-write-wins."""

    node = tree
    for key in pointer[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            # Either nothing was here yet, or a prior write left a non-dict (e.g. CreateAction's
            # "%p": None) - a write reaching deeper than that replaces it with a dict so the
            # deeper key has somewhere to land, exactly what the editor does when a SetData
            # targets a property under a freshly created, still-empty node.
            child = {}
            node[key] = child
        node = child
    node[pointer[-1]] = value


def _clear_expected(tree: dict[str, Any], pointer: tuple[str, ...]) -> None:
    node: Any = tree
    for key in pointer[:-1]:
        child = node.get(key) if isinstance(node, dict) else None
        if not isinstance(child, dict):
            return
        node = child
    if isinstance(node, dict):
        node.pop(pointer[-1], None)


def _lookup_expected(tree: dict[str, Any], pointer: tuple[str, ...]) -> tuple[bool, Any]:
    node: Any = tree
    for key in pointer:
        if not isinstance(node, dict) or key not in node:
            return False, None
        node = node[key]
    return True, node


def _build_expected_tree(plans: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Replay every plan, in order, into one shared tree - the cumulative effect of the payload.

    See the module docstring for why this cannot be done per-change.
    """

    tree: dict[str, Any] = {}
    for plan in plans:
        kind = plan["kind"]
        if kind == "node":
            _set_expected(tree, plan["pointer"], copy.deepcopy(plan["expected"]))
        elif kind == "leaf":
            _set_expected(tree, (*plan["pointer"], plan["leaf_key"]), plan["expected"])
        elif kind == "delete":
            _clear_expected(tree, plan["pointer"])
        # "unreadable" and "redacted" plans carry no comparable expectation - they do not
        # participate in the replay.
    return tree


def verify_changes(
    profile: str,
    changes: Sequence[dict[str, Any]],
    *,
    app_id: str | None = None,
    app_version: str = "test",
    reader: Reader | None = None,
) -> dict[str, Any]:
    """Re-read every path `changes` wrote and report where the app tree differs from intent.

    Never turns a successful write into a failure: `ok` reports that verification RAN, not that
    the write was good, and a read failure (playwright_missing, editor_unstable,
    not_logged_in, ...) is reported as `unverified` rather than as a divergence - it means "we
    don't know", not "it's wrong".
    """

    read = reader or read_live_nodes

    plans: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        plan = _plan_change(change)
        if plan is not None:
            plans.append(plan)

    # Replay the whole payload's cumulative effect once, in order, before comparing anything -
    # see the module docstring for why comparing each change against its own recorded body is
    # wrong for two-step writes.
    expected_tree = _build_expected_tree(plans)

    # Several changes in one payload often touch the same node (a SetData plus its sibling
    # property edits, or two leaves under one parent): read each distinct pointer once no
    # matter how many plans reference it.
    pointers: list[tuple[str, ...]] = []
    seen_pointers: set[tuple[str, ...]] = set()
    for plan in plans:
        pointer = plan.get("pointer")
        if pointer is not None and pointer not in seen_pointers:
            seen_pointers.add(pointer)
            pointers.append(pointer)

    read_results: dict[tuple[str, ...], dict[str, Any]] = {}
    if pointers:
        read_results = read(profile, pointers, app_id=app_id, app_version=app_version) or {}

    divergences: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []

    for plan in plans:
        kind = plan["kind"]

        if kind == "unreadable":
            unverified.append(
                {"path": plan["path"], "error": "unreadable_leaf", "message": plan["message"]}
            )
            continue

        if kind == "redacted":
            unverified.append(
                {
                    "path": plan["path"],
                    "error": "redacted",
                    "message": (
                        "this change's body was redacted before verification because it carries "
                        "sensitive data (an API token, a sensitive setting); it cannot be "
                        "compared without re-exposing the real value."
                    ),
                }
            )
            continue

        result = read_results.get(plan["pointer"])
        if not isinstance(result, dict):
            unverified.append(
                {
                    "path": plan["path"],
                    "error": "no_read_result",
                    "message": f"No read result for pointer '{'.'.join(plan['pointer'])}'.",
                }
            )
            continue

        if kind == "delete":
            # A later change in the SAME payload may write back under this pointer (e.g. a
            # RemoveElement followed by a SetData that recreates the parent as a dict and fills
            # a key under it) - the replay tree is what governs the pointer at the END of the
            # payload, so check there first. When nothing later claims this pointer, the delete
            # is still what governs it and absence is what verification demands.
            found, expected = _lookup_expected(expected_tree, plan["pointer"])
            if not found:
                if result.get("ok"):
                    divergences.append(
                        {
                            "path": plan["path"],
                            "divergence": "<root>",
                            "expected": "absent",
                            "actual": result.get("node"),
                        }
                    )
                elif result.get("error") == "pointer_not_found":
                    pass  # exactly the pass condition for a Delete: the path is gone
                else:
                    unverified.append(
                        {
                            "path": plan["path"],
                            "error": result.get("error") or "unverified",
                            "message": result.get("message") or "",
                        }
                    )
                continue
            # Superseded: a later write in this payload governs this pointer now, so verify it
            # the same way a node-kind plan would - against what SHOULD be there, not absence.
            if not result.get("ok"):
                error = str(result.get("error") or "unverified")
                if error == "pointer_not_found":
                    divergences.append(
                        {
                            "path": plan["path"],
                            "divergence": "<root>",
                            "expected": "present",
                            "actual": "absent",
                        }
                    )
                else:
                    unverified.append(
                        {
                            "path": plan["path"],
                            "error": error,
                            "message": result.get("message") or "",
                        }
                    )
                continue
            actual = result.get("node")
            divergence = first_divergence(expected, actual)
            if divergence is not None:
                divergences.append(
                    {
                        "path": plan["path"],
                        "divergence": divergence,
                        "expected": expected,
                        "actual": actual,
                    }
                )
            continue

        if not result.get("ok"):
            error = str(result.get("error") or "unverified")
            if error == "pointer_not_found" and kind in ("node", "leaf"):
                # For a node-kind plan the write was supposed to land AT this pointer, so a read
                # that finds nothing here is exactly the orphan-node signal this layer exists to
                # catch (docs/session-findings-2026-08-26.md section 8) - a divergence, not "we
                # couldn't check". For a leaf-kind plan, pointer is the PARENT node; an absent
                # parent proves the intended leaf does not exist either (measured against the
                # live editor: %p and its children ARE addressable through appquery's `_child()`
                # walk, so pointer_not_found means genuine absence, not "cannot address").
                divergences.append(
                    {
                        "path": plan["path"],
                        "divergence": "<root>",
                        "expected": "present" if kind == "node" else plan["expected"],
                        "actual": "absent",
                    }
                )
            else:
                # Reserved for failures that produced no semantic read at all - editor_unstable,
                # not_logged_in, playwright_missing, wrong_app: "we don't know", not "it's wrong".
                unverified.append(
                    {
                        "path": plan["path"],
                        "error": error,
                        "message": result.get("message") or "",
                    }
                )
            continue

        found, expected = _lookup_expected(
            expected_tree,
            plan["pointer"] if kind == "node" else (*plan["pointer"], plan["leaf_key"]),
        )
        if not found:
            # A later change in the same payload overwrote this pointer's ancestor with a fresh
            # node that no longer carries this key: this plan's own expectation was superseded
            # before the payload finished applying. Whatever the final state is, it is checked by
            # whichever later plan governs that pointer instead.
            continue

        actual_node = result.get("node")
        if kind == "node":
            actual: Any = actual_node
        else:  # leaf
            actual = actual_node.get(plan["leaf_key"]) if isinstance(actual_node, dict) else None

        divergence = first_divergence(expected, actual)
        if divergence is not None:
            divergences.append(
                {
                    "path": plan["path"],
                    "divergence": divergence,
                    "expected": expected,
                    "actual": actual,
                }
            )

    checked = len(plans)
    verified = not divergences and not unverified

    return {
        "ok": True,
        "checked": checked,
        "verified": verified,
        "divergences": divergences,
        "unverified": unverified,
        "render_unverified": True,
        "verified_meaning": VERIFIED_MEANING,
    }
