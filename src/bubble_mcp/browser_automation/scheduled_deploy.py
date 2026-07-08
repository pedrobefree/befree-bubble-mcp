"""Preview-first scheduled deploy workflow."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bubble_mcp.browser_automation.models import ScheduledDeployPreview, ScheduledDeployRecord
from bubble_mcp.browser_automation.store import (
    append_history,
    delete_preview,
    delete_scheduled_record,
    evidence_dir,
    list_history_records,
    list_scheduled_records,
    load_preview,
    load_scheduled_record,
    save_preview,
    save_scheduled_record,
)
from bubble_mcp.core.config import load_settings, resolve_profile

APP_VERSION = "test"

_timers_lock = threading.Lock()
_timers: dict[str, threading.Timer] = {}


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_timezone() -> str:
    local = datetime.now().astimezone().tzinfo
    key = getattr(local, "key", None)
    if key:
        return str(key)
    name = datetime.now().astimezone().tzname()
    return str(name or "local")


def _parse_datetime(value: str, timezone_name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("scheduled_at is required.")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("scheduled_at must be an ISO datetime.") from exc
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except Exception:
            parsed = parsed.astimezone().replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(UTC)


def _id(prefix: str, *parts: str) -> str:
    stamp = _now().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{stamp}_{digest}"


def _resolve_profile(profile_name: str) -> tuple[str, str]:
    settings = load_settings()
    profile = resolve_profile(settings, profile_name)
    if profile is None:
        raise ValueError(f"Unknown profile: {profile_name}")
    return profile.name, profile.app_id


def _timer_key(profile: str, deploy_id: str) -> str:
    return f"{profile}:{deploy_id}"


def _arm_timer(record: ScheduledDeployRecord, executor: Callable[[ScheduledDeployRecord], dict[str, Any]] | None) -> None:
    if executor is None:
        return
    scheduled_at = datetime.fromisoformat(record.scheduled_at.replace("Z", "+00:00"))
    delay = max(0.0, (scheduled_at - _now()).total_seconds())
    key = _timer_key(record.profile, record.deploy_id)

    def run() -> None:
        with _timers_lock:
            _timers.pop(key, None)
        result = executor(record)
        status = "executed" if result.get("ok") else "failed"
        finished = ScheduledDeployRecord(
            **{
                **record.to_dict(),
                "status": status,
                "updated_at": _now_iso(),
                "executed_at": _now_iso(),
                "error": str(result.get("error") or "") or None,
                "evidence_dir": str(evidence_dir(record.profile, record.deploy_id)),
            }
        )
        delete_scheduled_record(record.profile, record.deploy_id)
        append_history(record.profile, finished.to_dict())

    timer = threading.Timer(delay, run)
    timer.daemon = True
    with _timers_lock:
        previous = _timers.get(key)
        if previous:
            previous.cancel()
        _timers[key] = timer
    timer.start()


def schedule_deploy(
    *,
    profile: str,
    scheduled_at: str,
    message: str,
    execute: bool = False,
    confirm: bool = False,
    preview_id: str | None = None,
    retry_count: int = 0,
    headless: bool = False,
    wait_seconds: int = 120,
    executor: Callable[[ScheduledDeployRecord], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_profile, app_id = _resolve_profile(profile)
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("message is required.")
    timezone_name = _local_timezone()
    scheduled_dt = _parse_datetime(scheduled_at, timezone_name)
    normalized_scheduled_at = scheduled_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    retry = max(0, int(retry_count or 0))
    wait = max(1, int(wait_seconds or 120))

    if not execute:
        preview = ScheduledDeployPreview(
            preview_id=_id("deploy_preview", resolved_profile, app_id, normalized_scheduled_at, clean_message),
            profile=resolved_profile,
            app_id=app_id,
            app_version=APP_VERSION,
            scheduled_at=normalized_scheduled_at,
            timezone=timezone_name,
            message=clean_message,
            retry_count=retry,
            headless=bool(headless),
            wait_seconds=wait,
            created_at=_now_iso(),
        )
        path = save_preview(preview)
        return {
            "ok": True,
            "mode": "preview",
            "preview": preview.to_dict(),
            "preview_path": str(path),
            "confirmation_required": True,
            "next_mcp_call": {
                "tool": "bubble_schedule_deploy",
                "arguments": {
                    "profile": resolved_profile,
                    "scheduled_at": normalized_scheduled_at,
                    "message": clean_message,
                    "execute": True,
                    "confirm": True,
                    "preview_id": preview.preview_id,
                },
            },
        }

    if not confirm:
        return {"ok": False, "error": "scheduled_deploy_requires_confirmation", "confirmation_required": True}
    if not preview_id:
        return {"ok": False, "error": "scheduled_deploy_requires_preview_id", "confirmation_required": True}
    preview = load_preview(resolved_profile, preview_id)
    if preview.app_id != app_id or preview.message != clean_message or preview.scheduled_at != normalized_scheduled_at:
        return {"ok": False, "error": "scheduled_deploy_preview_mismatch", "confirmation_required": True}

    deploy_id = _id("deploy", resolved_profile, app_id, normalized_scheduled_at, clean_message)
    created_at = _now_iso()
    record = ScheduledDeployRecord(
        deploy_id=deploy_id,
        profile=resolved_profile,
        app_id=app_id,
        app_version=APP_VERSION,
        scheduled_at=normalized_scheduled_at,
        timezone=preview.timezone,
        message=clean_message,
        retry_count=preview.retry_count,
        headless=preview.headless,
        wait_seconds=preview.wait_seconds,
        status="scheduled",
        created_at=created_at,
        updated_at=created_at,
        preview_id=preview.preview_id,
    )
    path = save_scheduled_record(record)
    append_history(resolved_profile, {**record.to_dict(), "event": "scheduled"})
    delete_preview(resolved_profile, preview.preview_id)
    _arm_timer(record, executor)
    return {
        "ok": True,
        "mode": "scheduled",
        "deploy": record.to_dict(),
        "deploy_path": str(path),
        "history_path": str(path.parent.parent / "history.jsonl"),
    }


def list_scheduled_deploys(*, profile: str) -> dict[str, Any]:
    resolved_profile, _app_id = _resolve_profile(profile)
    records = [record.to_dict() for record in list_scheduled_records(resolved_profile)]
    return {"ok": True, "profile": resolved_profile, "scheduled": records, "count": len(records)}


def cancel_scheduled_deploy(*, profile: str, deploy_id: str) -> dict[str, Any]:
    resolved_profile, _app_id = _resolve_profile(profile)
    record = load_scheduled_record(resolved_profile, deploy_id)
    key = _timer_key(resolved_profile, deploy_id)
    with _timers_lock:
        timer = _timers.pop(key, None)
        if timer:
            timer.cancel()
    cancelled = ScheduledDeployRecord(
        **{
            **record.to_dict(),
            "status": "cancelled",
            "updated_at": _now_iso(),
            "cancelled_at": _now_iso(),
        }
    )
    delete_scheduled_record(resolved_profile, deploy_id)
    append_history(resolved_profile, {**cancelled.to_dict(), "event": "cancelled"})
    return {"ok": True, "profile": resolved_profile, "cancelled": True, "deploy": cancelled.to_dict()}


def deploy_history(*, profile: str, limit: int = 50, include_cancelled: bool = True) -> dict[str, Any]:
    resolved_profile, _app_id = _resolve_profile(profile)
    records = list_history_records(resolved_profile, limit=limit, include_cancelled=include_cancelled)
    return {"ok": True, "profile": resolved_profile, "history": records, "count": len(records)}


def write_evidence(profile: str, deploy_id: str, payload: dict[str, Any]) -> Path:
    directory = evidence_dir(profile, deploy_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "result.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
