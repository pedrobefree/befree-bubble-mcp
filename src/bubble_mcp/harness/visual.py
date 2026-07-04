"""Structured visual snapshot comparison for Bubble MCP evals."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


JsonObject = dict[str, Any]


def load_visual_snapshot(path: Path) -> JsonObject:
    """Load a visual snapshot JSON object from disk."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Visual snapshot must be a JSON object.")
    return payload


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _norm_key(value: Any) -> str:
    return _norm_text(value).lower().replace(" ", "_")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def _bbox(node: JsonObject) -> JsonObject:
    for key in ("bbox", "box", "bounds", "rect"):
        value = node.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _style(node: JsonObject) -> JsonObject:
    value = node.get("style") or node.get("styles") or node.get("computed")
    return value if isinstance(value, dict) else {}


def _node_type(node: JsonObject) -> str:
    return _norm_key(node.get("role") or node.get("type") or node.get("tag") or node.get("element_type"))


def _node_label(node: JsonObject) -> str:
    for key in ("text", "content", "label", "name", "id"):
        value = _norm_text(node.get(key))
        if value:
            return value
    return _node_type(node)


def _walk_nodes(value: Any) -> list[JsonObject]:
    nodes: list[JsonObject] = []
    if isinstance(value, dict):
        if any(key in value for key in ("bbox", "box", "bounds", "rect", "text", "content", "label", "style", "styles")):
            nodes.append(value)
        for key in ("root", "nodes", "children", "elements"):
            child = value.get(key)
            if child is not None:
                nodes.extend(_walk_nodes(child))
    elif isinstance(value, list):
        for item in value:
            nodes.extend(_walk_nodes(item))
    return nodes


def _root(snapshot: JsonObject) -> JsonObject:
    root = snapshot.get("root")
    if isinstance(root, dict):
        return root
    nodes = snapshot.get("nodes")
    if isinstance(nodes, list) and nodes and isinstance(nodes[0], dict):
        return nodes[0]
    return snapshot


def _text_nodes(snapshot: JsonObject) -> list[JsonObject]:
    nodes = []
    for node in _walk_nodes(snapshot):
        node_type = _node_type(node)
        text = _norm_text(node.get("text") or node.get("content") or node.get("label"))
        if text and (node_type in {"text", "button", "link", "h1", "h2", "h3", "p", "span"} or not node_type):
            nodes.append(node)
    return nodes


def _image_nodes(snapshot: JsonObject) -> list[JsonObject]:
    return [node for node in _walk_nodes(snapshot) if _node_type(node) in {"image", "img", "picture"} or node.get("src")]


def _node_index(snapshot: JsonObject) -> dict[str, JsonObject]:
    indexed: dict[str, JsonObject] = {}
    for node in _walk_nodes(snapshot):
        keys = [
            _norm_key(node.get("id")),
            _norm_key(node.get("name")),
            _norm_key(node.get("data_id")),
            _norm_key(_node_label(node)),
        ]
        for key in keys:
            if key:
                indexed.setdefault(key, node)
    return indexed


def _within_tolerance(reference: float, actual: float, *, tolerance_px: float, tolerance_ratio: float) -> bool:
    tolerance = max(tolerance_px, abs(reference) * tolerance_ratio)
    return abs(reference - actual) <= tolerance


def _compare_numeric(
    issues: list[str],
    *,
    label: str,
    reference: Any,
    actual: Any,
    tolerance_px: float,
    tolerance_ratio: float,
) -> bool:
    ref_number = _number(reference)
    actual_number = _number(actual)
    if ref_number is None or actual_number is None:
        return False
    if not _within_tolerance(ref_number, actual_number, tolerance_px=tolerance_px, tolerance_ratio=tolerance_ratio):
        issues.append(f"{label} expected {ref_number:g}, got {actual_number:g}.")
        return True
    return True


def _normalized_gradient(value: Any) -> str:
    text = str(value or "").lower()
    if "gradient" not in text:
        return ""
    colors = re.findall(r"#[0-9a-f]{3,8}|rgba?\([^)]+\)", text)
    angle = re.search(r"(-?\d+(?:\.\d+)?)deg", text)
    direction = angle.group(1) if angle else ""
    return "|".join([direction, *colors])


