"""Local profile-scoped storage for scheduled deploys."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.browser_automation.models import ScheduledDeployPreview, ScheduledDeployRecord
from bubble_mcp.core.config import get_config_dir

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _safe_segment(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text or not SAFE_ID_RE.match(text) or ".." in text:
        raise ValueError(f"Invalid {label}: {value}")
    return text


def profile_deploy_root(profile: str) -> Path:
    safe_profile = _safe_segment(profile, "profile")
    return get_config_dir() / "profiles" / safe_profile / "deploys"


def previews_dir(profile: str) -> Path:
    return profile_deploy_root(profile) / "previews"


def scheduled_dir(profile: str) -> Path:
    return profile_deploy_root(profile) / "scheduled"


def evidence_dir(profile: str, deploy_id: str) -> Path:
    return profile_deploy_root(profile) / "evidence" / _safe_segment(deploy_id, "deploy_id")


def history_path(profile: str) -> Path:
    return profile_deploy_root(profile) / "history.jsonl"


def preview_path(profile: str, preview_id: str) -> Path:
    return previews_dir(profile) / f"{_safe_segment(preview_id, 'preview_id')}.json"


def scheduled_path(profile: str, deploy_id: str) -> Path:
    return scheduled_dir(profile) / f"{_safe_segment(deploy_id, 'deploy_id')}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def save_preview(preview: ScheduledDeployPreview) -> Path:
    return _write_json(preview_path(preview.profile, preview.preview_id), preview.to_dict())


def load_preview(profile: str, preview_id: str) -> ScheduledDeployPreview:
    path = preview_path(profile, preview_id)
    if not path.exists():
        raise FileNotFoundError(f"Scheduled deploy preview not found: {preview_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Malformed scheduled deploy preview JSON at {path}")
    return ScheduledDeployPreview(
        preview_id=str(payload.get("preview_id") or ""),
        profile=str(payload.get("profile") or ""),
        app_id=str(payload.get("app_id") or ""),
        app_version=str(payload.get("app_version") or "test"),
        scheduled_at=str(payload.get("scheduled_at") or ""),
        timezone=str(payload.get("timezone") or ""),
        message=str(payload.get("message") or ""),
        retry_count=int(payload.get("retry_count") or 0),
        headless=bool(payload.get("headless")),
        wait_seconds=int(payload.get("wait_seconds") or 120),
        created_at=str(payload.get("created_at") or ""),
    )


def delete_preview(profile: str, preview_id: str) -> None:
    path = preview_path(profile, preview_id)
    if path.exists():
        path.unlink()


def save_scheduled_record(record: ScheduledDeployRecord) -> Path:
    return _write_json(scheduled_path(record.profile, record.deploy_id), record.to_dict())


def load_scheduled_record(profile: str, deploy_id: str) -> ScheduledDeployRecord:
    path = scheduled_path(profile, deploy_id)
    if not path.exists():
        raise FileNotFoundError(f"Scheduled deploy not found: {deploy_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Malformed scheduled deploy JSON at {path}")
    return ScheduledDeployRecord.from_dict(payload)


def delete_scheduled_record(profile: str, deploy_id: str) -> None:
    path = scheduled_path(profile, deploy_id)
    if path.exists():
        path.unlink()


def append_history(profile: str, payload: dict[str, Any]) -> Path:
    path = history_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def list_scheduled_records(profile: str) -> list[ScheduledDeployRecord]:
    directory = scheduled_dir(profile)
    if not directory.exists():
        return []
    records: list[ScheduledDeployRecord] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            records.append(ScheduledDeployRecord.from_dict(payload))
    return records


def list_history_records(profile: str, *, limit: int = 50, include_cancelled: bool = True) -> list[dict[str, Any]]:
    path = history_path(profile)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        if not include_cancelled and payload.get("status") == "cancelled":
            continue
        records.append(payload)
    return records[-max(1, limit) :]
