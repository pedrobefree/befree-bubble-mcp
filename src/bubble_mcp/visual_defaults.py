"""Deterministic visual creation defaults enforced outside the LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BUTTON_FALLBACK_STYLE = "Button_primary_button_"


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _css_px(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = int(value) if float(value).is_integer() else value
        return f"{number}px"
    text = str(value).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return f"{text}px"
    return text


def _style_is_explicitly_disabled(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {
        "none",
        "null",
        "undefined",
        "custom",
        "none (custom)",
        "none(custom)",
        "no style",
    }


def has_explicit_style_arg(args: dict[str, Any]) -> bool:
    return any(key in args for key in ("style", "style_id", "%s1"))


def _context_metadata(context: Any | None) -> dict[str, Any]:
    metadata = getattr(context, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def project_default_style_id(metadata: dict[str, Any], element_type: str) -> str | None:
    settings = _obj(metadata.get("settings"))
    client_safe = _obj(settings.get("client_safe"))
    default_styles = _obj(client_safe.get("default_styles") or metadata.get("default_styles"))
    style_id = str(default_styles.get(element_type) or "").strip()
    return style_id or None


def style_metadata_from_artifact(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_app = payload.get("app")
    app = raw_app if isinstance(raw_app, dict) else payload
    return {
        "settings": _obj(app.get("settings") or payload.get("settings")),
        "styles": _obj(app.get("styles") or payload.get("styles")),
    }


def default_style_for_element(
    element_type: str,
    *,
    context: Any | None = None,
    metadata: dict[str, Any] | None = None,
    fallback: str | None = None,
) -> str | None:
    merged_metadata = dict(metadata or {})
    merged_metadata.update(_context_metadata(context))
    return project_default_style_id(merged_metadata, element_type) or fallback


def apply_visual_default_args(tool_name: str, args: dict[str, Any], *, context: Any | None = None) -> dict[str, Any]:
    """Apply project-aware defaults that should not depend on agent memory."""

    if tool_name != "create_button":
        return args
    if has_explicit_style_arg(args):
        return args
    style = default_style_for_element("Button", context=context, fallback=BUTTON_FALLBACK_STYLE)
    if style and not _style_is_explicitly_disabled(style):
        args = dict(args)
        args["style"] = style
    return args


def enforce_button_create_payload_quality(
    body: dict[str, Any],
    *,
    context: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Normalize Button create payloads to the required quality baseline."""

    props = body.get("%p")
    if not isinstance(props, dict):
        props = {}
        body["%p"] = props
    height = props.get("%h") if props.get("%h") is not None else 44
    props["%h"] = height
    props["fixed_height"] = True
    props["single_height"] = True
    props["fit_height"] = False
    height_css = _css_px(height)
    if height_css is not None:
        props["min_height_css"] = height_css
        props["max_height_css"] = height_css
    props["fit_width"] = True
    props.setdefault("single_width", False)
    if not body.get("%s1"):
        style = default_style_for_element("Button", context=context, metadata=metadata, fallback=BUTTON_FALLBACK_STYLE)
        if style:
            body["%s1"] = style


def enforce_visual_create_payload_quality(
    body: dict[str, Any],
    *,
    context: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    element_type = str(body.get("%x") or body.get("type") or "").strip()
    if element_type == "Button":
        enforce_button_create_payload_quality(body, context=context, metadata=metadata)