def _style_value(style: JsonObject, *keys: str) -> Any:
    for key in keys:
        if key in style:
            return style[key]
    return None


def _record_issue(issues: list[str], issue_details: list[JsonObject], *, code: str, message: str) -> None:
    issues.append(message)
    issue_details.append({"code": code, "message": message})


def compare_visual_snapshots(
    reference: JsonObject,
    actual: JsonObject,
    *,
    tolerance_px: float = 4,
    tolerance_ratio: float = 0.08,
    require_text: bool = True,
    require_images: bool = False,
) -> dict[str, Any]:
    """Compare two structured visual snapshots and return a compact report."""

    issues: list[str] = []
    issue_details: list[JsonObject] = []
    warnings: list[str] = []
    comparisons = 0

    reference_root = _root(reference)
    actual_root = _root(actual)
    for field in ("x", "y", "width", "height"):
        ref_value = _bbox(reference_root).get(field)
        actual_value = _bbox(actual_root).get(field)
        if ref_value is None or actual_value is None:
            continue
        comparisons += 1
        before = len(issues)
        _compare_numeric(
            issues,
            label=f"root.{field}",
            reference=ref_value,
            actual=actual_value,
            tolerance_px=tolerance_px,
            tolerance_ratio=tolerance_ratio,
        )
        if len(issues) > before:
            issue_details.append({"code": "root_bbox_mismatch", "message": issues[-1]})

    reference_style = _style(reference_root)
    actual_style = _style(actual_root)
    for style_name, aliases in {
        "max_width": ("max_width", "maxWidth"),
        "font_family": ("font_family", "fontFamily"),
    }.items():
        ref_value = _style_value(reference_style, *aliases)
        actual_value = _style_value(actual_style, *aliases)
        if ref_value is None or actual_value is None:
            continue
        comparisons += 1
        if _number(ref_value) is not None and _number(actual_value) is not None:
            before = len(issues)
            _compare_numeric(
                issues,
                label=f"root.style.{style_name}",
                reference=ref_value,
                actual=actual_value,
                tolerance_px=tolerance_px,
                tolerance_ratio=tolerance_ratio,
            )
            if len(issues) > before:
                issue_details.append({"code": "root_style_numeric_mismatch", "message": issues[-1]})
        elif _norm_text(ref_value).lower() != _norm_text(actual_value).lower():
            _record_issue(
                issues,
                issue_details,
                code="root_style_value_mismatch",
                message=f"root.style.{style_name} expected {ref_value!r}, got {actual_value!r}.",
            )

    ref_gradient = _normalized_gradient(
        _style_value(reference_style, "background", "backgroundImage", "background_image")
    )
    actual_gradient = _normalized_gradient(
        _style_value(actual_style, "background", "backgroundImage", "background_image")
    )
    if ref_gradient and actual_gradient:
        comparisons += 1
        if ref_gradient != actual_gradient:
            _record_issue(
                issues,
                issue_details,
                code="gradient_mismatch",
                message="root.style.gradient does not match reference direction/color order.",
            )

    reference_texts = [_norm_text(node.get("text") or node.get("content") or node.get("label")) for node in _text_nodes(reference)]
    actual_texts = [_norm_text(node.get("text") or node.get("content") or node.get("label")) for node in _text_nodes(actual)]
    if require_text and reference_texts:
        for text in reference_texts:
            comparisons += 1
            if text not in actual_texts:
                _record_issue(
                    issues,
                    issue_details,
                    code="text_missing",
                    message=f"text missing from actual snapshot: {text!r}.",
                )

    actual_index = _node_index(actual)
    for ref_node in _walk_nodes(reference):
        ref_key = _norm_key(ref_node.get("id")) or _norm_key(ref_node.get("name")) or _norm_key(_node_label(ref_node))
        if not ref_key or ref_key not in actual_index:
            continue
        actual_node = actual_index[ref_key]
        for field in ("x", "y", "width", "height"):
            ref_value = _bbox(ref_node).get(field)
            actual_value = _bbox(actual_node).get(field)
            if ref_value is None or actual_value is None:
                continue
            comparisons += 1
            before = len(issues)
            _compare_numeric(
                issues,
                label=f"node.{ref_key}.{field}",
                reference=ref_value,
                actual=actual_value,
                tolerance_px=tolerance_px,
                tolerance_ratio=tolerance_ratio,
            )
            if len(issues) > before:
                issue_details.append({"code": "node_bbox_mismatch", "message": issues[-1]})
        ref_style = _style(ref_node)
        actual_node_style = _style(actual_node)
        for style_name, aliases in {
            "font_size": ("font_size", "fontSize"),
            "font_family": ("font_family", "fontFamily"),
            "font_weight": ("font_weight", "fontWeight"),
        }.items():
            ref_value = _style_value(ref_style, *aliases)
            actual_value = _style_value(actual_node_style, *aliases)
            if ref_value is None or actual_value is None:
                continue
            comparisons += 1
            if _number(ref_value) is not None and _number(actual_value) is not None:
                before = len(issues)
                _compare_numeric(
                    issues,
                    label=f"node.{ref_key}.style.{style_name}",
                    reference=ref_value,
                    actual=actual_value,
                    tolerance_px=tolerance_px,
                    tolerance_ratio=tolerance_ratio,
                )
                if len(issues) > before:
                    issue_details.append({"code": "node_style_numeric_mismatch", "message": issues[-1]})
            elif _norm_text(ref_value).lower() != _norm_text(actual_value).lower():
                _record_issue(
                    issues,
                    issue_details,
                    code="node_style_value_mismatch",
                    message=f"node.{ref_key}.style.{style_name} expected {ref_value!r}, got {actual_value!r}.",
                )

    reference_images = _image_nodes(reference)
    actual_images = _image_nodes(actual)
    if reference_images and (require_images or actual_images):
        comparisons += 1
        if len(actual_images) < len(reference_images):
            _record_issue(
                issues,
                issue_details,
                code="image_count_mismatch",
                message=f"expected at least {len(reference_images)} image nodes, got {len(actual_images)}.",
            )
        for index, ref_image in enumerate(reference_images):
            if index >= len(actual_images):
                break
            actual_image = actual_images[index]
            for field in ("width", "height"):
                ref_value = _bbox(ref_image).get(field) or ref_image.get(f"natural_{field}") or ref_image.get(f"natural{field.title()}")
                actual_value = _bbox(actual_image).get(field) or actual_image.get(f"natural_{field}") or actual_image.get(f"natural{field.title()}")
                if ref_value is None or actual_value is None:
                    continue
                comparisons += 1
                before = len(issues)
                _compare_numeric(
                    issues,
                    label=f"image[{index}].{field}",
                    reference=ref_value,
                    actual=actual_value,
                    tolerance_px=tolerance_px,
                    tolerance_ratio=tolerance_ratio,
                )
                if len(issues) > before:
                    issue_details.append({"code": "image_size_mismatch", "message": issues[-1]})
    elif reference_images and not require_images:
        warnings.append("reference snapshot has images but image comparison is not required.")

    issue_count = len(issues)
    score = 1.0 if comparisons == 0 else max(0.0, 1.0 - (issue_count / max(1, comparisons)))
    if not math.isfinite(score):
        score = 0.0
    return {
        "ok": issue_count == 0,
        "score": round(score, 4),
        "summary": {
            "comparisons": comparisons,
            "issue_count": issue_count,
            "warning_count": len(warnings),
            "reference_text_count": len(reference_texts),
            "actual_text_count": len(actual_texts),
            "reference_image_count": len(reference_images),
            "actual_image_count": len(actual_images),
        },
        "issues": issues,
        "issue_details": issue_details,
        "warnings": warnings,
    }


def compare_visual_snapshot_files(
    reference_path: Path,
    actual_path: Path,
    *,
    tolerance_px: float = 4,
    tolerance_ratio: float = 0.08,
    require_text: bool = True,
    require_images: bool = False,
) -> dict[str, Any]:
    """Compare two visual snapshot JSON files."""

    report = compare_visual_snapshots(
        load_visual_snapshot(reference_path),
        load_visual_snapshot(actual_path),
        tolerance_px=tolerance_px,
        tolerance_ratio=tolerance_ratio,
        require_text=require_text,
        require_images=require_images,
    )
    return {
        "ok": bool(report["ok"]),
        "reference": str(reference_path),
        "actual": str(actual_path),
        **report,
    }
