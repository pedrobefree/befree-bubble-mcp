from __future__ import annotations

from typing import Any

from bubble_mcp.style_import.models import BubbleStyleCandidate


STATE_ORDER = ("hover", "focus", "pressed", "disabled")


def _create_style_args(
    profile: str,
    candidate: BubbleStyleCandidate,
    *,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "name": candidate.name,
        "element_type": candidate.element_type,
        "dry_run": dry_run,
        "execute": execute,
        "allow_property_match": False,
        **candidate.base,
    }


def _condition_args(
    profile: str,
    candidate: BubbleStyleCandidate,
    condition: str,
    properties: dict[str, Any],
    *,
    dry_run: bool,
    execute: bool,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "name": candidate.name,
        "condition": condition,
        "dry_run": dry_run,
        "execute": execute,
        **properties,
    }


def build_style_operations(
    profile: str,
    candidates: list[BubbleStyleCandidate],
    execute: bool,
) -> list[dict[str, Any]]:
    dry_run = not execute
    operations: list[dict[str, Any]] = []

    for candidate in candidates:
        operations.append(
            {
                "tool": "create_style",
                "arguments": _create_style_args(
                    profile,
                    candidate,
                    dry_run=dry_run,
                    execute=execute,
                ),
            }
        )

        present_states: list[str] = []
        for state in STATE_ORDER:
            properties = candidate.states.get(state)
            if not properties:
                continue

            present_states.append(state)
            operations.append(
                {
                    "tool": "add_style_condition",
                    "arguments": _condition_args(
                        profile,
                        candidate,
                        state,
                        properties,
                        dry_run=dry_run,
                        execute=execute,
                    ),
                }
            )

        if present_states:
            operations.append(
                {
                    "tool": "reorder_style_states",
                    "arguments": {
                        "profile": profile,
                        "name": candidate.name,
                        "order": ",".join(present_states),
                        "dry_run": dry_run,
                        "execute": execute,
                    },
                }
            )

    return operations
