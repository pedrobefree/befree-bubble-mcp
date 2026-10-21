"""Which editor page has to be open for a given pointer to be readable.

The Bubble editor loads its tree lazily and per page. On a large app that means opening
``page?name=index`` initializes the index page plus everything app-wide (``api``, ``styles``,
``option_sets``) and leaves a reusable's subtree - ``%ed.<key>`` - unprimed, so a pointer into
it keeps answering ``NotReadyError`` until the read times out, and no timeout is long enough
because the node is not loading at all. That is the failure this module exists to prevent.

How much of the tree one page primes is NOT constant across apps, and the threshold has not
been measured. On a small app the index primes everything: on ``mcp-test-app`` (5 pages, 1
reusable) both ``%p3.<other page>`` and ``%ed.<key>`` read fine with the URL pinned to
``index``, so choosing the page changes nothing there. The observed failure comes from
``orana-digital-system``, and this module has not yet been run against it - see
``TEST_PLAN_raw_node_edit.md`` section 3B.

So the page cannot be assumed constant. It is a function of the pointer, which is what this
module computes: the leading bucket says WHICH KIND of context the pointer lives in (``%ed`` reusable,
``%p3`` page), the segment after it is that context's KEY, and the editor URL wants the
context's NAME. That last step is a lookup against the profile's cached export, which is why
this lives beside ``live_node_read`` rather than inside it: the read itself stays a pure
browser driver and the cache access is here, injectable, and testable without a browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import quote

from bubble_mcp.context.detector import default_bubble_export_path, default_bubble_modules_dir


INDEX_EDITOR_URL_TEMPLATE = "https://bubble.io/page?name=index&id={app_id}&version={app_version}"
PAGE_EDITOR_URL_TEMPLATE = "https://bubble.io/page?name={name}&id={app_id}&version={app_version}"
REUSABLE_EDITOR_URL_TEMPLATE = (
    "https://bubble.io/page?type=reusable&name={name}&id={app_id}&tab=elements&version={app_version}"
)

# Both spellings of each bucket are accepted because both reach this code in practice: pointers
# built from a live ``_raw()`` read are encoded (``%ed``/``%p3``), pointers built from a decoded
# ``.bubble`` export are not (``element_definitions``/``pages``).
CONTEXT_BUCKETS: dict[str, str] = {
    "%ed": "reusable",
    "element_definitions": "reusable",
    "%p3": "page",
    "pages": "page",
}

MODULE_INDEX_BUCKETS: dict[str, str] = {"reusable": "element_definitions", "page": "pages"}

NameResolver = Callable[[str, str, str, str], str | None]


def pointer_context(pointer: Sequence[str]) -> tuple[str, str] | None:
    """Return ``(kind, key)`` for the context a pointer lives in, or ``None`` for app-wide ones.

    ``None`` is the answer for ``api``, ``styles``, ``option_sets`` and friends: those load with
    the app itself on whatever editor page is open, so no particular page has to be chosen for
    them. It is also the answer for a bare bucket (``["%ed"]``), which names no single context.
    """

    segments = [str(part) for part in pointer]
    if len(segments) < 2:
        return None
    kind = CONTEXT_BUCKETS.get(segments[0])
    if not kind or not segments[1]:
        return None
    return kind, segments[1]


def editor_url(
    app_id: str, app_version: str, *, kind: str | None = None, name: str | None = None
) -> str:
    """Return the editor URL that opens ``name`` (a page or a reusable) for this app.

    With no ``kind``/``name`` this is the app's default editor page (``index``), which is the
    right page for app-wide pointers and the only page this module used to know about.
    """

    if kind and name:
        template = (
            REUSABLE_EDITOR_URL_TEMPLATE if kind == "reusable" else PAGE_EDITOR_URL_TEMPLATE
        )
        return template.format(name=quote(str(name), safe=""), app_id=app_id, app_version=app_version)
    return INDEX_EDITOR_URL_TEMPLATE.format(app_id=app_id, app_version=app_version)


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        # A missing, unreadable or half-written cache is a reason to try the next source, not
        # to fail the read: the caller falls back to the key itself and the editor reports a
        # page that does not exist, which is a far clearer failure than a corrupt-cache stack.
        return None


def _name_from_module_index(profile: str, app_id: str, kind: str, key: str) -> str | None:
    bucket = MODULE_INDEX_BUCKETS.get(kind)
    if not bucket:
        return None
    index = _load_json(default_bubble_modules_dir(profile, app_id) / bucket / "__index.json")
    if not isinstance(index, dict):
        return None
    raw = index.get(key)
    if not isinstance(raw, str) or not raw:
        return None
    # Reusables are indexed as "<Type>:<Name>" (e.g. "CustomDefinition:New Client Form"); pages
    # are indexed by name alone. Split on the FIRST colon only - a name may contain more.
    if kind == "reusable" and ":" in raw:
        return raw.split(":", 1)[1].strip() or None
    return raw.strip() or None


def _name_from_export(profile: str, app_id: str, kind: str, key: str) -> str | None:
    bucket = MODULE_INDEX_BUCKETS.get(kind)
    if not bucket:
        return None
    export = _load_json(default_bubble_export_path(profile, app_id))
    if not isinstance(export, dict):
        return None
    container = export.get(bucket)
    if not isinstance(container, dict):
        return None
    node = container.get(key)
    if not isinstance(node, dict):
        return None
    name = node.get("name")
    return str(name).strip() or None if isinstance(name, str) else None


def resolve_context_name(profile: str, app_id: str, kind: str, key: str) -> str | None:
    """Return the editor-facing NAME of the page or reusable ``key``, from the profile's cache.

    The split module index is tried first because it is a few kilobytes keyed exactly this way,
    where the ``.bubble`` export is tens of megabytes and has to be parsed whole. Both are the
    same data; only the cost differs.
    """

    return _name_from_module_index(profile, app_id, kind, key) or _name_from_export(
        profile, app_id, kind, key
    )


def editor_url_for_pointer(
    pointer: Sequence[str],
    *,
    profile: str,
    app_id: str,
    app_version: str,
    resolver: NameResolver = resolve_context_name,
) -> str:
    """Return the editor URL whose page primes ``pointer``'s subtree.

    When the context's name cannot be resolved the KEY is used as the name rather than falling
    back to ``index``. Reading is not thereby made to work, but the failure changes from "this
    pointer never became ready" after a full timeout - which reads as a broken pointer - to a
    page that plainly does not exist, which points at the stale cache that actually caused it.
    """

    context = pointer_context(pointer)
    if context is None:
        return editor_url(app_id, app_version)
    kind, key = context
    return editor_url(app_id, app_version, kind=kind, name=resolver(profile, app_id, kind, key) or key)
