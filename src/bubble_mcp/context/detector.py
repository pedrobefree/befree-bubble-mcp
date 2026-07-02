"""Project context detection for standalone Bubble MCP."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.path_api import BubblePathApiClient, PathResult, decode_bubble_path
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.config import get_config_dir, load_settings
from bubble_mcp.sessions.store import BubbleSessionData, load_session


@dataclass(frozen=True)
class DetectionResult:
    ok: bool
    app_id: str
    source: str
    context_path: Path
    crawler_index_path: Path | None
    summary: dict[str, Any]
    attempts: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "app_id": self.app_id,
            "source": self.source,
            "context_path": str(self.context_path),
            "crawler_index_path": str(self.crawler_index_path) if self.crawler_index_path else None,
            "summary": self.summary,
            "attempts": self.attempts,
        }


def context_cache_dir() -> Path:
    return get_config_dir() / "contexts"


def default_context_path(profile: str, app_id: str) -> Path:
    safe_profile = _safe_name(profile or "default")
    safe_app = _safe_name(app_id)
    return context_cache_dir() / safe_profile / f"{safe_app}-context.json"


def default_crawler_index_path(profile: str, app_id: str) -> Path:
    safe_profile = _safe_name(profile or "default")
    safe_app = _safe_name(app_id)
    return context_cache_dir() / safe_profile / f"{safe_app}-crawler-index.json"


def detect_project_context(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str = "test",
    force: bool = False,
    output: Path | None = None,
    bubble_file: Path | None = None,
    consolelog_file: Path | None = None,
    include_id_to_path: bool = True,
) -> DetectionResult:
    """Detect and materialize project context using Aria's source priority."""

    attempts: list[dict[str, Any]] = []
    session = load_session(profile)
    settings = load_settings()
    configured_profile = settings.profiles.get(profile)
    resolved_app_id = str(
        app_id
        or (session.app_id if session else "")
        or (configured_profile.app_id if configured_profile else "")
    ).strip()
    if not resolved_app_id:
        raise ValueError("Context detection requires --app-id or a profile/session with app_id.")

    context_path = output or default_context_path(profile, resolved_app_id)
    if context_path.exists() and not force:
        context = load_context(context_path)
        return DetectionResult(
            ok=True,
            app_id=resolved_app_id,
            source="cached_context",
            context_path=context_path,
            crawler_index_path=None,
            summary=context.summary(),
            attempts=[{"source": "cached_context", "ok": True, "path": str(context_path)}],
        )

    if bubble_file:
        attempts.append({"source": "bubble_file", "path": str(bubble_file), "ok": bubble_file.exists()})
        if bubble_file.exists():
            return _persist_imported_context(
                bubble_file,
                kind="bubble",
                app_id=resolved_app_id,
                source="bubble_file",
                context_path=context_path,
                attempts=attempts,
            )

    if consolelog_file:
        attempts.append(
            {"source": "consolelog_file", "path": str(consolelog_file), "ok": consolelog_file.exists()}
        )
        if consolelog_file.exists():
            console_payload = _read_consolelog_file(consolelog_file)
            if console_payload is not None:
                return _persist_payload_context(
                    console_payload,
                    app_id=resolved_app_id,
                    source="consolelog_file",
                    context_path=context_path,
                    attempts=attempts,
                )
            try:
                return _persist_imported_context(
                    consolelog_file,
                    kind="bubble",
                    app_id=resolved_app_id,
                    source="consolelog_file",
                    context_path=context_path,
                    attempts=attempts,
                )
            except Exception as exc:
                attempts.append({"source": "consolelog_file", "ok": False, "reason": str(exc)})

    if session:
        downloaded = _try_download_bubble_export(
            session=session,
            app_id=resolved_app_id,
            app_version=app_version,
            attempts=attempts,
        )
        if downloaded is not None:
            return _persist_payload_context(
                downloaded,
                app_id=resolved_app_id,
                source="downloaded_bubble",
                context_path=context_path,
                attempts=attempts,
            )

        console_payload = _try_extract_consolelog_app(session=session, app_id=resolved_app_id, attempts=attempts)
        if console_payload is not None:
            return _persist_payload_context(
                console_payload,
                app_id=resolved_app_id,
                source="consolelog_app",
                context_path=context_path,
                attempts=attempts,
            )

        crawler_index = crawl_project_index(
            session=session,
            profile=profile,
            app_id=resolved_app_id,
            app_version=app_version,
            include_id_to_path=include_id_to_path,
        )
        crawler_path = default_crawler_index_path(profile, resolved_app_id)
        crawler_path.parent.mkdir(parents=True, exist_ok=True)
        crawler_path.write_text(json.dumps(crawler_index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        attempts.append(
            {
                "source": "editor_crawler",
                "ok": True,
                "path": str(crawler_path),
                "pages": len(crawler_index.get("pages") or []),
                "reusables": len(crawler_index.get("reusables") or []),
            }
        )
        context = import_context_artifact(crawler_path, kind="crawler")
        save_context(context, context_path)
        return DetectionResult(
            ok=True,
            app_id=resolved_app_id,
            source="editor_crawler",
            context_path=context_path,
            crawler_index_path=crawler_path,
            summary=context.summary(),
            attempts=attempts,
        )

    raise ValueError(
        "No local Bubble artifact and no captured session available. Run `bubble-mcp session login` first."
    )


def crawl_project_index(
    *,
    session: BubbleSessionData,
    profile: str,
    app_id: str,
    app_version: str,
    include_id_to_path: bool = True,
) -> dict[str, Any]:
    start = time.time()
    api = BubblePathApiClient(app_id=app_id, app_version=app_version, session=session)
    discovery_paths = [
        ["_index", "page_name_to_id"],
        ["_index", "page_name_to_path"],
        ["_index", "custom_name_to_id"],
        ["pages"],
        ["element_definitions"],
        ["CustomDefinition"],
        ["custom_definitions"],
        ["_index", "id_to_path"],
        ["plugin_special"],
    ]
    last_change, discovered = api.resolve_multiple(discovery_paths)

    page_name_to_id = _string_map(_data(discovered, 0))
    page_name_to_path = _string_map(_data(discovered, 1))
    id_to_path = _string_map(_data(discovered, 7)) if include_id_to_path else {}

    page_ids = set(page_name_to_id.values())
    page_ids.update(_keys_or_data_keys(discovered, 3))
    page_ids.update(_top_level_ids_from_id_to_path(id_to_path, ("%p3", "pages")))
    for page_id in sorted(page_ids):
        page_name_to_id.setdefault(page_id, page_id)
    page_paths_by_id = _top_level_path_by_id_from_id_to_path(id_to_path, ("%p3", "pages"))
    for name, page_id in list(page_name_to_id.items()):
        page_name_to_path.setdefault(name, page_paths_by_id.get(page_id) or f"%p3.{page_id}")

    custom_name_to_id = _custom_name_to_id(_data(discovered, 2))
    for reusable_id in (
        set(_keys_or_data_keys(discovered, 4))
        | set(_keys_or_data_keys(discovered, 5))
        | set(_keys_or_data_keys(discovered, 6))
        | set(_top_level_ids_from_id_to_path(id_to_path, ("%ed", "element_definitions", "CustomDefinition")))
    ):
        custom_name_to_id.setdefault(reusable_id, {"name": reusable_id, "custom_id": reusable_id})

    pages = [_crawl_page(api, name, page_id, page_name_to_path.get(name) or f"%p3.{page_id}") for name, page_id in page_name_to_id.items()]
    reusables = [_crawl_reusable(api, item["name"], item["custom_id"]) for item in custom_name_to_id.values()]
    backend_ids = api.list_backend_workflow_ids()
    backend_workflows = [_crawl_backend(api, backend_id) for backend_id in backend_ids]

    global_paths = [["user_types"], ["option_sets"], ["styles"]]
    _, global_results = api.resolve_multiple(global_paths)

    return {
        "appId": app_id,
        "profile": profile,
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lastChange": last_change,
        "sectionHashes": {},
        "pages": [item for item in pages if item],
        "reusables": [item for item in reusables if item],
        "backendWorkflows": [item for item in backend_workflows if item],
        "apiConnectorCalls": _api_connector_calls(_data(discovered, 8)),
        "pageIndex": dict(page_name_to_id),
        "reusableIndex": {item["name"]: item["custom_id"] for item in custom_name_to_id.values()},
        "apiIndex": {},
        "idToPath": id_to_path,
        "dataTypes": _obj(_result_data(global_results[0] if global_results else None)),
        "optionSets": _obj(_result_data(global_results[1] if len(global_results) > 1 else None)),
        "styles": _obj(_result_data(global_results[2] if len(global_results) > 2 else None)),
        "source": "full_crawl",
        "apiCallCount": 4 + len(page_name_to_id) * 3 + len(custom_name_to_id) * 3 + len(backend_ids),
        "durationMs": int((time.time() - start) * 1000),
    }


def _crawl_page(api: BubblePathApiClient, name: str, page_id: str, encoded_path: str) -> dict[str, Any] | None:
    segments = decode_bubble_path(encoded_path)
    _, results = api.resolve_multiple([segments, [*segments, "elements"], [*segments, "workflows"]])
    base = _obj(_result_data(results[0] if results else None))
    elements = _obj(_result_data(results[1] if len(results) > 1 else None)) or _obj(base.get("elements") or base.get("%el"))
    workflows = _obj(_result_data(results[2] if len(results) > 2 else None)) or _obj(base.get("workflows") or base.get("%wf"))
    return {
        "id": page_id,
        "name": str(base.get("%d") or base.get("%nm") or base.get("name") or name),
        "rootId": str(base.get("id") or base.get("root_id") or _obj(base.get("%p")).get("id") or "").strip() or None,
        "properties": _obj(base.get("%p") or base.get("properties")),
        "elements": elements,
        "workflows": workflows,
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _crawl_reusable(api: BubblePathApiClient, name: str, reusable_id: str) -> dict[str, Any] | None:
    for source_key in ("element_definitions", "CustomDefinition", "custom_definitions"):
        _, results = api.resolve_multiple(
            [[source_key, reusable_id], [source_key, reusable_id, "elements"], [source_key, reusable_id, "workflows"]]
        )
        base = _obj(_result_data(results[0] if results else None))
        if not base:
            continue
        elements = _obj(_result_data(results[1] if len(results) > 1 else None)) or _obj(base.get("elements") or base.get("%el"))
        workflows = _obj(_result_data(results[2] if len(results) > 2 else None)) or _obj(base.get("workflows") or base.get("%wf"))
        return {
            "id": reusable_id,
            "name": str(base.get("%d") or base.get("%nm") or base.get("name") or name),
            "sourceKey": source_key,
            "rootId": str(base.get("id") or base.get("root_id") or _obj(base.get("%p")).get("id") or "").strip() or None,
            "properties": _obj(base.get("%p") or base.get("properties")),
            "elements": elements,
            "workflows": workflows,
            "parameters": _obj(base.get("parameters")) or None,
            "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    return None


def _crawl_backend(api: BubblePathApiClient, backend_id: str) -> dict[str, Any] | None:
    result = api.resolve_path(["api", backend_id])
    raw = _obj(_result_data(result))
    if not raw:
        return None
    props = _obj(raw.get("properties") or raw.get("%p"))
    return {
        "id": backend_id,
        "name": str(raw.get("%d") or raw.get("name") or props.get("wf_name") or props.get("event_name") or backend_id),
        "trigger": str(raw.get("type") or props.get("event_type") or "unknown"),
        "properties": props,
        "actions": _obj(raw.get("actions") or raw.get("%actions")),
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _try_download_bubble_export(
    *,
    session: BubbleSessionData,
    app_id: str,
    app_version: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    # Bubble's export endpoint is not stable across plans/editor versions. Keep
    # this as a best-effort stage before falling back to the path crawler.
    _ = (session, app_id, app_version)
    attempts.append({"source": "downloaded_bubble", "ok": False, "reason": "no stable public export endpoint"})
    return None


def _try_extract_consolelog_app(
    *,
    session: BubbleSessionData,
    app_id: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    _ = (session, app_id)
    attempts.append({"source": "consolelog_app", "ok": False, "reason": "no captured console payload available"})
    return None


def extract_consolelog_app(text: str) -> dict[str, Any] | None:
    match = re.search(r"console\.log\(\s*app\s*\).*?({.*})", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _read_consolelog_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            app_payload = payload.get("app")
            if isinstance(app_payload, dict):
                return app_payload
            return payload
    except json.JSONDecodeError:
        pass
    return extract_consolelog_app(text)


def _persist_imported_context(
    path: Path,
    *,
    kind: str,
    app_id: str,
    source: str,
    context_path: Path,
    attempts: list[dict[str, Any]],
) -> DetectionResult:
    context = import_context_artifact(path, kind=kind)
    save_context(context, context_path)
    return DetectionResult(
        ok=True,
        app_id=app_id,
        source=source,
        context_path=context_path,
        crawler_index_path=None,
        summary=context.summary(),
        attempts=attempts,
    )


def _persist_payload_context(
    payload: dict[str, Any],
    *,
    app_id: str,
    source: str,
    context_path: Path,
    attempts: list[dict[str, Any]],
) -> DetectionResult:
    temp_path = context_path.with_suffix(f".{source}.json")
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    context = import_context_artifact(temp_path, kind="bubble")
    save_context(context, context_path)
    return DetectionResult(
        ok=True,
        app_id=app_id,
        source=source,
        context_path=context_path,
        crawler_index_path=None,
        summary=context.summary(),
        attempts=attempts,
    )


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip()) or "default"


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _result_data(result: PathResult | None) -> Any:
    return result.data if result and result.type == "data" else None


def _data(results: list[PathResult], index: int) -> Any:
    return _result_data(results[index]) if len(results) > index else {}


def _string_map(value: Any) -> dict[str, str]:
    return {str(key): str(item) for key, item in _obj(value).items() if str(item).strip()}


def _keys_or_data_keys(results: list[PathResult], index: int) -> list[str]:
    if len(results) <= index:
        return []
    result = results[index]
    if result.type == "keys":
        return [str(item) for item in result.keys or []]
    return list(_obj(result.data).keys()) if result.type == "data" else []


def _custom_name_to_id(value: Any) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for key, item in _obj(value).items():
        if isinstance(item, dict):
            custom_id = str(item.get("custom_id") or item.get("id") or key).strip()
            name = str(item.get("name") or item.get("%nm") or key).strip()
        else:
            custom_id = str(item or key).strip()
            name = str(key).strip()
        if custom_id:
            out[name] = {"name": name, "custom_id": custom_id}
    return out


def _top_level_ids_from_id_to_path(id_to_path: dict[str, str], prefixes: tuple[str, ...]) -> list[str]:
    ids: set[str] = set()
    for encoded_path in id_to_path.values():
        for prefix in prefixes:
            if encoded_path.startswith(f"{prefix}."):
                candidate = encoded_path[len(prefix) + 1 :].split(".")[0]
                if candidate:
                    ids.add(candidate)
    return sorted(ids)


def _top_level_path_by_id_from_id_to_path(id_to_path: dict[str, str], prefixes: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for encoded_path in id_to_path.values():
        for prefix in prefixes:
            if encoded_path.startswith(f"{prefix}."):
                candidate = encoded_path[len(prefix) + 1 :].split(".")[0]
                if candidate:
                    out.setdefault(candidate, f"{prefix}.{candidate}")
    return out


def _api_connector_calls(value: Any) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for collection_id, collection in _obj(value).items():
        collection_obj = _obj(collection)
        collection_name = str(collection_obj.get("%nm") or collection_obj.get("name") or collection_id)
        for call_id, call in _obj(collection_obj.get("calls") or collection_obj.get("api_calls")).items():
            call_obj = _obj(call)
            calls.append(
                {
                    "collectionId": str(collection_id),
                    "collectionName": collection_name,
                    "callId": str(call_id),
                    "callName": str(call_obj.get("%nm") or call_obj.get("name") or call_id),
                }
            )
    return calls
