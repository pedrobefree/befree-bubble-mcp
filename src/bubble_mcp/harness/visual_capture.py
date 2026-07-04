"""Capture structured visual snapshots from HTML, files, or URLs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag


JsonObject = dict[str, Any]


STYLE_FIELDS = [
    "display",
    "position",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "lineHeight",
    "letterSpacing",
    "color",
    "background",
    "backgroundColor",
    "backgroundImage",
    "borderRadius",
    "boxShadow",
    "maxWidth",
    "minWidth",
    "minHeight",
    "width",
    "height",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "marginTop",
    "marginRight",
    "marginBottom",
    "marginLeft",
    "gap",
    "rowGap",
    "columnGap",
    "flexDirection",
    "alignItems",
    "justifyContent",
    "objectFit",
]


def _source_type(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return "url"
    path = Path(source).expanduser()
    if path.exists():
        return "file"
    return "html"


def _read_source_text(source: str, source_type: str) -> str:
    if source_type == "url":
        response = requests.get(source, timeout=20)
        response.raise_for_status()
        return response.text
    if source_type == "file":
        return Path(source).expanduser().read_text(encoding="utf-8")
    return source


def _raw_node(tag: Tag, *, depth: int = 0, max_nodes: int = 250, counter: list[int] | None = None) -> JsonObject:
    if counter is None:
        counter = [0]
    counter[0] += 1
    attrs = tag.attrs
    raw_classes = attrs.get("class")
    classes = [str(item) for item in raw_classes] if isinstance(raw_classes, list) else []
    if not classes and raw_classes:
        classes = [str(raw_classes)]
    direct_text = " ".join(
        str(child).strip()
        for child in tag.children
        if isinstance(child, str) and str(child).strip()
    )
    node: JsonObject = {
        "id": str(attrs.get("id") or ""),
        "tag": tag.name,
        "type": "image" if tag.name == "img" else tag.name,
        "class": " ".join(str(item) for item in classes if str(item).strip()),
        "text": direct_text,
        "bbox": {},
        "style": {},
        "depth": depth,
    }
    if tag.name == "img":
        node["src"] = str(attrs.get("src") or "")
        node["alt"] = str(attrs.get("alt") or "")
    children: list[JsonObject] = []
    for child in tag.children:
        if counter[0] >= max_nodes:
            break
        if isinstance(child, Tag):
            children.append(_raw_node(child, depth=depth + 1, max_nodes=max_nodes, counter=counter))
    if children:
        node["children"] = children
    return node


def _flatten_nodes(node: JsonObject) -> list[JsonObject]:
    nodes = [_without_children(node)]
    raw_children = node.get("children")
    if isinstance(raw_children, list):
        for child in raw_children:
            if isinstance(child, dict):
                nodes.extend(_flatten_nodes(child))
    return nodes


def _without_children(node: JsonObject) -> JsonObject:
    return {key: value for key, value in node.items() if key != "children"}


def _raw_snapshot(source: str, selector: str, *, max_nodes: int, warnings: list[str]) -> JsonObject:
    source_type = _source_type(source)
    html = _read_source_text(source, source_type)
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(selector) if selector else soup.body or soup
    if root is None or not isinstance(root, Tag):
        return {
            "ok": False,
            "source_type": source_type,
            "selector": selector,
            "rendered": False,
            "error": f"Selector not found: {selector}",
            "warnings": warnings,
        }
    root_node = _raw_node(root, max_nodes=max_nodes)
    return {
        "ok": True,
        "source_type": source_type,
        "selector": selector,
        "rendered": False,
        "viewport": None,
        "root": _without_children(root_node),
        "nodes": _flatten_nodes(root_node),
        "warnings": warnings,
    }


def _capture_rendered(
    source: str,
    selector: str,
    *,
    viewport_width: int,
    viewport_height: int,
    wait_ms: int,
    max_nodes: int,
) -> JsonObject:
    from playwright.sync_api import sync_playwright

    source_type = _source_type(source)
    html = "" if source_type == "url" else _read_source_text(source, source_type)
    js = """
    ({ selector, styleFields, maxNodes }) => {
      const root = selector ? document.querySelector(selector) : document.body;
      if (!root) return { ok: false, error: `Selector not found: ${selector}` };
      let count = 0;
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width >= 0 && rect.height >= 0;
      };
      const ownText = (el) => Array.from(el.childNodes)
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent.trim())
        .filter(Boolean)
        .join(' ');
      const textFor = (el) => {
        const tag = el.tagName.toLowerCase();
        const direct = ownText(el);
        if (direct) return direct;
        if (['h1','h2','h3','h4','h5','h6','p','span','a','button','label','li'].includes(tag)) {
          return (el.innerText || '').trim();
        }
        return el.getAttribute('aria-label') || el.getAttribute('alt') || '';
      };
      const nodeFor = (el, depth) => {
        count += 1;
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        const stylePayload = {};
        for (const key of styleFields) stylePayload[key] = style[key] || '';
        const tag = el.tagName.toLowerCase();
        const node = {
          id: el.id || '',
          name: el.getAttribute('name') || el.getAttribute('data-name') || '',
          tag,
          type: tag === 'img' ? 'image' : tag,
          class: el.className && typeof el.className === 'string' ? el.className : '',
          text: textFor(el),
          bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          style: stylePayload,
          depth
        };
        if (tag === 'img') {
          node.src = el.currentSrc || el.src || '';
          node.alt = el.alt || '';
          node.natural_width = el.naturalWidth || null;
          node.natural_height = el.naturalHeight || null;
        }
        const children = [];
        for (const child of Array.from(el.children)) {
          if (count >= maxNodes) break;
          if (visible(child)) children.push(nodeFor(child, depth + 1));
        }
        if (children.length) node.children = children;
        return node;
      };
      const rootNode = nodeFor(root, 0);
      const flat = [];
      const walk = (node) => {
        flat.push(node);
        for (const child of node.children || []) walk(child);
      };
      walk(rootNode);
      return { ok: true, root: rootNode, nodes: flat };
    }
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height})
            if source_type == "url":
                page.goto(source, wait_until="networkidle")
            else:
                page.set_content(html, wait_until="networkidle")
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            captured = page.evaluate(js, {"selector": selector, "styleFields": STYLE_FIELDS, "maxNodes": max_nodes})
        finally:
            browser.close()
    if not isinstance(captured, dict):
        raise ValueError("Rendered visual capture returned an invalid payload.")
    root = captured.get("root")
    if isinstance(root, dict):
        captured["root"] = _without_children(root)
    nodes = captured.get("nodes")
    if isinstance(nodes, list):
        captured["nodes"] = [_without_children(node) if isinstance(node, dict) else node for node in nodes]
    captured.setdefault("warnings", [])
    captured.update(
        {
            "source_type": source_type,
            "selector": selector,
            "rendered": True,
            "viewport": {"width": viewport_width, "height": viewport_height},
        }
    )
    return captured


def capture_visual_snapshot(
    source: str,
    *,
    selector: str = "",
    rendered_html: bool = True,
    viewport_width: int = 1365,
    viewport_height: int = 768,
    wait_ms: int = 0,
    max_nodes: int = 250,
    allow_raw_fallback: bool = True,
    output: Path | None = None,
) -> JsonObject:
    """Capture a structured visual snapshot and optionally write it to disk."""

    if not source.strip():
        raise ValueError("source is required.")
    warnings: list[str] = []
    if rendered_html:
        try:
            snapshot = _capture_rendered(
                source,
                selector,
                viewport_width=viewport_width,
                viewport_height=viewport_height,
                wait_ms=wait_ms,
                max_nodes=max_nodes,
            )
        except Exception as exc:
            if not allow_raw_fallback:
                raise
            warnings.append(f"Rendered capture unavailable; used raw HTML fallback ({exc.__class__.__name__}).")
            snapshot = _raw_snapshot(source, selector, max_nodes=max_nodes, warnings=warnings)
    else:
        snapshot = _raw_snapshot(source, selector, max_nodes=max_nodes, warnings=warnings)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        snapshot["output"] = str(output)
    return snapshot
