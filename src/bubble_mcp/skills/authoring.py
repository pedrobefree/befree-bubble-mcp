"""Friendly authoring sessions for executable skill contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.skills.validator import validate_skill_file


AUTHORING_SESSION_FILENAME = "session.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return text or fallback


def _session_id(objective: str) -> str:
    return f"skillwiz_{datetime.now(UTC).strftime('%Y%m%d')}_{_slug(objective, fallback='skill')[:32]}_{uuid4().hex[:8]}"


def _authoring_dir() -> Path:
    return get_config_dir() / "skills" / "authoring"


def _sessions_dir() -> Path:
    return _authoring_dir() / "sessions"


def _generated_dir() -> Path:
    return _authoring_dir() / "generated"


def _session_path(session_id: str) -> Path:
    if "/" in session_id or "\\" in session_id or session_id in {"", ".", ".."}:
        raise ValueError(f"Skill authoring session id must be a safe path segment: {session_id}")
    return _sessions_dir() / session_id / AUTHORING_SESSION_FILENAME


@dataclass(frozen=True)
class SkillAuthoringSession:
    id: str
    objective: str
    risk: str
    profile: str | None = None
    answers: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "objective": self.objective,
            "risk": self.risk,
            "answers": self.answers,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.profile:
            payload["profile"] = self.profile
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SkillAuthoringSession":
        answers = payload.get("answers")
        return cls(
            id=str(payload.get("id") or ""),
            objective=str(payload.get("objective") or ""),
            risk=str(payload.get("risk") or "read_only"),
            profile=str(payload.get("profile") or "") or None,
            answers=[dict(answer) for answer in answers if isinstance(answer, dict)]
            if isinstance(answers, list)
            else [],
            created_at=str(payload.get("created_at") or _utc_now_iso()),
            updated_at=str(payload.get("updated_at") or _utc_now_iso()),
        )


def _write_session(session: SkillAuthoringSession) -> None:
    path = _session_path(session.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_session(session_id: str) -> SkillAuthoringSession:
    path = _session_path(session_id)
    if not path.exists():
        raise ValueError(f"Unknown skill authoring session: {session_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected skill authoring session object in {path}")
    return SkillAuthoringSession.from_dict(payload)


def create_skill_authoring_session(
    *,
    objective: str,
    risk: str = "read_only",
    profile: str | None = None,
) -> dict[str, object]:
    normalized_objective = str(objective or "").strip()
    if not normalized_objective:
        raise ValueError("bubble_skill_author_start requires objective.")
    normalized_risk = str(risk or "read_only").strip()
    if normalized_risk not in {"read_only", "mutating", "destructive"}:
        raise ValueError("risk must be read_only, mutating, or destructive.")
    session = SkillAuthoringSession(
        id=_session_id(normalized_objective),
        objective=normalized_objective,
        risk=normalized_risk,
        profile=str(profile or "").strip() or None,
    )
    _write_session(session)
    return {
        "ok": True,
        "session": session.to_dict(),
        "next_question": "What should this skill produce for the user when it finishes?",
        "next_mcp_call": {"tool": "bubble_skill_author_update", "arguments": {"session_id": session.id}},
    }


def update_skill_authoring_session(
    session_id: str,
    *,
    answer: str,
    field: str | None = None,
) -> dict[str, object]:
    session = _load_session(session_id)
    normalized_answer = str(answer or "").strip()
    if not normalized_answer:
        raise ValueError("bubble_skill_author_update requires answer.")
    entry = {
        "field": str(field or "notes").strip() or "notes",
        "answer": normalized_answer,
        "recorded_at": _utc_now_iso(),
    }
    updated = SkillAuthoringSession(
        id=session.id,
        objective=session.objective,
        risk=session.risk,
        profile=session.profile,
        answers=[*session.answers, entry],
        created_at=session.created_at,
        updated_at=_utc_now_iso(),
    )
    _write_session(updated)
    return {
        "ok": True,
        "session": updated.to_dict(),
        "ready_to_generate": len(updated.answers) >= 1,
        "next_question": (
            "Any tools, app areas, gates, or outputs this skill must include? "
            "If not, call bubble_skill_author_generate."
        ),
    }


def _answer_text(session: SkillAuthoringSession) -> str:
    return " ".join(answer["answer"] for answer in session.answers if answer.get("answer"))


def _default_skill_id(session: SkillAuthoringSession) -> str:
    return _slug(session.objective, fallback="generated-skill")


def _skill_name(skill_id: str) -> str:
    return " ".join(part.capitalize() for part in skill_id.replace("_", "-").split("-") if part)


def _generated_skill_payload(session: SkillAuthoringSession, skill_id: str) -> dict[str, object]:
    answer_text = _answer_text(session)
    query = answer_text or session.objective
    allowed_tools = ["bubble_context_detect", "bubble_context_find"]
    steps: list[dict[str, object]] = [
        {
            "id": "refresh_context",
            "type": "tool",
            "tool": "bubble_context_detect",
            "args": {"profile": "{{inputs.profile}}", "force": True},
            "mode": "read",
        },
        {
            "id": "inspect_scope",
            "type": "tool",
            "tool": "bubble_context_find",
            "args": {"profile": "{{inputs.profile}}", "query": query, "include_metadata": False},
            "mode": "read",
            "dependsOn": ["refresh_context"],
        },
    ]
    gates: list[dict[str, object]] = [{"type": "evidence_required", "outputs": ["plan", "risk_summary"]}]
    approval: dict[str, object] = {}
    if session.risk in {"mutating", "destructive"}:
        approval = {"requiredFor": ["mutating", "destructive"], "mode": "plan_then_approve"}
        gates.insert(0, {"type": "approval_required", "whenRisk": ["mutating", "destructive"]})
    return {
        "id": skill_id,
        "name": _skill_name(skill_id),
        "version": "0.1.0",
        "description": session.objective,
        "risk": session.risk,
        "inputs": {
            "profile": {"type": "string", "required": True},
            "scope": {"type": "string", "required": False},
        },
        "allowedTools": allowed_tools,
        "steps": steps,
        "approval": approval,
        "gates": gates,
        "outputs": ["plan", "risk_summary", "execution_log"],
    }


def generate_skill_from_authoring_session(
    session_id: str,
    *,
    skill_id: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, object]:
    session = _load_session(session_id)
    requested_skill_id = _slug(skill_id or _default_skill_id(session), fallback="generated-skill")
    base = output_dir.expanduser() if output_dir else _generated_dir()
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{requested_skill_id}.skill.json"
    payload = _generated_skill_payload(session, requested_skill_id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation = validate_skill_file(path)
    return {
        "ok": bool(validation.get("ok")),
        "session_id": session.id,
        "skill_id": requested_skill_id,
        "path": str(path),
        "validation": validation,
        "next_mcp_calls": [
            {"tool": "bubble_skill_validate", "arguments": {"path": str(path)}},
            {"tool": "bubble_skill_import", "arguments": {"path": str(path)}},
            {"tool": "bubble_skill_enable", "arguments": {"skill_id": requested_skill_id}},
            {
                "tool": "bubble_skill_run",
                "arguments": {
                    "skill_id": requested_skill_id,
                    "inputs": {"profile": session.profile or "<profile>"},
                    "execute": False,
                },
            },
        ],
    }
