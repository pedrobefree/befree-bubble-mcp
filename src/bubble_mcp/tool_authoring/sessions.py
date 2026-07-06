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
ACTIVE_SESSION_FILENAME = "active-session.json"
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


def _active_session_path() -> Path:
    return get_config_dir() / "tool-authoring" / ACTIVE_SESSION_FILENAME


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


def set_active_authoring_session(session_id: str) -> dict[str, object]:
    session = _load_session(session_id)
    path = _active_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"session_id": session.id, "activated_at": _utc_now_iso()}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": True, **payload}


def active_authoring_session_id() -> str | None:
    path = _active_session_path()
    if path.is_symlink():
        raise ValueError(f"Active tool-authoring session file cannot be a symlink: {path}")
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected active tool-authoring session JSON object in {path}")
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return None
    safe_session_id = _validate_safe_segment(session_id, label="session_id")
    _load_session(safe_session_id)
    return safe_session_id


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
    set_active_authoring_session(session.id)
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
    bodies = _capture_bodies(session)
    changes: list[object] = []
    app_id: object = None
    app_version: object = None
    for body in bodies:
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


def _capture_bodies(session: ToolAuthoringSession) -> list[dict[str, object]]:
    captures = _captures_dir(session.id)
    bodies: list[dict[str, object]] = []
    for filename in session.capture_files:
        safe_filename = _validate_safe_segment(filename, label="capture filename")
        path = captures / safe_filename
        _ensure_under_base(path, captures)
        payload = _load_json_object(path)
        bodies.append(_extract_write_body(payload))
    return bodies


def _path_parts_from_change(change: object) -> list[str]:
    if not isinstance(change, dict):
        return []
    path = change.get("path_array") or change.get("path") or []
    return [str(part) for part in path] if isinstance(path, list) else []


def _intent_name_from_change(change: object) -> str | None:
    if not isinstance(change, dict):
        return None
    intent = change.get("intent")
    if isinstance(intent, dict):
        name = str(intent.get("name") or "").strip()
        return name or None
    return None


def _body_keys_from_change(change: object) -> list[str]:
    if not isinstance(change, dict):
        return []
    body = change.get("body")
    if not isinstance(body, dict):
        return []
    return sorted(str(key) for key in body)


def _unique_limited(values: list[str], *, limit: int = 20) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
        if len(unique) >= limit:
            break
    return unique


def _api_connector_ids(paths: list[list[str]]) -> dict[str, list[str]]:
    collections: list[str] = []
    calls: list[str] = []
    for path in paths:
        for marker in ("apiconnector2", "api_connector"):
            if marker not in path:
                continue
            marker_index = path.index(marker)
            if len(path) > marker_index + 1 and path[marker_index + 1] != "calls":
                collections.append(path[marker_index + 1])
            if "calls" in path:
                call_index = path.index("calls")
                if len(path) > call_index + 1:
                    calls.append(path[call_index + 1])
    return {
        "collections": _unique_limited(collections),
        "calls": _unique_limited(calls),
    }


def _finalization_questions(session: ToolAuthoringSession, paths: list[list[str]]) -> list[str]:
    normalized = f"{session.intent} {session.target}".lower()
    questions = [
        "Qual deve ser o nome final da tool exportada e seu namespace no extension pack?",
        "Quais argumentos devem ser obrigatorios e quais devem ter default ou aceitar inferencia pelo contexto?",
        "A tool deve ficar inicialmente somente em preview/dry-run ou ja pode aceitar execute=true em ambiente de teste?",
    ]
    if "api" in normalized or any("apiconnector2" in path or "api_connector" in path for path in paths):
        questions.extend(
            [
                "A tool deve criar uma chamada nova, atualizar uma chamada existente ou suportar os dois modos?",
                "Quais campos da chamada de API devem ser parametrizados: nome, metodo, URL, headers, query params, body, autenticacao e inicializacao da resposta?",
                "Ha variacoes de autenticacao ou payload que devem virar fixtures separadas antes de publicar a tool?",
            ]
        )
    return questions


