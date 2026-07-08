"""Transfer plan assembly from source inventory and target context."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bubble_mcp.context.freshness import load_context_with_overlay
from bubble_mcp.transfer.api_connector import (
    extract_api_connector_bundle,
    plan_api_connector_bundle,
    redact_api_connector_bundle,
)
from bubble_mcp.transfer.collections import extract_collection_bundle, plan_collection_bundle
from bubble_mcp.transfer.compiler import (
    compile_api_connector_actions_to_payloads,
    compile_context_shell_payload,
    compile_collection_actions_to_payloads,
    compile_inventory_to_target_payloads,
)
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


def _api_connector_refs_to_create(decisions: list[Any]) -> list[str]:
    refs: list[str] = []
    for decision in decisions:
        dependency = getattr(decision, "dependency", None)
        if getattr(decision, "action", "") != "create_copy" or dependency is None:
            continue
        kind = str(getattr(dependency, "kind", ""))
        key = str(getattr(dependency, "key", "")).strip()
        metadata = getattr(dependency, "metadata", {}) or {}
        if kind == "api_connector" and key:
            refs.append(key)
        elif kind == "api_connector_call":
            api_id = str(metadata.get("api_id") or "").strip()
            if api_id:
                refs.append(api_id)
            elif "." in key:
                refs.append(key.split(".", 1)[0])
    return list(dict.fromkeys(refs))


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


def _compile_api_connector_payloads(
    *,
    source_ctx: Any,
    target_ctx: Any,
    decisions: list[Any],
    target_app_id: str,
    target_app_version: str,
    api_connector_policy: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if api_connector_policy == "skip":
        return [], []
    payloads: list[dict[str, Any]] = []
    blocked: list[str] = []
    for api_ref in _api_connector_refs_to_create(decisions):
        bundle = redact_api_connector_bundle(extract_api_connector_bundle(source_ctx, api_ref))
        api_plan = plan_api_connector_bundle(bundle, target_ctx, policy=api_connector_policy)
        blocked.extend(str(reason) for reason in api_plan.get("blocked_reasons", []))
        if api_plan.get("ok"):
            payloads.extend(
                compile_api_connector_actions_to_payloads(
                    actions=list(api_plan.get("actions", [])),
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
    reuse_policy: str = "prefer_existing",
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
        reuse_policy=reuse_policy,
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
    api_payloads, api_blocked = _compile_api_connector_payloads(
        source_ctx=source_ctx,
        target_ctx=target_ctx,
        decisions=decisions,
        target_app_id=resolved.target.app_id,
        target_app_version=resolved.target.app_version or "test",
        api_connector_policy=api_connector_policy,
    )
    blocked.extend(api_blocked)
    effective_target_context = target_context or "index"
    effective_target_context_type = "reusable" if source_type == "reusable" else "page"
    shell_payloads: list[dict[str, Any]] = []
    if source_type in {"page", "reusable"} and not target_context:
        shell = compile_context_shell_payload(
            source_type=source_type,
            source_root=inventory.root,
            target_app_id=resolved.target.app_id,
            target_app_version=resolved.target.app_version or "test",
            target_name=target_name or source_ref,
        )
        if shell is not None:
            shell_payload, shell_context_ref, shell_context_type = shell
            shell_payloads.append(shell_payload)
            effective_target_context = shell_context_ref
            effective_target_context_type = shell_context_type
    payloads = [] if blocked else [
        *api_payloads,
        *collection_payloads,
        *shell_payloads,
        *compile_inventory_to_target_payloads(
            inventory=inventory,
            target_context=target_ctx,
            target_app_id=resolved.target.app_id,
            target_app_version=resolved.target.app_version or "test",
            target_context_ref=effective_target_context,
            target_parent_ref=target_parent,
            target_name=target_name,
            target_context_type=effective_target_context_type,
        ),
    ]
    plan = TransferPlan(
        transfer_id=_transfer_id(source_ref),
        source=inventory.source,
        target_profile=resolved.target.name,
        target_app_id=resolved.target.app_id,
        target_app_version=resolved.target.app_version or "test",
        target_context=target_context or effective_target_context,
        target_parent=target_parent,
        target_name=target_name,
        conflict_policy=conflict_policy,  # type: ignore[arg-type]
        asset_policy=asset_policy,  # type: ignore[arg-type]
        collection_policy=collection_policy,  # type: ignore[arg-type]
        api_connector_policy=api_connector_policy,  # type: ignore[arg-type]
        data_records_policy=data_records_policy,  # type: ignore[arg-type]
        reuse_policy=reuse_policy,  # type: ignore[arg-type]
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
        "reuse_policy": reuse_policy,
        "target_write_ready": resolved.target_write_ready,
        "next_action": "preview" if not blocked else "resolve_blocked_dependencies",
    }
