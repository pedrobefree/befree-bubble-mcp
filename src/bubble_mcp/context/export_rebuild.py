"""Rebuild an importable ``.bubble`` file when Bubble's own export comes back incomplete or wrong.

Three measured problems make a downloaded export fail on import (production app, 2026-10-30):

1. The export leaves reusables out (the 14 MB file of a 346-reusable app carried two stubs).
   ``context/hydration.py`` already fills them from the editor path API.
2. Hydration stores them in the editor's SHRUNK key space (``%el``, ``%p``, ``%x``...), which the
   import does not expand: it escapes the keys again and the reusables arrive empty or nameless.
   ``editor_keys.decode_keys`` expands them back.
3. The export disagrees with the live editor on some nodes. When a node carries a field in both
   forms (``%ds`` and ``data_source``), the server-side export and the editor's decoded ``raw()``
   both let the stale long copy win, so API workflows lose their ``wf_name``/``parameters`` or come
   out with the wrong constraints, and some reusables come only as a stub. The source of truth is
   what the editor stores, ``_raw()`` (``execution/live_section_read.py``), decoded here with the
   shrunk-form-wins rule of ``editor_keys``; the editor's entry wins where it is complete and
   different.

This tool only READS Bubble. It writes one new local file and never overwrites the profile cache.
It also never invents a fix: the output reflects the live editor, nothing else.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from bubble_mcp.context.editor_keys import DecodeStats, decode_keys, percent_key_paths
from bubble_mcp.context.hydration import reusable_root_ids

REBUILD_SECTIONS = (
    "api",
    "element_definitions",
    "user_types",
    "option_sets",
    "styles",
    "settings",
    "pages",
)
# `_index` is NOT rebuilt: it is bookkeeping (id paths, issue lists) the editor recomputes as it
# works, and its live copy can carry holes the export never has (measured: an issues_sub list
# stored as a JSON string with three `null` items). The export's own `_index` is kept as-is.
# What makes an editor entry "complete" enough to replace the export's, per section. The editor
# returns null for deleted reusables and loose fragments (only `elements`, only `properties`) for
# half-loaded ones; none of those carry the marker, so none of them can displace or be added.
# None means any non-null value counts (settings has no marker key).
COMPLETENESS_KEY: dict[str, str | None] = {
    "api": "type",
    "element_definitions": "type",
    "styles": "type",
    "pages": "type",
    "user_types": "display",
    "option_sets": "display",
    "settings": None,
}
SAMPLE = 25


def strip_nulls(value: Any) -> Any:
    """Drop null-valued object keys, recursively.

    The editor's stored form spells some absent keys as null (every page carries
    ``is_mobile_view: null``; also ``style: null`` and null workflows) while the export never
    writes a null key at all (measured: zero in
    every section of a 116 MB export). Comparing and writing without them keeps a page that only
    differs by that from counting as changed.
    """

    if isinstance(value, dict):
        return {key: strip_nulls(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [strip_nulls(item) for item in value]
    return value


def canonical(value: Any) -> str:
    return json.dumps(strip_nulls(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def is_complete(section: str, entry: Any) -> bool:
    if entry is None:
        return False
    marker = COMPLETENESS_KEY.get(section)
    if marker is None:
        return True
    return isinstance(entry, dict) and marker in entry


def _label(section: str, key: str, entry: Any) -> dict[str, Any]:
    label: dict[str, Any] = {"id": key}
    if isinstance(entry, dict):
        name = entry.get("name")
        if not name and section == "api":
            properties = entry.get("properties")
            name = properties.get("wf_name") if isinstance(properties, dict) else None
        if name:
            label["name"] = name
    return label


def merge_section(
    section: str, exported: dict[str, Any], editor: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge one section; return the merged section and its report.

    Rules: equal entries stay; where the editor's entry is complete and differs, it replaces the
    export's (missing in the export counts as differing, so it is added); an incomplete editor
    entry (null, fragment, counter) never replaces or adds anything; an entry only the export has
    is kept and listed, since the tool reports what it cannot confirm instead of deleting it.
    """

    merged = dict(exported)
    replaced: list[dict[str, Any]] = []
    added: list[dict[str, Any]] = []
    export_only: list[str] = []
    editor_incomplete: list[str] = []
    ignored: list[str] = []
    same = 0
    for key, entry in exported.items():
        if key not in editor:
            export_only.append(key)
            continue
        live = editor[key]
        if not is_complete(section, live):
            editor_incomplete.append(key)
            continue
        if canonical(live) == canonical(entry):
            same += 1
            continue
        merged[key] = strip_nulls(live)
        replaced.append(_label(section, key, merged[key]))
    for key, live in editor.items():
        if key in exported:
            continue
        if not is_complete(section, live):
            ignored.append(key)
            continue
        merged[key] = strip_nulls(live)
        added.append(_label(section, key, merged[key]))
    report = {
        "same": same,
        "different": len(replaced),
        "export_only": len(export_only),
        "editor_only": len(added),
        "replaced": replaced,
        "added": added,
        "export_only_ids": export_only[:SAMPLE],
        "editor_incomplete": len(editor_incomplete),
        "editor_incomplete_ids": editor_incomplete[:SAMPLE],
        "editor_ignored": len(ignored),
        "editor_ignored_ids": ignored[:SAMPLE],
    }
    return merged, report


