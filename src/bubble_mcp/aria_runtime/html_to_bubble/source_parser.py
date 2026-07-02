from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag


class HTMLParser:
    """Parse HTML into a semantic tree for Bubble mapping."""

    TAILWIND_SPACE = {
        "0": 0,
        "0.5": 2,
        "1": 4,
        "1.5": 6,
        "2": 8,
        "2.5": 10,
        "3": 12,
        "3.5": 14,
        "4": 16,
        "5": 20,
        "6": 24,
        "7": 28,
        "8": 32,
        "9": 36,
        "10": 40,
        "11": 44,
        "12": 48,
        "14": 56,
        "16": 64,
    }

    def __init__(self, base_url: str = ""):
        self.base_url = (base_url or "").strip()
        self._style_rules: List[Dict[str, Any]] = []

    def parse(self, html_string: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html_string or "", "html.parser")
        self._style_rules = self._collect_style_rules(soup)
        root = soup.body or soup
        children = [self.parse_element(child) for child in root.children if isinstance(child, Tag)]
        children = [c for c in children if c]
        return {
            "type": "fragment",
            "text": "",
            "attributes": {},
            "styles": {},
            "computed_styles": {},
            "children": children,
        }

    def parse_snapshot(self, snapshot_node: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a structured DOM snapshot (from Puppeteer extractor) into pipeline tree."""
        root = self._parse_snapshot_node(snapshot_node)
        if not root:
            return {
                "type": "fragment",
                "text": "",
                "attributes": {},
                "styles": {},
                "computed_styles": {},
                "children": [],
            }
        return root

    def parse_element(self, element: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(element, Tag):
            return None

        attrs = self._normalize_attrs(dict(element.attrs))
        classes = attrs.get("class", [])
        styles = self._parse_inline_styles(str(element.get("style", "")))
        computed = self._infer_from_classes(classes)
        if self._style_rules:
            computed.update(self._apply_style_rules(element, attrs))
        text = self._extract_text(element)

        children: List[Dict[str, Any]] = []
        for child in element.children:
            if isinstance(child, Tag):
                parsed = self.parse_element(child)
                if parsed:
                    children.append(parsed)

        node: Dict[str, Any] = {
            "type": element.name.lower(),
            "text": text,
            "attributes": attrs,
            "styles": styles,
            "computed_styles": computed,
            "text_segments": self._extract_text_segments_tag(element, styles),
            "children": children,
        }
        self._inject_media_url(node)
        return node

    def _collect_style_rules(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        rules: List[Dict[str, Any]] = []
        for style_tag in soup.find_all("style"):
            raw = style_tag.string or style_tag.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue
            rules.extend(self._parse_css_rules(raw))
        return rules

    def _parse_css_rules(self, css_text: str) -> List[Dict[str, Any]]:
        cleaned = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
        rules: List[Dict[str, Any]] = []
        for chunk in cleaned.split("}"):
            if "{" not in chunk:
                continue
            selector_raw, body = chunk.split("{", 1)
            selector_raw = selector_raw.strip()
            body = body.strip()
            if not selector_raw or not body:
                continue
            decls = self._parse_inline_styles(body)
            if not decls:
                continue
            selectors = [s.strip() for s in selector_raw.split(",") if s.strip()]
            for sel in selectors:
                rules.append({"selector": sel, "styles": dict(decls)})
        return rules

    def _apply_style_rules(self, element: Tag, attrs: Dict[str, Any]) -> Dict[str, Any]:
        matched: Dict[str, Any] = {}
        tag_name = element.name.lower()
        element_id = str(attrs.get("id", "")).strip()
        classes = attrs.get("class", []) or []
        for rule in self._style_rules:
            selector = str(rule.get("selector", "")).strip()
            if not selector:
                continue
            if not self._selector_matches(tag_name, element_id, classes, selector):
                continue
            for k, v in (rule.get("styles", {}) or {}).items():
                matched[str(k).strip().lower()] = v
        return matched

    def _selector_matches(self, tag: str, element_id: str, classes: List[str], selector: str) -> bool:
        s = selector.strip()
        if not s:
            return False
        if ":" in s:
            s = s.split(":", 1)[0].strip()
        if not s:
            return False
        if any(ch in s for ch in (" ", ">", "+", "~", "[")):
            return False
        if s == "*":
            return True
        if s.startswith("#"):
            return element_id == s[1:]
        if s.startswith("."):
            required = [p for p in s.split(".") if p]
            return all(r in classes for r in required)
        if "." in s:
            tag_part, class_part = s.split(".", 1)
            if tag_part and tag_part != tag:
                return False
            required = [p for p in class_part.split(".") if p]
            return all(r in classes for r in required)
        return s == tag

    def _parse_snapshot_node(self, node: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None
        node_type = str(node.get("type", "")).strip().lower()
        if node_type == "text":
            return None
        if node_type != "element":
            return None

        tag = self._clean_text(str(node.get("tag", ""))).lower() or "div"
        attrs = self._normalize_attrs(dict(node.get("attributes", {}) or {}))
        inline_styles = self._parse_inline_styles(str(attrs.get("style", "")))
        computed = {
            str(k).strip().lower(): str(v).strip()
            for k, v in dict(node.get("computedStyle", {}) or {}).items()
            if str(k).strip() and str(v).strip()
        }
        # Computed style must be the primary visual source. Class inference is
        # only a last-resort fallback when extractor style data is missing.
        if computed:
            merged_computed = dict(computed)
        else:
            merged_computed = dict(self._infer_from_classes(attrs.get("class", [])))
        text = self._clean_text(str(node.get("text", "")))

        children: List[Dict[str, Any]] = []
        for child in list(node.get("children", []) or []):
            parsed_child = self._parse_snapshot_node(child)
            if parsed_child:
                children.append(parsed_child)

        parsed: Dict[str, Any] = {
            "type": tag,
            "text": text,
            "attributes": attrs,
            "styles": inline_styles,
            "computed_styles": merged_computed,
            "pseudo": dict(node.get("pseudo", {}) or {}),
            "text_segments": self._extract_text_segments_snapshot(node, merged_computed),
            "children": children,
            "rect": dict(node.get("rect", {}) or {}),
            "intrinsic": dict(node.get("intrinsic", {}) or {}),
        }
        self._inject_media_url(parsed)
        return parsed

    def _extract_text_segments_snapshot(self, node: Dict[str, Any], base_styles: Dict[str, Any]) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        self._collect_snapshot_segments(node, dict(base_styles or {}), segments)
        return segments

    def _collect_snapshot_segments(
        self,
        node: Dict[str, Any],
        inherited_styles: Dict[str, Any],
        out: List[Dict[str, Any]],
    ) -> None:
        if not isinstance(node, dict):
            return
        node_type = str(node.get("type", "")).strip().lower()
        if node_type == "text":
            raw_text = str(node.get("rawText") or node.get("text") or "")
            txt = self._normalize_segment_raw_text(
                raw_text,
                leading=bool(node.get("leadingSpace")),
                trailing=bool(node.get("trailingSpace")),
            )
            if txt:
                out.append(
                    {
                        "text": txt,
                        "styles": dict(inherited_styles or {}),
                        "raw_text": raw_text,
                        "leading_space": bool(node.get("leadingSpace")),
                        "trailing_space": bool(node.get("trailingSpace")),
                    }
                )
            return
        if node_type != "element":
            return

        tag = str(node.get("tag", "")).strip().lower()
        if tag == "br":
            out.append(
                {
                    "text": "\n",
                    "styles": dict(inherited_styles or {}),
                    "raw_text": "\n",
                    "leading_space": False,
                    "trailing_space": False,
                }
            )
            return

        own_styles = {
            str(k).strip().lower(): str(v).strip()
            for k, v in dict(node.get("computedStyle", {}) or {}).items()
            if str(k).strip() and str(v).strip()
        }
        merged_styles = dict(inherited_styles or {})
        merged_styles.update(own_styles)

        for child in list(node.get("children", []) or []):
            self._collect_snapshot_segments(child, merged_styles, out)

    def _extract_text_segments_tag(self, element: Tag, base_styles: Dict[str, Any]) -> List[Dict[str, Any]]:
        segments: List[Dict[str, Any]] = []
        self._collect_tag_segments(element, dict(base_styles or {}), segments)
        return segments

    def _collect_tag_segments(
        self,
        node: Any,
        inherited_styles: Dict[str, Any],
        out: List[Dict[str, Any]],
    ) -> None:
        if isinstance(node, NavigableString):
            raw_text = str(node)
            txt = self._normalize_segment_raw_text(
                raw_text,
                leading=bool(re.match(r"^\s", raw_text or "")),
                trailing=bool(re.search(r"\s$", raw_text or "")),
            )
            if txt:
                out.append(
                    {
                        "text": txt,
                        "styles": dict(inherited_styles or {}),
                        "raw_text": raw_text,
                        "leading_space": bool(re.match(r"^\s", raw_text or "")),
                        "trailing_space": bool(re.search(r"\s$", raw_text or "")),
                    }
                )
            return
        if not isinstance(node, Tag):
            return

        if node.name and node.name.lower() == "br":
            out.append(
                {
                    "text": "\n",
                    "styles": dict(inherited_styles or {}),
                    "raw_text": "\n",
                    "leading_space": False,
                    "trailing_space": False,
                }
            )
            return

        merged_styles = dict(inherited_styles or {})
        merged_styles.update(self._parse_inline_styles(str(node.get("style", ""))))

        for child in node.children:
            self._collect_tag_segments(child, merged_styles, out)

    def _normalize_attrs(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in attrs.items():
            if isinstance(value, list):
                out[key] = [str(v).strip() for v in value if str(v).strip()]
            else:
                out[key] = str(value).strip()
        if "class" not in out:
            out["class"] = []
        return out

    def _extract_text(self, element: Tag) -> str:
        # Interactive controls often contain nested wrappers; keep full visible label text.
        if element.name and element.name.lower() in {"a", "button", "label"}:
            return self._clean_text(element.get_text(" ", strip=True))

        block_children = any(isinstance(ch, Tag) for ch in element.children)
        if not block_children:
            return self._clean_text(element.get_text(" ", strip=True))

        parts: List[str] = []
        inline_like_tags = {
            "span", "strong", "em", "small", "b", "i", "u", "a", "mark", "label", "code", "sup", "sub"
        }
        for ch in element.children:
            if isinstance(ch, NavigableString):
                t = self._clean_text(str(ch))
                if t:
                    parts.append(t)
            elif isinstance(ch, Tag) and ch.name and ch.name.lower() in inline_like_tags:
                t = self._clean_text(ch.get_text(" ", strip=True))
                if t:
                    parts.append(t)
        joined = self._clean_text(" ".join(parts))
        if joined:
            return joined

        # Some animated headings split each glyph into nested block wrappers.
        # When that happens, fallback to full visible text extraction.
        if element.name and element.name.lower() in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}:
            fallback = self._clean_text(element.get_text(" ", strip=True))
            if fallback:
                return self._compact_fragmented_text(fallback)
        return joined

    def _compact_fragmented_text(self, text: str) -> str:
        t = self._clean_text(text)
        if not t:
            return ""
        tokens = t.split()
        if len(tokens) < 8:
            return t
        alnum_tokens = [re.sub(r"[^A-Za-z0-9]", "", tok) for tok in tokens]
        short_tokens = sum(1 for tok in alnum_tokens if len(tok) <= 1)
        if short_tokens / max(len(tokens), 1) < 0.65:
            return t

        compact = "".join(tokens)
        compact = compact.replace("&", " & ")
        compact = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", compact)
        compact = re.sub(r"\s+", " ", compact).strip()
        return compact or t

    def _parse_inline_styles(self, style_str: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not style_str:
            return out
        for chunk in style_str.split(";"):
            if ":" not in chunk:
                continue
            key, value = chunk.split(":", 1)
            k = key.strip().lower()
            v = value.strip()
            if k and v:
                out[k] = v
        return out

    def _base_tokens(self, classes: List[str]) -> List[str]:
        tokens: List[str] = []
        for cls in classes:
            c = str(cls).strip().lower()
            if not c:
                continue
            tokens.append(c)
            if ":" in c:
                tokens.append(c.split(":")[-1])
        # dedupe preserving order
        seen = set()
        out: List[str] = []
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
        return out

    def _infer_from_classes(self, classes: List[str]) -> Dict[str, str]:
        computed: Dict[str, str] = {}
        tokens = self._base_tokens(classes)

        if "grid" in tokens or any(t.startswith("grid-cols-") for t in tokens):
            computed["display"] = "grid"
            max_cols = 1
            for t in tokens:
                m = re.match(r"grid-cols-(\d+)$", t)
                if m:
                    try:
                        max_cols = max(max_cols, int(m.group(1)))
                    except Exception:
                        pass
            computed["grid-template-columns"] = str(max_cols)

        if (
            "flex" in tokens
            or "d-flex" in tokens
            or "row" in tokens
            or "d-inline-flex" in tokens
        ):
            computed["display"] = "flex"
            if "flex-col" in tokens or "flex-column" in tokens:
                computed["flex-direction"] = "column"
            elif "flex-row" in tokens or "row" in tokens:
                computed["flex-direction"] = "row"

        for t in tokens:
            m = re.match(r"gap-(\d+(?:\.\d+)?)$", t)
            if m:
                gap_token = m.group(1)
                if gap_token in self.TAILWIND_SPACE:
                    computed["gap"] = f"{self.TAILWIND_SPACE[gap_token]}px"
                break
            m = re.match(r"g-(\d+)$", t)  # Bootstrap gap scale
            if m:
                computed["gap"] = f"{int(m.group(1)) * 4}px"
                break

        if "text-center" in tokens:
            computed["text-align"] = "center"
        elif "text-right" in tokens or "text-end" in tokens:
            computed["text-align"] = "right"
        elif "text-left" in tokens or "text-start" in tokens:
            computed["text-align"] = "left"

        if "font-bold" in tokens:
            computed["font-weight"] = "700"
        elif "font-semibold" in tokens:
            computed["font-weight"] = "600"
        elif "font-medium" in tokens:
            computed["font-weight"] = "500"

        for t in tokens:
            m = re.match(r"text-(\d+)xl$", t)
            if m:
                computed["font-size"] = f"{16 + (int(m.group(1)) * 4)}px"
                break
            if t == "text-lg":
                computed["font-size"] = "18px"
                break
            if t == "text-base":
                computed["font-size"] = "16px"
                break
            if t == "text-sm":
                computed["font-size"] = "14px"
                break

        for t in tokens:
            m = re.match(r"py-(\d+(?:\.\d+)?)$", t)
            if m:
                s = self.TAILWIND_SPACE.get(m.group(1))
                if s is not None:
                    computed["padding-top"] = f"{s}px"
                    computed["padding-bottom"] = f"{s}px"
            m = re.match(r"px-(\d+(?:\.\d+)?)$", t)
            if m:
                s = self.TAILWIND_SPACE.get(m.group(1))
                if s is not None:
                    computed["padding-left"] = f"{s}px"
                    computed["padding-right"] = f"{s}px"

        if "bg-white" in tokens:
            computed["background-color"] = "#ffffff"
        return computed

    def _extract_media_from_style(self, styles: Dict[str, str]) -> str:
        bg = f"{styles.get('background', '')} {styles.get('background-image', '')}"
        m = re.search(r"url\(([^)]+)\)", bg, re.IGNORECASE)
        if not m:
            return ""
        return self._absolutize_url(m.group(1))

    def _inject_media_url(self, node: Dict[str, Any]) -> None:
        attrs = node.get("attributes", {}) or {}
        styles = node.get("styles", {}) or {}
        candidates = [
            attrs.get("src"),
            attrs.get("data-src"),
            attrs.get("data-lottie-url"),
            attrs.get("poster"),
            self._extract_media_from_style(styles),
        ]
        for raw in candidates:
            url = self._absolutize_url(raw)
            if url:
                node["media_url"] = url
                return

    def _absolutize_url(self, raw_url: Any) -> str:
        if raw_url is None:
            return ""
        url = self._clean_text(str(raw_url))
        if not url:
            return ""
        if (url.startswith("'") and url.endswith("'")) or (url.startswith('"') and url.endswith('"')):
            url = url[1:-1].strip()
        if not url or url.startswith("#") or url.lower().startswith("javascript:"):
            return ""
        if url.lower().startswith(("http://", "https://", "data:")):
            return url
        if self.base_url.lower().startswith(("http://", "https://")):
            return urljoin(self.base_url, url)
        return url

    def _normalize_segment_raw_text(self, raw_text: str, leading: bool = False, trailing: bool = False) -> str:
        if not raw_text:
            return ""
        raw = str(raw_text)
        if not re.search(r"\S", raw):
            return " "
        core = re.sub(r"\s+", " ", raw).strip()
        if not core:
            return ""
        if leading:
            core = " " + core
        if trailing:
            core = core + " "
        return core

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip())
