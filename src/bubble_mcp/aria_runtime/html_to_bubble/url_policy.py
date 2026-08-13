from __future__ import annotations

import base64
import re
from typing import Any, Optional
from urllib.parse import unquote_to_bytes, urljoin, urlsplit


_SVG_DATA_URL = re.compile(
    r"^data:image/svg\+xml(?:;charset=[^;,]+)?(?P<base64>;base64)?,(?P<payload>.*)$",
    flags=re.IGNORECASE | re.DOTALL,
)
_RASTER_DATA_URL = re.compile(
    r"^data:image/(?:png|jpe?g|gif|webp|avif);base64,[A-Za-z0-9+/=_-]+$",
    flags=re.IGNORECASE,
)
_UNSAFE_SVG = re.compile(
    r"<(?:script|foreignobject|iframe|object|embed)\b|\bon[a-z]+\s*=|(?:javascript|vbscript)\s*:|<!entity\b|<!doctype\b",
    flags=re.IGNORECASE,
)


def _safe_svg_data_url(url: str) -> bool:
    match = _SVG_DATA_URL.fullmatch(url)
    if not match:
        return False
    try:
        payload = unquote_to_bytes(match.group("payload"))
        if match.group("base64"):
            payload = base64.b64decode(payload, validate=False)
        svg = payload.decode("utf-8", errors="strict").strip()
    except (UnicodeDecodeError, ValueError):
        return False
    if not svg.lower().startswith("<svg") or _UNSAFE_SVG.search(svg):
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
