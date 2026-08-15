"""Composition root for style lifecycle services."""

from __future__ import annotations

from .protocols import StyleReferenceHost
from .references import StyleReferenceResolver


class StyleLifecycleService:
    """Compose typed style lifecycle operations over one BubbleCLI host."""

    def __init__(self, host: StyleReferenceHost) -> None:
        self.references = StyleReferenceResolver(host)
