"""Composition root for schema lifecycle services."""

from __future__ import annotations

from .protocols import SchemaLifecycleHost
from .references import SchemaReferenceResolver


class SchemaLifecycleService:
    """Compose typed schema lifecycle operations over one BubbleCLI host."""

    def __init__(self, host: SchemaLifecycleHost) -> None:
        self.references = SchemaReferenceResolver(host)
