"""Transfer plan assembly from source inventory and target context."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
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
    compile_reusable_inventory_to_payload,
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


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _node_display_name(node: BubbleContextNode) -> str:
    metadata = _obj(node.metadata)
    properties = _obj(metadata.get("properties"))
    props = _obj(properties.get("%p"))
    for value in (
        props.get("%nm"),
        properties.get("%nm"),
        metadata.get("name"),
        metadata.get("key"),
        metadata.get("bubble_id"),
        node.label,
        node.id.rsplit(":", 1)[-1],
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return node.id


def _context_ref(node: BubbleContextNode) -> str:
    metadata = _obj(node.metadata)
    for key in ("bubble_id", "key", "root_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return node.id.rsplit(":", 1)[-1]


def _find_named_node(
    context: BubbleProjectContext,
    *,
    node_type: str,
    name: str,
    context_ref: str | None = None,
) -> BubbleContextNode | None:
    wanted = _normalize_name(name)
    if not wanted:
        return None
    context_wanted = _normalize_name(context_ref or "")
    for node in context.nodes:
        if node.type != node_type:
            continue
        if context_wanted and node_type == "element":
            metadata = _obj(node.metadata)
            node_context = _normalize_name(str(metadata.get("context") or ""))
            path = metadata.get("path") or metadata.get("path_array")
            path_values = {_normalize_name(str(item)) for item in path} if isinstance(path, list) else set()
            if node_context and node_context != context_wanted:
                continue
            if not node_context and path_values and context_wanted not in path_values:
                continue
        candidates = {
            _normalize_name(node.id),
            _normalize_name(node.label),
            _normalize_name(_node_display_name(node)),
        }
        if wanted in candidates:
            return node
    return None


def _name_exists(context: BubbleProjectContext, *, node_type: str, name: str) -> bool:
    wanted = _normalize_name(name)
    for node in context.nodes:
        if node.type != node_type:
            continue
        candidates = {
            _normalize_name(node.id),
            _normalize_name(node.label),
            _normalize_name(_node_display_name(node)),
        }
        if wanted in candidates:
            return True
    return False


def _unique_name(context: BubbleProjectContext, *, node_type: str, base_name: str) -> str:
    base = str(base_name or "copy").strip() or "copy"
    candidate = f"{base}_copy"
    if not _name_exists(context, node_type=node_type, name=candidate):
        return candidate
    index = 2
    while _name_exists(context, node_type=node_type, name=f"{candidate}_{index}"):
        index += 1
    return f"{candidate}_{index}"


def _resolve_context_conflict(
    *,
    target_ctx: BubbleProjectContext,
    source_type: str,
    source_ref: str,
    target_context: str | None,
    target_name: str | None,
    conflict_policy: str,
) -> tuple[str | None, str | None, str | None, list[str]]:
    if conflict_policy not in {"fail", "rename", "replace", "reuse_existing"}:
        raise ValueError("conflict_policy must be one of: fail, rename, replace, reuse_existing.")
    blocked: list[str] = []
    effective_target_context = target_context
    effective_target_name = target_name
    reused_context_type: str | None = None
    desired_name = str(target_name or source_ref or "").strip()
    if source_type in {"page", "reusable"} and not target_context and desired_name:
        existing = _find_named_node(target_ctx, node_type=source_type, name=desired_name)
        if existing is None:
            return effective_target_context, effective_target_name, reused_context_type, blocked
        if conflict_policy == "fail":
            blocked.append(f"Target {source_type} already exists: {desired_name}")
        elif conflict_policy == "replace":
            blocked.append(
                f"Target {source_type} already exists and replace requires a dedicated destructive confirmation path: "
                f"{desired_name}"
            )
        elif conflict_policy == "rename":
            effective_target_name = _unique_name(target_ctx, node_type=source_type, base_name=desired_name)
        elif conflict_policy == "reuse_existing":
            effective_target_context = _context_ref(existing)
            effective_target_name = desired_name
            reused_context_type = "reusable" if source_type == "reusable" else "page"
        return effective_target_context, effective_target_name, reused_context_type, blocked
    if source_type == "element" and desired_name:
        existing = _find_named_node(target_ctx, node_type="element", name=desired_name, context_ref=target_context)
        if existing is None:
            return effective_target_context, effective_target_name, reused_context_type, blocked
        if conflict_policy == "fail":
            blocked.append(f"Target element already exists: {desired_name}")
        elif conflict_policy == "replace":
            blocked.append(
                f"Target element already exists and replace requires a dedicated destructive confirmation path: "
                f"{desired_name}"
            )
        elif conflict_policy == "rename":
            effective_target_name = _unique_name(target_ctx, node_type="element", base_name=desired_name)
        elif conflict_policy == "reuse_existing":
            blocked.append(
                f"Target element already exists and reuse_existing cannot update element subtrees yet: {desired_name}"
            )
    return effective_target_context, effective_target_name, reused_context_type, blocked


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


def _asset_policy_blocked(decisions: list[Any], *, asset_policy: str) -> list[str]:
    if asset_policy not in {"reference_url", "stage_and_upload", "skip"}:
        raise ValueError("asset_policy must be one of: reference_url, stage_and_upload, skip.")
    blocked: list[str] = []
    for decision in decisions:
        dependency = getattr(decision, "dependency", None)
        if dependency is None or str(getattr(dependency, "kind", "")) != "asset":
            continue
        if getattr(decision, "action", "") not in {"create_copy", "map_existing"}:
            continue
        label = str(getattr(dependency, "label", "") or getattr(dependency, "key", "") or "asset")
        if asset_policy == "stage_and_upload":
            blocked.append(
                f"Asset staging/upload is not implemented yet for transfer asset '{label}'. "
                "Use asset_policy=reference_url or skip."
            )
        elif asset_policy == "skip" and bool(getattr(dependency, "required", True)):
            blocked.append(f"Required transfer asset cannot be skipped: {label}")
    return blocked


def _unsupported_create_copy_blocked(decisions: list[Any]) -> list[str]:
    compiler_supported = {
        "api_connector",
        "api_connector_call",
        "asset",
        "data_field",
        "data_type",
        "option_set",
        "privacy_rule",
    }
    blocked: list[str] = []
    for decision in decisions:
        if getattr(decision, "action", "") != "create_copy":
            continue
        dependency = getattr(decision, "dependency", None)
        if dependency is None:
            continue
        kind = str(getattr(dependency, "kind", ""))
        if kind in compiler_supported:
            continue
        key = str(getattr(dependency, "key", "") or getattr(dependency, "label", "") or kind)
        blocked.append(
            f"Missing transfer dependency has no safe create compiler yet: {kind}:{key}. "
            "Map or reuse it in the target project before executing the transfer."
        )
    return blocked


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
    (
        effective_target_context,
        effective_target_name,
        reused_context_type,
        conflict_blocked,
    ) = _resolve_context_conflict(
        target_ctx=target_ctx,
        source_type=source_type,
        source_ref=source_ref,
        target_context=target_context,
        target_name=target_name,
        conflict_policy=conflict_policy,
    )
    decisions = build_dependency_decisions(
        inventory,
        target_ctx,
        dependency_policy=dependency_policy,
        reuse_policy=reuse_policy,
    )
    blocked = _blocked_reasons(decisions)
    blocked.extend(conflict_blocked)
    blocked.extend(_unsupported_create_copy_blocked(decisions))
    blocked.extend(_asset_policy_blocked(decisions, asset_policy=asset_policy))
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
    effective_target_context = effective_target_context or "index"
    effective_target_context_type = reused_context_type or ("reusable" if source_type == "reusable" else "page")
    shell_payloads: list[dict[str, Any]] = []
    reusable_payloads: list[dict[str, Any]] = []
    if source_type == "reusable" and not target_context and reused_context_type is None and not blocked:
        reusable_compiled = compile_reusable_inventory_to_payload(
            inventory=inventory,
            target_app_id=resolved.target.app_id,
            target_app_version=resolved.target.app_version or "test",
            target_name=effective_target_name or source_ref,
            dependency_decisions=decisions,
        )
        if reusable_compiled is not None:
            reusable_payload, reusable_context_ref = reusable_compiled
            reusable_payloads.append(reusable_payload)
            effective_target_context = reusable_context_ref
            effective_target_context_type = "reusable"
    if source_type == "page" and not target_context and reused_context_type is None:
        shell = compile_context_shell_payload(
            source_type=source_type,
            source_root=inventory.root,
            target_app_id=resolved.target.app_id,
            target_app_version=resolved.target.app_version or "test",
            target_name=effective_target_name or source_ref,
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
        *reusable_payloads,
        *(
            []
            if reusable_payloads
            else compile_inventory_to_target_payloads(
                inventory=inventory,
                target_context=target_ctx,
                target_app_id=resolved.target.app_id,
                target_app_version=resolved.target.app_version or "test",
                target_context_ref=effective_target_context,
                target_parent_ref=target_parent,
                target_name=effective_target_name,
                target_context_type=effective_target_context_type,
                dependency_decisions=decisions,
            )
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
        target_name=effective_target_name,
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
