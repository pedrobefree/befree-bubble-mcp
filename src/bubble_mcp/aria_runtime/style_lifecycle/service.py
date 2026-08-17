"""Composition root for style lifecycle services."""

from __future__ import annotations

from .assignments import StyleAssignmentService, StyleOverridePolicy
from .colors import ColorTokenService
from .fonts import FontTokenService
from .protocols import StyleLifecycleHost
from .references import StyleReferenceResolver


class StyleLifecycleService:
    """Compose typed style lifecycle operations over one BubbleCLI host."""

    def __init__(self, host: StyleLifecycleHost) -> None:
        self.references = StyleReferenceResolver(host)
        self.assignments = StyleAssignmentService(StyleOverridePolicy(host, self.references))
        self.colors = ColorTokenService(host)
        self.fonts = FontTokenService(host)
