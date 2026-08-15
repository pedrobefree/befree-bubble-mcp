"""Composed visual mutation family boundary."""

from __future__ import annotations

from .creations import VisualCreationService
from .deletions import VisualDeletionService
from .protocols import VisualMutationHost
from .targets import VisualMutationTargets


class VisualMutationService:
    """Expose operation-specific services over one typed BubbleCLI host."""

    def __init__(self, host: VisualMutationHost) -> None:
        self.targets = VisualMutationTargets(host)
        self.deletions = VisualDeletionService(host, self.targets)
        self.creations = VisualCreationService(host)