def _testing_guidance(session: ToolAuthoringSession) -> list[str]:
    return [
        "Validar o extension pack gerado com bubble_extension_validate antes de importar.",
        "Importar e habilitar o pack em um config/profile de teste com bubble_extension_import e bubble_extension_enable.",
        "Executar a tool exportada primeiro com execute=false para revisar o payload compilado sem escrever no Bubble.",
        f"Executar em ambiente de teste do profile {session.profile} somente depois do preview estar correto.",
        "Atualizar o cache/contexto do profile e verificar no export .bubble se a alteracao criada pela tool aparece no local esperado.",
        "Registrar pelo menos uma fixture de sucesso e uma fixture de erro/argumento incompleto para evitar regressao.",
    ]


def finalize_authoring_session(session_id: str) -> dict[str, object]:
    session = _load_session(session_id)
    bodies = _capture_bodies(session)
    classification = _aggregate_classification(session)
    changes: list[dict[str, object]] = []
    for body in bodies:
        body_changes = body.get("changes")
        if not isinstance(body_changes, list):
            continue
        changes.extend(change for change in body_changes if isinstance(change, dict))
    paths = [_path_parts_from_change(change) for change in changes]
    path_strings = ["/".join(path) for path in paths if path]
    intents = _unique_limited([intent for change in changes if (intent := _intent_name_from_change(change))])
    body_keys = _unique_limited([key for change in changes for key in _body_keys_from_change(change)])
    app_ids = _unique_limited(
        [
            str(value)
            for body in bodies
            for value in [body.get("appname") or body.get("app_id") or body.get("appId")]
            if value
        ]
    )
    app_versions = _unique_limited(
        [
            str(value)
            for body in bodies
            for value in [body.get("app_version") or body.get("appVersion")]
            if value
        ]
    )
    api_ids = _api_connector_ids(paths)
    has_captures = bool(session.capture_files)
    learned: list[str] = []
    if has_captures:
        learned.append(
            f"A sessao capturou {len(session.capture_files)} arquivo(s) com {classification.get('change_count', 0)} mudanca(s) Bubble."
        )
    if intents:
        learned.append(f"Intents observados: {', '.join(intents)}.")
    families = classification.get("families")
    if isinstance(families, list) and families:
        learned.append(f"Familias classificadas: {', '.join(str(item) for item in families)}.")
    if path_strings:
        learned.append(f"Principais caminhos Bubble: {', '.join(_unique_limited(path_strings, limit=5))}.")
    if api_ids["collections"] or api_ids["calls"]:
        learned.append(
            "Foram detectados IDs do API Connector: "
            f"collections={api_ids['collections'] or []}, calls={api_ids['calls'] or []}."
        )
    if not learned:
        learned.append("Nenhuma captura valida foi adicionada a sessao ainda.")
    return {
        "ok": has_captures,
        "status": "ready_for_review" if has_captures else "needs_captures",
        "session": session.to_dict(),
        "active": active_authoring_session_id() == session.id,
        "classification": classification,
        "capture_summary": {
            "capture_count": len(session.capture_files),
            "change_count": classification.get("change_count", 0),
            "app_ids": app_ids,
            "app_versions": app_versions,
            "intents": intents,
            "body_keys": body_keys,
            "paths": _unique_limited(path_strings, limit=20),
            "api_connector_ids": api_ids,
        },
        "understanding": {
            "intent": session.intent,
            "target": session.target,
            "learned": learned,
            "next_step": "Responder as perguntas pendentes e gerar o contrato/fixture do extension pack.",
        },
        "questions": _finalization_questions(session, paths),
        "testing_guidance": _testing_guidance(session),
    }


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
        "active": active_authoring_session_id() == session.id,
        "classification": _aggregate_classification(session),
    }
