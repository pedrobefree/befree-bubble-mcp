"""Target dependency mapping for Bubble transfer plans."""

from __future__ import annotations

import re
from typing import Literal

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.models import TransferInventory, TransferMappingDecision
from bubble_mcp.transfer.reuse import find_compatible_target_dependency


DependencyPolicy = Literal["map_only", "map_or_create", "skip_optional"]
ReusePolicy = Literal["prefer_existing", "exact_only", "create_new"]


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _candidate_values(node: BubbleContextNode) -> set[str]:
    values = {node.id, node.label}
    for key in ("bubble_id", "key", "name"):
        value = node.metadata.get(key)
        if isinstance(value, str):
            values.add(value)
    return {_normalize(value) for value in values if value}


def _target_reference(node: BubbleContextNode) -> dict[str, str]:
    reference: dict[str, str] = {"id": node.id, "label": node.label}
    for key in (
        "api_id",
        "bubble_id",
        "call_id",
        "context",
        "data_type",
        "field_key",
        "key",
        "name",
        "option_set",
        "value_key",
    ):
        value = node.metadata.get(key)
        if isinstance(value, str) and value.strip():
            reference[key] = value.strip()
    return reference


def _find_target_dependency(
    target_context: BubbleProjectContext,
    *,
    kind: str,
    key: str,
    label: str,
) -> BubbleContextNode | None:
    wanted = {_normalize(key), _normalize(label)}
    if kind == "data_field" and "." in key:
        wanted.add(_normalize(key.rsplit(".", 1)[-1]))
    for node in target_context.nodes:
        if node.type != kind:
            continue
        if wanted & _candidate_values(node):
            return node
    return None


def build_dependency_decisions(
    inventory: TransferInventory,
    target_context: BubbleProjectContext,
    *,
    dependency_policy: str = "map_or_create",
    reuse_policy: str = "prefer_existing",
) -> list[TransferMappingDecision]:
    """Map source dependencies to target dependencies or explicit actions."""

    if dependency_policy not in {"map_only", "map_or_create", "skip_optional"}:
        raise ValueError("dependency_policy must be one of: map_only, map_or_create, skip_optional.")
    if reuse_policy not in {"prefer_existing", "exact_only", "create_new"}:
        raise ValueError("reuse_policy must be one of: prefer_existing, exact_only, create_new.")

    decisions: list[TransferMappingDecision] = []
    for dependency in inventory.dependencies:
        if reuse_policy != "create_new":
            target = _find_target_dependency(
                target_context,
                kind=dependency.kind,
                key=dependency.key,
                label=dependency.label,
            )
            if target is not None:
                decisions.append(
                    TransferMappingDecision(
                        dependency=dependency,
                        action="map_existing",
                        target_id=target.id,
                        target_label=target.label,
                        reason="Matched existing target dependency.",
                        confidence=1.0,
                        metadata={"match_type": "exact", "target_reference": _target_reference(target)},
                    )
                )
                continue
            if reuse_policy == "prefer_existing":
                compatible = find_compatible_target_dependency(dependency, target_context)
                if compatible is not None:
                    decisions.append(
                        TransferMappingDecision(
                            dependency=dependency,
                            action="map_existing",
                            target_id=compatible.target_id,
                            target_label=compatible.target_label,
                            reason=compatible.reason,
                            confidence=compatible.confidence,
                            metadata=compatible.metadata,
                        )
                    )
                    continue
        if dependency_policy == "skip_optional" and not dependency.required:
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="skip",
                    reason="Missing optional dependency skipped by policy.",
                )
            )
            continue
        if dependency_policy == "map_or_create":
            decisions.append(
                TransferMappingDecision(
                    dependency=dependency,
                    action="create_copy",
                    reason="Missing target dependency will be created or staged by the transfer compiler.",
                )
            )
            continue
        decisions.append(
            TransferMappingDecision(
                dependency=dependency,
                action="block",
                reason=f"Required target dependency not found: {dependency.kind}:{dependency.key}",
            )
        )
    return decisions
