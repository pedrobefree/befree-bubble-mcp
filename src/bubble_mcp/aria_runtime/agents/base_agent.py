from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAgent(ABC):
    """Base interface for all Bubble CLI domain agents."""

    def __init__(self, sdk: Any, discovery: Any):
        self.sdk = sdk
        self.discovery = discovery

    @abstractmethod
    def can_handle(self, intent: str) -> bool:
        """Return True when this agent can process the given intent/command."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, command: Dict[str, Any], dry_run: bool = False) -> bool:
        """Execute a normalized command object."""
        raise NotImplementedError
