from __future__ import annotations

import math
import re
import unicodedata
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin


class HTMLToBubbleMapper:
    """Map parsed HTML nodes to generic Bubble component nodes."""

    def __init__(self, base_url: str = "") -> None:
        self.base_url = (base_url or "").strip()

    ELEMENT_MAP = {
        "fragment": "map_container",
        "section": "map_container",
        "div": "map_container",
        "article": "map_container",
        "header": "map_container",
        "footer": "map_container",
        "main": "map_container",
        "aside": "map_container",
        "nav": "map_container",
        "ul": "map_container",
        "ol": "map_container",
        "li": "map_text",
        "h1": "map_heading",
        "h2": "map_heading",
        "h3": "map_heading",
        "h4": "map_heading",
        "h5": "map_heading",
        "h6": "map_heading",
        "p": "map_text",
        "span": "map_text",
        "small": "map_text",
        "strong": "map_text",
        "em": "map_text",
        "button": "map_button",
        "a": "map_link_or_button",
        "input": "map_input",
        "textarea": "map_input",
        "select": "map_input",
        "img": "map_image",
        "iframe": "map_container",
        "svg": "map_shape",
        "i": "map_shape",
    }

    SKIP_TAGS = {"script", "style", "noscript", "meta", "link", "head", "title", "template"}
    NOISE_MARKERS = {
        "privacy policy",
        "submitting this form",
        "unsubscribe",
        "cookie policy",
        "terms of service",
        "recaptcha",
    }

    HEADING_SIZE = {"h1": 32, "h2": 24, "h3": 20, "h4": 18, "h5": 16, "h6": 14}
    COLOR_TOKENS = {
        "bg-white": "#ffffff",
        "bg-black": "#000000",
        "bg-gray-100": "#f3f4f6",
        "bg-gray-200": "#e5e7eb",
        "bg-gray-800": "#1f2937",
        "bg-ruby": "#ff5b2e",
        "text-white": "#ffffff",
        "text-black": "#000000",
        "text-gray-900": "#111827",
        "text-orange-4": "#f97316",
    }
    GENERIC_NAME_TOKENS = {
        "div",
        "section",
        "container",
        "group",
        "wrapper",
        "content",
        "framer",
        "desktop",
        "mobile",
        "variant",
        "hidden",
        "root",
        "row",
        "col",
        "column",
        "block",
        "item",
        "inner",
        "outer",
        "text",
        "styles",
        "preset",
    }

    def map_tree(
        self,
        parsed_element: Dict[str, Any],
        depth: int = 0,
        parent_layout: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not parsed_element:
            return None
        node_type = str(parsed_element.get("type", "")).lower()
        if node_type in self.SKIP_TAGS:
            return None
        styles = self._merge_styles(parsed_element)
        if self._is_hidden_node(parsed_element, styles):
            return None

        if self._should_skip_background_layer(parsed_element, styles):
            return None

        if self._should_flatten_node(parsed_element, styles, parent_layout=parent_layout):
            flat_children = self._map_children(
                parsed_element.get("children", []) or [],
                depth,
                parent_layout=parent_layout,
                inherited_parent_rect=parsed_element.get("_parent_rect"),
                inherited_parent_styles=parsed_element.get("_parent_styles"),
                inherited_parent_relative_mode=parsed_element.get("_parent_relative_mode"),
            )
            if not flat_children:
                return None
            return {"bubble_type": "__fragment__", "properties": {}, "children": flat_children}

        if (
            parsed_element.get("media_url")
            and node_type not in {"img"}
            and not self._clean_text(parsed_element.get("text", ""))
            and not (parsed_element.get("children") or [])
            and (
                bool((parsed_element.get("attributes", {}) or {}).get("data-lottie-url"))
                or bool((parsed_element.get("attributes", {}) or {}).get("src"))
                or bool((parsed_element.get("attributes", {}) or {}).get("data-src"))
            )
        ):
            media_node = dict(parsed_element)
            media_node["type"] = "img"
            mapped_media = self.map_image(media_node, depth=depth)
            if mapped_media:
                self._apply_parent_positioning(parsed_element, mapped_media, parent_layout)
                return mapped_media

        mapper_name = self.ELEMENT_MAP.get(node_type, "map_container")
        display = self._clean_text(styles.get("display", "")).lower()
        if node_type in {"p", "span", "div"} and display in {"flex", "inline-flex"}:
            if self._has_descendant_tag(parsed_element, {"svg", "img", "i"}):
                mapper_name = "map_container"
        if node_type == "li":
            children = [c for c in (parsed_element.get("children", []) or []) if isinstance(c, dict)]
            if children or self._has_descendant_tag(parsed_element, {"a", "span", "strong", "em", "img", "svg", "i"}):
                mapper_name = "map_container"
        mapper_method = getattr(self, mapper_name)
        bubble_element = mapper_method(parsed_element, depth=depth)
        if not bubble_element:
            return None

        self._apply_parent_positioning(parsed_element, bubble_element, parent_layout)

        next_parent_layout = None
        next_parent_relative_mode = None
        if bubble_element.get("bubble_type") == "Group":
            next_parent_layout = str((bubble_element.get("properties", {}) or {}).get("layout", "column")).lower()
            next_parent_relative_mode = self._clean_text(
                (bubble_element.get("properties", {}) or {}).get("__relative_layout_mode", "")
            ).lower() or None

        # Only container nodes should recurse into children.
        if bubble_element.get("bubble_type") == "Group":
            parent_rect = parsed_element.get("rect")
            parent_styles = self._merge_styles(parsed_element)
            synthetic_padding = parsed_element.get("_synthetic_padding") or {}
            if isinstance(parent_styles, dict) and isinstance(synthetic_padding, dict) and synthetic_padding:
                parent_styles = {**parent_styles, **synthetic_padding}
            if isinstance(parent_rect, dict):
                for child in parsed_element.get("children", []) or []:
                    if not isinstance(child, dict):
                        continue
                    if child.get("_parent_rect") is None:
                        child["_parent_rect"] = parent_rect
                    if child.get("_parent_styles") is None:
                        child["_parent_styles"] = parent_styles
                    if next_parent_relative_mode and child.get("_parent_relative_mode") is None:
                        child["_parent_relative_mode"] = next_parent_relative_mode
            bubble_element["children"] = self._map_children(
                parsed_element.get("children", []) or [],
                depth,
                parent_layout=next_parent_layout,
                inherited_parent_rect=parent_rect if isinstance(parent_rect, dict) else None,
                inherited_parent_styles=parent_styles,
                inherited_parent_relative_mode=next_parent_relative_mode,
            )
            self._postprocess_group_children(bubble_element)
        else:
            bubble_element["children"] = []
        return bubble_element

    def _map_children(
        self,
        children: List[Dict[str, Any]],
        depth: int,
        parent_layout: Optional[str] = None,
        inherited_parent_rect: Optional[Dict[str, Any]] = None,
        inherited_parent_styles: Optional[Dict[str, Any]] = None,
        inherited_parent_relative_mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        eligible_children = [
            child
            for child in (children or [])
            if isinstance(child, dict) and not child.get("_skip_from_mapping")
        ]
        filtered_children = self._sort_children_by_visual_flow(eligible_children, parent_layout)
        parent_rect = inherited_parent_rect
        parent_styles = inherited_parent_styles
        parent_relative_mode = inherited_parent_relative_mode
        if isinstance(filtered_children, list) and filtered_children:
            # Attempt to infer parent rect from first child's stored parent rect
            # or upstream node assignment if present.
            for _c in filtered_children:
                if isinstance(_c, dict):
                    if parent_rect is None:
                        parent_rect = _c.get("_parent_rect")
                    if parent_styles is None:
                        parent_styles = _c.get("_parent_styles")
                    if parent_relative_mode is None:
                        parent_relative_mode = _c.get("_parent_relative_mode")
                    if parent_rect is not None:
                        break
        # Absolute full-cover background wrappers should not become regular flow
        # blocks inside row/column layouts; they must be treated as background.
        if str(parent_layout or "").lower() != "relative" and len(filtered_children) > 1:
            wrappers = [c for c in filtered_children if self._is_full_cover_background_wrapper(c)]
            if wrappers and len(wrappers) < len(filtered_children):
                filtered_children = [c for c in filtered_children if not self._is_full_cover_background_wrapper(c)]

        mapped_children: List[Dict[str, Any]] = []
        for child in filtered_children:
            if isinstance(child, dict) and parent_rect is not None and child.get("_parent_rect") is None:
                child["_parent_rect"] = parent_rect
            if isinstance(child, dict) and parent_styles is not None and child.get("_parent_styles") is None:
                child["_parent_styles"] = parent_styles
            if isinstance(child, dict) and parent_relative_mode is not None and child.get("_parent_relative_mode") is None:
                child["_parent_relative_mode"] = parent_relative_mode
            mapped = self.map_tree(child, depth=depth + 1, parent_layout=parent_layout)
            if not mapped:
                continue
            if mapped.get("bubble_type") == "__fragment__":
                mapped_children.extend(mapped.get("children", []) or [])
            else:
                mapped_children.append(mapped)
        return mapped_children

    def _postprocess_group_children(self, group_node: Dict[str, Any], parent_width: Optional[int] = None) -> None:
        children = group_node.get("children", []) or []
        if not children:
            return
        props = group_node.get("properties", {}) or {}
        for css_key in ("min_width_css", "max_width_css", "min_height_css", "max_height_css"):
            if self._clean_text(props.get(css_key, "")).lower() == "0px":
                props.pop(css_key, None)
        current_width = self._to_int(props.get("width"), None)

        # Recurse first.
        for child in children:
            if isinstance(child, dict) and child.get("bubble_type") == "Group":
                self._postprocess_group_children(child, parent_width=current_width)
                child_props = child.get("properties", {}) or {}
                for css_key in ("min_width_css", "max_width_css", "min_height_css", "max_height_css"):
                    if self._clean_text(child_props.get(css_key, "")).lower() == "0px":
                        child_props.pop(css_key, None)
                child["properties"] = child_props

        # If a non-visual wrapper exists only to position a single small icon/image,
        # the child should inherit the wrapper's horizontal alignment instead of
        # defaulting to centered media placement.
        if (
            not self._has_visual_shell_props(props)
            and self._clean_text(props.get("horiz_alignment", "")).lower() in {"flex-start", "flex-end", "center"}
        ):
            image_children = [child for child in children if isinstance(child, dict) and child.get("bubble_type") == "Image"]
            if len(image_children) == 1 and len(children) == 1:
                image_props = image_children[0].get("properties", {}) or {}
                image_width = self._to_int(image_props.get("width"), None)
                if image_width is None:
                    image_width = self._parse_dimension(image_props.get("min_width_css"))
                wrapper_width = self._to_int(props.get("width"), None)
                if image_width is not None and wrapper_width is not None and image_width <= 96 and wrapper_width >= image_width + 24:
                    image_props["horiz_alignment"] = self._clean_text(props.get("horiz_alignment", "")).lower()
                    image_children[0]["properties"] = image_props

        if self._restructure_mosaic_group_to_row_columns(group_node):
            children = group_node.get("children", []) or []
            props = group_node.get("properties", {}) or {}
            current_width = self._to_int(props.get("width"), None)

        layout = str(props.get("layout", "")).lower()
        if layout == "row":
            self._normalize_blog_card_row(group_node)
            props = group_node.get("properties", {}) or {}
            children = group_node.get("children", []) or []
            self._normalize_negative_row_gutters(group_node)
            props = group_node.get("properties", {}) or {}
            children = group_node.get("children", []) or []
            current_width = self._to_int(props.get("width"), None)
            for child in children:
                if not isinstance(child, dict) or child.get("bubble_type") != "Group":
                    continue
                ch_props = child.get("properties", {}) or {}
                child_width = self._to_int(ch_props.get("width"), None)
                if (
                    current_width is not None
                    and child_width is not None
                    and current_width > 0
                    and float(child_width) / float(current_width) >= 0.25
                ):
                    ch_props["fit_width"] = False
                    ch_props["width_unset"] = False
                if self._clean_text(ch_props.get("vert_alignment", "")).lower() != "stretch":
                    child["properties"] = ch_props
                    continue
                child_height = self._to_int(ch_props.get("height"), None)
                nested = [node for node in (child.get("children", []) or []) if isinstance(node, dict)]
                if len(nested) != 1 or nested[0].get("bubble_type") != "Group":
                    child["properties"] = ch_props
                    continue
                inner_props = nested[0].get("properties", {}) or {}
                inner_height = self._to_int(inner_props.get("height"), None)
                if child_height is not None and inner_height is not None and abs(child_height - inner_height) <= 2:
                    inner_props.pop("min_height_css", None)
                    nested[0]["properties"] = inner_props
                child["properties"] = ch_props

        # Inline form adjustments: remove explicit input margins and ensure a sensible gap.
        if props.get("__inline_form"):
            if not props.get("gap"):
                props["gap"] = 16
                props["use_gap"] = True
            for child in children:
                if not isinstance(child, dict):
                    continue
                if child.get("bubble_type") == "Input":
                    ch_props = child.get("properties", {}) or {}
                    if (ch_props.get("margin_right") or 0) >= 40:
                        ch_props["margin_right"] = 0
                    if (ch_props.get("margin_left") or 0) >= 40:
                        ch_props["margin_left"] = 0
                    # Stretch inputs to match row height when used alongside buttons.
                    ch_props["vert_alignment"] = "stretch"
                    child["properties"] = ch_props
            group_node["properties"] = props

        # Inline-block icon rows (e.g., social icons): ensure row layout and gap.
        if layout != "row" and self._should_inline_block_row(group_node):
            props["layout"] = "row"
            props["container_layout"] = "row"
            if not props.get("gap"):
                inferred = self._infer_inline_block_gap_from_children(children)
                props["gap"] = inferred or 6
                props["use_gap"] = True
            group_node["properties"] = props

        # Align-items-end rows: ensure children are bottom-aligned in Bubble.
        if (props.get("__align_items_end") or props.get("container_vert_alignment") == "flex-end") and props.get("layout") == "row":
            for child in children:
                if not isinstance(child, dict):
                    continue
                ch_props = child.get("properties", {}) or {}
                if ch_props.get("vert_alignment") in {None, "top", "flex-start"}:
                    ch_props["vert_alignment"] = "flex-end"
                child["properties"] = ch_props

        # Equal-height row siblings should stretch vertically instead of relying
        # on copied min-height constraints from the browser snapshot.
        if props.get("layout") == "row":
            row_children = [child for child in children if isinstance(child, dict)]
            row_heights: List[int] = []
            for child in row_children:
                ch_props = child.get("properties", {}) or {}
                raw_h = (
                    self._to_int(ch_props.get("height"), None)
                    or self._to_int(ch_props.get("%h"), None)
                    or self._to_int(ch_props.get("__source_height"), None)
                )
                if raw_h is None or raw_h <= 0:
                    row_heights = []
                    break
                row_heights.append(raw_h)
            if len(row_heights) >= 2 and max(row_heights) - min(row_heights) <= 2:
                for child in row_children:
                    ch_props = child.get("properties", {}) or {}
                    ch_props["vert_alignment"] = "stretch"
                    min_height_css = self._clean_text(ch_props.get("min_height_css", ""))
                    source_h = (
                        self._to_int(ch_props.get("height"), None)
                        or self._to_int(ch_props.get("%h"), None)
                        or self._to_int(ch_props.get("__source_height"), None)
                    )
                    if source_h is not None and min_height_css == f"{int(source_h)}px":
                        ch_props.pop("min_height_css", None)
                    child["properties"] = ch_props

        # Flatten trivial image wrappers generated by absolute Framer shells.
        flattened: List[Dict[str, Any]] = []
        for child in children:
            if self._can_flatten_image_wrapper(child):
                inner = (child.get("children", []) or [None])[0]
                if isinstance(inner, dict):
                    wrapper_props = child.get("properties", {}) or {}
                    inner_props = inner.get("properties", {}) or {}
                    for k in (
                        "margin_left",
                        "margin_right",
                        "margin_top",
                        "margin_bottom",
                        "nonant_alignment",
                        "horiz_alignment",
                        "vert_alignment",
                        "container_horiz_alignment",
                        "container_vert_alignment",
                        "zindex",
                    ):
                        if wrapper_props.get(k) is not None and inner_props.get(k) is None:
                            inner_props[k] = wrapper_props.get(k)
                    inner["properties"] = inner_props
                    flattened.append(inner)
                    continue
            flattened.append(child)
        group_node["children"] = flattened

        # If a wrapper preserves rounded corners around a single image, mirror
        # the radius on the image itself so clipping remains visually faithful.
        for child in group_node["children"]:
            if not isinstance(child, dict) or child.get("bubble_type") != "Group":
                continue
            wrapper_props = child.get("properties", {}) or {}
            wrapper_radius = self._to_int(wrapper_props.get("border_radius"), 0) or 0
            if wrapper_radius <= 0:
                continue
            nested_children = child.get("children", []) or []
            if len(nested_children) != 1:
                continue
            inner = nested_children[0]
            if not isinstance(inner, dict) or inner.get("bubble_type") != "Image":
                continue
            inner_props = inner.get("properties", {}) or {}
            image_url = self._clean_text(inner_props.get("image_url", "")).lower()
            if image_url.endswith(".svg") or image_url.startswith("data:image/svg"):
                continue
            inner_radius = self._to_int(inner_props.get("border_radius"), 0) or 0
            if inner_radius <= 0:
                inner_props["border_radius"] = wrapper_radius
                inner["properties"] = inner_props

        self._propagate_parent_top_corners_to_full_width_header(group_node)
        self._inherit_single_child_visual_shell(group_node)
        self._relax_single_media_wrapper_widths(group_node)
        self._split_wrapped_row_into_rows(group_node)
        self._compress_non_visual_spacers_into_gap(group_node)
        self._tune_avatar_strip(group_node)
        self._tune_compact_badges(group_node)
        self._tune_compact_badge_wrappers(group_node)
        self._tune_avatar_media_groups(group_node)
        self._tune_absolute_center_offsets(group_node)
        self._tune_absolute_media_wrappers(group_node)
        self._tune_relative_overlay_layers(group_node)
        self._tune_relative_flow_media_layers(group_node)
        self._tune_relative_primary_flow_child(group_node)
        self._tune_inline_text_wrappers(group_node)
        self._tune_visual_fixed_height_groups(group_node)
        self._tune_content_sized_column_wrappers(group_node, parent_width=parent_width)
        self._normalize_relative_overlay_testimonial_section(group_node)
        self._inherit_single_child_visual_shell(group_node)

    def _tune_content_sized_column_wrappers(self, group_node: Dict[str, Any], parent_width: Optional[int] = None) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        layout = self._clean_text(props.get("layout", "")).lower()
        if layout not in {"row", "column"}:
            return
        width = self._to_int(props.get("width"), None)
        if width is None or width <= 0 or width > 360:
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if not children:
            return
        child_widths: List[int] = []
        for child in children:
            child_props = child.get("properties", {}) or {}
            child_width = self._to_int(child_props.get("width"), None)
            if child_width is None:
                child_width = self._to_int(child_props.get("%w"), None)
            if child_width is not None and child_width > 0:
                child_widths.append(child_width)
        if not child_widths:
            return
        gap = self._to_int(props.get("gap"), None)
        if gap is None:
            gap = self._to_int(props.get("column_gap"), None) if layout == "row" else self._to_int(props.get("row_gap"), None)
        gap = gap or 0
        padding_left = self._to_int(props.get("padding_left"), 0) or 0
        padding_right = self._to_int(props.get("padding_right"), 0) or 0
        content_width = max(child_widths) if layout == "column" else (sum(child_widths) + max(len(child_widths) - 1, 0) * gap)
        expected_width = content_width + padding_left + padding_right
        if abs(expected_width - width) <= 2:
            if parent_width is not None and (
                abs(width - parent_width) <= 2
                or float(width) / float(max(parent_width, 1)) >= 0.25
            ):
                props["fit_width"] = False
            else:
                props["fit_width"] = True
            props["width_unset"] = False
            group_node["properties"] = props

    def _cluster_mosaic_axis(self, values: List[int], threshold: int) -> List[int]:
        ordered = sorted(values)
        if not ordered:
            return []
        anchors = [ordered[0]]
        for value in ordered[1:]:
            if abs(value - anchors[-1]) > threshold:
                anchors.append(value)
        return anchors

    def _restructure_mosaic_group_to_row_columns(self, group_node: Dict[str, Any]) -> bool:
        props = group_node.get("properties", {}) or {}
        if self._clean_text(props.get("__relative_layout_mode", "")).lower() != "mosaic":
            return False
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) < 3:
            return False

        positioned = []
        for child in children:
            child_props = child.get("properties", {}) or {}
            x = self._to_int(child_props.get("__mosaic_x"), None)
            y = self._to_int(child_props.get("__mosaic_y"), None)
            w = self._to_int(child_props.get("__mosaic_width"), None) or self._to_int(child_props.get("width"), None)
            h = self._to_int(child_props.get("__mosaic_height"), None) or self._to_int(child_props.get("height"), None)
            if x is None or y is None or w is None or h is None:
                return False
            positioned.append((child, child_props, x, y, w, h))

        avg_w = sum(item[4] for item in positioned) / len(positioned)
        x_threshold = max(16, int(round(avg_w * 0.25)))
        anchors = self._cluster_mosaic_axis([item[2] for item in positioned], x_threshold)
        if len(anchors) < 2:
            return False

        columns: List[List[tuple]] = [[] for _ in anchors]
        for item in positioned:
            x = item[2]
            idx = min(range(len(anchors)), key=lambda i: abs(x - anchors[i]))
            columns[idx].append(item)

        parent_height = self._to_int(props.get("height"), None) or max((item[3] + item[5] for item in positioned), default=0)
        new_children: List[Dict[str, Any]] = []
        created_wrapper = False

        for idx, column_items in enumerate(columns, start=1):
            if not column_items:
                continue
            column_items.sort(key=lambda item: item[3])
            column_width = max((item[4] for item in column_items), default=0)

            if len(column_items) == 1:
                child, child_props, _x, _y, _w, _h = column_items[0]
                child_props["margin_left"] = 0
                child_props["margin_top"] = 0
                child_props["margin_right"] = 0
                child_props["margin_bottom"] = 0
                child_props.pop("nonant_alignment", None)
                child_props.pop("align_to_parent_pos", None)
                child_props["fit_width"] = False
                child_props["width_unset"] = True
                child_props.pop("width", None)
                child_props.pop("min_width_css", None)
                child_props.pop("max_width_css", None)
                child_props.pop("fixed_width", None)
                child_props.pop("single_width", None)
                child_props["fit_height"] = True
                child_props.pop("min_height_css", None)
                child_props.pop("max_height_css", None)
                child_props["vert_alignment"] = "stretch"
                for meta_key in ("__mosaic_x", "__mosaic_y", "__mosaic_width", "__mosaic_height"):
                    child_props.pop(meta_key, None)
                child["properties"] = child_props
                new_children.append(child)
                continue

            wrapper_name = f"column_{idx}"
            first_top = column_items[0][3]
            last_bottom = max((item[3] + item[5] for item in column_items), default=0)
            top_gap = first_top
            bottom_gap = max(parent_height - last_bottom, 0)
            space_between = top_gap <= 4 and bottom_gap <= 6

            wrapper_props: Dict[str, Any] = {
                "name": wrapper_name,
                "layout": "column",
                "gap": 0,
                "width": None,
                "height": None,
                "fit_width": False,
                "width_unset": True,
                "fit_height": True,
                "container_vert_alignment": "space-between" if space_between else "stretch",
                "vert_alignment": "stretch",
                "horiz_alignment": "flex-start",
                "margin_left": 0,
                "margin_right": 0,
                "margin_top": 0,
                "margin_bottom": 0,
            }

            wrapper_children: List[Dict[str, Any]] = []
            for child, child_props, _x, _y, _w, _h in column_items:
                child_props["margin_left"] = 0
                child_props["margin_top"] = 0
                child_props["margin_right"] = 0
                child_props["margin_bottom"] = 0
                child_props.pop("nonant_alignment", None)
                child_props.pop("align_to_parent_pos", None)
                child_props["fit_height"] = True
                child_props.pop("min_height_css", None)
                child_props.pop("max_height_css", None)
                child_props["vert_alignment"] = "stretch"
                for meta_key in ("__mosaic_x", "__mosaic_y", "__mosaic_width", "__mosaic_height"):
                    child_props.pop(meta_key, None)
                child["properties"] = child_props
                wrapper_children.append(child)

            new_children.append({
                "bubble_type": "Group",
                "properties": wrapper_props,
                "children": wrapper_children,
            })
            created_wrapper = True

        if not created_wrapper:
            return False

        props["layout"] = "row"
        props["gap"] = 0
        props["fit_height"] = True
        props["fit_width"] = False
        props["width_unset"] = False
        props["container_vert_alignment"] = "stretch"
        props.pop("__relative_layout_mode", None)
        group_node["properties"] = props
        group_node["children"] = new_children
        return True

    def _normalize_relative_overlay_testimonial_section(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if self._clean_text(props.get("layout", "")).lower() != "row":
            return

        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) != 2:
            return

        content_wrapper, overlay_image = children
        if content_wrapper.get("bubble_type") != "Group" or overlay_image.get("bubble_type") != "Image":
            return

        content_props = content_wrapper.get("properties", {}) or {}
        if self._clean_text(content_props.get("layout", "")).lower() != "column":
            return

        content_children = [child for child in (content_wrapper.get("children", []) or []) if isinstance(child, dict)]
        if len(content_children) != 3:
            return

        leading_spacer, center_block, trailing_spacer = content_children
        if not self._is_non_visual_flow_spacer(leading_spacer, "column"):
            return
        if not self._is_non_visual_flow_spacer(trailing_spacer, "column"):
            return
        if center_block.get("bubble_type") != "Group":
            return

        pad_top = self._spacer_size_from_node(leading_spacer, "column")
        pad_bottom = self._spacer_size_from_node(trailing_spacer, "column")
        if pad_top < 40 or pad_bottom < 40:
            return

        center_props = center_block.get("properties", {}) or {}
        center_children = [child for child in (center_block.get("children", []) or []) if isinstance(child, dict)]
        if len(center_children) == 1 and center_children[0].get("bubble_type") == "Group":
            inner_row = center_children[0]
            inner_row_props = inner_row.get("properties", {}) or {}
            if self._clean_text(inner_row_props.get("layout", "")).lower() == "row":
                row_gap = max(
                    self._to_int(inner_row_props.get("gap"), 0) or 0,
                    abs(self._to_int(inner_row_props.get("margin_left"), 0) or 0) * 2,
                    abs(self._to_int(inner_row_props.get("margin_right"), 0) or 0) * 2,
                    40,
                )
                center_props["layout"] = "row"
                center_props["gap"] = row_gap
                center_props["column_gap"] = row_gap
                center_props["use_gap"] = True
                center_props["container_vert_alignment"] = "flex-start"
                center_props["container_horiz_alignment"] = "flex-start"
                center_props["margin_left"] = 0
                center_props["margin_right"] = 0
                center_props["margin_top"] = 0
                center_props["margin_bottom"] = 0
                center_props["padding_left"] = 0
                center_props["padding_right"] = 0
                center_block["properties"] = center_props
                center_block["children"] = [child for child in (inner_row.get("children", []) or []) if isinstance(child, dict)]

        group_node["properties"]["layout"] = "relative"
        group_node["properties"]["padding_top"] = pad_top
        group_node["properties"]["padding_bottom"] = pad_bottom
        group_node["properties"]["fit_height"] = True
        group_node["properties"]["container_horiz_alignment"] = "center"
        group_node["properties"]["container_vert_alignment"] = "center"

        content_wrapper["children"] = [center_block]
        content_props = content_wrapper.get("properties", {}) or {}
        content_props["nonant_alignment"] = "bb"
        content_props["fit_width"] = False
        content_props["fit_height"] = True
        content_props["width_unset"] = True
        content_props.pop("width", None)
        content_props.pop("min_width_css", None)
        content_props.pop("max_width_css", None)
        content_props.pop("fixed_width", None)
        content_props.pop("single_width", None)
        content_props["margin_left"] = 0
        content_props["margin_right"] = 0
        content_props["margin_top"] = 0
        content_props["margin_bottom"] = 0
        content_props["container_vert_alignment"] = "flex-start"
        content_props["vert_alignment"] = "stretch"
        content_wrapper["properties"] = content_props

        overlay_props = overlay_image.get("properties", {}) or {}
        overlay_props["nonant_alignment"] = "cc"
        overlay_props["margin_right"] = 85
        overlay_props["margin_bottom"] = -50
        overlay_props["margin_left"] = 0
        overlay_props["margin_top"] = 0
        overlay_image["properties"] = overlay_props

        normalized_children = [content_wrapper, overlay_image]

        def _left_align_svg_descendants(node: Dict[str, Any]) -> None:
            if not isinstance(node, dict):
                return
            node_props = node.get("properties", {}) or {}
            image_url = self._clean_text(node_props.get("image_url", "")).lower()
            image_name = self._clean_text(node_props.get("name", "")).lower()
            if node.get("bubble_type") == "Image" and (
                image_url.endswith(".svg")
                or image_url.startswith("data:image/svg")
                or "svg" in image_name
                or "quote" in image_name
            ):
                node_props["horiz_alignment"] = "flex-start"
                node["properties"] = node_props
            for nested_child in [child for child in (node.get("children", []) or []) if isinstance(child, dict)]:
                _left_align_svg_descendants(nested_child)

        center_children = [child for child in (center_block.get("children", []) or []) if isinstance(child, dict)]
        for column in center_children:
            if column.get("bubble_type") != "Group":
                continue
            column_props = column.get("properties", {}) or {}
            if self._clean_text(column_props.get("layout", "")).lower() != "column":
                continue
            column_props["fit_width"] = False
            column_props["width_unset"] = True
            column_props.pop("width", None)
            column_props.pop("min_width_css", None)
            column_props.pop("max_width_css", None)
            column_props.pop("fixed_width", None)
            column_props.pop("single_width", None)
            column_props["gap"] = 40
            column_props["use_gap"] = True
            column_props["container_vert_alignment"] = "flex-start"
            column_props["vert_alignment"] = "flex-start"
            column["properties"] = column_props

            filtered_col_children: List[Dict[str, Any]] = []
            for card in column.get("children", []) or []:
                if not isinstance(card, dict):
                    continue
                card_props = card.get("properties", {}) or {}
                card_height = self._to_int(card_props.get("height"), 0) or 0
                if card_height == 0 and not card.get("children"):
                    continue
                if self._clean_text(card_props.get("name", "")).lower() == "grid sizer":
                    continue
                if "testimonial style radius overflow" in self._clean_text(card_props.get("name", "")).lower():
                    card_props["fit_height"] = True
                    card_props.pop("min_height_css", None)
                    card_props.pop("height", None)
                    card["properties"] = card_props
                    _left_align_svg_descendants(card)
                    for nested in [child for child in (card.get("children", []) or []) if isinstance(child, dict)]:
                        nested_props = nested.get("properties", {}) or {}
                        nested_name = self._clean_text(nested_props.get("name", "")).lower()
                        if nested.get("bubble_type") == "Group" and "testmonial icon" in nested_name:
                            nested_props["horiz_alignment"] = "flex-start"
                            nested_props["fit_width"] = True
                            nested_props["width_unset"] = True
                            nested_props.pop("width", None)
                            nested_props.pop("min_width_css", None)
                            nested_props.pop("max_width_css", None)
                            nested_props.pop("fixed_width", None)
                            nested_props.pop("single_width", None)
                            nested["properties"] = nested_props
                            _left_align_svg_descendants(nested)
                        if nested.get("bubble_type") == "Button" and not self._clean_text(nested_props.get("label", "")):
                            nested_props.pop("width", None)
                            nested_props.pop("min_width_css", None)
                            nested_props.pop("max_width_css", None)
                            nested_props.pop("fixed_width", None)
                            nested_props.pop("single_width", None)
                            nested["properties"] = nested_props
                filtered_col_children.append(card)
            column["children"] = filtered_col_children

        group_node["children"] = normalized_children

    def _tune_avatar_media_groups(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        children = group_node.get("children", []) or []
        if len(children) != 1:
            return
        child = children[0]
        if not isinstance(child, dict) or child.get("bubble_type") != "Group":
            return
        child_props = child.get("properties", {}) or {}
        child_children = child.get("children", []) or []
        if len(child_children) != 1 or child_children[0].get("bubble_type") != "Image":
            return
        img = child_children[0]
        img_props = img.get("properties", {}) or {}
        img_w = self._to_int(img_props.get("width"), 0) or self._to_int(img_props.get("%w"), 0) or 0
        img_h = self._to_int(img_props.get("height"), 0) or self._to_int(img_props.get("%h"), 0) or 0
        if img_w <= 0 or img_h <= 0:
            return
        if max(img_w, img_h) > 160:
            return
        img_br = self._to_int(img_props.get("border_radius"), 0) or 0
        if img_br < 50 and abs(img_w - img_h) > 4:
            return
        child_w = self._to_int(child_props.get("width"), 0) or img_w
        if child_props.get("single_width") is None:
            child_props["single_width"] = True
        if child_props.get("min_width_css") in {None, "0px"} and child_w > 0:
            child_props["min_width_css"] = f"{child_w}px"
        child["properties"] = child_props
        parent_props = group_node.get("properties", {}) or {}
        if parent_props.get("fit_width") is None:
            parent_props["fit_width"] = True
        group_node["properties"] = parent_props

    def _tune_compact_badges(self, group_node: Dict[str, Any]) -> None:
        """Normalize compact circular/rounded badges using structural + CSS cues."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        children = group_node.get("children", []) or []
        if len(children) != 1:
            return
        child = children[0]
        if not isinstance(child, dict) or child.get("bubble_type") != "Text":
            return

        width = self._to_int(props.get("width"), 0) or 0
        height = self._to_int(props.get("height"), 0) or 0
        radius = self._to_int(props.get("border_radius"), 0) or 0
        bg_color = props.get("bg_color")
        if width <= 0 or height <= 0:
            return
        if width > 80 or height > 80:
            return
        if abs(width - height) > 4:
            return
        if radius < 80:
            return
        if self._is_transparent_color(bg_color):
            return

        # Compact badges should keep fixed geometry and center content.
        props["fit_height"] = False
        props["fit_width"] = False
        props["single_width"] = True
        props["single_height"] = True
        props["min_width_css"] = f"{width}px"
        props["max_width_css"] = f"{width}px"
        props["min_height_css"] = f"{height}px"
        props["max_height_css"] = f"{height}px"
        props["container_horiz_alignment"] = "center"
        props["container_vert_alignment"] = "center"
        props["align"] = "center"
        group_node["properties"] = props

        child_props = child.get("properties", {}) or {}
        child_props["align"] = "center"
        child_props["font_alignment"] = "center"
        child_props["horiz_alignment"] = "center"
        if width > 0:
            child_props.setdefault("width", width)
        child["properties"] = child_props

    def _is_compact_badge_group(self, node: Dict[str, Any]) -> bool:
        if not isinstance(node, dict) or node.get("bubble_type") != "Group":
            return False
        props = node.get("properties", {}) or {}
        children = node.get("children", []) or []
        if len(children) != 1:
            return False
        child = children[0]
        if not isinstance(child, dict) or child.get("bubble_type") != "Text":
            return False
        width = self._to_int(props.get("width"), 0) or 0
        height = self._to_int(props.get("height"), 0) or 0
        radius = self._to_int(props.get("border_radius"), 0) or 0
        bg_color = props.get("bg_color")
        if width <= 0 or height <= 0:
            return False
        if width > 80 or height > 80:
            return False
        if abs(width - height) > 4:
            return False
        if radius < 80:
            return False
        if self._is_transparent_color(bg_color):
            return False
        return True

    def _tune_compact_badge_wrappers(self, group_node: Dict[str, Any]) -> None:
        """Ensure wrapper groups around compact badges fit content width."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        children = group_node.get("children", []) or []
        if len(children) != 1:
            return
        child = children[0]
        if not self._is_compact_badge_group(child):
            return
        props = group_node.get("properties", {}) or {}
        # Only shrink wrappers that don't add their own visual padding/background.
        if not self._is_transparent_color(props.get("bg_color")):
            return
        if any((props.get(k) or 0) > 0 for k in ("padding_left", "padding_right", "padding_top", "padding_bottom")):
            return
        child_props = child.get("properties", {}) or {}
        child_w = self._to_int(child_props.get("width"), 0) or 0
        if child_w <= 0:
            return
        # Fit wrapper to badge content.
        props["fit_width"] = True
        if props.get("width") is None or (self._to_int(props.get("width"), 0) or 0) > child_w:
            props["width"] = child_w
        props["min_width_css"] = f"{child_w}px"
        props["max_width_css"] = f"{child_w}px"
        group_node["properties"] = props

    def _tune_absolute_center_offsets(self, group_node: Dict[str, Any]) -> None:
        """When an absolute child is center-anchored, mirror offsets on both sides."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        nonant = self._clean_text(props.get("nonant_alignment", "")).lower()
        if len(nonant) != 2:
            return
        x_axis, y_axis = nonant[0], nonant[1]
        if x_axis == "b":
            left = self._to_int(props.get("margin_left"), None)
            right = self._to_int(props.get("margin_right"), None)
            if left is not None and right is not None and abs(left - right) <= 2:
                props["margin_left"] = 0
                props["margin_right"] = 0
            elif left is not None and right is None:
                props["margin_right"] = left
            elif right is not None and left is None:
                props["margin_left"] = right
        if y_axis == "b":
            top = self._to_int(props.get("margin_top"), None)
            bottom = self._to_int(props.get("margin_bottom"), None)
            if top is not None and bottom is not None and abs(top - bottom) <= 2:
                props["margin_top"] = 0
                props["margin_bottom"] = 0
            elif top is not None and bottom is None:
                props["margin_bottom"] = top
            elif bottom is not None and top is None:
                props["margin_top"] = bottom
        group_node["properties"] = props

    def _tune_absolute_media_wrappers(self, group_node: Dict[str, Any]) -> None:
        """Absolute media shells should fit their content width and avoid stretching."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        nonant = self._clean_text(props.get("nonant_alignment", "")).lower()
        if len(nonant) != 2:
            return
        offsets = [
            self._to_int(props.get(k), 0) or 0
            for k in ("margin_left", "margin_right", "margin_top", "margin_bottom")
        ]
        has_offset = any(val != 0 for val in offsets)
        has_negative_offset = any(val < 0 for val in offsets)
        if not has_offset:
            return
        children = group_node.get("children", []) or []
        if len(children) != 1:
            return
        child = children[0]
        if not isinstance(child, dict) or child.get("bubble_type") != "Image":
            return
        if not self._is_transparent_color(props.get("bg_color")):
            return
        if any((props.get(k) or 0) > 0 for k in ("padding_left", "padding_right", "padding_top", "padding_bottom")):
            return
        child_props = child.get("properties", {}) or {}
        child_w = self._to_int(child_props.get("width"), 0) or 0
        if child_w <= 0:
            return
        if child_w >= 240:
            if props.get("min_width_css") == f"{child_w}px":
                props["min_width_css"] = None
            if props.get("max_width_css") == f"{child_w}px":
                props["max_width_css"] = None
            if props.get("single_width") is True:
                props["single_width"] = False
            if props.get("fit_width") is True:
                props["fit_width"] = False
            group_node["properties"] = props
            return
        props["fit_width"] = True
        props["single_width"] = True
        if props.get("width") is None or (self._to_int(props.get("width"), 0) or 0) > child_w:
            props["width"] = child_w
        props["min_width_css"] = f"{child_w}px"
        props["max_width_css"] = f"{child_w}px"
        group_node["properties"] = props

    def _tune_relative_overlay_layers(self, group_node: Dict[str, Any]) -> None:
        """Ensure overlay children in relative containers preserve front/back order."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if str(props.get("layout", "")).lower() != "relative":
            return
        children = group_node.get("children", []) or []
        if len(children) < 2:
            return
        for idx, child in enumerate(children, start=1):
            if not isinstance(child, dict):
                continue
            child_props = child.get("properties", {}) or {}
            if child_props.get("zindex") is not None:
                continue
            nonant = self._clean_text(child_props.get("nonant_alignment", "")).lower()
            has_offsets = any(
                child_props.get(k) is not None
                for k in ("margin_left", "margin_right", "margin_top", "margin_bottom")
            )
            if nonant or has_offsets:
                child_props["zindex"] = 30 + idx
            else:
                child_props["zindex"] = idx
            child["properties"] = child_props

    def _tune_relative_flow_media_layers(self, group_node: Dict[str, Any]) -> None:
        """Anchor in-flow media layers inside relative groups and keep overlays above them."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if str(props.get("layout", "")).lower() != "relative":
            return
        parent_w = self._to_int(props.get("width"), None)
        parent_h = self._to_int(props.get("height"), None)
        if parent_w is None or parent_h is None:
            return
        pad_left = self._to_int(props.get("padding_left"), 0) or 0
        pad_right = self._to_int(props.get("padding_right"), 0) or 0
        pad_top = self._to_int(props.get("padding_top"), 0) or 0
        pad_bottom = self._to_int(props.get("padding_bottom"), 0) or 0
        inner_w = max(parent_w - pad_left - pad_right, 0)
        inner_h = max(parent_h - pad_top - pad_bottom, 0)
        if inner_w <= 0 or inner_h <= 0:
            return
        horiz_align = self._clean_text(props.get("container_horiz_alignment", "")).lower()
        vert_align = self._clean_text(props.get("container_vert_alignment", "")).lower()
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) < 2:
            return

        base_layers: List[Dict[str, Any]] = []
        overlays: List[Dict[str, Any]] = []
        for child in children:
            child_props = child.get("properties", {}) or {}
            anchored = bool(self._clean_text(child_props.get("nonant_alignment", "")))
            if anchored or any(
                (self._to_int(child_props.get(k), 0) or 0) != 0
                for k in ("margin_left", "margin_right", "margin_top", "margin_bottom")
            ):
                overlays.append(child)
                continue
            if self._is_relative_base_media_child(child):
                base_layers.append(child)

        if not base_layers or not overlays:
            return

        for idx, child in enumerate(base_layers, start=1):
            child_props = child.get("properties", {}) or {}
            child_w = self._to_int(child_props.get("width"), None)
            child_h = self._to_int(child_props.get("height"), None)
            if child_w is None or child_h is None or child_w <= 0 or child_h <= 0:
                continue
            extra_x = max(inner_w - child_w, 0)
            extra_y = max(inner_h - child_h, 0)

            x_axis = "a"
            if horiz_align in {"center", "space-around", "space-evenly"}:
                x_axis = "b"
                child_props["margin_left"] = 0
                child_props["margin_right"] = 0
            elif horiz_align in {"flex-end", "end", "right"}:
                x_axis = "c"
                child_props["margin_right"] = pad_right
            else:
                child_props["margin_left"] = pad_left

            y_axis = "a"
            if extra_y <= 4 and pad_bottom > 0:
                y_axis = "c"
                child_props["margin_top"] = 0
                child_props["margin_bottom"] = 0
            elif vert_align in {"center", "space-around", "space-evenly"}:
                y_axis = "b"
                child_props["margin_top"] = 0
                child_props["margin_bottom"] = 0
            elif vert_align in {"flex-end", "end", "bottom"}:
                y_axis = "c"
                child_props["margin_bottom"] = 0
            elif pad_top > 0 or pad_bottom > 0:
                child_props["margin_top"] = 0

            child_props["nonant_alignment"] = f"{x_axis}{y_axis}"
            child_props["zindex"] = idx
            child["properties"] = child_props

        max_base_z = max(
            (self._to_int((child.get("properties", {}) or {}).get("zindex"), 0) or 0)
            for child in base_layers
        )
        next_z = max_base_z + 1
        for child in overlays:
            child_props = child.get("properties", {}) or {}
            current_z = self._to_int(child_props.get("zindex"), 0) or 0
            if current_z <= max_base_z:
                child_props["zindex"] = next_z
                next_z += 1
            child["properties"] = child_props

    def _tune_relative_primary_flow_child(self, group_node: Dict[str, Any]) -> None:
        """Anchor a single substantive flow child inside a relative shell."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if str(props.get("layout", "")).lower() != "relative":
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) < 2:
            return
        flow_children: List[Dict[str, Any]] = []
        overlays: List[Dict[str, Any]] = []
        for child in children:
            child_props = child.get("properties", {}) or {}
            anchored = bool(self._clean_text(child_props.get("nonant_alignment", "")))
            has_offsets = any(
                (self._to_int(child_props.get(k), 0) or 0) != 0
                for k in ("margin_left", "margin_right", "margin_top", "margin_bottom")
            )
            if anchored or has_offsets:
                overlays.append(child)
            else:
                flow_children.append(child)
        if len(flow_children) != 1 or not overlays:
            return
        child = flow_children[0]
        child_props = child.get("properties", {}) or {}
        child_w = self._to_int(child_props.get("width"), None)
        child_h = self._to_int(child_props.get("height"), None)
        parent_w = self._to_int(props.get("width"), None)
        parent_h = self._to_int(props.get("height"), None)
        if child_w is None or child_h is None or parent_w is None or parent_h is None:
            return
        pad_left = self._to_int(props.get("padding_left"), 0) or 0
        pad_right = self._to_int(props.get("padding_right"), 0) or 0
        pad_top = self._to_int(props.get("padding_top"), 0) or 0
        pad_bottom = self._to_int(props.get("padding_bottom"), 0) or 0
        inner_w = max(parent_w - pad_left - pad_right, 0)
        inner_h = max(parent_h - pad_top - pad_bottom, 0)
        horiz_align = self._clean_text(child_props.get("horiz_alignment", "")).lower()
        x_axis = "b" if horiz_align == "center" else ("c" if horiz_align in {"flex-end", "end", "right"} else "a")
        vert_align = self._clean_text(props.get("container_vert_alignment", "")).lower()
        if vert_align in {"center", "space-around", "space-evenly"}:
            y_axis = "b"
        elif vert_align in {"flex-end", "end", "bottom"}:
            y_axis = "c"
        elif abs(inner_h - child_h) <= 4 and (pad_top > 0 or pad_bottom > 0):
            y_axis = "b"
        else:
            y_axis = "a"
        child_props["nonant_alignment"] = f"{x_axis}{y_axis}"
        child_props["margin_left"] = 0
        child_props["margin_right"] = 0
        child_props["margin_top"] = 0
        child_props["margin_bottom"] = 0
        child["properties"] = child_props

    def _tune_inline_text_wrappers(self, group_node: Dict[str, Any]) -> None:
        """Compact inline text wrappers in row layouts should size to content."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if self._clean_text(props.get("layout", "")).lower() != "row":
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) < 2:
            return
        candidates: List[Dict[str, Any]] = []
        widths: List[int] = []
        for child in children:
            if child.get("bubble_type") != "Group":
                continue
            child_props = child.get("properties", {}) or {}
            if self._has_visual_shell_props(child_props):
                continue
            nested = [c for c in (child.get("children", []) or []) if isinstance(c, dict)]
            if len(nested) != 1 or nested[0].get("bubble_type") != "Text":
                continue
            width = self._to_int(child_props.get("width"), None)
            if width is None or width <= 0 or width > 220:
                continue
            if any((self._to_int(child_props.get(k), 0) or 0) != 0 for k in ("padding_top", "padding_right", "padding_bottom", "padding_left")):
                continue
            candidates.append(child)
            widths.append(width)
        if len(candidates) < 2:
            return
        if max(widths) - min(widths) < 4:
            return
        for child in candidates:
            child_props = child.get("properties", {}) or {}
            child_props["fit_width"] = True
            child_props["single_width"] = False
            child["properties"] = child_props

    def _is_relative_base_media_child(self, child: Dict[str, Any]) -> bool:
        if not isinstance(child, dict):
            return False
        bubble_type = str(child.get("bubble_type", "")).lower()
        if bubble_type == "image":
            return True
        if bubble_type != "group":
            return False
        props = child.get("properties", {}) or {}
        if props.get("background_style") == "image":
            return True
        bg = props.get("bg_color")
        if bg and not self._is_transparent_color(bg):
            return True
        children = [c for c in (child.get("children", []) or []) if isinstance(c, dict)]
        if len(children) == 1 and children[0].get("bubble_type") == "Image":
            return True
        return False

    def _tune_visual_fixed_height_groups(self, group_node: Dict[str, Any]) -> None:
        """Keep explicit heights for decorative shells and distribute split card content."""
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        layout = self._clean_text(props.get("layout", "")).lower()
        if layout not in {"column", "row"}:
            return
        height = self._to_int(props.get("height"), None)
        if height is None or height < 180:
            return
        if not self._has_visual_shell_props(props):
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if not children:
            return

        if props.get("min_height_css") is None:
            props["min_height_css"] = f"{height}px"

        if (
            layout == "column"
            and len(children) == 2
            and props.get("container_vert_alignment") in {None, "", "stretch", "flex-start"}
            and all(self._node_has_textual_content(child) for child in children)
        ):
            props["container_vert_alignment"] = "space-between"
        group_node["properties"] = props

    def _compress_non_visual_spacers_into_gap(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        layout = self._clean_text(props.get("layout", "")).lower()
        if layout not in {"row", "column"}:
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) < 2:
            return
        leading_index = 0
        trailing_index = len(children) - 1
        leading_padding = 0
        trailing_padding = 0
        while leading_index < len(children) and self._is_non_visual_flow_spacer(children[leading_index], layout):
            leading_padding += self._spacer_size_from_node(children[leading_index], layout)
            leading_index += 1
        while trailing_index >= leading_index and self._is_non_visual_flow_spacer(children[trailing_index], layout):
            trailing_padding += self._spacer_size_from_node(children[trailing_index], layout)
            trailing_index -= 1
        if leading_padding > 0:
            pad_key = "padding_top" if layout == "column" else "padding_left"
            current = self._to_int(props.get(pad_key), 0) or 0
            if leading_padding > current:
                props[pad_key] = leading_padding
        if trailing_padding > 0:
            pad_key = "padding_bottom" if layout == "column" else "padding_right"
            current = self._to_int(props.get(pad_key), 0) or 0
            if trailing_padding > current:
                props[pad_key] = trailing_padding
        interior_children = children[leading_index : trailing_index + 1] if trailing_index >= leading_index else []
        kept_children: List[Dict[str, Any]] = []
        spacer_sizes: List[int] = []
        for child in interior_children:
            if self._is_non_visual_flow_spacer(child, layout):
                spacer_size = self._spacer_size_from_node(child, layout)
                if spacer_size > 0:
                    spacer_sizes.append(spacer_size)
                continue
            kept_children.append(child)
        if not kept_children:
            return
        interior_spacer_count = len(interior_children) - len(kept_children)
        expected_gap_spacers = max(len(kept_children) - 1, 0)
        if spacer_sizes and len(kept_children) >= 2:
            ordered = sorted(spacer_sizes)
            if interior_spacer_count == expected_gap_spacers and all(abs(size - ordered[0]) <= 2 for size in ordered):
                inferred_gap = ordered[len(ordered) // 2]
                current_gap = self._to_int(props.get("gap"), 0) or 0
                if inferred_gap > current_gap:
                    props["gap"] = inferred_gap
                    props["use_gap"] = True
            else:
                kept_children = interior_children
        if (leading_padding > 0 or trailing_padding > 0) and len(kept_children) <= 1:
            props["fit_height" if layout == "column" else "fit_width"] = True
        group_node["properties"] = props
        group_node["children"] = kept_children

    def _normalize_blog_card_row(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if self._clean_text(props.get("layout", "")).lower() != "row":
            return
        width = self._to_int(props.get("width"), None)
        height = self._to_int(props.get("height"), None)
        if width is None or height is None or not (620 <= width <= 720 and 150 <= height <= 230):
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) != 2:
            return

        media_child: Optional[Dict[str, Any]] = None
        info_child: Optional[Dict[str, Any]] = None
        for child in children:
            child_props = child.get("properties", {}) or {}
            child_width = self._to_int(child_props.get("width"), None)
            child_height = self._to_int(child_props.get("height"), None)
            nested = [c for c in (child.get("children", []) or []) if isinstance(c, dict)]
            nested_group = nested[0] if len(nested) == 1 and nested[0].get("bubble_type") == "Group" else None
            nested_group_props = nested_group.get("properties", {}) or {} if nested_group else {}
            nested_group_width = self._to_int(nested_group_props.get("width"), None)
            nested_group_height = self._to_int(nested_group_props.get("height"), None)
            nested_group_children = [c for c in (nested_group.get("children", []) or []) if isinstance(c, dict)] if nested_group else []
            has_media_shell = (
                nested_group is not None
                and nested_group_width is not None
                and nested_group_height is not None
                and 100 <= nested_group_width <= 140
                and 100 <= nested_group_height <= 130
                and any(c.get("bubble_type") == "Image" for c in nested_group_children)
            )
            if (
                child.get("bubble_type") == "Group"
                and child_width is not None
                and 140 <= child_width <= 190
                and (
                    (child_height is not None and 100 <= child_height <= 140 and any(c.get("bubble_type") == "Image" for c in nested))
                    or has_media_shell
                )
            ):
                media_child = child
            elif (
                child.get("bubble_type") == "Group"
                and child_width is not None
                and 360 <= child_width <= 460
            ):
                info_child = child

        if media_child is None or info_child is None:
            return

        props["layout"] = "relative"
        props["fit_width"] = False
        props["width_unset"] = False
        props["fit_height"] = False
        props["height"] = height
        props["container_horiz_alignment"] = "flex-start"
        props["container_vert_alignment"] = "flex-start"
        props["padding_left"] = max(self._to_int(props.get("padding_left"), 0) or 0, 100)
        props["border_type"] = "independent"
        if not (self._to_int(props.get("border_width_bottom"), 0) or 0):
            props["border_width_bottom"] = 1
        props.setdefault("border_style_bottom", "solid")
        props.setdefault("border_color_bottom", "rgba(52, 46, 173, 0.06)")
        group_node["properties"] = props

        media_props = media_child.get("properties", {}) or {}
        media_props["nonant_alignment"] = "aa"
        media_props["margin_left"] = 0
        media_props["margin_top"] = 0
        media_props["margin_right"] = 0
        media_props["margin_bottom"] = 0
        media_props["fit_width"] = False
        media_props["fit_height"] = False
        media_props["width_unset"] = False
        media_child["properties"] = media_props

        info_props = info_child.get("properties", {}) or {}
        info_props["layout"] = "relative"
        info_props["nonant_alignment"] = "aa"
        info_props["margin_left"] = 0
        info_props["margin_top"] = 0
        info_props["margin_right"] = 0
        info_props["margin_bottom"] = 0
        info_props["fit_width"] = False
        info_props["fit_height"] = False
        info_props["width_unset"] = False
        info_props["height"] = height
        info_props["container_horiz_alignment"] = "flex-start"
        info_props["container_vert_alignment"] = "flex-start"
        info_props["padding_right"] = max(self._to_int(info_props.get("padding_right"), 0) or 0, 100)
        for key in (
            "border_radius",
            "border_roundness_top_left",
            "border_roundness_top_right",
            "border_roundness_bottom_right",
            "border_roundness_bottom_left",
        ):
            info_props[key] = 0
        info_child["properties"] = info_props

        info_children = [c for c in (info_child.get("children", []) or []) if isinstance(c, dict)]
        if not info_children:
            return

        date_group: Optional[Dict[str, Any]] = None
        title_group: Optional[Dict[str, Any]] = None
        button_group: Optional[Dict[str, Any]] = None
        for child in info_children:
            child_props = child.get("properties", {}) or {}
            child_name = self._clean_text(child_props.get("name", "")).lower()
            child_width = self._to_int(child_props.get("width"), None)
            child_height = self._to_int(child_props.get("height"), None)
            if child.get("bubble_type") == "Group" and child_width is not None and child_height is not None:
                if 50 <= child_width <= 70 and 60 <= child_height <= 80:
                    date_group = child
                    continue
                if 300 <= child_width <= 320:
                    title_group = child
                    continue
                if 32 <= child_height <= 40 and child_width is not None and child_width <= 48:
                    button_group = child
            if child.get("bubble_type") == "Group" and "blog date" in child_name:
                date_group = child
                continue
            if child.get("bubble_type") == "Group" and child_name == "column_2":
                title_group = child
                continue
            if child.get("bubble_type") == "Group" and "circle btn style type" in child_name:
                button_group = child

        if date_group is not None:
            d_props = date_group.get("properties", {}) or {}
            d_props["nonant_alignment"] = "aa"
            d_props["fit_width"] = True
            d_props["width_unset"] = False
            if self._to_int(d_props.get("width"), None) is None:
                d_props["width"] = 58
            d_props["margin_left"] = -100
            d_props["margin_top"] = 0
            d_props["margin_right"] = 0
            d_props["margin_bottom"] = 0
            d_props["fit_height"] = False
            date_group["properties"] = d_props

        if title_group is not None:
            t_props = title_group.get("properties", {}) or {}
            t_props["nonant_alignment"] = "aa"
            t_props["width"] = 310
            t_props["fit_width"] = False
            t_props["fit_height"] = False
            t_props["width_unset"] = False
            t_props["margin_left"] = 155
            t_props["margin_top"] = 0
            t_props["margin_right"] = 0
            t_props["margin_bottom"] = 0
            title_group["properties"] = t_props

        if button_group is not None:
            b_props = button_group.get("properties", {}) or {}
            b_props["nonant_alignment"] = "cc"
            b_props["width"] = 36
            b_props["height"] = 36
            b_props["fit_width"] = False
            b_props["fit_height"] = False
            b_props["fixed_width"] = True
            b_props["fixed_height"] = True
            b_props["width_unset"] = False
            b_props["min_width_css"] = "36px"
            b_props["max_width_css"] = "36px"
            b_props["min_height_css"] = "36px"
            b_props["max_height_css"] = "36px"
            b_props["margin_left"] = 0
            b_props["margin_top"] = 0
            b_props["margin_right"] = -100
            b_props["margin_bottom"] = 0
            button_group["properties"] = b_props
            button_children = [c for c in (button_group.get("children", []) or []) if isinstance(c, dict)]
            if button_children:
                def _score(child: Dict[str, Any]) -> int:
                    c_props = child.get("properties", {}) or {}
                    return (
                        abs(self._to_int(c_props.get("margin_left"), 0) or 0)
                        + abs(self._to_int(c_props.get("margin_top"), 0) or 0)
                        + abs(self._to_int(c_props.get("margin_right"), 0) or 0)
                        + abs(self._to_int(c_props.get("margin_bottom"), 0) or 0)
                    )

                kept = min(button_children, key=_score)
                c_props = kept.get("properties", {}) or {}
                c_props["horiz_alignment"] = "center"
                c_props["vert_alignment"] = "center"
                c_props["margin_left"] = 0
                c_props["margin_top"] = 0
                c_props["margin_right"] = 0
                c_props["margin_bottom"] = 0
                kept["properties"] = c_props
                button_group["children"] = [kept]

    def _propagate_parent_top_corners_to_full_width_header(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if self._clean_text(props.get("layout", "")).lower() != "column":
            return
        top_left = self._to_int(props.get("border_roundness_top_left"), 0) or 0
        top_right = self._to_int(props.get("border_roundness_top_right"), 0) or 0
        if top_left <= 0 and top_right <= 0:
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict)]
        if len(children) < 2:
            return
        header = children[0]
        if header.get("bubble_type") != "Group":
            return
        header_props = header.get("properties", {}) or {}
        parent_width = self._to_int(props.get("width"), None)
        header_width = self._to_int(header_props.get("width"), None)
        header_height = self._to_int(header_props.get("height"), None)
        if parent_width is None or header_width is None or abs(parent_width - header_width) > 3:
            return
        if header_height is None or header_height < 60:
            return
        if not self._has_visual_shell_props(header_props):
            return
        header_props["four_border_style"] = True
        header_props["border_roundness_top_left"] = top_left
        header_props["border_roundness_top_right"] = top_right
        header_props["border_roundness_bottom_left"] = 0
        header_props["border_roundness_bottom_right"] = 0
        header_props["min_height_css"] = f"{int(header_height)}px"
        header["properties"] = header_props

    def _normalize_negative_row_gutters(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        props = group_node.get("properties", {}) or {}
        if self._clean_text(props.get("layout", "")).lower() != "row":
            return
        margin_left = self._to_int(props.get("margin_left"), 0) or 0
        margin_right = self._to_int(props.get("margin_right"), 0) or 0
        if margin_left >= 0 or margin_right >= 0:
            return
        gutter_left = abs(margin_left)
        gutter_right = abs(margin_right)
        if abs(gutter_left - gutter_right) > 2 or gutter_left > 24:
            return
        children = [child for child in (group_node.get("children", []) or []) if isinstance(child, dict) and child.get("bubble_type") == "Group"]
        if len(children) < 2:
            return
        matching_children = 0
        for child in children:
            child_props = child.get("properties", {}) or {}
            pad_left = self._to_int(child_props.get("padding_left"), 0) or 0
            pad_right = self._to_int(child_props.get("padding_right"), 0) or 0
            if abs(pad_left - gutter_left) <= 2 and abs(pad_right - gutter_right) <= 2:
                matching_children += 1
        if matching_children < 2:
            return
        props["margin_left"] = 0
        props["margin_right"] = 0
        props["fit_width"] = False
        props["width_unset"] = False
        group_node["properties"] = props
        for child in children:
            child_props = child.get("properties", {}) or {}
            if abs((self._to_int(child_props.get("padding_left"), 0) or 0) - gutter_left) <= 2:
                child_props["padding_left"] = 0
            if abs((self._to_int(child_props.get("padding_right"), 0) or 0) - gutter_right) <= 2:
                child_props["padding_right"] = 0
            child["properties"] = child_props

    def _spacer_size_from_node(self, node: Dict[str, Any], layout: str) -> int:
        if not isinstance(node, dict):
            return 0
        child_props = node.get("properties", {}) or {}
        return self._to_int(
            child_props.get("height") if layout == "column" else child_props.get("width"),
            0,
        ) or 0

    def _is_non_visual_flow_spacer(self, node: Dict[str, Any], layout: str) -> bool:
        if not isinstance(node, dict) or node.get("bubble_type") != "Group":
            return False
        props = node.get("properties", {}) or {}
        if node.get("children"):
            return False
        if self._has_visual_shell_props(props):
            return False
        if any((self._to_int(props.get(k), 0) or 0) != 0 for k in ("padding_top", "padding_right", "padding_bottom", "padding_left")):
            return False
        if self._clean_text(props.get("nonant_alignment", "")):
            return False
        if props.get("zindex") is not None:
            return False
        size = self._to_int(props.get("height") if layout == "column" else props.get("width"), 0) or 0
        cross = self._to_int(props.get("width") if layout == "column" else props.get("height"), 0) or 0
        if size < 6 or size > 200:
            return False
        if cross > 0 and cross < 8:
            return False
        return True

    def _is_non_visual_flow_spacer_element(self, element: Dict[str, Any], layout: str) -> bool:
        if not isinstance(element, dict):
            return False
        styles = self._merge_styles(element)
        if self._is_absolutely_positioned(styles):
            return False
        if self._has_visual_box(styles):
            return False
        if self._has_text_content(element) or self._has_media_content(element):
            return False
        children = [child for child in (element.get("children", []) or []) if isinstance(child, dict)]
        if children:
            return False
        if any((self._parse_dimension(styles.get(key)) or 0) != 0 for key in ("padding-top", "padding-right", "padding-bottom", "padding-left")):
            return False
        rect = element.get("rect", {}) or {}
        size = self._to_int((rect.get("height") if layout == "column" else rect.get("width")), None)
        if size is None:
            size = self._parse_dimension(styles.get("height") if layout == "column" else styles.get("width"))
        cross = self._to_int((rect.get("width") if layout == "column" else rect.get("height")), None)
        if cross is None:
            cross = self._parse_dimension(styles.get("width") if layout == "column" else styles.get("height"))
        if size is None or size < 6 or size > 200:
            return False
        if cross is not None and 0 < cross < 8:
            return False
        return True

    def _extract_edge_spacer_padding_from_children(
        self,
        children: List[Dict[str, Any]],
        layout: str,
    ) -> tuple[Dict[str, str], List[Dict[str, Any]]]:
        if layout not in {"row", "column"}:
            return {}, []
        parsed_children = [child for child in (children or []) if isinstance(child, dict)]
        if len(parsed_children) < 3:
            return {}, []
        substantive_indexes = [
            idx
            for idx, child in enumerate(parsed_children)
            if not child.get("_skip_from_mapping")
            and not self._is_absolutely_positioned(self._merge_styles(child))
            and not self._is_non_visual_flow_spacer_element(child, layout)
        ]
        if not substantive_indexes:
            return {}, []
        first_idx = substantive_indexes[0]
        last_idx = substantive_indexes[-1]
        leading_spacers: List[Dict[str, Any]] = []
        trailing_spacers: List[Dict[str, Any]] = []
        idx = first_idx - 1
        while idx >= 0:
            child = parsed_children[idx]
            if self._is_non_visual_flow_spacer_element(child, layout):
                leading_spacers.append(child)
                idx -= 1
                continue
            if self._is_absolutely_positioned(self._merge_styles(child)):
                idx -= 1
                continue
            break
        idx = last_idx + 1
        while idx < len(parsed_children):
            child = parsed_children[idx]
            if self._is_non_visual_flow_spacer_element(child, layout):
                trailing_spacers.append(child)
                idx += 1
                continue
            if self._is_absolutely_positioned(self._merge_styles(child)):
                idx += 1
                continue
            break
        def _sum_size(nodes: List[Dict[str, Any]]) -> int:
            total = 0
            for node in nodes:
                rect = node.get("rect", {}) or {}
                value = self._to_int(rect.get("height") if layout == "column" else rect.get("width"), None)
                if value is None:
                    styles = self._merge_styles(node)
                    value = self._parse_dimension(styles.get("height") if layout == "column" else styles.get("width"))
                total += value or 0
            return total
        leading_size = _sum_size(leading_spacers)
        trailing_size = _sum_size(trailing_spacers)
        padding: Dict[str, str] = {}
        if leading_size > 0:
            padding["padding-top" if layout == "column" else "padding-left"] = f"{leading_size}px"
        if trailing_size > 0:
            padding["padding-bottom" if layout == "column" else "padding-right"] = f"{trailing_size}px"
        return padding, leading_spacers + trailing_spacers

    def _has_visual_shell_props(self, props: Dict[str, Any]) -> bool:
        bg_style = self._clean_text(props.get("background_style") or props.get("bg_style")).lower()
        if bg_style in {"image", "gradient"}:
            return True
        if not self._is_transparent_color(props.get("bg_color")):
            return True
        if self._clean_text(props.get("shadow_style", "")).lower() not in {"", "none"}:
            return True
        if any(
            (self._to_int(props.get(k), 0) or 0) > 0
            for k in ("shadow_h", "shadow_v", "shadow_blur", "shadow_spread")
        ):
            return True
        if any(
            (self._to_int(props.get(k), 0) or 0) > 0
            for k in (
                "border_width",
                "border_width_top",
                "border_width_right",
                "border_width_bottom",
                "border_width_left",
            )
        ):
            return True
        if any(
            self._clean_text(props.get(k, "")).lower() not in {"", "none"}
            for k in ("border_style_top", "border_style_right", "border_style_bottom", "border_style_left")
        ):
            return True
        return False

    def _has_container_children(self, element: Dict[str, Any]) -> bool:
        children = [c for c in (element.get("children", []) or []) if isinstance(c, dict)]
        for child in children:
            child_type = str(child.get("type", "")).lower()
            if child_type in {"div", "section", "article", "header", "footer", "main", "aside", "nav", "ul", "ol", "form"}:
                return True
        return False

    def _should_auto_constrain_leaf_width(
        self,
        element: Dict[str, Any],
        layout: str,
        width: Optional[int],
    ) -> bool:
        # Do not auto-inject CSS width constraints for group containers.
        return False

    def _should_prefer_fit_width_for_container(
        self,
        element: Dict[str, Any],
        layout: str,
        width: Optional[int],
        classes: List[str],
    ) -> bool:
        if layout not in {"row", "column"}:
            return False
        if width is None or width <= 0 or width > 480:
            return False
        styles = self._merge_styles(element)
        explicit_width = self._parse_dimension(styles.get("width"))
        if explicit_width is not None and explicit_width > 0:
            return False
        if self._is_bootstrap_container(classes, layout):
            return False
        parent_rect = element.get("_parent_rect") or {}
        parent_width = self._to_int(parent_rect.get("width"), None)
        if parent_width is not None and parent_width > 0:
            if float(width) / float(parent_width) >= 0.25:
                return False
        if not any(isinstance(c, dict) for c in (element.get("children", []) or [])):
            return False
        return True

    def _inherit_single_child_visual_shell(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        def _inherit_shell_radius(wrapper_node: Dict[str, Any], shell_node: Dict[str, Any]) -> None:
            wrapper_props = wrapper_node.get("properties", {}) or {}
            shell_props = shell_node.get("properties", {}) or {}
            for key in (
                "border_roundness_top_left",
                "border_roundness_top_right",
                "border_roundness_bottom_right",
                "border_roundness_bottom_left",
                "border_roundness_top",
                "border_roundness_right",
                "border_roundness_bottom",
                "border_roundness_left",
                "border_radius",
            ):
                if wrapper_props.get(key) in {None, 0} and shell_props.get(key) not in {None, 0}:
                    wrapper_props[key] = shell_props.get(key)
            wrapper_node["properties"] = wrapper_props

        group_children = [c for c in (group_node.get("children", []) or []) if isinstance(c, dict)]
        direct_shell_groups = [
            child for child in group_children
            if child.get("bubble_type") == "Group" and self._has_visual_shell_props(child.get("properties", {}) or {})
        ]
        if len(direct_shell_groups) == 1:
            group_props = group_node.get("properties", {}) or {}
            shell_candidate = direct_shell_groups[0]
            if not self._has_visual_shell_props(group_props):
                _inherit_shell_radius(group_node, shell_candidate)

        for child in group_children:
            if child.get("bubble_type") != "Group":
                continue
            child_props = child.get("properties", {}) or {}
            if self._has_visual_shell_props(child_props):
                continue
            nested_children = [c for c in (child.get("children", []) or []) if isinstance(c, dict)]
            shell_children = [
                c for c in nested_children
                if isinstance(c, dict) and c.get("bubble_type") == "Group" and self._has_visual_shell_props(c.get("properties", {}) or {})
            ]
            if len(shell_children) != 1:
                continue
            shell = shell_children[0]
            _inherit_shell_radius(child, shell)

    def _relax_single_media_wrapper_widths(self, group_node: Dict[str, Any]) -> None:
        if not isinstance(group_node, dict) or group_node.get("bubble_type") != "Group":
            return
        for child in group_node.get("children", []) or []:
            if not isinstance(child, dict) or child.get("bubble_type") != "Group":
                continue
            props = child.get("properties", {}) or {}
            if self._has_visual_shell_props(props):
                continue
            nested_children = [c for c in (child.get("children", []) or []) if isinstance(c, dict)]
            if len(nested_children) != 1:
                continue
            inner = nested_children[0]
            if not isinstance(inner, dict) or inner.get("bubble_type") != "Image":
                continue
            width = self._to_int(props.get("width"), None)
            max_width_css = self._clean_text(props.get("max_width_css", ""))
            if width is not None and width > 72 and not max_width_css:
                continue
            props.pop("max_width_css", None)
            props.pop("min_width_css", None)
            props.pop("single_width", None)
            child["properties"] = props

    def _node_has_textual_content(self, node: Dict[str, Any]) -> bool:
        if not isinstance(node, dict):
            return False
        bubble_type = str(node.get("bubble_type", "")).lower()
        if bubble_type == "text":
            props = node.get("properties", {}) or {}
            return bool(self._clean_text(props.get("content") or props.get("text") or ""))
        for child in node.get("children", []) or []:
            if self._node_has_textual_content(child):
                return True
        return False

    def _element_has_textual_content(self, element: Dict[str, Any]) -> bool:
        if not isinstance(element, dict):
            return False
        node_type = str(element.get("type", "")).lower()
        if node_type in {"text", "#text"}:
            return bool(self._clean_text(element.get("text") or element.get("content") or ""))
        if element.get("text_segments"):
            for seg in element.get("text_segments") or []:
                if isinstance(seg, dict) and self._clean_text(seg.get("text") or ""):
                    return True
        if self._clean_text(element.get("text") or element.get("content") or ""):
            return True
        for child in element.get("children", []) or []:
            if self._element_has_textual_content(child):
                return True
        return False

    def _split_wrapped_row_into_rows(self, group_node: Dict[str, Any]) -> None:
        props = group_node.get("properties", {}) or {}
        if str(props.get("layout", "")).lower() != "row":
            return
        flex_wrap = str(props.get("flex_wrap", "")).lower()

        children = group_node.get("children", []) or []
        if len(children) < 4:
            return
        if not all(isinstance(ch, dict) and ch.get("bubble_type") == "Group" for ch in children):
            return

        parent_width = self._to_int(props.get("width"), 0) or 0
        child_widths: List[int] = []
        unresolved_children = 0
        for ch in children:
            ch_props = (ch.get("properties", {}) or {})
            w = self._to_int(ch_props.get("width"), 0) or 0
            if w <= 0:
                w = self._to_int(ch_props.get("%w"), 0) or 0
            if w <= 0 and parent_width > 0:
                span = ch_props.get("__col_span")
                if isinstance(span, int) and 1 <= span <= 12:
                    w = int(round((float(parent_width) * float(span)) / 12.0))
            if w <= 0 and parent_width > 0:
                max_width_css = self._clean_text(ch_props.get("max_width_css", "")).lower()
                if max_width_css:
                    pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", max_width_css)
                    if pct_m:
                        try:
                            pct = float(pct_m.group(1))
                        except Exception:
                            pct = 0.0
                        if pct > 0:
                            w = int(round((float(parent_width) * pct) / 100.0))
                    if w <= 0:
                        px_m = re.search(r"(\d+(?:\.\d+)?)\s*px", max_width_css)
                        if px_m:
                            try:
                                w = int(round(float(px_m.group(1))))
                            except Exception:
                                w = 0
            if w <= 0:
                unresolved_children += 1
                continue
            child_widths.append(w)
        if not child_widths:
            return
        if unresolved_children > 0:
            sorted_known = sorted(child_widths)
            fallback_w = max(sorted_known[len(sorted_known) // 2], 1)
            child_widths.extend([fallback_w] * unresolved_children)

        sorted_widths = sorted(child_widths)
        median_width = sorted_widths[len(sorted_widths) // 2]
        base_width = max(median_width, 1)
        approx_per_row = int(round(float(parent_width) / float(base_width))) if parent_width > 0 else 0
        width_variation = max(child_widths) - min(child_widths)
        likely_wrapped_grid = (
            parent_width > 0
            and width_variation <= 12
            and 2 <= approx_per_row <= 4
            and len(children) >= approx_per_row * 2
            and len(children) % approx_per_row == 0
            and sum(child_widths) > int(parent_width * 1.2)
        )
        if flex_wrap not in {"wrap", "wrap-reverse"} and not likely_wrapped_grid:
            return
        if approx_per_row < 2:
            return
        if approx_per_row >= len(children):
            return

        chunk_size = approx_per_row
        chunks = [children[i:i + chunk_size] for i in range(0, len(children), chunk_size)]
        if len(chunks) <= 1:
            return

        gap_value = self._to_int(props.get("gap"), 0) or 0
        row_children: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(chunks, start=1):
            row_children.append(
                {
                    "bubble_type": "Group",
                    "properties": {
                        "name": f"Wrapped Row {idx}",
                        "layout": "row",
                        "gap": gap_value,
                        "width": parent_width if parent_width > 0 else None,
                        "height": None,
                        "fit_height": True,
                        "padding_top": 0,
                        "padding_bottom": 0,
                        "padding_left": 0,
                        "padding_right": 0,
                        "bg_color": None,
                    },
                    "children": chunk,
                }
            )

        props["layout"] = "column"
        props["gap"] = gap_value
        props.pop("flex_wrap", None)
        group_node["properties"] = props
        group_node["children"] = row_children

    def _sort_children_by_visual_flow(
        self,
        children: List[Dict[str, Any]],
        parent_layout: Optional[str],
    ) -> List[Dict[str, Any]]:
        layout = self._clean_text(parent_layout).lower()
        if layout not in {"row", "column"} or len(children) < 2:
            return children
        sortable = []
        for idx, child in enumerate(children):
            if not isinstance(child, dict):
                return children
            styles = self._merge_styles(child)
            if self._is_absolutely_positioned(styles):
                return children
            rect = child.get("rect", {}) or {}
            try:
                x = float(rect.get("x") or rect.get("left") or 0)
                y = float(rect.get("y") or rect.get("top") or 0)
                width = float(rect.get("width") or 0)
                height = float(rect.get("height") or 0)
            except Exception:
                return children
            order_raw = self._clean_text(styles.get("order", "")).lower()
            if order_raw in {"", "normal", "initial", "unset"}:
                order_value = 0.0
            else:
                try:
                    order_value = float(order_raw)
                except Exception:
                    order_value = 0.0
            sortable.append((idx, order_value, x, y, x + width, y + height, child))

        has_non_default_order = any(abs(item[1]) > 0.001 for item in sortable)
        if has_non_default_order:
            sortable.sort(key=lambda item: (item[1], item[3], item[2], item[0]))
            return [item[6] for item in sortable]

        if layout == "column":
            sortable.sort(key=lambda item: (item[3], item[2], item[0]))
            return [item[6] for item in sortable]

        top_span = max(item[3] for item in sortable) - min(item[3] for item in sortable)
        bottom_span = max(item[5] for item in sortable) - min(item[5] for item in sortable)
        rounded_columns = {int(round(item[2] / 24.0)) for item in sortable}
        repeated_x_columns = len(rounded_columns) < len(sortable)
        if top_span <= 24 or bottom_span <= 24:
            sortable.sort(key=lambda item: (item[2], item[3], item[0]))
        elif repeated_x_columns:
            sortable.sort(key=lambda item: (item[3], item[2], item[0]))
        else:
            sortable.sort(key=lambda item: (item[2], item[3], item[0]))
        return [item[6] for item in sortable]

    def _can_flatten_image_wrapper(self, node: Dict[str, Any]) -> bool:
        if not isinstance(node, dict) or node.get("bubble_type") != "Group":
            return False
        children = node.get("children", []) or []
        if len(children) != 1:
            return False
        inner = children[0]
        if not isinstance(inner, dict) or inner.get("bubble_type") != "Image":
            return False
        props = node.get("properties", {}) or {}
        bg = props.get("bg_color")
        if bg and not self._is_transparent_color(bg):
            return False
        if props.get("border_width"):
            return False
        if (self._to_int(props.get("border_radius"), 0) or 0) > 0:
            return False
        if props.get("nonant_alignment"):
            return False
        for margin_key in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            if (self._to_int(props.get(margin_key), 0) or 0) != 0:
                return False
        if props.get("zindex") is not None:
            return False
        for pad_key in ("padding_top", "padding_right", "padding_bottom", "padding_left"):
            if (self._to_int(props.get(pad_key), 0) or 0) != 0:
                return False
        inner_props = inner.get("properties", {}) or {}
        wrapper_w = self._to_int(props.get("width"), None)
        wrapper_h = self._to_int(props.get("height"), None)
        inner_w = self._to_int(inner_props.get("width"), None)
        inner_h = self._to_int(inner_props.get("height"), None)
        if (
            wrapper_w
            and inner_w
            and abs(int(wrapper_w) - int(inner_w)) > 2
        ) or (
            wrapper_h
            and inner_h
            and abs(int(wrapper_h) - int(inner_h)) > 2
        ):
            return False
        # Wrappers that only carry position/size around a single image are safe to flatten.
        return True

    def _tune_avatar_strip(self, group_node: Dict[str, Any]) -> None:
        children = group_node.get("children", []) or []
        avatar_indexes: List[int] = []
        for idx, child in enumerate(children):
            if not isinstance(child, dict) or child.get("bubble_type") != "Image":
                continue
            props = child.get("properties", {}) or {}
            width = self._to_int(props.get("width"), 0) or 0
            height = self._to_int(props.get("height"), 0) or 0
            radius = self._to_int(props.get("border_radius"), 0) or 0
            # Accept explicit circles and near-square compact avatars.
            if width <= 80 and height <= 80 and (radius >= 80 or abs(width - height) <= 6):
                avatar_indexes.append(idx)

        if len(avatar_indexes) < 3:
            return

        group_props = group_node.get("properties", {}) or {}
        # Avatar strips should always stay horizontal to preserve overlap.
        group_props["layout"] = "row"
        group_props.setdefault("container_horiz_alignment", "flex-end")
        group_node["properties"] = group_props

        for order, idx in enumerate(avatar_indexes):
            img = children[idx]
            props = img.get("properties", {}) or {}
            w = self._to_int(props.get("width"), 35) or 35
            h = self._to_int(props.get("height"), 35) or 35
            props["fixed_size"] = True
            props["use_aspect_ratio"] = True
            props["border_radius"] = 100
            props.setdefault("min_width_css", f"{w}px")
            props.setdefault("min_height_css", f"{h}px")
            current_margin = self._to_int(props.get("margin_left"), None)
            if order > 0 and (current_margin is None or current_margin >= 0):
                props["margin_left"] = -5
            img["properties"] = props

    def map_container(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        styles = self._merge_styles(element)
        rect = element.get("rect", {}) or {}
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        child_nodes = [ch for ch in (element.get("children", []) or []) if isinstance(ch, dict)]

        if (
            not child_nodes
            and not self._has_text_content(element)
            and not self._has_media_content(element)
            and not self._has_visual_box(styles)
            and not self._has_background_image_layer(element)
            and (self._to_int(rect.get("height"), None) or self._parse_dimension(styles.get("height")) or 0) <= 0
        ):
            return None

        # Collapse complex embedded players into a single placeholder box.
        if self._is_complex_player_node(element):
            visual = self._extract_visual_properties(
                styles,
                rect,
                node_type="group",
                intrinsic=element.get("intrinsic", {}) or {},
            )
            placeholder_bg = visual.get("bg_color")
            if self._is_transparent_color(placeholder_bg):
                placeholder_bg = None
            return {
                "bubble_type": "Group",
                "properties": {
                    "name": self._name_from_element(element, fallback="Video Placeholder"),
                    "layout": "column",
                    "width": visual.get("width") or 800,
                    "height": visual.get("height") or 450,
                    "bg_color": placeholder_bg or "#1f2937",
                    "border_radius": visual.get("border_radius") or 8,
                    "border_width": 1,
                    "border_color": "#374151",
                },
                "children": [],
            }

        if self._should_map_container_as_text(element, styles):
            return self.map_text(element, depth=depth)

        layout, layout_props = self._determine_bubble_layout(styles, element)
        if "row" in classes and layout != "row":
            layout = "row"
        inline_form = self._is_inline_form_container(element, styles)
        if inline_form:
            layout = "row"
        absolute_child_count = sum(
            1
            for child in child_nodes
            if self._is_absolutely_positioned(self._merge_styles(child))
        )
        substantive_flow_children = [
            child
            for child in child_nodes
            if not self._is_absolutely_positioned(self._merge_styles(child))
            and not self._is_non_visual_flow_spacer_element(child, layout)
        ]
        all_spacer_nodes = [
            child
            for child in child_nodes
            if self._is_non_visual_flow_spacer_element(child, layout)
        ]
        edge_padding_styles, edge_spacer_nodes = self._extract_edge_spacer_padding_from_children(child_nodes, layout)
        if (
            layout == "column"
            and absolute_child_count >= 1
            and len(substantive_flow_children) == 1
            and len(all_spacer_nodes) >= 2
        ):
            spacer_sizes = sorted(
                [
                    self._to_int((node.get("rect", {}) or {}).get("height"), None)
                    or self._parse_dimension(self._merge_styles(node).get("height"))
                    or 0
                    for node in all_spacer_nodes
                ]
            )
            inferred_edge = spacer_sizes[len(spacer_sizes) // 2] if spacer_sizes else 0
            if inferred_edge > 0:
                edge_padding_styles.setdefault("padding-top", f"{inferred_edge}px")
                edge_padding_styles.setdefault("padding-bottom", f"{inferred_edge}px")
        if (
            layout == "column"
            and absolute_child_count >= 1
            and len(substantive_flow_children) == 1
            and "padding-bottom" in edge_padding_styles
            and "padding-top" not in edge_padding_styles
        ):
            edge_padding_styles["padding-top"] = edge_padding_styles["padding-bottom"]
        if edge_padding_styles:
            element["_synthetic_padding"] = edge_padding_styles
            for spacer_node in edge_spacer_nodes:
                spacer_node["_skip_from_mapping"] = True
        if absolute_child_count >= 1 and edge_padding_styles:
            layout = "relative"
        elif self._should_use_relative_layout(element, styles, layout):
            layout = "relative"
        relative_layout_mode = "mosaic" if layout == "relative" and self._rect_mosaic_geometry(element) else None
        name = self._name_from_element(
            element,
            fallback=self._container_fallback_name(element, styles, depth, layout),
        )
        visual = self._extract_visual_properties(
            styles,
            rect,
            node_type="group",
            intrinsic=element.get("intrinsic", {}) or {},
        )
        gap = self._parse_gap(styles.get("gap") or styles.get("column-gap") or styles.get("row-gap"))
        explicit_spacers_present = any(self._is_non_visual_flow_spacer_element(child, layout) for child in child_nodes)
        if gap <= 0 and not explicit_spacers_present and not (inline_form or ("container" in classes and layout == "column")):
            inferred_margin_gap = self._infer_gap_from_margins(element, layout)
            if inferred_margin_gap > 0:
                gap = inferred_margin_gap
        if gap <= 0 and not explicit_spacers_present and layout == "row" and not self._is_bootstrap_container(classes, layout) and not inline_form:
            inferred_rect_gap = self._infer_gap_from_rects(element, layout)
            if inferred_rect_gap > 0:
                gap = inferred_rect_gap
        if inline_form and gap <= 0:
            gap = self._infer_inline_form_gap(element)
        if layout == "column" and gap > 80:
            gap = 0
        width = visual.get("width")
        max_width = self._parse_dimension(styles.get("max-width"))
        if width is None and max_width is not None:
            width = max_width
        if width is not None and max_width is not None and width > max_width:
            width = max_width
        explicit_max_width = self._parse_dimension(styles.get("max-width"))
        auto_leaf_width_constraint = False
        prefer_fit_width = False
        if visual.get("max_width_css") is None and explicit_max_width is None:
            auto_leaf_width_constraint = self._should_auto_constrain_leaf_width(element, layout, width)
            prefer_fit_width = self._should_prefer_fit_width_for_container(element, layout, width, classes)
            if auto_leaf_width_constraint and width is not None:
                visual["max_width_css"] = f"{int(width)}px"
        height = visual.get("height")
        bg_color = visual.get("bg_color") or self._class_color(classes, prefix="bg-")
        if self._is_transparent_color(bg_color):
            bg_color = None
            if self._has_background_image_layer(element):
                inferred = self._infer_background_fallback(element)
                bg_color = inferred or "#000000"
        pseudo = element.get("pseudo", {}) or {}
        pseudo_after = pseudo.get("after", {}) if isinstance(pseudo, dict) else {}
        pseudo_before = pseudo.get("before", {}) if isinstance(pseudo, dict) else {}
        pseudo_bg = None
        pseudo_src = None
        pseudo_bg_source = None
        if isinstance(pseudo_after, dict):
            pseudo_src = pseudo_after.get("background-image") or pseudo_after.get("background")
            pseudo_bg = self._extract_background_image_url(pseudo_src)
            if not pseudo_bg:
                pseudo_bg = self._extract_url_from_style_dict(pseudo_after)
            if pseudo_bg:
                pseudo_bg_source = "after"
        if not pseudo_bg and isinstance(pseudo_before, dict):
            pseudo_src = pseudo_before.get("background-image") or pseudo_before.get("background")
            pseudo_bg = self._extract_background_image_url(pseudo_src)
            if not pseudo_bg:
                pseudo_bg = self._extract_url_from_style_dict(pseudo_before)
            if pseudo_bg:
                pseudo_bg_source = "before"

        if (
            depth > 0
            and width is not None
            and width > 1400
            and max_width is None
            and not self._is_absolutely_positioned(styles)
        ):
            width = 1120

        if depth == 0 and width is None:
            width = 1120
        if depth > 0 and layout == "column" and width is None:
            width = 540
        if depth > 0 and layout == "row" and width is None:
            width = 1120
        if layout == "relative" and width is None:
            width = 1120 if depth <= 1 else 540
        if not self._should_keep_explicit_height(element, styles, depth):
            height = None

        has_structural_children = bool(child_nodes)
        has_single_text_child = (
            len(child_nodes) == 1
            and str((child_nodes[0] or {}).get("type", "")).lower() in {"text", "#text"}
        )
        radius_val = self._to_int(visual.get("border_radius"), 0) or 0
        is_compact_badge = bool(
            width is not None
            and height is not None
            and width <= 80
            and height <= 80
            and abs(width - height) <= 4
            and radius_val >= 80
            and has_single_text_child
            and not self._is_transparent_color(bg_color)
        )
        has_single_media_child = bool(
            len(child_nodes) == 1
            and str((child_nodes[0] or {}).get("type", "")).lower() not in {"text", "#text"}
        )
        is_compact_media_shell = bool(
            width is not None
            and height is not None
            and width <= 120
            and height <= 120
            and abs(width - height) <= 6
            and radius_val >= 80
            and has_single_media_child
            and not self._is_transparent_color(bg_color)
        )
        fit_height_value = bool(height is None)
        if is_compact_badge:
            fit_height_value = False
        elif is_compact_media_shell:
            fit_height_value = False
        elif (
            not fit_height_value
            and has_structural_children
            and layout in {"row", "column"}
            and not self._is_absolutely_positioned(styles)
        ):
            # Rendered snapshots often inject computed pixel heights; for flow
            # containers we should keep height content-driven by default.
            fit_height_value = True
        elif (
            not fit_height_value
            and height is not None
            and height <= 220
            and (
                radius_val > 0
                or not self._is_transparent_color(bg_color)
            )
        ):
            fit_height_value = True

        # Treat auto-centered blocks as alignment, not explicit margins.
        container_center = "container" in classes
        parent_rect = element.get("_parent_rect") or {}
        try:
            pw = float(parent_rect.get("width") or (float(parent_rect.get("right") or 0) - float(parent_rect.get("left") or 0)))
        except Exception:
            pw = 0
        try:
            wv = float(width or rect.get("width") or 0)
        except Exception:
            wv = 0
        ml = self._to_int(visual.get("margin_left"), 0) or 0
        mr = self._to_int(visual.get("margin_right"), 0) or 0
        auto_center_from_margins = False
        if ml > 0 and mr > 0 and pw > 0 and wv > 0:
            if abs((pw - wv) - (ml + mr)) <= 2 and abs(ml - mr) <= 2:
                visual["margin_left"] = 0
                visual["margin_right"] = 0
                container_center = True
                auto_center_from_margins = True
        if container_center:
            if visual.get("margin_left") or visual.get("margin_right"):
                visual["margin_left"] = 0
                visual["margin_right"] = 0

        props: Dict[str, Any] = {
            "name": name,
            "layout": layout,
            "flex_wrap": self._clean_text(styles.get("flex-wrap", "")).lower(),
            "gap": gap,
            "width": width,
            "height": height,
            "bg_color": bg_color,
            "fit_height": fit_height_value,
            "padding_top": visual.get("padding_top"),
            "padding_bottom": visual.get("padding_bottom"),
            "padding_left": visual.get("padding_left"),
            "padding_right": visual.get("padding_right"),
            "margin_top": visual.get("margin_top"),
            "margin_bottom": visual.get("margin_bottom"),
            "margin_left": visual.get("margin_left"),
            "margin_right": visual.get("margin_right"),
            "border_radius": visual.get("border_radius"),
            "border_roundness_top_left": visual.get("border_roundness_top_left"),
            "border_roundness_top_right": visual.get("border_roundness_top_right"),
            "border_roundness_bottom_right": visual.get("border_roundness_bottom_right"),
            "border_roundness_bottom_left": visual.get("border_roundness_bottom_left"),
            "border_width": visual.get("border_width"),
            "border_color": visual.get("border_color"),
            "border_style_top": visual.get("border_style_top"),
            "border_style_right": visual.get("border_style_right"),
            "border_style_bottom": visual.get("border_style_bottom"),
            "border_style_left": visual.get("border_style_left"),
            "border_width_top": visual.get("border_width_top"),
            "border_width_right": visual.get("border_width_right"),
            "border_width_bottom": visual.get("border_width_bottom"),
            "border_width_left": visual.get("border_width_left"),
            "border_color_top": visual.get("border_color_top"),
            "border_color_right": visual.get("border_color_right"),
            "border_color_bottom": visual.get("border_color_bottom"),
            "border_color_left": visual.get("border_color_left"),
            "shadow_style": visual.get("shadow_style"),
            "shadow_h": visual.get("shadow_h"),
            "shadow_v": visual.get("shadow_v"),
            "shadow_blur": visual.get("shadow_blur"),
            "shadow_spread": visual.get("shadow_spread"),
            "shadow_color": visual.get("shadow_color"),
            "opacity": self._normalize_opacity_percent(visual.get("opacity")),
            "min_width_css": visual.get("min_width_css"),
            "max_width_css": visual.get("max_width_css"),
            "min_height_css": visual.get("min_height_css"),
            "max_height_css": visual.get("max_height_css"),
            "__source_height": self._parse_dimension(styles.get("height")) or self._to_int(rect.get("height"), None),
        }
        if edge_padding_styles:
            if "padding-top" in edge_padding_styles:
                props["padding_top"] = max(self._to_int(props.get("padding_top"), 0) or 0, self._parse_dimension(edge_padding_styles.get("padding-top")) or 0)
            if "padding-right" in edge_padding_styles:
                props["padding_right"] = max(self._to_int(props.get("padding_right"), 0) or 0, self._parse_dimension(edge_padding_styles.get("padding-right")) or 0)
            if "padding-bottom" in edge_padding_styles:
                props["padding_bottom"] = max(self._to_int(props.get("padding_bottom"), 0) or 0, self._parse_dimension(edge_padding_styles.get("padding-bottom")) or 0)
            if "padding-left" in edge_padding_styles:
                props["padding_left"] = max(self._to_int(props.get("padding_left"), 0) or 0, self._parse_dimension(edge_padding_styles.get("padding-left")) or 0)
        side_border_values = [
            props.get("border_width_top"),
            props.get("border_width_right"),
            props.get("border_width_bottom"),
            props.get("border_width_left"),
            props.get("border_style_top"),
            props.get("border_style_right"),
            props.get("border_style_bottom"),
            props.get("border_style_left"),
            props.get("border_color_top"),
            props.get("border_color_right"),
            props.get("border_color_bottom"),
            props.get("border_color_left"),
        ]
        corner_values = [
            props.get("border_roundness_top_left"),
            props.get("border_roundness_top_right"),
            props.get("border_roundness_bottom_right"),
            props.get("border_roundness_bottom_left"),
        ]
        meaningful_side_borders = False
        for side in ("top", "right", "bottom", "left"):
            style_val = str(props.get(f"border_style_{side}") or "").strip().lower()
            width_val = self._to_int(props.get(f"border_width_{side}"), 0) or 0
            color_val = props.get(f"border_color_{side}")
            if width_val > 0 and style_val not in {"", "none"} and not self._is_transparent_color(color_val):
                meaningful_side_borders = True
                break
        if meaningful_side_borders:
            props["border_type"] = "independent"
        elif len({v for v in corner_values if v is not None}) > 1:
            props["border_type"] = "independent"
        if auto_center_from_margins:
            props["__auto_center"] = True
        if self._is_non_visual_flow_spacer_element(element, layout):
            if layout == "column" and height is not None:
                props["fit_height"] = False
                props["fixed_height"] = True
                props["min_height_css"] = f"{int(height)}px"
                props["max_height_css"] = f"{int(height)}px"
            elif layout == "row" and width is not None:
                props["fit_width"] = False
                props["fixed_width"] = True
                props["min_width_css"] = f"{int(width)}px"
                props["max_width_css"] = f"{int(width)}px"
        if layout == "relative":
            if props.get("height") is None:
                h = self._to_int(rect.get("height"), None)
                if h:
                    props["height"] = h
            if props.get("width") is None:
                w = self._to_int(rect.get("width"), None)
                if w:
                    props["width"] = w
            if props.get("height") is not None:
                props["fit_height"] = False
                props.setdefault("min_height_css", f"{int(props['height'])}px")
            if props.get("width") is not None:
                props.setdefault("min_width_css", f"{int(props['width'])}px")
            if relative_layout_mode:
                props["__relative_layout_mode"] = relative_layout_mode
        parent_inner_width, parent_inner_height = self._parent_inner_dimensions(element)
        raw_background = styles.get("background-image") or styles.get("background")
        native_gradient = self._extract_native_gradient_props(raw_background)
        inline_bg = self._extract_background_image_url(raw_background) if not native_gradient else None
        if pseudo_bg and (
            (pseudo_bg_source == "after" and isinstance(pseudo_after, dict) and self._should_use_pseudo_background(pseudo_after, classes))
            or (pseudo_bg_source == "before" and isinstance(pseudo_before, dict) and self._should_use_pseudo_background(pseudo_before, classes))
        ):
            props["background_style"] = "image"
            props["background_image"] = {"%x": "TextExpression", "%e": {"0": pseudo_bg}}
            if bg_color and not self._is_transparent_color(bg_color):
                props["background_color_if_empty_image"] = bg_color
        elif native_gradient:
            props.update(native_gradient)
        elif inline_bg:
            props["background_style"] = "image"
            props["background_image"] = {"%x": "TextExpression", "%e": {"0": inline_bg}}
            if bg_color and not self._is_transparent_color(bg_color):
                props["background_color_if_empty_image"] = bg_color
        props.update(layout_props)
        if inline_form:
            props["layout"] = "row"
            props["fit_height"] = True
            props["__inline_form"] = True
            # Remove large padding used for absolute button overlays.
            if (props.get("padding_right") or 0) >= 40:
                props["padding_right"] = 0
            if (props.get("padding_left") or 0) >= 40:
                props["padding_left"] = 0

        # Bubble align-to-parent overlays that are purely content containers
        # should size to content height instead of preserving rendered pixel
        # heights from the browser snapshot.
        if (
            has_structural_children
            and layout in {"row", "column"}
            and self._clean_text(props.get("nonant_alignment", ""))
            and not self._has_visual_shell_props(props)
        ):
            props["fit_height"] = True
        if (
            layout in {"row", "column"}
            and not self._has_visual_shell_props(props)
            and width is not None
            and parent_inner_width is not None
            and abs(width - parent_inner_width) <= 4
        ):
            props["fit_width"] = False
            props["width_unset"] = False

        if (
            layout == "column"
            and width is not None
            and parent_inner_width is not None
            and width > 0
            and float(width) / float(max(parent_inner_width, 1)) >= 0.25
        ):
            props["fit_width"] = False
            props["width_unset"] = False

        if any("button" == c or c.endswith("button") or "button" in c for c in classes):
            if self._has_descendant_tag(element, {"button"}):
                props["fit_width"] = True
                props["width_unset"] = True

        if prefer_fit_width and not self._has_visual_shell_props(props):
            visible_child_count = len([c for c in child_nodes if isinstance(c, dict)])
            has_box_spacing = any((self._to_int(props.get(k), 0) or 0) > 0 for k in (
                "padding_top",
                "padding_bottom",
                "padding_left",
                "padding_right",
                "border_width",
                "border_width_top",
                "border_width_right",
                "border_width_bottom",
                "border_width_left",
            ))
            if not (layout == "row" and visible_child_count > 1) and not has_box_spacing:
                props["fit_width"] = True
                props["width_unset"] = True
                if not auto_leaf_width_constraint:
                    props["max_width_css"] = None

        # For non-visual column stacks with explicit width, Bubble should size
        # the wrapper to its content instead of stretching across the parent.
        if (
            layout == "column"
            and width is not None
            and width > 0
            and width <= 480
            and not self._has_visual_shell_props(props)
            and child_nodes
            and not (parent_inner_width is not None and abs(width - parent_inner_width) <= 4)
        ):
            child_widths = []
            for child in child_nodes:
                child_rect = child.get("rect", {}) or {}
                child_width = self._to_int(child_rect.get("width"), None)
                if child_width is not None and child_width > 0:
                    child_widths.append(child_width)
            if child_widths and max(child_widths) <= width + 2:
                props["fit_width"] = True
                props["width_unset"] = False

        if layout == "row" and child_nodes and not self._has_visual_shell_props(props):
            visible_children = [c for c in child_nodes if isinstance(c, dict) and not c.get("_skip_from_mapping")]
            if len(visible_children) == 2:
                has_textual = any(self._element_has_textual_content(child) for child in visible_children)
                has_media = any(
                    str((child or {}).get("type", "")).lower() in {"img", "svg", "i"}
                    or self._has_media_content(child)
                    for child in visible_children
                )
                if has_textual and has_media:
                    props["fit_width"] = True
                    props["width_unset"] = False

        if "align-items-end" in classes:
            if props.get("layout") == "row":
                props["container_vert_alignment"] = "flex-end"
            else:
                props["container_horiz_alignment"] = "flex-end"
            props["__align_items_end"] = True

        if container_center:
            props["horiz_alignment"] = "center"
        if any(c in {"m-auto", "mx-auto"} for c in classes):
            props["horiz_alignment"] = "center"
            props["margin_left"] = 0
            props["margin_right"] = 0
            props["__auto_center"] = True

        text_align = self._clean_text(styles.get("text-align", "")).lower()
        if text_align in {"center"}:
            if self._element_has_textual_content(element):
                props["align"] = "center"
        elif text_align in {"right", "end"}:
            if self._element_has_textual_content(element):
                props["align"] = "right"
        elif text_align in {"left", "start"}:
            if self._element_has_textual_content(element):
                props["align"] = "left"
        if self._element_has_textual_content(element):
            if text_align in {"center"}:
                props["horiz_alignment"] = "center"
            elif text_align in {"right", "end"}:
                props["horiz_alignment"] = "flex-end"
            elif text_align in {"left", "start"}:
                props["horiz_alignment"] = "flex-start"

        # Center this container inside its parent when CSS indicates auto margins.
        margin_left = self._clean_text(styles.get("margin-left", "")).lower()
        margin_right = self._clean_text(styles.get("margin-right", "")).lower()
        align_self = self._clean_text(styles.get("align-self", "")).lower()
        if margin_left == "auto" and margin_right == "auto":
            props["horiz_alignment"] = "center"
        elif margin_left == "auto":
            props["horiz_alignment"] = "flex-end"
        elif margin_right == "auto":
            props["horiz_alignment"] = "flex-start"
        elif align_self == "center":
            props["horiz_alignment"] = "center"
        elif (
            self._parse_margin_value(styles.get("margin-left")) is not None
            and self._parse_margin_value(styles.get("margin-right")) is not None
            and self._parse_margin_value(styles.get("margin-left")) == self._parse_margin_value(styles.get("margin-right"))
            and (self._parse_margin_value(styles.get("margin-left")) or 0) > 0
        ):
            props["horiz_alignment"] = "center"
        elif align_self in {"flex-end", "end"}:
            props["horiz_alignment"] = "flex-end"
        elif align_self in {"flex-start", "start"}:
            props["horiz_alignment"] = "flex-start"

        parent_styles = element.get("_parent_styles") or {}
        parent_display = self._clean_text((parent_styles or {}).get("display", "")).lower()
        parent_direction = self._clean_text((parent_styles or {}).get("flex-direction", "")).lower() or "row"
        parent_align_items = self._clean_text((parent_styles or {}).get("align-items", "")).lower()
        if parent_display == "flex" and parent_direction == "row":
            if parent_align_items == "center":
                props["vert_alignment"] = "center"
            elif parent_align_items in {"flex-end", "end"}:
                props["vert_alignment"] = "flex-end"
            elif parent_align_items in {"flex-start", "start"}:
                props["vert_alignment"] = "flex-start"

        if is_compact_media_shell:
            props["fit_width"] = False
            props["fit_height"] = False
            props["fixed_width"] = True
            props["fixed_height"] = True
            props["single_width"] = True
            props["single_height"] = True
            props["min_width_css"] = f"{int(width)}px"
            props["min_height_css"] = f"{int(height)}px"

        progress_like = any("progress" in c for c in classes)
        progressbar_shell = any("progressbar" in c for c in classes)
        progress_fill = any(c.endswith("progress_in") or "progress_in" in c for c in classes)
        if progress_like:
            props["fit_width"] = False
            props["width_unset"] = False
            if width is not None and progress_fill:
                props["fixed_width"] = True
            else:
                props["fixed_width"] = False
            if height is not None and height <= 12:
                props["fit_height"] = False
                props["fixed_height"] = False
                props["min_height_css"] = f"{int(height)}px"
                props["height"] = None
            elif height is not None:
                props["fit_height"] = False
                props["fixed_height"] = True
            if progressbar_shell:
                props["fixed_width"] = False

        return {"bubble_type": "Group", "properties": props}

    def _apply_parent_positioning(
        self,
        element: Dict[str, Any],
        bubble_element: Optional[Dict[str, Any]],
        parent_layout: Optional[str],
    ) -> None:
        if not bubble_element:
            return
        if bubble_element.get("bubble_type") == "__fragment__":
            return
        if str(parent_layout or "").lower() != "relative":
            return
        props = bubble_element.get("properties")
        if not isinstance(props, dict):
            return
        styles = self._merge_styles(element)
        nonant = self._infer_nonant_alignment(styles)
        if nonant:
            props["nonant_alignment"] = nonant
        if props.get("zindex") is None:
            zindex = self._parse_z_index(styles.get("z-index"))
            if zindex is not None:
                props["zindex"] = zindex
        parent_styles = element.get("_parent_styles") or {}
        parent_pad_top = self._parse_dimension((parent_styles or {}).get("padding-top")) or 0
        parent_pad_right = self._parse_dimension((parent_styles or {}).get("padding-right")) or 0
        parent_pad_bottom = self._parse_dimension((parent_styles or {}).get("padding-bottom")) or 0
        parent_pad_left = self._parse_dimension((parent_styles or {}).get("padding-left")) or 0

        top_offset = self._parse_margin_value(styles.get("top"))
        right_offset = self._parse_margin_value(styles.get("right"))
        bottom_offset = self._parse_margin_value(styles.get("bottom"))
        left_offset = self._parse_margin_value(styles.get("left"))
        raw_has_top = top_offset is not None
        raw_has_right = right_offset is not None
        raw_has_bottom = bottom_offset is not None
        raw_has_left = left_offset is not None
        explicit_offsets = self._has_position_offsets(styles)
        has_offsets = explicit_offsets
        is_abs = self._is_absolutely_positioned(styles)
        transform_translates = self._has_translation_transform(styles)
        parent_relative_mode = self._clean_text(element.get("_parent_relative_mode", "")).lower()
        if parent_relative_mode == "mosaic":
            rect = element.get("rect") or {}
            parent_rect = element.get("_parent_rect") or {}
            try:
                parent_x = float(parent_rect.get("x") or parent_rect.get("left") or 0)
                parent_y = float(parent_rect.get("y") or parent_rect.get("top") or 0)
                parent_w = float(parent_rect.get("width") or 0)
                parent_h = float(parent_rect.get("height") or 0)
                child_x = float(rect.get("x") or rect.get("left") or 0)
                child_y = float(rect.get("y") or rect.get("top") or 0)
                child_w = float(rect.get("width") or props.get("width") or 0)
                child_h = float(rect.get("height") or props.get("height") or 0)
                dx = int(round(child_x - parent_x))
                dy = int(round(child_y - parent_y))
                remaining_right = int(round(parent_w - child_w - dx))
                remaining_bottom = int(round(parent_h - child_h - dy))
                nonant = self._nonant_from_rect_offsets(
                    dx,
                    dy,
                    remaining_right,
                    remaining_bottom,
                    int(round(child_w)),
                    int(round(child_h)),
                )
                props["nonant_alignment"] = nonant
                props["__mosaic_x"] = dx
                props["__mosaic_y"] = dy
                props["__mosaic_width"] = int(round(child_w))
                props["__mosaic_height"] = int(round(child_h))
                left_offset = dx
                right_offset = remaining_right
                top_offset = dy
                bottom_offset = remaining_bottom
                has_offsets = True
            except Exception:
                pass
        # Fallback to rect deltas when explicit offsets are missing.
        if isinstance(element.get("rect"), dict):
            rect = element.get("rect") or {}
            parent_rect = element.get("_parent_rect") or {}
            if isinstance(parent_rect, dict) and parent_rect:
                try:
                    parent_y = float(parent_rect.get("y") or parent_rect.get("top") or 0)
                    parent_x = float(parent_rect.get("x") or parent_rect.get("left") or 0)
                    child_y = float(rect.get("y") or rect.get("top") or 0)
                    child_x = float(rect.get("x") or rect.get("left") or 0)
                    dy = int(round(child_y - parent_y))
                    dx = int(round(child_x - parent_x))
                    if (is_abs or has_offsets) and (top_offset is None or left_offset is None):
                        if top_offset is None:
                            top_offset = dy
                        if left_offset is None:
                            left_offset = dx
                    elif not (is_abs or has_offsets):
                        # Only treat negative deltas as absolute-like offsets.
                        if dy < -2 and top_offset is None:
                            top_offset = dy
                            has_offsets = True
                        if dx < -2 and left_offset is None:
                            left_offset = dx
                            has_offsets = True
                except Exception:
                    pass

        if is_abs and transform_translates:
            final_offsets = self._final_rect_offsets(element)
            if final_offsets is not None:
                dx, dy, remaining_right, remaining_bottom, child_w, child_h = final_offsets
                nonant = self._nonant_from_rect_offsets(dx, dy, remaining_right, remaining_bottom, child_w, child_h)
                props["nonant_alignment"] = nonant
                x_axis = nonant[0]
                y_axis = nonant[1]
                left_offset = dx if x_axis in {"a", "b"} else None
                right_offset = remaining_right if x_axis in {"b", "c"} else None
                top_offset = dy if y_axis in {"a", "b"} else None
                bottom_offset = remaining_bottom if y_axis in {"b", "c"} else None
                has_offsets = True

        if transform_translates and nonant:
            x_axis = nonant[0]
            y_axis = nonant[1]
            if raw_has_left and raw_has_right and x_axis == "b":
                x_axis = "b"
                left_offset = None
                right_offset = None
            if raw_has_top and raw_has_bottom and y_axis == "b":
                y_axis = "b"
                top_offset = None
                bottom_offset = None
            nonant = f"{x_axis}{y_axis}"
            props["nonant_alignment"] = nonant

        def _discount(offset: Optional[int], pad: int) -> Optional[int]:
            if offset is None:
                return None
            if offset <= 0 or pad <= 0:
                return offset
            return offset - pad

        left_offset = _discount(left_offset, parent_pad_left)
        right_offset = _discount(right_offset, parent_pad_right)
        top_offset = _discount(top_offset, parent_pad_top)
        bottom_offset = _discount(bottom_offset, parent_pad_bottom)

        if not is_abs and not explicit_offsets and has_offsets:
            rect = element.get("rect") or {}
            rect_w = self._to_int(rect.get("width"), None) or 0
            rect_h = self._to_int(rect.get("height"), None) or 0
            if max(rect_w, rect_h) >= 240:
                top_offset = None
                right_offset = None
                bottom_offset = None
                left_offset = None
                has_offsets = False

        if not (is_abs or has_offsets):
            if top_offset is None and right_offset is None and bottom_offset is None and left_offset is None:
                return

        if (is_abs or has_offsets) and not nonant and (
            top_offset is not None
            or left_offset is not None
            or right_offset is not None
            or bottom_offset is not None
        ):
            nonant = "aa"
            props["nonant_alignment"] = nonant

        if nonant:
            x_axis = nonant[0]
            y_axis = nonant[1]
            rect = element.get("rect") or {}
            parent_rect = element.get("_parent_rect") or {}
            child_width = (
                self._to_int(rect.get("width"), None)
                or self._to_int(props.get("width"), None)
                or self._parse_dimension(styles.get("width"))
            )
            child_height = (
                self._to_int(rect.get("height"), None)
                or self._to_int(props.get("height"), None)
                or self._parse_dimension(styles.get("height"))
            )
            parent_width = self._to_int(parent_rect.get("width"), None)
            parent_height = self._to_int(parent_rect.get("height"), None)
            parent_inner_width = None
            parent_inner_height = None
            if parent_width is not None:
                parent_inner_width = max(parent_width - parent_pad_left - parent_pad_right, 0)
            if parent_height is not None:
                parent_inner_height = max(parent_height - parent_pad_top - parent_pad_bottom, 0)
            centered_x = bool(
                x_axis == "b"
                and left_offset is not None
                and right_offset is not None
                and abs(left_offset - right_offset) <= 4
            )
            centered_y = bool(
                y_axis == "b"
                and top_offset is not None
                and bottom_offset is not None
                and abs(top_offset - bottom_offset) <= 4
            )
            tx = 0.0
            ty = 0.0
            if transform_translates:
                tx, ty = self._extract_transform_translation(styles)
                if not centered_x and x_axis == "b" and child_width is not None:
                    if abs(tx + (float(child_width) / 2.0)) <= 4:
                        centered_x = True
                if not centered_y and y_axis == "b" and child_height is not None:
                    if abs(ty + (float(child_height) / 2.0)) <= 4:
                        centered_y = True
            if transform_translates and (not centered_x or not centered_y):
                if parent_width is None:
                    parent_width = self._parse_dimension((parent_styles or {}).get("width"))
                if parent_height is None:
                    parent_height = self._parse_dimension((parent_styles or {}).get("height"))
                if parent_width is None and left_offset is not None and right_offset is not None and child_width is not None:
                    parent_width = int(round(left_offset + child_width + right_offset))
                if parent_height is None and top_offset is not None and bottom_offset is not None and child_height is not None:
                    parent_height = int(round(top_offset + child_height + bottom_offset))
                if not centered_x and x_axis == "b" and left_offset is not None and child_width is not None and parent_width is not None:
                    effective_left = left_offset + int(round(tx))
                    effective_right = int(round(parent_width - child_width - effective_left))
                    if abs(effective_left - effective_right) <= 4:
                        centered_x = True
                if not centered_y and y_axis == "b" and top_offset is not None and child_height is not None and parent_height is not None:
                    effective_top = top_offset + int(round(ty))
                    effective_bottom = int(round(parent_height - child_height - effective_top))
                    if abs(effective_top - effective_bottom) <= 4:
                        centered_y = True
            if centered_x:
                props["fit_width"] = False
                props["width_unset"] = False
                props["margin_left"] = 0
                props["margin_right"] = 0
                left_offset = None
                right_offset = None
            if centered_y:
                props["margin_top"] = 0
                props["margin_bottom"] = 0
                top_offset = None
                bottom_offset = None
            if x_axis == "a" and left_offset is not None and (props.get("margin_left") is None or props.get("margin_left") == 0):
                props["margin_left"] = left_offset
            elif x_axis == "c" and right_offset is not None and (props.get("margin_right") is None or props.get("margin_right") == 0):
                props["margin_right"] = right_offset
            elif x_axis == "b":
                if left_offset is not None and (props.get("margin_left") is None or props.get("margin_left") == 0):
                    props["margin_left"] = left_offset
                if right_offset is not None and (props.get("margin_right") is None or props.get("margin_right") == 0):
                    props["margin_right"] = right_offset

            if y_axis == "a" and top_offset is not None and (props.get("margin_top") is None or props.get("margin_top") == 0):
                props["margin_top"] = top_offset
            elif y_axis == "c" and bottom_offset is not None and (props.get("margin_bottom") is None or props.get("margin_bottom") == 0):
                props["margin_bottom"] = bottom_offset
            elif y_axis == "b":
                if top_offset is not None and (props.get("margin_top") is None or props.get("margin_top") == 0):
                    props["margin_top"] = top_offset
                if bottom_offset is not None and (props.get("margin_bottom") is None or props.get("margin_bottom") == 0):
                    props["margin_bottom"] = bottom_offset

    def map_heading(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        content = self._clean_text(element.get("text", ""))
        if not content:
            if self._has_class_token(element, "text-anime") or self._has_class_token(element, "split-line"):
                content = self._extract_split_text(element)
            if not content:
                content = self._deep_text(element)
        if not content or self._is_noise_text(content):
            return None

        node_type = str(element.get("type", "")).lower()
        styles = self._merge_styles(element)
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        text_style_source = self._derive_text_style_source(element, styles)

        size = self.HEADING_SIZE.get(node_type, 24)
        explicit = self._parse_dimension(text_style_source.get("font-size")) or self._parse_dimension(styles.get("font-size"))
        if explicit:
            size = explicit

        weight_val = text_style_source.get("font-weight") or styles.get("font-weight")
        font_weight = str(self._font_weight_num(weight_val))
        font_style = self._clean_text(text_style_source.get("font-style") or styles.get("font-style") or "").lower()
        italic = font_style in {"italic", "oblique"}
        text_decoration = self._clean_text(
            text_style_source.get("text-decoration-line")
            or text_style_source.get("text-decoration")
            or styles.get("text-decoration-line")
            or styles.get("text-decoration")
            or ""
        ).lower()
        underline = "underline" in text_decoration
        font_family = self._parse_font_family(text_style_source) or self._parse_font_family(styles)
        letter_spacing = self._parse_letter_spacing(
            text_style_source.get("letter-spacing") or styles.get("letter-spacing"),
            size,
        )

        color = (
            self._text_color(text_style_source.get("color"), text_style_source)
            or self._text_color(styles.get("color"), styles)
            or self._class_color(classes, prefix="text-")
            or "#111827"
        )
        rich_content = self._build_rich_text_content(element, fallback_text=content)
        if rich_content:
            content = rich_content
        else:
            content = self._compose_heading_rich_text(element, content, color)
        content = self._normalize_heading_content(content)
        transform = text_style_source.get("text-transform") or styles.get("text-transform")
        if transform:
            content = self._apply_text_transform(content, transform)
        line_height = self._parse_line_height(
            text_style_source.get("line-height") or styles.get("line-height"),
            size,
            heading=True,
        )
        align = self._align_from_styles(styles)
        width_hint = self._parse_dimension(styles.get("width"))
        margin_bottom = self._parse_margin_value(styles.get("margin-bottom"))
        margin_left = self._parse_margin_value(styles.get("margin-left"))
        padding_top = self._parse_dimension(styles.get("padding-top"))
        padding_bottom = self._parse_dimension(styles.get("padding-bottom"))
        padding_left = self._parse_dimension(styles.get("padding-left"))
        padding_right = self._parse_dimension(styles.get("padding-right"))
        props: Dict[str, Any] = {
            "bubble_type": "Text",
            "properties": {
                "name": self._name_from_element(element, fallback="Heading"),
                "content": content,
                "font_size": size,
                "font_weight": font_weight,
                "color": color,
                "font_color": color,
                "line_height": line_height,
                "align": align,
                "font_alignment": align,
                "width": width_hint or self._text_width_hint(content, depth=depth, heading=True),
                "margin_top": self._parse_margin_value(styles.get("margin-top")),
                "margin_bottom": margin_bottom,
                "margin_left": margin_left,
                "margin_right": self._parse_margin_value(styles.get("margin-right")),
                "padding_top": padding_top,
                "padding_bottom": padding_bottom,
                "padding_left": padding_left,
                "padding_right": padding_right,
                "opacity": self._normalize_opacity_percent(text_style_source.get("opacity") or styles.get("opacity")),
            },
        }
        if font_family:
            props["properties"]["font_family"] = font_family
        if letter_spacing is not None:
            props["properties"]["letter_spacing"] = letter_spacing
        if italic:
            props["properties"]["italic"] = True
        if underline:
            props["properties"]["underline"] = True
        if self._font_weight_num(weight_val) >= 600:
            props["properties"]["bold"] = True
        return props

    def map_text(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        content = self._clean_text(element.get("text", ""))
        if not content or self._is_noise_text(content):
            return None

        styles = self._merge_styles(element)
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        text_style_source = self._derive_text_style_source(element, styles)
        rich_content = self._build_rich_text_content(element, fallback_text=content)
        if rich_content:
            content = rich_content

        size = self._parse_dimension(text_style_source.get("font-size")) or self._parse_dimension(styles.get("font-size")) or 16
        weight_val = text_style_source.get("font-weight") or styles.get("font-weight") or "400"
        weight = str(self._font_weight_num(weight_val))
        font_style = self._clean_text(text_style_source.get("font-style") or styles.get("font-style") or "").lower()
        italic = font_style in {"italic", "oblique"}
        text_decoration = self._clean_text(
            text_style_source.get("text-decoration-line")
            or text_style_source.get("text-decoration")
            or styles.get("text-decoration-line")
            or styles.get("text-decoration", "")
        ).lower()
        underline = "underline" in text_decoration
        font_family = self._parse_font_family(text_style_source) or self._parse_font_family(styles)
        letter_spacing = self._parse_letter_spacing(
            text_style_source.get("letter-spacing") or styles.get("letter-spacing"),
            size,
        )
        color = (
            self._text_color(text_style_source.get("color"), text_style_source)
            or self._text_color(styles.get("color"), styles)
            or self._class_color(classes, prefix="text-")
            or "#1f2937"
        )
        transform = text_style_source.get("text-transform") or styles.get("text-transform")
        if transform:
            content = self._apply_text_transform(content, transform)
        line_height = self._parse_line_height(
            text_style_source.get("line-height") or styles.get("line-height"),
            size,
            heading=False,
        )
        align = self._align_from_styles(styles)
        parent_styles = element.get("_parent_styles") or {}
        parent_display = self._clean_text((parent_styles or {}).get("display", "")).lower()
        parent_flex_direction = self._clean_text((parent_styles or {}).get("flex-direction", "")).lower()
        fit_width = parent_display in {"flex", "inline-flex"} and parent_flex_direction in {"row", "row-reverse"}

        width_hint = self._parse_dimension(styles.get("width")) or self._to_int((element.get("rect", {}) or {}).get("width"), None)
        margin_bottom = self._parse_margin_value(styles.get("margin-bottom"))
        margin_left = self._parse_margin_value(styles.get("margin-left"))
        padding_top = self._parse_dimension(styles.get("padding-top"))
        padding_bottom = self._parse_dimension(styles.get("padding-bottom"))
        padding_left = self._parse_dimension(styles.get("padding-left"))
        padding_right = self._parse_dimension(styles.get("padding-right"))
        props: Dict[str, Any] = {
            "bubble_type": "Text",
            "properties": {
                "name": self._name_from_element(element, fallback="Text"),
                "content": content,
                "font_size": size,
                "font_weight": weight,
                "color": color,
                "font_color": color,
                "line_height": line_height,
                "align": align,
                "font_alignment": align,
                "width": width_hint or self._text_width_hint(content, depth=depth, heading=False),
                "fit_width": fit_width,
                "margin_top": self._parse_margin_value(styles.get("margin-top")),
                "margin_bottom": margin_bottom,
                "margin_left": margin_left,
                "margin_right": self._parse_margin_value(styles.get("margin-right")),
                "padding_top": padding_top,
                "padding_bottom": padding_bottom,
                "padding_left": padding_left,
                "padding_right": padding_right,
                "opacity": self._normalize_opacity_percent(text_style_source.get("opacity") or styles.get("opacity")),
            },
        }
        if font_family:
            props["properties"]["font_family"] = font_family
        if letter_spacing is not None:
            props["properties"]["letter_spacing"] = letter_spacing
        if italic:
            props["properties"]["italic"] = True
        if underline:
            props["properties"]["underline"] = True
        if self._font_weight_num(weight_val) >= 600:
            props["properties"]["bold"] = True
        return props

    def map_button(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        label = self._clean_text(element.get("text", "")) or self._deep_text(element)
        label = self._clean_text(label)
        icon_spec = self._infer_button_icon(element)
        if label and self._is_noise_text(label):
            return None
        if not label and not icon_spec:
            return None

        styles = self._merge_styles(element)
        rect = element.get("rect", {}) or {}
        visual = self._extract_visual_properties(
            styles,
            rect,
            node_type="button",
            intrinsic=element.get("intrinsic", {}) or {},
        )
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        class_blob = " ".join(classes)
        text_style_source = self._derive_text_style_source(element, styles)
        border_radius = visual.get("border_radius") or 10
        border_width = visual.get("border_width")
        border_color = visual.get("border_color")
        weight_val = text_style_source.get("font-weight") or styles.get("font-weight") or "600"
        font_weight = str(self._font_weight_num(weight_val))
        font_size = self._parse_dimension(text_style_source.get("font-size")) or self._parse_dimension(styles.get("font-size")) or 16
        font_family = self._parse_font_family(text_style_source) or self._parse_font_family(styles)
        letter_spacing = self._parse_letter_spacing(
            text_style_source.get("letter-spacing") or styles.get("letter-spacing"),
            font_size,
        )
        font_style = self._clean_text(text_style_source.get("font-style") or styles.get("font-style") or "").lower()
        italic = font_style in {"italic", "oblique"}
        text_decoration = self._clean_text(
            text_style_source.get("text-decoration-line")
            or text_style_source.get("text-decoration")
            or styles.get("text-decoration-line")
            or styles.get("text-decoration")
            or ""
        ).lower()
        underline = "underline" in text_decoration
        text_color = (
            self._text_color(text_style_source.get("color"), text_style_source)
            or self._text_color(styles.get("color"), styles)
            or self._class_color(classes, prefix="text-")
            or "#ffffff"
        )
        raw_width = visual.get("width") or 240
        min_w = self._parse_dimension(styles.get("min-width"))
        max_w = self._parse_dimension(styles.get("max-width"))
        if max_w is not None and raw_width > max_w:
            raw_width = max_w
        if min_w is not None and raw_width < min_w:
            raw_width = min_w
        if raw_width > 900 and min_w is not None and min_w <= 600:
            raw_width = max(min_w, 440)
        raw_height = visual.get("height") or 56
        display = self._clean_text(styles.get("display", "")).lower()
        fit_width = display.startswith("inline")
        if any(tok in class_blob for tok in ("theme-btn", "theme-btn1", "theme-btn2", "btn", "button")):
            fit_width = True
        margin_l_raw = self._clean_text(styles.get("margin-left", "")).lower()
        margin_r_raw = self._clean_text(styles.get("margin-right", "")).lower()
        align_self = self._clean_text(styles.get("align-self", "")).lower()
        horiz_alignment: Optional[str] = None
        if margin_l_raw == "auto" and margin_r_raw == "auto":
            horiz_alignment = "center"
        elif margin_l_raw == "auto":
            horiz_alignment = "flex-end"
        elif margin_r_raw == "auto":
            horiz_alignment = "flex-start"
        elif align_self == "center":
            horiz_alignment = "center"
        elif align_self in {"flex-end", "end", "right"}:
            horiz_alignment = "flex-end"
        elif align_self in {"flex-start", "start", "left"}:
            horiz_alignment = "flex-start"
        if horiz_alignment is None:
            text_align = self._clean_text(styles.get("text-align", "")).lower()
            if text_align in {"right", "end"}:
                horiz_alignment = "flex-end"
            elif text_align in {"center"}:
                horiz_alignment = "center"
            elif text_align in {"left", "start"}:
                horiz_alignment = "flex-start"

        transform = text_style_source.get("text-transform") or styles.get("text-transform")
        if transform:
            label = self._apply_text_transform(label, transform)

        button_props = {
            "bubble_type": "Button",
            "properties": {
                "name": self._name_from_element(element, fallback=label[:24] or "Button"),
                "label": label or "",
                "width": raw_width,
                "height": raw_height,
                "fit_width": fit_width,
                "bg_color": (
                    visual.get("bg_color")
                    or self._class_color(classes, prefix="bg-")
                    or "#ff5b2e"
                ),
                "text_color": text_color,
                "font_color": text_color,
                "font_size": font_size,
                "font_weight": font_weight,
                "font_family": font_family,
                "letter_spacing": letter_spacing,
                "bold": True if self._font_weight_num(weight_val) >= 600 else None,
                "italic": True if italic else None,
                "underline": True if underline else None,
                "border_radius": border_radius,
                "border_roundness_top_left": visual.get("border_roundness_top_left"),
                "border_roundness_top_right": visual.get("border_roundness_top_right"),
                "border_roundness_bottom_right": visual.get("border_roundness_bottom_right"),
                "border_roundness_bottom_left": visual.get("border_roundness_bottom_left"),
                "border_width": border_width,
                "border_color": border_color,
                "min_width_css": f"{int(min_w)}px" if min_w is not None and min_w > 0 else None,
                "max_width_css": f"{int(max_w)}px" if max_w is not None and max_w > 0 else None,
                "padding_top": visual.get("padding_top"),
                "padding_bottom": visual.get("padding_bottom"),
                "padding_left": visual.get("padding_left"),
                "padding_right": visual.get("padding_right"),
                "margin_top": self._parse_margin_value(styles.get("margin-top")),
                "margin_bottom": self._parse_margin_value(styles.get("margin-bottom")),
                "margin_left": self._parse_margin_value(styles.get("margin-left")),
                "margin_right": self._parse_margin_value(styles.get("margin-right")),
                "horiz_alignment": horiz_alignment,
                "opacity": self._normalize_opacity_percent(visual.get("opacity")),
                "zindex": visual.get("zindex"),
            },
        }
        if icon_spec:
            props = button_props["properties"]
            props["icon"] = icon_spec.get("icon")
            props["button_type"] = icon_spec.get("button_type")
            if icon_spec.get("icon_size") is not None:
                props["icon_size"] = icon_spec.get("icon_size")
            if icon_spec.get("icon_color"):
                props["icon_color"] = icon_spec.get("icon_color")
            if icon_spec.get("icon_placement"):
                props["icon_placement"] = icon_spec.get("icon_placement")
            if icon_spec.get("button_gap") is not None:
                props["button_gap"] = icon_spec.get("button_gap")
            if icon_spec.get("button_type") == "icon":
                props["fit_width"] = False
                props["single_width"] = True
                props["single_height"] = True
                if raw_width:
                    props["min_width_css"] = f"{int(raw_width)}px"
                    props["max_width_css"] = f"{int(raw_width)}px"
                if raw_height:
                    props["min_height_css"] = f"{int(raw_height)}px"
                    props["max_height_css"] = f"{int(raw_height)}px"
        return button_props

    def map_link_or_button(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        styles = self._merge_styles(element)
        text = self._clean_text(element.get("text", "")) or self._deep_text(element)
        has_media_descendants = (
            self._has_media_content(element)
            or self._has_descendant_tag(element, {"svg", "img", "i"})
            or self._has_icon_descendant(element)
        )
        has_rich_children = bool([c for c in (element.get("children", []) or []) if isinstance(c, dict)])
        has_visual_link_shell = self._has_visual_box(styles) or self._is_absolutely_positioned(styles)
        if not text:
            icon_spec = self._infer_button_icon(element)
            if icon_spec and (
                has_visual_link_shell
                or has_media_descendants
            ):
                return self.map_button(element, depth=depth)
            # Preserve icon-like links/buttons (e.g. square social/icon chips).
            if (
                has_visual_link_shell
                or has_media_descendants
            ):
                node = self.map_container(element, depth=depth)
                if node and isinstance(node.get("properties"), dict):
                    props = node["properties"]
                    w = self._parse_dimension(styles.get("width")) or self._to_int(props.get("width"), None)
                    h = self._parse_dimension(styles.get("height")) or self._to_int(props.get("height"), None)
                    lh = self._parse_dimension(styles.get("line-height"))
                    if (w is None or h is None) and lh:
                        if w is None:
                            w = lh
                        if h is None:
                            h = lh
                    if w and h:
                        props["width"] = w
                        props["height"] = h
                        props["min_width_css"] = f"{w}px"
                        props["min_height_css"] = f"{h}px"
                        props["max_width_css"] = f"{w}px"
                        props["max_height_css"] = f"{h}px"
                        props["single_width"] = True
                        props["single_height"] = True
                        # Ensure icon buttons stay centered inside their box.
                        props["fit_width"] = True
                        props["fit_height"] = True
                        props["container_horiz_alignment"] = "center"
                        props["container_vert_alignment"] = "center"
                        props.setdefault("align", "center")
                    if self._has_class_token(element, "magnifying-glass"):
                        mr = self._to_int(props.get("margin_right"), 0) or 0
                        if mr <= 0:
                            props["margin_right"] = 36
                        props["vert_alignment"] = "center"
                    node["properties"] = props
                return node
            return None
        if self._is_noise_text(text):
            return None

        # Rich content links should stay containers so media layers, overlays,
        # and nested text survive the conversion. Treat only simple inline links
        # as plain text.
        if has_media_descendants or (has_rich_children and has_visual_link_shell):
            return self.map_container(element, depth=depth)

        class_blob = " ".join(classes)
        button_tokens = ("btn", "button", "cta", "theme-btn", "theme-btn1", "theme-btn2", "btn-", "button-")
        button_like = any(tok in class_blob for tok in button_tokens)
        bg_color = styles.get("background-color")
        has_bg = bool(bg_color and not self._is_transparent_color(bg_color))
        border_width = self._parse_dimension(styles.get("border-width")) or 0
        has_border = border_width and border_width > 0
        border_radius = self._parse_dimension(styles.get("border-radius")) or 0
        pad_vals = [
            self._parse_dimension(styles.get("padding-top")),
            self._parse_dimension(styles.get("padding-right")),
            self._parse_dimension(styles.get("padding-bottom")),
            self._parse_dimension(styles.get("padding-left")),
        ]
        has_padding = any((p or 0) >= 8 for p in pad_vals)
        if has_bg or has_border:
            button_like = True
        if border_radius >= 8 and has_padding and (has_bg or has_border):
            button_like = True
        if button_like:
            return self.map_button(element, depth=depth)
        return self.map_text(element, depth=depth)

    def map_input(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        attrs = element.get("attributes", {}) or {}
        placeholder = self._clean_text(attrs.get("placeholder", "")) or "Type here..."
        styles = self._merge_styles(element)
        rect = element.get("rect", {}) or {}
        visual = self._extract_visual_properties(
            styles,
            rect,
            node_type="input",
            intrinsic=element.get("intrinsic", {}) or {},
        )
        width = visual.get("width")
        height = visual.get("height")
        font_color = self._text_color(styles.get("color"), styles)
        font_size = self._parse_dimension(styles.get("font-size"))
        border_style = self._clean_text(styles.get("border-style", "")).lower()
        if not border_style or border_style in {"none", "hidden"}:
            border_style = None
        border_width = visual.get("border_width") or 0
        if border_style is None and border_width and border_width > 0:
            border_style = "solid"
        single_height = True if height else None
        single_width = True if (width and (visual.get("border_radius") or 0) >= 40) else None
        return {
            "bubble_type": "Input",
            "properties": {
                "name": self._name_from_element(element, fallback="Input"),
                "placeholder": placeholder,
                "content_format": "text",
                "width": width,
                "height": height,
                "single_width": single_width,
                "single_height": single_height,
                "min_width_css": visual.get("min_width_css"),
                "max_width_css": visual.get("max_width_css"),
                "min_height_css": visual.get("min_height_css"),
                "max_height_css": visual.get("max_height_css"),
                "margin_top": visual.get("margin_top"),
                "margin_bottom": visual.get("margin_bottom"),
                "margin_left": visual.get("margin_left"),
                "margin_right": visual.get("margin_right"),
                "padding_top": visual.get("padding_top"),
                "padding_bottom": visual.get("padding_bottom"),
                "padding_left": visual.get("padding_left"),
                "padding_right": visual.get("padding_right"),
                "border_radius": visual.get("border_radius"),
                "border_width": visual.get("border_width"),
                "border_style": border_style,
                "border_color": visual.get("border_color"),
                "bg_color": visual.get("bg_color"),
                "font_color": font_color,
                "text_color": font_color,
                "font_size": font_size,
            },
        }

    def map_image(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        attrs = element.get("attributes", {}) or {}
        node_type = str(element.get("type", "")).lower()
        styles = self._merge_styles(element)
        rect = element.get("rect", {}) or {}
        intrinsic = element.get("intrinsic", {}) or {}
        visual = self._extract_visual_properties(
            styles,
            rect,
            node_type="image",
            intrinsic=intrinsic,
        )
        src = (
            element.get("media_url")
            or attrs.get("src")
            or attrs.get("data-src")
            or attrs.get("data-lottie-url")
        )
        src = self._clean_text(str(src or ""))
        if src:
            src = self._absolutize_url(src) or src
        if node_type != "img":
            if self._is_complex_player_node(element):
                return {
                    "bubble_type": "Group",
                    "properties": {
                        "name": self._name_from_element(element, fallback="Video Placeholder"),
                        "layout": "column",
                        "width": visual.get("width") or 800,
                        "height": visual.get("height") or 450,
                        "bg_color": "#1f2937",
                    },
                }
            if src and not re.search(r"\.(png|jpe?g|webp|gif|svg|avif)(?:[?#]|$)", src, re.IGNORECASE):
                return None
        rect_w = self._to_int(rect.get("width"), None)
        rect_h = self._to_int(rect.get("height"), None)
        attr_w = self._parse_dimension(attrs.get("width"))
        attr_h = self._parse_dimension(attrs.get("height"))
        intrinsic_w = self._to_int(intrinsic.get("width"), None)
        intrinsic_h = self._to_int(intrinsic.get("height"), None)
        width = visual.get("width") or rect_w or attr_w or intrinsic_w
        height = visual.get("height") or rect_h or attr_h or intrinsic_h
        if width is None and height is None:
            width, height = 200, 120
        elif width is None and height is not None:
            if intrinsic_w and intrinsic_h and intrinsic_h > 0:
                width = int(round((intrinsic_w / float(intrinsic_h)) * float(height)))
            else:
                width = max(int(round(float(height) * 1.6)), 60)
        elif height is None and width is not None:
            if intrinsic_w and intrinsic_h and intrinsic_w > 0:
                height = int(round((intrinsic_h / float(intrinsic_w)) * float(width)))
            else:
                height = max(int(round(float(width) / 1.6)), 40)
        if rect_w and width and width > rect_w * 2:
            width = rect_w
        if rect_h and height and height > rect_h * 2:
            height = rect_h
        if not src:
            if self._is_complex_player_node(element):
                return {
                    "bubble_type": "Group",
                    "properties": {
                        "name": self._name_from_element(element, fallback="Video Placeholder"),
                        "layout": "column",
                        "width": width,
                        "height": height,
                        "bg_color": "#1f2937",
                    },
                }
            return None
        # Keep explicit geometry from computed styles/rect when available.
        explicit_box = bool(width and height and width > 0 and height > 0)
        fixed_size = bool(visual.get("fixed_size"))
        if not fixed_size and width and height and width <= 120 and height <= 120:
            fixed_size = True
        if not fixed_size and width and height:
            if max(width, height) <= 200:
                fixed_size = True
            elif height <= 80 and width / float(max(height, 1)) >= 2.2:
                fixed_size = True
        border_radius = visual.get("border_radius")
        if border_radius and border_radius >= 40:
            fixed_size = True
        classes = self._classes(attrs)
        is_quote = any("quote" in c for c in classes) or ("quote" in src.lower())
        is_svg_asset = src.lower().endswith(".svg") or src.lower().startswith("data:image/svg")
        if any("avatar" in c for c in classes):
            fixed_size = True
            if border_radius is None:
                border_radius = 100
        if is_quote:
            fixed_size = True
        if is_svg_asset and not any("avatar" in c for c in classes):
            border_radius = None
        css_filter = self._extract_css_filter(styles)
        margin_left = visual.get("margin_left")
        horiz_alignment: Optional[str] = None
        margin_l_raw = self._clean_text(styles.get("margin-left", "")).lower()
        margin_r_raw = self._clean_text(styles.get("margin-right", "")).lower()
        align_self = self._clean_text(styles.get("align-self", "")).lower()
        if margin_l_raw == "auto" and margin_r_raw == "auto":
            horiz_alignment = "center"
        elif margin_l_raw == "auto":
            horiz_alignment = "flex-end"
        elif margin_r_raw == "auto":
            horiz_alignment = "flex-start"
        elif align_self == "center":
            horiz_alignment = "center"
        elif align_self in {"flex-end", "end", "right"}:
            horiz_alignment = "flex-end"
        elif align_self in {"flex-start", "start", "left"}:
            horiz_alignment = "flex-start"
        if horiz_alignment is None:
            horiz_alignment = self._parent_horiz_alignment_from_styles(element)
        if horiz_alignment is None:
            horiz_alignment = self._geometry_horiz_alignment(element, width, default=None)
        parent_rect = element.get("_parent_rect") or {}
        parent_styles = element.get("_parent_styles") or {}
        vert_alignment: Optional[str] = None
        vertical_align = self._clean_text(styles.get("vertical-align", "")).lower()
        if vertical_align in {"middle", "center"}:
            vert_alignment = "center"
        parent_display = self._clean_text((parent_styles or {}).get("display", "")).lower()
        parent_direction = self._clean_text((parent_styles or {}).get("flex-direction", "")).lower() or "row"
        parent_align_items = self._clean_text((parent_styles or {}).get("align-items", "")).lower()
        if vert_alignment is None and parent_display == "flex" and parent_direction == "row":
            if parent_align_items == "center":
                vert_alignment = "center"
            elif parent_align_items in {"flex-end", "end"}:
                vert_alignment = "flex-end"
            elif parent_align_items in {"flex-start", "start"}:
                vert_alignment = "flex-start"
        min_width_css = visual.get("min_width_css") if fixed_size else None
        min_height_css = visual.get("min_height_css") if fixed_size else None
        max_width_css = None if is_svg_asset else (visual.get("max_width_css") if fixed_size else None)
        max_height_css = None if is_svg_asset else (visual.get("max_height_css") if fixed_size else None)
        parent_width = self._to_int(parent_rect.get("width"), None)
        if parent_width is None:
            parent_width = self._parse_dimension((parent_styles or {}).get("width"))
        if (
            max_width_css is None
            and width is not None
            and width > 0
            and parent_width is not None
            and parent_width > width + 4
        ):
            max_width_css = f"{int(width)}px"
        image_props = {
            "bubble_type": "Image",
            "properties": {
                "name": self._name_from_element(element, fallback="Image"),
                "image_url": src,
                "width": width,
                "height": height,
                "alt_text": self._clean_text(attrs.get("alt", "")),
                "fixed_size": fixed_size,
                "border_radius": border_radius,
                "border_roundness_top_left": visual.get("border_roundness_top_left"),
                "border_roundness_top_right": visual.get("border_roundness_top_right"),
                "border_roundness_bottom_right": visual.get("border_roundness_bottom_right"),
                "border_roundness_bottom_left": visual.get("border_roundness_bottom_left"),
                "use_aspect_ratio": bool(visual.get("use_aspect_ratio", True)),
                "aspect_ratio_width": visual.get("aspect_ratio_width"),
                "aspect_ratio_height": visual.get("aspect_ratio_height"),
                "margin_left": margin_left,
                "margin_top": self._parse_margin_value(styles.get("margin-top")),
                "margin_bottom": self._parse_margin_value(styles.get("margin-bottom")),
                "margin_right": self._parse_margin_value(styles.get("margin-right")),
                "min_width_css": min_width_css or (f"{width}px" if fixed_size and width else None),
                "min_height_css": min_height_css or (f"{height}px" if fixed_size and height else None),
                "border_width": visual.get("border_width"),
                "border_color": visual.get("border_color"),
                "horiz_alignment": horiz_alignment,
                "vert_alignment": vert_alignment,
                "max_width_css": max_width_css,
                "max_height_css": max_height_css,
                "opacity": self._normalize_opacity_percent(visual.get("opacity")),
            },
        }
        if css_filter:
            image_props["properties"]["css_filter"] = css_filter
        return image_props

    def map_shape(self, element: Dict[str, Any], depth: int = 0) -> Optional[Dict[str, Any]]:
        # Preserve vector geometry as an image so static visual fidelity survives.
        styles = self._merge_styles(element)
        rect = element.get("rect", {}) or {}
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        tag = str(element.get("type") or element.get("tag") or "").lower()
        visual = self._extract_visual_properties(
            styles,
            rect,
            node_type="group",
            intrinsic=element.get("intrinsic", {}) or {},
        )
        width = visual.get("width") or 24
        height = visual.get("height") or 24
        if width <= 0 or height <= 0:
            return None

        if tag == "svg":
            svg_markup = self._serialize_svg_node(element, width=width, height=height)
            if not svg_markup:
                return None
            horiz_alignment = self._parent_horiz_alignment_from_styles(element)
            if horiz_alignment is None:
                horiz_alignment = self._geometry_horiz_alignment(element, width, default="center")
            return {
                "bubble_type": "Image",
                "properties": {
                    "name": self._name_from_element(element, fallback="SVG"),
                    "image_url": f"data:image/svg+xml;utf8,{quote(svg_markup)}",
                    "width": width,
                    "height": height,
                    "fixed_size": True,
                    "border_radius": 0,
                    "use_aspect_ratio": True,
                    "aspect_ratio_width": width,
                    "aspect_ratio_height": height,
                    "min_width_css": f"{width}px",
                    "horiz_alignment": horiz_alignment,
                    "vert_alignment": "center",
                    "margin_right": self._parse_margin_value(styles.get("margin-right")),
                },
            }

        if tag == "i" or any(c.startswith("fa-") for c in classes):
            color = self._text_color(styles.get("color"), styles) or "#111827"
            svg_url = self._svg_placeholder_icon(width, height, color=color)
            margin_right = self._parse_margin_value(styles.get("margin-right"))
            horiz_alignment = self._parent_horiz_alignment_from_styles(element)
            if horiz_alignment is None:
                horiz_alignment = self._geometry_horiz_alignment(element, width, default="center")
            if any("magnifying-glass" in c for c in classes):
                mr = self._to_int(margin_right, 0) or 0
                if mr <= 0:
                    margin_right = 36
            return {
                "bubble_type": "Image",
                "properties": {
                    "name": self._name_from_element(element, fallback="Icon"),
                    "image_url": svg_url,
                    "width": width,
                    "height": height,
                    "fixed_size": True,
                    "border_radius": 0,
                    "use_aspect_ratio": True,
                    "aspect_ratio_width": width,
                    "aspect_ratio_height": height,
                    "min_width_css": f"{width}px",
                    "horiz_alignment": horiz_alignment,
                    "vert_alignment": "center",
                    "margin_right": margin_right,
                },
            }

        return {
            "bubble_type": "Group",
            "properties": {
                "name": self._name_from_element(element, fallback="Icon Placeholder"),
                "layout": "column",
                "width": width,
                "height": height,
                "bg_color": None,
            },
            "children": [],
        }

    def _merge_styles(self, element: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        merged.update(element.get("computed_styles", {}) or {})
        merged.update(element.get("styles", {}) or {})
        return merged

    def _parent_inner_dimensions(
        self,
        element: Dict[str, Any],
    ) -> tuple[Optional[int], Optional[int]]:
        parent_rect = element.get("_parent_rect") or {}
        parent_styles = element.get("_parent_styles") or {}
        parent_width = self._to_int(parent_rect.get("width"), None)
        parent_height = self._to_int(parent_rect.get("height"), None)
        if parent_width is None and parent_height is None:
            return None, None
        pad_left = self._parse_dimension((parent_styles or {}).get("padding-left")) or 0
        pad_right = self._parse_dimension((parent_styles or {}).get("padding-right")) or 0
        pad_top = self._parse_dimension((parent_styles or {}).get("padding-top")) or 0
        pad_bottom = self._parse_dimension((parent_styles or {}).get("padding-bottom")) or 0
        inner_width = None if parent_width is None else max(parent_width - pad_left - pad_right, 0)
        inner_height = None if parent_height is None else max(parent_height - pad_top - pad_bottom, 0)
        return inner_width, inner_height

    def _geometry_horiz_alignment(
        self,
        element: Dict[str, Any],
        width: Optional[int],
        default: Optional[str] = None,
    ) -> Optional[str]:
        rect = element.get("rect") or {}
        parent_rect = element.get("_parent_rect") or {}
        parent_styles = element.get("_parent_styles") or {}
        rect_x = self._to_float(rect.get("x"))
        rect_w = self._to_float(rect.get("width"))
        parent_x = self._to_float(parent_rect.get("x"))
        parent_w = self._to_float(parent_rect.get("width"))
        if rect_x is None or rect_w is None or parent_x is None or parent_w is None or parent_w <= 0:
            return default
        pad_left = float(self._parse_dimension((parent_styles or {}).get("padding-left")) or 0)
        pad_right = float(self._parse_dimension((parent_styles or {}).get("padding-right")) or 0)
        left_gap = rect_x - parent_x - pad_left
        right_gap = (parent_x + parent_w - pad_right) - (rect_x + rect_w)
        tolerance = max(4.0, min(float(width or rect_w), 40.0) * 0.12)
        if abs(left_gap - right_gap) <= tolerance:
            return "center"
        if left_gap <= right_gap:
            return "flex-start"
        return "flex-end"

    def _parent_horiz_alignment_from_styles(self, element: Dict[str, Any]) -> Optional[str]:
        parent_styles = element.get("_parent_styles") or {}
        parent_display = self._clean_text((parent_styles or {}).get("display", "")).lower()
        parent_justify = self._clean_text((parent_styles or {}).get("justify-content", "")).lower()
        parent_text_align = self._clean_text((parent_styles or {}).get("text-align", "")).lower()

        if parent_display == "flex":
            if parent_justify == "center":
                return "center"
            if parent_justify in {"flex-end", "end", "right"}:
                return "flex-end"
            if parent_justify in {"flex-start", "start", "left", "space-between", "space-around", "space-evenly", ""}:
                return "flex-start"

        if parent_text_align == "center":
            return "center"
        if parent_text_align in {"right", "end"}:
            return "flex-end"
        if parent_text_align in {"left", "start", ""}:
            return "flex-start"
        return None

    def _derive_text_style_source(self, element: Dict[str, Any], fallback_styles: Dict[str, Any]) -> Dict[str, Any]:
        def _normalize(style_map: Dict[str, Any]) -> Dict[str, Any]:
            return {str(k).strip().lower(): str(v).strip() for k, v in (style_map or {}).items() if str(k).strip()}

        def _has_core_text_props(style_map: Dict[str, Any]) -> bool:
            return any(self._clean_text(style_map.get(k, "")) for k in ("font-size", "font-weight", "color", "line-height", "font-family"))

        base = _normalize(fallback_styles)
        segments = [
            seg for seg in (element.get("text_segments", []) or [])
            if isinstance(seg, dict) and self._clean_text(seg.get("text", ""))
        ]

        if len(segments) == 1:
            seg_styles = _normalize((segments[0] or {}).get("styles", {}) or {})
            if _has_core_text_props(seg_styles):
                merged = dict(base)
                merged.update(seg_styles)
                return merged or seg_styles

        if len(segments) > 1:
            first_seg_styles = _normalize((segments[0] or {}).get("styles", {}) or {})
            if _has_core_text_props(first_seg_styles):
                merged = dict(base)
                for key in (
                    "font-size",
                    "font-weight",
                    "color",
                    "line-height",
                    "font-family",
                    "font-style",
                    "text-decoration",
                    "text-decoration-line",
                    "letter-spacing",
                    "text-transform",
                    "opacity",
                ):
                    if self._clean_text(first_seg_styles.get(key, "")):
                        merged[key] = first_seg_styles[key]
                return merged or first_seg_styles
            if _has_core_text_props(base):
                return base

        text_children = [
            child for child in (element.get("children", []) or [])
            if isinstance(child, dict) and self._clean_text(child.get("text", ""))
        ]
        if len(text_children) == 1:
            child_styles = _normalize(self._merge_styles(text_children[0]))
            if _has_core_text_props(child_styles):
                merged = dict(base)
                for key in (
                    "font-size",
                    "font-weight",
                    "color",
                    "line-height",
                    "font-family",
                    "font-style",
                    "text-decoration",
                    "text-decoration-line",
                    "letter-spacing",
                    "text-transform",
                    "opacity",
                ):
                    if not self._clean_text(merged.get(key, "")) and self._clean_text(child_styles.get(key, "")):
                        merged[key] = child_styles[key]
                return merged or child_styles

        return base

    def _normalize_opacity_percent(self, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            numeric = float(value)
        except Exception:
            return None
        if numeric <= 1:
            return max(0, min(100, int(round(numeric * 100))))
        return max(0, min(100, int(round(numeric))))

    def _should_map_container_as_text(self, element: Dict[str, Any], styles: Dict[str, Any]) -> bool:
        children = [ch for ch in (element.get("children", []) or []) if isinstance(ch, dict)]
        if children:
            return False
        text = self._clean_text(element.get("text", "")) or self._deep_text(element)
        if not text or self._is_noise_text(text):
            return False
        if self._has_media_content(element):
            return False
        if self._has_visual_box(styles) or self._has_background_image_layer(element):
            return False
        pseudo = element.get("pseudo", {}) or {}
        if isinstance(pseudo, dict):
            for pseudo_key in ("before", "after"):
                pseudo_styles = pseudo.get(pseudo_key)
                if not isinstance(pseudo_styles, dict):
                    continue
                bg = pseudo_styles.get("background-image") or pseudo_styles.get("background")
                if self._extract_background_image_url(bg):
                    return False
        return True

    def _determine_bubble_layout(self, styles: Dict[str, Any], element: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        display = self._clean_text(styles.get("display", "")).lower()
        layout = self._detect_layout(element, styles)
        props: Dict[str, Any] = {}
        classes = self._classes(element.get("attributes", {}) or {})
        class_blob = " ".join(classes)
        has_flex_class = bool(
            any(c in {"d-flex", "flex", "flex-row", "flex-column", "flex-wrap"} for c in classes)
            or "flex-" in class_blob
        )

        if display == "flex":
            direction = self._clean_text(styles.get("flex-direction", "")).lower()
            if direction in {"row", "column"}:
                layout = direction
            elif direction in {"row-reverse", "column-reverse"}:
                layout = "row" if direction.startswith("row") else "column"
            else:
                # CSS default for flex-direction is row.
                layout = "row"
        elif display == "grid":
            cols = self._grid_column_count(styles.get("grid-template-columns"))
            layout = "row" if cols > 1 else "column"
        else:
            flex_direction = self._clean_text(styles.get("flex-direction", "")).lower()
            if flex_direction in {"row", "column", "row-reverse", "column-reverse"} and has_flex_class:
                layout = "row" if flex_direction.startswith("row") else "column"

        align_items = self._clean_text(styles.get("align-items", "")).lower()
        justify_content = self._clean_text(styles.get("justify-content", "")).lower()
        align_map = {
            "flex-start": "flex-start",
            "start": "flex-start",
            "left": "flex-start",
            "center": "center",
            "flex-end": "flex-end",
            "end": "flex-end",
            "right": "flex-end",
            "stretch": "stretch",
            "space-between": "space-between",
            "space-around": "space-around",
            "space-evenly": "space-evenly",
        }
        if layout == "row":
            if justify_content in align_map:
                props["container_horiz_alignment"] = align_map[justify_content]
            if align_items in align_map:
                props["container_vert_alignment"] = align_map[align_items]
        else:
            if align_items in align_map:
                props["container_horiz_alignment"] = align_map[align_items]
            if justify_content in align_map:
                props["container_vert_alignment"] = align_map[justify_content]

        return layout, props

    def _extract_visual_properties(
        self,
        styles: Dict[str, Any],
        rect: Dict[str, Any],
        node_type: str = "generic",
        intrinsic: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        intrinsic = intrinsic or {}
        width = self._parse_dimension(styles.get("width"))
        height = self._parse_dimension(styles.get("height"))
        if width is None:
            width = self._to_int(rect.get("width"), None)
        if height is None:
            height = self._to_int(rect.get("height"), None)

        min_width = self._parse_dimension(styles.get("min-width"))
        min_height = self._parse_dimension(styles.get("min-height"))
        max_width = self._parse_dimension(styles.get("max-width"))
        max_height = self._parse_dimension(styles.get("max-height"))
        if min_width is not None and min_width <= 0:
            min_width = None
        if min_height is not None and min_height <= 0:
            min_height = None
        if max_width is not None and max_width <= 0:
            max_width = None
        if max_height is not None and max_height <= 0:
            max_height = None

        raw_radius = self._clean_text(styles.get("border-radius", "")).lower()
        corner_roundness: Dict[str, Optional[int]] = {
            "border_roundness_top_left": None,
            "border_roundness_top_right": None,
            "border_roundness_bottom_right": None,
            "border_roundness_bottom_left": None,
        }
        def _expand_box_values(values: List[Any]) -> List[Any]:
            if len(values) == 1:
                return [values[0], values[0], values[0], values[0]]
            if len(values) == 2:
                return [values[0], values[1], values[0], values[1]]
            if len(values) == 3:
                return [values[0], values[1], values[2], values[1]]
            if len(values) >= 4:
                return [values[0], values[1], values[2], values[3]]
            return [None, None, None, None]

        radius_tokens = [tok for tok in raw_radius.replace("/", " ").split() if tok]
        if len(radius_tokens) >= 2:
            parsed_corners: List[Optional[int]] = []
            for tok in radius_tokens[:4]:
                if tok.endswith("%"):
                    try:
                        parsed_corners.append(100 if float(tok.replace("%", "").strip()) >= 50 else 0)
                    except Exception:
                        parsed_corners.append(None)
                else:
                    parsed_corners.append(self._parse_dimension(tok))
            expanded = _expand_box_values(parsed_corners)
            corner_roundness["border_roundness_top_left"] = expanded[0]
            corner_roundness["border_roundness_top_right"] = expanded[1]
            corner_roundness["border_roundness_bottom_right"] = expanded[2]
            corner_roundness["border_roundness_bottom_left"] = expanded[3]
        border_radius: Optional[int] = None
        percent_radii = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", raw_radius)]
        if percent_radii and max(percent_radii) >= 50:
            border_radius = 100
        if border_radius is None:
            for key in (
                "border-top-left-radius",
                "border-top-right-radius",
                "border-bottom-left-radius",
                "border-bottom-right-radius",
            ):
                corner_raw = self._clean_text(styles.get(key, "")).lower()
                pct = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", corner_raw)]
                if pct and max(pct) >= 50:
                    border_radius = 100
                    break
        if raw_radius.endswith("%"):
            try:
                pct = float(raw_radius.replace("%", "").strip())
                if pct >= 50:
                    border_radius = 100
            except Exception:
                border_radius = None
        if border_radius is None:
            parsed_radius = self._parse_dimension(raw_radius)
            if parsed_radius is not None:
                border_radius = parsed_radius
                if node_type == "image" and width and height and parsed_radius >= int(min(width, height) / 2):
                    border_radius = 100
        if border_radius is None:
            corner_vals = []
            for key, prop_key in (
                ("border-top-left-radius", "border_roundness_top_left"),
                ("border-top-right-radius", "border_roundness_top_right"),
                ("border-bottom-right-radius", "border_roundness_bottom_right"),
                ("border-bottom-left-radius", "border_roundness_bottom_left"),
            ):
                v = self._parse_dimension(styles.get(key))
                if v is not None:
                    corner_vals.append(v)
                    corner_roundness[prop_key] = v
            if corner_vals:
                border_radius = max(corner_vals)
                if node_type == "image" and width and height and border_radius >= int(min(width, height) / 2):
                    border_radius = 100
        if border_radius is None:
            corner_vals = [v for v in corner_roundness.values() if v is not None]
            if corner_vals:
                border_radius = max(corner_vals)
        if border_radius is not None and not any(v is not None for v in corner_roundness.values()):
            for key in tuple(corner_roundness.keys()):
                corner_roundness[key] = border_radius

        border_width = self._parse_dimension(styles.get("border-width"))
        border_color = self._resolve_color(styles.get("border-color"), styles)
        border_width_top = self._parse_dimension(styles.get("border-top-width"))
        border_width_right = self._parse_dimension(styles.get("border-right-width"))
        border_width_bottom = self._parse_dimension(styles.get("border-bottom-width"))
        border_width_left = self._parse_dimension(styles.get("border-left-width"))
        border_style_top = self._clean_text(styles.get("border-top-style", "")).lower() or None
        border_style_right = self._clean_text(styles.get("border-right-style", "")).lower() or None
        border_style_bottom = self._clean_text(styles.get("border-bottom-style", "")).lower() or None
        border_style_left = self._clean_text(styles.get("border-left-style", "")).lower() or None
        border_color_top = self._resolve_color(styles.get("border-top-color"), styles)
        border_color_right = self._resolve_color(styles.get("border-right-color"), styles)
        border_color_bottom = self._resolve_color(styles.get("border-bottom-color"), styles)
        border_color_left = self._resolve_color(styles.get("border-left-color"), styles)
        if any(v is None for v in (border_width_top, border_width_right, border_width_bottom, border_width_left)):
            width_tokens = [self._parse_dimension(tok) for tok in self._clean_text(styles.get("border-width", "")).split() if tok]
            if width_tokens:
                expanded = _expand_box_values(width_tokens)
                if border_width_top is None:
                    border_width_top = expanded[0]
                if border_width_right is None:
                    border_width_right = expanded[1]
                if border_width_bottom is None:
                    border_width_bottom = expanded[2]
                if border_width_left is None:
                    border_width_left = expanded[3]
        if any(v is None for v in (border_style_top, border_style_right, border_style_bottom, border_style_left)):
            style_tokens = [tok for tok in self._clean_text(styles.get("border-style", "")).split() if tok]
            if style_tokens:
                expanded = _expand_box_values(style_tokens)
                if border_style_top is None:
                    border_style_top = expanded[0]
                if border_style_right is None:
                    border_style_right = expanded[1]
                if border_style_bottom is None:
                    border_style_bottom = expanded[2]
                if border_style_left is None:
                    border_style_left = expanded[3]
        if any(v is None for v in (border_color_top, border_color_right, border_color_bottom, border_color_left)):
            color_tokens = re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]+|[a-zA-Z-]+", self._clean_text(styles.get("border-color", "")))
            if color_tokens:
                resolved = [self._resolve_color(tok, styles) or tok for tok in color_tokens]
                expanded = _expand_box_values(resolved)
                if border_color_top is None:
                    border_color_top = expanded[0]
                if border_color_right is None:
                    border_color_right = expanded[1]
                if border_color_bottom is None:
                    border_color_bottom = expanded[2]
                if border_color_left is None:
                    border_color_left = expanded[3]
        zindex = self._parse_z_index(styles.get("z-index"))
        bg_color = self._resolve_color(styles.get("background-color"), styles) or self._resolve_color(styles.get("background"), styles)
        box_shadow = self._clean_text(styles.get("box-shadow", "")) or None
        shadow_props = self._extract_shadow_properties(box_shadow)
        opacity = self._clean_text(styles.get("opacity", ""))
        margin_left = self._parse_margin_value(styles.get("margin-left"))
        aspect_ratio = self._clean_text(styles.get("aspect-ratio", "")).lower()
        intrinsic_width = self._to_int(intrinsic.get("width"), None)
        intrinsic_height = self._to_int(intrinsic.get("height"), None)
        aspect_ratio_width: Optional[int] = None
        aspect_ratio_height: Optional[int] = None
        if intrinsic_width and intrinsic_height:
            aspect_ratio_width = intrinsic_width
            aspect_ratio_height = intrinsic_height
        elif width and height:
            aspect_ratio_width = width
            aspect_ratio_height = height
        use_aspect_ratio = False
        if aspect_ratio and "/" in aspect_ratio and aspect_ratio_width and aspect_ratio_height:
            use_aspect_ratio = True
        elif aspect_ratio_width and aspect_ratio_height and node_type in {"image", "video", "iframe", "button"}:
            use_aspect_ratio = True

        fixed_size = bool(node_type == "image" and width and height and width <= 120 and height <= 120)
        min_width_css = None
        min_height_css = None
        if min_width is not None:
            min_width_css = f"{min_width}px"
        elif fixed_size and width:
            min_width_css = f"{width}px"
        if min_height is not None:
            min_height_css = f"{min_height}px"
        elif fixed_size and height:
            min_height_css = f"{height}px"

        return {
            "width": width,
            "height": height,
            "min_width": min_width,
            "min_height": min_height,
            "max_width": max_width,
            "max_height": max_height,
            "intrinsic_width": intrinsic_width,
            "intrinsic_height": intrinsic_height,
            "border_radius": border_radius,
            "border_roundness_top_left": corner_roundness["border_roundness_top_left"],
            "border_roundness_top_right": corner_roundness["border_roundness_top_right"],
            "border_roundness_bottom_right": corner_roundness["border_roundness_bottom_right"],
            "border_roundness_bottom_left": corner_roundness["border_roundness_bottom_left"],
            "border_width": border_width,
            "border_color": border_color,
            "border_width_top": border_width_top,
            "border_width_right": border_width_right,
            "border_width_bottom": border_width_bottom,
            "border_width_left": border_width_left,
            "border_style_top": border_style_top,
            "border_style_right": border_style_right,
            "border_style_bottom": border_style_bottom,
            "border_style_left": border_style_left,
            "border_color_top": border_color_top,
            "border_color_right": border_color_right,
            "border_color_bottom": border_color_bottom,
            "border_color_left": border_color_left,
            "zindex": zindex,
            "box_shadow": box_shadow,
            "shadow_style": shadow_props.get("shadow_style"),
            "shadow_h": shadow_props.get("shadow_h"),
            "shadow_v": shadow_props.get("shadow_v"),
            "shadow_blur": shadow_props.get("shadow_blur"),
            "shadow_spread": shadow_props.get("shadow_spread"),
            "shadow_color": shadow_props.get("shadow_color"),
            "opacity": float(opacity) if opacity and opacity.replace(".", "", 1).isdigit() else None,
            "bg_color": bg_color,
            "margin_top": self._parse_margin_value(styles.get("margin-top")),
            "margin_bottom": self._parse_margin_value(styles.get("margin-bottom")),
            "margin_left": margin_left,
            "margin_right": self._parse_margin_value(styles.get("margin-right")),
            "padding_top": self._parse_dimension(styles.get("padding-top")),
            "padding_bottom": self._parse_dimension(styles.get("padding-bottom")),
            "padding_left": self._parse_dimension(styles.get("padding-left")),
            "padding_right": self._parse_dimension(styles.get("padding-right")),
            "use_aspect_ratio": use_aspect_ratio,
            "aspect_ratio_width": aspect_ratio_width,
            "aspect_ratio_height": aspect_ratio_height,
            "fixed_size": fixed_size,
            "min_width_css": min_width_css,
            "min_height_css": min_height_css,
            "max_width_css": f"{max_width}px" if max_width is not None else None,
            "max_height_css": f"{max_height}px" if max_height is not None else None,
        }

    def _parse_z_index(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        s = self._clean_text(value).lower()
        if not s or s in {"auto", "initial", "inherit"}:
            return None
        if re.fullmatch(r"-?\d+", s):
            try:
                return int(s)
            except Exception:
                return None
        try:
            return int(round(float(s)))
        except Exception:
            return None

    def _extract_shadow_properties(self, box_shadow: Any) -> Dict[str, Any]:
        raw = self._clean_text(box_shadow)
        if not raw:
            return {}
        lowered = raw.lower()
        if lowered in {"none", "0px 0px 0px 0px transparent"}:
            return {}

        def _split_shadow_layers(value: str) -> List[str]:
            layers: List[str] = []
            current: List[str] = []
            depth = 0
            for ch in value:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth = max(0, depth - 1)
                if ch == "," and depth == 0:
                    layer = "".join(current).strip()
                    if layer:
                        layers.append(layer)
                    current = []
                    continue
                current.append(ch)
            layer = "".join(current).strip()
            if layer:
                layers.append(layer)
            return layers

        layer = next((part for part in _split_shadow_layers(raw) if part), "")
        if not layer:
            return {}

        style = "inset" if re.search(r"\binset\b", layer, flags=re.IGNORECASE) else "outset"
        cleaned = re.sub(r"\binset\b", "", layer, flags=re.IGNORECASE).strip()
        color_match = re.search(r"(rgba?\([^)]*\)|hsla?\([^)]*\)|#[0-9a-fA-F]{3,8}|\b[a-zA-Z]+\b)", cleaned)
        shadow_color = None
        if color_match:
            token = color_match.group(1)
            shadow_color = self._resolve_color(token, {}) or token
            cleaned = (cleaned[:color_match.start()] + cleaned[color_match.end():]).strip()

        values = []
        for match in re.findall(r"-?\d+(?:\.\d+)?px", cleaned):
            try:
                values.append(int(round(float(match[:-2]))))
            except Exception:
                continue
        if len(values) < 2:
            return {}
        shadow_h = values[0]
        shadow_v = values[1]
        shadow_blur = values[2] if len(values) > 2 else 0
        shadow_spread = values[3] if len(values) > 3 else 0
        return {
            "shadow_style": style,
            "shadow_h": shadow_h,
            "shadow_v": shadow_v,
            "shadow_blur": shadow_blur,
            "shadow_spread": shadow_spread,
            "shadow_color": shadow_color,
        }

    def _build_rich_text_content(self, element: Dict[str, Any], fallback_text: str = "") -> str:
        segments = element.get("text_segments", []) or []
        if not segments:
            return fallback_text

        base_styles = self._merge_styles(element)
        base_style = self._bb_style_from_styles(base_styles)
        # Use first non-empty text segment as baseline when available.
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            txt = str(seg.get("text", ""))
            if txt.strip():
                base_style = self._bb_style_from_styles(seg.get("styles", {}) or {}, fallback=base_style)
                break

        out: List[str] = []
        prev_piece: Optional[str] = None
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            raw_segment = str(seg.get("text", ""))
            if not raw_segment:
                continue
            if raw_segment == "\n":
                out.append("\n")
                continue
            seg_styles = seg.get("styles", {}) or {}
            stripped = raw_segment.strip(" ")
            if not stripped:
                out.append(raw_segment)
                continue
            lead_count = len(raw_segment) - len(raw_segment.lstrip(" "))
            trail_count = len(raw_segment) - len(raw_segment.rstrip(" "))
            seg_style = self._bb_style_from_styles(seg_styles, fallback=base_style)
            piece = self._wrap_bbcode_delta(stripped, base_style, seg_style)
            leading = " " * lead_count
            trailing = " " * trail_count
            if not leading and prev_piece:
                if re.search(r"[A-Za-z0-9]$", prev_piece) and re.match(r"[A-Za-z0-9]", stripped):
                    leading = " "
            out.append(leading + piece + trailing)
            prev_piece = piece if piece else prev_piece

        joined = self._normalize_bbcode_whitespace("".join(out))
        if fallback_text:
            def _space_count(val: str) -> int:
                return len(re.findall(r"\s+", val))
            if _space_count(joined) + 2 < _space_count(fallback_text):
                return fallback_text
        return joined or fallback_text

    def _font_weight_num(self, value: Any) -> int:
        s = self._clean_text(value).lower()
        if not s:
            return 400
        named = {"normal": 400, "regular": 400, "medium": 500, "semibold": 600, "bold": 700}
        if s in named:
            return named[s]
        try:
            return int(float(s))
        except Exception:
            return 400

    def _bb_style_from_styles(self, styles: Dict[str, Any], fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        source = {str(k).strip().lower(): str(v).strip() for k, v in (styles or {}).items() if str(k).strip()}
        base = dict(fallback or {})
        color = self._to_bbcode_color(self._resolve_color(source.get("color"), source))
        if color:
            base["color"] = color
        if source.get("font-weight") is not None:
            base["weight"] = self._font_weight_num(source.get("font-weight"))
        elif "weight" not in base:
            base["weight"] = 400
        font_style = self._clean_text(source.get("font-style", "")).lower()
        if font_style:
            base["italic"] = font_style in {"italic", "oblique"}
        elif "italic" not in base:
            base["italic"] = False
        text_decoration = self._clean_text(source.get("text-decoration-line") or source.get("text-decoration", "")).lower()
        if text_decoration:
            base["underline"] = "underline" in text_decoration
        elif "underline" not in base:
            base["underline"] = False
        return base

    def _wrap_bbcode_delta(self, text: str, base: Dict[str, Any], current: Dict[str, Any]) -> str:
        out = text
        curr_color = current.get("color")
        base_color = base.get("color")
        if curr_color and curr_color != base_color:
            out = f"[color={curr_color}]{out}[/color]"

        curr_weight = int(current.get("weight", 400) or 400)
        base_weight = int(base.get("weight", 400) or 400)
        if curr_weight >= 600 and curr_weight > base_weight:
            out = f"[b]{out}[/b]"

        curr_italic = bool(current.get("italic", False))
        base_italic = bool(base.get("italic", False))
        if curr_italic and not base_italic:
            out = f"[i]{out}[/i]"

        curr_underline = bool(current.get("underline", False))
        base_underline = bool(base.get("underline", False))
        if curr_underline and not base_underline:
            out = f"[u]{out}[/u]"
        return out

    def _normalize_bbcode_whitespace(self, text: str) -> str:
        if not text:
            return ""
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[ \t\f\v]+", " ", line) for line in t.split("\n")]
        t = "\n".join(lines)
        t = re.sub(r"\n{3,}", "\n\n", t)
        t = re.sub(r" {2,}", " ", t)
        t = re.sub(r" *\n *", "\n", t)
        return t.strip()

    def _normalize_heading_content(self, text: str) -> str:
        t = self._clean_text(text)
        if not t:
            return t
        if "[" in t and "]" in t:
            return t

        tokens = t.split()
        if len(tokens) >= 8:
            alnum_tokens = [re.sub(r"[^A-Za-z0-9]", "", tok) for tok in tokens]
            short_tokens = sum(1 for tok in alnum_tokens if len(tok) <= 1)
            if short_tokens / max(len(tokens), 1) >= 0.65:
                t = "".join(tokens)

        if " " not in t and len(t) >= 18:
            t = t.replace("&", " & ")
            t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", t)
            t = re.sub(r"\s+", " ", t).strip()

        return t

    def _is_complex_player_node(self, element: Dict[str, Any]) -> bool:
        node_type = str(element.get("type", "")).lower()
        if node_type in {"video", "iframe"}:
            return True
        # Wrapper nodes that contain embedded players should collapse too.
        if self._has_descendant_tag(element, {"video", "iframe"}):
            return True
        attrs = element.get("attributes", {}) or {}
        class_blob = " ".join(self._classes(attrs))
        attr_blob = " ".join([str(k).lower() for k in attrs.keys()])
        value_blob = " ".join([self._clean_text(v).lower() for v in attrs.values() if isinstance(v, (str, int, float))])
        markers = ("player", "smartplayer", "v-turb", "vturb", "youtube", "vimeo")
        if any(m in class_blob for m in markers):
            return True
        if any(m in attr_blob for m in markers):
            return True
        if any(m in value_blob for m in markers):
            return True
        return False

    def _to_int(self, value: Any, fallback: Optional[int]) -> Optional[int]:
        try:
            if value is None:
                return fallback
            if isinstance(value, bool):
                return fallback
            if isinstance(value, (int, float)):
                return int(round(float(value)))
            s = self._clean_text(value).lower().replace("px", "")
            if not s:
                return fallback
            return int(round(float(s)))
        except Exception:
            return fallback

    def _to_float(self, value: Any, fallback: Optional[float] = None) -> Optional[float]:
        try:
            if value is None or isinstance(value, bool):
                return fallback
            if isinstance(value, (int, float)):
                return float(value)
            s = self._clean_text(value).lower().replace("px", "")
            if not s:
                return fallback
            return float(s)
        except Exception:
            return fallback

    @staticmethod
    def _classes(attrs: Dict[str, Any]) -> List[str]:
        raw = attrs.get("class", [])
        if isinstance(raw, list):
            return [str(c).strip().lower() for c in raw if str(c).strip()]
        if not str(raw).strip():
            return []
        return [c for c in re.split(r"\s+", str(raw).strip().lower()) if c]

    def _detect_layout(self, element: Dict[str, Any], styles: Dict[str, Any]) -> str:
        classes = self._classes(element.get("attributes", {}) or {})
        if "row" in classes:
            return "row"
        display = str(styles.get("display", "")).lower()
        if display == "grid":
            cols = self._grid_column_count(styles.get("grid-template-columns"))
            return "row" if cols > 1 else "column"
        if display == "flex":
            direction = str(styles.get("flex-direction", "column")).lower()
            return "row" if direction == "row" else "column"

        children = element.get("children", []) or []
        if len(children) >= 2:
            if display not in {"flex", "grid"}:
                text_children = 0
                for ch in children:
                    if not isinstance(ch, dict):
                        continue
                    if self._has_text_content(ch):
                        text_children += 1
                if text_children >= 2 and text_children == len(children):
                    return "column"
            later_children = children[1:]
            # Block containers often stack sibling sections with explicit top
            # margins (e.g. Bootstrap rows). Prefer vertical flow in that case.
            later_has_positive_top_margin = any(
                (self._parse_margin_value(self._merge_styles(ch).get("margin-top")) or 0) > 0
                for ch in later_children
                if isinstance(ch, dict)
            )
            if later_has_positive_top_margin:
                return "column"

            # When multiple direct children are explicit ".row" flex blocks, the
            # parent is usually a vertical section container, not a horizontal row.
            row_like_children = 0
            for ch in children:
                if not isinstance(ch, dict):
                    continue
                ch_styles = self._merge_styles(ch)
                ch_display = str(ch_styles.get("display", "")).lower()
                ch_classes = self._classes(ch.get("attributes", {}) or {})
                if ch_display == "flex" and "row" in ch_classes:
                    row_like_children += 1
            if row_like_children >= 2:
                return "column"

        if len(children) >= 2:
            rects = []
            for ch in children:
                if not isinstance(ch, dict):
                    continue
                rect = ch.get("rect", {}) or {}
                top = rect.get("top")
                left = rect.get("left")
                width = rect.get("width")
                height = rect.get("height")
                if top is None or left is None or width is None or height is None:
                    continue
                try:
                    top = float(top)
                    left = float(left)
                    width = float(width)
                    height = float(height)
                except Exception:
                    continue
                if width <= 0 or height <= 0:
                    continue
                rects.append({"top": top, "left": left, "width": width, "height": height})

            if len(rects) >= 2:
                ys = [r["top"] for r in rects]
                xs = [r["left"] for r in rects]
                y_span = max(ys) - min(ys)
                x_span = max(xs) - min(xs)
                avg_h = sum(r["height"] for r in rects) / len(rects)
                avg_w = sum(r["width"] for r in rects) / len(rects)
                row_threshold = max(10.0, avg_h * 0.35)
                col_threshold = max(10.0, avg_w * 0.35)
                if y_span <= row_threshold and x_span > max(20.0, avg_w * 0.4):
                    return "row"
                if x_span <= col_threshold and y_span > max(20.0, avg_h * 0.4):
                    return "column"
                if y_span > x_span * 1.1 and y_span > max(14.0, avg_h * 0.4):
                    return "column"
                if x_span > y_span * 1.1 and x_span > max(14.0, avg_w * 0.4):
                    return "row"

        if len(children) >= 2:
            absolute_children = [c for c in children if self._is_absolutely_positioned(self._merge_styles(c))]
            if absolute_children and len(absolute_children) == len(children):
                return "row"
            # Framer-like avatar strips often mix absolute avatar nodes with a
            # single non-absolute label. Keep them horizontal.
            if len(absolute_children) >= 3:
                width = self._parse_dimension(styles.get("width")) or 0
                height = self._parse_dimension(styles.get("height")) or 0
                has_left_anchors = any(
                    self._clean_text(self._merge_styles(c).get("left", ""))
                    for c in absolute_children
                )
                if has_left_anchors and width > 0 and (height <= 0 or width >= (height * 2)):
                    return "row"
        if len(children) == 2:
            left, right = children[0], children[1]
            if self._has_text_content(left) and self._has_media_content(right):
                return "row"
        return "column"

    def _rect_mosaic_geometry(self, element: Dict[str, Any]) -> Optional[Dict[str, int]]:
        children = [child for child in (element.get("children", []) or []) if isinstance(child, dict) and not child.get("_skip_from_mapping")]
        if len(children) < 3:
            return None
        rects: List[Dict[str, float]] = []
        for child in children:
            rect = child.get("rect", {}) or {}
            try:
                x = float(rect.get("x") or rect.get("left"))
                y = float(rect.get("y") or rect.get("top"))
                width = float(rect.get("width") or 0)
                height = float(rect.get("height") or 0)
            except Exception:
                continue
            if width <= 0 or height <= 0:
                continue
            rects.append({"x": x, "y": y, "width": width, "height": height})
        if len(rects) < 3:
            return None

        avg_w = sum(item["width"] for item in rects) / len(rects)
        avg_h = sum(item["height"] for item in rects) / len(rects)
        x_threshold = max(12.0, avg_w * 0.3)
        y_threshold = max(12.0, avg_h * 0.3)

        def _cluster_count(values: List[float], threshold: float) -> int:
            ordered = sorted(values)
            if not ordered:
                return 0
            count = 1
            anchor = ordered[0]
            for value in ordered[1:]:
                if abs(value - anchor) > threshold:
                    count += 1
                    anchor = value
            return count

        x_clusters = _cluster_count([item["x"] for item in rects], x_threshold)
        y_clusters = _cluster_count([item["y"] for item in rects], y_threshold)
        if x_clusters >= 2 and y_clusters >= 2:
            return {"x_clusters": x_clusters, "y_clusters": y_clusters}
        return None

    def _should_use_relative_layout(self, element: Dict[str, Any], styles: Dict[str, Any], detected_layout: str) -> bool:
        display = self._clean_text(styles.get("display", "")).lower()
        classes = self._classes(element.get("attributes", {}) or {})
        if "row" in classes:
            return False
        if display not in {"flex", "grid"} and self._rect_mosaic_geometry(element):
            return True
        if self._is_inline_form_container(element, styles):
            return False
        children = [
            child
            for child in (element.get("children", []) or [])
            if isinstance(child, dict) and not child.get("_skip_from_mapping")
        ]
        if not children:
            return False
        abs_children = [c for c in children if self._is_absolutely_positioned(self._merge_styles(c))]
        if not abs_children:
            return False
        non_abs_count = len(children) - len(abs_children)
        parent_position = self._clean_text(styles.get("position", "")).lower()

        # Relative shells with one in-flow media layer plus one/two overlays
        # should stay align-to-parent even when authored as flex wrappers.
        if 1 <= len(abs_children) <= 2 and 0 < non_abs_count <= 1 and len(children) <= 3:
            non_abs_media = 0
            for child in children:
                if child in abs_children:
                    continue
                if self._has_media_content(child):
                    non_abs_media += 1
            if non_abs_media == non_abs_count and parent_position in {"relative", "absolute", "fixed"}:
                return True

        if display == "grid":
            return False

        if abs_children and non_abs_count == 0:
            return True

        # Keep dense absolute collections (e.g. avatar strips) in flow layout.
        if len(abs_children) >= 3 and len(children) >= 3:
            return False

        # Keep mixed stacks in flow if they still have meaningful regular content.
        if non_abs_count >= 2:
            return False

        if display == "flex":
            return False

        # Row-like wrappers with media/text children should remain row/column.
        if detected_layout in {"row", "column"} and (self._has_text_content(element) or self._has_media_content(element)):
            return False

        # Only use align-to-parent for very small overlay wrappers.
        return len(children) <= 2 and len(abs_children) >= 1

    def _infer_nonant_alignment(self, styles: Dict[str, Any]) -> Optional[str]:
        if not self._is_absolutely_positioned(styles):
            return None

        top_raw = self._clean_text(styles.get("top", ""))
        right_raw = self._clean_text(styles.get("right", ""))
        bottom_raw = self._clean_text(styles.get("bottom", ""))
        left_raw = self._clean_text(styles.get("left", ""))
        transform_raw = self._clean_text(styles.get("transform", "")).lower()
        width_px = self._parse_dimension(styles.get("width"))
        height_px = self._parse_dimension(styles.get("height"))
        tx, ty = self._extract_transform_translation(styles)

        def _to_axis(raw_start: str, raw_end: str, center_hint: str) -> str:
            if center_hint in transform_raw:
                return "b"
            start_pct = self._percent_value(raw_start)
            end_pct = self._percent_value(raw_end)
            start_off = self._parse_margin_value(raw_start)
            end_off = self._parse_margin_value(raw_end)
            if start_pct is not None and end_pct is None:
                if start_pct <= 20:
                    return "a"
                if start_pct >= 80:
                    return "c"
                return "b"
            if end_pct is not None and start_pct is None:
                if end_pct <= 20:
                    return "c"
                if end_pct >= 80:
                    return "a"
                return "b"
            if start_off is not None and end_off is not None:
                if abs(float(start_off) - float(end_off)) <= 2:
                    return "b"
                return "a" if abs(float(start_off)) < abs(float(end_off)) else "c"
            has_start = bool(raw_start)
            has_end = bool(raw_end)
            if has_start and not has_end:
                return "a"
            if has_end and not has_start:
                return "c"
            return "b"

        x = _to_axis(left_raw, right_raw, "translatex(-50%)")
        y = _to_axis(top_raw, bottom_raw, "translatey(-50%)")
        if width_px is not None and abs(tx + (float(width_px) / 2.0)) <= 4:
            x = "b"
        if height_px is not None and abs(ty + (float(height_px) / 2.0)) <= 4:
            y = "b"
        if "translate(-50%" in transform_raw:
            x = "b"
            y = "b"
        return f"{x}{y}"

    def _has_translation_transform(self, styles: Dict[str, Any]) -> bool:
        transform_raw = self._clean_text(styles.get("transform", "")).lower()
        if not transform_raw or transform_raw in {"none", "initial", "unset"}:
            return False
        if "translate" in transform_raw:
            return True
        match = re.search(r"matrix\(([^)]+)\)", transform_raw)
        if not match:
            return False
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) != 6:
            return False
        try:
            tx = float(parts[4])
            ty = float(parts[5])
        except Exception:
            return False
        return abs(tx) > 0.5 or abs(ty) > 0.5

    def _extract_transform_translation(self, styles: Dict[str, Any]) -> tuple[float, float]:
        transform_raw = self._clean_text(styles.get("transform", "")).lower()
        if not transform_raw or transform_raw in {"none", "initial", "unset"}:
            return 0.0, 0.0
        match = re.search(r"matrix\(([^)]+)\)", transform_raw)
        if match:
            parts = [part.strip() for part in match.group(1).split(",")]
            if len(parts) == 6:
                try:
                    return float(parts[4]), float(parts[5])
                except Exception:
                    return 0.0, 0.0
        translate_match = re.search(r"translate\(\s*([-.\d]+)px(?:\s*,\s*|\s+)([-.\d]+)px\s*\)", transform_raw)
        if translate_match:
            try:
                return float(translate_match.group(1)), float(translate_match.group(2))
            except Exception:
                return 0.0, 0.0
        tx = 0.0
        ty = 0.0
        match_x = re.search(r"translatex\(\s*([-.\d]+)px\s*\)", transform_raw)
        match_y = re.search(r"translatey\(\s*([-.\d]+)px\s*\)", transform_raw)
        if match_x:
            try:
                tx = float(match_x.group(1))
            except Exception:
                tx = 0.0
        if match_y:
            try:
                ty = float(match_y.group(1))
            except Exception:
                ty = 0.0
        return tx, ty

    def _final_rect_offsets(
        self,
        element: Dict[str, Any],
    ) -> Optional[tuple[int, int, int, int, int, int]]:
        rect = element.get("rect") or {}
        parent_rect = element.get("_parent_rect") or {}
        if not isinstance(rect, dict) or not isinstance(parent_rect, dict) or not rect or not parent_rect:
            return None
        try:
            parent_x = float(parent_rect.get("x") or parent_rect.get("left") or 0)
            parent_y = float(parent_rect.get("y") or parent_rect.get("top") or 0)
            parent_w = float(parent_rect.get("width") or 0)
            parent_h = float(parent_rect.get("height") or 0)
            child_x = float(rect.get("x") or rect.get("left") or 0)
            child_y = float(rect.get("y") or rect.get("top") or 0)
            child_w = float(rect.get("width") or 0)
            child_h = float(rect.get("height") or 0)
        except Exception:
            return None
        dx = int(round(child_x - parent_x))
        dy = int(round(child_y - parent_y))
        remaining_right = int(round(parent_w - child_w - dx)) if parent_w > 0 and child_w > 0 else 0
        remaining_bottom = int(round(parent_h - child_h - dy)) if parent_h > 0 and child_h > 0 else 0
        return dx, dy, remaining_right, remaining_bottom, int(round(child_w)), int(round(child_h))

    def _nonant_from_rect_offsets(
        self,
        dx: int,
        dy: int,
        remaining_right: int,
        remaining_bottom: int,
        child_w: int,
        child_h: int,
    ) -> str:
        x_threshold = max(24, int(round(child_w * 0.15))) if child_w > 0 else 24
        y_threshold = max(24, int(round(child_h * 0.15))) if child_h > 0 else 24
        if dx <= x_threshold:
            x_axis = "a"
        elif remaining_right <= x_threshold:
            x_axis = "c"
        else:
            x_axis = "b"
        if dy <= y_threshold:
            y_axis = "a"
        elif remaining_bottom <= y_threshold:
            y_axis = "c"
        else:
            y_axis = "b"
        return f"{x_axis}{y_axis}"

    def _percent_value(self, raw: Any) -> Optional[float]:
        s = self._clean_text(raw).lower()
        if not s.endswith("%"):
            return None
        try:
            return float(s[:-1].strip())
        except Exception:
            return None

    def _grid_column_count(self, raw: Any) -> int:
        s = self._clean_text(raw).lower()
        if not s:
            return 1
        repeat = re.search(r"repeat\(\s*(\d+)\s*,", s)
        if repeat:
            try:
                return max(int(repeat.group(1)), 1)
            except Exception:
                return 1
        tokens = [tok for tok in re.split(r"\s+", s) if tok and tok != "/"]
        if len(tokens) > 1:
            return len(tokens)
        parsed = self._parse_dimension(s)
        if parsed:
            return max(parsed, 1)
        return 1

    def _has_text_content(self, node: Dict[str, Any]) -> bool:
        if self._clean_text(node.get("text", "")):
            return True
        for child in node.get("children", []) or []:
            if self._has_text_content(child):
                return True
        return False

    def _has_media_content(self, node: Dict[str, Any]) -> bool:
        node_type = str(node.get("type", "")).lower()
        attrs = node.get("attributes", {}) or {}
        if node_type in {"img", "svg", "iframe", "video"}:
            return True
        if node.get("media_url") or attrs.get("data-lottie-url"):
            return True
        for child in node.get("children", []) or []:
            if self._has_media_content(child):
                return True
        return False

    def _parse_gap(self, gap_str: Any) -> int:
        if gap_str is None:
            return 0
        s = str(gap_str).strip().lower()
        if not s:
            return 0
        m = re.match(r"(\d+(?:\.\d+)?)(px|rem|em)?", s)
        if not m:
            return 0
        value = float(m.group(1))
        unit = m.group(2)
        if unit in {"rem", "em"}:
            return int(round(value * 16))
        return int(round(value))

    def _infer_gap_from_rects(self, element: Dict[str, Any], layout: str) -> int:
        if layout not in {"row", "column"}:
            return 0
        children = []
        for child in element.get("children", []) or []:
            if not isinstance(child, dict):
                continue
            rect = child.get("rect", {}) or {}
            w = self._to_int(rect.get("width"), None)
            h = self._to_int(rect.get("height"), None)
            if w is None or h is None or w <= 0 or h <= 0:
                continue
            children.append(child)
        if len(children) < 2:
            return 0
        if layout == "row":
            children.sort(key=lambda c: float((c.get("rect") or {}).get("x") or 0))
            gaps = []
            for curr, nxt in zip(children, children[1:]):
                c_rect = curr.get("rect", {}) or {}
                n_rect = nxt.get("rect", {}) or {}
                gap = float(n_rect.get("x") or 0) - (float(c_rect.get("x") or 0) + float(c_rect.get("width") or 0))
                if gap > 1 and gap <= 200:
                    gaps.append(gap)
        else:
            children.sort(key=lambda c: float((c.get("rect") or {}).get("y") or 0))
            gaps = []
            for curr, nxt in zip(children, children[1:]):
                c_rect = curr.get("rect", {}) or {}
                n_rect = nxt.get("rect", {}) or {}
                gap = float(n_rect.get("y") or 0) - (float(c_rect.get("y") or 0) + float(c_rect.get("height") or 0))
                if gap > 1 and gap <= 200:
                    gaps.append(gap)
        if not gaps:
            return 0
        gaps.sort()
        return int(round(gaps[len(gaps) // 2]))

    def _infer_gap_from_margins(self, element: Dict[str, Any], layout: str) -> int:
        if layout != "column":
            return 0
        gaps: List[int] = []
        children = [c for c in (element.get("children", []) or []) if isinstance(c, dict)]
        if len(children) < 2:
            return 0
        for child in children[1:]:
            styles = self._merge_styles(child)
            mt = self._parse_margin_value(styles.get("margin-top"))
            if mt is None:
                continue
            if mt <= 0 or mt > 80:
                continue
            gaps.append(int(mt))
        if not gaps:
            return 0
        gaps.sort()
        return gaps[len(gaps) // 2]

    def _bootstrap_col_span(self, classes: List[str]) -> Optional[int]:
        return None

    def _is_bootstrap_container(self, classes: List[str], layout: str) -> bool:
        if layout != "column":
            return False
        return any(cls in {"container", "container-fluid"} for cls in classes)

    def _infer_bootstrap_gutter(
        self,
        element: Dict[str, Any],
        classes: List[str],
        layout: str,
    ) -> int:
        return 0

    def _parse_dimension(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        s = str(value).strip().lower()
        if not s or s in {"auto", "100%"}:
            return None
        if re.fullmatch(r"\d+", s):
            return int(s)
        m = re.match(r"(\d+(?:\.\d+)?)(px|rem|em)?", s)
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2)
        if unit in {"rem", "em"}:
            return int(round(num * 16))
        return int(round(num))

    def _parse_margin_value(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        s = self._clean_text(value).lower()
        if not s:
            return None
        sign = -1 if s.startswith("-") else 1
        s = s.lstrip("+-")
        m = re.match(r"(\d+(?:\.\d+)?)(px|rem|em)?", s)
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2)
        if unit in {"rem", "em"}:
            num *= 16
        return int(round(sign * num))

    def _class_color(self, classes: List[str], prefix: str) -> Optional[str]:
        if prefix == "bg-":
            tokens = [f"bg-{c.split('bg-')[-1]}" for c in classes if "bg-" in c]
        elif prefix == "text-":
            tokens = [f"text-{c.split('text-')[-1]}" for c in classes if "text-" in c]
        else:
            tokens = classes
        for token in tokens:
            if token in self.COLOR_TOKENS:
                return self.COLOR_TOKENS[token]
        return None

    def _extract_native_gradient_props(self, value: Any) -> Optional[Dict[str, Any]]:
        raw = self._clean_text(value)
        if not raw:
            return None
        lower = raw.lower()
        if lower.startswith("linear-gradient("):
            inner = self._function_inner(raw, "linear-gradient")
            if inner is None:
                return None
            parts = self._split_css_args(inner)
            if len(parts) < 2:
                return None
            angle = 180
            if self._looks_like_gradient_direction(parts[0]):
                angle = int(round(self._gradient_angle(parts.pop(0))))
            stops = self._gradient_stops(parts)
            if len(stops) < 2:
                return None
            start_offset, start_color, start_opacity = stops[0]
            end_offset, end_color, end_opacity = stops[-1]
            start_rgba = self._color_with_opacity(start_color, start_opacity)
            end_rgba = self._color_with_opacity(end_color, end_opacity)
            props: Dict[str, Any] = {
                "background_style": "gradient",
                "gradient_style": "linear",
                "gradient_start_color": start_rgba,
                "gradient_end_color": end_rgba,
            }
            if len(stops) > 2:
                mid_offset, mid_color, mid_opacity = stops[1]
                props["gradient_mid_color"] = self._color_with_opacity(mid_color, mid_opacity)
            if angle % 90 == 0:
                direction_map = {
                    0: "top",
                    90: "right",
                    180: "bottom",
                    270: "left",
                    -90: "left",
                }
                props["gradient_direction"] = direction_map.get(angle, "custom")
                if props["gradient_direction"] == "custom":
                    props["gradient_angle"] = angle
            else:
                props["gradient_direction"] = "custom"
                props["gradient_angle"] = angle
            return props
        if lower.startswith("radial-gradient("):
            inner = self._function_inner(raw, "radial-gradient")
            if inner is None:
                return None
            parts = self._split_css_args(inner)
            if len(parts) < 2:
                return None
            if self._looks_like_radial_descriptor(parts[0]):
                parts = parts[1:]
            stops = self._gradient_stops(parts)
            if len(stops) < 2:
                return None
            start_offset, start_color, start_opacity = stops[0]
            end_offset, end_color, end_opacity = stops[-1]
            props = {
                "background_style": "gradient",
                "gradient_style": "radial",
                "gradient_start_color": self._color_with_opacity(start_color, start_opacity),
                "gradient_end_color": self._color_with_opacity(end_color, end_opacity),
            }
            if len(stops) > 2:
                _mid_offset, mid_color, mid_opacity = stops[1]
                props["gradient_mid_color"] = self._color_with_opacity(mid_color, mid_opacity)
            return props
        return None

    def _color_with_opacity(self, color: Optional[str], opacity: float) -> Optional[str]:
        if not color:
            return None
        resolved = self._resolve_color(color, {}) or color
        if opacity >= 0.999:
            return resolved
        rgba_match = re.match(r"rgba?\(([^)]+)\)", resolved.strip(), re.IGNORECASE)
        if rgba_match:
            parts = [part.strip() for part in rgba_match.group(1).split(",")]
            if len(parts) >= 3:
                return f"rgba({parts[0]}, {parts[1]}, {parts[2]}, {opacity:.4f})"
        hex_color = resolved.strip().lstrip("#")
        if len(hex_color) == 6:
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return f"rgba({r}, {g}, {b}, {opacity:.4f})"
            except Exception:
                return resolved
        return resolved

    def _extract_background_image_url(self, value: Any) -> Optional[str]:
        s = self._clean_text(value)
        if not s or s.lower() == "none":
            return None
        m = re.search(r"url\((?:['\"])?(.*?)(?:['\"])?\)", s)
        if m:
            return self._absolutize_url(self._clean_text(m.group(1)))
        if "gradient(" in s.lower():
            return self._gradient_placeholder_image(s)
        return None

    def _gradient_placeholder_image(self, value: str) -> Optional[str]:
        raw = self._clean_text(value)
        if not raw:
            return None
        lower = raw.lower()
        if lower.startswith("linear-gradient("):
            svg = self._linear_gradient_svg(raw)
        elif lower.startswith("radial-gradient("):
            svg = self._radial_gradient_svg(raw)
        else:
            return None
        if not svg:
            return None
        return f"data:image/svg+xml;utf8,{quote(svg)}"

    def _linear_gradient_svg(self, raw: str) -> Optional[str]:
        inner = self._function_inner(raw, "linear-gradient")
        if inner is None:
            return None
        parts = self._split_css_args(inner)
        if len(parts) < 2:
            return None
        angle = 180.0
        if self._looks_like_gradient_direction(parts[0]):
            angle = self._gradient_angle(parts.pop(0))
        stops = self._gradient_stops(parts)
        if len(stops) < 2:
            return None
        rad = math.radians(angle)
        dx = math.sin(rad)
        dy = -math.cos(rad)
        x1 = 50.0 - (dx * 50.0)
        y1 = 50.0 - (dy * 50.0)
        x2 = 50.0 + (dx * 50.0)
        y2 = 50.0 + (dy * 50.0)
        stop_markup = "".join(
            f"<stop offset='{offset:.2f}%' stop-color='{escape(color)}' stop-opacity='{opacity:.4f}'/>"
            for offset, color, opacity in stops
        )
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' preserveAspectRatio='none'>"
            f"<defs><linearGradient id='g' gradientUnits='userSpaceOnUse' x1='{x1:.2f}' y1='{y1:.2f}' x2='{x2:.2f}' y2='{y2:.2f}'>{stop_markup}</linearGradient></defs>"
            "<rect x='0' y='0' width='100' height='100' fill='url(#g)'/>"
            "</svg>"
        )

    def _radial_gradient_svg(self, raw: str) -> Optional[str]:
        inner = self._function_inner(raw, "radial-gradient")
        if inner is None:
            return None
        parts = self._split_css_args(inner)
        if len(parts) < 2:
            return None
        if self._looks_like_radial_descriptor(parts[0]):
            parts = parts[1:]
        stops = self._gradient_stops(parts)
        if len(stops) < 2:
            return None
        stop_markup = "".join(
            f"<stop offset='{offset:.2f}%' stop-color='{escape(color)}' stop-opacity='{opacity:.4f}'/>"
            for offset, color, opacity in stops
        )
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' preserveAspectRatio='none'>"
            f"<defs><radialGradient id='g' cx='50%' cy='50%' r='70%'>{stop_markup}</radialGradient></defs>"
            "<rect x='0' y='0' width='100' height='100' fill='url(#g)'/>"
            "</svg>"
        )

    def _function_inner(self, raw: str, fn_name: str) -> Optional[str]:
        lower = raw.lower()
        prefix = f"{fn_name}("
        if not lower.startswith(prefix) or not raw.endswith(")"):
            return None
        return raw[len(prefix):-1].strip()

    def _split_css_args(self, raw: str) -> List[str]:
        parts: List[str] = []
        current: List[str] = []
        depth = 0
        for ch in raw:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            if ch == "," and depth == 0:
                piece = "".join(current).strip()
                if piece:
                    parts.append(piece)
                current = []
                continue
            current.append(ch)
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts

    def _looks_like_gradient_direction(self, token: str) -> bool:
        lowered = self._clean_text(token).lower()
        return lowered.startswith("to ") or lowered.endswith("deg") or lowered.endswith("turn") or lowered.endswith("rad")

    def _looks_like_radial_descriptor(self, token: str) -> bool:
        lowered = self._clean_text(token).lower()
        return any(marker in lowered for marker in ("circle", "ellipse", "closest-", "farthest-", "at "))

    def _gradient_angle(self, token: str) -> float:
        lowered = self._clean_text(token).lower()
        if lowered.startswith("to "):
            dirs = lowered[3:].strip().split()
            x = 0.0
            y = 0.0
            for part in dirs:
                if part == "right":
                    x += 1.0
                elif part == "left":
                    x -= 1.0
                elif part == "bottom":
                    y += 1.0
                elif part == "top":
                    y -= 1.0
            if x == 0.0 and y == 0.0:
                return 180.0
            angle = math.degrees(math.atan2(x, -y))
            return angle % 360.0
        match = re.match(r"(-?\d+(?:\.\d+)?)(deg|turn|rad)", lowered)
        if not match:
            return 180.0
        value = float(match.group(1))
        unit = match.group(2)
        if unit == "turn":
            return (value * 360.0) % 360.0
        if unit == "rad":
            return math.degrees(value) % 360.0
        return value % 360.0

    def _gradient_stops(self, parts: List[str]) -> List[tuple[float, str, float]]:
        parsed: List[tuple[Optional[float], str, float]] = []
        for idx, part in enumerate(parts):
            color_token, offset = self._split_gradient_stop(part)
            color, opacity = self._normalize_gradient_color(color_token)
            if not color:
                continue
            parsed.append((offset, color, opacity))
        if len(parsed) < 2:
            return []
        total = len(parsed) - 1
        resolved: List[tuple[float, str, float]] = []
        for idx, (offset, color, opacity) in enumerate(parsed):
            final_offset = offset if offset is not None else (idx / float(total)) * 100.0
            resolved.append((max(0.0, min(100.0, final_offset)), color, opacity))
        return resolved

    def _split_gradient_stop(self, raw: str) -> tuple[str, Optional[float]]:
        token = self._clean_text(raw)
        depth = 0
        split_at: Optional[int] = None
        for idx in range(len(token) - 1, -1, -1):
            ch = token[idx]
            if ch == ")":
                depth += 1
            elif ch == "(" and depth > 0:
                depth -= 1
            elif ch.isspace() and depth == 0:
                candidate = token[idx + 1:].strip()
                if re.match(r"-?\d+(?:\.\d+)?%$", candidate):
                    split_at = idx
                    break
        if split_at is None:
            return token, None
        color_token = token[:split_at].strip()
        offset_token = token[split_at + 1:].strip()
        try:
            return color_token, float(offset_token.rstrip("%"))
        except Exception:
            return token, None

    def _normalize_gradient_color(self, raw: str) -> tuple[Optional[str], float]:
        token = self._clean_text(raw)
        if not token:
            return None, 1.0
        rgba_match = re.match(
            r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$",
            token,
            re.IGNORECASE,
        )
        if rgba_match:
            r = max(0, min(255, int(round(float(rgba_match.group(1))))))
            g = max(0, min(255, int(round(float(rgba_match.group(2))))))
            b = max(0, min(255, int(round(float(rgba_match.group(3))))))
            opacity = float(rgba_match.group(4)) if rgba_match.group(4) is not None else 1.0
            return f"rgb({r}, {g}, {b})", max(0.0, min(1.0, opacity))
        return token, 1.0

    def _serialize_svg_node(self, node: Dict[str, Any], width: int, height: int) -> Optional[str]:
        tag = self._clean_text(node.get("type") or node.get("tag")).lower()
        if not tag:
            return None
        styles = self._merge_styles(node)
        current_color = (
            self._text_color(styles.get("color"), styles)
            or self._resolve_color(styles.get("fill"), styles)
            or self._resolve_color(styles.get("stroke"), styles)
        )
        attrs = dict((node.get("attributes") or {}))
        normalized_attrs: Dict[str, Any] = {}
        svg_allowed = {
            "xmlns",
            "width",
            "height",
            "viewBox",
            "fill",
            "stroke",
            "stroke-width",
            "stroke-linecap",
            "stroke-linejoin",
            "stroke-miterlimit",
            "fill-rule",
            "clip-rule",
            "d",
            "cx",
            "cy",
            "r",
            "rx",
            "ry",
            "x",
            "y",
            "x1",
            "x2",
            "y1",
            "y2",
            "points",
            "transform",
            "opacity",
            "class",
            "id",
            "preserveAspectRatio",
            "xmlns:xlink",
            "xlink:href",
            "href",
        }
        for raw_key, raw_value in attrs.items():
            key = self._clean_text(raw_key)
            if not key:
                continue
            lowered = key.lower()
            if lowered == "viewbox":
                key = "viewBox"
            elif lowered == "preserveaspectratio":
                key = "preserveAspectRatio"
            elif lowered == "xmlns:xlink":
                key = "xmlns:xlink"
            elif lowered == "xlink:href":
                key = "xlink:href"
            if key == "style":
                continue
            if key not in svg_allowed:
                continue
            if isinstance(raw_value, str) and raw_value.strip().lower() == "currentcolor" and current_color:
                raw_value = current_color
            normalized_attrs[key] = raw_value
        attrs = normalized_attrs
        if tag == "svg":
            attrs.setdefault("xmlns", "http://www.w3.org/2000/svg")
            attrs.setdefault("width", str(width))
            attrs.setdefault("height", str(height))
            if not attrs.get("viewBox"):
                attrs["viewBox"] = f"0 0 {width} {height}"
        attr_parts: List[str] = []
        for key, value in attrs.items():
            if value is None:
                continue
            if isinstance(value, list):
                value = " ".join(str(v) for v in value if v is not None)
            val = self._clean_text(value)
            if not val:
                continue
            attr_parts.append(f"{key}=\"{escape(val, quote=True)}\"")
        attr_blob = (" " + " ".join(attr_parts)) if attr_parts else ""
        children_markup = "".join(
            child_markup
            for child in (node.get("children") or [])
            if isinstance(child, dict)
            for child_markup in [self._serialize_svg_node(child, width=width, height=height)]
            if child_markup
        )
        text_value = ""
        if not children_markup:
            text_value = escape(self._clean_text(node.get("text", "")))
        return f"<{tag}{attr_blob}>{text_value}{children_markup}</{tag}>"

    def _absolutize_url(self, raw_url: Any) -> Optional[str]:
        if raw_url is None:
            return None
        url = self._clean_text(str(raw_url))
        if not url:
            return None
        if (url.startswith("'") and url.endswith("'")) or (url.startswith('"') and url.endswith('"')):
            url = url[1:-1].strip()
        if not url or url.startswith("#") or url.lower().startswith("javascript:"):
            return None
        if url.lower().startswith(("http://", "https://", "data:")):
            return url
        if self.base_url.lower().startswith(("http://", "https://")):
            return urljoin(self.base_url, url)
        return url

    def _extract_css_filter(self, styles: Dict[str, Any]) -> Optional[str]:
        raw = self._clean_text(styles.get("filter", ""))
        if not raw or raw.lower() == "none":
            return None
        return raw

    def _should_use_pseudo_background(self, pseudo_styles: Dict[str, Any], classes: List[str]) -> bool:
        if not isinstance(pseudo_styles, dict) or not pseudo_styles:
            return False
        opacity_raw = self._clean_text(pseudo_styles.get("opacity", ""))
        if not opacity_raw:
            return True
        try:
            opacity = float(opacity_raw)
        except Exception:
            opacity = None
        if opacity is None:
            return True
        if opacity > 0:
            return True
        active_tokens = {"hover", "active", "is-active", "is_active", "current", "selected"}
        return any(token in classes for token in active_tokens)

    def _extract_url_from_style_dict(self, style_dict: Dict[str, Any]) -> Optional[str]:
        if not isinstance(style_dict, dict):
            return None
        for val in style_dict.values():
            url = self._extract_background_image_url(val)
            if url:
                return url
        return None

    def _align_from_styles(self, styles: Dict[str, Any]) -> str:
        align = str(styles.get("text-align", "")).strip().lower()
        if align == "center":
            return "center"
        if align in {"right", "end"}:
            return "right"
        return "left"

    def _parse_font_family(self, styles: Dict[str, Any]) -> Optional[str]:
        raw = styles.get("font-family") or styles.get("font_family")
        if raw is None:
            return None
        s = self._clean_text(raw)
        if not s:
            return None
        parts = [p.strip().strip('"').strip("'") for p in s.split(",") if p.strip()]
        if not parts:
            return None
        first = parts[0]
        if first.lower() in {"inherit", "initial", "unset"}:
            return None
        return first

    def _parse_letter_spacing(self, raw: Any, font_size: int) -> Optional[float]:
        s = self._clean_text(raw).lower()
        if not s or s == "normal":
            return None
        try:
            if s.endswith("px"):
                return float(s.replace("px", ""))
            if s.endswith("em"):
                return float(s.replace("em", "")) * float(font_size or 16)
            if s.endswith("rem"):
                return float(s.replace("rem", "")) * 16.0
            return float(s)
        except Exception:
            return None

    def _apply_text_transform(self, text: str, transform: str) -> str:
        if not text:
            return text
        if "[" in text and "]" in text:
            # Avoid mangling BBCode markup.
            return text
        t = self._clean_text(transform).lower()
        if t == "uppercase":
            return text.upper()
        if t == "lowercase":
            return text.lower()
        if t == "capitalize":
            return " ".join(w[:1].upper() + w[1:] if w else "" for w in text.split(" "))
        return text

    def _parse_line_height(self, raw: Any, font_size: int, heading: bool) -> float:
        s = self._clean_text(raw).lower()
        if not s:
            return 1.1 if heading else 1.4
        if s.endswith("px"):
            try:
                px = float(s.replace("px", ""))
                if font_size > 0:
                    return max(0.8, round(px / float(font_size), 3))
            except Exception:
                return 1.1 if heading else 1.4
        try:
            return max(0.8, float(s))
        except Exception:
            return 1.1 if heading else 1.4

    def _compose_heading_rich_text(self, element: Dict[str, Any], content: str, base_color: str) -> str:
        children = element.get("children", []) or []
        if not children or not content:
            return content
        out = content
        normalized_base = self._normalize_color(base_color)
        for child in children:
            child_text = self._clean_text(child.get("text", ""))
            if not child_text:
                continue
            child_styles = self._merge_styles(child)
            child_color = self._resolve_color(child_styles.get("color"), child_styles)
            if not child_color:
                continue
            if self._normalize_color(child_color) == normalized_base:
                continue
            bb_color = self._to_bbcode_color(child_color)
            if not bb_color:
                continue
            out = out.replace(child_text, f"[color={bb_color}]{child_text}[/color]", 1)
        return out

    def _resolve_color(self, raw: Any, styles: Dict[str, Any]) -> Optional[str]:
        value = self._resolve_css_value(raw, styles)
        return self._normalize_color(value)

    def _normalize_color(self, raw: Any) -> Optional[str]:
        s = self._clean_text(raw).lower()
        if not s:
            return None
        if s in {"transparent", "none", "initial", "inherit"}:
            return None
        return s

    def _to_bbcode_color(self, raw: Any) -> Optional[str]:
        c = self._normalize_color(raw)
        if not c:
            return None
        if c.startswith("#"):
            if len(c) == 4:
                return "#" + "".join(ch * 2 for ch in c[1:]).lower()
            if len(c) == 7:
                return c.lower()
            return None
        m = re.search(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", c)
        if m:
            r = max(0, min(255, int(m.group(1))))
            g = max(0, min(255, int(m.group(2))))
            b = max(0, min(255, int(m.group(3))))
            return f"#{r:02x}{g:02x}{b:02x}"
        return None

    def _text_color(self, raw: Any, styles: Dict[str, Any], default: Optional[str] = None) -> Optional[str]:
        resolved = self._resolve_color(raw, styles) if raw is not None else None
        if not resolved:
            resolved = default
        if not resolved:
            return None
        solid = self._to_bbcode_color(resolved)
        return solid or resolved

    def _is_default_link_blue(self, raw: Any) -> bool:
        c = self._normalize_color(raw)
        if not c:
            return False
        if c in {"#0000ee", "rgb(0, 0, 238)", "rgb(0,0,238)", "rgba(0, 0, 238, 1)", "rgba(0,0,238,1)"}:
            return True
        return False

    def _resolve_css_value(self, raw: Any, styles: Dict[str, Any], depth: int = 0) -> str:
        if depth > 6:
            return self._clean_text(raw)
        s = self._clean_text(raw)
        if not s.startswith("var(") or not s.endswith(")"):
            return s
        body = s[4:-1].strip()
        name, fallback = self._split_var_expr(body)
        resolved = ""
        if name:
            key = name.strip()
            if key in styles:
                resolved = self._resolve_css_value(styles.get(key), styles, depth + 1)
        if not resolved and fallback:
            resolved = self._resolve_css_value(fallback, styles, depth + 1)
        return resolved or s

    def _split_var_expr(self, body: str) -> tuple[str, str]:
        depth = 0
        for idx, ch in enumerate(body):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                left = body[:idx].strip()
                right = body[idx + 1 :].strip()
                return left, right
        return body.strip(), ""

    def _text_width_hint(self, content: str, depth: int, heading: bool) -> int:
        length = len(self._clean_text(content))
        if depth <= 1:
            if heading:
                return 900
            if length <= 60:
                return 700
            return 900
        if heading:
            if length <= 24:
                return 320
            if length <= 64:
                return 420
            return 540
        if length <= 24:
            return 220
        if length <= 80:
            return 360
        return 540

    def _name_from_element(self, element: Dict[str, Any], fallback: str) -> str:
        attrs = element.get("attributes", {}) or {}
        for key in ("data-framer-name", "aria-label", "id", "data-qa", "name"):
            v = self._clean_text(str(attrs.get(key, "")))
            if self._looks_generated_identifier(v):
                continue
            if v:
                return self._humanize_name(v)[:64]
        class_name = self._semantic_name_from_classes(self._classes(attrs))
        if class_name:
            return self._humanize_name(class_name)
        text_hint = self._clean_text(element.get("text", ""))
        if text_hint:
            words = [w for w in re.findall(r"[A-Za-z0-9]+", text_hint) if w][:5]
            if words:
                return self._humanize_name(" ".join(words))[:64]
        node_type = str(element.get("type", "")).strip().lower()
        if node_type in {"ul", "ol"}:
            return self._humanize_name(fallback.strip() or "List")
        descendant_hint = self._descendant_name_hint(element)
        if descendant_hint:
            return self._humanize_name(descendant_hint)
        styles = self._merge_styles(element)
        if node_type in {"section", "article", "main"}:
            return self._humanize_name("Content Section")
        if node_type in {"header", "footer"}:
            return self._humanize_name(f"Page {node_type.title()}")
        if node_type == "img":
            w = self._parse_dimension(styles.get("width")) or 0
            h = self._parse_dimension(styles.get("height")) or 0
            br = self._parse_dimension(styles.get("border-radius")) or 0
            if br >= 40 or (w > 0 and h > 0 and w <= 80 and h <= 80):
                return self._humanize_name("Avatar Photo")
            return self._humanize_name("Content Image")
        if node_type in {"div", "fragment"}:
            return self._humanize_name(fallback.strip() or "Container")
        return self._humanize_name(f"{fallback} {node_type}".strip())

    def _looks_generated_identifier(self, value: str) -> bool:
        s = self._clean_text(value).lower()
        if not s:
            return True
        if s.startswith(("framer-", "hidden-", "variant-", "css-")):
            return True
        # Common short randomized IDs/classnames (e.g. "7pepox", "68gx1i").
        if re.fullmatch(r"[a-z0-9]{5,}", s) and any(ch.isdigit() for ch in s):
            return True
        if re.fullmatch(r"(?:[a-z0-9]{2,}-)+[a-z0-9]{2,}", s):
            parts = [p for p in s.split("-") if p]
            digit_parts = sum(1 for p in parts if any(ch.isdigit() for ch in p))
            if digit_parts >= 1 and all(len(p) <= 8 for p in parts):
                return True
        # Common builder hash-like names without digits (e.g. "ktnuvu", "cmydm").
        if re.fullmatch(r"[a-z]{5,8}", s):
            semantic_allow = {
                "header",
                "footer",
                "button",
                "desktop",
                "mobile",
                "video",
                "image",
                "avatar",
                "section",
                "content",
                "overlay",
                "columns",
                "headline",
                "cta",
            }
            if s not in semantic_allow:
                return True
        return False

    def _semantic_name_from_classes(self, classes: List[str]) -> str:
        if not classes:
            return ""
        candidates: List[str] = []
        for cls in classes:
            for token in re.split(r"[_\-\s]+", cls.strip().lower()):
                t = token.strip()
                if not t:
                    continue
                if t in self.GENERIC_NAME_TOKENS:
                    continue
                if len(t) <= 2:
                    continue
                if re.search(r"\d", t):
                    # Usually a generated/hash fragment in visual builders.
                    continue
                candidates.append(t)
        if not candidates:
            return ""
        return self._humanize_name(" ".join(candidates[:4]))[:64]

    def _descendant_name_hint(self, node: Dict[str, Any]) -> str:
        queue = list(node.get("children", []) or [])
        best_text = ""
        while queue:
            current = queue.pop(0)
            attrs = current.get("attributes", {}) or {}
            for key in ("data-framer-name", "aria-label", "id", "data-qa", "name"):
                v = self._clean_text(str(attrs.get(key, "")))
                if v:
                    return v[:64]
            cls_name = self._semantic_name_from_classes(self._classes(attrs))
            if cls_name:
                return cls_name
            text = self._clean_text(current.get("text", ""))
            if text and len(text) > len(best_text):
                best_text = text
            queue.extend(current.get("children", []) or [])
        if best_text:
            words = [w for w in re.findall(r"[A-Za-z0-9]+", best_text) if w][:5]
            if words:
                return " ".join(words)[:64]
        return ""

    def _is_noise_text(self, text: str) -> bool:
        t = self._clean_text(text).lower()
        if not t:
            return True
        if len(t) > 1200:
            return True
        return any(marker in t for marker in self.NOISE_MARKERS)

    def _deep_text(self, node: Dict[str, Any]) -> str:
        chunks: List[str] = []
        local = self._clean_text(node.get("text", ""))
        if local:
            chunks.append(local)
        for child in node.get("children", []) or []:
            c = self._deep_text(child)
            if c:
                chunks.append(c)
        return self._clean_text(" ".join(chunks))

    def _extract_split_text(self, node: Dict[str, Any]) -> str:
        def collect_letters(n: Dict[str, Any]) -> List[str]:
            letters: List[str] = []
            if not isinstance(n, dict):
                return letters
            t = self._clean_text(n.get("text", ""))
            if t:
                letters.append(t)
            for ch in n.get("children", []) or []:
                letters.extend(collect_letters(ch))
            return letters

        words: List[str] = []
        for line in node.get("children", []) or []:
            if not isinstance(line, dict):
                continue
            if self._has_class_token(line, "split-line"):
                for word_node in line.get("children", []) or []:
                    if not isinstance(word_node, dict):
                        continue
                    letters = collect_letters(word_node)
                    if letters:
                        words.append("".join(letters))
            else:
                letters = collect_letters(line)
                if letters:
                    words.append("".join(letters))
        if words:
            return self._clean_text(" ".join(words))
        letters = collect_letters(node)
        if letters:
            if all(len(tok) == 1 for tok in letters) and len(letters) > 6:
                return self._clean_text("".join(letters))
            return self._clean_text(" ".join(letters))
        return ""

    def _is_hidden_node(self, element: Dict[str, Any], styles: Dict[str, Any]) -> bool:
        display = self._clean_text(styles.get("display", "")).lower()
        visibility = self._clean_text(styles.get("visibility", "")).lower()
        opacity = self._clean_text(styles.get("opacity", ""))
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        if display == "none" or visibility == "hidden":
            return True
        if opacity and opacity in {"0", "0.0"}:
            has_aos_marker = (
                "aos-init" in classes
                or any(cls.startswith("aos-") for cls in classes)
                or bool(attrs.get("data-aos"))
            )
            if not has_aos_marker:
                return True
        if self._has_descendant_tag(element, {"iframe", "video"}):
            return False
        # Treat only explicit utility-hidden markers as hidden. Do not match
        # hashed classnames like "hidden-8e4sdv" used by some builders.
        has_hidden_utility = any(
            token == "hidden" or token.endswith(":hidden") or token == "invisible" or token.endswith(":invisible")
            for token in classes
        )
        if has_hidden_utility and not self._clean_text(element.get("text", "")):
            return True
        rect = element.get("rect", {}) or {}
        rw = self._to_int(rect.get("width"), None)
        rh = self._to_int(rect.get("height"), None)
        if rw is not None and rh is not None and rw <= 1 and rh <= 1:
            classes = self._classes(element.get("attributes", {}) or {})
            if any(cls.startswith("hidden-") for cls in classes):
                return True
            if not self._has_text_content(element) and not self._has_media_content(element):
                return True
        return False

    def _should_skip_background_layer(self, element: Dict[str, Any], styles: Dict[str, Any]) -> bool:
        # Keep background/image wrappers so media URLs survive conversion.
        # Layout decisions are handled downstream (flatten/nonant heuristics).
        return False

    def _should_flatten_node(
        self,
        element: Dict[str, Any],
        styles: Dict[str, Any],
        parent_layout: Optional[str] = None,
    ) -> bool:
        node_type = str(element.get("type", "")).lower()
        if node_type == "fragment":
            return True
        if node_type == "svg":
            return False
        display = self._clean_text(styles.get("display", "")).lower()
        if display == "contents":
            return True

        children = element.get("children", []) or []
        text = self._clean_text(element.get("text", ""))
        if not children:
            return False

        if self._has_descendant_tag(element, {"iframe", "video"}):
            return False

        explicit_w = self._parse_dimension(styles.get("width")) or self._to_int((element.get("rect", {}) or {}).get("width"), None)
        explicit_h = self._parse_dimension(styles.get("height")) or self._to_int((element.get("rect", {}) or {}).get("height"), None)
        if (
            len(children) == 1
            and not text
            and explicit_w is not None
            and explicit_h is not None
            and explicit_w > 1
            and explicit_h > 1
            and self._has_media_content(children[0])
        ):
            return False

        # Preserve full-cover background wrappers until child filtering runs.
        # If we flatten these nodes, the huge background image itself becomes a
        # normal flow child and breaks composition.
        if self._is_full_cover_background_wrapper(element):
            return False
        classes = self._classes(element.get("attributes", {}) or {})
        if "row" in classes:
            return False

        parent_rect = element.get("_parent_rect") or {}
        rect = element.get("rect") or {}
        if isinstance(parent_rect, dict) and isinstance(rect, dict) and parent_rect and rect:
            try:
                parent_x = float(parent_rect.get("x") or parent_rect.get("left") or 0)
                parent_y = float(parent_rect.get("y") or parent_rect.get("top") or 0)
                child_x = float(rect.get("x") or rect.get("left") or 0)
                child_y = float(rect.get("y") or rect.get("top") or 0)
                dx = child_x - parent_x
                dy = child_y - parent_y
                if dx < -2 or dy < -2:
                    return False
            except Exception:
                pass

        # In align-to-parent containers, keep positioned wrappers so we can map
        # their quadrant anchors (nonant_alignment).
        if str(parent_layout or "").lower() == "relative":
            if self._is_absolutely_positioned(styles):
                return False
            parent_rect = element.get("_parent_rect") or {}
            rect = element.get("rect") or {}
            if isinstance(parent_rect, dict) and isinstance(rect, dict) and parent_rect and rect:
                try:
                    parent_x = float(parent_rect.get("x") or parent_rect.get("left") or 0)
                    parent_y = float(parent_rect.get("y") or parent_rect.get("top") or 0)
                    child_x = float(rect.get("x") or rect.get("left") or 0)
                    child_y = float(rect.get("y") or rect.get("top") or 0)
                    dx = child_x - parent_x
                    dy = child_y - parent_y
                    if abs(dx) > 2 or abs(dy) > 2:
                        return False
                except Exception:
                    pass

        # Preserve absolute wrappers that carry explicit offsets so we don't
        # lose top/left/right/bottom positioning information.
        if self._is_absolutely_positioned(styles):
            for key in ("top", "right", "bottom", "left"):
                if self._clean_text(styles.get(key, "")):
                    return False

        # Generic pass-through wrappers (single child and no own box/content).
        if len(children) == 1 and not text and not element.get("media_url") and not self._has_visual_box(styles):
            return True

        # Absolute wrappers around media/icons should not create extra columns.
        if len(children) == 1 and self._is_absolutely_positioned(styles) and not text and not self._covers_parent(styles):
            return True

        # Compact absolute wrappers around avatar/media nodes are usually
        # positioning shells and should not become extra Bubble groups.
        if len(children) == 1 and self._is_absolutely_positioned(styles) and not text:
            w = self._parse_dimension(styles.get("width")) or 0
            h = self._parse_dimension(styles.get("height")) or 0
            if w > 0 and h > 0 and w <= 80 and h <= 80 and self._has_media_content(children[0]):
                return True

        return False

    def _has_visual_box(self, styles: Dict[str, Any]) -> bool:
        if not self._is_transparent_color(styles.get("background-color")):
            return True
        background_image = self._clean_text(styles.get("background-image", "")).lower()
        if background_image and background_image not in {"none"}:
            return True
        border = self._clean_text(styles.get("border", "")).lower()
        if border and "none" not in border:
            return True
        box_shadow = self._clean_text(styles.get("box-shadow", "")).lower()
        if box_shadow and box_shadow not in {"none", "0px 0px 0px 0px transparent"}:
            return True
        radius = self._parse_dimension(styles.get("border-radius")) or 0
        if radius > 0:
            return True
        for key in ("padding-top", "padding-right", "padding-bottom", "padding-left", "gap", "row-gap", "column-gap"):
            val = self._parse_dimension(styles.get(key))
            if val and val > 0:
                return True
        return False

    def _covers_parent(self, styles: Dict[str, Any]) -> bool:
        vals = []
        for key in ("top", "right", "bottom", "left"):
            raw = self._clean_text(styles.get(key, ""))
            if not raw:
                return False
            n = self._parse_dimension(raw)
            vals.append(0 if n is None else n)
        return all(v <= 1 for v in vals)

    def _is_absolutely_positioned(self, styles: Dict[str, Any]) -> bool:
        pos = self._clean_text(styles.get("position", "")).lower()
        return pos in {"absolute", "fixed"}

    def _has_position_offsets(self, styles: Dict[str, Any]) -> bool:
        for key in ("top", "right", "bottom", "left"):
            raw = self._clean_text(styles.get(key, ""))
            if raw and raw not in {"auto"}:
                return True
        return False

    def _is_full_cover_background_wrapper(self, node: Dict[str, Any]) -> bool:
        styles = self._merge_styles(node)
        if not self._is_absolutely_positioned(styles):
            return False
        if not self._covers_parent(styles):
            return False
        if self._clean_text(node.get("text", "")):
            return False
        if not self._has_media_content(node):
            return False
        # Do not classify tiny avatar/media shells as page background wrappers.
        width = self._parse_dimension(styles.get("width")) or self._to_int((node.get("rect", {}) or {}).get("width"), 0) or 0
        height = self._parse_dimension(styles.get("height")) or self._to_int((node.get("rect", {}) or {}).get("height"), 0) or 0
        radius = self._clean_text(styles.get("border-radius", "")).lower()
        if (width and width <= 120 and height and height <= 120) or ("50%" in radius) or ("100%" in radius):
            return False
        return True

    def _has_background_image_layer(self, element: Dict[str, Any]) -> bool:
        parent_rect = element.get("rect", {}) or {}
        parent_w = self._to_int(parent_rect.get("width"), None) or 0
        parent_h = self._to_int(parent_rect.get("height"), None) or 0
        for child in element.get("children", []) or []:
            styles = self._merge_styles(child)
            attrs = child.get("attributes", {}) or {}
            attr_keys = " ".join([str(k).lower() for k in attrs.keys()])
            attr_vals = " ".join([self._clean_text(v).lower() for v in attrs.values() if isinstance(v, (str, int, float))])
            has_marker = "background-image-wrapper" in attr_keys or "background-image-wrapper" in attr_vals
            if self._is_absolutely_positioned(styles) and self._covers_parent(styles) and self._has_media_content(child):
                if has_marker:
                    return True
                child_rect = child.get("rect", {}) or {}
                child_w = self._to_int(child_rect.get("width"), None) or self._parse_dimension(styles.get("width")) or 0
                child_h = self._to_int(child_rect.get("height"), None) or self._parse_dimension(styles.get("height")) or 0
                if parent_w > 0 and parent_h > 0 and child_w > 0 and child_h > 0:
                    area_ratio = (child_w * child_h) / float(parent_w * parent_h)
                    if area_ratio >= 0.70:
                        return True
                elif has_marker:
                    return True
            if has_marker and self._is_full_cover_background_wrapper(child):
                return True
        return False

    def _has_descendant_tag(self, node: Dict[str, Any], tags: set[str]) -> bool:
        for child in node.get("children", []) or []:
            child_tag = str(child.get("tag") or child.get("type") or "").lower()
            if child_tag in tags:
                return True
            if self._has_descendant_tag(child, tags):
                return True
        return False

    def _has_icon_descendant(self, node: Dict[str, Any]) -> bool:
        for child in node.get("children", []) or []:
            if not isinstance(child, dict):
                continue
            child_tag = str(child.get("tag") or child.get("type") or "").lower()
            if child_tag == "i":
                attrs = child.get("attributes", {}) or {}
                classes = self._classes(attrs)
                if not classes:
                    return True
                if any(c.startswith("fa") or "icon" in c for c in classes):
                    return True
            if self._has_icon_descendant(child):
                return True
        return False

    def _has_class_token(self, node: Dict[str, Any], token: str) -> bool:
        attrs = node.get("attributes", {}) or {}
        classes = self._classes(attrs)
        if any(token in c for c in classes):
            return True
        for child in node.get("children", []) or []:
            if not isinstance(child, dict):
                continue
            if self._has_class_token(child, token):
                return True
        return False

    @staticmethod
    def _fontawesome_spec(classes: List[str]) -> Optional[tuple[str, str]]:
        if not classes:
            return None
        style_bucket = "solid"
        if "fa-brands" in classes:
            style_bucket = "brands"
        elif "fa-regular" in classes:
            style_bucket = "regular"
        elif "fa-solid" in classes:
            style_bucket = "solid"
        ignore = {"fa-brands", "fa-solid", "fa-regular", "fa-light", "fa-thin", "fa-duotone"}
        for cls in classes:
            if not cls.startswith("fa-"):
                continue
            if cls in ignore:
                continue
            return style_bucket, cls.replace("fa-", "", 1)
        return None

    def _infer_button_icon(self, element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        styles = self._merge_styles(element)
        label = self._clean_text(element.get("text", "")) or self._deep_text(element)
        label = self._clean_text(label)
        button_rect = element.get("rect", {}) or {}
        try:
            button_center_x = float(button_rect.get("x") or button_rect.get("left") or 0) + (
                float(button_rect.get("width") or 0) / 2.0
            )
        except Exception:
            button_center_x = 0.0

        def _resolve_hint_icon(tokens: List[str]) -> Optional[str]:
            hint_blob = " ".join(tokens)
            if any(token in hint_blob for token in ("play", "video-play", "popup-video")):
                return "phosphor regular play"
            if any(token in hint_blob for token in ("download", "dl")):
                return "phosphor regular download-simple"
            if any(
                token in hint_blob
                for token in (
                    "arrow-right",
                    "angle-right",
                    "caret-right",
                    "chevron-right",
                    "long-arrow-right",
                )
            ):
                return "phosphor regular caret-right"
            if any(
                token in hint_blob
                for token in (
                    "arrow-left",
                    "angle-left",
                    "caret-left",
                    "chevron-left",
                    "long-arrow-left",
                )
            ):
                return "phosphor regular caret-left"
            return None

        best_match: Optional[Dict[str, Any]] = None

        def _walk(node: Dict[str, Any]) -> None:
            nonlocal best_match
            if not isinstance(node, dict) or best_match is not None:
                return
            node_tag = str(node.get("tag") or node.get("type") or "").lower()
            node_attrs = node.get("attributes", {}) or {}
            node_classes = self._classes(node_attrs)
            node_styles = self._merge_styles(node)
            tokens = [c.lower() for c in node_classes]
            raw_blob = " ".join(
                [
                    str(node_attrs.get("aria-label") or "").lower(),
                    str(node_attrs.get("title") or "").lower(),
                    str(node.get("text") or "").lower(),
                    node_tag,
                    " ".join(tokens),
                ]
            )
            icon_name = _resolve_hint_icon(tokens + [raw_blob])
            if icon_name and (node_tag in {"i", "svg", "img", "span"} or self._has_media_content(node)):
                node_rect = node.get("rect", {}) or {}
                icon_color = (
                    self._text_color(node_styles.get("color"), node_styles)
                    or self._resolve_color(node_styles.get("fill"), node_styles)
                    or self._resolve_color(node_styles.get("stroke"), node_styles)
                )
                icon_size = (
                    self._to_int(node_rect.get("width"), None)
                    or self._to_int(node_rect.get("height"), None)
                    or self._parse_dimension(node_styles.get("font-size"))
                )
                try:
                    icon_center_x = float(node_rect.get("x") or node_rect.get("left") or 0) + (
                        float(node_rect.get("width") or 0) / 2.0
                    )
                except Exception:
                    icon_center_x = button_center_x
                best_match = {
                    "icon": icon_name,
                    "icon_color": icon_color,
                    "icon_size": icon_size,
                    "icon_placement": "right" if icon_center_x >= button_center_x else "left",
                }
                return
            for child in node.get("children", []) or []:
                if isinstance(child, dict):
                    _walk(child)

        _walk(element)
        if not best_match:
            root_hint = _resolve_hint_icon(classes + [str(attrs.get("aria-label") or "").lower()])
            if root_hint:
                best_match = {"icon": root_hint}
        if not best_match:
            return None

        button_gap = 10 if label else None
        if label:
            best_match["button_type"] = "label_icon"
            if best_match.get("icon_placement") is None:
                best_match["icon_placement"] = "right"
            best_match["button_gap"] = button_gap
        else:
            best_match["button_type"] = "icon"
            best_match["icon_placement"] = None
        return best_match

    def _svg_placeholder_icon(self, width: int, height: int, color: str = "#111827") -> str:
        w = max(int(width), 8)
        h = max(int(height), 8)
        r = min(w, h) / 2.0
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
            f"<circle cx='{w/2:.2f}' cy='{h/2:.2f}' r='{r:.2f}' fill='{color}'/></svg>"
        )
        return f"data:image/svg+xml;utf8,{quote(svg)}"

    def _should_inline_block_row(self, group_node: Dict[str, Any]) -> bool:
        children = group_node.get("children", []) or []
        if len(children) < 2:
            return False
        inline_like = 0
        for child in children:
            if not isinstance(child, dict):
                continue
            ch_props = child.get("properties", {}) or {}
            w = self._to_int(ch_props.get("width"), 0)
            h = self._to_int(ch_props.get("height"), 0)
            if 8 <= w <= 80 and 8 <= h <= 80:
                inline_like += 1
        return inline_like >= 2 and inline_like == len(children)

    def _infer_inline_block_gap_from_children(self, children: List[Dict[str, Any]]) -> int:
        gaps = []
        for child in children:
            if not isinstance(child, dict):
                continue
            props = child.get("properties", {}) or {}
            ml = self._to_int(props.get("margin_left"), 0) or 0
            mr = self._to_int(props.get("margin_right"), 0) or 0
            if ml or mr:
                gaps.append(ml + mr)
        if gaps:
            gaps.sort()
            return gaps[len(gaps) // 2]
        return 6

    def _is_light_color(self, raw: Any) -> bool:
        hex_color = self._to_bbcode_color(raw)
        if not hex_color or not hex_color.startswith("#") or len(hex_color) != 7:
            return False
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
        except Exception:
            return False
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return luminance >= 200

    def _has_descendant_tag_with_position(
        self,
        node: Dict[str, Any],
        tags: set[str],
        positions: set[str],
    ) -> bool:
        for child in node.get("children", []) or []:
            if not isinstance(child, dict):
                continue
            child_tag = str(child.get("tag") or child.get("type") or "").lower()
            if child_tag in tags:
                styles = self._merge_styles(child)
                pos = self._clean_text(styles.get("position", "")).lower()
                if pos in positions:
                    return True
            if self._has_descendant_tag_with_position(child, tags, positions):
                return True
        return False

    def _is_inline_form_container(self, element: Dict[str, Any], styles: Dict[str, Any]) -> bool:
        attrs = element.get("attributes", {}) or {}
        classes = self._classes(attrs)
        tag = str(element.get("tag") or element.get("type") or "").lower()
        if tag == "form" or "form" in classes or any("form" in c for c in classes):
            pass
        children = [c for c in (element.get("children", []) or []) if isinstance(c, dict)]
        if len(children) < 2:
            return False
        has_input = self._has_descendant_tag(element, {"input", "textarea", "select"})
        has_button = self._has_descendant_tag(element, {"button"})
        if not (has_input and has_button):
            return False
        if tag == "form" or "form" in classes or any("form" in c for c in classes):
            return True
        # Common pattern: absolute-positioned button inside a form wrapper.
        if self._has_descendant_tag_with_position(element, {"button"}, {"absolute", "fixed"}):
            return True
        # Allow inline form if direct children are input + button wrapper.
        direct_input = any(str(c.get("tag") or "").lower() in {"input", "textarea", "select"} for c in children)
        direct_button = any(self._has_descendant_tag(c, {"button"}) for c in children)
        return direct_input and direct_button

    def _infer_inline_form_gap(self, element: Dict[str, Any]) -> int:
        children = [c for c in (element.get("children", []) or []) if isinstance(c, dict)]
        if len(children) < 2:
            return 16
        rects = []
        for ch in children:
            rect = ch.get("rect") or {}
            if not isinstance(rect, dict):
                continue
            try:
                x = float(rect.get("x") or rect.get("left") or 0)
                w = float(rect.get("width") or 0)
                rects.append((x, w))
            except Exception:
                continue
        rects = [r for r in rects if r[1] > 0]
        if len(rects) < 2:
            return 16
        rects.sort(key=lambda r: r[0])
        gaps = []
        for idx in range(1, len(rects)):
            prev_x, prev_w = rects[idx - 1]
            cur_x, _ = rects[idx]
            gap = cur_x - (prev_x + prev_w)
            if gap > 0:
                gaps.append(gap)
        if not gaps:
            return 16
        gap = int(round(sorted(gaps)[0]))
        if gap <= 0:
            return 16
        return max(16, min(gap, 40))

    def _container_fallback_name(
        self,
        element: Dict[str, Any],
        styles: Dict[str, Any],
        depth: int,
        layout: str,
    ) -> str:
        children = element.get("children", []) or []
        has_text = self._has_text_content(element)
        has_media = self._has_media_content(element)
        if depth == 0:
            return "root_section"
        if self._is_full_cover_background_wrapper(element):
            return "background_layer"
        if self._has_descendant_tag(element, {"iframe", "video"}):
            return "video_container"
        if self._has_descendant_tag(element, {"button", "a"}):
            return "cta_container"
        if self._has_descendant_tag(element, {"h1", "h2", "h3", "h4", "h5", "h6"}):
            return "headline_container"
        if self._has_descendant_tag(element, {"img"}) and self._has_text_content(element):
            return "media_text_container"
        if self._has_descendant_tag(element, {"img"}) and not self._has_text_content(element):
            return "image_strip_container"
        if layout == "relative":
            return "overlay_container"
        if layout == "row" and len(children) >= 3:
            return "columns_row"
        if layout == "column" and len(children) >= 3:
            return "content_stack"
        if has_media and not has_text:
            return "media_container"
        if has_text and not has_media:
            return "text_container"
        if layout == "row":
            return f"row_cluster_{depth}"
        if layout == "column":
            return f"stack_cluster_{depth}"
        if layout == "relative":
            return f"overlay_cluster_{depth}"
        return f"content_cluster_{depth}"

    def _humanize_name(self, value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[_\-]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        words = [w for w in text.split(" ") if w]
        return " ".join(words[:8]).strip()

    def _contains_light_text(self, node: Dict[str, Any]) -> bool:
        styles = self._merge_styles(node)
        color = self._clean_text(styles.get("color", "")).lower()
        if color:
            rgb = re.search(r"rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)", color)
            if rgb:
                r, g, b = int(rgb.group(1)), int(rgb.group(2)), int(rgb.group(3))
                if (r + g + b) / 3 >= 185:
                    return True
            if color in {"#fff", "#ffffff", "white"}:
                return True
            if color.startswith("#") and len(color) == 7:
                try:
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)
                    if (r + g + b) / 3 >= 185:
                        return True
                except Exception:
                    pass
        for child in node.get("children", []) or []:
            if self._contains_light_text(child):
                return True
        return False

    def _infer_background_fallback(self, element: Dict[str, Any]) -> Optional[str]:
        if self._contains_light_text(element):
            return "#000000"
        return None

    def _is_transparent_color(self, value: Any) -> bool:
        s = self._clean_text(value).lower()
        if not s:
            return True
        return s in {"transparent", "rgba(0, 0, 0, 0)", "rgba(0,0,0,0)"}

    def _should_keep_explicit_height(self, element: Dict[str, Any], styles: Dict[str, Any], depth: int) -> bool:
        if self._is_absolutely_positioned(styles):
            return True
        if depth == 0:
            return True
        explicit_height = self._parse_dimension(styles.get("height"))
        if explicit_height is not None and explicit_height > 0 and self._has_visual_box(styles):
            return True
        children = element.get("children", []) or []
        if not children:
            return True
        overflow = self._clean_text(styles.get("overflow", "")).lower()
        if overflow in {"auto", "scroll"}:
            return True
        return False

    @staticmethod
    def _clean_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()
