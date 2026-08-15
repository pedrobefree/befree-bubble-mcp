"""Composition root for style lifecycle services."""

from __future__ import annotations

from .assignments import StyleAssignmentService, StyleOverridePolicy
from .protocols import StyleAssignmentHost
from .references import StyleReferenceResolver


class StyleLifecycleService:
    """Compose typed style lifecycle operations over one BubbleCLI host."""

    def __init__(self, host: StyleAssignmentHost) -> None:
        self.references = StyleReferenceResolver(host)
        self.assignments = StyleAssignmentService(StyleOverridePolicy(host, self.references))
