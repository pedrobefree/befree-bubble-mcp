"""Actionable visual audit and repair planning for Bubble MCP."""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from typing import Any

from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.harness.visual import (
    _bbox,
    _image_nodes,
    _node_label,
    _norm_key,
    _norm_text,
    _normalized_gradient,
    _number,
    _root,
    _style,
    _style_value,
    _text_nodes,
    compare_visual_snapshots,
    load_visual_snapshot,
)
from bubble_mcp.harness.visual_bubble import capture_bubble_visual_snapshot
from bubble_mcp.harness.visual_capture import capture_visual_snapshot


JsonObject = dict[str, Any]


def _first_present(value: JsonObject, *keys: str) -> Any:
    for key in keys:
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _target_ref(node: JsonObject, fallback: str = "") -> str:
    for key in ("bubble_id", "data_id", "element_id", "id", "name", "label"):
        value = _norm_text(node.get(key))
        if value:
            return value
    return fallback


def _target_args(
    *,
    node: JsonObject,
    context: str,
    parent: str,
    profile: str,
    app_id: str,
    app_version: str,
    fallback: str = "",
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "context": context or "index",
        "parent": parent or "root",
        "element_name": _target_ref(node, fallback),
    }
    if profile:
        args["profile"] = profile
    if app_id:
        args["app_id"] = app_id
    if app_version:
        args["app_version"] = app_version
    return args


def _issue(
    *,
    code: str,
    severity: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
    node: str = "",
    repair_step: dict[str, Any] | None = None,
    blocked_reason: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "node": node,
        "expected": expected,
        "actual": actual,
        "repairable": repair_step is not None and not blocked_reason,
    }
    if repair_step is not None:
        payload["repair_step"] = repair_step
    if blocked_reason:
        payload["blocked_reason"] = blocked_reason
    return payload


def _numeric_drift(
    expected: Any,
    actual: Any,
    *,
    tolerance_px: float,
    tolerance_ratio: float,
) -> tuple[bool, float | None, float | None]:
    expected_number = _number(expected)
    actual_number = _number(actual)
    if expected_number is None or actual_number is None:
        return False, expected_number, actual_number
    tolerance = max(tolerance_px, abs(expected_number) * tolerance_ratio)
    return abs(expected_number - actual_number) > tolerance, expected_number, actual_number


def _style_number(style: JsonObject, *keys: str) -> float | None:
    return _number(_style_value(style, *keys))


def _font_value(value: Any) -> str:
    return re.sub(r"['\"]", "", _norm_text(value)).lower()


def _pair_text_nodes(reference: JsonObject, actual: JsonObject) -> list[tuple[JsonObject, JsonObject]]:
    actual_by_text: dict[str, JsonObject] = {}
    actual_by_id: dict[str, JsonObject] = {}
    for node in _text_nodes(actual):
        actual_by_text.setdefault(_norm_key(node.get("text") or node.get("content") or node.get("label")), node)
        actual_by_id.setdefault(_norm_key(_target_ref(node)), node)

    pairs: list[tuple[JsonObject, JsonObject]] = []
    for ref_node in _text_nodes(reference):
        ref_key = _norm_key(ref_node.get("text") or ref_node.get("content") or ref_node.get("label"))
        ref_id = _norm_key(_target_ref(ref_node))
        actual_node = actual_by_text.get(ref_key) or actual_by_id.get(ref_id)
        if actual_node is not None:
            pairs.append((ref_node, actual_node))
    return pairs


def _paired_images(reference: JsonObject, actual: JsonObject) -> list[tuple[int, JsonObject, JsonObject]]:
    pairs: list[tuple[int, JsonObject, JsonObject]] = []
    for index, ref_image in enumerate(_image_nodes(reference)):
        actual_images = _image_nodes(actual)
        if index < len(actual_images):
            pairs.append((index, ref_image, actual_images[index]))
    return pairs


