"""Typed orchestration boundary for Bubble visual element mutations."""

from .protocols import VisualElementTarget, VisualMutationHost
from .service import VisualMutationService

__all__ = ["VisualElementTarget", "VisualMutationHost", "VisualMutationService"]
