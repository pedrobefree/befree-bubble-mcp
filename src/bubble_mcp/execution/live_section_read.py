"""Read whole app sections, decoded, out of the running Bubble editor.

``live_node_read`` reads one node in the editor's SHRUNK form (``_child``/``_raw``), which is what
``/appeditor/write`` wants. Rebuilding an importable ``.bubble`` needs the opposite: the LONG form
the export and the import use. The editor gives that through the public accessors, ``child()`` and
``raw()``: ``root.child('<section>').raw()`` returns the section already expanded, for ``api``,
``element_definitions``, ``user_types``, ``option_sets``, ``styles``, ``settings`` and ``_index``.

Measured on the live editor:

* ``child_names()`` on the root throws ("loading the entire app object is disabled"), and on
  ``pages`` it throws too, so pages are read one at a time by id (``child('pages').child(id)``).
* Every section first throws ``NotReadyError`` in a fresh headless page: the tree loads lazily.
  ``element_definitions`` took about 10s to arrive on a 346-reusable app. The ready gate below
  primes each node with ``ensure_loading()`` and keeps polling until ``raw()`` stops throwing.
* ``element_definitions`` comes back with ``null`` for deleted reusables, loose fragments (an entry
  with only ``elements`` or only ``properties``) and a ``length`` counter. They are returned as-is;
  deciding what to keep is ``context/export_rebuild.py``'s job.

The browser plumbing (persistent profile, cookie seeding, editor navigation, identity check in the
same evaluation, retries on a reinitializing page) is ``live_node_read``'s, reused unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Sequence

from bubble_mcp.execution.live_node_read import (
    DEFAULT_READ_TIMEOUT_SEC,
    BrowserProfileMissing,
    NotLoggedIn,
    PlaywrightMissing,
    _evaluate_with_retries,
    _open_editor_page,
)

EDITOR_SECTIONS = (
    "api",
    "element_definitions",
    "user_types",
    "option_sets",
    "styles",
    "settings",
    "_index",
)

# Reads one decoded node at a path and returns it (None when absent); raises when it cannot.
SectionReader = Callable[[Sequence[str]], Any]

SETUP_ERRORS: dict[type[BaseException], str] = {
    PlaywrightMissing: "playwright_missing",
    BrowserProfileMissing: "browser_profile_missing",
    NotLoggedIn: "not_logged_in",
}


class EditorSetupFailed(RuntimeError):
    """The editor page could not be opened at all, so no path can be read."""

    def __init__(self, error: str, message: str) -> None:
        self.error = error
        super().__init__(message)


def _walk(path: Sequence[str]) -> str:
    return "".join(
        f"  node = node ? node.child({json.dumps(str(part))}) : node;\n"
        "  try { if (node && typeof node.ensure_loading === 'function') node.ensure_loading(); } "
        "catch (primeError) {}\n"
        for part in path
    )


def build_section_ready_script(path: Sequence[str], app_id: str) -> str:
    """Return the gate that is true once the node at ``path`` stops throwing NotReadyError.

    Same contract as ``live_node_read.build_pointer_ready_script`` (app-aware, NotReadyError
    detected structurally because it is not a real Error in the editor), on the public accessors.
    """

    return (
        "() => {\n"
        "  try {\n"
        "  const root = window.appquery.app().json;\n"
        f"  if (root.appname() !== {json.dumps(app_id)}) return false;\n"
        "  let node = root;\n"
        f"{_walk(path)}"
        "  if (node) node.raw();\n"
        "  return true;\n"
        "  } catch (error) {\n"
        "    const isNotReady = Boolean(error && typeof error === 'object' && (\n"
        "      'not_ready_key' in error ||\n"
        "      (error.constructor && error.constructor.name === 'NotReadyError')));\n"
        "    return !isNotReady;\n"
        "  }\n"
        "}\n"
    )


def build_section_script(path: Sequence[str]) -> str:
    """Return the script that reads the decoded node at ``path`` plus the app it came from."""

    return (
        "() => {\n"
        "  const root = window.appquery.app().json;\n"
        "  let node = root;\n"
        f"{_walk(path)}"
        "  const raw = node ? node.raw() : null;\n"
        "  return {appname: root.appname(), app_version: root.app_version(), "
        "node: raw === undefined ? null : raw};\n"
        "}\n"
    )


def read_editor_snapshot(
    reader: SectionReader,
    *,
    sections: Iterable[str],
    page_ids: Iterable[str] = (),
    reusable_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Read ``sections``, then each page, then any reusable the bulk read left incomplete.

    ``page_ids`` are the pages to read one by one; the editor's own ``_index.page_name_to_id`` is
    added to them when ``_index`` was read, so a page the export lost is still found.
    ``reusable_ids`` are the ids the export knows about: when the bulk ``element_definitions`` read
    did not bring one complete (lazy loading), it is read again on its own path.
    """

    wanted = list(dict.fromkeys(sections))
    snapshot: dict[str, Any] = {"sections": {}, "pages": {}, "refetched_reusables": [], "errors": {}}
    for section in [name for name in wanted if name != "pages"]:
        try:
            snapshot["sections"][section] = reader([section])
        except EditorSetupFailed:
            raise
        except Exception as exc:  # noqa: BLE001 - one failed section is reported, not fatal
            snapshot["errors"][section] = f"{type(exc).__name__}: {exc}"

    definitions = snapshot["sections"].get("element_definitions")
    if isinstance(definitions, dict):
        for reusable_id in dict.fromkeys(str(item) for item in reusable_ids):
            current = definitions.get(reusable_id)
            if isinstance(current, dict) and "type" in current:
                continue
            try:
                definitions[reusable_id] = reader(["element_definitions", reusable_id])
            except EditorSetupFailed:
                raise
            except Exception as exc:  # noqa: BLE001
                snapshot["errors"][f"element_definitions.{reusable_id}"] = f"{type(exc).__name__}: {exc}"
                continue
            snapshot["refetched_reusables"].append(reusable_id)

    if "pages" in wanted:
        ids = [str(item) for item in page_ids]
        index = snapshot["sections"].get("_index")
        name_to_id = index.get("page_name_to_id") if isinstance(index, dict) else None
        if isinstance(name_to_id, dict):
            ids.extend(str(value) for value in name_to_id.values() if isinstance(value, str))
        for page_id in dict.fromkeys(ids):
            try:
                snapshot["pages"][page_id] = reader(["pages", page_id])
            except EditorSetupFailed:
                raise
            except Exception as exc:  # noqa: BLE001
                snapshot["errors"][f"pages.{page_id}"] = f"{type(exc).__name__}: {exc}"
    return snapshot