def _repair_plan(issues: list[dict[str, Any]]) -> dict[str, Any]:
    steps = []
    blocked = []
    seen_ids: set[str] = set()
    for item in issues:
        step = item.get("repair_step")
        if isinstance(step, dict) and item.get("repairable"):
            step_id = str(step.get("id") or "")
            if step_id and step_id in seen_ids:
                continue
            if step_id:
                seen_ids.add(step_id)
            steps.append(step)
        elif item.get("blocked_reason"):
            blocked.append(
                {
                    "code": item.get("code"),
                    "node": item.get("node"),
                    "reason": item.get("blocked_reason"),
                    "message": item.get("message"),
                }
            )

    return {
        "ok": bool(steps),
        "executable": bool(steps),
        "step_count": len(steps),
        "blocked_count": len(blocked),
        "plan": {
            "steps": steps,
            "metadata": {
                "source": "bubble_visual_audit",
                "blocked": blocked,
            },
        },
        "blocked": blocked,
    }


def _text_repair_step(
    *,
    ref_node: JsonObject,
    actual_node: JsonObject,
    args: dict[str, Any],
    issue_code: str,
    property_args: dict[str, Any],
) -> dict[str, Any] | None:
    target = _target_ref(actual_node)
    if not target:
        return None
    step_args = {**args, "element_name": target, **property_args}
    return {
        "id": f"repair_{issue_code}_{_norm_key(target)}",
        "tool_name": "update_text_element",
        "args": step_args,
        "reason": f"Align text node {_node_label(ref_node)!r} with the visual reference.",
    }


def _visual_repair_step(
    *,
    tool_name: str,
    node: JsonObject,
    args: dict[str, Any],
    issue_code: str,
    property_args: dict[str, Any],
    reason: str,
    fallback: str = "",
) -> dict[str, Any] | None:
    target = _target_ref(node, fallback)
    if not target:
        return None
    step_args = {**args, "element_name": target, **property_args}
    return {
        "id": f"repair_{issue_code}_{_norm_key(target)}",
        "tool_name": tool_name,
        "args": step_args,
        "reason": reason,
    }


