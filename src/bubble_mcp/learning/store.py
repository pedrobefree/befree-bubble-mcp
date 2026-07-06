"""Append-only local store for consultative learning records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.learning.models import LearningRecord


VALID_SCOPES = {"global", "profile", "project", "extension"}


def learning_path() -> Path:
    return get_config_dir() / "learning" / "records.jsonl"


def _validate_scope(scope: str) -> str:
    normalized = str(scope or "").strip()
    if normalized not in VALID_SCOPES:
        raise ValueError(f"Learning record scope must be one of: {', '.join(sorted(VALID_SCOPES))}.")
    return normalized


def append_learning_record(
    *,
    scope: str,
    key: str,
    value: dict[str, Any] | None = None,
    source: str,
    confidence: str,
    profile: str | None = None,
    project: str | None = None,
    extension_id: str | None = None,
) -> LearningRecord:
    normalized_scope = _validate_scope(scope)
    normalized_profile = str(profile or "").strip() or None
    normalized_project = str(project or "").strip() or None
    normalized_extension_id = str(extension_id or "").strip() or None
    if normalized_scope == "profile" and not normalized_profile:
        raise ValueError("Learning record scope 'profile' requires profile.")
    if normalized_scope == "project" and not normalized_project:
        raise ValueError("Learning record scope 'project' requires project.")
    if normalized_scope == "extension" and not normalized_extension_id:
        raise ValueError("Learning record scope 'extension' requires extension_id.")
    normalized_key = str(key or "").strip()
    if not normalized_key:
        raise ValueError("Learning record key is required.")
    normalized_source = str(source or "").strip()
    if not normalized_source:
        raise ValueError("Learning record source is required.")
    normalized_confidence = str(confidence or "").strip()
    if not normalized_confidence:
        raise ValueError("Learning record confidence is required.")
    if value is not None and not isinstance(value, dict):
        raise ValueError("Learning record value must be a JSON object.")
    record = LearningRecord.create(
        scope=normalized_scope,
        key=normalized_key,
        value=value or {},
        source=normalized_source,
        confidence=normalized_confidence,
        profile=normalized_profile,
        project=normalized_project,
        extension_id=normalized_extension_id,
    )
    path = learning_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    return record


def list_learning_records(
    *,
    scope: str | None = None,
    profile: str | None = None,
    project: str | None = None,
    extension_id: str | None = None,
) -> list[LearningRecord]:
    path = learning_path()
    if not path.exists():
        return []
    scope_filter = _validate_scope(scope) if scope is not None else None
    profile_filter = str(profile or "").strip() or None
    project_filter = str(project or "").strip() or None
    extension_filter = str(extension_id or "").strip() or None
    records: list[LearningRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed learning record JSONL at {path}:{line_number}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                continue
            record = LearningRecord.from_dict(payload)
            if scope_filter and record.scope != scope_filter:
                continue
            if profile_filter and record.profile != profile_filter:
                continue
            if project_filter and record.project != project_filter:
                continue
            if extension_filter and record.extension_id != extension_filter:
                continue
            records.append(record)
    return records
