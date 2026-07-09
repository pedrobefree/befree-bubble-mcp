"""Authenticated Bubble editor metadata endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.execution.client import (
    EDITOR_WRITE_TIMEOUT_SEC,
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