def build_screenshot_llm_review(
    *,
    reference_screenshot: Path | None = None,
    actual_screenshot: Path | None = None,
    task: str = "",
    max_bytes: int = 4_000_000,
) -> dict[str, Any]:
    """Return a multimodal-ready payload for screenshot comparison by an LLM client."""

    screenshots: list[dict[str, Any]] = []
    for role, path in (("reference", reference_screenshot), ("actual", actual_screenshot)):
        if path is None:
            continue
        if not path.exists():
            return {
                "available": False,
                "requires_llm": True,
                "error": f"{role} screenshot does not exist: {path}",
            }
        size = path.stat().st_size
        if size > max_bytes:
            return {
                "available": False,
                "requires_llm": True,
                "error": f"{role} screenshot is too large ({size} bytes, limit {max_bytes}).",
            }
        mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
        screenshots.append(
            {
                "role": role,
                "path": str(path),
                "mime_type": mime_type,
                "size_bytes": size,
                "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        )

    if not screenshots:
        return {"available": False, "requires_llm": True, "images": []}

    return {
        "available": len(screenshots) >= 2,
        "requires_llm": True,
        "images": screenshots,
        "prompt": (
            "Compare the reference and actual UI screenshots. Return strict JSON with keys: "
            "ok, summary, issues, and repair_recommendations. Each issue must include code, severity, "
            "visual_region, expected, actual, and a concrete Bubble-oriented correction suggestion. "
            "Call out typography, spacing, max-width, image sizing, color/gradient direction, alignment, "
            "missing pseudo-elements/custom CSS needs, and responsive container problems."
        ),
        "task": task,
        "notes": [
            "This payload is intentionally LLM-ready. The MCP server does not mutate Bubble based on screenshot-only judgement.",
            "Use structured snapshots for executable repair plans; use screenshot review to catch visual issues snapshots cannot infer.",
        ],
    }


def audit_visual_snapshots(
    reference: JsonObject,
    actual: JsonObject,
    *,
    profile: str = "",
    context: str = "index",
    parent: str = "root",
    app_id: str = "",
    app_version: str = "test",
    execute: bool = False,
    tolerance_px: float = 4,
    tolerance_ratio: float = 0.08,
    require_text: bool = True,
    require_images: bool = False,
    reference_screenshot: Path | None = None,
    actual_screenshot: Path | None = None,
    screenshot_task: str = "",
) -> dict[str, Any]:
    """Compare snapshots, produce actionable issues, and optionally execute repairs."""

    report = compare_visual_snapshots(
        reference,
        actual,
        tolerance_px=tolerance_px,
        tolerance_ratio=tolerance_ratio,
        require_text=require_text,
        require_images=require_images,
    )
    issues: list[dict[str, Any]] = []
    common_args = {
        "context": context or "index",
        "parent": parent or "root",
    }
    if profile:
        common_args["profile"] = profile
    if app_id:
        common_args["app_id"] = app_id
    if app_version:
        common_args["app_version"] = app_version

    reference_root = _root(reference)
    actual_root = _root(actual)
    root_target_args = _target_args(
        node=actual_root,
        context=context,
        parent=parent,
        profile=profile,
        app_id=app_id,
        app_version=app_version,
        fallback=parent if parent and parent != "root" else "",
    )

    ref_root_style = _style(reference_root)
    actual_root_style = _style(actual_root)
    ref_gradient = _normalized_gradient(_style_value(ref_root_style, "background", "backgroundImage", "background_image"))
    actual_gradient = _normalized_gradient(_style_value(actual_root_style, "background", "backgroundImage", "background_image"))
    if ref_gradient and actual_gradient and ref_gradient != actual_gradient:
        step = _visual_repair_step(
            tool_name="update_group",
            node=actual_root,
            args=root_target_args,
            issue_code="gradient_direction_mismatch",
            property_args={"background_style": _style_value(ref_root_style, "background", "backgroundImage", "background_image")},
            reason="Align the container background gradient with the reference direction and color order.",
            fallback=parent if parent != "root" else "",
        )
        issues.append(
            _issue(
                code="gradient_direction_mismatch",
                severity="high",
                message="Root/container gradient direction or color order differs from the reference.",
                expected=_style_value(ref_root_style, "background", "backgroundImage", "background_image"),
                actual=_style_value(actual_root_style, "background", "backgroundImage", "background_image"),
                node=_target_ref(actual_root, parent),
                repair_step=step,
                blocked_reason="" if step else "No resolvable Bubble element target for the gradient container.",
            )
        )

    for label, ref_value, actual_value, prop in (
        (
            "root_max_width_drift",
            _style_number(ref_root_style, "max_width", "maxWidth"),
            _style_number(actual_root_style, "max_width", "maxWidth"),
            "max_width",
        ),
        (
            "root_width_drift",
            _bbox(reference_root).get("width"),
            _bbox(actual_root).get("width"),
            "width",
        ),
        (
            "root_height_drift",
            _bbox(reference_root).get("height"),
            _bbox(actual_root).get("height"),
            "height",
        ),
    ):
        drift, expected_number, actual_number = _numeric_drift(
            ref_value,
            actual_value,
            tolerance_px=tolerance_px,
            tolerance_ratio=tolerance_ratio,
        )
        if not drift or expected_number is None:
            continue
        step = _visual_repair_step(
            tool_name="update_layout",
            node=actual_root,
            args=root_target_args,
            issue_code=label,
            property_args={prop: expected_number},
            reason=f"Align root/container {prop} with the reference snapshot.",
            fallback=parent if parent != "root" else "",
        )
        issues.append(
            _issue(
                code=label,
                severity="medium",
                message=f"Root/container {prop} differs from the reference.",
                expected=expected_number,
                actual=actual_number,
                node=_target_ref(actual_root, parent),
                repair_step=step,
                blocked_reason="" if step else f"No resolvable Bubble element target for {prop}.",
            )
        )

    for gap_key in ("gap", "rowGap", "row_gap", "columnGap", "column_gap"):
        ref_gap = _style_number(ref_root_style, gap_key)
        actual_gap = _style_number(actual_root_style, gap_key)
        drift, expected_number, actual_number = _numeric_drift(
            ref_gap,
            actual_gap,
            tolerance_px=tolerance_px,
            tolerance_ratio=tolerance_ratio,
        )
        if not drift or expected_number is None:
            continue
        property_name = "row_gap" if "row" in gap_key.lower() or gap_key == "gap" else "column_gap"
        step = _visual_repair_step(
            tool_name="update_group",
            node=actual_root,
            args=root_target_args,
            issue_code=f"{property_name}_mismatch",
            property_args={property_name: expected_number},
            reason=f"Align container {property_name} with the reference snapshot.",
            fallback=parent if parent != "root" else "",
        )
        issues.append(
            _issue(
                code=f"{property_name}_mismatch",
                severity="medium",
                message=f"Container {property_name} differs from the reference.",
                expected=expected_number,
                actual=actual_number,
                node=_target_ref(actual_root, parent),
                repair_step=step,
                blocked_reason="" if step else f"No resolvable Bubble element target for {property_name}.",
            )
        )

    for ref_node, actual_node in _pair_text_nodes(reference, actual):
        ref_style = _style(ref_node)
        actual_style = _style(actual_node)
        ref_font = _first_present(ref_style, "fontFamily", "font_family")
        actual_font = _first_present(actual_style, "fontFamily", "font_family")
        if ref_font and actual_font and _font_value(ref_font) != _font_value(actual_font):
            step = _text_repair_step(
                ref_node=ref_node,
                actual_node=actual_node,
                args=common_args,
                issue_code="font_family_mismatch",
                property_args={"font_family": ref_font},
            )
            issues.append(
                _issue(
                    code="font_family_mismatch",
                    severity="medium",
                    message="Text font family differs from the reference.",
                    expected=ref_font,
                    actual=actual_font,
                    node=_target_ref(actual_node),
                    repair_step=step,
                    blocked_reason="" if step else "No resolvable Bubble text element target.",
                )
            )
        for code, keys, arg_name in (
            ("font_size_drift", ("fontSize", "font_size"), "font_size"),
            ("font_weight_mismatch", ("fontWeight", "font_weight"), "font_weight"),
        ):
            ref_value = _style_number(ref_style, *keys)
            actual_value = _style_number(actual_style, *keys)
            drift, expected_number, actual_number = _numeric_drift(
                ref_value,
                actual_value,
                tolerance_px=tolerance_px,
                tolerance_ratio=tolerance_ratio,
            )
            if not drift or expected_number is None:
                continue
            step = _text_repair_step(
                ref_node=ref_node,
                actual_node=actual_node,
                args=common_args,
                issue_code=code,
                property_args={arg_name: int(expected_number) if expected_number.is_integer() else expected_number},
            )
            issues.append(
                _issue(
                    code=code,
                    severity="medium",
                    message=f"Text {arg_name} differs from the reference.",
                    expected=expected_number,
                    actual=actual_number,
                    node=_target_ref(actual_node),
                    repair_step=step,
                    blocked_reason="" if step else "No resolvable Bubble text element target.",
                )
            )

    for index, ref_image, actual_image in _paired_images(reference, actual):
        for code, prop in (("image_width_drift", "width"), ("image_height_drift", "height")):
            ref_value = _bbox(ref_image).get(prop) or ref_image.get(f"natural_{prop}") or ref_image.get(f"natural{prop.title()}")
            actual_value = _bbox(actual_image).get(prop) or actual_image.get(f"natural_{prop}") or actual_image.get(f"natural{prop.title()}")
            drift, expected_number, actual_number = _numeric_drift(
                ref_value,
                actual_value,
                tolerance_px=tolerance_px,
                tolerance_ratio=tolerance_ratio,
            )
            if not drift or expected_number is None:
                continue
            property_args: dict[str, Any] = {prop: expected_number}
            if prop == "width":
                property_args["max_width"] = expected_number
                property_args["fixed_width"] = True
            if prop == "height":
                property_args["fixed_height"] = True
            step = _visual_repair_step(
                tool_name="update_image_element",
                node=actual_image,
                args=common_args,
                issue_code=code,
                property_args=property_args,
                reason=f"Align image {prop} with the reference snapshot.",
            )
            issues.append(
                _issue(
                    code=code,
                    severity="high" if prop == "width" else "medium",
                    message=f"Image[{index}] {prop} differs from the reference.",
                    expected=expected_number,
                    actual=actual_number,
                    node=_target_ref(actual_image, f"image[{index}]"),
                    repair_step=step,
                    blocked_reason="" if step else "No resolvable Bubble image element target.",
                )
            )

    repair_plan = _repair_plan(issues)
    screenshot_review = build_screenshot_llm_review(
        reference_screenshot=reference_screenshot,
        actual_screenshot=actual_screenshot,
        task=screenshot_task,
    )

    execution: dict[str, Any] | None = None
    if execute:
        if not profile:
            execution = {"ok": False, "executed": False, "reason": "profile_required"}
        elif not repair_plan["executable"]:
            execution = {"ok": False, "executed": False, "reason": "no_executable_repair_steps"}
        else:
            execution = execute_plan(
                repair_plan["plan"],
                profile=profile,
                execute=True,
                app_id=app_id or None,
                app_version=app_version or "test",
                compile_missing=True,
            )

    result: dict[str, Any] = {
        "ok": bool(report.get("ok")) and not issues,
        "visual_report": report,
        "summary": {
            "issue_count": len(issues),
            "repairable_count": sum(1 for issue in issues if issue.get("repairable")),
            "blocked_count": repair_plan["blocked_count"],
            "executable_repair_steps": repair_plan["step_count"],
            "screenshot_review_available": bool(screenshot_review.get("available")),
        },
        "issues": issues,
        "repair_plan": repair_plan,
        "llm_screenshot_review": screenshot_review,
    }
    if execution is not None:
        result["execution"] = execution
        result["ok"] = bool(execution.get("ok"))
    return result


def audit_visual_from_inputs(arguments: dict[str, Any]) -> dict[str, Any]:
    """Resolve snapshots/screenshots from MCP or CLI arguments and run audit."""

    reference_snapshot: JsonObject | None = None
    actual_snapshot: JsonObject | None = None

    reference_path = str(arguments.get("reference") or "").strip()
    actual_path = str(arguments.get("actual") or "").strip()
    raw_reference_snapshot = arguments.get("reference_snapshot") or arguments.get("visual_reference")
    raw_actual_snapshot = arguments.get("actual_snapshot") or arguments.get("visual_actual")
    if isinstance(raw_reference_snapshot, dict):
        reference_snapshot = raw_reference_snapshot
    if isinstance(raw_actual_snapshot, dict):
        actual_snapshot = raw_actual_snapshot
    if reference_path:
        reference_snapshot = load_visual_snapshot(Path(reference_path))
    if actual_path:
        actual_snapshot = load_visual_snapshot(Path(actual_path))

    if reference_snapshot is None and str(arguments.get("reference_source") or "").strip():
        reference_snapshot = capture_visual_snapshot(
            str(arguments.get("reference_source") or ""),
            selector=str(arguments.get("reference_selector") or arguments.get("selector") or ""),
            rendered_html=bool(arguments.get("rendered_html", True)),
            viewport_width=int(arguments.get("viewport_width") or 1365),
            viewport_height=int(arguments.get("viewport_height") or 768),
            wait_ms=int(arguments.get("wait_ms") or 0),
            selector_timeout_ms=int(arguments.get("selector_timeout_ms") or 5000),
            max_nodes=int(arguments.get("max_nodes") or 250),
            allow_raw_fallback=bool(arguments.get("allow_raw_fallback", True)),
        )

    if actual_snapshot is None and str(arguments.get("actual_source") or "").strip():
        actual_snapshot = capture_visual_snapshot(
            str(arguments.get("actual_source") or ""),
            selector=str(arguments.get("actual_selector") or arguments.get("selector") or ""),
            rendered_html=bool(arguments.get("rendered_html", True)),
            viewport_width=int(arguments.get("viewport_width") or 1365),
            viewport_height=int(arguments.get("viewport_height") or 768),
            wait_ms=int(arguments.get("wait_ms") or 0),
            selector_timeout_ms=int(arguments.get("selector_timeout_ms") or 5000),
            max_nodes=int(arguments.get("max_nodes") or 250),
            allow_raw_fallback=bool(arguments.get("allow_raw_fallback", True)),
        )

    actual_profile = str(arguments.get("actual_profile") or "").strip()
    if actual_snapshot is None and (
        actual_profile
        or str(arguments.get("actual_app_id") or "").strip()
        or str(arguments.get("actual_url") or "").strip()
    ):
        actual_snapshot = capture_bubble_visual_snapshot(
            profile=actual_profile or str(arguments.get("profile") or ""),
            app_id=str(arguments.get("actual_app_id") or arguments.get("app_id") or ""),
            app_version=str(arguments.get("actual_app_version") or arguments.get("app_version") or "test"),
            page=str(arguments.get("actual_page") or arguments.get("context") or "index"),
            selector=str(arguments.get("actual_selector") or arguments.get("selector") or ""),
            public_base_url=str(arguments.get("actual_public_base_url") or arguments.get("public_base_url") or ""),
            url=str(arguments.get("actual_url") or ""),
            query={},
            viewport_width=int(arguments.get("viewport_width") or 1365),
            viewport_height=int(arguments.get("viewport_height") or 768),
            wait_ms=int(arguments.get("wait_ms") or 1000),
            selector_timeout_ms=int(arguments.get("selector_timeout_ms") or 10000),
            max_nodes=int(arguments.get("max_nodes") or 250),
        )

    reference_screenshot = str(arguments.get("reference_screenshot") or "").strip()
    actual_screenshot = str(arguments.get("actual_screenshot") or "").strip()
    if reference_snapshot is None or actual_snapshot is None:
        if reference_screenshot or actual_screenshot:
            return {
                "ok": True,
                "summary": {
                    "issue_count": 0,
                    "repairable_count": 0,
                    "blocked_count": 0,
                    "executable_repair_steps": 0,
                    "screenshot_review_available": bool(reference_screenshot and actual_screenshot),
                },
                "issues": [],
                "repair_plan": _repair_plan([]),
                "llm_screenshot_review": build_screenshot_llm_review(
                    reference_screenshot=Path(reference_screenshot) if reference_screenshot else None,
                    actual_screenshot=Path(actual_screenshot) if actual_screenshot else None,
                    task=str(arguments.get("screenshot_task") or ""),
                ),
            }
        raise ValueError("bubble_visual_audit requires reference and actual snapshots, sources, or screenshots.")

    return audit_visual_snapshots(
        reference_snapshot,
        actual_snapshot,
        profile=str(arguments.get("profile") or ""),
        context=str(arguments.get("context") or "index"),
        parent=str(arguments.get("parent") or "root"),
        app_id=str(arguments.get("app_id") or arguments.get("actual_app_id") or ""),
        app_version=str(arguments.get("app_version") or arguments.get("actual_app_version") or "test"),
        execute=bool(arguments.get("execute")),
        tolerance_px=float(arguments.get("tolerance_px") or 4),
        tolerance_ratio=float(arguments.get("tolerance_ratio") or 0.08),
        require_text=bool(arguments.get("require_text", True)),
        require_images=bool(arguments.get("require_images")),
        reference_screenshot=Path(reference_screenshot) if reference_screenshot else None,
        actual_screenshot=Path(actual_screenshot) if actual_screenshot else None,
        screenshot_task=str(arguments.get("screenshot_task") or ""),
    )
