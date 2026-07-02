from typing import Any, Dict, Optional, Tuple

from .base_agent import BaseAgent


class DiscoveryAgent(BaseAgent):
    """
    Discovery helper agent.

    This agent is intentionally utility-focused. It is used by other agents and
    keeps lookup logic centralized (context/parent/element resolution).
    """

    def can_handle(self, intent: str) -> bool:
        return intent == "discovery"

    def execute(self, command: Dict[str, Any], dry_run: bool = False) -> bool:
        # Discovery commands are utility calls, not standalone CLI operations.
        return False

    def resolve_context(self, context_name: str) -> Tuple[Optional[str], Optional[str]]:
        return self.sdk._find_context(context_name)

    def resolve_parent(
        self,
        context_id: str,
        context_type: str,
        context_name: str,
        parent_name: str,
    ) -> Optional[Dict[str, Any]]:
        if parent_name == context_name or str(parent_name).lower() == "root":
            return {"path": [], "id": context_id}
        return self.discovery.find_element_by_name(
            context_id, parent_name, context_type=context_type
        )

    def find_element(
        self, context_id: str, context_type: str, element_name: str
    ) -> Optional[Dict[str, Any]]:
        return self.discovery.find_element_by_name(
            context_id, element_name, context_type=context_type
        )
