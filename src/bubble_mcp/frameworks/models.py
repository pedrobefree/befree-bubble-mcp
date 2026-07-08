"""Models for framework adapter artifacts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameworkAdapter:
    framework_id: str
    name: str
    description: str
    modes: tuple[str, ...]
    artifacts: tuple[str, ...]
    evidence_targets: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.framework_id,
            "name": self.name,
            "description": self.description,
            "modes": list(self.modes),
            "artifacts": list(self.artifacts),
            "evidence_targets": list(self.evidence_targets),
        }