def read_live_editor_snapshot(
    *,
    profile: str,
    app_id: str,
    app_version: str,
    sections: Iterable[str] = EDITOR_SECTIONS + ("pages",),
    page_ids: Iterable[str] = (),
    reusable_ids: Iterable[str] = (),
    headless: bool = True,
    timeout_sec: int = DEFAULT_READ_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Open the profile's editor once, headless by default, and read a snapshot through it."""

    context = _open_editor_page(
        profile=profile,
        app_id=app_id,
        app_version=app_version,
        headless=headless,
        timeout_sec=timeout_sec,
    )
    try:
        page = context.__enter__()
    except tuple(SETUP_ERRORS) as exc:
        raise EditorSetupFailed(SETUP_ERRORS[type(exc)], str(exc)) from exc

    def reader(path: Sequence[str]) -> Any:
        try:
            envelope = _evaluate_with_retries(
                page,
                ready_script=build_section_ready_script(path, app_id),
                script=build_section_script(path),
                expected_app_id=app_id,
                expected_app_version=app_version,
                timeout_sec=timeout_sec,
            )
        except NotLoggedIn as exc:
            # The page bounced off the app mid-read: every later path would fail the same way.
            raise EditorSetupFailed("not_logged_in", str(exc)) from exc
        return envelope.get("node") if isinstance(envelope, dict) else None

    try:
        return read_editor_snapshot(
            reader, sections=sections, page_ids=page_ids, reusable_ids=reusable_ids
        )
    finally:
        context.__exit__(None, None, None)
