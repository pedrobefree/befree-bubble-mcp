"""Diagnostics for .bubble export files.

Answers two recurring support questions without guessing:

- Why did the module split emit ``_inferred_from_index`` skeletons for
  reusable definitions? (The export itself lacks the payloads — this report
  shows exactly which top-level sections exist and where reusable ids appear.)
- Which branch/version produced the cached export? (Read from the
  ``.meta.json`` provenance sidecar written at download time, plus any
  version-like keys embedded in the payload.)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REUSABLE_SOURCE_KEYS = (
    "element_definitions",
    "%ed",
    "CustomDefinition",
    "custom_definitions",
)
REUSABLE_INDEX_ROOTS = {"%ed", "element_definitions", "CustomDefinition", "custom_definitions"}


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _split_path(raw_path: Any) -> list[str]:
    return [part for part in str(raw_path or "").split(".") if part]


def _looks_like_reusable_definition(value: Any) -> bool:
    record = _obj(value)
    if not record:
        return False
    type_name = str(record.get("%x") or record.get("type") or "")
    if type_name in {"CustomDefinition", "ReusableElement"}:
        return True
    props = _obj(record.get("%p") or record.get("properties"))
    has_name = bool(props.get("%nm") or props.get("name"))
    has_tree = isinstance(record.get("%el") or record.get("elements"), dict) or isinstance(
        record.get("%wf") or record.get("workflows"), dict
    )
    return has_name and has_tree


def _display_names_by_id(app: dict[str, Any]) -> dict[str, str]:
    raw_index = _obj(_obj(app.get("_index")).get("custom_name_to_id"))
    names: dict[str, str] = {}
    for index_name, raw in raw_index.items():
        if isinstance(raw, dict):
            reusable_id = str(raw.get("custom_id") or raw.get("id") or index_name).strip()
            display = str(
                raw.get("display") or raw.get("%d") or raw.get("name") or raw.get("%nm") or index_name
            ).strip()
        else:
            reusable_id = str(raw or index_name).strip()
            display = str(index_name).strip()
        if reusable_id and display:
            names.setdefault(reusable_id, display)
    return names


def _summarize_top_level(app: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for key, value in app.items():
        entry: dict[str, Any] = {"type": type(value).__name__}
        if isinstance(value, (dict, list)):
            entry["entries"] = len(value)
        elif isinstance(value, (str, int, float, bool)):
            entry["value"] = value if not isinstance(value, str) or len(value) <= 120 else value[:120]
        summary[key] = entry
    return summary


def _version_hints(app: dict[str, Any]) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    for key, value in app.items():
        if "version" in key.lower() and isinstance(value, (str, int, float, bool)):
            hints[key] = value
    settings = _obj(app.get("settings"))
    for scope_name in ("client_safe", "secure"):
        for key, value in _obj(settings.get(scope_name)).items():
            if "version" in key.lower() and isinstance(value, (str, int, float, bool)):
                hints[f"settings.{scope_name}.{key}"] = value
    return hints


def inspect_bubble_export(path: Path, *, sample_limit: int = 20) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Bubble export must be a JSON object.")

    app = raw
    wrapped = False
    app_markers = ("pages", "element_definitions", "_index", "user_types", "styles")
    inner = raw.get("app")
    if isinstance(inner, dict) and not any(key in raw for key in app_markers):
        app = inner
        wrapped = True

    id_to_path = _obj(_obj(app.get("_index")).get("id_to_path"))
    index_reusable_ids: set[str] = set()
    for encoded_path in id_to_path.values():
        parts = _split_path(encoded_path)
        if len(parts) >= 2 and parts[0] in REUSABLE_INDEX_ROOTS and parts[1] != "length":
            index_reusable_ids.add(parts[1])

    material_by_source: dict[str, int] = {}
    material_ids: set[str] = set()
    for source_key in REUSABLE_SOURCE_KEYS:
        entries = {
            str(key): value
            for key, value in _obj(app.get(source_key)).items()
            if key != "length" and isinstance(value, dict)
        }
        if entries:
            material_by_source[source_key] = len(entries)
            material_ids.update(entries)

    names = _display_names_by_id(app)
    index_only = sorted(index_reusable_ids - material_ids)
    known_roots = set(REUSABLE_SOURCE_KEYS) | {
        "api",
        "pages",
        "styles",
        "option_sets",
        "user_types",
        "settings",
        "mobile_views",
        "comments",
        "screenshot",
        "closest_ancestor_snapshots",
        "_index",
    }
    suspect_roots: dict[str, int] = {}
    for key, value in app.items():
        if key in known_roots or not isinstance(value, dict):
            continue
        hits = sum(1 for child in value.values() if _looks_like_reusable_definition(child))
        if hits:
            suspect_roots[key] = hits

    meta_path = path.with_name(path.name + ".meta.json")
    meta: dict[str, Any] | None = None
    if meta_path.exists():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError):
            meta = None

    material_count = len(material_ids)
    index_only_count = len(index_only)
    sparse = index_only_count > 0 and index_only_count >= material_count

    return {
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "wrapped_app_payload": wrapped,
        "provenance": meta,
        "app_id": str(app.get("_id") or app.get("appname") or app.get("app_name") or "") or None,
        "version_hints": _version_hints(app),
        "top_level": _summarize_top_level(app),
        "reusables": {
            "material_by_source": material_by_source,
            "material_count": material_count,
            "index_reusable_count": len(index_reusable_ids),
            "index_only_count": index_only_count,
            "named_in_index_count": len(names),
            "index_only_sample": [
                {"id": reusable_id, "name": names.get(reusable_id)} for reusable_id in index_only[:sample_limit]
            ],
            "sparse_export": sparse,
        },
        "reusable_payloads_under_unexpected_roots": suspect_roots,
        "verdict": (
            "sparse: reusable definitions exist only in _index.id_to_path; the export payload "
            "is missing element_definitions content (check export version/branch and source file)"
            if sparse
            else "ok: reusable definition payloads are present in the export"
            if material_count
            else "no reusable definitions found in this export"
        ),
    }
