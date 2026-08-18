"""Deterministic hydration of sparse reusable definitions.

Bubble's ``/appeditor/export`` endpoint stopped inlining reusable element
definitions for large apps: the export carries every reusable id in
``_index.id_to_path`` but leaves ``element_definitions`` almost empty, so the
module split can only emit ``_inferred_from_index`` skeletons.

This module fills that gap without any LLM involvement: it fetches each
missing definition straight from the editor's path API
(``/appeditor/load_multiple_paths``) — the same authoritative source the
Bubble editor itself uses — and merges the payloads into the export in place.
Requests are batched, results are merged deterministically, and failures are
reported per reusable id.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from bubble_mcp.context.path_api import BubblePathApiClient, PathResult
from bubble_mcp.sessions.store import BubbleSessionData

REUSABLE_INDEX_ROOTS = {"%ed", "element_definitions", "CustomDefinition", "custom_definitions"}
MATERIAL_SOURCE_KEYS = ("element_definitions", "%ed", "CustomDefinition", "custom_definitions")
# The editor path API only accepts the raw token, not the readable alias, as the
# first path segment. Resolving ["%ed", <id>] returns the whole definition subtree
# (properties, %el, %wf) inlined, so a single fetch per reusable is enough; the
# element/workflow fetches below are only a safety net for partially-chunked nodes.
FETCH_SOURCE_KEY = "%ed"
FALLBACK_FETCH_SOURCE_KEYS = ("CustomDefinition", "custom_definitions")
DEFAULT_BATCH_SIZE = 10


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _result_data(result: PathResult | None) -> Any:
    return result.data if result is not None and result.type == "data" else None


def reusable_root_ids(data: dict[str, Any]) -> set[str]:
    """Reusable definition ids that own a top-level ``%ed.<id>`` index entry.

    An id that appears only inside deeper paths (e.g. ``%ed.<id>.%wf.…``) but has
    no length-2 root entry is a stale/orphaned reference: the editor path API has
    no definition node for it and returns null. Excluding those keeps hydration
    from chasing entries that can never resolve.
    """
    id_to_path = _obj(_obj(data.get("_index")).get("id_to_path"))
    root_ids: set[str] = set()
    for encoded_path in id_to_path.values():
        parts = [part for part in str(encoded_path or "").split(".") if part]
        if len(parts) == 2 and parts[0] in REUSABLE_INDEX_ROOTS and parts[1] != "length":
            root_ids.add(parts[1])
    return root_ids


def orphan_reusable_ids(data: dict[str, Any]) -> list[str]:
    """Ids seen only in deep ``%ed.<id>.…`` paths with no resolvable root node."""
    id_to_path = _obj(_obj(data.get("_index")).get("id_to_path"))
    roots = reusable_root_ids(data)
    deep_ids: set[str] = set()
    for encoded_path in id_to_path.values():
        parts = [part for part in str(encoded_path or "").split(".") if part]
        if len(parts) > 2 and parts[0] in REUSABLE_INDEX_ROOTS and parts[1] != "length":
            deep_ids.add(parts[1])
    return sorted(deep_ids - roots)


def material_reusable_ids(data: dict[str, Any]) -> set[str]:
    material_ids: set[str] = set()
    for source_key in MATERIAL_SOURCE_KEYS:
        for key, value in _obj(data.get(source_key)).items():
            if key != "length" and isinstance(value, dict) and value:
                material_ids.add(str(key))
    return material_ids


def index_only_reusable_ids(data: dict[str, Any]) -> list[str]:
    """Real reusable ids known to _index.id_to_path but missing a material payload."""
    return sorted(reusable_root_ids(data) - material_reusable_ids(data))


def _has_key(record: dict[str, Any], *keys: str) -> bool:
    return any(key in record for key in keys)


def _merge_definition_parts(
    base: Any,
    elements: Any,
    workflows: Any,
) -> dict[str, Any] | None:
    if not isinstance(base, dict) or not base:
        return None
    definition = dict(base)
    if isinstance(elements, dict) and elements and not _has_key(definition, "%el", "elements"):
        definition["%el"] = elements
    if isinstance(workflows, dict) and workflows and not _has_key(definition, "%wf", "workflows"):
        definition["%wf"] = workflows
    return definition


def hydrate_reusable_definitions_payload(
    data: dict[str, Any],
    api: BubblePathApiClient,
    *,
    ids: list[str] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Fetch missing reusable definitions and merge them into ``data`` in place."""
    targets = [str(item) for item in ids] if ids else index_only_reusable_ids(data)
    hydrated: list[str] = []
    failed: dict[str, str] = {}
    started = time.time()
    if not targets:
        return {
            "requested": 0,
            "hydrated": 0,
            "failed": {},
            "hydrated_ids": [],
            "duration_ms": 0,
        }

    section = data.get("element_definitions")
    if not isinstance(section, dict):
        section = {}
        data["element_definitions"] = section

    batch = max(int(batch_size or DEFAULT_BATCH_SIZE), 1)
    for offset in range(0, len(targets), batch):
        chunk = targets[offset : offset + batch]
        paths = [[FETCH_SOURCE_KEY, reusable_id] for reusable_id in chunk]
        try:
            _, results = api.resolve_multiple(paths)
        except Exception as exc:
            for reusable_id in chunk:
                failed[reusable_id] = str(exc)
            continue
        for position, reusable_id in enumerate(chunk):
            base = _result_data(results[position]) if position < len(results) else None
            definition = base if isinstance(base, dict) and base else None
            if definition is None or not _has_key(definition, "%el", "elements", "%wf", "workflows"):
                definition = _fetch_definition_fallback(api, reusable_id, base=definition)
            if definition is None:
                failed[reusable_id] = "path API returned no definition payload"
                continue
            section[reusable_id] = definition
            hydrated.append(reusable_id)

    return {
        "requested": len(targets),
        "hydrated": len(hydrated),
        "failed": failed,
        "hydrated_ids": hydrated,
        "duration_ms": int((time.time() - started) * 1000),
    }


