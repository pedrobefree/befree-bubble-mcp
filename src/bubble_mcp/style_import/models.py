from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StyleState = Literal["base", "hover", "focus", "disabled", "pressed"]


@dataclass(frozen=True)
class ExtractedStyleRule:
    selector: str
    source_selector: str
    state: StyleState
    declarations: dict[str, str]


@dataclass(frozen=True)
class BubbleStyleCandidate:
    name: str
    element_type: str
    selector: str
    base: dict[str, Any]
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    unsupported: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "element_type": self.element_type,
            "selector": self.selector,
            "base": self.base,
            "states": self.states,
            "unsupported": self.unsupported,
        }