def decode_sections(data: dict[str, Any], names: Iterable[str]) -> DecodeStats:
    """Expand the shrunk keys of every section in ``names``, top-level keys included, in place.

    Top-level keys are shrunk too: a data type named ``event`` is stored as ``%e1``.
    """

    stats = DecodeStats()
    for name in names:
        section = data.get(name)
        if isinstance(section, dict):
            data[name] = decode_keys(section, stats=stats, path=(name,))[0]
    return stats


def editor_nameless_reusables(editor: dict[str, Any]) -> set[str]:
    """Complete reusables the live editor itself holds without a name.

    Measured: two reusables of a production app (``type: ReusableElement``) have no name in the
    editor either. Naming them would be inventing data, so validation reports them instead of
    failing.
    """

    section = editor.get("element_definitions")
    if not isinstance(section, dict):
        return set()
    return {
        key
        for key, entry in section.items()
        if is_complete("element_definitions", entry) and not entry.get("name")
    }


def validate_rebuilt(
    data: dict[str, Any],
    *,
    escaped_paths: set[Any] | None = None,
    editor_nameless: set[str] | None = None,
) -> dict[str, Any]:
    """Check the rebuilt export is importable: decoded sections, named and typed reusables.

    A reusable without a name fails, unless the live editor has it without a name too
    (``editor_nameless``): then the file reflects the editor and the id is only reported.
    """

    section = data.get("element_definitions")
    reusables = section if isinstance(section, dict) else {}
    rebuilt = {name: data[name] for name in REBUILD_SECTIONS if isinstance(data.get(name), dict)}
    percent = percent_key_paths(rebuilt, allowed=escaped_paths or set())
    nameless = [
        key
        for key, entry in reusables.items()
        if not (isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"])
    ]
    accepted = editor_nameless or set()
    missing_name = [key for key in nameless if key not in accepted]
    missing_type = [
        key for key, entry in reusables.items() if not (isinstance(entry, dict) and entry.get("type"))
    ]
    return {
        "ok": not percent and not missing_name and not missing_type and isinstance(section, dict),
        "reusables": len(reusables),
        "percent_keys": len(percent),
        "percent_key_paths": [list(path) for path in percent[:SAMPLE]],
        "missing_name": missing_name[:SAMPLE],
        "nameless_in_editor": [key for key in nameless if key in accepted][:SAMPLE],
        "missing_type": missing_type[:SAMPLE],
    }


def section_counts(data: dict[str, Any]) -> dict[str, int]:
    return {
        name: len(data[name])
        for name in REBUILD_SECTIONS
        if isinstance(data.get(name), dict)
    }


def build_rebuilt_export(
    exported: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    sections: Iterable[str] = REBUILD_SECTIONS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Decode both sides, compare with the editor snapshot and merge. Pure: no I/O.

    The snapshot holds the editor's ENCODED nodes (``_raw()``); they are decoded here with the
    same table and collision rule as the export, so both sides are compared in one key space.
    """

    data = dict(exported)
    # Only the export's reusables are shrunk (hydrated from the path API). Every other section of
    # the server-side export is already long-form, so a `%` key there is a literal (a style's
    # expression carries one) and decoding it would invent a `properties`.
    export_stats = decode_sections(data, ["element_definitions"])
    literal_paths = set(
        percent_key_paths(
            {name: data[name] for name in REBUILD_SECTIONS if name != "element_definitions" and isinstance(data.get(name), dict)}
        )
    )
    editor: dict[str, Any] = dict(snapshot.get("sections") or {})
    if isinstance(snapshot.get("pages"), dict):
        editor["pages"] = snapshot["pages"]
    editor_stats = decode_sections(editor, REBUILD_SECTIONS)
    report_sections: dict[str, Any] = {}
    for name in sections:
        live = editor.get(name)
        current = data.get(name)
        if not isinstance(live, dict) or not isinstance(current, dict):
            report_sections[name] = {"skipped": "not read from the editor" if not isinstance(live, dict) else "not in the export"}
            continue
        data[name], report_sections[name] = merge_section(name, current, live)
    nameless = editor_nameless_reusables(editor)
    escaped = export_stats.escaped_paths | editor_stats.escaped_paths | literal_paths
    report = {
        "decode": {"export": export_stats.to_dict(), "editor": editor_stats.to_dict()},
        "sections": report_sections,
        "refetched_reusables": list(snapshot.get("refetched_reusables") or []),
        "editor_errors": dict(snapshot.get("errors") or {}),
        "validation": validate_rebuilt(data, escaped_paths=escaped, editor_nameless=nameless),
        "counts": section_counts(data),
        "_validation_scope": {"escaped_paths": escaped, "editor_nameless": nameless},
    }
    return data, report


def write_rebuilt_export(
    data: dict[str, Any], output: Path, *, validation_scope: dict[str, Any]
) -> dict[str, Any]:
    """Write to a temp file, read it back, validate the re-read copy, then move it into place."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        reread = json.loads(temporary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        temporary.unlink(missing_ok=True)
        return {"ok": False, "error": "reread_failed", "message": str(exc)}
    validation = validate_rebuilt(reread, **validation_scope)
    counts_match = section_counts(reread) == section_counts(data)
    if not validation["ok"] or not counts_match:
        temporary.unlink(missing_ok=True)
        return {"ok": False, "error": "reread_validation_failed", "validation": validation, "counts_match": counts_match}
    temporary.replace(output)
    return {"ok": True, "path": str(output), "bytes": output.stat().st_size, "validation": validation}


Downloader = Callable[[str, str, str, Path], dict[str, Any]]
SnapshotReader = Callable[..., dict[str, Any]]


def _timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def rebuild_export(
    *,
    profile: str,
    app_id: str,
    app_version: str = "test",
    bubble_file: Path | None = None,
    output: Path | None = None,
    sections: Iterable[str] | None = None,
    execute: bool = False,
    work_dir: Path,
    protected_paths: Iterable[Path] = (),
    download: Downloader,
    read_snapshot: SnapshotReader,
) -> dict[str, Any]:
    """Run the whole rebuild. ``download`` and ``read_snapshot`` are the only I/O with Bubble."""

    wanted = list(dict.fromkeys(sections or REBUILD_SECTIONS))
    unknown = [name for name in wanted if name not in REBUILD_SECTIONS]
    if unknown:
        return {"ok": False, "error": "unknown_sections", "unknown": unknown, "allowed": list(REBUILD_SECTIONS)}
    stamp = _timestamp()
    target = (output or work_dir / f"{app_id}-{app_version}-rebuilt-{stamp}.bubble").expanduser()
    protected = {path.expanduser().resolve() for path in protected_paths}
    if bubble_file is not None:
        protected.add(bubble_file.expanduser().resolve())
    if target.resolve() in protected:
        return {"ok": False, "error": "output_would_overwrite_source", "output": str(target)}
    if target.exists():
        return {"ok": False, "error": "output_exists", "output": str(target)}

    if bubble_file is not None:
        source = bubble_file.expanduser()
        if not source.exists():
            return {"ok": False, "error": "bubble_file_missing", "bubble_file": str(source)}
        export_info: dict[str, Any] = {"source": "file", "path": str(source)}
    else:
        source = work_dir / f"{app_id}-{app_version}-export-{stamp}.bubble"
        export_info = {"source": "download", "path": str(source)}
        export_info.update(download(profile, app_id, app_version, source))
        if not export_info.get("ok", False):
            return {"ok": False, "error": "export_download_failed", "export": export_info}
    exported = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(exported, dict):
        return {"ok": False, "error": "export_not_an_object", "export": export_info}

    definitions = exported.get("element_definitions")
    reusable_ids = set(definitions) if isinstance(definitions, dict) else set()
    reusable_ids |= reusable_root_ids(exported)
    pages = exported.get("pages")
    snapshot = read_snapshot(
        sections=wanted,
        page_ids=sorted(pages) if isinstance(pages, dict) else [],
        reusable_ids=sorted(reusable_ids),
    )
    if snapshot.get("setup_error"):
        return {
            "ok": False,
            "error": snapshot["setup_error"],
            "message": snapshot.get("message"),
            "export": export_info,
        }
    data, report = build_rebuilt_export(exported, snapshot, sections=wanted)
    validation_scope = report.pop("_validation_scope")
    result: dict[str, Any] = {
        "ok": report["validation"]["ok"] and not report["editor_errors"],
        "executed": False,
        "profile": profile,
        "app_id": app_id,
        "app_version": app_version,
        "export": export_info,
        "output": str(target),
        **report,
    }
    if report["editor_errors"]:
        result["error"] = "editor_read_incomplete"
        result["next_user_action"] = (
            "Some editor reads failed (see editor_errors). Retry, or pass sections without the "
            "failing ones; nothing is written while a section could not be compared."
        )
        return result
    if not report["validation"]["ok"]:
        result["error"] = "validation_failed"
        result["next_user_action"] = (
            "The rebuilt export is not importable (see validation). Unknown '%' keys mean the key "
            "table is out of date: re-extract it (docs/export-rebuild.md)."
        )
        return result
    if not execute:
        result["next_user_action"] = (
            f"Preview only. Run again with execute=true and bubble_file='{export_info['path']}' to "
            "write the rebuilt file without downloading the export again."
        )
        return result
    written = write_rebuilt_export(data, target, validation_scope=validation_scope)
    result["executed"] = bool(written.get("ok"))
    result["write"] = written
    result["ok"] = bool(written.get("ok"))
    result["next_user_action"] = (
        f"Import {target} into the target Bubble app."
        if written.get("ok")
        else "The written file failed its read-back check and was removed; see write."
    )
    return result
