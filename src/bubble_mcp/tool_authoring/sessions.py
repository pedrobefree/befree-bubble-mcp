"""Local storage and classification for tool-authoring sessions."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.harness.expert import classify_editor_payload
from bubble_mcp.tool_authoring.models import ToolAuthoringSession


SESSION_FILENAME = "session.json"
_SAFE_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return text or fallback


def _validate_safe_segment(value: str, *, label: str) -> str:
    segment = str(value or "").strip()
    if not segment:
        raise ValueError(f"{label} is required.")
    if segment in {".", ".."} or "/" in segment or "\\" in segment:
        raise ValueError(f"{label} must be a safe path segment: {value}")
    if not _SAFE_SEGMENT_PATTERN.match(segment):
        raise ValueError(f"{label} must be a safe path segment: {value}")
    return segment


def _sessions_dir() -> Path:
    return get_config_dir() / "tool-authoring" / "sessions"


def _ensure_under_base(path: Path, base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    resolved_base = base.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Tool-authoring path escapes storage directory: {path}") from exc
    return resolved_path


def _session_dir(session_id: str) -> Path:
    safe_session_id = _validate_safe_segment(session_id, label="session_id")
    sessions = _sessions_dir()
    path = sessions / safe_session_id
    _ensure_under_base(path, sessions)
    return path


def _session_path(session_id: str) -> Path:
    return _session_dir(session_id) / SESSION_FILENAME


def _captures_dir(session_id: str) -> Path:
    captures = _session_dir(session_id) / "captures"
    _ensure_under_base(captures, _session_dir(session_id))
    captures.mkdir(parents=True, exist_ok=True)
    return captures


def _load_session(session_id: str) -> ToolAuthoringSession:
    path = _session_path(session_id)
    if path.is_symlink():
        raise ValueError(f"Tool-authoring session file cannot be a symlink: {path}")
    if not path.exists():
        raise ValueError(f"Unknown tool-authoring session: {session_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected session JSON object in {path}")
    session = ToolAuthoringSession.from_dict(payload)
    if session.id != _validate_safe_segment(session_id, label="session_id"):
        raise ValueError(f"Session id mismatch in {path}")
    return session


def _write_session(session: ToolAuthoringSession) -> None:
    path = _session_path(session.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _new_session_id(target: str) -> str:
    date = datetime.now(UTC).strftime("%Y%m%d")
    target_slug = _slug(target, fallback="candidate")
    suffix = uuid4().hex[:8]
    return _validate_safe_segment(f"toolwiz_{date}_{target_slug}_{suffix}", label="session_id")


def create_authoring_session(*, intent: str, target: str, profile: str) -> ToolAuthoringSession:
    normalized_intent = str(intent or "").strip()
    normalized_target = str(target or "").strip()
    normalized_profile = str(profile or "").strip()
    if not normalized_intent:
        raise ValueError("Tool-authoring session intent is required.")
    if not normalized_target:
        raise ValueError("Tool-authoring session target is required.")
    if not normalized_profile:
        raise ValueError("Tool-authoring session profile is required.")
    session = ToolAuthoringSession(
        id=_new_session_id(normalized_target),
        intent=normalized_intent,
        target=normalized_target,
        profile=normalized_profile,
        created_at=_utc_now_iso(),
        capture_files=[],
    )
    _write_session(session)
    _captures_dir(session.id)
    return session


def _resolve_capture_input(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ValueError(f"Capture input cannot be a symlink: {path}")
    resolved = expanded.resolve(strict=True)
    if resolved.is_symlink():
        raise ValueError(f"Capture input cannot be a symlink: {path}")
    return resolved


def _load_json_object(path: Path) -> dict[str, object]:
    resolved = _resolve_capture_input(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected capture JSON object in {path}")
    return payload


def _extract_write_body(payload: dict[str, object]) -> dict[str, object]:
    candidates: list[object] = [
        payload.get("payload"),
        payload.get("write_payload"),
        payload.get("body"),
        payload.get("requestBody"),
        payload.get("request_body"),
    ]
    request = payload.get("request")
    if isinstance(request, dict):
        candidates.extend([request.get("payload"), request.get("body")])
    for candidate in candidates:
        if isinstance(candidate, dict):
            body = candidate.get("body") if isinstance(candidate.get("body"), dict) else candidate
            if isinstance(body, dict) and isinstance(body.get("changes"), list):
                return body
    raise ValueError("Capture file does not contain a Bubble editor write body with changes.")


def _safe_capture_filename(source: Path, index: int) -> str:
    stem = _slug(source.stem, fallback="capture")
    suffix = source.suffix if source.suffix.lower() == ".json" else ".json"
    return f"{index:04d}_{stem}{suffix}"


def _safe_capture_label_filename(label: str, index: int) -> str:
    stem = _slug(Path(label).stem, fallback="capture")
    return f"{index:04d}_{stem}.json"


def _copy_capture(session: ToolAuthoringSession, source: Path) -> str:
    source_resolved = _resolve_capture_input(source)
    captures = _captures_dir(session.id)
    filename = _safe_capture_filename(source_resolved, len(session.capture_files) + 1)
    target = captures / filename
    _ensure_under_base(target, captures)
    shutil.copy2(source_resolved, target)
    return filename


def _write_capture_payload(session: ToolAuthoringSession, payload: dict[str, object], source_label: str) -> str:
    captures = _captures_dir(session.id)
    filename = _safe_capture_label_filename(source_label, len(session.capture_files) + 1)
    target = captures / filename
    _ensure_under_base(target, captures)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return filename


def _aggregate_classification(session: ToolAuthoringSession) -> dict[str, object]:
    captures = _captures_dir(session.id)
    changes: list[object] = []
    app_id: object = None
    app_version: object = None
    for filename in session.capture_files:
        safe_filename = _validate_safe_segment(filename, label="capture filename")
        path = captures / safe_filename
        _ensure_under_base(path, captures)
        payload = _load_json_object(path)
        body = _extract_write_body(payload)
        body_changes = body.get("changes")
        if isinstance(body_changes, list):
            changes.extend(body_changes)
        app_id = app_id or body.get("appname") or body.get("app_id") or body.get("appId")
        app_version = app_version or body.get("app_version") or body.get("appVersion")
    classification_payload = {
        "appname": app_id,
        "app_version": app_version,
        "changes": changes,
    }
    return classify_editor_payload(classification_payload)


def append_capture_to_authoring_session(session_id: str, capture_file: Path) -> dict[str, object]:
    session = _load_session(session_id)
    payload = _load_json_object(capture_file)
    body = _extract_write_body(payload)
    classification = classify_editor_payload(body)
    filename = _copy_capture(session, capture_file)
    updated_session = ToolAuthoringSession(
        id=session.id,
        intent=session.intent,
        target=session.target,
        profile=session.profile,
        created_at=session.created_at,
        capture_files=[*session.capture_files, filename],
    )
    _write_session(updated_session)
    return {
        "ok": True,
        "session_id": updated_session.id,
        "capture_file": filename,
        "classification": classification,
    }


def append_capture_payload_to_authoring_session(
    session_id: str,
    payload: dict[str, object],
    *,
    source_label: str = "extension-capture",
) -> dict[str, object]:
    session = _load_session(session_id)
    body = _extract_write_body(payload)
    classification = classify_editor_payload(body)
    filename = _write_capture_payload(session, payload, source_label)
    updated_session = ToolAuthoringSession(
        id=session.id,
        intent=session.intent,
        target=session.target,
        profile=session.profile,
        created_at=session.created_at,
        capture_files=[*session.capture_files, filename],
    )
    _write_session(updated_session)
    return {
        "ok": True,
        "session_id": updated_session.id,
        "capture_file": filename,
        "classification": classification,
    }


def describe_authoring_session(session_id: str) -> dict[str, object]:
    session = _load_session(session_id)
    return {
        "ok": True,
        "session": session.to_dict(),
        "classification": _aggregate_classification(session),
    }
