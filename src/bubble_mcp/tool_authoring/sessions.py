"""Local storage and classification for tool-authoring sessions."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.core.config import get_config_dir
from bubble_mcp.extensions.validator import validate_extension_pack
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


def _generated_packs_dir() -> Path:
    return get_config_dir() / "tool-authoring" / "generated-packs"


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


def _next_authoring_action(session: ToolAuthoringSession) -> dict[str, object]:
    if not session.capture_files:
        return {
            "next_user_action": (
                "Open the Bubble editor, enable the Chrome companion, perform the target actions, "
                "then return and call bubble_tool_wizard_finalize for this session."
            ),
            "next_mcp_calls": [
                {"tool": "bubble_tool_wizard_finalize", "arguments": {"session_id": session.id}},
            ],
        }
    return {
        "next_user_action": (
            "Generate the candidate extension pack from this reviewed capture session. "
            "The tool will not appear in the catalog until the generated pack is imported and enabled."
        ),
        "next_mcp_calls": [
            {"tool": "bubble_tool_wizard_generate", "arguments": {"session_id": session.id}},
        ],
    }


def set_active_authoring_session(session_id: str) -> dict[str, object]:
    session = _load_session(session_id)
    path = _active_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"session_id": session.id, "activated_at": _utc_now_iso()}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        **payload,
        "capture_count": len(session.capture_files),
        **_next_authoring_action(session),
    }


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


def _default_extension_id(session: ToolAuthoringSession) -> str:
    return f"local.toolwiz.{_slug(session.target, fallback='tool')}.{session.id[-8:]}"


def _default_tool_name(session: ToolAuthoringSession, extension_id: str) -> str:
    return f"{extension_id}.{_slug(session.intent, fallback=session.target)}"


def _safe_tool_filename(tool_name: str) -> str:
    return f"{_slug(tool_name.split('.')[-1], fallback='generated_tool')}.tool.json"


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


def _generated_tool_input_schema(session: ToolAuthoringSession, body_keys: list[str]) -> dict[str, object]:
    properties: dict[str, object] = {
        "profile": {
            "type": "string",
            "description": "Local Bubble MCP profile to use for preview and future execution.",
        },
        "execute": {
            "type": "boolean",
            "description": "Execute the write after preview and validation. v1 generated tools must default to false.",
            "default": False,
        },
    }
    required = ["profile"]
    normalized = f"{session.intent} {session.target}".lower()
    if "api" in normalized:
        api_fields = {
            "collection_id": "Existing API Connector collection id. Omit to let a future runner create or infer one.",
            "collection_name": "Human name for a new or existing API Connector collection.",
            "name": "API call display name.",
            "method": "HTTP method for the API call.",
            "url": "API call URL.",
            "publish_as": "Bubble API Connector exposure mode, usually data or action.",
            "headers": "Optional HTTP headers object keyed by header name.",
            "query_params": "Optional query parameters object.",
            "body": "Optional request body template.",
            "body_params": "Optional API Connector body parameters object keyed by parameter name.",
            "authentication": "Optional API Connector authentication mode or reference.",
            "initialize": "Whether a future runner should initialize the call after creating/updating it.",
            "initialization_values": "Optional values used to initialize dynamic body/query/header parameters.",
        }
        for field, description in api_fields.items():
            properties[field] = {
                "type": "boolean"
                if field == "initialize"
                else "object"
                if field in {"headers", "query_params", "body_params", "initialization_values"}
                else "string",
                "description": description,
            }
        required.extend(field for field in ("name", "method", "url") if field in properties)
    else:
        properties["context"] = {
            "type": "string",
            "description": "Target page or reusable context, when the generated tool needs one.",
        }
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_authoring_extension_pack(
    session_id: str,
    *,
    extension_id: str | None = None,
    tool_name: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, object]:
    finalized = finalize_authoring_session(session_id)
    if not finalized.get("ok"):
        return {
            **finalized,
            "error": "tool_authoring_session_has_no_captures",
            "message": "Add captures to the tool-authoring session before generating an extension pack.",
        }
    session = _load_session(session_id)
    requested_extension_id = str(extension_id or "").strip() or _default_extension_id(session)
    safe_extension_id = _validate_safe_segment(requested_extension_id, label="extension_id")
    requested_tool_name = str(tool_name or "").strip() or _default_tool_name(session, safe_extension_id)
    if not requested_tool_name:
        raise ValueError("tool_name is required.")
    if "/" in requested_tool_name or "\\" in requested_tool_name:
        raise ValueError(f"tool_name must not contain path separators: {requested_tool_name}")

    base = output_dir.expanduser() if output_dir else _generated_packs_dir()
    if base.exists() and base.is_symlink():
        raise ValueError(f"Generated extension output directory cannot be a symlink: {base}")
    pack_path = base / safe_extension_id
    if pack_path.exists():
        if pack_path.is_symlink():
            raise ValueError(f"Generated extension pack path cannot be a symlink: {pack_path}")
        shutil.rmtree(pack_path)
    pack_path.mkdir(parents=True, exist_ok=True)

    raw_capture_summary = finalized.get("capture_summary")
    capture_summary: dict[str, object] = raw_capture_summary if isinstance(raw_capture_summary, dict) else {}
    raw_body_keys = capture_summary.get("body_keys")
    body_keys = raw_body_keys if isinstance(raw_body_keys, list) else []
    body_key_strings = [str(key) for key in body_keys]
    tool_relative = f"tools/{_safe_tool_filename(requested_tool_name)}"
    evidence_relative = "evidence/tool-authoring-summary.json"
    input_schema = _generated_tool_input_schema(session, body_key_strings)
    input_properties = input_schema.get("properties")
    supported_arguments = sorted(input_properties) if isinstance(input_properties, dict) else []
    manifest = {
        "id": safe_extension_id,
        "name": f"Generated Tool Authoring Pack - {session.target}",
        "version": "0.1.0",
        "bubbleMcpVersion": ">=0.1.0",
        "capabilities": ["tools", "evals"],
        "risk": "mutating",
        "author": "local-tool-wizard",
        "exports": {
            "tools": [tool_relative],
            "skills": [],
            "evals": [],
        },
    }
    tool_payload = {
        "name": requested_tool_name,
        "description": (
            f"Generated candidate tool from tool-authoring session {session.id}. "
            "Use execute=false for preview and review the captured evidence before implementing execution."
        ),
        "risk": "mutating",
        "inputSchema": input_schema,
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "template": redact_sensitive(
            {
                "kind": "appeditor_write",
                "family": session.target,
                "source_session_id": session.id,
                "intent": session.intent,
                "requiresValidation": True,
                "captured_intents": capture_summary.get("intents", []),
                "captured_paths": capture_summary.get("paths", []),
                "captured_body_keys": body_key_strings,
                "change_count": capture_summary.get("change_count", 0),
                "supported_arguments": supported_arguments,
                "execution_status": "preview_only_until_api_connector_runner_is_implemented",
                "status": "candidate_requires_review",
            }
        ),
    }
    evidence = redact_sensitive(
        {
            "session": session.to_dict(),
            "finalization": finalized,
            "source": "bubble_tool_wizard_generate",
            "generated_at": _utc_now_iso(),
        }
    )

    _write_json(pack_path / "extension.json", manifest)
    _write_json(pack_path / tool_relative, tool_payload)
    _write_json(pack_path / evidence_relative, evidence)
    validation = validate_extension_pack(pack_path)
    return {
        "ok": validation.ok,
        "session_id": session.id,
        "extension_id": safe_extension_id,
        "tool_name": requested_tool_name,
        "pack_path": str(pack_path),
        "manifest_path": str(pack_path / "extension.json"),
        "tool_path": str(pack_path / tool_relative),
        "evidence_path": str(pack_path / evidence_relative),
        "validation": validation.to_dict(),
        "next_user_action": (
            "Call bubble_extension_validate, bubble_extension_import, and bubble_extension_enable for the generated "
            "extension pack. After enabling, use bubble_extension_call for immediate preview; direct catalog exposure "
            "can require a fresh MCP client tool-list refresh."
        ),
        "catalog_visibility": (
            "bubble_tool_wizard_generate creates the pack only. The generated tool becomes available after "
            "bubble_extension_import and bubble_extension_enable. If the client does not expose dynamic tools "
            "as direct callables in the current session, use bubble_extension_call with the returned tool_name."
        ),
        "next_mcp_calls": [
            {"tool": "bubble_extension_validate", "arguments": {"path": str(pack_path)}},
            {"tool": "bubble_extension_import", "arguments": {"path": str(pack_path)}},
            {"tool": "bubble_extension_enable", "arguments": {"extension_id": safe_extension_id}},
            {
                "tool": "bubble_extension_call",
                "arguments": {
                    "tool": requested_tool_name,
                    "arguments": {"profile": session.profile, "execute": False},
                },
            },
        ],
    }


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
            "next_step": "Call bubble_tool_wizard_generate with this session_id to create the candidate extension pack.",
        },
        **_next_authoring_action(session),
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
        **_next_authoring_action(session),
    }