def _fetch_definition_fallback(
    api: BubblePathApiClient,
    reusable_id: str,
    *,
    base: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    # Safety net for definitions whose element/workflow subtrees came back as a
    # separate chunk instead of inlined in the base node. Fetch %el and %wf
    # explicitly and merge them onto whatever base we already have.
    try:
        _, results = api.resolve_multiple(
            [
                [FETCH_SOURCE_KEY, reusable_id],
                [FETCH_SOURCE_KEY, reusable_id, "%el"],
                [FETCH_SOURCE_KEY, reusable_id, "%wf"],
            ]
        )
    except Exception:
        return base if isinstance(base, dict) and base else None
    fetched_base = _result_data(results[0]) if results else None
    resolved_base = fetched_base if isinstance(fetched_base, dict) and fetched_base else base
    definition = _merge_definition_parts(
        resolved_base,
        _result_data(results[1]) if len(results) > 1 else None,
        _result_data(results[2]) if len(results) > 2 else None,
    )
    return definition


def hydrate_bubble_export_file(
    path: Path,
    *,
    session: BubbleSessionData,
    app_id: str,
    app_version: str,
    ids: list[str] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Hydrate a sparse .bubble export file in place and update its meta sidecar."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Bubble export must be a JSON object.")

    api = BubblePathApiClient(app_id=app_id, app_version=app_version, session=session)
    report = hydrate_reusable_definitions_payload(data, api, ids=ids, batch_size=batch_size)
    if report["hydrated"]:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _record_hydration_meta(path, report, app_version=app_version)
    report["file"] = str(path)
    report["remaining_index_only"] = len(index_only_reusable_ids(data))
    report["orphan_index_refs"] = len(orphan_reusable_ids(data))
    return report


def _record_hydration_meta(path: Path, report: dict[str, Any], *, app_version: str) -> None:
    meta_path = path.with_name(path.name + ".meta.json")
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            meta = {}
    meta["hydration"] = {
        "source": "editor_path_api",
        "app_version": app_version,
        "hydrated": report["hydrated"],
        "failed": len(report["failed"]),
        "hydrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass
