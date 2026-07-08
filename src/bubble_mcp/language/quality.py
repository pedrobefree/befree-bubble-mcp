"""Deterministic quality gates for framework-compiled Bubble MCP programs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

VISUAL_DEFAULTS: dict[str, dict[str, Any]] = {
    "create_button": {"fit_width": True, "fit_height": True},
    "create_text": {"fit_height": True},
    "create_icon": {"width": 20, "height": 20, "fixed_width": True, "fixed_height": True},
    "create_image": {"width": 120, "fixed_width": True, "min_height": 64},
    "create_shape": {"width": 120, "height": 120, "fixed_width": True, "fixed_height": True},
    "create_group": {"layout": "column", "min_height": 40, "fit_height": True, "min_width": 40},
    "create_input": {"height": 44, "fixed_height": True, "min_width": 0, "max_width": 240},
}


def _apply_visual_defaults(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    for key, value in VISUAL_DEFAULTS.get(tool, {}).items():
        normalized.setdefault(key, value)
    if normalized.get("fixed_width") is True and "width" in normalized:
        normalized.setdefault("min_width", normalized["width"])
        normalized.setdefault("max_width", normalized["width"])
    if normalized.get("fixed_height") is True and "height" in normalized:
        normalized.setdefault("min_height", normalized["height"])
        normalized.setdefault("max_height", normalized["height"])
    return normalized


def evaluate_compiled_calls(calls: list[dict[str, Any]], *, profile: str) -> dict[str, Any]:
    normalized_calls = deepcopy(calls)
    violations: list[dict[str, Any]] = []
    for index, call in enumerate(normalized_calls, start=1):
        tool = str(call.get("tool") or "")
        raw_args = call.get("arguments")
        args = raw_args if isinstance(raw_args, dict) else {}
        if args.get("profile") not in (None, "", profile):
            violations.append(
                {
                    "step": index,
                    "tool": tool,
                    "code": "compiled_call_profile_mismatch",
                    "message": "Compiled call profile must match the requested framework profile.",
                }
            )
        if args.get("execute") is True:
            violations.append(
                {
                    "step": index,
                    "tool": tool,
                    "code": "mutating_call_must_start_as_preview",
                    "message": "Mutating calls must compile with execute=false before explicit execution.",
                }
            )
        call["arguments"] = _apply_visual_defaults(tool, args)
    return {
        "ok": not violations,
        "violations": violations,
        "normalized_calls": normalized_calls,
        "policy_version": "framework_quality_v2",
    }
