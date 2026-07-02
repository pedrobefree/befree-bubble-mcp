#!/usr/bin/env python3
# mypy: ignore-errors
# ruff: noqa
"""
Split and merge Bubble .bubble JSON exports into modules for version control.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_SECTIONS: Dict[str, Dict[str, str]] = {
    "api": {
        "mode": "split",
        "dir": "workflows",
        "group_by": "type",
        "index_label": "api",
    },
    "element_definitions": {
        "mode": "split",
        "dir": "element_definitions",
        "group_by": "type",
        "index_label": "type_name",
    },
    "pages": {
        "mode": "split",
        "dir": "pages",
        "derived_dirs": ["parts"],
    },
    "styles": {
        "mode": "split",
        "dir": "styles",
        "group_by": "type",
        "index_label": "type_name",
    },
    "option_sets": {
        "mode": "split",
        "dir": "option_sets",
        "derived_dirs": ["values"],
    },
    "user_types": {
        "mode": "split",
        "dir": "user_types",
        "name_from": "display",
        "derived_dirs": ["privacy_rules", "fields"],
    },
    "_index": {"mode": "single", "file": "_index.json"},
    "settings": {
        "mode": "split",
        "dir": "settings",
        "index_label": "key",
    },
    "mobile_views": {
        "mode": "split",
        "dir": "mobile_views",
        "group_by": "type",
        "index_label": "type_name",
    },
    "comments": {"mode": "single", "file": "comments.json"},
    "screenshot": {"mode": "single", "file": "screenshot.json"},
    "closest_ancestor_snapshots": {"mode": "single", "file": "closest_ancestor_snapshots.json"},
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump_json(path: Path, data: Any, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        if pretty:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        else:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))


def _pick_label(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("name", "display", "title", "label"):
            if key in item and isinstance(item[key], (str, int, float, bool)):
                return str(item[key])
    return ""


def _get_nested(obj: Any, path: str) -> Optional[Any]:
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _api_label(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    wf_name = props.get("wf_name") or props.get("name") or props.get("event_name")
    type_name = props.get("type") or item.get("type")
    if wf_name and type_name:
        return f"{type_name}:{wf_name}"
    if wf_name:
        return str(wf_name)
    if type_name:
        return str(type_name)
    return _pick_label(item)


def _type_name_label(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    type_name = item.get("type")
    name = item.get("name") or item.get("display")
    if type_name and name:
        return f"{type_name}:{name}"
    if name:
        return str(name)
    if type_name:
        return str(type_name)
    return _pick_label(item)

def _slugify(value: str) -> str:
    if not value:
        return ""
    raw = value.strip().lower()
    # Replace non-ascii with spaces, then slugify.
    raw = raw.encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return raw


def _safe_segment(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    raw = raw.replace("/", "-").replace("\\", "-")
    raw = re.sub(r"\s+", "_", raw)
    return raw


def _pick_dict(obj: Any, *keys: str) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    for key in keys:
        val = obj.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _split_path_tokens(raw_path: Any) -> List[str]:
    if isinstance(raw_path, list):
        return [str(p) for p in raw_path if str(p)]
    raw = str(raw_path or "").strip()
    if not raw:
        return []
    sep = "." if "." in raw else "/"
    return [p.strip() for p in raw.split(sep) if p.strip()]


def _collect_page_id_to_path(data: Dict[str, Any], page_id: str) -> Dict[str, str]:
    if not isinstance(data, dict):
        return {}
    idx = data.get("_index", {}) if isinstance(data.get("_index"), dict) else {}
    id_to_path = idx.get("id_to_path", {}) if isinstance(idx.get("id_to_path"), dict) else {}
    prefix = f"%p3.{page_id}"
    out: Dict[str, str] = {}
    for object_id, raw_path in id_to_path.items():
        normalized = ".".join(_split_path_tokens(raw_path))
        if not normalized:
            continue
        if normalized == prefix or normalized.startswith(prefix + "."):
            out[str(object_id)] = normalized
    return out


def _page_path_exists(page_obj: Dict[str, Any], raw_path: Any, page_id: str) -> bool:
    """
    Best-effort check whether an id_to_path entry resolves inside the page payload.
    Supports normalized keys (elements/workflows/properties) and raw tokens (%el/%wf/%p).
    """
    if not isinstance(page_obj, dict):
        return False
    parts = _split_path_tokens(raw_path)
    if len(parts) < 2:
        return False
    if parts[0] not in {"%p3", "pages"}:
        return False
    if str(parts[1]) != str(page_id):
        return False
    if len(parts) == 2:
        return True

    cur: Any = page_obj
    i = 2
    while i < len(parts):
        token = parts[i]
        if token in {"%el", "elements"}:
            if i + 1 >= len(parts):
                return False
            container = _pick_dict(cur, "elements", "%el")
            key = parts[i + 1]
            if key not in container:
                return False
            cur = container.get(key)
            i += 2
            continue
        if token in {"%wf", "workflows"}:
            if i + 1 >= len(parts):
                return False
            container = _pick_dict(cur, "workflows", "%wf")
            key = parts[i + 1]
            if key not in container:
                return False
            cur = container.get(key)
            i += 2
            continue
        if token in {"%p", "properties"}:
            nxt = _pick_dict(cur, "properties", "%p")
            if not nxt:
                return False
            cur = nxt
            i += 1
            continue
        if isinstance(cur, dict) and token in cur:
            cur = cur.get(token)
            i += 1
            continue
        return False
    return True


def _list_section_files(section_dir: Path) -> List[Path]:
    if not section_dir.exists():
        return []
    return sorted(
        [
            p
            for p in section_dir.rglob("*.json")
            if p.is_file() and not p.name.startswith("__")
        ]
    )


def _export_api_connector(out_dir: Path, data: Dict[str, Any], pretty: bool, force: bool) -> None:
    settings = data.get("settings", {})
    client_safe = settings.get("client_safe", {}) if isinstance(settings, dict) else {}
    secure = settings.get("secure", {}) if isinstance(settings, dict) else {}
    api2 = client_safe.get("apiconnector2")
    api2_secure = secure.get("apiconnector2")
    if not isinstance(api2, dict) or not api2:
        return

    base_dir = out_dir / "api_connector"
    secrets_dir = out_dir / "api_connector_secrets"
    base_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    if force:
        for p in base_dir.rglob("*.json"):
            if p.is_file():
                p.unlink()
        for p in secrets_dir.rglob("*.json"):
            if p.is_file():
                p.unlink()

    collections_index: Dict[str, str] = {}
    secrets_index: Dict[str, str] = {}
    used_folders: set[str] = set()

    api2_secure = api2_secure if isinstance(api2_secure, dict) else {}

    for collection_id, collection in api2.items():
        if not isinstance(collection, dict):
            continue
        human = collection.get("human") or collection.get("name") or collection_id
        folder = _slugify(str(human)) or _slugify(str(collection_id)) or str(collection_id)
        if folder in used_folders:
            folder = f"{folder}__{collection_id}"
        used_folders.add(folder)

        collection_dir = base_dir / folder
        calls_dir = collection_dir / "calls"
        calls_dir.mkdir(parents=True, exist_ok=True)

        # Collection metadata (exclude calls to avoid duplication)
        collection_meta = {k: v for k, v in collection.items() if k != "calls"}
        collection_meta["collection_id"] = collection_id
        if "human" not in collection_meta and collection.get("human"):
            collection_meta["human"] = collection.get("human")

        # Enrich shared headers with human-readable keys from secure data
        if isinstance(collection_meta.get("shared_headers"), dict):
            secure_headers = (
                api2_secure.get(collection_id, {}).get("shared_headers", {})
                if isinstance(api2_secure, dict)
                else {}
            )
            enhanced = {}
            for header_id, header_data in collection_meta["shared_headers"].items():
                entry = header_data if isinstance(header_data, dict) else {}
                entry = dict(entry)
                secure_entry = secure_headers.get(header_id) if isinstance(secure_headers, dict) else None
                if isinstance(secure_entry, dict) and secure_entry.get("key"):
                    entry["key"] = secure_entry.get("key")
                enhanced[header_id] = entry
            collection_meta["shared_headers"] = enhanced

        _dump_json(collection_dir / "collection.json", collection_meta, pretty)

        calls = collection.get("calls", {})
        calls_index: Dict[str, str] = {}
        used_call_files: set[str] = set()
        if isinstance(calls, dict):
            for call_id, call in calls.items():
                if not isinstance(call, dict):
                    continue
                call_name = call.get("name") or call_id
                filename = _slugify(str(call_name)) or _slugify(str(call_id)) or str(call_id)
                filename = f"{filename}.json"
                if filename in used_call_files:
                    filename = f"{Path(filename).stem}__{call_id}.json"
                used_call_files.add(filename)
                _dump_json(calls_dir / filename, call, pretty)
                calls_index[call_id] = str(call_name)

        _dump_json(calls_dir / "__index.json", calls_index, pretty)
        collections_index[collection_id] = str(human)

        # Secrets folder (if available)
        secure_collection = api2_secure.get(collection_id, {}) if isinstance(api2_secure, dict) else {}
        if isinstance(secure_collection, dict) and secure_collection:
            sec_collection_dir = secrets_dir / folder
            sec_calls_dir = sec_collection_dir / "calls"
            sec_calls_dir.mkdir(parents=True, exist_ok=True)
            # Collection metadata (secure)
            sec_meta = {k: v for k, v in secure_collection.items() if k != "calls"}
            sec_meta["collection_id"] = collection_id
            if "human" not in sec_meta and collection.get("human"):
                sec_meta["human"] = collection.get("human")
            _dump_json(sec_collection_dir / "collection.json", sec_meta, pretty)

            sec_calls = secure_collection.get("calls", {})
            sec_calls_index: Dict[str, str] = {}
            if isinstance(sec_calls, dict):
                for call_id, call in sec_calls.items():
                    if not isinstance(call, dict):
                        continue
                    call_name = calls_index.get(call_id) or call_id
                    filename = _slugify(str(call_name)) or _slugify(str(call_id)) or str(call_id)
                    filename = f"{filename}.json"
                    if filename in used_call_files:
                        filename = f"{Path(filename).stem}__{call_id}.json"
                    _dump_json(sec_calls_dir / filename, call, pretty)
                    sec_calls_index[call_id] = str(call_name)

            if sec_calls_index:
                _dump_json(sec_calls_dir / "__index.json", sec_calls_index, pretty)
            secrets_index[collection_id] = str(human)

    # Include secure collections missing from client_safe (rare)
    for collection_id, collection in api2_secure.items():
        if collection_id in collections_index:
            continue
        if not isinstance(collection, dict):
            continue
        human = collection.get("human") or collection.get("name") or collection_id
        folder = _slugify(str(human)) or _slugify(str(collection_id)) or str(collection_id)
        if folder in used_folders:
            folder = f"{folder}__{collection_id}"
        used_folders.add(folder)
        sec_collection_dir = secrets_dir / folder
        sec_calls_dir = sec_collection_dir / "calls"
        sec_calls_dir.mkdir(parents=True, exist_ok=True)
        sec_meta = {k: v for k, v in collection.items() if k != "calls"}
        sec_meta["collection_id"] = collection_id
        _dump_json(sec_collection_dir / "collection.json", sec_meta, pretty)
        sec_calls = collection.get("calls", {})
        sec_calls_index: Dict[str, str] = {}
        if isinstance(sec_calls, dict):
            for call_id, call in sec_calls.items():
                if not isinstance(call, dict):
                    continue
                filename = _slugify(str(call_id)) or str(call_id)
                filename = f"{filename}.json"
                _dump_json(sec_calls_dir / filename, call, pretty)
                sec_calls_index[call_id] = str(call_id)
        if sec_calls_index:
            _dump_json(sec_calls_dir / "__index.json", sec_calls_index, pretty)
        secrets_index[collection_id] = str(human)

    _dump_json(base_dir / "__index.json", collections_index, pretty)
    if secrets_index:
        _dump_json(secrets_dir / "__index.json", secrets_index, pretty)


def _export_custom_definitions(out_dir: Path, data: Dict[str, Any], pretty: bool, force: bool) -> None:
    """
    Export top-level CustomDefinition payload as a derived module.
    Keeps otherwise hidden definitions discoverable without changing manifest sections.
    """
    raw = data.get("CustomDefinition")
    if not isinstance(raw, dict) or not raw:
        return

    base_dir = out_dir / "custom_definitions"
    items_dir = base_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    if force:
        for p in items_dir.rglob("*.json"):
            if p.is_file():
                p.unlink()

    _dump_json(base_dir / "raw.json", raw, pretty)

    index_map: Dict[str, str] = {}
    for _key, value in raw.items():
        if not isinstance(value, dict):
            continue
        if str(value.get("type")) != "CustomDefinition":
            continue
        item_id = str(value.get("id") or "").strip()
        if not item_id:
            continue
        index_map[item_id] = _pick_label(value) or item_id
        _dump_json(items_dir / f"{item_id}.json", value, pretty)

    if index_map:
        _dump_json(items_dir / "__index.json", index_map, pretty)


def _infer_app_name_from_bubble_json(input_path: Path) -> tuple[Optional[str], Optional[str]]:
    if not input_path.exists() or not input_path.is_file():
        return None, None
    try:
        with input_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None, None

    if isinstance(data, dict):
        if isinstance(data.get("_id"), str) and data["_id"].strip():
            return data["_id"].strip(), "bubble:_id"
        if isinstance(data.get("appname"), str) and data["appname"].strip():
            return data["appname"].strip(), "bubble:appname"
        if isinstance(data.get("app_name"), str) and data["app_name"].strip():
            return data["app_name"].strip(), "bubble:app_name"
    return None, None


def _infer_app_name_from_bubble_file(input_path: Path) -> Optional[str]:
    if input_path.suffix == ".bubble" and input_path.stem:
        if input_path.stem.lower() == "app":
            return None
        return input_path.stem
    return None


def _detect_app_name(input_path: Path) -> tuple[str, str]:
    json_name, json_source = _infer_app_name_from_bubble_json(input_path)
    if json_name:
        return json_name, json_source or "bubble"

    env_name = os.getenv("BUBBLE_CLI_APPNAME")
    if env_name:
        return env_name, "env:BUBBLE_CLI_APPNAME"
    env_name = os.getenv("BUBBLE_APPNAME")
    if env_name:
        return env_name, "env:BUBBLE_APPNAME"

    inferred = _infer_app_name_from_bubble_file(input_path)
    if inferred:
        return inferred, f"filename:{input_path.name}"

    return "app", "default"


def _resolve_modules_dir(base_dir: Path, app_name: Optional[str]) -> Path:
    if (base_dir / "manifest.json").exists():
        return base_dir
    if app_name:
        candidate = base_dir / app_name
        if (candidate / "manifest.json").exists():
            return candidate
    return base_dir


def split_app(
    input_path: Path,
    out_dir: Path,
    app_name: Optional[str],
    force: bool,
    pretty: bool,
    write_index: bool,
) -> None:
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    if app_name:
        resolved_app = app_name
    else:
        resolved_app, _ = _detect_app_name(input_path)
    if out_dir.name != resolved_app:
        out_dir = out_dir / resolved_app

    if out_dir.exists():
        has_contents = any(out_dir.iterdir())
        if has_contents and not force:
            raise SystemExit(
                f"Output dir not empty: {out_dir} (use --force to overwrite)"
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    data = _load_json(input_path)
    top_order = list(data.keys())

    sections: Dict[str, Dict[str, str]] = {}
    for key, spec in DEFAULT_SECTIONS.items():
        if key in data:
            sections[key] = spec

    root: Dict[str, Any] = {}
    orders: Dict[str, List[str]] = {}
    filenames: Dict[str, Dict[str, str]] = {}

    for key, value in data.items():
        if key in sections:
            spec = sections[key]
            mode = spec["mode"]
            if mode == "single":
                _dump_json(out_dir / spec["file"], value, pretty)
            elif mode == "split":
                if not isinstance(value, dict):
                    raise SystemExit(f"Section '{key}' is not an object; cannot split.")
                section_dir = out_dir / spec["dir"]
                section_dir.mkdir(parents=True, exist_ok=True)
                if force:
                    for p in section_dir.rglob("*.json"):
                        if p.is_file():
                            p.unlink()
                orders[key] = list(value.keys())
                filenames[key] = {}
                index_data: Dict[str, str] = {}
                privacy_rules_index: Dict[str, str] = {}
                user_fields_index: Dict[str, str] = {}
                option_values_index: Dict[str, str] = {}
                page_parts_index: Dict[str, str] = {}
                group_indexes: Dict[str, Dict[str, str]] = {}
                used_filenames: set[str] = set()
                group_by = spec.get("group_by")
                index_label = spec.get("index_label")
                for item_id, item_value in value.items():
                    filename = f"{item_id}.json"
                    name_from = spec.get("name_from")
                    if name_from == "display":
                        label = _pick_label(item_value)
                        slug = _slugify(label)
                        if slug:
                            filename = f"{slug}.json"
                    group_segment = ""
                    if group_by:
                        group_value = _get_nested(item_value, group_by)
                        group_segment = _safe_segment(group_value) or "unknown"
                    if group_segment:
                        group_dir = section_dir / group_segment
                        group_dir.mkdir(parents=True, exist_ok=True)
                        rel_path = (Path(group_segment) / filename).as_posix()
                        path = group_dir / filename
                    else:
                        rel_path = Path(filename).as_posix()
                        path = section_dir / filename
                    if rel_path in used_filenames:
                        rel_path = f"{Path(rel_path).with_suffix('').as_posix()}__{item_id}.json"
                        path = section_dir / rel_path
                    used_filenames.add(rel_path)
                    filenames[key][item_id] = rel_path
                    _dump_json(path, item_value, pretty)
                    if index_label == "api":
                        label = _api_label(item_value)
                    elif index_label == "type_name":
                        label = _type_name_label(item_value)
                    elif index_label == "key":
                        label = str(item_id)
                    else:
                        label = _pick_label(item_value)
                    if write_index:
                        index_data[item_id] = label
                        if group_segment:
                            group_indexes.setdefault(group_segment, {})[item_id] = label
                        if key == "user_types" and isinstance(item_value, dict):
                            privacy_role = item_value.get("privacy_role")
                            if isinstance(privacy_role, dict) and privacy_role:
                                privacy_rules_dir = section_dir / "privacy_rules"
                                privacy_rules_dir.mkdir(parents=True, exist_ok=True)
                                privacy_filename = Path(rel_path).name
                                _dump_json(privacy_rules_dir / privacy_filename, privacy_role, pretty)
                                privacy_rules_index[item_id] = item_value.get("display") or label
                            fields = item_value.get("fields")
                            if isinstance(fields, dict) and fields:
                                fields_dir = section_dir / "fields"
                                fields_dir.mkdir(parents=True, exist_ok=True)
                                fields_filename = Path(rel_path).name
                                _dump_json(fields_dir / fields_filename, fields, pretty)
                                user_fields_index[item_id] = item_value.get("display") or label
                        if key == "option_sets" and isinstance(item_value, dict):
                            values = item_value.get("values")
                            if isinstance(values, dict) and values:
                                values_dir = section_dir / "values"
                                values_dir.mkdir(parents=True, exist_ok=True)
                                values_filename = Path(rel_path).name
                                _dump_json(values_dir / values_filename, values, pretty)
                                option_values_index[item_id] = item_value.get("display") or label
                        if key == "pages" and isinstance(item_value, dict):
                            parts_dir = section_dir / "parts" / Path(rel_path).stem
                            parts_dir.mkdir(parents=True, exist_ok=True)
                            properties_blob = _pick_dict(item_value, "properties", "%p")
                            elements_blob = _pick_dict(item_value, "elements", "%el")
                            workflows_blob = _pick_dict(item_value, "workflows", "%wf")
                            custom_states_blob = _pick_dict(item_value, "custom_states", "%custom_states")

                            _dump_json(parts_dir / "properties.json", properties_blob, pretty)
                            _dump_json(parts_dir / "elements.json", elements_blob, pretty)
                            _dump_json(parts_dir / "workflows.json", workflows_blob, pretty)
                            if custom_states_blob:
                                _dump_json(parts_dir / "custom_states.json", custom_states_blob, pretty)

                            page_id_to_path = _collect_page_id_to_path(data, str(item_id))
                            if page_id_to_path:
                                _dump_json(parts_dir / "id_to_path.json", page_id_to_path, pretty)
                                unresolved = {
                                    object_id: raw_path
                                    for object_id, raw_path in page_id_to_path.items()
                                    if not _page_path_exists(item_value, raw_path, str(item_id))
                                }
                                if unresolved:
                                    _dump_json(parts_dir / "id_to_path_unresolved.json", unresolved, pretty)
                            page_parts_index[item_id] = item_value.get("name") or label
                if write_index:
                    _dump_json(section_dir / "__index.json", index_data, pretty)
                    for group_segment, mapping in group_indexes.items():
                        _dump_json(section_dir / group_segment / "__index.json", mapping, pretty)
                    if key == "user_types" and privacy_rules_index:
                        privacy_rules_dir = section_dir / "privacy_rules"
                        privacy_rules_dir.mkdir(parents=True, exist_ok=True)
                        _dump_json(privacy_rules_dir / "__index.json", privacy_rules_index, pretty)
                    if key == "user_types" and user_fields_index:
                        fields_dir = section_dir / "fields"
                        fields_dir.mkdir(parents=True, exist_ok=True)
                        _dump_json(fields_dir / "__index.json", user_fields_index, pretty)
                    if key == "option_sets" and option_values_index:
                        values_dir = section_dir / "values"
                        values_dir.mkdir(parents=True, exist_ok=True)
                        _dump_json(values_dir / "__index.json", option_values_index, pretty)
                    if key == "pages" and page_parts_index:
                        parts_dir = section_dir / "parts"
                        parts_dir.mkdir(parents=True, exist_ok=True)
                        _dump_json(parts_dir / "__index.json", page_parts_index, pretty)
            else:
                raise SystemExit(f"Unknown mode for section '{key}': {mode}")
        else:
            root[key] = value

    manifest = {
        "format": "bubble-modules",
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "app_name": resolved_app,
        "source": str(input_path),
        "root": "root.json",
        "sections": sections,
        "orders": orders,
        "filenames": filenames,
        "top_order": top_order,
    }

    _dump_json(out_dir / "root.json", root, pretty)
    _dump_json(out_dir / "manifest.json", manifest, True)
    _export_api_connector(out_dir, data, pretty=pretty, force=force)
    _export_custom_definitions(out_dir, data, pretty=pretty, force=force)

    print(f"Split complete: {input_path} -> {out_dir}")
    print(f"Sections: {', '.join(sections.keys())}")


def merge_app(
    modules_dir: Path,
    output_path: Path,
    pretty: bool,
    strict: bool,
) -> None:
    manifest_path = modules_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = _load_json(manifest_path)
    if manifest.get("format") != "bubble-modules":
        raise SystemExit("Manifest format mismatch or missing.")

    root_path = modules_dir / manifest.get("root", "root.json")
    if not root_path.exists():
        raise SystemExit(f"Missing root file: {root_path}")

    root = _load_json(root_path)
    sections = manifest.get("sections", {})
    orders = manifest.get("orders", {})
    filenames = manifest.get("filenames", {})
    top_order = manifest.get("top_order") or []

    merged: Dict[str, Any] = {}
    keys_in_order = set()

    def load_section(key: str) -> Any:
        spec = sections[key]
        mode = spec["mode"]
        if mode == "single":
            path = modules_dir / spec["file"]
            if not path.exists():
                if strict:
                    raise SystemExit(f"Missing file for section '{key}': {path}")
                return {}
            return _load_json(path)
        if mode == "split":
            section_dir = modules_dir / spec["dir"]
            if not section_dir.exists():
                if strict:
                    raise SystemExit(f"Missing dir for section '{key}': {section_dir}")
                return {}
            order = orders.get(key, [])
            filename_map = filenames.get(key, {}) if isinstance(filenames, dict) else {}
            reverse_map = {v: k for k, v in filename_map.items() if isinstance(v, str)}
            seen = set()
            out: Dict[str, Any] = {}
            for item_id in order:
                filename = filename_map.get(item_id, f"{item_id}.json")
                path = section_dir / filename
                if not path.exists():
                    if strict:
                        raise SystemExit(
                            f"Missing item '{item_id}' for section '{key}': {path}"
                        )
                    continue
                out[item_id] = _load_json(path)
                seen.add(item_id)
            used_files = {filename_map.get(item_id, f"{item_id}.json") for item_id in seen}
            extra_files = [
                p
                for p in _list_section_files(section_dir)
                if p.relative_to(section_dir).as_posix() not in used_files
            ]
            ignore_dirs = set(spec.get("derived_dirs") or [])
            for path in extra_files:
                rel = path.relative_to(section_dir).as_posix()
                if ignore_dirs:
                    if any(part in ignore_dirs for part in rel.split("/")):
                        continue
                item_id = reverse_map.get(rel, path.stem)
                if item_id in out:
                    continue
                out[item_id] = _load_json(path)
            return out
        raise SystemExit(f"Unknown mode for section '{key}': {mode}")

    if top_order:
        for key in top_order:
            if key in sections:
                merged[key] = load_section(key)
            elif key in root:
                merged[key] = root[key]
            else:
                if strict:
                    raise SystemExit(f"Missing key '{key}' in root or sections.")
            keys_in_order.add(key)

    if not top_order:
        for key, value in root.items():
            merged[key] = value
            keys_in_order.add(key)
        for key in sections:
            if key in merged:
                continue
            merged[key] = load_section(key)
            keys_in_order.add(key)

    for key in root:
        if key not in keys_in_order:
            merged[key] = root[key]

    for key in sections:
        if key not in keys_in_order:
            merged[key] = load_section(key)

    _dump_json(output_path, merged, pretty=pretty)

    print(f"Merge complete: {modules_dir} -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split and merge Bubble .bubble JSON exports into modules."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    split_parser = subparsers.add_parser("split", help="Split app.bubble into modules")
    split_parser.add_argument(
        "--input",
        "-i",
        default="src/app.bubble",
        help="Path to app.bubble JSON",
    )
    split_parser.add_argument(
        "--out",
        "-o",
        default="src/bubble_modules",
        help="Output directory for modules",
    )
    split_parser.add_argument(
        "--app-name",
        default=None,
        help="App name for subfolder (defaults to .bubble _id, env, then filename)",
    )
    split_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output directory if it is not empty",
    )
    split_parser.add_argument(
        "--minify",
        action="store_true",
        help="Write module files in minified JSON",
    )
    split_parser.add_argument(
        "--no-index",
        action="store_true",
        help="Do not write __index.json files in split sections",
    )

    merge_parser = subparsers.add_parser("merge", help="Merge modules into app.bubble")
    merge_parser.add_argument(
        "--input",
        "-i",
        default="src/bubble_modules",
        help="Modules directory",
    )
    merge_parser.add_argument(
        "--app-name",
        default=None,
        help="App name subfolder (optional if input already points to the app folder)",
    )
    merge_parser.add_argument(
        "--out",
        "-o",
        default="src/app.bubble",
        help="Output path for merged app.bubble JSON",
    )
    merge_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write merged app.bubble in pretty JSON",
    )
    merge_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on missing files/keys referenced in manifest",
    )

    list_parser = subparsers.add_parser(
        "list-apps", help="List available app module folders"
    )
    list_parser.add_argument(
        "--input",
        "-i",
        default="src/bubble_modules",
        help="Modules root directory",
    )

    detect_parser = subparsers.add_parser(
        "detect-app", help="Detect app name from a .bubble file or env"
    )
    detect_parser.add_argument(
        "--input",
        "-i",
        default="src/app.bubble",
        help="Path to .bubble file",
    )
    detect_parser.add_argument(
        "--explain",
        action="store_true",
        help="Show the source used to detect the app name",
    )

    list_types_parser = subparsers.add_parser(
        "list-user-types", help="List user types (id -> display) from a .bubble file"
    )
    list_types_parser.add_argument(
        "--input",
        "-i",
        default="src/app.bubble",
        help="Path to .bubble file",
    )
    list_types_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of text",
    )

    args = parser.parse_args()

    if args.command == "split":
        split_app(
            input_path=Path(args.input),
            out_dir=Path(args.out),
            app_name=args.app_name,
            force=args.force,
            pretty=not args.minify,
            write_index=not args.no_index,
        )
        return

    if args.command == "merge":
        base_dir = Path(args.input)
        resolved_dir = _resolve_modules_dir(base_dir, args.app_name)
        if not (resolved_dir / "manifest.json").exists():
            # Try auto-resolve if there is exactly one app folder.
            candidates = [
                p
                for p in base_dir.iterdir()
                if p.is_dir() and (p / "manifest.json").exists()
            ] if base_dir.exists() else []
            if len(candidates) == 1:
                resolved_dir = candidates[0]
            else:
                raise SystemExit(
                    f"Missing manifest in {resolved_dir}. Provide --app-name or point --input to the app folder."
                )
        merge_app(
            modules_dir=resolved_dir,
            output_path=Path(args.out),
            pretty=args.pretty,
            strict=args.strict,
        )
        return

    if args.command == "list-apps":
        base_dir = Path(args.input)
        if not base_dir.exists():
            raise SystemExit(f"Modules root not found: {base_dir}")
        app_dirs = sorted(
            [
                p
                for p in base_dir.iterdir()
                if p.is_dir() and (p / "manifest.json").exists()
            ],
            key=lambda p: p.name.lower(),
        )
        if not app_dirs:
            print("No apps found.")
            return
        for app_dir in app_dirs:
            manifest = _load_json(app_dir / "manifest.json")
            app_name = manifest.get("app_name") or app_dir.name
            print(f"{app_name}\t{app_dir}")
        return

    if args.command == "detect-app":
        input_path = Path(args.input)
        name, source = _detect_app_name(input_path)
        if args.explain:
            print(f"{name}\t{source}")
        else:
            print(name)
        return

    if args.command == "list-user-types":
        input_path = Path(args.input)
        if not input_path.exists():
            raise SystemExit(f"Input file not found: {input_path}")
        try:
            with input_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Failed to read JSON: {exc}")
        user_types = data.get("user_types", {})
        if not isinstance(user_types, dict) or not user_types:
            print("No user types found.")
            return
        mapping = {
            type_id: (type_data.get("display") if isinstance(type_data, dict) else None)
            for type_id, type_data in user_types.items()
        }
        if args.json:
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
            return
        for type_id, display in sorted(mapping.items(), key=lambda x: x[0]):
            print(f"{type_id}\t{display or ''}")
        return

    raise SystemExit("Unknown command.")


if __name__ == "__main__":
    main()
