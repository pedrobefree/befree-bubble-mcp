"""Tool implementations for the initial MCP server."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, cast
from pathlib import Path

from bubble_mcp import __version__
from bubble_mcp.aria_dispatch import dispatch_aria_runtime_tool
from bubble_mcp.browser_automation import (
    cancel_scheduled_deploy,
    deploy_history,
    list_scheduled_deploys,
    rearm_scheduled_deploys,
    schedule_deploy,
)
from bubble_mcp.catalog_quality import catalog_quality_report
from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.context.importers import import_context_artifact
from bubble_mcp.context.detector import (
    default_bubble_export_path,
    default_bubble_modules_dir,
    default_context_path,
    default_crawler_index_path,
    detect_project_context,
)
from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.context.freshness import context_freshness, load_context_with_overlay
from bubble_mcp.context.queries import context_find_payload
from bubble_mcp.context.source import load_context, save_context
from bubble_mcp.core.config import BubbleProfile, load_settings, resolve_profile, save_settings, with_profile
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.execution.client import BubbleEditorClient, build_editor_write_headers
from bubble_mcp.execution.editor_api import (
    confirm_bubble_branch_merge,
    create_bubble_branch,
    delete_bubble_branch,
    describe_bubble_branch_merge_conflicts,
    fetch_jetstream_logs,
    fetch_changelog_entries,
    fetch_plan_usage,
    fetch_storage_usage,
    fetch_workflow_runs,
    fetch_workload_usage_breakdown,
    fetch_workload_usage_by_date,
    list_branch_contributors,
    list_bubble_branches,
    performance_audit,
    read_time_series,
    start_bubble_branch_merge,
)
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.execution.plugins import install_plugin
from bubble_mcp.execution.state import next_user_action, operation_snapshot
from bubble_mcp.execution.structural import validate_structure
from bubble_mcp.extensions.store import (
    disable_extension,
    enable_extension,
    import_extension,
    list_extensions,
)
from bubble_mcp.extensions.tools import enabled_extension_tool_schemas, preview_extension_tool_call
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.extension_companion import (
    ExtensionCompanionConfig,
    extension_companion_background_status,
    start_extension_companion_background,
    stop_extension_companion_background,
)
from bubble_mcp.frameworks import (
    framework_status,
    generate_framework_artifacts,
    list_frameworks,
    sync_framework_evidence,
)
from bubble_mcp.frameworks.text_planner import plan_framework_text
from bubble_mcp.frameworks.workspace import sync_artifacts_to_workspace
from bubble_mcp.language import (
    build_language_index,
    compile_framework_program,
    framework_language_pack,
    language_diff,
    language_query,
    language_tool_detail,
)
from bubble_mcp.language.cache import cached_language_index
from bubble_mcp.harness.expert import export_expert_eval_cases
from bubble_mcp.harness.eval_runner import run_eval
from bubble_mcp.harness.visual import compare_visual_snapshot_files
from bubble_mcp.harness.visual_audit import audit_visual_from_inputs
from bubble_mcp.harness.visual_bubble import capture_bubble_visual_snapshot
from bubble_mcp.harness.visual_capture import capture_visual_snapshot
from bubble_mcp.html_runtime import create_from_html_runtime
from bubble_mcp.knowledge.advisor import knowledge_advice
from bubble_mcp.knowledge.cache import fetch_knowledge_record, import_knowledge_records, knowledge_search
from bubble_mcp.learning.store import append_learning_record, list_learning_records
from bubble_mcp.planner.deterministic import plan_message
from bubble_mcp.profile_status import profile_status
from bubble_mcp.readiness import run_readiness_check
from bubble_mcp.runtime_coverage import catalog_coverage_report
from bubble_mcp.runtime_smoke import run_runtime_smoke
from bubble_mcp.server.agent_guide import agent_guide, search_tool_catalog, task_recipe, task_runbook
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.skills.authoring import (
    create_skill_authoring_session,
    generate_skill_from_authoring_session,
    update_skill_authoring_session,
)
from bubble_mcp.skills.runner import run_skill
from bubble_mcp.skills.store import (
    disable_skill,
    enable_skill,
    export_skill,
    get_skill,
    import_skill,
    list_skills,
)
from bubble_mcp.skills.validator import describe_skill_file, validate_skill_file
from bubble_mcp.sessions.browser import capture_session_with_playwright
from bubble_mcp.sessions.store import list_sessions, load_session, save_session, session_from_payload
from bubble_mcp.style_import.runtime import create_styles_from_html_runtime
from bubble_mcp.tool_authoring.sessions import (
    append_capture_to_authoring_session,
    create_authoring_session,
    describe_authoring_session,
    finalize_authoring_session,
    generate_authoring_extension_pack,
    set_active_authoring_session,
)
from bubble_mcp.transfer.executor import execute_transfer_plan, preview_transfer_plan
from bubble_mcp.transfer.inventory import inventory_source_object
from bubble_mcp.transfer.planner import create_transfer_plan
from bubble_mcp.transfer.store import load_transfer_plan
from bubble_mcp.validators.semantic import validate_plan

_scheduled_deploys_rearmed = False


def _ensure_scheduled_deploys_rearmed() -> None:
    global _scheduled_deploys_rearmed
    if _scheduled_deploys_rearmed:
        return
    rearm_scheduled_deploys()
    _scheduled_deploys_rearmed = True


def _manual_guidance_payload(query: str, *, limit: int, purpose: str) -> dict[str, Any]:
    local = knowledge_search(query, limit=limit)
    if local.get("ok"):
        return {
            **local,
            "purpose": purpose,
            "cache_only": True,
            "remote_docs": "selective_fetch_available",
            "knowledge_advice": knowledge_advice(task=query, family=purpose),
        }
    advice = knowledge_advice(task=query, family=purpose)
    guidance = advice.get("guidance", []) if isinstance(advice, dict) else []
    return {
        "ok": bool(advice.get("used")),
        "query": query,
        "limit": limit,
        "count": len(guidance),
        "results": [
            {
                "id": item.get("id"),
                "source": item.get("source_id"),
                "source_url": item.get("source_url"),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "retrieved_at": item.get("retrieved_at"),
                "confidence": item.get("confidence"),
            }
            for item in guidance[:limit]
        ],
        "purpose": purpose,
        "cache_only": not bool(advice.get("remote_used")),
        "remote_docs": "selective_fetch",
        "knowledge_advice": advice,
    }


def _required_string_arg(arguments: dict[str, Any] | None, key: str, tool_name: str) -> str:
    value = str((arguments or {}).get(key) or "").strip()
    if not value:
        raise ValueError(f"{tool_name} requires {key}.")
    return value


def _cache_artifact_status(path: Path) -> dict[str, Any]:
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "path": str(path),
        "exists": exists,
        "mtime": stat.st_mtime if stat is not None else None,
    }


def _arguments_with_profile_defaults(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments or {})
    profile_name = str(args.get("profile") or "").strip()
    if not profile_name:
        return args
    profile = resolve_profile(load_settings(), profile_name)
    if profile is None:
        return args
    if profile.app_id and not str(args.get("app_id") or "").strip():
        args["app_id"] = profile.app_id
    if profile.appname and not str(args.get("appname") or "").strip():
        args["appname"] = profile.appname
    if profile.app_version and not str(args.get("app_version") or "").strip():
        args["app_version"] = profile.app_version
    return args


def _write_payload_for_target_version(payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    target_version = str(args.get("app_version") or "").strip()
    if not target_version:
        return payload
    normalized = deepcopy(payload)
    body = normalized.get("body") if isinstance(normalized.get("body"), dict) else normalized
    if isinstance(body, dict):
        body["app_version"] = target_version
        if "appVersion" in body:
            body["appVersion"] = target_version
    return normalized


def _style_metadata_name(style_id: str, style_data: dict[str, Any]) -> str:
    return str(
        style_data.get("name")
        or style_data.get("%nm")
        or style_data.get("%d")
        or style_data.get("display")
        or style_id
    ).strip()


def _style_metadata_type(style_id: str, style_data: dict[str, Any]) -> str:
    raw_type = str(style_data.get("type") or style_data.get("%x") or "").strip()
    if raw_type:
        return raw_type
    if "_" in style_id:
        return style_id.split("_", 1)[0]
    return ""


STYLE_IMPORT_PROPERTY_ALIASES: dict[str, tuple[str, ...]] = {
    "bg_color": ("%bgc", "background_color", "bg_color", "bgcolor"),
    "font_color": ("%fc", "font_color"),
    "font_size": ("%fs", "font_size"),
    "font_weight": ("font_weight",),
    "line_height": ("%lh", "line_height"),
    "letter_spacing": ("%ls", "letter_spacing"),
    "tag": ("tag_type", "tag"),
    "border_color": ("%bc", "border_color"),
    "border_width": ("%bw", "border_width"),
    "border_radius": ("%br", "border_radius", "border_roundness"),
    "border_style": ("%bos", "border_style"),
    "shadow_style": ("%bs", "shadow_style", "boxshadow_style"),
    "shadow_h": ("%bh", "shadow_h", "boxshadow_horizontal"),
    "shadow_v": ("%bv", "shadow_v", "boxshadow_vertical"),
    "shadow_blur": ("%bsb", "shadow_blur", "boxshadow_blur"),
    "shadow_spread": ("%bsp", "shadow_spread", "boxshadow_spread"),
    "shadow_color": ("%bsc", "shadow_color", "boxshadow_color"),
    "padding_top": ("padding_top",),
    "padding_bottom": ("padding_bottom",),
    "padding_left": ("padding_left",),
    "padding_right": ("padding_right",),
    "border_style_top": ("border_style_top",),
    "border_style_bottom": ("border_style_bottom",),
    "border_style_left": ("border_style_left",),
    "border_style_right": ("border_style_right",),
    "border_color_top": ("border_color_top",),
    "border_color_bottom": ("border_color_bottom",),
    "border_color_left": ("border_color_left",),
    "border_color_right": ("border_color_right",),
    "border_width_top": ("border_width_top",),
    "border_width_bottom": ("border_width_bottom",),
    "border_width_left": ("border_width_left",),
    "border_width_right": ("border_width_right",),
    "radius_top_left": ("border_roundness_top", "radius_top_left"),
    "radius_top_right": ("border_roundness_right", "radius_top_right"),
    "radius_bottom_right": ("border_roundness_bottom", "radius_bottom_right"),
    "radius_bottom_left": ("border_roundness_left", "radius_bottom_left"),
}

STYLE_IMPORT_STATE_TRIGGERS = {
    "hover": "is_hovered",
    "focus": "is_focused",
    "pressed": "is_pressed",
    "disabled": "isnt_clickable",
}


def _expanded_style_properties(properties: dict[str, Any]) -> dict[str, Any]:
    expanded = dict(properties)
    padding = expanded.pop("padding", None)
    if padding is not None:
        expanded.setdefault("padding_top", padding)
        expanded.setdefault("padding_bottom", padding)
        expanded.setdefault("padding_left", padding)
        expanded.setdefault("padding_right", padding)
    border_type = expanded.pop("border_type", None)
    if border_type == "independent":
        expanded["four_border_style"] = True
    elif border_type == "shared":
        expanded["four_border_style"] = False
    return expanded


def _style_property_aliases(property_name: str) -> tuple[str, ...]:
    aliases = STYLE_IMPORT_PROPERTY_ALIASES.get(property_name)
    if aliases is not None:
        return aliases
    return (property_name,)


def _style_color_tokens(metadata: dict[str, Any]) -> dict[str, str]:
    settings = metadata.get("settings") if isinstance(metadata.get("settings"), dict) else {}
    client_safe = settings.get("client_safe") if isinstance(settings.get("client_safe"), dict) else {}
    tokens: dict[str, str] = {}

    system_tokens = client_safe.get("color_tokens") if isinstance(client_safe.get("color_tokens"), dict) else {}
    for name, token_data in system_tokens.items():
        color_value = token_data.get("%d1") or token_data.get("default") if isinstance(token_data, dict) else token_data
        if isinstance(color_value, str) and color_value.strip():
            tokens[f"var(--color_{name}_default)"] = color_value.strip()

    user_tokens_wrapper = (
        client_safe.get("color_tokens_user") if isinstance(client_safe.get("color_tokens_user"), dict) else {}
    )
    user_tokens = user_tokens_wrapper.get("%d1") or user_tokens_wrapper.get("default") or {}
    if isinstance(user_tokens, dict):
        for color_id, token_data in user_tokens.items():
            if not isinstance(token_data, dict):
                continue
            if bool(token_data.get("%del", token_data.get("deleted", False))):
                continue
            color_value = token_data.get("rgba")
            if isinstance(color_value, str) and color_value.strip():
                tokens[f"var(--color_{color_id}_default)"] = color_value.strip()
    return tokens


def _style_color_tuple(value: Any, color_tokens: dict[str, str]) -> tuple[int, int, int, float] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in color_tokens:
        return _style_color_tuple(color_tokens[text], color_tokens)
    rgb_var_match = re.fullmatch(r"rgba\(\s*var\((--color_[^)]+_default)_rgb\)\s*,\s*([0-9.]+)\s*\)", text)
    if rgb_var_match is not None:
        base = _style_color_tuple(f"var({rgb_var_match.group(1)})", color_tokens)
        if base is None:
            return None
        return (base[0], base[1], base[2], float(rgb_var_match.group(2)))
    hex_match = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", text)
    if hex_match is not None:
        hex_value = hex_match.group(1)
        if len(hex_value) == 3:
            hex_value = "".join(char * 2 for char in hex_value)
        return (
            int(hex_value[0:2], 16),
            int(hex_value[2:4], 16),
            int(hex_value[4:6], 16),
            1.0,
        )
    rgb_match = re.fullmatch(
        r"rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})(?:\s*,\s*([0-9.]+))?\s*\)",
        text,
        flags=re.I,
    )
    if rgb_match is not None:
        alpha = float(rgb_match.group(4)) if rgb_match.group(4) is not None else 1.0
        return (int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3)), alpha)
    return None


def _style_colors_equal(expected: Any, actual: Any, color_tokens: dict[str, str]) -> bool:
    expected_color = _style_color_tuple(expected, color_tokens)
    actual_color = _style_color_tuple(actual, color_tokens)
    if expected_color is None or actual_color is None:
        return False
    rgb_distance = sum((expected_color[index] - actual_color[index]) ** 2 for index in range(3)) ** 0.5
    alpha_distance = abs(expected_color[3] - actual_color[3])
    return rgb_distance <= 16 and alpha_distance <= 0.02


def _style_values_equal(expected: Any, actual: Any, color_tokens: dict[str, str] | None = None) -> bool:
    if expected == actual:
        return True
    if expected is None and actual in (None, ""):
        return True
    if actual is None and expected in (None, ""):
        return True
    if color_tokens and _style_colors_equal(expected, actual, color_tokens):
        return True
    try:
        return float(expected) == float(actual)
    except (TypeError, ValueError):
        return str(expected).strip().lower() == str(actual).strip().lower()


def _compare_style_properties(
    expected: dict[str, Any],
    actual: dict[str, Any] | None,
    *,
    color_tokens: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(actual, dict):
        return {
            "ok": True,
            "checked": False,
            "reason": "style_properties_unavailable",
            "missing": [],
            "mismatched": [],
        }
    missing: list[dict[str, Any]] = []
    mismatched: list[dict[str, Any]] = []
    for property_name, expected_value in _expanded_style_properties(expected).items():
        aliases = _style_property_aliases(property_name)
        actual_key = next((alias for alias in aliases if alias in actual), None)
        if actual_key is None:
            missing.append({"property": property_name, "aliases": list(aliases), "expected": expected_value})
            continue
        actual_value = actual.get(actual_key)
        if not _style_values_equal(expected_value, actual_value, color_tokens):
            mismatched.append(
                {
                    "property": property_name,
                    "actual_key": actual_key,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
    return {
        "ok": not missing and not mismatched,
        "checked": True,
        "reason": None if not missing and not mismatched else "style_properties_mismatch",
        "missing": missing,
        "mismatched": mismatched,
    }


def _deep_string_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_deep_string_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_deep_string_values(item))
        return values
    if isinstance(value, str):
        return [value]
    return []


def _style_state_matches(state_name: str, state_data: dict[str, Any]) -> bool:
    trigger = STYLE_IMPORT_STATE_TRIGGERS.get(state_name)
    if not trigger:
        return False
    condition = state_data.get("%c") if isinstance(state_data.get("%c"), dict) else state_data.get("condition")
    return trigger in {value.strip() for value in _deep_string_values(condition)}


def _verify_style_states(
    expected_states: dict[str, dict[str, Any]],
    actual_states: Any,
    *,
    color_tokens: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not expected_states:
        return {"ok": True, "checked": True, "missing": [], "properties": {}}
    if not isinstance(actual_states, dict):
        return {
            "ok": True,
            "checked": False,
            "reason": "style_states_unavailable",
            "missing": [],
            "properties": {},
        }
    missing: list[str] = []
    property_checks: dict[str, Any] = {}
    for state_name, expected_properties in expected_states.items():
        actual_state = next(
            (
                state_data
                for state_data in actual_states.values()
                if isinstance(state_data, dict) and _style_state_matches(state_name, state_data)
            ),
            None,
        )
        if actual_state is None:
            missing.append(state_name)
            continue
        actual_properties = actual_state.get("%p") if isinstance(actual_state.get("%p"), dict) else actual_state.get("properties")
        property_checks[state_name] = _compare_style_properties(
            expected_properties,
            actual_properties,
            color_tokens=color_tokens,
        )
    return {
        "ok": not missing and all(check.get("ok") for check in property_checks.values()),
        "checked": True,
        "reason": None if not missing else "style_states_missing",
        "missing": missing,
        "properties": property_checks,
    }


def _verify_html_style_import(profile: str, candidate: dict[str, Any]) -> dict[str, Any]:
    style_name = str(candidate.get("name") or "").strip()
    element_type = str(candidate.get("element_type") or "").strip()
    expected_states_map = cast(
        dict[str, dict[str, Any]],
        candidate.get("states") if isinstance(candidate.get("states"), dict) else {},
    )
    expected_states = sorted(expected_states_map)
    refresh = _profile_cache_refresh({"profile": profile, "force": True})
    detection = cast(dict[str, Any], refresh.get("context_detection") if isinstance(refresh.get("context_detection"), dict) else {})
    context_path = str(detection.get("context_path") or "").strip()
    if not context_path:
        return {
            "ok": False,
            "reason": "context_path_missing",
            "refresh": refresh,
            "style_name": style_name,
            "element_type": element_type,
            "expected_states": expected_states,
        }
    context = load_context(Path(context_path))
    color_tokens = _style_color_tokens(context.metadata)
    styles = cast(dict[str, Any], context.metadata.get("styles") if isinstance(context.metadata.get("styles"), dict) else {})
    match: dict[str, Any] | None = None
    for style_id, style_data in styles.items():
        if not isinstance(style_data, dict):
            continue
        if _style_metadata_name(str(style_id), style_data).lower() != style_name.lower():
            continue
        if _style_metadata_type(str(style_id), style_data).lower() != element_type.lower():
            continue
        match = {"id": str(style_id), **style_data}
        break
    actual_properties: dict[str, Any] | None = None
    if isinstance(match, dict):
        if isinstance(match.get("%p"), dict):
            actual_properties = cast(dict[str, Any], match.get("%p"))
        elif isinstance(match.get("properties"), dict):
            actual_properties = cast(dict[str, Any], match.get("properties"))
    expected_base = cast(dict[str, Any], candidate.get("base") if isinstance(candidate.get("base"), dict) else {})
    property_check = _compare_style_properties(
        expected_base,
        actual_properties,
        color_tokens=color_tokens,
    )
    actual_states = None
    if isinstance(match, dict):
        actual_states = match.get("%s") if isinstance(match.get("%s"), dict) else match.get("states")
    state_check = _verify_style_states(
        expected_states_map,
        actual_states,
        color_tokens=color_tokens,
    )
    verification_ok = match is not None and bool(property_check.get("ok")) and bool(state_check.get("ok"))
    return {
        "ok": verification_ok,
        "reason": None if verification_ok else "style_verification_failed",
        "context_path": context_path,
        "style_name": style_name,
        "element_type": element_type,
        "expected_states": expected_states,
        "property_check": property_check,
        "state_check": state_check,
        "style": match,
        "refresh": {
            "ok": bool(refresh.get("ok")),
            "source": refresh.get("source"),
            "app_id": refresh.get("app_id"),
            "app_version": refresh.get("app_version"),
        },
    }


def _profile_cache_refresh(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = _arguments_with_profile_defaults(arguments)
    requested_profile = _required_string_arg(args, "profile", "bubble_profile_cache_refresh")
    settings = load_settings()
    resolved_profile = resolve_profile(settings, requested_profile)
    if resolved_profile is None:
        return {
            "ok": False,
            "error": "profile_not_found",
            "requested_profile": requested_profile,
            "available_profiles": sorted(settings.profiles),
            "next_user_action": "Create the profile with bubble_project_bootstrap or bubble_profile_add before refreshing cache.",
        }

    app_id = str(args.get("app_id") or resolved_profile.app_id).strip()
    app_version = str(args.get("app_version") or resolved_profile.app_version or "test").strip()
    force = bool(args.get("force", True))
    detection = detect_project_context(
        profile=resolved_profile.name,
        app_id=app_id or None,
        app_version=app_version,
        force=force,
        output=Path(str(args.get("output"))) if str(args.get("output") or "").strip() else None,
        bubble_file=Path(str(args.get("bubble_file"))) if str(args.get("bubble_file") or "").strip() else None,
        consolelog_file=Path(str(args.get("consolelog_file")))
        if str(args.get("consolelog_file") or "").strip()
        else None,
        include_id_to_path=not bool(args.get("skip_id_to_path")),
    )
    status = profile_status(
        resolved_profile.name,
        max_age_hours=int(args.get("max_age_hours") or 24),
    )
    bubble_file_path = default_bubble_export_path(resolved_profile.name, detection.app_id)
    bubble_modules_path = default_bubble_modules_dir(resolved_profile.name, detection.app_id)
    crawler_index_path = (
        detection.crawler_index_path
        if detection.crawler_index_path is not None
        else default_crawler_index_path(resolved_profile.name, detection.app_id)
    )
    artifacts = {
        "context": _cache_artifact_status(detection.context_path),
        "bubble_file": _cache_artifact_status(bubble_file_path),
        "bubble_modules": _cache_artifact_status(bubble_modules_path),
        "crawler_index": _cache_artifact_status(crawler_index_path),
    }
    return {
        "ok": bool(detection.ok),
        "profile": resolved_profile.name,
        "requested_profile": requested_profile,
        "app_id": detection.app_id,
        "app_version": app_version,
        "force": force,
        "source": detection.source,
        "updated": {name: bool(item["exists"]) for name, item in artifacts.items()},
        "artifacts": artifacts,
        "context_detection": detection.to_dict(),
        "ready": bool(status.get("ready")),
        "status": status,
        "next_user_action": "Profile cache refreshed. Use bubble_profile_status only if you need readiness details.",
    }


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a supported tool and return a JSON-serializable payload."""

    arguments = _arguments_with_profile_defaults(arguments)
    _ = arguments
    if name == "bubble_health_check":
        return {
            "ok": True,
            "version": __version__,
            "capabilities": {
                "profiles": True,
                "session_capture": "manual-interface",
                "context_engine": True,
                "planner": True,
                "html_import": True,
                "evals": True,
                "mutations": True,
                "dry_run": "optional",
                "figma_bridge": True,
                "figma_plugin": False,
                "aria_runtime_dispatch": True,
                "aria_tool_catalog_count": len(ARIA_BUBBLE_TOOL_NAMES),
            },
        }
    if name == "bubble_tool_coverage":
        args = arguments or {}
        return catalog_coverage_report(include_tools=bool(args.get("include_tools") or args.get("include_details")))
    if name == "bubble_catalog_quality":
        return catalog_quality_report()
    if name == "bubble_schedule_deploy":
        _ensure_scheduled_deploys_rearmed()
        args = arguments or {}
        return schedule_deploy(
            profile=_required_string_arg(args, "profile", name),
            scheduled_at=_required_string_arg(args, "scheduled_at", name),
            message=_required_string_arg(args, "message", name),
            execute=bool(args.get("execute")),
            confirm=bool(args.get("confirm")),
            preview_id=str(args.get("preview_id") or "") or None,
            retry_count=int(args.get("retry_count") or 0),
            headless=bool(args.get("headless")),
            wait_seconds=int(args.get("wait_seconds") or 120),
            auto_fix_objective_issues=bool(args.get("auto_fix_objective_issues")),
        )
    if name == "bubble_list_scheduled_deploys":
        _ensure_scheduled_deploys_rearmed()
        args = arguments or {}
        return list_scheduled_deploys(profile=_required_string_arg(args, "profile", name))
    if name == "bubble_cancel_scheduled_deploy":
        _ensure_scheduled_deploys_rearmed()
        args = arguments or {}
        return cancel_scheduled_deploy(
            profile=_required_string_arg(args, "profile", name),
            deploy_id=_required_string_arg(args, "deploy_id", name),
        )
    if name == "bubble_deploy_history":
        _ensure_scheduled_deploys_rearmed()
        args = arguments or {}
        return deploy_history(
            profile=_required_string_arg(args, "profile", name),
            limit=int(args.get("limit") or 50),
            include_cancelled=bool(args.get("include_cancelled", True)),
        )
    if name == "bubble_extension_list":
        return {"ok": True, "extensions": [item.to_dict() for item in list_extensions()]}
    if name == "bubble_extension_validate":
        extension_path = _required_string_arg(arguments, "path", name)
        return validate_extension_pack(Path(extension_path)).to_dict()
    if name == "bubble_extension_import":
        extension_path = _required_string_arg(arguments, "path", name)
        return import_extension(Path(extension_path)).to_dict()
    if name == "bubble_extension_enable":
        extension_id = _required_string_arg(arguments, "extension_id", name)
        return enable_extension(extension_id).to_dict()
    if name == "bubble_extension_disable":
        extension_id = _required_string_arg(arguments, "extension_id", name)
        return disable_extension(extension_id).to_dict()
    if name == "bubble_extension_call":
        args = arguments or {}
        tool_name = _required_string_arg(args, "tool", name)
        raw_tool_arguments = args.get("arguments")
        if not isinstance(raw_tool_arguments, dict):
            raise ValueError("bubble_extension_call requires arguments object.")
        return preview_extension_tool_call(tool_name, raw_tool_arguments)
    if name == "bubble_extension_companion_start":
        args = arguments or {}
        raw_port = args.get("port")
        port = 3847 if raw_port in (None, "") else int(str(raw_port))
        return start_extension_companion_background(
            ExtensionCompanionConfig(
                host=str(args.get("host") or "127.0.0.1"),
                port=port,
                capture_key=str(args.get("capture_key") or ""),
                tool_session_id=str(args.get("tool_session_id") or "") or None,
            )
        )
    if name == "bubble_extension_companion_status":
        return extension_companion_background_status()
    if name == "bubble_extension_companion_stop":
        return stop_extension_companion_background()
    if name == "bubble_skill_validate":
        skill_path = _required_string_arg(arguments, "path", name)
        return validate_skill_file(Path(skill_path))
    if name == "bubble_skill_describe":
        args = arguments or {}
        skill_path = str(args.get("path") or "").strip()
        skill_id = str(args.get("skill_id") or "").strip()
        if skill_path:
            return describe_skill_file(Path(skill_path))
        if skill_id:
            installed = get_skill(skill_id)
            return describe_skill_file(installed.path)
        raise ValueError("bubble_skill_describe requires path or skill_id.")
    if name == "bubble_skill_import":
        skill_path = _required_string_arg(arguments, "path", name)
        return import_skill(Path(skill_path))
    if name == "bubble_skill_export":
        args = arguments or {}
        skill_id = _required_string_arg(args, "skill_id", name)
        output = _required_string_arg(args, "output", name)
        return export_skill(skill_id, Path(output))
    if name == "bubble_skill_list":
        return {"ok": True, "skills": [skill.to_dict() for skill in list_skills()]}
    if name == "bubble_skill_enable":
        skill_id = _required_string_arg(arguments, "skill_id", name)
        return enable_skill(skill_id)
    if name == "bubble_skill_disable":
        skill_id = _required_string_arg(arguments, "skill_id", name)
        return disable_skill(skill_id)
    if name == "bubble_skill_run":
        args = arguments or {}
        skill_id = _required_string_arg(args, "skill_id", name)
        raw_inputs = args.get("inputs")
        if raw_inputs is not None and not isinstance(raw_inputs, dict):
            raise ValueError("bubble_skill_run requires inputs to be an object.")
        return run_skill(
            skill_id,
            inputs=raw_inputs,
            execute=bool(args.get("execute")),
            approve_execution=bool(args.get("approve_execution")),
            run_id=str(args.get("run_id") or "") or None,
        )
    if name == "bubble_skill_author_start":
        args = arguments or {}
        return create_skill_authoring_session(
            objective=_required_string_arg(args, "objective", name),
            risk=str(args.get("risk") or "read_only"),
            profile=str(args.get("profile") or "") or None,
        )
    if name == "bubble_skill_author_update":
        args = arguments or {}
        return update_skill_authoring_session(
            _required_string_arg(args, "session_id", name),
            answer=_required_string_arg(args, "answer", name),
            field=str(args.get("field") or "") or None,
        )
    if name == "bubble_skill_author_generate":
        args = arguments or {}
        output_dir = str(args.get("output_dir") or "").strip()
        return generate_skill_from_authoring_session(
            _required_string_arg(args, "session_id", name),
            skill_id=str(args.get("skill_id") or "") or None,
            output_dir=Path(output_dir) if output_dir else None,
        )
    if name == "bubble_language_index":
        args = arguments or {}
        return build_language_index(profile=str(args.get("profile") or "") or None)
    if name == "bubble_language_query":
        args = arguments or {}
        return language_query(
            query=_required_string_arg(args, "query", name),
            families=args.get("families") if isinstance(args.get("families"), list) else None,
            sources=args.get("sources") if isinstance(args.get("sources"), list) else None,
            risks=args.get("risks") if isinstance(args.get("risks"), list) else None,
            limit=int(args.get("limit") or 12),
            profile=str(args.get("profile") or "") or None,
            framework=str(args.get("framework") or "") or None,
            cached_registry_version=str(args.get("cached_registry_version") or "") or None,
        )
    if name == "bubble_language_tool_detail":
        args = arguments or {}
        raw_tools = args.get("tools")
        if not isinstance(raw_tools, list):
            raise ValueError("bubble_language_tool_detail requires tools to be an array.")
        return language_tool_detail([str(tool) for tool in raw_tools], detail=str(args.get("detail") or "compact"))
    if name == "bubble_language_diff":
        args = arguments or {}
        return language_diff(since=_required_string_arg(args, "since", name), profile=str(args.get("profile") or "") or None)
    if name == "bubble_framework_language_pack":
        args = arguments or {}
        return framework_language_pack(
            framework=_required_string_arg(args, "framework", name),
            profile=str(args.get("profile") or "") or None,
            scope=str(args.get("scope") or ""),
            max_tools=int(args.get("limit") or args.get("max_tools") or 12),
        )
    if name == "bubble_framework_compile_program":
        args = arguments or {}
        raw_program = args.get("program")
        if not isinstance(raw_program, dict):
            raise ValueError("bubble_framework_compile_program requires program to be an object.")
        return compile_framework_program(
            framework=_required_string_arg(args, "framework", name),
            profile=_required_string_arg(args, "profile", name),
            program=raw_program,
        )
    if name == "bubble_framework_plan_from_text":
        args = arguments or {}
        return plan_framework_text(
            _required_string_arg(args, "framework", name),
            _required_string_arg(args, "profile", name),
            _required_string_arg(args, "text", name),
        )
    if name == "bubble_framework_execute_program":
        from bubble_mcp.frameworks.program_runner import execute_framework_program

        args = arguments or {}
        raw_program = args.get("program")
        if not isinstance(raw_program, dict):
            raise ValueError("bubble_framework_execute_program requires program to be an object.")
        artifact_dir = str(args.get("artifact_dir") or "").strip()
        return execute_framework_program(
            framework=_required_string_arg(args, "framework", name),
            profile=_required_string_arg(args, "profile", name),
            program=raw_program,
            mode=str(args.get("mode") or "") or None,
            approved=bool(args.get("approved")),
            artifact_dir=Path(artifact_dir) if artifact_dir else None,
        )
    if name == "bubble_framework_workspace_sync":
        args = arguments or {}
        return sync_artifacts_to_workspace(
            framework=_required_string_arg(args, "framework", name),
            artifact_dir=Path(_required_string_arg(args, "artifact_dir", name)),
            workspace_dir=Path(_required_string_arg(args, "workspace_dir", name)),
        )
    if name == "bubble_language_cache_status":
        args = arguments or {}
        return cached_language_index(
            _required_string_arg(args, "framework", name),
            _required_string_arg(args, "profile", name),
        )
    if name == "bubble_framework_list":
        return list_frameworks()
    if name == "bubble_framework_generate_artifacts":
        args = arguments or {}
        raw_context_summary = args.get("context_summary")
        if raw_context_summary is not None and not isinstance(raw_context_summary, dict):
            raise ValueError("bubble_framework_generate_artifacts requires context_summary to be an object.")
        output_dir = str(args.get("output_dir") or "").strip()
        return generate_framework_artifacts(
            framework=_required_string_arg(args, "framework", name),
            profile=_required_string_arg(args, "profile", name),
            objective=_required_string_arg(args, "objective", name),
            scope=str(args.get("scope") or "") or None,
            context_summary=raw_context_summary,
            output_dir=Path(output_dir) if output_dir else None,
        )
    if name == "bubble_framework_sync_evidence":
        args = arguments or {}
        raw_evidence = args.get("evidence")
        if not isinstance(raw_evidence, dict):
            raise ValueError("bubble_framework_sync_evidence requires evidence to be an object.")
        artifact_dir = str(args.get("artifact_dir") or "").strip()
        output_dir = str(args.get("output_dir") or "").strip()
        return sync_framework_evidence(
            framework=_required_string_arg(args, "framework", name),
            profile=_required_string_arg(args, "profile", name),
            evidence=raw_evidence,
            artifact_dir=Path(artifact_dir) if artifact_dir else None,
            output_dir=Path(output_dir) if output_dir else None,
        )
    if name == "bubble_framework_status":
        args = arguments or {}
        output_dir = str(args.get("output_dir") or "").strip()
        return framework_status(
            framework=str(args.get("framework") or "") or None,
            profile=str(args.get("profile") or "") or None,
            output_dir=Path(output_dir) if output_dir else None,
        )
    if name == "bubble_tool_wizard_start":
        args = arguments or {}
        session = create_authoring_session(
            intent=_required_string_arg(args, "intent", name),
            target=_required_string_arg(args, "target", name),
            profile=_required_string_arg(args, "profile", name),
        )
        return {
            "ok": True,
            "session": session.to_dict(),
            "active": True,
            "workflow": {
                "next_user_action": (
                    "Open the Bubble editor, enable the Chrome companion, perform the target actions, "
                    "then return and finalize this same session."
                ),
                "finish_with": "bubble_tool_wizard_finalize",
            },
        }
    if name == "bubble_tool_wizard_add_capture":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        file_path = _required_string_arg(args, "file", name)
        return append_capture_to_authoring_session(session_id, Path(file_path))
    if name == "bubble_tool_wizard_activate":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        return set_active_authoring_session(session_id)
    if name == "bubble_tool_wizard_describe":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        return describe_authoring_session(session_id)
    if name == "bubble_tool_wizard_finalize":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        if bool(args.get("generate_pack") or args.get("generate")):
            output_dir = str(args.get("output_dir") or "").strip()
            return generate_authoring_extension_pack(
                session_id,
                extension_id=str(args.get("extension_id") or "") or None,
                tool_name=str(args.get("tool_name") or "") or None,
                output_dir=Path(output_dir) if output_dir else None,
            )
        return finalize_authoring_session(session_id)
    if name == "bubble_tool_wizard_generate":
        args = arguments or {}
        session_id = _required_string_arg(args, "session_id", name)
        output_dir = str(args.get("output_dir") or "").strip()
        return generate_authoring_extension_pack(
            session_id,
            extension_id=str(args.get("extension_id") or "") or None,
            tool_name=str(args.get("tool_name") or "") or None,
            output_dir=Path(output_dir) if output_dir else None,
        )
    if name == "bubble_learning_record":
        args = arguments or {}
        value = args.get("value")
        if value is not None and not isinstance(value, dict):
            raise ValueError("bubble_learning_record requires value to be a JSON object.")
        record = append_learning_record(
            scope=str(args.get("scope") or ""),
            key=str(args.get("key") or ""),
            value=value,
            source=str(args.get("source") or ""),
            confidence=str(args.get("confidence") or ""),
            profile=str(args.get("profile") or "") or None,
            project=str(args.get("project") or "") or None,
            extension_id=str(args.get("extension_id") or "") or None,
        )
        return {"ok": True, "record": record.to_dict()}
    if name == "bubble_learning_list":
        args = arguments or {}
        return {
            "ok": True,
            "records": [
                record.to_dict()
                for record in list_learning_records(
                    scope=str(args.get("scope") or "") or None,
                    profile=str(args.get("profile") or "") or None,
                    project=str(args.get("project") or "") or None,
                    extension_id=str(args.get("extension_id") or "") or None,
                )
            ],
        }
    if name == "bubble_knowledge_refresh_source":
        args = arguments or {}
        source = _required_string_arg(args, "source", name)
        file_path = _required_string_arg(args, "file", name)
        return import_knowledge_records(Path(file_path), source=source)
    if name == "bubble_knowledge_search":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        return knowledge_search(query, limit=int(args.get("limit") or 8))
    if name == "bubble_knowledge_fetch":
        args = arguments or {}
        record_id = _required_string_arg(args, "record_id", name)
        return fetch_knowledge_record(record_id)
    if name == "bubble_manual_guidance":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        return _manual_guidance_payload(query, limit=int(args.get("limit") or 5), purpose="manual_guidance")
    if name == "bubble_manual_context_for_tool_authoring":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        return _manual_guidance_payload(query, limit=int(args.get("limit") or 5), purpose="tool_authoring")
    if name == "bubble_manual_context_for_validation":
        args = arguments or {}
        query = _required_string_arg(args, "query", name)
        return _manual_guidance_payload(query, limit=int(args.get("limit") or 5), purpose="validation")
    if name == "bubble_readiness_check":
        args = arguments or {}
        return run_readiness_check(
            call_tool,
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "root"),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            max_age_hours=int(args.get("max_age_hours") or 24),
            include_family_preview=bool(args.get("include_family_preview")),
            include_details=bool(args.get("include_details")),
            stop_on_failure=bool(args.get("stop_on_failure")),
        )
    if name == "bubble_agent_guide":
        return agent_guide(str((arguments or {}).get("task") or (arguments or {}).get("message") or ""))
    if name == "bubble_tool_search":
        args = arguments or {}
        return search_tool_catalog(str(args.get("query") or ""), limit=int(args.get("limit") or 8))
    if name == "bubble_task_recipe":
        args = arguments or {}
        return task_recipe(
            str(args.get("task") or args.get("message") or ""),
            recipe=str(args.get("recipe") or ""),
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or ""),
            parent=str(args.get("parent") or "root"),
            execute=bool(args.get("execute")),
        )
    if name == "bubble_task_runbook":
        args = arguments or {}
        return task_runbook(
            str(args.get("task") or args.get("message") or ""),
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or ""),
            parent=str(args.get("parent") or "root"),
            execute=bool(args.get("execute")),
            search_limit=int(args.get("search_limit") or args.get("limit") or 6),
            include_profile_status=bool(args.get("include_profile_status")),
        )
    if name == "bubble_runtime_smoke":
        args = arguments or {}
        return run_runtime_smoke(
            call_tool,
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "root"),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            suite=str(args.get("suite") or "coverage"),
            limit=int(args.get("limit") or 0),
            html_url=str(args.get("html_url") or args.get("url") or ""),
            selector=str(args.get("selector") or ""),
            include_details=bool(args.get("include_details")),
            stop_on_failure=bool(args.get("stop_on_failure")),
            execute=bool(args.get("execute")),
            cleanup=bool(args.get("cleanup")),
            run_id=str(args.get("run_id") or ""),
            verify_context=bool(args.get("verify_context")),
            verification_output=str(args.get("verification_output") or ""),
        )
    if name == "bubble_project_bootstrap":
        args = arguments or {}
        profile_name = str(args.get("profile") or args.get("name") or "").strip()
        if not profile_name:
            raise ValueError("bubble_project_bootstrap requires profile.")
        settings = load_settings()
        existing_profile = resolve_profile(settings, profile_name)
        app_id = str(args.get("app_id") or (existing_profile.app_id if existing_profile else "")).strip()
        if app_id:
            updated_profile = BubbleProfile(
                name=profile_name,
                app_id=app_id,
                appname=str(args.get("appname") or (existing_profile.appname if existing_profile else app_id)).strip()
                or app_id,
                editor_url=str(
                    args.get("editor_url") or (existing_profile.editor_url if existing_profile else "")
                ).strip()
                or None,
                app_version=str(
                    args.get("app_version") or (existing_profile.app_version if existing_profile else "test")
                ).strip()
                or None,
                app_json_path=str(
                    args.get("app_json_path") or (existing_profile.app_json_path if existing_profile else "")
                ).strip()
                or None,
                consolelog_json_path=str(
                    args.get("consolelog_json_path")
                    or (existing_profile.consolelog_json_path if existing_profile else "")
                ).strip()
                or None,
            )
            save_settings(with_profile(settings, updated_profile))

        context_detection: dict[str, Any] | None = None
        if bool(args.get("detect_context")) and app_id:
            try:
                detection_result = detect_project_context(
                    profile=profile_name,
                    app_id=app_id,
                    app_version=str(args.get("app_version") or "test"),
                    force=bool(args.get("force_context")),
                )
                context_detection = detection_result.to_dict()
            except Exception as exc:
                context_detection = {"ok": False, "error": str(exc)}

        status = profile_status(
            profile_name,
            max_age_hours=int(args.get("max_age_hours") or 24),
        )
        profile_changed = bool(app_id) and (
            existing_profile is None
            or existing_profile.app_id != app_id
            or bool(
                args.get("appname")
                or args.get("editor_url")
                or args.get("app_version")
                or args.get("app_json_path")
                or args.get("consolelog_json_path")
            )
        )
        return {
            "ok": bool(status.get("ok")),
            "profile": profile_name,
            "profile_changed": profile_changed,
            "context_detection": context_detection,
            "ready": bool(status.get("ready")),
            "next_actions": status.get("next_actions", []),
            "status": status,
        }
    if name == "bubble_profile_add":
        args = arguments or {}
        profile_name = str(args.get("name") or args.get("profile") or "").strip()
        app_id = str(args.get("app_id") or "").strip()
        if not profile_name:
            raise ValueError("bubble_profile_add requires name.")
        if not app_id:
            raise ValueError("bubble_profile_add requires app_id.")
        settings = load_settings()
        new_profile = BubbleProfile(
            name=profile_name,
            app_id=app_id,
            appname=str(args.get("appname") or app_id).strip() or app_id,
            editor_url=str(args.get("editor_url") or "").strip() or None,
            app_version=str(args.get("app_version") or "test").strip() or None,
            app_json_path=str(args.get("app_json_path") or "").strip() or None,
            consolelog_json_path=str(args.get("consolelog_json_path") or "").strip() or None,
        )
        save_settings(with_profile(settings, new_profile))
        return {
            "ok": True,
            "profile": new_profile.name,
            "app_id": new_profile.app_id,
            "settings": str(settings.config_dir / "settings.json"),
        }
    if name == "bubble_profile_list":
        settings = load_settings()
        return {
            "ok": True,
            "default_profile": settings.default_profile,
            "profiles": [
                {
                    "name": profile_item.name,
                    "app_id": profile_item.app_id,
                    "appname": profile_item.appname,
                    "editor_url": profile_item.editor_url,
                }
                for profile_item in settings.profiles.values()
            ],
        }
    if name == "bubble_profile_status":
        args = arguments or {}
        return profile_status(
            str(args.get("profile") or ""),
            max_age_hours=int(args.get("max_age_hours") or 24),
        )
    if name == "bubble_profile_cache_refresh":
        return _profile_cache_refresh(arguments)
    if name == "bubble_context_summary":
        summary_path = Path(str((arguments or {}).get("file") or ""))
        context = load_context(summary_path)
        return {
            "ok": True,
            "summary": context.summary(),
            "freshness": context_freshness(context, path=summary_path),
        }
    if name == "bubble_context_find":
        args = arguments or {}
        profile_name = str(args.get("profile") or "").strip()
        if args.get("file"):
            context = load_context(Path(str(args.get("file") or "")))
        else:
            settings = load_settings()
            resolved_profile = resolve_profile(settings, profile_name or None)
            if resolved_profile is None:
                return {
                    "ok": False,
                    "error": "profile_required",
                    "message": "Provide file or a configured profile to search project context.",
                }
            status = profile_status(resolved_profile.name)
            raw_context_status = status.get("context")
            context_status = raw_context_status if isinstance(raw_context_status, dict) else {}
            context_path = str(context_status.get("path") or "").strip()
            if not context_path or not Path(context_path).exists():
                return {
                    "ok": False,
                    "error": "context_missing",
                    "profile": resolved_profile.name,
                    "next_actions": status.get("next_actions", []),
                }
            context = load_context_with_overlay(
                Path(context_path),
                profile=resolved_profile.name,
                app_id=resolved_profile.app_id,
            )
        return {
            "ok": True,
            **({"profile": profile_name} if profile_name and args.get("file") else {}),
            **context_find_payload(
                context,
                str(args.get("query") or ""),
                int(args.get("limit") or 10),
                exact=bool(args.get("exact")),
                include_metadata=bool(args.get("include_metadata", True)),
            ),
        }
    if name == "bubble_context_import":
        args = arguments or {}
        context = import_context_artifact(
            Path(str(args.get("file") or "")),
            kind=str(args.get("kind") or "auto"),
        )
        output = str(args.get("output") or "").strip()
        if output:
            save_context(context, Path(output))
        return {"ok": True, "summary": context.summary(), "output": output or None}
    if name in {"bubble_context_detect", "crawl_project", "get_project_index"}:
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError(f"{name} requires a profile.")
        detection_result = detect_project_context(
            profile=profile,
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            force=bool(args.get("force")),
            output=Path(str(args.get("output"))) if str(args.get("output") or "").strip() else None,
            bubble_file=Path(str(args.get("bubble_file"))) if str(args.get("bubble_file") or "").strip() else None,
            consolelog_file=Path(str(args.get("consolelog_file")))
            if str(args.get("consolelog_file") or "").strip()
            else None,
            include_id_to_path=not bool(args.get("skip_id_to_path")),
        )
        return detection_result.to_dict()
    if name in {"bubble_plan", "bubble_plan_dry_run"}:
        args = arguments or {}
        plan = plan_message(
            str(args.get("message") or ""),
            context=str(args.get("context") or "index"),
            parent=str(args.get("parent") or "index"),
        ).to_dict()
        validation = validate_plan(plan)
        structural_validation = validate_structure(plan, execute=False)
        return {
            "ok": True,
            "plan": plan,
            "validation": validation,
            "structural_validation": structural_validation,
            "next_user_action": next_user_action(structural_validation),
            "operation_snapshot": operation_snapshot(
                plan=plan,
                validation=structural_validation,
                execute=False,
                phase="planned",
            ),
        }
    if name == "bubble_eval_run":
        args = arguments or {}
        offset_value = str(args.get("offset") or "").strip()
        limit_value = str(args.get("limit") or "").strip()
        failed_from_value = str(args.get("failed_from") or "").strip()
        return {
            "ok": True,
            "report": run_eval(
                Path(str(args.get("dataset") or "")),
                app_id=str(args.get("app_id") or "") or None,
                compile_plans=bool(args.get("compile")),
                case_filter=args.get("filter") or args.get("case_filter") or None,
                failed_from=Path(failed_from_value) if failed_from_value else None,
                offset=int(offset_value) if offset_value else 0,
                limit=int(limit_value) if limit_value else None,
            ),
        }
    if name == "bubble_eval_export_expert":
        args = arguments or {}
        return export_expert_eval_cases(
            Path(str(args.get("input") or "")),
            Path(str(args.get("output") or "")),
            limit=int(args.get("limit") or 250),
        )
    if name == "bubble_visual_compare":
        args = arguments or {}
        return compare_visual_snapshot_files(
            Path(str(args.get("reference") or "")),
            Path(str(args.get("actual") or "")),
            tolerance_px=float(args.get("tolerance_px") or 4),
            tolerance_ratio=float(args.get("tolerance_ratio") or 0.08),
            require_text=bool(args.get("require_text", True)),
            require_images=bool(args.get("require_images")),
        )
    if name == "bubble_visual_audit":
        return audit_visual_from_inputs(arguments or {})
    if name == "bubble_visual_capture":
        args = arguments or {}
        output_value = str(args.get("output") or "").strip()
        return capture_visual_snapshot(
            str(args.get("source") or ""),
            selector=str(args.get("selector") or ""),
            rendered_html=bool(args.get("rendered_html", True)),
            viewport_width=int(args.get("viewport_width") or 1365),
            viewport_height=int(args.get("viewport_height") or 768),
            wait_ms=int(args.get("wait_ms") or 0),
            selector_timeout_ms=int(args.get("selector_timeout_ms") or 5000),
            max_nodes=int(args.get("max_nodes") or 250),
            allow_raw_fallback=bool(args.get("allow_raw_fallback", True)),
            output=Path(output_value) if output_value else None,
        )
    if name == "bubble_visual_capture_actual":
        args = arguments or {}
        output_value = str(args.get("output") or "").strip()
        raw_query = args.get("url_query") or args.get("query")
        visual_query = {str(key): str(value) for key, value in raw_query.items()} if isinstance(raw_query, dict) else {}
        return capture_bubble_visual_snapshot(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            page=str(args.get("page") or args.get("context") or "index"),
            selector=str(args.get("selector") or ""),
            public_base_url=str(args.get("public_base_url") or ""),
            url=str(args.get("url") or ""),
            query=visual_query,
            viewport_width=int(args.get("viewport_width") or 1365),
            viewport_height=int(args.get("viewport_height") or 768),
            wait_ms=int(args.get("wait_ms") or 1000),
            selector_timeout_ms=int(args.get("selector_timeout_ms") or 10000),
            max_nodes=int(args.get("max_nodes") or 250),
            output=Path(output_value) if output_value else None,
        )
    if name == "bubble_compile_plan":
        args = arguments or {}
        compile_plan = args.get("plan")
        if not isinstance(compile_plan, dict):
            raise ValueError("bubble_compile_plan requires a plan object.")
        app_id = str(args.get("app_id") or "").strip()
        if not app_id:
            raise ValueError("bubble_compile_plan requires app_id.")
        compile_context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            compile_context = load_context_with_overlay(
                Path(context_file),
                profile=str(args.get("profile") or "") or None,
                app_id=app_id,
            )
        return {
            "ok": True,
            "plan": compile_plan_to_write_payloads(
                compile_plan,
                app_id=app_id,
                app_version=str(args.get("app_version") or "test"),
                context=compile_context,
            ),
        }
    if name == "bubble_session_list":
        return {"ok": True, "sessions": list_sessions()}
    if name == "bubble_session_inspect":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_session_inspect requires a profile.")
        inspected_session = load_session(profile)
        if inspected_session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        app_id = str(args.get("app_id") or inspected_session.app_id or "").strip()
        sample_payload: dict[str, Any] = {
            "appname": app_id,
            "app_version": inspected_session.app_version or "test",
            "changes": [],
        }
        write_headers = build_editor_write_headers(inspected_session, sample_payload)
        return {
            "ok": True,
            "profile": profile,
            "session": inspected_session.to_dict(redact=True),
            "stored_header_keys": sorted(inspected_session.headers.keys()),
            "session_auth_present": bool(inspected_session.cookies),
            "session_auth_value_length": len(inspected_session.cookies or ""),
            "computed_write_header_keys": sorted(write_headers.keys()),
            "computed_write_headers": redact_sensitive(write_headers),
        }
    if name == "bubble_session_login":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_session_login requires a profile.")
        settings = load_settings()
        configured_profile = resolve_profile(settings, profile)
        app_id = str(args.get("app_id") or (configured_profile.app_id if configured_profile else "")).strip()
        if not app_id:
            raise ValueError("bubble_session_login requires app_id when the profile is not configured.")
        app_version = str(
            args.get("app_version") or (configured_profile.app_version if configured_profile else "test")
        ).strip() or "test"
        progress_messages: list[str] = []

        def collect_progress(message: str) -> None:
            progress_messages.append(message)

        captured_session = capture_session_with_playwright(
            app_id=app_id,
            editor_url=str(args.get("editor_url") or "").strip() or None,
            headless=bool(args.get("headless")),
            wait_seconds=int(args.get("wait_seconds") or 180),
            user_data_dir=settings.config_dir / "browser-profiles" / profile,
            app_version=app_version,
            progress=collect_progress,
        )
        session_path = save_session(profile, captured_session)
        return {
            "ok": True,
            "profile": profile,
            "path": str(session_path),
            "progress": progress_messages,
            "session": captured_session.to_dict(redact=True),
        }
    if name == "bubble_session_import":
        args = arguments or {}
        raw_session = args.get("session")
        if not isinstance(raw_session, dict):
            raise ValueError("bubble_session_import requires a session object.")
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_session_import requires a profile.")
        imported_session = session_from_payload(
            raw_session,
            default_app_id=str(args.get("app_id") or "") or None,
        )
        session_path = save_session(profile, imported_session)
        return {
            "ok": True,
            "profile": profile,
            "path": str(session_path),
            "session": imported_session.to_dict(redact=True),
        }
    if name == "bubble_editor_write":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_editor_write requires a profile.")
        write_payload = args.get("payload")
        if not isinstance(write_payload, dict):
            raise ValueError("bubble_editor_write requires a payload object.")
        write_session = load_session(profile)
        if write_session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        execute = bool(args.get("execute"))
        targeted_payload = _write_payload_for_target_version(write_payload, args)
        write_result: dict[str, Any] = BubbleEditorClient().write(
            targeted_payload,
            write_session,
            dry_run=not execute,
            calculate_derived=bool(args.get("calculate_derived")),
        )
        if execute and write_result.get("ok"):
            record_mutation_overlay(
                profile=profile,
                app_id=str(
                    write_result.get("request", {}).get("payload", {}).get("appname")
                    or write_session.app_id
                ),
                payload=write_result.get("request", {}).get("payload") or targeted_payload,
                source="bubble_editor_write",
                response=write_result.get("response"),
            )
        return write_result
    if name == "bubble_plugin_install":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_plugin_install requires a profile.")
        plugin_key = str(args.get("plugin_key") or args.get("plugin") or "").strip()
        if not plugin_key:
            raise ValueError("bubble_plugin_install requires plugin_key.")
        write_session = load_session(profile)
        if write_session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        execute = bool(args.get("execute"))
        result = install_plugin(
            profile=profile,
            session=write_session,
            plugin_key=plugin_key,
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
            plugin_value=args.get("plugin_value", True),
            installed_version=args.get("installed_version", 1),
            installed_version_key=str(args.get("installed_version_key") or "") or None,
            include_installed_version=(
                bool(args["include_installed_version"])
                if "include_installed_version" in args
                else None
            ),
            id_counter=int(args["id_counter"]) if args.get("id_counter") is not None else None,
            execute=execute,
            post_check_conflicts=bool(args.get("post_check_conflicts", True)),
            calculate_derived=bool(args.get("calculate_derived", True)),
            notify_ai_context_change=bool(args.get("notify_ai_context_change", True)),
        )
        write_step = result.get("steps", {}).get("write") if isinstance(result.get("steps"), dict) else {}
        if execute and result.get("ok") and isinstance(write_step, dict):
            record_mutation_overlay(
                profile=profile,
                app_id=str(
                    write_step.get("request", {}).get("payload", {}).get("appname")
                    or write_session.app_id
                ),
                payload=write_step.get("request", {}).get("payload") or result.get("write_payload"),
                source="bubble_plugin_install",
                response=write_step.get("response"),
            )
        return result
    if name == "bubble_execute_plan":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_execute_plan requires a profile.")
        execution_plan = args.get("plan")
        if not isinstance(execution_plan, dict):
            raise ValueError("bubble_execute_plan requires a plan object.")
        execution_context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            execution_context = load_context_with_overlay(
                Path(context_file),
                profile=profile,
                app_id=str(args.get("app_id") or "") or None,
            )
        return execute_plan(
            execution_plan,
            profile=profile,
            execute=bool(args.get("execute")),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            compile_missing=bool(args.get("compile")),
            context=execution_context,
        )
    if name == "bubble_transfer_inventory":
        args = arguments or {}
        settings = load_settings()
        requested_source_profile = _required_string_arg(args, "source_profile", name)
        resolved_source_profile = resolve_profile(settings, requested_source_profile)
        if resolved_source_profile is None:
            raise ValueError(f"source_profile not configured: {requested_source_profile}")
        configured_path = Path(resolved_source_profile.app_json_path).expanduser() if resolved_source_profile.app_json_path else None
        if configured_path is not None and not configured_path.is_absolute():
            configured_path = settings.config_dir / configured_path
        source_context_path = (
            configured_path
            if configured_path and configured_path.exists() and configured_path.name.endswith("-context.json")
            else default_context_path(
                resolved_source_profile.name,
                resolved_source_profile.app_id,
            )
        )
        if not source_context_path.exists():
            raise ValueError(f"Source context is missing for profile '{resolved_source_profile.name}'. Run bubble-mcp context detect.")
        transfer_context = load_context_with_overlay(
            source_context_path,
            profile=resolved_source_profile.name,
            app_id=resolved_source_profile.app_id,
        )
        inventory = inventory_source_object(
            context=transfer_context,
            profile=resolved_source_profile.name,
            app_version=resolved_source_profile.app_version or "test",
            source_type=_required_string_arg(args, "source_type", name),
            source_ref=_required_string_arg(args, "source_ref", name),
            source_context=str(args.get("source_context") or "") or None,
        )
        payload = inventory.to_dict()
        payload["ok"] = True
        if not bool(args.get("include_raw")):
            payload.pop("nodes", None)
            payload.pop("root", None)
        return payload
    if name == "bubble_transfer_plan":
        args = arguments or {}
        return create_transfer_plan(
            source_profile=_required_string_arg(args, "source_profile", name),
            target_profile=_required_string_arg(args, "target_profile", name),
            source_type=_required_string_arg(args, "source_type", name),
            source_ref=_required_string_arg(args, "source_ref", name),
            source_context=str(args.get("source_context") or "") or None,
            target_context=str(args.get("target_context") or "") or None,
            target_parent=str(args.get("target_parent") or "root"),
            target_name=str(args.get("target_name") or "") or None,
            conflict_policy=str(args.get("conflict_policy") or "fail"),
            asset_policy=str(args.get("asset_policy") or "reference_url"),
            dependency_policy=str(args.get("dependency_policy") or "map_or_create"),
            reuse_policy=str(args.get("reuse_policy") or "prefer_existing"),
            collection_policy=(
                "skip" if args.get("include_collections") is False else str(args.get("collection_policy") or "map_existing")
            ),
            api_connector_policy=(
                "skip"
                if args.get("include_api_connector") is False
                else str(args.get("api_connector_policy") or "structure_only")
            ),
            data_records_policy=str(args.get("data_records_policy") or "skip"),
        )
    if name == "bubble_transfer_preview":
        args = arguments or {}
        return preview_transfer_plan(
            _required_string_arg(args, "transfer_id", name),
            include_payloads=bool(args.get("include_payloads")),
        )
    if name == "bubble_transfer_execute":
        args = arguments or {}
        return execute_transfer_plan(
            _required_string_arg(args, "transfer_id", name),
            execute=bool(args.get("execute")),
            confirm=bool(args.get("confirm")),
            max_steps=int(args["max_steps"]) if args.get("max_steps") else None,
        )
    if name == "bubble_transfer_status":
        args = arguments or {}
        return {"ok": True, "transfer": load_transfer_plan(_required_string_arg(args, "transfer_id", name))}
    if name == "bubble_branch_list":
        args = arguments or {}
        return list_bubble_branches(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
        )
    if name == "bubble_branch_contributors":
        args = arguments or {}
        return list_branch_contributors(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
        )
    if name == "bubble_changelog_fetch":
        args = arguments or {}
        return fetch_changelog_entries(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
            start_index=int(args.get("start_index") or 0),
            num_fetch=int(args.get("num_fetch") or 50),
            filters=_changelog_filters_from_args(args),
        )
    if name == "bubble_branch_create":
        args = arguments or {}
        return create_bubble_branch(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            name=str(args.get("name") or ""),
            from_app_version=str(args.get("from_app_version") or "") or None,
            description=str(args.get("description") or ""),
            execute=bool(args.get("execute")),
            version_control_api_version=int(args.get("version_control_api_version") or 7),
        )
    if name == "bubble_branch_delete":
        args = arguments or {}
        return delete_bubble_branch(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or ""),
            soft_delete=bool(args.get("soft_delete", True)),
            execute=bool(args.get("execute")),
            confirm=bool(args.get("confirm")),
        )
    if name == "bubble_branch_merge_start":
        args = arguments or {}
        return start_bubble_branch_merge(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            ours_version_id=str(args.get("ours_version_id") or ""),
            theirs_version_id=str(args.get("theirs_version_id") or ""),
            savepoint_message=str(args.get("savepoint_message") or ""),
            session_id=str(args.get("session_id") or "") or None,
            execute=bool(args.get("execute")),
        )
    if name == "bubble_branch_merge_confirm":
        args = arguments or {}
        return confirm_bubble_branch_merge(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            merge_app_version=str(args.get("merge_app_version") or ""),
            conflicts_resolved=bool(args.get("conflicts_resolved")),
            session_id=str(args.get("session_id") or "") or None,
            execute=bool(args.get("execute")),
        )
    if name == "bubble_branch_merge_conflicts_describe":
        args = arguments or {}
        payload = args.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("bubble_branch_merge_conflicts_describe requires a payload object.")
        return describe_bubble_branch_merge_conflicts(payload=payload)
    if name == "bubble_performance_audit":
        args = arguments or {}
        return performance_audit(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
            start=str(args.get("start") or "") or None,
            end=str(args.get("end") or "") or None,
            granularity=str(args.get("granularity") or "day"),
            platform=str(args.get("platform") or "web_and_mobile"),
            include_logs=bool(args.get("include_logs", True)),
            include_raw=bool(args.get("include_raw")),
        )
    if name == "bubble_workload_usage_by_date":
        args = arguments or {}
        return fetch_workload_usage_by_date(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            start=_required_string_arg(args, "start", name),
            end=_required_string_arg(args, "end", name),
            granularity=str(args.get("granularity") or "day"),
            include_raw=bool(args.get("include_raw")),
        )
    if name == "bubble_workload_usage_breakdown":
        args = arguments or {}
        return fetch_workload_usage_breakdown(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            start=_required_string_arg(args, "start", name),
            end=_required_string_arg(args, "end", name),
            granularity=str(args.get("granularity") or "day"),
            tag1=str(args.get("tag1") or "") or None,
            tag2=str(args.get("tag2") or "") or None,
            platform=str(args.get("platform") or "web_and_mobile"),
            include_raw=bool(args.get("include_raw")),
            limit=int(args.get("limit") or 50),
        )
    if name == "bubble_logs_fetch":
        args = arguments or {}
        raw_messages = args.get("messages")
        messages = [str(item) for item in raw_messages] if isinstance(raw_messages, list) else None
        return fetch_jetstream_logs(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "") or None,
            start=_required_string_arg(args, "start", name),
            end=_required_string_arg(args, "end", name),
            messages=messages,
            ascending=bool(args.get("ascending", True)),
            is_state_ar=bool(args.get("is_state_ar", True)),
            include_raw=bool(args.get("include_raw")),
            limit=int(args.get("limit") or 100),
        )
    if name == "bubble_plan_usage_get":
        args = arguments or {}
        return fetch_plan_usage(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            include_raw=bool(args.get("include_raw")),
        )
    if name == "bubble_workflow_runs_get":
        args = arguments or {}
        return fetch_workflow_runs(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            platform=str(args.get("platform") or "web_and_mobile"),
            include_raw=bool(args.get("include_raw")),
        )
    if name == "bubble_storage_usage_get":
        args = arguments or {}
        return fetch_storage_usage(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            refresh=bool(args.get("refresh", True)),
            include_raw=bool(args.get("include_raw")),
        )
    if name == "bubble_time_series_read":
        args = arguments or {}
        resolution = args.get("resolution")
        resolution_value: float | None = None
        if resolution not in (None, ""):
            resolution_value = float(str(resolution))
        return read_time_series(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or "") or None,
            start=_required_string_arg(args, "start", name),
            end=_required_string_arg(args, "end", name),
            metric=_required_string_arg(args, "metric", name),
            resolution=resolution_value,
            use_observe=bool(args.get("use_observe", True)),
            include_raw=bool(args.get("include_raw")),
        )
    enabled_extension_tools = {str(tool.get("name") or "") for tool in enabled_extension_tool_schemas()}
    if name in enabled_extension_tools:
        return preview_extension_tool_call(name, arguments or {})
    if name in ARIA_BUBBLE_TOOL_NAMES:
        return call_legacy_catalog_tool(name, arguments or {})
    raise ValueError(f"Unknown Bubble MCP tool: {name}")


