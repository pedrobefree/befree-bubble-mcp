"""Audit storage for skill runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.skills.store import skill_runs_dir


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    return f"skillrun_{datetime.now(UTC).strftime('%Y%m%d')}_{uuid4().hex[:10]}"


def run_path(run_id: str) -> Path:
    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise ValueError(f"Skill run id must be a safe path segment: {run_id}")
    return skill_runs_dir() / f"{run_id}.json"


def save_run_record(record: dict[str, Any]) -> Path:
    run_id = str(record.get("run_id") or "")
    path = run_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_record = redact_sensitive(record)
    path.write_text(json.dumps(safe_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_run_record(run_id: str) -> dict[str, Any]:
    path = run_path(run_id)
    if not path.exists():
        raise ValueError(f"Unknown skill run: {run_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected skill run object in {path}")
    return payload
