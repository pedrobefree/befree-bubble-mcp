"""Typed style and design-token lifecycle boundary."""

from .protocols import StyleReferenceHost
from .references import StyleReferenceResolver
from .service import StyleLifecycleService

__all__ = [
    "StyleLifecycleService",
    "StyleReferenceHost",
    "StyleReferenceResolver",
]