def _changelog_filters_from_args(args: dict[str, Any]) -> dict[str, Any]:
    raw_filters = args.get("filters")
    filters: dict[str, Any] = dict(raw_filters) if isinstance(raw_filters, dict) else {}
    mapping = {
        "start_timestamp": "start_timestamp",
        "end_timestamp": "end_timestamp",
        "change_type": "type",
        "root": "root",
        "change_identifier": "change_identifier",
        "change_path": "change_path",
        "user_id": "user_id",
    }
    for input_key, output_key in mapping.items():
        if input_key not in args:
            continue
        value = args[input_key]
        if value == "":
            continue
        if input_key == "user_id" and isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        filters[output_key] = value
    return filters


def call_legacy_catalog_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Handle a ported Aria Bubble MCP tool name.

    The standalone package exposes every Aria tool name. Families implemented by
    the local compiler can be compiled/executed directly. Any family can execute
    when the caller provides an exact Bubble ``write_payload``.
    """

    if name == "create_from_html":
        html_file = str(args.get("url") or args.get("html_file") or args.get("file") or "").strip()
        html = str(args.get("html") or "").strip()
        return create_from_html_runtime(
            profile=str(args.get("profile") or ""),
            context=str(args.get("context") or ""),
            parent=str(args.get("parent") or ""),
            html_file=html_file or None,
            html=html or None,
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            execute=bool(args.get("execute")),
            selector=str(args.get("selector") or "") or None,
            placement=str(args.get("placement") or "") or None,
            translate_to_existing_styles=bool(args.get("translate_to_existing_styles")),
            style_match_threshold=float(args.get("style_match_threshold") or 0.78),
            rendered_html=args.get("rendered_html") if isinstance(args.get("rendered_html"), bool) else None,
            strict_validate=bool(args.get("strict_validate")),
            validation_out_dir=str(args.get("validation_out_dir") or "") or None,
            refresh_context=bool(args.get("refresh_context")),
        )

    if name == "create_styles_from_html":
        html_file = str(args.get("url") or args.get("html_file") or args.get("file") or "").strip()
        html = str(args.get("html") or "").strip()
        return create_styles_from_html_runtime(
            profile=str(args.get("profile") or ""),
            selector=str(args.get("selector") or "") or None,
            style_name=str(args.get("style_name") or args.get("name") or "") or None,
            style_prefix=str(args.get("style_prefix") or "") or None,
            style_name_prefix=str(args.get("style_name_prefix") or "") or None,
            element_type=str(args.get("element_type") or ""),
            html=html or None,
            html_file=html_file or None,
            url=str(args.get("url") or "") or None,
            rendered_html=args.get("rendered_html") if isinstance(args.get("rendered_html"), bool) else None,
            execute=bool(args.get("execute")),
            include_states=bool(args.get("include_states", True)),
            states=args.get("states") if isinstance(args.get("states"), list) else None,
            extra_css=args.get("extra_css") if isinstance(args.get("extra_css"), list) else None,
            executor=lambda tool, tool_args: call_legacy_catalog_tool(tool, tool_args),
            verifier=lambda candidate: _verify_html_style_import(str(args.get("profile") or ""), candidate),
        )

    write_payload = args.get("write_payload") or args.get("payload")
    profile = str(args.get("profile") or "").strip()
    execute = bool(args.get("execute"))

    if isinstance(write_payload, dict):
        if not profile:
            return {
                "ok": True,
                "tool_name": name,
                "executed": False,
                "requires_profile": execute,
                "plan": {
                    "steps": [
                        {"id": "step_1", "tool_name": name, "args": {"write_payload": write_payload}}
                    ]
                },
                "validation": validate_plan(
                    {"steps": [{"id": "step_1", "tool_name": "bubble_editor_write", "args": {"write_payload": write_payload}}]}
                ),
            }
        session = load_session(profile)
        if session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        targeted_payload = _write_payload_for_target_version(write_payload, args)
        result = BubbleEditorClient().write(
            targeted_payload,
            session,
            dry_run=not execute,
            calculate_derived=name in {
                "delete_data_field",
                "create_privacy_rule",
                "delete_privacy_rule",
                "set_privacy_rule_name",
                "set_privacy_rule_condition",
                "set_privacy_rule_permission",
                "set_privacy_rule_field_visibility",
                "set_privacy_rule_auto_binding",
            }
            or bool(args.get("calculate_derived")),
        )
        if execute and result.get("ok"):
            record_mutation_overlay(
                profile=profile,
                app_id=str(result.get("request", {}).get("payload", {}).get("appname") or session.app_id),
                payload=result.get("request", {}).get("payload") or targeted_payload,
                source=name,
                response=result.get("response"),
            )
        return result

    runtime_result = dispatch_aria_runtime_tool(name, args)
    if runtime_result is not None:
        return runtime_result

    app_id = str(args.get("app_id") or args.get("appname") or "").strip()
    plan = {"steps": [{"id": "step_1", "tool_name": name, "args": dict(args)}]}
    if app_id:
        context = None
        context_file = str(args.get("context_file") or "").strip()
        if context_file:
            context = load_context_with_overlay(
                Path(context_file),
                profile=profile or None,
                app_id=app_id or None,
            )
        compiled_plan = compile_plan_to_write_payloads(
            plan,
            app_id=app_id,
            app_version=str(args.get("app_version") or "test"),
            context=context,
        )
        can_execute = any(
            isinstance(step, dict)
            and isinstance(step.get("args"), dict)
            and isinstance(step["args"].get("write_payload"), dict)
            for step in compiled_plan.get("steps", [])
        )
        if profile and can_execute:
            return execute_plan(
                compiled_plan,
                profile=profile,
                execute=execute,
                app_id=app_id,
                app_version=str(args.get("app_version") or "test"),
            )
        return {
            "ok": can_execute,
            "tool_name": name,
            "compiled": can_execute,
            "executed": False,
            "plan": compiled_plan,
            "validation": validate_plan(compiled_plan),
        }

    return {
        "ok": False,
        "tool_name": name,
        "compiled": False,
        "executed": False,
        "error": "This tool is exposed from the full Aria catalog, but standalone execution requires app_id for compiler support or write_payload for exact execution.",
        "plan": plan,
    }
