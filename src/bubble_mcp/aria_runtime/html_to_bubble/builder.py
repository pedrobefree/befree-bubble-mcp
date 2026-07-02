from __future__ import annotations

from typing import Any, Dict, List


class BubbleCommandBuilder:
    """Build ordered create-* commands from mapped Bubble tree."""

    def __init__(self) -> None:
        self._counter = 0

    def build_commands(self, context: str, parent: str, bubble_tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        commands: List[Dict[str, Any]] = []
        self._counter = 0
        self._build_recursive(bubble_tree, "__ROOT__", commands)
        return commands

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def _build_recursive(self, node: Dict[str, Any], parent_ref: str, commands: List[Dict[str, Any]]) -> None:
        bubble_type = node.get("bubble_type")
        props = node.get("properties", {}) or {}
        children = node.get("children", []) or []

        if bubble_type == "Group":
            result_id = self._next_id("group")
            commands.append(
                {
                    "action": "create_group",
                    "parent_ref": parent_ref,
                    "result_id": result_id,
                    "params": props,
                }
            )
            for child in children:
                self._build_recursive(child, result_id, commands)
            return

        if bubble_type == "Text":
            commands.append(
                {
                    "action": "create_text",
                    "parent_ref": parent_ref,
                    "params": props,
                }
            )
            return

        if bubble_type == "Button":
            commands.append(
                {
                    "action": "create_button",
                    "parent_ref": parent_ref,
                    "params": props,
                }
            )
            return

        if bubble_type == "Image":
            commands.append(
                {
                    "action": "create_image",
                    "parent_ref": parent_ref,
                    "params": props,
                }
            )
            return

        if bubble_type == "Input":
            commands.append(
                {
                    "action": "create_input",
                    "parent_ref": parent_ref,
                    "params": props,
                }
            )
            return

        # Unknown leaf/container type: still traverse children.
        for child in children:
            self._build_recursive(child, parent_ref, commands)
