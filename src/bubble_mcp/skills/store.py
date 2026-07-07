"""Local storage for executable Bubble MCP skills."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.extensions.store import list_extensions
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.server.schema_families import native_tool_schemas
from bubble_mcp.skills.validator import validate_skill_file


STATE_FILENAME = "state.json"
SKILL_FILENAME = "skill.json"


def _validate_skill_id(skill_id: str) -> str:
    safe_id = str(skill_id or "").strip()
    if not safe_id:
        raise ValueError("Skill id is required.")
    if safe_id in {".", ".."} or "/" in safe_id or "\\" in safe_id:
        raise ValueError(f"Skill id must be a safe path segment: {skill_id}")
    return safe_id


def skills_dir() -> Path:
    return get_config_dir() / "skills"


def installed_skills_dir() -> Path:
    return skills_dir() / "installed"


def skill_runs_dir() -> Path:
    return skills_dir() / "runs"


def _skill_dir(skill_id: str) -> Path:
    root = installed_skills_dir()
    path = root / _validate_skill_id(skill_id)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Skill path escapes storage directory: {path}") from exc
    return path


def _skill_path(skill_id: str) -> Path:
    return _skill_dir(skill_id) / SKILL_FILENAME


def _state_path(skill_id: str) -> Path:
    return _skill_dir(skill_id) / STATE_FILENAME


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _native_available_tool_names() -> set[str]:
    names = {str(tool.get("name") or "") for tool in native_tool_schemas()}
    names.update(ARIA_BUBBLE_TOOL_NAMES)
    return {name for name in names if name}


def _skill_source_path(source: Path) -> Path:
    if source.is_dir():
        return source / SKILL_FILENAME
    return source


def _write_state(skill_id: str, state: str) -> None:
    path = _state_path(skill_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"state": state}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_state(skill_id: str) -> str:
    path = _state_path(skill_id)
    if not path.exists():
        return "pending"
    payload = _read_json_object(path)
    return str(payload.get("state") or "pending")


@dataclass(frozen=True)
class InstalledSkill:
    skill_id: str
    state: str
    path: Path
    source: str = "local"
    extension_id: str | None = None
    skill: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "skill_id": self.skill_id,
            "state": self.state,
            "path": str(self.path),
            "source": self.source,
        }
        if self.extension_id:
            payload["extension_id"] = self.extension_id
        if self.skill is not None:
            payload["skill"] = self.skill
        return payload


def import_skill(source: Path) -> dict[str, Any]:
    skill_path = _skill_source_path(source)
    report = validate_skill_file(skill_path)
    if not report.get("ok"):
        return {"ok": False, "skill_id": "", "state": "invalid", "path": str(skill_path), "errors": report["errors"]}
    skill = report["skill"]
    skill_id = _validate_skill_id(str(skill.get("id") or ""))
    target_dir = _skill_dir(skill_id)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)
    shutil.copy2(skill_path, target_dir / SKILL_FILENAME)
    _write_state(skill_id, "pending")
    return {
        "ok": True,
        "skill_id": skill_id,
        "state": "pending",
        "path": str(target_dir),
        "skill": skill,
        "errors": [],
    }


def export_skill(skill_id: str, output: Path) -> dict[str, Any]:
    skill_id = _validate_skill_id(skill_id)
    source = _skill_path(skill_id)
    if not source.exists():
        raise ValueError(f"Unknown skill: {skill_id}")
    if output.suffix:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        target = output
    else:
        output.mkdir(parents=True, exist_ok=True)
        target = output / f"{skill_id}.skill.json"
        shutil.copy2(source, target)
    return {"ok": True, "skill_id": skill_id, "path": str(target)}


def _local_skill_from_path(path: Path) -> InstalledSkill | None:
    skill_path = path / SKILL_FILENAME
    if not skill_path.exists():
        return None
    report = validate_skill_file(skill_path)
    payload = report.get("skill") if report.get("ok") else None
    skill_id = str((payload or {}).get("id") or path.name)
    return InstalledSkill(
        skill_id=skill_id,
        state=_read_state(skill_id),
        path=skill_path,
        source="local",
        skill=payload if isinstance(payload, dict) else None,
    )


def _extension_skill_entries() -> list[InstalledSkill]:
    entries: list[InstalledSkill] = []
    for extension in list_extensions():
        if extension.state != "enabled":
            continue
        for relative in extension.manifest.exports.skills:
            skill_path = (extension.path / relative).resolve(strict=False)
            try:
                skill_path.relative_to(extension.path.resolve(strict=True))
            except ValueError:
                continue
            if not skill_path.exists():
                continue
            report = validate_skill_file(skill_path, available_tools=_native_available_tool_names())
            if not report.get("ok"):
                continue
            skill = report["skill"]
            entries.append(
                InstalledSkill(
                    skill_id=str(skill.get("id") or skill_path.stem),
                    state="enabled",
                    path=skill_path,
                    source="extension",
                    extension_id=extension.extension_id,
                    skill=skill,
                )
            )
    return entries


def list_skills() -> list[InstalledSkill]:
    root = installed_skills_dir()
    local_entries: list[InstalledSkill] = []
    if root.exists():
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            entry = _local_skill_from_path(path)
            if entry is not None:
                local_entries.append(entry)
    return [*local_entries, *_extension_skill_entries()]


def get_skill(skill_id: str) -> InstalledSkill:
    skill_id = _validate_skill_id(skill_id)
    path = _skill_path(skill_id)
    if path.exists():
        entry = _local_skill_from_path(path.parent)
        if entry is not None:
            return entry
    for entry in _extension_skill_entries():
        if entry.skill_id == skill_id:
            return entry
    raise ValueError(f"Unknown skill: {skill_id}")


def enable_skill(skill_id: str) -> dict[str, Any]:
    skill_id = _validate_skill_id(skill_id)
    path = _skill_path(skill_id)
    if not path.exists():
        raise ValueError(f"Unknown local skill: {skill_id}")
    report = validate_skill_file(path)
    if not report.get("ok"):
        return {"ok": False, "skill_id": skill_id, "state": _read_state(skill_id), "errors": report["errors"]}
    _write_state(skill_id, "enabled")
    return {"ok": True, "skill_id": skill_id, "state": "enabled", "errors": []}


def disable_skill(skill_id: str) -> dict[str, Any]:
    skill_id = _validate_skill_id(skill_id)
    if not _skill_path(skill_id).exists():
        raise ValueError(f"Unknown local skill: {skill_id}")
    _write_state(skill_id, "disabled")
    return {"ok": True, "skill_id": skill_id, "state": "disabled", "errors": []}
