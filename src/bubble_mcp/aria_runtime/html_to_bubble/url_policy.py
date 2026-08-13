from __future__ import annotations

import base64
import re
from typing import Any, Optional
from urllib.parse import unquote_to_bytes, urljoin, urlsplit
from xml.etree import ElementTree


_SVG_DATA_URL = re.compile(
    r"^data:image/svg\+xml(?:;charset=[^;,]+)?(?P<base64>;base64)?,(?P<payload>.*)$",
    flags=re.IGNORECASE | re.DOTALL,
)
_RASTER_DATA_URL = re.compile(
    r"^data:image/(?:png|jpe?g|gif|webp|avif);base64,[A-Za-z0-9+/=_-]+$",
    flags=re.IGNORECASE,
)
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_SAFE_SVG_TAGS = {
    "svg",
    "g",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
}
_SAFE_SVG_ATTRIBUTES = {
    "id",
    "viewBox",
    "width",
    "height",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "d",
    "points",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-dasharray",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "transform",
    "preserveAspectRatio",
    "offset",
    "stop-color",
    "stop-opacity",
    "gradientUnits",
    "gradientTransform",
    "spreadMethod",
    "clip-path",
    "mask",
    "fill-rule",
    "clip-rule",
}


def _xml_name(raw: str) -> tuple[str, str]:
    if raw.startswith("{") and "}" in raw:
        namespace, local = raw[1:].split("}", 1)
        return namespace, local
    return "", raw


def _safe_paint_reference(value: str) -> bool:
    lowered = value.strip().lower()
    if "url(" not in lowered:
        return True
    return bool(re.fullmatch(r"url\(#[A-Za-z_][A-Za-z0-9_.:-]*\)", value.strip()))


def _safe_svg_data_url(url: str) -> bool:
    match = _SVG_DATA_URL.fullmatch(url)
    if not match:
        return False
    try:
        payload = unquote_to_bytes(match.group("payload"))
        if match.group("base64"):
            payload = base64.b64decode(payload, validate=False)
        if len(payload) > 1_000_000 or b"<!" in payload or b"<?" in payload:
            return False
        svg = payload.decode("utf-8", errors="strict").strip()
        root = ElementTree.fromstring(svg)
    except (ElementTree.ParseError, UnicodeDecodeError, ValueError):
        return False
    root_namespace, root_name = _xml_name(root.tag)
    if root_name != "svg" or root_namespace not in {"", _SVG_NAMESPACE}:
        return False
    for element in root.iter():
        namespace, name = _xml_name(element.tag)
        if namespace not in {"", _SVG_NAMESPACE} or name not in _SAFE_SVG_TAGS:
            return False
        if element.text and element.text.strip():
            return False
        if element.tail and element.tail.strip():
            return False
        for raw_name, raw_value in element.attrib.items():
            attr_namespace, attr_name = _xml_name(raw_name)
            if attr_namespace or attr_name not in _SAFE_SVG_ATTRIBUTES:
                return False
            value = str(raw_value).strip()
            if not _safe_paint_reference(value) or any(ord(char) < 32 for char in value):
                return False
    return True


def normalize_media_url(raw_url: Any, *, base_url: str = "") -> Optional[str]:
    """Return a safe web/image URL or ``None`` for active and local schemes."""
    if raw_url is None:
        return None
    url = str(raw_url).strip()
    if (url.startswith("'") and url.endswith("'")) or (url.startswith('"') and url.endswith('"')):
        url = url[1:-1].strip()
    if not url or url.startswith("#"):
        return None
    if any(char.isspace() or ord(char) < 32 for char in url):
        return None
    if re.search(r"%(?:0[0ad]|1[0-9a-f])", url, flags=re.IGNORECASE):
        return None

    lowered = url.lower()
    if lowered.startswith("data:"):
        if _RASTER_DATA_URL.fullmatch(url) or _safe_svg_data_url(url):
            return url
        return None

    parsed = urlsplit(url)
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        return url

    normalized_base = str(base_url or "").strip()
    if url.startswith("//"):
        if urlsplit(normalized_base).scheme.lower() not in {"http", "https"}:
            return None
        return normalize_media_url(urljoin(normalized_base, url))
    if url.startswith(("/", "./", "../")) or ":" not in url.split("/", 1)[0]:
        if urlsplit(normalized_base).scheme.lower() in {"http", "https"}:
            return normalize_media_url(urljoin(normalized_base, url))
        return url
    return None
