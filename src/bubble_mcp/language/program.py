"""Typed framework program contracts for the Bubble MCP language."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class FrameworkProgramStep:
    index: int
    step_id: str
    intent: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, index: int) -> "FrameworkProgramStep":
        raw_arguments = _dict(payload.get("arguments"))
        inline_arguments = {
            str(key): value
            for key, value in payload.items()
            if key
            not in {
                "id",
                "step_id",
                "intent",
                "tool",
                "arguments",
                "outputs",
                "requires",
                "description",
            }
        }
        arguments = {**inline_arguments, **raw_arguments}
        step_id = str(payload.get("id") or payload.get("step_id") or f"step_{index}").strip()
        return cls(
            index=index,
            step_id=step_id,
            intent=str(payload.get("intent") or "").strip(),
            tool=str(payload.get("tool") or "").strip(),
            arguments=arguments,
            outputs={str(key): str(value) for key, value in _dict(payload.get("outputs")).items()},
            requires=[str(item) for item in _list(payload.get("requires")) if str(item).strip()],
            description=str(payload.get("description") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.step_id,
            "arguments": dict(self.arguments),
        }
        if self.intent:
            payload["intent"] = self.intent
        if self.tool:
            payload["tool"] = self.tool
        if self.outputs:
            payload["outputs"] = dict(self.outputs)
        if self.requires:
            payload["requires"] = list(self.requires)
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class FrameworkProgram:
    ok: bool
    objective: str
    steps: list[FrameworkProgramStep]
    execution_mode: str = "preview"
    approval: str = "required"
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "objective": self.objective,
            "execution": {"mode": self.execution_mode, "approval": self.approval},
            "metadata": dict(self.metadata),
            "steps": [step.to_dict() for step in self.steps],
            "error": self.error,
        }


@dataclass(frozen=True)
class CompiledFrameworkCall:
    step_id: str
    step_index: int
    tool: str
    arguments: dict[str, Any]
    intent: str = ""
    risk: str = "mutating"
    read_only: bool = False
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "intent": self.intent,
            "risk": self.risk,
            "read_only": self.read_only,
            "requires_approval": self.requires_approval,
        }


def parse_framework_program(program: dict[str, Any]) -> FrameworkProgram:
    if not isinstance(program, dict):
        raise ValueError("framework program must be an object.")
    steps = [
        FrameworkProgramStep.from_dict(step, index=index)
        for index, step in enumerate(_list(program.get("steps")), start=1)
        if isinstance(step, dict)
    ]
    if not steps:
        return FrameworkProgram(
            ok=False,
            objective=str(program.get("objective") or ""),
            steps=[],
            error="framework_program_has_no_steps",
        )
    execution = _dict(program.get("execution"))
    metadata = _dict(program.get("metadata"))
    return FrameworkProgram(
        ok=True,
        objective=str(program.get("objective") or ""),
        steps=steps,
        execution_mode=str(execution.get("mode") or "preview"),
        approval=str(execution.get("approval") or "required"),
        metadata=metadata,
    )
