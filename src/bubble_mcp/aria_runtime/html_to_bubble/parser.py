from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any, Dict, Optional


def _load_source_parser_class():
    runtime_root = Path(__file__).resolve().parents[2]
    source_parser_path = (runtime_root / "../bubble-editor/html_to_bubble/parser.py").resolve()
    spec = importlib.util.spec_from_file_location("_bubble_editor_source_parser", source_parser_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load source parser from {source_parser_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.HTMLParser


_SourceHTMLParser = _load_source_parser_class()


class HTMLParser(_SourceHTMLParser):
    """Runtime override for progressbar normalization in rendered HTML imports."""

    def parse_element(self, element: Any) -> Optional[Dict[str, Any]]:
        node = super().parse_element(element)
        self._hydrate_rendered_inline_geometry(node)
        self._normalize_progressbar_node(node)
        self._normalize_interactive_container_text(node)
        return node

    def _parse_snapshot_node(self, node: Any) -> Optional[Dict[str, Any]]:
        parsed = super()._parse_snapshot_node(node)
        self._normalize_progressbar_node(parsed)
        self._normalize_interactive_container_text(parsed)
        return parsed

    def _parse_px(self, value: Any) -> Optional[float]:
        raw = str(value or "").strip().lower()
        if not raw or raw in {"none", "auto", "normal", "initial", "unset"}:
            return None
        match = re.match(r"^(-?\d+(?:\.\d+)?)px$", raw)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                return None
        match = re.match(r"^(-?\d+(?:\.\d+)?)$", raw)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                return None
        return None

    def _hydrate_rendered_inline_geometry(self, node: Optional[Dict[str, Any]]) -> None:
        if not isinstance(node, dict):
            return

        styles = dict(node.get("styles", {}) or {})
        computed = dict(node.get("computed_styles", {}) or {})
        if styles:
            computed.update({str(k).strip().lower(): str(v).strip() for k, v in styles.items() if str(k).strip()})
            node["computed_styles"] = computed

        rect = dict(node.get("rect", {}) or {})
        width = self._parse_px(styles.get("width") or computed.get("width"))
        height = self._parse_px(styles.get("height") or computed.get("height"))
        left = self._parse_px(styles.get("left") or computed.get("left"))
        top = self._parse_px(styles.get("top") or computed.get("top"))

        if width is not None and rect.get("width") in {None, "", 0}:
            rect["width"] = width
        if height is not None and rect.get("height") in {None, "", 0}:
            rect["height"] = height
        if left is not None and rect.get("left") in {None, ""}:
            rect["left"] = left
            rect["x"] = left
        if top is not None and rect.get("top") in {None, ""}:
            rect["top"] = top
            rect["y"] = top
        if rect:
            node["rect"] = rect

        for child in list(node.get("children", []) or []):
            if isinstance(child, dict):
                self._hydrate_rendered_inline_geometry(child)

    def _normalize_interactive_container_text(self, node: Optional[Dict[str, Any]]) -> None:
        if not isinstance(node, dict):
            return
        tag = str(node.get("type", "")).strip().lower()
        if tag not in {"a", "button", "label"}:
            return
        children = [child for child in list(node.get("children", []) or []) if isinstance(child, dict)]
        if not children:
            return

        inline_like = {
            "span", "strong", "em", "small", "b", "i", "u", "a", "label", "code", "sup", "sub", "svg", "img"
        }

        def _has_media_descendant(item: Dict[str, Any]) -> bool:
            item_tag = str(item.get("type", "")).strip().lower()
            if item_tag in {"img", "svg", "video", "canvas", "picture", "iframe"}:
                return True
            return any(_has_media_descendant(child) for child in list(item.get("children", []) or []) if isinstance(child, dict))

        has_media = any(_has_media_descendant(child) for child in children)
        has_structural_children = any(str(child.get("type", "")).strip().lower() not in inline_like for child in children)
        if has_media and has_structural_children:
            node["text"] = ""
            node["text_segments"] = []

    def _normalize_progressbar_node(self, node: Optional[Dict[str, Any]]) -> None:
        if not isinstance(node, dict):
            return
        attrs = node.get("attributes", {}) or {}
        classes = attrs.get("class", []) or []
        class_list = [str(cls).strip().lower() for cls in classes if str(cls).strip()]
        if "cs_progressbar" not in class_list:
            return

        progress_value: Optional[str] = None
        for child in list(node.get("children", []) or []):
            if not isinstance(child, dict):
                continue
            child_attrs = child.get("attributes", {}) or {}
            raw_value = child_attrs.get("data-progress")
            if raw_value is None:
                continue
            candidate = str(raw_value).strip()
            if candidate:
                progress_value = candidate
                break

        if not progress_value:
            return

        normalized = f"{progress_value}%"
        for child in list(node.get("children", []) or []):
            if not isinstance(child, dict):
                continue
            child_attrs = child.get("attributes", {}) or {}
            child_classes = [
                str(cls).strip().lower()
                for cls in (child_attrs.get("class", []) or [])
                if str(cls).strip()
            ]
            if "cs_progressbar_head" not in child_classes:
                continue
            child["text"] = normalized
            child["text_segments"] = [
                {
                    "text": normalized,
                    "styles": dict(child.get("computed_styles", {}) or {}),
                    "raw_text": normalized,
                    "leading_space": False,
                    "trailing_space": False,
                }
            ]
            break
