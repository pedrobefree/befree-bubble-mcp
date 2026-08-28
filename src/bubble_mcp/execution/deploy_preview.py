"""What a deploy would push: the diff between the deployed `live` version and `test`.

There is no local copy of `live` to maintain. `live` only changes when someone deploys, and the
path API answers for it the same way it answers for `test`, so the baseline is read on demand.

Two sources for the list of paths to compare, because they have different blind spots:

- ``overlay`` - the paths the local mutation overlay recorded. Precise and free, but it only knows
  what the MCP itself wrote: a change made by hand in the editor is invisible to it.
- ``full_scan`` - walk the app roots in both versions and diff. Sees everything regardless of
  origin, at the cost of pulling both trees.

``/appeditor/fetch_changelog_entries`` would have been the ideal source - server-side, per change,
with paths - but it answers HTTP 200 with an empty list on the app this was built against, so
nothing here depends on it.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence

from bubble_mcp.execution.raw_node_edit import all_divergences


Pointer = tuple[str, ...]
Reader = Callable[..., dict[Pointer, Any]]

# The roots the editor itself loads on boot, minus `_index`, which is its own lookup tree.
APP_ROOTS: tuple[Pointer, ...] = (
    ("%p3",),
    ("api",),
    ("%ed",),
    ("styles",),
    ("user_types",),
    ("option_sets",),
    ("settings",),
    ("global_expressions",),
)
SUPPORTED_SOURCES = ("overlay", "full_scan")


class PathReadError(RuntimeError):
    """A read did not answer. Distinct from a path that answered "nothing here"."""



def _is_bookkeeping(segments: Sequence[str]) -> bool:
    return bool(segments) and str(segments[0]) == "_index"


def changed_pointers(
    overlay: dict[str, Any], *, since: str | None = None
) -> list[Pointer]:
    """Distinct node pointers the overlay recorded, in the order they were first written.

    `since` is compared as an ISO-8601 string against each entry's `captured_at`, which is how
    the overlay stores it; both are UTC, so lexicographic order is chronological order.
    """

    pointers: list[Pointer] = []
    seen: set[Pointer] = set()
    for entry in overlay.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if since and str(entry.get("captured_at") or "") < since:
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            path_array = change.get("path_array")
            if not isinstance(path_array, list) or not path_array:
                continue
            segments = tuple(str(part) for part in path_array)
            if _is_bookkeeping(segments) or segments in seen:
                continue
            seen.add(segments)
            pointers.append(segments)
    return pointers


def diff_versions(
    before: dict[Pointer, Any], after: dict[Pointer, Any]
) -> list[dict[str, Any]]:
    """Compare two pointer->node maps and describe what a deploy would do to each path."""

    entries: list[dict[str, Any]] = []
    for pointer in list(before) + [p for p in after if p not in before]:
        in_before = pointer in before
        in_after = pointer in after
        if in_before and not in_after:
            entries.append(
                {"pointer": list(pointer), "status": "removed", "before": before[pointer]}
            )
            continue
        if in_after and not in_before:
            entries.append({"pointer": list(pointer), "status": "added", "after": after[pointer]})
            continue
        divergences = all_divergences(before[pointer], after[pointer])
        if not divergences:
            continue
        entries.append(
            {
                "pointer": list(pointer),
                "status": "changed",
                # Every differing path, not just the first: one root can hold many edits, and a
                # report that names one of them under-states what the deploy would push.
                "divergences": divergences,
                "divergence": divergences[0],
                "before": before[pointer],
                "after": after[pointer],
            }
        )
    return entries


def preview_deploy(
    *,
    profile: str,
    app_id: str | None = None,
    overlay: dict[str, Any] | None = None,
    source: str = "overlay",
    since: str | None = None,
    live_version: str = "live",
    test_version: str = "test",
    reader: Reader,
) -> dict[str, Any]:
    """Report what deploying `test_version` would change in `live_version`."""

    if source not in SUPPORTED_SOURCES:
        return {
            "ok": False,
            "error": "unknown_source",
            "message": f"source must be one of {', '.join(SUPPORTED_SOURCES)}; got '{source}'",
        }

    if source == "full_scan":
        pointers: list[Pointer] = list(APP_ROOTS)
    else:
        pointers = changed_pointers(overlay or {}, since=since)

    if not pointers:
        # An empty overlay means "this MCP recorded no writes", which is NOT the same as "there
        # is nothing to deploy": someone may have edited the app by hand. Say so, rather than
        # letting an empty list read as an all-clear.
        return {
            "ok": True,
            "profile": profile,
            "app_id": app_id,
            "source": source,
            "pointers": [],
            "changes": [],
            "complete": False,
            "message": (
                "No writes recorded locally, so nothing was compared. This does not mean the app "
                "is unchanged - edits made by hand in the editor are invisible here. Re-run with "
                "source='full_scan' to compare the app itself."
            ),
        }

    try:
        before = reader(profile, pointers, app_id=app_id, app_version=live_version) or {}
        after = reader(profile, pointers, app_id=app_id, app_version=test_version) or {}
    except PathReadError as error:
        return {
            "ok": False,
            "error": "read_failed",
            "message": str(error),
            "profile": profile,
            "app_id": app_id,
            "source": source,
        }
    return {
        "ok": True,
        "profile": profile,
        "app_id": app_id,
        "source": source,
        "live_version": live_version,
        "test_version": test_version,
        "pointers": [list(pointer) for pointer in pointers],
        "changes": diff_versions(before, after),
        # Only a full scan can claim to have seen everything. An overlay-sourced report covers
        # what this MCP wrote and nothing else, however many entries it holds.
        "complete": source == "full_scan",
        **(
            {}
            if source == "full_scan"
            else {
                "message": (
                    "Compared only the paths this MCP wrote. Edits made by hand in the editor are "
                    "not included - re-run with source='full_scan' for a complete comparison."
                )
            }
        ),
    }


def read_nodes_over_http(
    profile: str,
    pointers: Iterable[Pointer],
    *,
    app_id: str | None = None,
    app_version: str = "test",
    client: Any | None = None,
) -> dict[Pointer, Any]:
    """Read nodes through the editor's path API - no browser involved.

    ``/appeditor/load_multiple_paths`` returns nodes in the same ENCODED key space
    ``read_live_node`` reads through ``window.appquery._raw()`` (verified 2026-08-27 against
    ``api.bTGOS`` on mcp-test-app), which is what lets this stand in for a browser read.

    It reads the SERVER's persisted state, not the editor's in-memory tree. For a deploy diff -
    and for a savepoint taken before a write - server state is the right answer; the two differ
    only while a human has unsynced changes open in an editor tab.

    A pointer the version does not hold is left OUT of the result rather than mapped to None: for
    a diff, absent means "this path does not exist here", which is an addition or a removal, not a
    node whose value is null.

    NOT A SOURCE FOR A WRITE
    ------------------------
    The path API DROPS null-valued keys. Measured 2026-08-27: the node at ``api.bTGOj`` was
    written with ``%n``, ``optional`` and ``in_url`` all null
    (docs/capture-duplicate-workflow-custom-event.json) and reads back here without any of them.

    So never read a node through this and write it back: the round trip would silently delete
    every null-valued key, and /appeditor/write would answer 200. Use ``read_live_node``, which
    reads the editor's own ``_raw()``, whenever the node is going to be rewritten. This is safe
    for a deploy diff because both sides are read the same way, so the drop is symmetric - but
    comparing a browser-read node against one read here would manufacture divergences.

    ``for_rewrite = False`` marks that contract on the function itself.
    """

    paths = [list(pointer) for pointer in pointers]
    if not paths:
        return {}
    resolver = client
    if resolver is None:
        from bubble_mcp.context.path_api import BubblePathApiClient
        from bubble_mcp.sessions.store import load_session

        session = load_session(profile)
        if session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        resolver = BubblePathApiClient(
            app_id=str(app_id or session.app_id or ""),
            app_version=app_version,
            session=session,
        )

    _, results = resolver.resolve_multiple(paths)
    nodes: dict[Pointer, Any] = {}
    for path, result in zip(paths, results):
        kind = getattr(result, "type", "")
        dotted = ".".join(path)
        if kind == "error":
            # Never degrade a failed read into an absent node: a 401 or a dropped connection
            # would otherwise be reported as "every path was removed", or as an empty diff.
            raise PathReadError(f"reading {dotted} failed: {getattr(result, 'message', '')}")
        if kind in ("hash", "keys"):
            # resolve_multiple auto-resolves chunks; anything still unresolved here was not read.
            raise PathReadError(f"reading {dotted} returned an unresolved {kind}")
        if result.data is None:
            # Measured against the live editor: a path that does not exist answers data=None.
            continue
        nodes[tuple(path)] = result.data
    return nodes


# This reader loses null-valued keys; it must never feed a write. See the docstring.
read_nodes_over_http.for_rewrite = False
