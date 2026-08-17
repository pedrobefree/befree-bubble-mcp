"""Composition root for style lifecycle services."""

from __future__ import annotations

from .assignments import StyleAssignmentService, StyleOverridePolicy
from .colors import ColorTokenService
from .definitions import StyleDefinitionService
from .fonts import FontTokenService
from .figma_import import FigmaTokenImportService
from .protocols import StyleLifecycleHost
from .references import StyleReferenceResolver


class StyleLifecycleService:
    """Compose typed style lifecycle operations over one BubbleCLI host."""

    def __init__(self, host: StyleLifecycleHost) -> None:
        self.references = StyleReferenceResolver(host)
        self.assignments = StyleAssignmentService(StyleOverridePolicy(host, self.references))
        self.colors = ColorTokenService(host)
        self.fonts = FontTokenService(host)
        self.definitions = StyleDefinitionService(
            host,
            self.references,
            host.resolve_style_definition_color,
        )
        self.figma_import = FigmaTokenImportService(
            host,
            self.colors,
            self.fonts,
            self.definitions,
        )
