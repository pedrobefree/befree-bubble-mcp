"""Typed style and design-token lifecycle boundary."""

from .assignments import StyleAssignmentService, StyleOverridePolicy
from .colors import ColorSnapshot, ColorTokenService
from .fonts import FontSnapshot, FontTokenService
from .protocols import (
    StyleAssignmentHost,
    StyleLifecycleHost,
    StyleReferenceHost,
    StyleTokenHost,
    TokenMutationResult,
)
from .references import StyleReferenceResolver
from .service import StyleLifecycleService

__all__ = [
    "ColorSnapshot",
    "ColorTokenService",
    "FontSnapshot",
    "FontTokenService",
    "StyleAssignmentHost",
    "StyleAssignmentService",
    "StyleLifecycleHost",
    "StyleLifecycleService",
    "StyleOverridePolicy",
    "StyleReferenceHost",
    "StyleReferenceResolver",
    "StyleTokenHost",
    "TokenMutationResult",
]
