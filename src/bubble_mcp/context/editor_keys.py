"""Decode the Bubble editor's shrunk key space back to the long key names an import understands.

The editor keeps its tree with shrunk keys (``%el``, ``%p``, ``%x``, ``%nm``, ...) and the path
API returns nodes in that form, so a reusable hydrated from it (see ``context/hydration.py``) is
stored shrunk. Bubble's own ``.bubble`` import does NOT expand them: measured on a real import, it
escapes every ``%`` key once more (``%el`` lands as ``%%el``) and the reusable arrives empty. The
export the import expects uses the long names (``elements``, ``properties``, ``type``, ``name``).

The table is the editor's own ``mapping`` object from ``lib-browser/lang/shrink.js`` (bundled in
``edit.js``), versioned in ``data/editor_key_table.json`` as ``long -> abbreviation``. The editor
expands a key like this (``expand`` in that module): a key starting with ``%`` loses that ``%``;
what is left is looked up as an abbreviation and, when it is one, replaced by the long name. So a
long key that itself starts with ``%`` is stored escaped as ``%%<key>`` and expands to ``%<key>``.

Two deliberate differences from the editor's ``expand_object``:

* Collisions. A node can carry the same key in both forms (a hydrated ``%x`` next to an exported
  ``type``). The editor just lets the later entry win; here both are merged recursively and the
  shrunk value wins on a conflict, because the shrunk form is what the editor itself last wrote.
  Every collision and every conflicting leaf is counted, so the report shows it.
* Unknown abbreviations. The editor would turn ``%zz`` into ``zz``. A shrunk key the table does not
  know only appears when Bubble added an abbreviation after the table was extracted, and ``zz`` would
  then be the wrong long name. It is kept as-is and reported, which fails validation and points at
  re-extracting the table instead of silently writing a wrong key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ESCAPE = "%"
KEY_TABLE_PATH = Path(__file__).with_name("data") / "editor_key_table.json"
# The table is an object literal assigned to `mapping` in the editor bundle. bgcolor:"bgc" has been
# in it for as long as the table has existed, so it anchors the right literal among the thousands of
# other `mapping=` assignments a minified bundle carries.
_BUNDLE_MAPPING_RE = re.compile(r"\bmapping\s*=\s*\{([^{}]*\bbgcolor\s*:\s*\"bgc\"[^{}]*)\}")
_BUNDLE_PAIR_RE = re.compile(r"([A-Za-z_$][\w$]*|\"[^\"]*\")\s*:\s*\"([^\"]*)\"")

Path_ = tuple[str | int, ...]


@lru_cache(maxsize=1)
def load_key_table() -> dict[str, str]:
    """Return the versioned ``long name -> abbreviation`` table."""

    loaded = json.loads(KEY_TABLE_PATH.read_text(encoding="utf-8"))
    mapping = loaded.get("mapping") if isinstance(loaded, dict) else None
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(f"{KEY_TABLE_PATH} carries no 'mapping' object.")
    return {str(key): str(value) for key, value in mapping.items()}


def reverse_key_table(mapping: dict[str, str] | None = None) -> dict[str, str]:
    """Return ``abbreviation -> long name``, refusing a table two names share an abbreviation in."""

    table = load_key_table() if mapping is None else mapping
    reverse: dict[str, str] = {}
    for long_name, short in table.items():
        if short in reverse:
            raise ValueError(
                f"Abbreviation '{short}' is mapped to both '{reverse[short]}' and '{long_name}'."
            )
        reverse[short] = long_name
    return reverse


def extract_key_table_from_bundle(bundle_text: str) -> dict[str, str]:
    """Pull the ``mapping`` object literal out of the editor bundle source.

    Raises ``ValueError`` when the anchor is missing, which is what a renamed or moved table looks
    like; see docs/export-rebuild.md for where to look next.
    """

    match = _BUNDLE_MAPPING_RE.search(bundle_text)
    if match is None:
        raise ValueError(
            "No `mapping={... bgcolor:\"bgc\" ...}` object literal in this bundle. The editor "
            "table has moved: search the editor's JS bundles for bgcolor:\"bgc\"."
        )
    pairs = _BUNDLE_PAIR_RE.findall(match.group(1))
    mapping = {key.strip('"'): value for key, value in pairs}
    reverse_key_table(mapping)
    return mapping


@dataclass
class DecodeStats:
    """What decoding changed, for the report and for validation."""

    decoded_keys: int = 0
    escaped_keys: int = 0
    collisions: int = 0
    collision_conflicts: int = 0
    unknown_keys: dict[str, int] = field(default_factory=dict)
    escaped_paths: set[Path_] = field(default_factory=set)
    collision_paths: list[Path_] = field(default_factory=list)

    def to_dict(self, *, sample: int = 20) -> dict[str, Any]:
        return {
            "decoded_keys": self.decoded_keys,
            "escaped_keys": self.escaped_keys,
            "collisions": self.collisions,
            "collision_conflicts": self.collision_conflicts,
            "unknown_keys": dict(sorted(self.unknown_keys.items())),
            "collision_paths": [list(path) for path in self.collision_paths[:sample]],
        }


def _merge_collision(shrunk: Any, long_form: Any, stats: DecodeStats) -> Any:
    if isinstance(shrunk, dict) and isinstance(long_form, dict):
        merged = dict(long_form)
        for key, value in shrunk.items():
            merged[key] = _merge_collision(value, merged[key], stats) if key in merged else value
        return merged
    if shrunk != long_form:
        stats.collision_conflicts += 1
    return shrunk


def _decode(value: Any, path: Path_, reverse: dict[str, str], stats: DecodeStats) -> Any:
    if isinstance(value, list):
        return [_decode(item, path + (index,), reverse, stats) for index, item in enumerate(value)]
    if not isinstance(value, dict):
        return value
    long_form: dict[str, Any] = {}
    expanded: dict[str, Any] = {}
    for key, item in value.items():
        if key.startswith(ESCAPE + ESCAPE):
            literal = key[1:]
            stats.escaped_keys += 1
            stats.escaped_paths.add(path + (literal,))
            long_form[literal] = _decode(item, path + (literal,), reverse, stats)
        elif key.startswith(ESCAPE) and key[1:] in reverse:
            name = reverse[key[1:]]
            stats.decoded_keys += 1
            expanded[name] = _decode(item, path + (name,), reverse, stats)
        else:
            if key.startswith(ESCAPE):
                stats.unknown_keys[key] = stats.unknown_keys.get(key, 0) + 1
            long_form[key] = _decode(item, path + (key,), reverse, stats)
    decoded = dict(long_form)
    for name, item in expanded.items():
        if name in decoded:
            stats.collisions += 1
            stats.collision_paths.append(path + (name,))
            decoded[name] = _merge_collision(item, decoded[name], stats)
        else:
            decoded[name] = item
    return decoded


def decode_keys(
    value: Any,
    *,
    mapping: dict[str, str] | None = None,
    stats: DecodeStats | None = None,
    path: Path_ = (),
) -> tuple[Any, DecodeStats]:
    """Expand every shrunk key under ``value``; return the decoded copy and what changed."""

    collected = stats if stats is not None else DecodeStats()
    return _decode(value, path, reverse_key_table(mapping), collected), collected


def percent_key_paths(value: Any, *, allowed: set[Path_] | None = None, path: Path_ = ()) -> list[Path_]:
    """Paths of keys still starting with ``%``, except the escaped literals listed in ``allowed``."""

    found: list[Path_] = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = path + (key,)
            if key.startswith(ESCAPE) and here not in (allowed or set()):
                found.append(here)
            found.extend(percent_key_paths(item, allowed=allowed, path=here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(percent_key_paths(item, allowed=allowed, path=path + (index,)))
    return found
