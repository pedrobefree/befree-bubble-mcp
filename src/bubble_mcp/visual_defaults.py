"""Deterministic visual creation defaults enforced outside the LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FALLBACK_STYLES_BY_ELEMENT_TYPE = {
    "Button": "Button_primary_button_",
    "Input": "Input_std_dash_",
    "Dropdown": "Dropdown_dash_std_",
    "Checkbox": "Checkbox_standard",
    "DateInput": "DateInput_standard",
}
STYLE_DEFAULT_ELEMENT_TYPES = {
    "Text",
    "Icon",
    "Link",
    "Image",
    "Shape",
    "Alert",
    "VideoPlayer",
    "HTML",
    "Map",
    "Group",
    "RepeatingGroup",
    "Popup",
    "FloatingGroup",
    "GroupFocus",
    "Table",
    "Button",
    "Input",
    "MultiLineInput",
    "Dropdown",
    "AutocompleteDropdown",
    "Checkbox",
    "RadioButtons",
    "SliderInput",
    "DateInput",
    "FileInput",
    "PictureInput",
}
CREATE_TOOL_ELEMENT_TYPES = {
    "create_text": "Text",
    "create_icon": "Icon",
    "create_link": "Link",
    "create_image": "Image",
    "create_shape": "Shape",
    "create_alert": "Alert",
    "create_video": "VideoPlayer",
    "create_html": "HTML",
    "create_map": "Map",
    "create_group": "Group",
    "create_repeating_group": "RepeatingGroup",
    "create_popup": "Popup",
    "create_floating_group": "FloatingGroup",
    "create_group_focus": "GroupFocus",
    "create_table": "Table",
    "create_button": "Button",
    "create_input": "Input",
    "create_multiline_input": "MultiLineInput",
    "create_dropdown": "Dropdown",
    "create_searchbox": "AutocompleteDropdown",
    "create_checkbox": "Checkbox",
    "create_radio": "RadioButtons",
    "create_slider": "SliderInput",
    "create_datepicker": "DateInput",
    "create_file_uploader": "FileInput",
    "create_picture_uploader": "PictureInput",
}
DEFAULT_STYLE_LOOKUP_ALIASES = {
    "AutocompleteDropdown": ("AutocompleteDropdown", "SearchBox", "Searchbox"),
    "DateInput": ("DateInput", "DatePicker"),
    "FloatingGroup": ("FloatingGroup", "Floating Group"),
    "GroupFocus": ("GroupFocus", "Group Focus"),
    "MultiLineInput": ("MultiLineInput", "MultilineInput", "Multiline Input"),
    "PictureInput": ("PictureInput", "PictureUploader", "Picture Uploader"),
    "RadioButtons": ("RadioButtons", "RadioButton"),
    "RepeatingGroup": ("RepeatingGroup", "Repeating Group"),
    "VideoPlayer": ("VideoPlayer", "Video"),
}


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
    for key in DEFAULT_STYLE_LOOKUP_ALIASES.get(element_type, (element_type,)):
        style_id = str(default_styles.get(key) or "").strip()
        if style_id:
            return style_id
    return None


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


def fallback_style_for_element(element_type: str) -> str | None:
    return FALLBACK_STYLES_BY_ELEMENT_TYPE.get(element_type)


def apply_visual_default_args(tool_name: str, args: dict[str, Any], *, context: Any | None = None) -> dict[str, Any]:
    """Apply project-aware defaults that should not depend on agent memory."""

    element_type = CREATE_TOOL_ELEMENT_TYPES.get(tool_name)
    if element_type is None:
        return args
    if has_explicit_style_arg(args):
        return args
    style = default_style_for_element(element_type, context=context, fallback=fallback_style_for_element(element_type))
    if style and not _style_is_explicitly_disabled(style):
        args = dict(args)
        args["style"] = style
    return args


def _style_should_be_replaced(existing: Any, project_style: str | None) -> bool:
    if not project_style:
        return False
    if not existing:
        return True
    return str(existing).strip() in set(FALLBACK_STYLES_BY_ELEMENT_TYPE.values())


def enforce_default_style(
    body: dict[str, Any],
    element_type: str,
    *,
    context: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if element_type not in STYLE_DEFAULT_ELEMENT_TYPES:
        return
    project_style = default_style_for_element(element_type, context=context, metadata=metadata)
    fallback_style = fallback_style_for_element(element_type)
    existing = body.get("%s1")
    if _style_should_be_replaced(existing, project_style):
        body["%s1"] = project_style
    elif not existing and fallback_style:
        body["%s1"] = fallback_style


def enforce_button_create_payload_quality(
    body: dict[str, Any],
    *,
    context: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Apply Button style defaults without overriding the declared size policy."""

    enforce_default_style(body, "Button", context=context, metadata=metadata)


def enforce_visual_create_payload_quality(
    body: dict[str, Any],
    *,
    context: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    element_type = str(body.get("%x") or body.get("type") or "").strip()
    if element_type == "Button":
        enforce_button_create_payload_quality(body, context=context, metadata=metadata)
    else:
        enforce_default_style(body, element_type, context=context, metadata=metadata)
