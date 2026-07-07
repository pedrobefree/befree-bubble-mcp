"""Models for declarative Bubble MCP skill contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class SkillStep:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillStep":
        data = dict(payload)
        return cls(type=str(data.get("type") or "").strip(), payload=data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload) if self.payload else {"type": self.type}


@dataclass(frozen=True)
class SkillGate:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillGate":
        data = dict(payload)
        return cls(type=str(data.get("type") or "").strip(), payload=data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload) if self.payload else {"type": self.type}


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    inputs: list[str] | dict[str, Any]
    allowed_tools: list[str]
    steps: list[SkillStep]
    gates: list[SkillGate]
    outputs: list[str]
    version: str = ""
    description: str = ""
    risk: str = "read_only"
    approval: dict[str, Any] = field(default_factory=dict)
    executable: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillDefinition":
        raw_inputs = payload.get("inputs", [])
        inputs: list[str] | dict[str, Any]
        if isinstance(raw_inputs, Mapping):
            inputs = dict(raw_inputs)
        else:
            inputs = _string_list(raw_inputs)
        return cls(
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            inputs=inputs,
            allowed_tools=_string_list(payload.get("allowedTools", [])),
            steps=[SkillStep.from_dict(item) for item in _mapping_list(payload.get("steps", []))],
            gates=[SkillGate.from_dict(item) for item in _mapping_list(payload.get("gates", []))],
            outputs=_string_list(payload.get("outputs", [])),
            version=str(payload.get("version") or "").strip(),
            description=str(payload.get("description") or "").strip(),
            risk=str(payload.get("risk") or "read_only").strip(),
            approval=dict(payload.get("approval", {})) if isinstance(payload.get("approval"), Mapping) else {},
            executable=bool(payload.get("executable", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "inputs": self.inputs,
            "allowedTools": self.allowed_tools,
            "steps": [step.to_dict() for step in self.steps],
            "gates": [gate.to_dict() for gate in self.gates],
            "outputs": self.outputs,
            "executable": self.executable,
        }
        if self.version:
            payload["version"] = self.version
        if self.description:
            payload["description"] = self.description
        if self.risk:
            payload["risk"] = self.risk
        if self.approval:
            payload["approval"] = self.approval
        return payload
