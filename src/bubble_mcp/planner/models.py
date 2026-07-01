"""Planning models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanStep:
    id: str
    tool_name: str
    args: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BubblePlan:
    message: str
    steps: list[PlanStep]
    risk: str
    requires_approval: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "risk": self.risk,
            "requires_approval": self.requires_approval,
            "warnings": self.warnings,
            "steps": [
                {
                    "id": step.id,
                    "tool_name": step.tool_name,
                    "args": step.args,
                    "depends_on": step.depends_on,
                }
                for step in self.steps
            ],
        }
