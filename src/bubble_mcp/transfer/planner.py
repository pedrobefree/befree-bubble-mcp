"""Transfer plan assembly from source inventory and target context."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bubble_mcp.context.freshness import load_context_with_overlay
from bubble_mcp.transfer.collections import extract_collection_bundle, plan_collection_bundle
from bubble_mcp.transfer.compiler import compile_collection_actions_to_payloads, compile_inventory_to_target_payloads
from bubble_mcp.transfer.inventory import inventory_source_object
from bubble_mcp.transfer.mapping import build_dependency_decisions
from bubble_mcp.transfer.models import TransferPlan
from bubble_mcp.transfer.profiles import resolve_transfer_profiles
from bubble_mcp.transfer.store import save_transfer_plan


def _transfer_id(source_ref: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", str(source_ref or "").strip().lower()).strip("_") or "object"
    return f"transfer_{stamp}_{slug[:48]}"


def _blocked_reasons(decisions: list[Any]) -> list[str]:
    return [str(decision.reason) for decision in decisions if decision.action == "block"]


def _data_type_keys_to_create(decisions: list[Any]) -> list[str]:
    keys: list[str] = []
    for decision in decisions:
        dependency = getattr(decision, "dependency", None)
        if getattr(decision, "action", "") != "create_copy" or dependency is None:
            continue
        kind = str(getattr(dependency, "kind", ""))
        key = str(getattr(dependency, "key", "")).strip()
        if kind == "data_type" and key:
            keys.append(key)
        elif kind == "data_field" and "." in key:
            keys.append(key.split(".", 1)[0])
    return list(dict.fromkeys(keys))


def _compile_collection_payloads(
    *,
    source_ctx: Any,
    target_ctx: Any,
    decisions: list[Any],
    target_app_id: str,
    target_app_version: str,
    collection_policy: str,
    data_records_policy: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if collection_policy != "create_missing":
        return [], []
    payloads: list[dict[str, Any]] = []
    blocked: list[str] = []
    for data_type in _data_type_keys_to_create(decisions):
        bundle = extract_collection_bundle(source_ctx, data_type)
        collection_plan = plan_collection_bundle(
            bundle,
            target_ctx,
            policy=collection_policy,
            data_records_policy=data_records_policy,
        )
        blocked.extend(str(reason) for reason in collection_plan.get("blocked_reasons", []))
        if collection_plan.get("ok"):
            payloads.extend(
                compile_collection_actions_to_payloads(
                    actions=list(collection_plan.get("actions", [])),
                    target_context=target_ctx,
                    target_app_id=target_app_id,
                    target_app_version=target_app_version,
                )
            )
    return payloads, blocked


def create_transfer_plan(
    *,
    source_profile: str,
    target_profile: str,
    source_type: str,
    source_ref: str,
    source_context: str | None = None,
    target_context: str | None = None,
    target_parent: str | None = "root",
    target_name: str | None = None,
    conflict_policy: str = "fail",
    asset_policy: str = "reference_url",
    dependency_policy: str = "map_or_create",
    collection_policy: str = "map_existing",
    api_connector_policy: str = "structure_only",
    data_records_policy: str = "skip",
) -> dict[str, Any]:
    """Create and save a local transfer plan artifact."""

    resolved = resolve_transfer_profiles(source_profile, target_profile)
    if resolved.source_context_path is None:
        raise ValueError(f"Source context is missing for profile '{source_profile}'. Run bubble-mcp context detect.")
    if resolved.target_context_path is None:
        raise ValueError(f"Target context is missing for profile '{target_profile}'. Run bubble-mcp context detect.")

    source_ctx = load_context_with_overlay(
        resolved.source_context_path,
        profile=resolved.source.name,
        app_id=resolved.source.app_id,
    )
    target_ctx = load_context_with_overlay(
        resolved.target_context_path,
        profile=resolved.target.name,
        app_id=resolved.target.app_id,
    )
    inventory = inventory_source_object(
        context=source_ctx,
        profile=resolved.source.name,
        app_version=resolved.source.app_version or "test",
        source_type=source_type,
        source_ref=source_ref,
        source_context=source_context,
    )
    decisions = build_dependency_decisions(
        inventory,
        target_ctx,
        dependency_policy=dependency_policy,
    )
    blocked = _blocked_reasons(decisions)
    collection_payloads, collection_blocked = _compile_collection_payloads(
        source_ctx=source_ctx,
        target_ctx=target_ctx,
        decisions=decisions,
        target_app_id=resolved.target.app_id,
        target_app_version=resolved.target.app_version or "test",
        collection_policy=collection_policy,
        data_records_policy=data_records_policy,
    )
    blocked.extend(collection_blocked)
    payloads = [] if blocked else [
        *collection_payloads,
        *compile_inventory_to_target_payloads(
            inventory=inventory,
            target_context=target_ctx,
            target_app_id=resolved.target.app_id,
            target_app_version=resolved.target.app_version or "test",
            target_context_ref=target_context or "index",
            target_parent_ref=target_parent,
            target_name=target_name,
        ),
    ]
    plan = TransferPlan(
        transfer_id=_transfer_id(source_ref),
        source=inventory.source,
        target_profile=resolved.target.name,
        target_app_id=resolved.target.app_id,
        target_app_version=resolved.target.app_version or "test",
        target_context=target_context,
        target_parent=target_parent,
        target_name=target_name,
        conflict_policy=conflict_policy,  # type: ignore[arg-type]
        asset_policy=asset_policy,  # type: ignore[arg-type]
        collection_policy=collection_policy,  # type: ignore[arg-type]
        api_connector_policy=api_connector_policy,  # type: ignore[arg-type]
        data_records_policy=data_records_policy,  # type: ignore[arg-type]
        dependency_decisions=decisions,
        write_payloads=payloads,
        blocked_reasons=blocked,
    )
    path = save_transfer_plan(plan)
    return {
        "ok": not blocked,
        "transfer_id": plan.transfer_id,
        "plan_path": str(path),
        "blocked_reasons": blocked,
        "payload_count": len(payloads),
        "dependency_decisions": [decision.to_dict() for decision in decisions],
        "target_write_ready": resolved.target_write_ready,
        "next_action": "preview" if not blocked else "resolve_blocked_dependencies",
    }
