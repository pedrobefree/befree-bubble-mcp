"""Project context detection for standalone Bubble MCP."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path
from typing import Any

import requests

from bubble_mcp.context.composition import COMPLETE, PARTIAL, merge_project_contexts, with_provenance
from bubble_mcp.context.importers import (
    context_from_bubble_export,
    context_from_bubble_payload,
    context_from_crawler_payload,
)
from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.context.path_api import BubblePathApiClient, PathResult, decode_bubble_path
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.config import BubbleProfile, get_config_dir, load_settings, save_settings, with_profile
from bubble_mcp.sessions.store import BubbleSessionData, load_session
from bubble_mcp.vendor.bubble_modules import split_app

MAX_CONSOLE_APP_CHARS = 64 * 1024 * 1024
CONSOLE_APP_WAIT_MS = 15_000


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
        metadata = self.summary.get("metadata")
        safe_metadata = metadata if isinstance(metadata, dict) else {}
        provenance = safe_metadata.get("provenance")
        safe_provenance = provenance if isinstance(provenance, dict) else None
        return {
            "ok": self.ok,
            "app_id": self.app_id,
            "source": self.source,
            "completeness": str(safe_provenance.get("completeness") or "") if safe_provenance else None,
            "provenance": safe_provenance,
            "context_path": str(self.context_path),
            "crawler_index_path": str(self.crawler_index_path) if self.crawler_index_path else None,
            "summary": self.summary,
            "attempts": self.attempts,
        }


def _resolve_app_version(
    requested: str,
    configured_profile: BubbleProfile | None,
    session: BubbleSessionData | None,
) -> str:
    """Resolve the export/crawl app version: explicit arg > profile > session > test."""
    requested = str(requested or "").strip()
    if requested:
        return requested
    if configured_profile and str(configured_profile.app_version or "").strip():
        return str(configured_profile.app_version).strip()
    if session and str(session.app_version or "").strip():
        return str(session.app_version).strip()
    return "test"


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


def default_consolelog_app_path(profile: str, app_id: str) -> Path:
    safe_profile = _safe_name(profile or "default")
    safe_app = _safe_name(app_id)
    return context_cache_dir() / safe_profile / f"{safe_app}-consolelog-app.json"


def default_bubble_export_path(profile: str, app_id: str) -> Path:
    safe_profile = _safe_name(profile or "default")
    safe_app = _safe_name(app_id)
    return context_cache_dir() / safe_profile / f"{safe_app}.bubble"


def default_bubble_modules_dir(profile: str, app_id: str) -> Path:
    safe_profile = _safe_name(profile or "default")
    safe_app = _safe_name(app_id)
    return context_cache_dir() / safe_profile / "bubble_modules" / safe_app


def refresh_bubble_export(*, profile: str, app_id: str, app_version: str) -> Path:
    """Download a fresh authoritative .bubble export without browser fallback."""

    session = load_session(profile)
    if session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")
    attempts: list[dict[str, Any]] = []
    downloaded = _try_download_bubble_export(
        session=session,
        app_id=app_id,
        app_version=app_version,
        profile=profile,
        attempts=attempts,
    )
    if downloaded is None:
        raise ValueError(
            "A fresh .bubble export is required for permanent data type deletion; "
            "the authenticated export download failed."
        )
    _split_bubble_export(
        downloaded,
        app_id=app_id,
        modules_dir=default_bubble_modules_dir(profile, app_id),
        attempts=attempts,
    )
    _save_profile_app_json_path(
        profile=profile,
        app_id=app_id,
        app_json_path=downloaded,
    )
    return downloaded


def detect_project_context(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str = "",
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

    requested_app_version = str(app_version or "").strip()
    app_version = _resolve_app_version(requested_app_version, configured_profile, session)
    attempts.append(
        {
            "source": "app_version_resolution",
            "ok": True,
            "app_version": app_version,
            "requested": requested_app_version or None,
        }
    )

    canonical_context_path = default_context_path(profile, resolved_app_id)
    if canonical_context_path.exists() and not force:
        context = load_context(canonical_context_path)
        result_path = _copy_cached_context_output(canonical_path=canonical_context_path, output=output)
        return DetectionResult(
            ok=True,
            app_id=resolved_app_id,
            source="cached_context",
            context_path=result_path,
            crawler_index_path=None,
            summary=_safe_detection_summary(context),
            attempts=[{"source": "cached_context", "ok": True, "path": str(canonical_context_path)}],
        )

    bubble_candidates = _candidate_bubble_files(
        explicit=bubble_file,
        configured=configured_profile.app_json_path if configured_profile else None,
        settings_dir=settings.config_dir,
        profile=profile,
        app_id=resolved_app_id,
    )
    if force and session and bubble_file is None:
        # A forced refresh must never be satisfied by the previously downloaded
        # export cache, no matter which candidate slot it entered through
        # (profile_app_json_path or local_bubble_candidate) — otherwise a stale
        # cache silently wins and the fresh download never happens.
        default_export = default_bubble_export_path(profile, resolved_app_id).expanduser().resolve()
        bubble_candidates = [
            candidate
            for candidate in bubble_candidates
            if not (
                isinstance(candidate.get("path"), Path)
                and candidate["path"].expanduser().resolve() == default_export
            )
        ]
    bubble_context: BubbleProjectContext | None = None
    bubble_source = ""
    for candidate in bubble_candidates:
        attempts.append(
            {
                "source": candidate["source"],
                "path": str(candidate["path"]),
                "ok": candidate["path"].exists(),
            }
        )
        if candidate["path"].exists():
            try:
                bubble_context = context_from_bubble_export(candidate["path"])
            except Exception as exc:
                attempts.append({"source": candidate["source"], "ok": False, "reason": str(exc)})
                continue
            bubble_source = str(candidate["source"])
            break

    if bubble_context is None and session:
        downloaded = _try_download_bubble_export(
            session=session,
            app_id=resolved_app_id,
            app_version=app_version,
            profile=profile,
            attempts=attempts,
        )
        if downloaded is not None:
            _split_bubble_export(
                downloaded,
                app_id=resolved_app_id,
                modules_dir=default_bubble_modules_dir(profile, resolved_app_id),
                attempts=attempts,
            )
            _save_profile_app_json_path(
                profile=profile,
                app_id=resolved_app_id,
                app_json_path=downloaded,
            )
            bubble_context = context_from_bubble_export(downloaded)
            bubble_source = "downloaded_bubble"

    consolelog_candidates = _candidate_consolelog_files(
        explicit=consolelog_file,
        configured=configured_profile.consolelog_json_path if configured_profile else None,
        settings_dir=settings.config_dir,
        profile=profile,
        app_id=resolved_app_id,
    )
    console_payload, console_source, console_path = _first_console_payload(
        consolelog_candidates,
        attempts=attempts,
    )

    if bubble_context is not None:
        sources = [bubble_source]
        result_source = bubble_source
        if console_payload is not None:
            bubble_complement = context_from_bubble_payload(
                console_payload,
                str(console_path or console_source),
            )
            if _has_usable_console_context(bubble_complement):
                bubble_context = merge_project_contexts(
                    bubble_context,
                    bubble_complement,
                    source=f"{bubble_source}+{console_source}",
                )
                sources.append(console_source)
                result_source = f"{bubble_source}+{console_source}"
            else:
                attempts.append(
                    {
                        "source": "console_context_validation",
                        "ok": False,
                        "reason": "console app payload contained no usable schema or definitions",
                    }
                )
        complete_context = with_provenance(
            bubble_context,
            primary_source=bubble_source,
            sources=sources,
            completeness=COMPLETE,
            bubble_export_available=True,
        )
        return _context_detection_result(
            complete_context,
            app_id=resolved_app_id,
            source=result_source,
            canonical_path=canonical_context_path,
            output=output,
            crawler_index_path=None,
            attempts=attempts,
        )

    if console_payload is None and session:
        console_payload = _try_extract_consolelog_app(
            session=session,
            profile=profile,
            app_id=resolved_app_id,
            attempts=attempts,
        )
        if console_payload is not None:
            console_source = "consolelog_app"
            console_path = default_consolelog_app_path(profile, resolved_app_id)

    crawler_index: dict[str, Any] | None = None
    crawler_path: Path | None = None
    if session:
        try:
            crawler_index = crawl_project_index(
                session=session,
                profile=profile,
                app_id=resolved_app_id,
                app_version=app_version,
                include_id_to_path=include_id_to_path,
            )
        except Exception as exc:
            attempts.append({"source": "editor_crawler", "ok": False, "reason": str(exc)})
        if crawler_index is not None and _needs_editor_network_capture(crawler_index):
            network_index = _try_capture_editor_network_index(
                profile=profile,
                app_id=resolved_app_id,
                app_version=app_version,
                attempts=attempts,
            )
            if network_index is not None:
                crawler_index = _merge_crawler_indexes(crawler_index, network_index)
        if crawler_index is not None:
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

    console_context = (
        context_from_bubble_payload(console_payload, str(console_path or console_source))
        if console_payload is not None
        else None
    )
    crawler_context = (
        context_from_crawler_payload(crawler_index, crawler_path or Path("editor_crawler"))
        if crawler_index is not None
        else None
    )
    if console_context is not None and not _has_usable_console_context(console_context):
        attempts.append(
            {
                "source": "console_context_validation",
                "ok": False,
                "reason": "console app payload contained no usable schema or definitions",
            }
        )
        console_context = None
    if crawler_context is not None and not _has_usable_crawler_topology(crawler_context):
        attempts.append(
            {
                "source": "crawler_context_validation",
                "ok": False,
                "reason": "editor crawler payload contained no usable topology",
            }
        )
        crawler_context = None

    if console_context is not None and crawler_context is not None:
        composed = merge_project_contexts(
            console_context,
            crawler_context,
            source=f"{console_source}+editor_crawler",
            complement_is_topology=True,
        )
        composed = with_provenance(
            composed,
            primary_source=console_source,
            sources=[console_source, "editor_crawler"],
            completeness=COMPLETE,
            bubble_export_available=False,
        )
        return _context_detection_result(
            composed,
            app_id=resolved_app_id,
            source=f"{console_source}+editor_crawler",
            canonical_path=canonical_context_path,
            output=output,
            crawler_index_path=crawler_path,
            attempts=attempts,
        )

    partial_context = console_context or crawler_context
    if partial_context is not None:
        primary_source = console_source if console_context is not None else "editor_crawler"
        partial_context = with_provenance(
            partial_context,
            primary_source=primary_source,
            sources=[primary_source],
            completeness=PARTIAL,
            bubble_export_available=False,
        )
        attempts.append(
            {
                "source": "context_completeness",
                "ok": False,
                "reason": "crawler_missing" if crawler_context is None else "console_missing",
            }
        )
        return _context_detection_result(
            partial_context,
            app_id=resolved_app_id,
            source=primary_source,
            canonical_path=canonical_context_path,
            output=output,
            crawler_index_path=crawler_path,
            attempts=attempts,
        )

    if session is None:
        raise ValueError(
            "No local Bubble artifact and no captured session available. Run `bubble-mcp session login` first."
        )
    raise ValueError("No usable .bubble, console.log(app), or editor crawler context source was available.")


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


def _resolve_artifact_path(raw_path: str | Path | None, settings_dir: Path) -> Path | None:
    if raw_path is None:
        return None
    text = str(raw_path).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    settings_candidate = settings_dir / path
    if settings_candidate.exists():
        return settings_candidate
    return Path.cwd() / path


def _unique_existing_order(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for candidate in candidates:
        path = candidate.get("path")
        if not isinstance(path, Path):
            continue
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _candidate_bubble_files(
    *,
    explicit: Path | None,
    configured: str | None,
    settings_dir: Path,
    profile: str,
    app_id: str,
) -> list[dict[str, Any]]:
    profile_dir = context_cache_dir() / _safe_name(profile)
    resolved_explicit = _resolve_artifact_path(explicit, settings_dir)
    resolved_configured = _resolve_artifact_path(configured, settings_dir)
    candidates = [
        *([{"source": "bubble_file", "path": resolved_explicit}] if resolved_explicit else []),
        *(
            [{"source": "profile_app_json_path", "path": resolved_configured}]
            if resolved_configured
            else []
        ),
        {"source": "local_bubble_candidate", "path": profile_dir / f"{_safe_name(app_id)}.bubble"},
        {"source": "local_bubble_candidate", "path": profile_dir / "app.bubble"},
        {"source": "local_bubble_candidate", "path": Path.cwd() / f"{_safe_name(app_id)}.bubble"},
        {"source": "local_bubble_candidate", "path": Path.cwd() / "app.bubble"},
        {"source": "local_bubble_candidate", "path": Path.cwd() / "src" / "app.bubble"},
    ]
    return _unique_existing_order(candidates)


def _candidate_consolelog_files(
    *,
    explicit: Path | None,
    configured: str | None,
    settings_dir: Path,
    profile: str,
    app_id: str,
) -> list[dict[str, Any]]:
    profile_dir = context_cache_dir() / _safe_name(profile)
    resolved_explicit = _resolve_artifact_path(explicit, settings_dir)
    resolved_configured = _resolve_artifact_path(configured, settings_dir)
    candidates = [
        *([{"source": "consolelog_file", "path": resolved_explicit}] if resolved_explicit else []),
        *(
            [{"source": "profile_consolelog_json_path", "path": resolved_configured}]
            if resolved_configured
            else []
        ),
        {"source": "local_consolelog_candidate", "path": profile_dir / f"{_safe_name(app_id)}-consolelog-app.json"},
        {"source": "local_consolelog_candidate", "path": profile_dir / "consolelog-app.json"},
        {"source": "local_consolelog_candidate", "path": Path.cwd() / f"{_safe_name(app_id)}-consolelog-app.json"},
        {"source": "local_consolelog_candidate", "path": Path.cwd() / "consolelog-app.json"},
    ]
    return _unique_existing_order(candidates)


def _first_console_payload(
    candidates: list[dict[str, Any]],
    *,
    attempts: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, Path | None]:
    for candidate in candidates:
        path = candidate["path"]
        source = str(candidate["source"])
        if not path.exists():
            attempts.append({"source": source, "path": str(path), "ok": False, "reason": "file not found"})
            continue
        try:
            payload = _read_consolelog_file(path)
        except (OSError, UnicodeError) as exc:
            attempts.append({"source": source, "path": str(path), "ok": False, "reason": str(exc)})
            continue
        if payload is None:
            attempts.append(
                {
                    "source": source,
                    "path": str(path),
                    "ok": False,
                    "reason": "console artifact did not contain a JSON app object",
                }
            )
            continue
        attempts.append({"source": source, "path": str(path), "ok": True})
        return payload, source, path
    return None, "", None


def _needs_editor_network_capture(index: dict[str, Any]) -> bool:
    if _obj(index.get("idToPath")):
        return False
    pages = index.get("pages")
    if isinstance(pages, list) and any(_obj(page).get("elements") for page in pages):
        return False
    return True


def _try_capture_editor_network_index(
    *,
    profile: str,
    app_id: str,
    app_version: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        attempts.append({"source": "editor_network_capture", "ok": False, "reason": f"playwright unavailable: {exc}"})
        return None

    user_data_dir = get_config_dir() / "browser-profiles" / profile
    if not user_data_dir.exists():
        attempts.append(
            {"source": "editor_network_capture", "ok": False, "reason": f"browser profile not found: {user_data_dir}"}
        )
        return None

    captured: dict[str, Any] = {
        "pageNameToId": {},
        "pageNameToPath": {},
        "customNameToId": {},
        "idToPath": {},
        "issuesSub": {},
        "dataTypes": {},
        "optionSets": {},
        "styles": {},
    }

    def absorb_data(data: Any) -> None:
        if not isinstance(data, dict):
            return
        if _looks_like_id_to_path(data):
            captured["idToPath"].update({str(key): str(value) for key, value in data.items()})
            return
        if _looks_like_issues_sub(data):
            captured["issuesSub"].update({str(key): str(value) for key, value in data.items()})
            return
        if _looks_like_custom_name_to_id(data):
            captured["customNameToId"].update(data)

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=True,
            )
            page = context.pages[0] if context.pages else context.new_page()

            def on_response(response: Any) -> None:
                if "/appeditor/load_" not in str(response.url):
                    return
                try:
                    payload = response.json()
                except Exception:
                    return
                if not isinstance(payload, dict):
                    return
                data = payload.get("data")
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict) or "data" not in item:
                            continue
                        item_data = item.get("data")
                        absorb_data(item_data)
                        if _looks_like_page_name_to_id(item_data):
                            captured["pageNameToId"].update(_string_map(item_data))
                        if _looks_like_page_name_to_path(item_data):
                            captured["pageNameToPath"].update(_string_map(item_data))
                else:
                    absorb_data(data)

            page.on("response", on_response)
            page.goto(
                f"https://bubble.io/page?id={app_id}&tab=Design&name=index",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            page.wait_for_timeout(15_000)
            context.close()
    except Exception as exc:
        attempts.append({"source": "editor_network_capture", "ok": False, "reason": str(exc)})
        return None

    id_to_path = _string_map(captured["idToPath"])
    page_name_to_path = _string_map(captured["pageNameToPath"])
    page_name_to_id = _string_map(captured["pageNameToId"])
    issues_sub = _string_map(captured["issuesSub"])
    if not id_to_path and not page_name_to_path:
        attempts.append({"source": "editor_network_capture", "ok": False, "reason": "no editor index data captured"})
        return None

    pages = []
    for name, encoded_path in page_name_to_path.items():
        page_key = _last_path_segment(encoded_path) or page_name_to_id.get(name) or name
        root_id = page_name_to_id.get(name) or _root_id_for_path(id_to_path, encoded_path) or page_key
        children = _decode_children(issues_sub.get(root_id)) or _top_level_children_from_id_to_path(
            id_to_path,
            encoded_path,
        )
        pages.append(
            {
                "id": page_key,
                "name": name,
                "rootId": root_id,
                "properties": {},
                "elements": {child_id: {"id": child_id} for child_id in children},
                "workflows": {},
                "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )

    attempts.append(
        {
            "source": "editor_network_capture",
            "ok": True,
            "pages": len(pages),
            "id_to_path": len(id_to_path),
        }
    )
    return {
        "appId": app_id,
        "profile": profile,
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lastChange": 0,
        "sectionHashes": {},
        "pages": pages,
        "reusables": [],
        "backendWorkflows": [],
        "apiConnectorCalls": [],
        "pageIndex": {page["name"]: page["id"] for page in pages},
        "reusableIndex": {},
        "apiIndex": {},
        "idToPath": id_to_path,
        "dataTypes": _obj(captured["dataTypes"]),
        "optionSets": _obj(captured["optionSets"]),
        "styles": _obj(captured["styles"]),
        "source": "editor_network_capture",
        "apiCallCount": 0,
        "durationMs": 0,
        "_issuesSub": issues_sub,
        "_appVersion": app_version,
    }


def _merge_crawler_indexes(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ("idToPath", "dataTypes", "optionSets", "styles"):
        merged[key] = {**_obj(base.get(key)), **_obj(overlay.get(key))}
    for key in ("pages", "reusables", "backendWorkflows", "apiConnectorCalls"):
        if overlay.get(key):
            merged[key] = overlay[key]
    for key in ("pageIndex", "reusableIndex", "apiIndex"):
        merged[key] = {**_obj(base.get(key)), **_obj(overlay.get(key))}
    if overlay.get("_issuesSub"):
        merged["_issuesSub"] = overlay["_issuesSub"]
    merged["source"] = overlay.get("source") or base.get("source")
    return merged


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
    profile: str,
    attempts: list[dict[str, Any]],
) -> Path | None:
    version = app_version or session.app_version or "test"
    export_url = f"https://bubble.io/appeditor/export/{version}/{app_id}.bubble"
    headers = _export_headers(session)
    target_path = default_bubble_export_path(profile, app_id)
    try:
        response = requests.get(export_url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        attempts.append({"source": "downloaded_bubble", "ok": False, "url": export_url, "reason": str(exc)})
        return None

    if response.status_code != 200:
        attempts.append(
            {
                "source": "downloaded_bubble",
                "ok": False,
                "url": export_url,
                "status": response.status_code,
                "reason": "export endpoint rejected the captured session",
            }
        )
        return None

    content = response.content
    prefix = content[:256].lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        attempts.append(
            {
                "source": "downloaded_bubble",
                "ok": False,
                "url": export_url,
                "status": response.status_code,
                "reason": "export endpoint returned HTML; captured session is not editor-compatible",
            }
        )
        return None

    try:
        # RFC 8259 mandates UTF-8 for JSON interchange, so decode as UTF-8
        # unconditionally rather than trusting `requests`' guessed
        # `response.encoding`: when the response has no explicit charset,
        # requests/urllib3 falls back to ISO-8859-1 per the old HTTP default
        # for text/* content, silently mojibake-corrupting every non-ASCII
        # byte in the exported app (accented names, etc.) instead of raising.
        decoded = content.decode("utf-8")
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        attempts.append(
            {
                "source": "downloaded_bubble",
                "ok": False,
                "url": export_url,
                "status": response.status_code,
                "reason": f"export response is not a JSON .bubble payload: {exc}",
            }
        )
        return None
    if not isinstance(parsed, dict):
        attempts.append(
            {
                "source": "downloaded_bubble",
                "ok": False,
                "url": export_url,
                "status": response.status_code,
                "reason": "export response is not a JSON object",
            }
        )
        return None

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_bubble_export_meta(
        target_path,
        url=export_url,
        app_id=app_id,
        app_version=version,
        profile=profile,
        raw_bytes=content,
    )
    attempts.append(
        {
            "source": "downloaded_bubble",
            "ok": True,
            "url": export_url,
            "app_version": version,
            "path": str(target_path),
            "bytes": len(content),
        }
    )
    return target_path


def bubble_export_meta_path(export_path: Path) -> Path:
    return export_path.with_name(export_path.name + ".meta.json")


def _write_bubble_export_meta(
    export_path: Path,
    *,
    url: str,
    app_id: str,
    app_version: str,
    profile: str,
    raw_bytes: bytes,
) -> None:
    """Record which branch/version produced the cached export, for later audit."""
    meta = {
        "url": url,
        "app_id": app_id,
        "app_version": app_version,
        "profile": profile,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source": "https://bubble.io/appeditor/export",
    }
    try:
        bubble_export_meta_path(export_path).write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


def _export_headers(session: BubbleSessionData) -> dict[str, str]:
    blocked = {"content-length", "host", "connection"}
    headers = {
        str(key): str(value)
        for key, value in session.headers.items()
        if value is not None and str(key).lower() not in blocked
    }
    headers.setdefault("accept", "application/json, text/javascript, */*; q=0.01")
    headers.setdefault("x-requested-with", "XMLHttpRequest")
    headers.setdefault("referer", f"https://bubble.io/page?id={session.app_id}")
    if session.cookies and not any(key.lower() == "cookie" for key in headers):
        headers["cookie"] = session.cookies
    return headers


def _save_profile_app_json_path(*, profile: str, app_id: str, app_json_path: Path) -> None:
    settings = load_settings()
    existing = settings.profiles.get(profile)
    relative_path = _relative_to_config_dir(app_json_path, settings.config_dir)
    if existing:
        updated_profile = replace(existing, app_json_path=relative_path)
    else:
        updated_profile = BubbleProfile(
            name=profile,
            app_id=app_id,
            appname=app_id,
            app_json_path=relative_path,
        )
    save_settings(with_profile(settings, updated_profile))


def _relative_to_config_dir(path: Path, config_dir: Path) -> str:
    try:
        return str(path.relative_to(config_dir))
    except ValueError:
        return str(path)


def _split_bubble_export(
    path: Path,
    *,
    app_id: str,
    modules_dir: Path,
    attempts: list[dict[str, Any]],
) -> Path | None:
    try:
        split_output = StringIO()
        with redirect_stdout(split_output):
            split_app(
                input_path=path,
                out_dir=modules_dir.parent,
                app_name=app_id,
                force=True,
                pretty=True,
                write_index=True,
            )
    except (OSError, SystemExit, ValueError) as exc:
        attempts.append({"source": "bubble_modules_split", "ok": False, "reason": str(exc)})
        return None

    output = split_output.getvalue().strip()
    attempts.append(
        {
            "source": "bubble_modules_split",
            "ok": True,
            "path": str(modules_dir),
            "parser": "bubble_mcp.vendor.bubble_modules.split_app",
            **({"log": output} if output else {}),
        }
    )
    return modules_dir


def _try_extract_consolelog_app(
    *,
    session: BubbleSessionData,
    profile: str,
    app_id: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    _ = session
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        attempts.append({"source": "consolelog_app", "ok": False, "reason": f"playwright unavailable: {exc}"})
        return None

    user_data_dir = get_config_dir() / "browser-profiles" / profile
    if not user_data_dir.exists():
        attempts.append(
            {"source": "consolelog_app", "ok": False, "reason": f"browser profile not found: {user_data_dir}"}
        )
        return None

    capture: Any = None
    context = None
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(user_data_dir), headless=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(
                f"https://bubble.io/page?id={app_id}&tab=Design&name=index",
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            try:
                page.wait_for_function(
                    "() => typeof app !== 'undefined' || typeof globalThis.app !== 'undefined'",
                    timeout=CONSOLE_APP_WAIT_MS,
                )
            except Exception:
                pass
            capture = page.evaluate(
                """
                (maxChars) => {
                  try {
                    const value = typeof app !== "undefined" ? app : globalThis.app;
                    if (!value) return { ok: false, reason: "editor app object unavailable" };
                    const serialized = JSON.stringify(value);
                    if (!serialized) return { ok: false, reason: "editor app object is not serializable" };
                    if (serialized.length > maxChars) {
                      return { ok: false, reason: "editor app object exceeds capture limit", chars: serialized.length };
                    }
                    return { ok: true, serialized };
                  } catch (error) {
                    return { ok: false, reason: String(error) };
                  }
                }
                """,
                MAX_CONSOLE_APP_CHARS,
            )
    except Exception as exc:
        attempts.append({"source": "consolelog_app", "ok": False, "reason": str(exc)})
        return None
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass

    if not isinstance(capture, dict) or not capture.get("ok"):
        reason = str(capture.get("reason") or "editor app object unavailable") if isinstance(capture, dict) else "editor app object unavailable"
        attempt = {"source": "consolelog_app", "ok": False, "reason": reason}
        if isinstance(capture, dict) and isinstance(capture.get("chars"), int):
            attempt["chars"] = capture["chars"]
        attempts.append(attempt)
        return None

    try:
        payload = json.loads(str(capture.get("serialized") or ""))
    except json.JSONDecodeError as exc:
        attempts.append({"source": "consolelog_app", "ok": False, "reason": f"captured app JSON is invalid: {exc}"})
        return None
    if not isinstance(payload, dict):
        attempts.append({"source": "consolelog_app", "ok": False, "reason": "captured app payload is not an object"})
        return None

    path = default_consolelog_app_path(profile, app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    attempts.append(
        {
            "source": "consolelog_app",
            "ok": True,
            "path": str(path),
            "bytes": path.stat().st_size,
        }
    )
    return payload


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


def _save_context_outputs(
    context: BubbleProjectContext,
    *,
    canonical_path: Path,
    output: Path | None,
) -> Path:
    save_context(context, canonical_path)
    if output is None:
        return canonical_path
    if output.expanduser().resolve() != canonical_path.expanduser().resolve():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(canonical_path.read_text(encoding="utf-8"), encoding="utf-8")
    return output


def _copy_cached_context_output(*, canonical_path: Path, output: Path | None) -> Path:
    if output is None:
        return canonical_path
    if output.expanduser().resolve() != canonical_path.expanduser().resolve():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_path.read_bytes())
    return output


def _has_usable_console_context(context: BubbleProjectContext) -> bool:
    if context.nodes:
        return True
    return any(
        bool(context.metadata.get(key))
        for key in ("settings", "styles", "default_styles")
    )


def _has_usable_crawler_topology(context: BubbleProjectContext) -> bool:
    return any(
        node.type in {"page", "reusable", "element", "workflow"}
        for node in context.nodes
    )


def _context_detection_result(
    context: BubbleProjectContext,
    *,
    app_id: str,
    source: str,
    canonical_path: Path,
    output: Path | None,
    crawler_index_path: Path | None,
    attempts: list[dict[str, Any]],
) -> DetectionResult:
    result_path = _save_context_outputs(context, canonical_path=canonical_path, output=output)
    return DetectionResult(
        ok=True,
        app_id=app_id,
        source=source,
        context_path=result_path,
        crawler_index_path=crawler_index_path,
        summary=_safe_detection_summary(context),
        attempts=attempts,
    )


def _safe_detection_summary(context: BubbleProjectContext) -> dict[str, Any]:
    summary = context.summary()
    metadata = summary.get("metadata")
    raw_provenance = metadata.get("provenance") if isinstance(metadata, dict) else None
    safe_metadata: dict[str, Any] = {}
    if isinstance(raw_provenance, dict):
        sources = raw_provenance.get("sources")
        safe_metadata["provenance"] = {
            "primary_source": str(raw_provenance.get("primary_source") or ""),
            "sources": [str(item) for item in sources] if isinstance(sources, list) else [],
            "completeness": str(raw_provenance.get("completeness") or PARTIAL),
            "bubble_export_available": bool(raw_provenance.get("bubble_export_available")),
        }
    return {
        "app_id": summary.get("app_id"),
        "source": summary.get("source"),
        "counts": summary.get("counts", {}),
        "nodes": summary.get("nodes", 0),
        "edges": summary.get("edges", 0),
        **({"metadata": safe_metadata} if safe_metadata else {}),
    }


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


def _looks_like_id_to_path(value: Any) -> bool:
    data = _obj(value)
    if len(data) < 3:
        return False
    sample = [item for item in data.values() if isinstance(item, str)][:50]
    return bool(sample) and sum("%p3." in item or "%ed." in item for item in sample) >= max(1, len(sample) // 3)


def _looks_like_issues_sub(value: Any) -> bool:
    data = _obj(value)
    if len(data) < 3:
        return False
    sample = [item for item in data.values() if isinstance(item, str)][:50]
    return bool(sample) and sum(item.strip().startswith("[") for item in sample) >= max(1, len(sample) // 2)


def _looks_like_custom_name_to_id(value: Any) -> bool:
    data = _obj(value)
    if not data:
        return False
    sample = [item for item in data.values() if isinstance(item, dict)][:10]
    return bool(sample) and all("custom_id" in item and "name" in item for item in sample)


def _looks_like_page_name_to_id(value: Any) -> bool:
    data = _obj(value)
    if not data or not all(isinstance(item, str) for item in data.values()):
        return False
    return any(key in data for key in ("index", "404", "reset_pw")) and not _looks_like_page_name_to_path(data)


def _looks_like_page_name_to_path(value: Any) -> bool:
    data = _obj(value)
    return bool(data) and all(isinstance(item, str) and item.startswith("%p") for item in data.values())


def _last_path_segment(encoded_path: str) -> str:
    parts = [part for part in str(encoded_path or "").split(".") if part]
    return parts[-1] if parts else ""


def _root_id_for_path(id_to_path: dict[str, str], encoded_path: str) -> str:
    normalized = str(encoded_path or "").strip()
    for item_id, item_path in id_to_path.items():
        if item_path == normalized:
            return item_id
    return ""


def _top_level_children_from_id_to_path(id_to_path: dict[str, str], encoded_path: str) -> list[str]:
    prefix = f"{str(encoded_path or '').strip()}.%el."
    children: set[str] = set()
    for item_id, item_path in id_to_path.items():
        if not item_path.startswith(prefix):
            continue
        remainder = item_path[len(prefix) :]
        if ".%el." in remainder:
            continue
        if item_id and item_id not in {"index", "404", "reset_pw"}:
            children.add(item_id)
    return sorted(children)


def _decode_children(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item).strip()]
