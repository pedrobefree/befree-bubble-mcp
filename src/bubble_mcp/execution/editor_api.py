"""Authenticated Bubble editor metadata endpoints."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.execution.client import (
    EDITOR_WRITE_TIMEOUT_SEC,
    BubbleEditorClient,
    HttpTransport,
    build_editor_write_headers,
    default_http_transport,
    parse_response_body,
)
from bubble_mcp.sessions.store import BubbleSessionData, load_session


BUBBLE_EDITOR_BASE_URL = "https://bubble.io"
DEFAULT_LOG_MESSAGES = [
    "running event",
    "event condition passed",
    "event condition failed, terminating",
    "running action",
    "action condition failed",
    "action completed",
    "event completed",
    "error occurred during workflow execution",
    "failed because of error",
    "server_db.modify",
    "plugin action console output",
    "plugin action console error",
    "scheduled task to run",
    "scheduled task completed",
    "http_request",
    "http_request response",
    "received request for API workflow",
    "Sending email failed",
]
WORKLOAD_GRANULARITIES = {"minute", "hour", "day"}
PLATFORMS = {"web", "mobile", "web_and_mobile"}


class BubbleEditorApiClient:
    """Posts authenticated non-write Bubble editor API requests."""

    def __init__(
        self,
        *,
        transport: HttpTransport = default_http_transport,
        timeout: float = EDITOR_WRITE_TIMEOUT_SEC,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
        session: BubbleSessionData,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if not endpoint.startswith("/appeditor/"):
            raise ValueError("Bubble editor endpoint must start with /appeditor/.")
        url = f"{BUBBLE_EDITOR_BASE_URL}{endpoint}"
        headers = build_editor_write_headers(session, payload)
        safe_request = {
            "url": url,
            "payload": payload,
            "headers": redact_sensitive(headers),
        }
        if dry_run:
            return {"ok": True, "dry_run": True, "request": safe_request}

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        response = self._transport(url, body, headers, self._timeout)
        data = parse_response_body(response.body)

        if response.status in (401, 403):
            return {
                "ok": False,
                "dry_run": False,
                "status": response.status,
                "error": f"Bubble blocked the editor request ({response.status}).",
                "reason": "auth_blocked",
                "response": data,
                "request": safe_request,
            }
        if isinstance(data, str) and data.lstrip().startswith("<"):
            raise RuntimeError("Bubble session expired: received HTML instead of JSON.")

        return {
            "ok": 200 <= response.status < 300,
            "dry_run": False,
            "status": response.status,
            "response": data,
            "request": safe_request,
        }


def _load_session_for_profile(profile: str) -> BubbleSessionData:
    profile_name = str(profile or "").strip()
    if not profile_name:
        raise ValueError("A Bubble MCP profile is required.")
    session = load_session(profile_name)
    if session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile_name}'.")
    return session


def _resolve_app_id(profile: str, session: BubbleSessionData, app_id: str | None = None) -> str:
    explicit = str(app_id or "").strip()
    if explicit:
        return explicit
    settings = load_settings()
    configured_profile = resolve_profile(settings, profile)
    resolved = str((configured_profile.app_id if configured_profile else "") or session.app_id or "").strip()
    if not resolved:
        raise ValueError("Unable to resolve Bubble app id from arguments, profile, or session.")
    return resolved


def _resolve_app_version(profile: str, session: BubbleSessionData, app_version: str | None = None) -> str:
    explicit = str(app_version or "").strip()
    if explicit:
        return explicit
    settings = load_settings()
    configured_profile = resolve_profile(settings, profile)
    return str((configured_profile.app_version if configured_profile else "") or session.app_version or "test").strip()


def _resolve_metrics_app_version(app_version: str | None = None) -> str:
    return str(app_version or "live").strip() or "live"


def _iso_datetime(value: str | int | float | None, *, default: datetime | None = None) -> str:
    if value in (None, ""):
        if default is None:
            raise ValueError("A date/time value is required.")
        dt = default
    elif isinstance(value, int | float):
        dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    else:
        text = str(value).strip()
        if text.isdigit():
            dt = datetime.fromtimestamp(float(text) / 1000, tz=timezone.utc)
        else:
            normalized = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _epoch_ms(value: str | int | float | None, *, default: datetime | None = None) -> int:
    iso_value = _iso_datetime(value, default=default)
    dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _bounded_granularity(value: str) -> str:
    granularity = str(value or "day").strip().lower()
    if granularity not in WORKLOAD_GRANULARITIES:
        raise ValueError("granularity must be one of: minute, hour, day.")
    return granularity


def _bounded_platform(value: str) -> str:
    platform = str(value or "web_and_mobile").strip()
    if platform not in PLATFORMS:
        raise ValueError("platform must be one of: web, mobile, web_and_mobile.")
    return platform


def _response_items(response: Any) -> list[Any]:
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("results", "logs", "items", "rows", "data", "entries"):
            value = response.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for nested_key in ("rows", "results", "logs", "items", "entries"):
                    nested_value = value.get(nested_key)
                    if isinstance(nested_value, list):
                        return nested_value
    return []


def _sum_numeric(items: list[Any], *keys: str) -> float:
    total = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if isinstance(value, int | float):
                total += float(value)
                break
            if isinstance(value, str):
                try:
                    total += float(value)
                    break
                except ValueError:
                    continue
    return total


def _top_items(items: list[Any], *, key: str, limit: int = 10) -> list[dict[str, Any]]:
    dict_items = [item for item in items if isinstance(item, dict)]

    def score(item: dict[str, Any]) -> float:
        value = item.get(key)
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0

    return sorted(dict_items, key=score, reverse=True)[: max(1, int(limit))]


def _compact_result(result: dict[str, Any], *, include_raw: bool = False, limit: int = 50) -> dict[str, Any]:
    response = result.get("response")
    items = _response_items(response)
    compact = {
        **{key: value for key, value in result.items() if key not in {"response"}},
        "count": len(items) if items else (len(response) if isinstance(response, dict) else 0),
    }
    if items:
        compact["items"] = items[: max(1, int(limit))]
    elif isinstance(response, dict):
        compact["data"] = response if include_raw else {key: response[key] for key in list(response)[:50]}
    elif response is not None and include_raw:
        compact["data"] = response
    if include_raw:
        compact["raw_response"] = response
    return compact


def _post_profile_endpoint(
    *,
    profile: str,
    endpoint: str,
    payload: dict[str, Any],
    app_id: str | None = None,
    include_raw: bool = False,
    limit: int = 50,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    payload = {"appname": appname, **payload}
    result = _client(client).post(endpoint, payload, session)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        **_compact_result(result, include_raw=include_raw, limit=limit),
    }


def _client(client: BubbleEditorApiClient | None) -> BubbleEditorApiClient:
    return client or BubbleEditorApiClient()


def _editor_session_id(value: str | None = None) -> str:
    explicit = str(value or "").strip()
    if explicit:
        return explicit
    return f"{int(time.time() * 1000)}x32"


def _merge_write_change(
    *,
    path_array: list[str],
    body: Any,
    session_id: str,
    intent: dict[str, Any] | None = None,
    version_control_api_version: int = 4,
    changelog_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    change = {
        "body": body,
        "path_array": path_array,
        "version_control_api_version": version_control_api_version,
        "changelog_data": changelog_data or [],
        "session_id": session_id,
    }
    if intent is not None:
        change["intent"] = intent
    return change


def _session_user_id(session: BubbleSessionData, explicit: str | None = None) -> str:
    user_id = str(explicit or "").strip()
    if user_id:
        return user_id
    cookie = str(session.cookies or session.headers.get("cookie") or session.headers.get("Cookie") or "")
    for part in cookie.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key in {"meta_u1main", "ajs_user_id"}:
            resolved = unquote(value).strip()
            if resolved:
                return resolved
    return ""


def _merge_changelog_data(
    *,
    appname: str,
    target_version_id: str,
    source_version_id: str,
    temporary_merge_branch_id: str,
    source_branch_name: str,
    user_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "appname": appname,
            "app_version": target_version_id,
            "user_id": user_id,
            "change_identifier": temporary_merge_branch_id,
            "display_name": source_branch_name,
            "operation": "merge",
            "before_value": json.dumps(source_version_id),
            "inner_node_count": 1,
        }
    ]


def _intent_name(change: dict[str, Any]) -> str:
    intent = change.get("intent")
    if isinstance(intent, dict):
        return str(intent.get("name") or "")
    return ""


def _path_context(path_array: list[Any]) -> dict[str, Any]:
    path = [str(part) for part in path_array]
    joined = ".".join(path)
    context: dict[str, Any] = {
        "path": joined,
        "path_array": path,
        "category": "unknown",
    }
    if not path:
        return context
    if path[0] == "_index":
        context["category"] = "auxiliary_index"
        context["index_kind"] = path[1] if len(path) > 1 else ""
        context["target_id"] = path[2] if len(path) > 2 else ""
        return context
    if path[0] == "merge_changes_complete":
        context["category"] = "merge_confirmation"
        return context
    if path[0] == "merge_changes":
        context["category"] = "merge_conflicts_resolution_marker"
        return context
    if path[0] == "%ed":
        context["category"] = "editor_data"
        if len(path) > 1:
            context["element_or_event_id"] = path[1]
        if "%wf" in path:
            wf_index = path.index("%wf")
            context["category"] = "workflow"
            if wf_index + 1 < len(path):
                context["workflow_id"] = path[wf_index + 1]
            if path[-1] == "actions":
                context["category"] = "workflow_actions"
        return context
    if path[0] == "styles":
        context["category"] = "style"
        context["style_id"] = path[1] if len(path) > 1 else ""
        return context
    if path[0] == "user_types":
        context["category"] = "data_type"
        context["data_type"] = path[1] if len(path) > 1 else ""
        return context
    if path[0] == "option_sets":
        context["category"] = "option_set"
        context["option_set"] = path[1] if len(path) > 1 else ""
        return context
    if path[0] == "settings":
        context["category"] = "setting"
        return context
    return context


def _short_string(value: str, *, limit: int = 180) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(0, limit - 1)]}..."


def _collect_body_snippets(value: Any, snippets: list[str], *, limit: int = 8) -> None:
    if len(snippets) >= limit:
        return
    if isinstance(value, str):
        if value and not value.startswith("data:image/"):
            snippets.append(_short_string(value))
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if len(snippets) >= limit:
                return
            if key in {"%nm", "%x", "id", "custom_event", "option_set", "option_value"}:
                _collect_body_snippets(child, snippets, limit=limit)
            elif isinstance(child, (dict, list)):
                _collect_body_snippets(child, snippets, limit=limit)
        return
    if isinstance(value, list):
        for child in value:
            if len(snippets) >= limit:
                return
            _collect_body_snippets(child, snippets, limit=limit)


def _summarize_merge_body(body: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "kind": type(body).__name__,
    }
    decoded = body
    if isinstance(body, str):
        stripped = body.strip()
        summary["length"] = len(body)
        if stripped[:1] in {"{", "["}:
            try:
                decoded = json.loads(stripped)
                summary["kind"] = f"json_{type(decoded).__name__}"
            except json.JSONDecodeError:
                decoded = body
    if isinstance(decoded, dict):
        keys = [str(key) for key in decoded.keys()]
        summary["entry_count"] = len(keys)
        summary["top_level_keys"] = keys[:20]
        action_summaries: list[dict[str, Any]] = []
        for key in sorted(keys, key=lambda item: (0, int(item)) if item.isdigit() else (1, item)):
            item = decoded.get(key)
            if not isinstance(item, dict):
                continue
            properties = item.get("%p")
            action_summaries.append(
                {
                    "position": int(key) if key.isdigit() else key,
                    "id": item.get("id"),
                    "type": item.get("%x"),
                    "property_keys": list(properties.keys())[:12] if isinstance(properties, dict) else [],
                }
            )
        if action_summaries:
            summary["action_count"] = len(action_summaries)
            summary["actions"] = action_summaries[:20]
    elif isinstance(decoded, list):
        summary["entry_count"] = len(decoded)
    snippets: list[str] = []
    _collect_body_snippets(decoded, snippets)
    if snippets:
        summary["text_snippets"] = snippets
    return summary


def describe_bubble_branch_merge_conflicts(*, payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("request", {}).get("payload") if isinstance(payload.get("request"), dict) else None
    if not isinstance(candidate, dict):
        candidate = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    if not isinstance(candidate, dict):
        raise ValueError("bubble_branch_merge_conflicts_describe requires a payload object.")
    changes = candidate.get("changes")
    if not isinstance(changes, list):
        raise ValueError("bubble_branch_merge_conflicts_describe requires a payload with a changes array.")

    conflicts: list[dict[str, Any]] = []
    auxiliary_changes: list[dict[str, Any]] = []
    confirmations: list[dict[str, Any]] = []
    for index, raw_change in enumerate(changes):
        if not isinstance(raw_change, dict):
            auxiliary_changes.append({"change_index": index, "reason": "non_object_change"})
            continue
        path_array = raw_change.get("path_array") if isinstance(raw_change.get("path_array"), list) else []
        context = _path_context(path_array)
        intent_name = _intent_name(raw_change)
        if intent_name == "MergeConflict":
            conflict_id = f"merge_conflict_{len(conflicts) + 1}"
            conflicts.append(
                {
                    "id": conflict_id,
                    "change_index": index,
                    "intent": intent_name,
                    "context": context,
                    "body_summary": _summarize_merge_body(raw_change.get("body")),
                    "decision_required": True,
                    "decision_status": "pending_user_selection",
                    "user_prompt": (
                        f"Conflict {conflict_id} affects {context.get('category')} at "
                        f"{context.get('path')}. Ask the user which Bubble version to keep before writing."
                    ),
                }
            )
        elif context["category"].startswith("merge_"):
            confirmations.append(
                {
                    "change_index": index,
                    "intent": intent_name or None,
                    "context": context,
                    "body_summary": _summarize_merge_body(raw_change.get("body")),
                }
            )
        else:
            auxiliary_changes.append(
                {
                    "change_index": index,
                    "intent": intent_name or None,
                    "context": context,
                    "body_summary": _summarize_merge_body(raw_change.get("body")),
                }
            )

    return {
        "ok": True,
        "app_id": candidate.get("appname"),
        "merge_app_version": candidate.get("app_version") or candidate.get("appVersion"),
        "change_count": len(changes),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "auxiliary_change_count": len(auxiliary_changes),
        "auxiliary_changes": auxiliary_changes,
        "confirmation_change_count": len(confirmations),
        "confirmation_changes": confirmations,
        "decision_policy": "manual_user_selection_required",
        "next_steps": [
            "Review each conflict with the developer before applying any MergeConflict write.",
            "Use an exact Bubble conflict-selection write payload only after the developer chooses a version.",
            "After all conflict-selection writes are applied, call bubble_branch_merge_confirm with conflicts_resolved=true.",
        ],
    }


def list_bubble_branches(
    *,
    profile: str,
    app_id: str | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    payload = {"appname": appname}
    result = _client(client).post("/appeditor/get_versions", payload, session)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, **result}


def list_branch_contributors(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    payload = {"appname": appname, "app_version": version}
    result = _client(client).post("/appeditor/fetch_contributors_to_branch", payload, session)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "app_version": version, **result}


def fetch_changelog_entries(
    *,
    profile: str,
    app_id: str | None = None,
    app_version: str | None = None,
    start_index: int = 0,
    num_fetch: int = 50,
    filters: dict[str, Any] | None = None,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    version = _resolve_app_version(profile, session, app_version)
    payload = {
        "appname": appname,
        "app_version": version,
        "start_index": max(0, int(start_index)),
        "num_fetch": min(max(1, int(num_fetch)), 200),
        "filters": filters or {},
    }
    result = _client(client).post("/appeditor/fetch_changelog_entries", payload, session)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "app_version": version, **result}


def create_bubble_branch(
    *,
    profile: str,
    name: str,
    app_id: str | None = None,
    from_app_version: str | None = None,
    description: str = "",
    execute: bool = False,
    version_control_api_version: int = 7,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    branch_name = str(name or "").strip()
    if not branch_name:
        raise ValueError("bubble_branch_create requires a branch name.")
    payload = {
        "appname": appname,
        "from_app_version": str(from_app_version or _resolve_app_version(profile, session)).strip(),
        "app_version": branch_name,
        "description": str(description or ""),
        "version_control_api_version": int(version_control_api_version),
    }
    result = _client(client).post("/appeditor/create_new_app_version", payload, session, dry_run=not execute)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "executed": execute, **result}


def delete_bubble_branch(
    *,
    profile: str,
    app_version: str,
    app_id: str | None = None,
    soft_delete: bool = True,
    execute: bool = False,
    confirm: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    branch_version = str(app_version or "").strip()
    if not branch_version:
        raise ValueError("bubble_branch_delete requires app_version for the branch to delete.")
    if execute and not confirm:
        raise ValueError("bubble_branch_delete requires confirm=true when execute=true.")
    payload = {"appname": appname, "app_version": branch_version, "soft_delete": bool(soft_delete)}
    result = _client(client).post("/appeditor/delete_app_version", payload, session, dry_run=not execute)
    return {"ok": result.get("ok"), "profile": profile, "app_id": appname, "executed": execute, **result}


def start_bubble_branch_merge(
    *,
    profile: str,
    ours_version_id: str,
    theirs_version_id: str,
    savepoint_message: str,
    app_id: str | None = None,
    session_id: str | None = None,
    execute: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    ours = str(ours_version_id or "").strip()
    theirs = str(theirs_version_id or "").strip()
    message = str(savepoint_message or "").strip()
    if not ours:
        raise ValueError("bubble_branch_merge_start requires ours_version_id.")
    if not theirs:
        raise ValueError("bubble_branch_merge_start requires theirs_version_id.")
    if not message:
        raise ValueError("bubble_branch_merge_start requires savepoint_message.")
    merge_session_id = _editor_session_id(session_id)
    payload = {
        "appname": appname,
        "ours_version_id": ours,
        "theirs_version_id": theirs,
        "session_id": merge_session_id,
        "savepoint_message": message,
    }
    result = _client(client).post("/appeditor/sync", payload, session, dry_run=not execute)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "ours_version_id": ours,
        "theirs_version_id": theirs,
        "session_id": merge_session_id,
        "executed": execute,
        **result,
    }


def confirm_bubble_branch_merge(
    *,
    profile: str,
    merge_app_version: str,
    app_id: str | None = None,
    conflicts_resolved: bool = False,
    session_id: str | None = None,
    execute: bool = False,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    merge_version = str(merge_app_version or "").strip()
    if not merge_version:
        raise ValueError("bubble_branch_merge_confirm requires merge_app_version.")
    merge_session_id = _editor_session_id(session_id)
    if conflicts_resolved:
        changes = [
            _merge_write_change(
                path_array=["merge_changes_complete"],
                body=None,
                session_id=merge_session_id,
            ),
            _merge_write_change(
                path_array=["merge_changes"],
                body=None,
                session_id=merge_session_id,
                intent={"name": "ResolveMergeChanges"},
            ),
        ]
    else:
        changes = [
            _merge_write_change(
                path_array=["merge_changes_complete"],
                body=True,
                session_id=merge_session_id,
            )
        ]
    payload = {
        "v": 1,
        "appname": appname,
        "app_version": merge_version,
        "changes": changes,
    }
    result = (client or BubbleEditorClient()).write(payload, session, dry_run=not execute)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "merge_app_version": merge_version,
        "session_id": merge_session_id,
        "conflicts_resolved": conflicts_resolved,
        "executed": execute,
        **result,
    }


def resolve_bubble_branch_merge_conflicts(
    *,
    profile: str,
    merge_app_version: str,
    app_id: str | None = None,
    changelog_data: list[dict[str, Any]] | None = None,
    session_id: str | None = None,
    execute: bool = False,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    merge_version = str(merge_app_version or "").strip()
    if not merge_version:
        raise ValueError("bubble_branch_merge_resolve_conflicts requires merge_app_version.")
    merge_session_id = _editor_session_id(session_id)
    changes = [
        _merge_write_change(
            path_array=["conflicts"],
            body=None,
            session_id=merge_session_id,
            intent={"name": "ResolveConflicts"},
            version_control_api_version=7,
            changelog_data=changelog_data or [],
        ),
        _merge_write_change(
            path_array=["conflicts_theirs_version_name"],
            body=None,
            session_id=merge_session_id,
            intent={"name": "CleanupConflicts"},
            version_control_api_version=7,
        ),
        _merge_write_change(
            path_array=["conflicts_undo_snapshot_id"],
            body=None,
            session_id=merge_session_id,
            intent={"name": "CleanupConflicts"},
            version_control_api_version=7,
        ),
    ]
    payload = {
        "v": 1,
        "appname": appname,
        "app_version": merge_version,
        "changes": changes,
    }
    result = (client or BubbleEditorClient()).write(payload, session, dry_run=not execute)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "merge_app_version": merge_version,
        "session_id": merge_session_id,
        "executed": execute,
        **result,
    }


def finalize_bubble_branch_merge(
    *,
    profile: str,
    merge_app_version: str,
    target_version_id: str,
    source_version_id: str,
    source_branch_name: str,
    app_id: str | None = None,
    user_id: str | None = None,
    savepoint_message: str | None = None,
    version_control_api_version: int = 7,
    changelog_data: list[dict[str, Any]] | None = None,
    execute: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    merge_version = str(merge_app_version or "").strip()
    target_version = str(target_version_id or "").strip()
    source_version = str(source_version_id or "").strip()
    source_name = str(source_branch_name or "").strip()
    if not merge_version:
        raise ValueError("bubble_branch_merge_finalize requires merge_app_version.")
    if not target_version:
        raise ValueError("bubble_branch_merge_finalize requires target_version_id.")
    if not source_version:
        raise ValueError("bubble_branch_merge_finalize requires source_version_id.")
    if not source_name:
        raise ValueError("bubble_branch_merge_finalize requires source_branch_name.")
    resolved_user_id = _session_user_id(session, user_id)
    if not resolved_user_id:
        raise ValueError("bubble_branch_merge_finalize requires user_id when it cannot be derived from session cookies.")
    resolved_changelog_data = changelog_data or _merge_changelog_data(
        appname=appname,
        target_version_id=target_version,
        source_version_id=source_version,
        temporary_merge_branch_id=merge_version,
        source_branch_name=source_name,
        user_id=resolved_user_id,
    )
    message = str(savepoint_message or f"finalize_merge:Completed merging changes from {source_name}").strip()
    payload = {
        "appname": appname,
        "temporary_merge_branch_id": merge_version,
        "savepoint_message": message,
        "version_control_api_version": int(version_control_api_version),
        "changelog_data": resolved_changelog_data,
    }
    result = _client(client).post("/appeditor/finalize_merge", payload, session, dry_run=not execute)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "merge_app_version": merge_version,
        "target_version_id": target_version,
        "source_version_id": source_version,
        "source_branch_name": source_name,
        "executed": execute,
        **result,
    }


def deploy_app_test_and_hotfix(
    *,
    profile: str,
    message: str,
    app_id: str | None = None,
    from_app_version: str = "test",
    force_deploy: bool = False,
    deploy_mobile: bool = False,
    execute: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("deploy_app_test_and_hotfix requires a deploy message.")
    source_version = str(from_app_version or "test").strip() or "test"
    payload = {
        "appname": appname,
        "from_app_version": source_version,
        "force_deploy": bool(force_deploy),
        "message": clean_message,
        "deploy_mobile": bool(deploy_mobile),
    }
    result = _client(client).post("/appeditor/deploy_app_test_and_hotfix", payload, session, dry_run=not execute)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "app_version": source_version,
        "executed": execute,
        **result,
    }


def fetch_workload_usage_by_date(
    *,
    profile: str,
    start: str,
    end: str,
    granularity: str = "day",
    app_id: str | None = None,
    include_raw: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    payload = {
        "start_date_in_iso_format": _iso_datetime(start),
        "end_date_in_iso_format": _iso_datetime(end),
        "granularity": _bounded_granularity(granularity),
    }
    result = _post_profile_endpoint(
        profile=profile,
        endpoint="/appeditor/get_workload_usage_by_date",
        payload=payload,
        app_id=app_id,
        include_raw=include_raw,
        limit=500,
        client=client,
    )
    raw_items = result.get("items")
    items: list[Any] = raw_items if isinstance(raw_items, list) else []
    result["summary"] = {
        "total_workload_used": _sum_numeric(items, "total_workload_used", "workload_used"),
        "live_workload_used": _sum_numeric(items, "live_workload_used"),
        "test_workload_used": _sum_numeric(items, "test_workload_used"),
    }
    return result


def fetch_workload_usage_breakdown(
    *,
    profile: str,
    start: str,
    end: str,
    granularity: str = "day",
    tag1: str | None = None,
    tag2: str | None = None,
    platform: str = "web_and_mobile",
    app_id: str | None = None,
    include_raw: bool = False,
    limit: int = 50,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    payload = {
        "start_date_in_iso_format": _iso_datetime(start),
        "end_date_in_iso_format": _iso_datetime(end),
        "tag1": str(tag1).strip() if tag1 not in (None, "") else None,
        "tag2": str(tag2).strip() if tag2 not in (None, "") else None,
        "granularity": _bounded_granularity(granularity),
        "platformToggleValue": _bounded_platform(platform),
        "hasOnlyOneApp": False,
    }
    result = _post_profile_endpoint(
        profile=profile,
        endpoint="/appeditor/get_workload_usage_breakdown",
        payload=payload,
        app_id=app_id,
        include_raw=include_raw,
        limit=limit,
        client=client,
    )
    raw_items = result.get("items")
    items: list[Any] = raw_items if isinstance(raw_items, list) else []
    result["summary"] = {
        "total_workload_used": _sum_numeric(items, "workload_used", "total_workload_used"),
        "top_breakdown": _top_items(items, key="workload_used", limit=min(int(limit), 10)),
    }
    return result


def fetch_jetstream_logs(
    *,
    profile: str,
    start: str | int | float,
    end: str | int | float,
    app_id: str | None = None,
    app_version: str | None = None,
    messages: list[str] | None = None,
    ascending: bool = True,
    is_state_ar: bool = True,
    include_raw: bool = False,
    limit: int = 100,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    version = _resolve_metrics_app_version(app_version)
    session = _load_session_for_profile(profile)
    appname = _resolve_app_id(profile, session, app_id)
    payload = {
        "tags": {
            "message": messages or DEFAULT_LOG_MESSAGES,
            "appname": appname,
            "app_version": version,
        },
        "ascending": bool(ascending),
        "after": _epoch_ms(start),
        "before": _epoch_ms(end),
        "is_state_ar": bool(is_state_ar),
    }
    result = _client(client).post("/appeditor/get_jetstream_logs", payload, session)
    compact = _compact_result(result, include_raw=include_raw, limit=limit)
    return {
        "ok": result.get("ok"),
        "profile": profile,
        "app_id": appname,
        "app_version": version,
        "defaulted_to_live": app_version in (None, ""),
        **compact,
    }


def fetch_plan_usage(
    *,
    profile: str,
    app_id: str | None = None,
    include_raw: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    return _post_profile_endpoint(
        profile=profile,
        endpoint="/appeditor/get_current_app_plan_usage",
        payload={},
        app_id=app_id,
        include_raw=include_raw,
        client=client,
    )


def fetch_workflow_runs(
    *,
    profile: str,
    app_id: str | None = None,
    platform: str = "web_and_mobile",
    include_raw: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    return _post_profile_endpoint(
        profile=profile,
        endpoint="/appeditor/get_workflow_runs",
        payload={"platform": _bounded_platform(platform)},
        app_id=app_id,
        include_raw=include_raw,
        client=client,
    )


def fetch_storage_usage(
    *,
    profile: str,
    app_id: str | None = None,
    refresh: bool = True,
    include_raw: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    return _post_profile_endpoint(
        profile=profile,
        endpoint="/appeditor/get_storage_size",
        payload={"refresh": bool(refresh)},
        app_id=app_id,
        include_raw=include_raw,
        client=client,
    )


def read_time_series(
    *,
    profile: str,
    start: str | int | float,
    end: str | int | float,
    metric: str,
    resolution: float | None = None,
    app_id: str | None = None,
    use_observe: bool = True,
    include_raw: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    start_ms = _epoch_ms(start)
    end_ms = _epoch_ms(end)
    resolved_resolution = resolution
    if resolved_resolution is None:
        resolved_resolution = max(1.0, (end_ms - start_ms) / 36.0 / 1000.0)
    return _post_profile_endpoint(
        profile=profile,
        endpoint="/appeditor/read_time_series",
        payload={
            "start": start_ms,
            "end": end_ms,
            "resolution": float(resolved_resolution),
            "metric": str(metric or "").strip(),
            "use_observe": bool(use_observe),
        },
        app_id=app_id,
        include_raw=include_raw,
        client=client,
    )


def performance_audit(
    *,
    profile: str,
    start: str | None = None,
    end: str | None = None,
    app_id: str | None = None,
    app_version: str | None = None,
    granularity: str = "day",
    platform: str = "web_and_mobile",
    include_logs: bool = True,
    include_raw: bool = False,
    client: BubbleEditorApiClient | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start_iso = _iso_datetime(start, default=now - timedelta(days=30))
    end_iso = _iso_datetime(end, default=now)
    api_client = _client(client)
    by_date = fetch_workload_usage_by_date(
        profile=profile,
        app_id=app_id,
        start=start_iso,
        end=end_iso,
        granularity=granularity,
        include_raw=include_raw,
        client=api_client,
    )
    breakdown = fetch_workload_usage_breakdown(
        profile=profile,
        app_id=app_id,
        start=start_iso,
        end=end_iso,
        granularity=granularity,
        platform=platform,
        include_raw=include_raw,
        limit=25,
        client=api_client,
    )
    workflow_runs = fetch_workflow_runs(
        profile=profile,
        app_id=app_id,
        platform=platform,
        include_raw=include_raw,
        client=api_client,
    )
    plan_usage = fetch_plan_usage(profile=profile, app_id=app_id, include_raw=include_raw, client=api_client)
    storage = fetch_storage_usage(profile=profile, app_id=app_id, include_raw=include_raw, client=api_client)
    logs = None
    if include_logs:
        logs = fetch_jetstream_logs(
            profile=profile,
            app_id=app_id,
            app_version=app_version,
            start=start_iso,
            end=end_iso,
            limit=100,
            include_raw=include_raw,
            client=api_client,
        )

    top_breakdown = breakdown.get("summary", {}).get("top_breakdown", [])
    recommendations: list[dict[str, Any]] = []
    for item in top_breakdown[:5] if isinstance(top_breakdown, list) else []:
        tag = str(item.get("tag") or item.get("name") or item.get("tag1") or "workload").strip()
        recommendations.append(
            {
                "priority": len(recommendations) + 1,
                "area": tag,
                "reason": "High workload usage in Bubble's editor breakdown.",
                "suggestion": "Inspect the related workflows/searches, remove repeated searches or writes, and batch/defer non-critical work.",
                "workload_used": item.get("workload_used") or item.get("total_workload_used"),
                "activity_count": item.get("activity_count"),
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": 1,
                "area": "workload_breakdown",
                "reason": "No dominant workload bucket was returned or the app has little usage in the selected window.",
                "suggestion": "Run a wider date range or inspect workflow runs/logs for specific hotspots.",
            }
        )

    ok = all(
        bool(item.get("ok"))
        for item in [by_date, breakdown, workflow_runs, plan_usage, storage, *([logs] if logs else [])]
        if isinstance(item, dict)
    )
    return {
        "ok": ok,
        "profile": profile,
        "app_id": by_date.get("app_id"),
        "app_version": _resolve_metrics_app_version(app_version),
        "defaulted_to_live": app_version in (None, ""),
        "window": {"start": start_iso, "end": end_iso, "granularity": _bounded_granularity(granularity)},
        "summary": {
            "workload": by_date.get("summary"),
            "top_breakdown": top_breakdown,
            "recommendation_count": len(recommendations),
        },
        "recommendations": recommendations,
        "sources": {
            "workload_by_date": by_date,
            "workload_breakdown": breakdown,
            "workflow_runs": workflow_runs,
            "plan_usage": plan_usage,
            "storage": storage,
            **({"logs": logs} if logs is not None else {}),
        },
    }
