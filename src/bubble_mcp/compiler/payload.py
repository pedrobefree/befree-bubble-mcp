"""Minimal Bubble editor payload compiler.

This module intentionally keeps the payload surface small and explicit. It
compiles supported plan steps into Bubble `/appeditor/write` `CreateElement`
changes, using the same high-level envelope shape as Aria's Bubble SDK.
"""

from __future__ import annotations

import json
import random
import string
import time
from typing import Any

from bubble_mcp.aria_runtime.bubble_sdk import ElementBuilder
from bubble_mcp.context.models import BubbleProjectContext


ROOT_PARENT_NAMES = {"", "root", "page", "index"}
VISUAL_CREATE_TYPES = {
    "create_text": "Text",
    "create_group": "Group",
    "create_button": "Button",
    "create_input": "Input",
    "create_multiline_input": "MultiLineInput",
    "create_dropdown": "Dropdown",
    "create_searchbox": "AutocompleteDropdown",
    "create_checkbox": "Checkbox",
    "create_datepicker": "DateInput",
    "create_radio": "RadioButtons",
    "create_slider": "SliderInput",
    "create_file_uploader": "FileInput",
    "create_picture_uploader": "PictureInput",
    "create_shape": "Shape",
    "create_video": "VideoPlayer",
    "create_image": "Image",
    "create_icon": "Icon",
    "create_html": "HTML",
    "create_link": "Link",
    "create_alert": "Alert",
    "create_map": "Map",
    "create_popup": "Popup",
    "create_floating_group": "FloatingGroup",
    "create_group_focus": "GroupFocus",
    "create_repeating_group": "RepeatingGroup",
    "create_table": "Table",
    "create_reusable_instance": "ReusableElement",
}
ARIA_BUILDER_METHODS = {
    "create_text": "text",
    "create_group": "group",
    "create_button": "button",
    "create_input": "input",
    "create_dropdown": "dropdown",
    "create_checkbox": "checkbox",
    "create_datepicker": "date_picker",
    "create_radio": "radio_button",
    "create_slider": "slider",
    "create_file_uploader": "file_uploader",
    "create_picture_uploader": "picture_uploader",
    "create_shape": "shape",
    "create_video": "video_player",
    "create_image": "image",
    "create_icon": "icon",
    "create_html": "html",
    "create_link": "link",
    "create_alert": "alert",
    "create_map": "google_map",
    "create_popup": "popup",
    "create_floating_group": "floating_group",
    "create_repeating_group": "repeating_group",
}
CREATE_NAME_PREFIXES = {
    "create_button": "bt_",
    "create_text": "tx_",
    "create_icon": "ic_",
    "create_link": "li_",
    "create_image": "im_",
    "create_shape": "sh_",
    "create_alert": "al_",
    "create_video": "vd_",
    "create_html": "html_",
    "create_map": "map_",
    "create_group": "gp_",
    "create_repeating_group": "rg_",
    "create_popup": "pp_",
    "create_floating_group": "fg_",
    "create_group_focus": "gf_",
    "create_table": "tb_",
    "create_input": "in_",
    "create_multiline_input": "mli_",
    "create_checkbox": "cb_",
    "create_dropdown": "dd_",
    "create_searchbox": "sb_",
    "create_radio": "rb_",
    "create_slider": "sl_",
    "create_datepicker": "dtp_",
    "create_picture_uploader": "pu_",
    "create_file_uploader": "fu_",
}
CREATE_DEFAULT_ARGS: dict[str, dict[str, Any]] = {
    "create_button": {"fit_width": True, "fit_height": True},
    "create_text": {"fit_height": True},
    "create_icon": {"width": 20, "height": 20, "fixed_width": True, "fixed_height": True},
    "create_link": {"label": "Link label"},
    "create_image": {"width": 120, "fixed_width": True, "min_height": 64},
    "create_shape": {"width": 120, "height": 120, "fixed_width": True, "fixed_height": True},
    "create_alert": {"content": "Alert content", "at_to_top": True, "fit_height": True},
    "create_video": {
        "video_id": "id",
        "use_aspect_ratio": True,
        "aspect_ratio_width": 16,
        "aspect_ratio_height": 9,
        "width": 360,
        "fixed_width": True,
    },
    "create_html": {"content": "<html>...</html>", "fit_height": True, "min_height": 120, "width": 240, "fixed_width": True},
    "create_map": {"width": 360, "fixed_width": True, "height": 240, "fixed_height": True},
    "create_group": {"layout": "column", "min_height": 40, "fit_height": True, "min_width": 40},
    "create_repeating_group": {
        "data_type": "text",
        "cell_min_height": 32,
        "cell_min_width": 32,
        "stable_pagination": True,
        "min_width": 120,
        "min_height": 120,
        "fit_height": True,
    },
    "create_popup": {"min_width": 320, "fit_width": True, "min_height": 320, "fit_height": True},
    "create_floating_group": {
        "float_v_relative": "top",
        "float_h_relative": "left",
        "float_zindex": "front",
        "min_width": 0,
        "min_height": 64,
        "fit_height": True,
    },
    "create_group_focus": {"min_width": 0, "min_height": 64, "fit_height": True, "max_width": 320},
    "create_table": {
        "table_direction": "vertical",
        "stable_pagination": True,
        "min_height": 120,
        "min_width": 120,
        "fit_height": True,
    },
    "create_input": {"height": 44, "fixed_height": True, "min_width": 0, "max_width": 240},
    "create_multiline_input": {"min_height": 64, "fit_height": True, "min_width": 0, "max_width": 240},
    "create_checkbox": {"label": "Checkbox label", "min_height": 0, "min_width": 0, "fit_width": True, "fit_height": True},
    "create_dropdown": {"height": 44, "fixed_height": True, "min_width": 0, "max_width": 240},
    "create_searchbox": {"placeholder": "Search...", "height": 44, "fixed_height": True, "min_width": 0, "max_width": 240},
    "create_radio": {"min_height": 0, "min_width": 0, "fit_width": True, "fit_height": True},
    "create_slider": {"height": 32, "fixed_height": True, "min_width": 0, "max_width": 240},
    "create_datepicker": {"height": 44, "fixed_height": True, "min_width": 0, "max_width": 240},
    "create_picture_uploader": {"min_width": 0, "max_width": 240, "height": 64, "fixed_height": True},
    "create_file_uploader": {"min_width": 0, "max_width": 240, "height": 64, "fixed_height": True},
}
POST_CREATE_PROPERTY_KEYS = {
    "%3",
    "%w",
    "%h",
    "%t",
    "%l",
    "%z",
    "%fs",
    "%fc",
    "%fa",
    "%9i",
    "width",
    "height",
    "fit_width",
    "fit_height",
    "fixed_width",
    "fixed_height",
    "single_width",
    "single_height",
    "min_width_css",
    "max_width_css",
    "min_height_css",
    "max_height_css",
    "container_layout",
    "use_gap",
    "row_gap",
    "column_gap",
    "button_type",
    "cell_min_height",
    "cell_min_width",
    "stable_pagination",
    "at_to_top",
    "float_v_relative",
    "float_h_relative",
    "float_zindex",
    "use_aspect_ratio",
    "aspect_ratio_width",
    "aspect_ratio_height",
    "table_direction",
    "font_size",
    "font_color",
    "font_family",
    "font_weight",
    "font_alignment",
    "line_height",
    "letter_spacing",
    "horiz_alignment",
    "vert_alignment",
    "container_horiz_alignment",
    "container_vert_alignment",
    "nonant_alignment",
    "align_to_parent_pos",
    "padding_top",
    "padding_right",
    "padding_bottom",
    "padding_left",
    "margin_top",
    "margin_right",
    "margin_bottom",
    "margin_left",
    "border_width",
    "border_color",
    "border_radius",
    "%br",
    "%bgc",
    "%bas",
}
POST_CREATE_PROPERTY_ORDER = (
    "button_type",
    "%9i",
    "%3",
    "%fs",
    "font_size",
    "font_family",
    "font_weight",
    "%fc",
    "font_color",
    "%fa",
    "font_alignment",
    "line_height",
    "letter_spacing",
    "%w",
    "%h",
    "%t",
    "%l",
    "%z",
    "width",
    "height",
    "fit_width",
    "fit_height",
    "fixed_width",
    "fixed_height",
    "single_width",
    "single_height",
    "min_width_css",
    "max_width_css",
    "min_height_css",
    "max_height_css",
    "container_layout",
    "use_gap",
    "row_gap",
    "column_gap",
    "horiz_alignment",
    "vert_alignment",
    "container_horiz_alignment",
    "container_vert_alignment",
    "nonant_alignment",
    "align_to_parent_pos",
    "padding_top",
    "padding_right",
    "padding_bottom",
    "padding_left",
    "margin_top",
    "margin_right",
    "margin_bottom",
    "margin_left",
    "border_width",
    "border_color",
    "border_radius",
    "%br",
    "%bgc",
    "%bas",
    "cell_min_height",
    "cell_min_width",
    "stable_pagination",
    "at_to_top",
    "float_v_relative",
    "float_h_relative",
    "float_zindex",
    "use_aspect_ratio",
    "aspect_ratio_width",
    "aspect_ratio_height",
    "table_direction",
)
VISUAL_UPDATE_TOOLS = {
    "update_text",
    "update_text_element",
    "update_group",
    "update_group_focus",
    "update_floating_group",
    "update_repeating_group",
    "update_table",
    "update_button",
    "update_input",
    "update_multiline_input",
    "update_dropdown",
    "update_searchbox",
    "update_link",
    "update_alert",
    "update_image",
    "update_image_element",
    "update_icon",
    "update_icon_element",
    "update_checkbox",
    "update_datepicker",
    "update_radio",
    "update_slider",
    "update_file_uploader",
    "update_picture_uploader",
    "update_shape",
    "update_video",
    "update_map",
    "update_html",
    "update_popup",
    "update_layout",
    "update_name",
    "update_placeholder",
    "update_style",
}
VISUAL_DELETE_TOOLS = {
    "delete_element",
    "delete_text",
    "delete_button",
    "delete_checkbox",
    "delete_radio",
    "delete_input",
    "delete_multiline_input",
    "delete_dropdown",
    "delete_datepicker",
    "delete_file_uploader",
    "delete_picture_uploader",
    "delete_searchbox",
    "delete_slider",
    "delete_icon",
    "delete_image",
    "delete_link",
    "delete_shape",
    "delete_alert",
    "delete_video",
    "delete_html",
    "delete_map",
    "delete_group",
    "delete_group_focus",
    "delete_floating_group",
    "delete_repeating_group",
    "delete_table",
    "delete_popup",
}
AUTH_WORKFLOW_ACTION_TOOLS = {
    "log_the_user_in",
    "log_the_user_out",
    "sign_the_user_up",
    "signup_login_with_a_social_network",
    "send_confirmation_email",
    "make_changes_to_current_user",
    "update_user_credentials",
}


def bubble_element_id(length: int = 5) -> str:
    chars = string.ascii_letters + string.digits
    return "b" + "".join(random.choice(chars) for _ in range(length - 1))


def bubble_session_id() -> str:
    return f"{int(time.time() * 1000)}x{random.randint(10, 99)}"


def resolve_context_key(name: str, context: BubbleProjectContext | None = None) -> str:
    target = str(name or "index").strip()
    if context is not None:
        for node in context.nodes:
            if node.type not in {"page", "reusable"}:
                continue
            if (
                node.label == target
                or node.id == target
                or node.id.endswith(f":{target}")
                or str(node.metadata.get("bubble_id") or "") == target
                or str(node.metadata.get("key") or "") == target
            ):
                meta_key = node.metadata.get("bubble_id") or node.metadata.get("key")
                return str(meta_key or node.label or target)
    if ":" in target:
        return target.split(":", 1)[1]
    return target


def resolve_context_root_id(name: str, context: BubbleProjectContext | None = None) -> str | None:
    target = str(name or "index").strip()
    if context is not None:
        for node in context.nodes:
            if node.type not in {"page", "reusable"}:
                continue
            if (
                node.label == target
                or node.id == target
                or node.id.endswith(f":{target}")
                or str(node.metadata.get("bubble_id") or "") == target
                or str(node.metadata.get("key") or "") == target
            ):
                root_id = node.metadata.get("root_id") or node.metadata.get("root")
                return str(root_id).strip() or None
    return None


def resolve_context_node_id(name: str, context: BubbleProjectContext | None = None) -> str | None:
    target = str(name or "index").strip()
    if context is not None:
        for node in context.nodes:
            if node.type not in {"page", "reusable"}:
                continue
            if (
                node.label == target
                or node.id == target
                or node.id.endswith(f":{target}")
                or str(node.metadata.get("bubble_id") or "") == target
                or str(node.metadata.get("key") or "") == target
            ):
                return node.id
    return None


def resolve_context_root_token(name: str, context: BubbleProjectContext | None = None, args: dict[str, Any] | None = None) -> str:
    if str((args or {}).get("context_type") or "").strip().lower() == "reusable":
        return "%ed"
    target = str(name or "index").strip()
    if context is not None:
        for node in context.nodes:
            if node.type not in {"page", "reusable"}:
                continue
            if (
                node.label == target
                or node.id == target
                or node.id.endswith(f":{target}")
                or str(node.metadata.get("bubble_id") or "") == target
                or str(node.metadata.get("key") or "") == target
            ):
                raw_path = node.metadata.get("path_array")
                if isinstance(raw_path, list) and raw_path:
                    return str(raw_path[0])
                if node.type == "reusable":
                    return "%ed"
    return "%p3"


def resolve_workflow_key(args: dict[str, Any], context: BubbleProjectContext | None = None) -> str:
    explicit = str(args.get("workflow_id") or args.get("event_id") or "").strip()
    if explicit:
        return explicit
    event_ref = str(args.get("event_ref") or "").strip()
    if not event_ref:
        raise ValueError("workflow_id or event_ref is required.")
    context_node_id = resolve_context_node_id(str(args.get("context") or "index"), context)
    if context is not None:
        for node in context.nodes:
            if node.type != "workflow":
                continue
            if context_node_id and str(node.metadata.get("context") or "") not in {"", context_node_id}:
                continue
            if (
                node.label == event_ref
                or node.id == event_ref
                or node.id.endswith(f":{event_ref}")
                or str(node.metadata.get("bubble_id") or "") == event_ref
                or str(node.metadata.get("key") or "") == event_ref
            ):
                return str(node.metadata.get("bubble_id") or node.metadata.get("key") or node.id.rsplit(":", 1)[-1])
    if ":" in event_ref:
        return event_ref.split(":", 1)[1]
    return event_ref


def resolve_existing_children(args: dict[str, Any]) -> list[str]:
    raw = args.get("existing_children") or args.get("parent_children") or []
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        try:
            import json

            decoded = json.loads(stripped)
            if isinstance(decoded, list):
                return [str(item) for item in decoded if str(item).strip()]
        except Exception:
            return [part.strip() for part in stripped.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    return []


def resolve_parent_index_id(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    context_name: str,
) -> str:
    explicit_id = str(args.get("parent_id") or args.get("root_id") or "").strip()
    if explicit_id:
        return explicit_id

    parent = str(args.get("parent") or "").strip()
    if parent.lower() in ROOT_PARENT_NAMES:
        return resolve_context_root_id(context_name, context) or ""

    if parent and context is not None:
        for node in context.nodes:
            if node.type != "element":
                continue
            if node.label == parent or node.id == parent or node.id.endswith(f":{parent}"):
                element_id = str(node.metadata.get("bubble_id") or node.metadata.get("key") or "").strip()
                return element_id or node.id.rsplit(":", 1)[-1]

    return parent if parent and parent.lower() not in ROOT_PARENT_NAMES else ""


def resolve_context_children(
    parent_id: str,
    *,
    context: BubbleProjectContext | None,
    context_name: str,
    parent: str,
) -> list[str]:
    if context is None:
        return []
    target_parent = str(parent or "").strip()
    target_id = str(parent_id or "").strip()
    target_context = str(context_name or "").strip()
    for node in context.nodes:
        if node.type == "element":
            matches = (
                node.id == target_id
                or node.id.endswith(f":{target_id}")
                or str(node.metadata.get("bubble_id") or "") == target_id
                or node.label == target_parent
                or node.id == target_parent
                or node.id.endswith(f":{target_parent}")
            )
        else:
            matches = (
                node.type in {"page", "reusable"}
                and (
                    node.label == target_context
                    or node.id == target_context
                    or node.id.endswith(f":{target_context}")
                    or str(node.metadata.get("bubble_id") or "") == target_context
                    or str(node.metadata.get("key") or "") == target_context
                    or str(node.metadata.get("root_id") or "") == target_id
                )
            )
        if matches:
            children = node.metadata.get("children")
            if isinstance(children, list):
                return [str(item) for item in children if str(item).strip()]
    return []


def resolve_parent_path(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None = None,
) -> list[str]:
    context_key = resolve_context_key(str(args.get("context") or "index"), context)
    root_key = "%ed" if str(args.get("context_type") or "").strip().lower() == "reusable" else "%p3"
    parent = str(args.get("parent") or "").strip()
    path = [root_key, context_key]
    if parent.lower() in ROOT_PARENT_NAMES or parent == context_key:
        return path

    if context is not None:
        for node in context.nodes:
            if node.type != "element":
                continue
            if node.label == parent or node.id == parent or node.id.endswith(f":{parent}"):
                raw_path = node.metadata.get("path_array")
                if isinstance(raw_path, list) and raw_path:
                    return [str(item) for item in raw_path]
                element_key = str(node.metadata.get("bubble_id") or node.metadata.get("key") or "").strip()
                if element_key:
                    return [*path, "%el", element_key]

    return [*path, "%el", parent]


def create_change(path_array: list[str], body: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "CreateElement",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def update_index_change(path_array: list[str], body: Any, session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "Update index",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def set_data_change(path_array: list[str], body: Any, session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "SetData",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def create_action_change(path_array: list[str], body: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "CreateAction",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def change_app_setting_change(path_array: list[str], body: Any, session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "ChangeAppSetting",
        },
        "path_array": path_array,
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def create_visual_element_changes(
    args: dict[str, Any],
    body: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    context_name = str(args.get("context") or "index")
    context_key = str(args.get("context_key") or args.get("page_id") or "").strip() or resolve_context_key(
        context_name,
        context,
    )
    parent_path = resolve_parent_path({**args, "context": context_key}, context=context)
    object_id = str(body.get("id") or "").strip() or bubble_element_id()
    body["id"] = object_id
    slot_key = str(args.get("slot_key") or args.get("element_key") or "").strip() or bubble_element_id()
    if parent_path[-2:] == ["%el", slot_key]:
        create_path = parent_path
    elif parent_path[-1] == slot_key:
        create_path = parent_path
    else:
        create_path = [*parent_path, "%el", slot_key]
    full_path = ".".join(create_path)

    parent_id = resolve_parent_index_id(args, context=context, context_name=context_name)

    changes = [
        update_index_change(["_index", "id_to_path", object_id], full_path, session_id),
        create_change(create_path, body, session_id),
    ]
    raw_props = body.get("%p")
    props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
    ordered_keys = [key for key in POST_CREATE_PROPERTY_ORDER if key in props]
    ordered_keys.extend(sorted(key for key in POST_CREATE_PROPERTY_KEYS if key in props and key not in ordered_keys))
    for key in ordered_keys:
        if key in props:
            changes.append(set_data_change([*create_path, "%p", key], props[key], session_id))
    changes.append(update_index_change(["_index", "issues_list", object_id], "[]", session_id))
    if parent_id:
        children = resolve_existing_children(args) or resolve_context_children(
            parent_id,
            context=context,
            context_name=context_name,
            parent=str(args.get("parent") or ""),
        )
        if object_id not in children:
            children.append(object_id)
        import json

        changes.append(
            update_index_change(
                ["_index", "issues_sub", parent_id],
                json.dumps(children, separators=(",", ":")),
                session_id,
            )
        )
    if args.get("id_counter") is not None:
        changes.append({"type": "id_counter", "value": int(args["id_counter"])})
    return changes


def delete_change(path_array: list[str], session_id: str) -> dict[str, Any]:
    return {
        "intent": {
            "name": "Delete",
            "id": random.randint(2, 999),
            "source_appname": "",
        },
        "path_array": path_array,
        "body": None,
        "version_control_api_version": 4,
        "changelog_data": [],
        "session_id": session_id,
    }


def slug_key(value: str, prefix: str = "") -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in str(value).strip())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return f"{prefix}{normalized}" if prefix and not normalized.startswith(prefix) else normalized


def css_px(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return "0px"
    if text.endswith(("px", "%", "rem", "em", "vh", "vw")):
        return text
    return f"{text}px"


def text_expression(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    return {"%x": "TextExpression", "%e": {"0": str(value)}}


def normalize_element_name(tool_name: str, args: dict[str, Any], element_type: str) -> str:
    raw_name = str(args.get("name") or args.get("element_name") or "").strip()
    if not raw_name:
        raw_name = str(
            args.get("label")
            or args.get("content")
            or args.get("placeholder")
            or args.get("video_id")
            or element_type
        ).strip()
    normalized = slug_key(raw_name or element_type)
    prefix = CREATE_NAME_PREFIXES.get(tool_name, "")
    return normalized if not prefix or normalized.startswith(prefix) else f"{prefix}{normalized}"


def apply_create_defaults(tool_name: str, args: dict[str, Any], *, element_type: str) -> dict[str, Any]:
    merged = dict(CREATE_DEFAULT_ARGS.get(tool_name, {}))
    merged.update(args)
    merged["name"] = normalize_element_name(tool_name, merged, element_type)
    return merged


def first_present(*values: Any) -> Any | None:
    for value in values:
        if value is not None:
            return value
    return None


def apply_dimension_properties(properties: dict[str, Any], args: dict[str, Any]) -> None:
    if args.get("width") is not None:
        properties["%w"] = int(args["width"])
    if args.get("height") is not None:
        properties["%h"] = int(args["height"])
    if args.get("min_width") is not None:
        properties["min_width_css"] = css_px(args["min_width"])
    if args.get("max_width") is not None:
        properties["max_width_css"] = css_px(args["max_width"])
    if args.get("min_height") is not None:
        properties["min_height_css"] = css_px(args["min_height"])
    if args.get("max_height") is not None:
        properties["max_height_css"] = css_px(args["max_height"])
    if args.get("fit_width") is not None:
        properties["fit_width"] = bool(args["fit_width"])
    if args.get("fit_height") is not None:
        properties["fit_height"] = bool(args["fit_height"])
    if args.get("fixed_width") is True:
        properties["fixed_width"] = True
        properties["single_width"] = True
        properties["fit_width"] = False
        fixed_width = first_present(args.get("width"), args.get("max_width"), args.get("min_width"))
        if fixed_width is not None:
            fixed_width_css = css_px(fixed_width)
            properties["min_width_css"] = fixed_width_css
            properties["max_width_css"] = fixed_width_css
    elif args.get("single_width") is not None:
        properties["single_width"] = bool(args["single_width"])
    if args.get("fixed_height") is True:
        properties["fixed_height"] = True
        properties["single_height"] = True
        properties["fit_height"] = False
        fixed_height = first_present(args.get("height"), args.get("max_height"), args.get("min_height"))
        if fixed_height is not None:
            fixed_height_css = css_px(fixed_height)
            properties["min_height_css"] = fixed_height_css
            properties["max_height_css"] = fixed_height_css
    elif args.get("single_height") is not None:
        properties["single_height"] = bool(args["single_height"])


def _aria_builder_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Translate catalog args to the Aria ElementBuilder method surface."""
    kwargs = dict(args)
    kwargs.pop("context", None)
    kwargs.pop("context_key", None)
    kwargs.pop("context_type", None)
    kwargs.pop("parent", None)
    kwargs.pop("parent_id", None)
    kwargs.pop("root_id", None)
    kwargs.pop("existing_children", None)
    kwargs.pop("slot_key", None)
    kwargs.pop("element_key", None)
    kwargs.pop("id_counter", None)

    name = str(kwargs.get("name") or "").strip()
    if name:
        kwargs["name"] = name

    if tool_name == "create_text":
        kwargs["content"] = str(kwargs.get("content") or kwargs.get("text") or "")
        if "style" in kwargs and "style_id" not in kwargs:
            kwargs["style_id"] = kwargs.pop("style")
    elif tool_name == "create_button":
        kwargs["label"] = str(kwargs.get("label") or kwargs.get("content") or kwargs.get("text") or kwargs.get("name") or "Button")
        if kwargs.get("icon") and not kwargs.get("button_type"):
            kwargs["button_type"] = "label_icon"
    elif tool_name in {"create_link", "create_checkbox"}:
        kwargs["label"] = str(kwargs.get("label") or kwargs.get("content") or kwargs.get("name") or "Label")
    elif tool_name == "create_alert":
        kwargs["content"] = str(kwargs.get("content") or kwargs.get("label") or "Alert content")
    elif tool_name == "create_html":
        kwargs["content"] = str(kwargs.get("content") or "<html>...</html>")
    elif tool_name == "create_image":
        kwargs["source_url"] = str(
            kwargs.get("source_url")
            or kwargs.get("image_url")
            or kwargs.get("url")
            or kwargs.get("src")
            or ""
        )
    elif tool_name == "create_icon":
        kwargs["icon_name"] = str(kwargs.get("icon_name") or kwargs.get("icon") or "feather check-circle")
        kwargs["color"] = str(kwargs.get("color") or kwargs.get("font_color") or "#000000")
    elif tool_name == "create_repeating_group":
        if "type_of_content" in kwargs and "data_type" not in kwargs:
            kwargs["data_type"] = kwargs["type_of_content"]
    elif tool_name == "create_video":
        kwargs["video_id"] = str(kwargs.get("video_id") or "id")

    if "bg_color" in kwargs and "background_color" not in kwargs:
        kwargs["background_color"] = kwargs["bg_color"]
    if "font_color" in kwargs and "text_color" not in kwargs:
        kwargs["text_color"] = kwargs["font_color"]
    return kwargs


def _normalize_aria_body(body: dict[str, Any], *, element_type: str, name: str) -> dict[str, Any]:
    props = body.get("%p")
    if not isinstance(props, dict):
        props = {}
        body["%p"] = props
    body.setdefault("%x", element_type)
    body.setdefault("type", element_type)
    if name:
        body.setdefault("%dn", name)
        props.setdefault("%nm", name)
    props.pop("__explicit_dims", None)
    return body


def apply_catalog_argument_properties(properties: dict[str, Any], args: dict[str, Any], *, element_type: str) -> None:
    """Persist MCP catalog defaults that the Aria builder may not encode directly."""
    apply_dimension_properties(properties, args)
    for source_key, wire_key in (
        ("placeholder", "placeholder"),
        ("initial_content", "initial_content"),
        ("font_size", "%fs"),
        ("font_color", "%fc"),
        ("font_alignment", "%fa"),
        ("bg_color", "%bgc"),
        ("background_style", "%bas"),
        ("border_radius", "%br"),
        ("url", "url"),
        ("image_url", "image_url"),
        ("icon", "%9i"),
        ("video_id", "video_id"),
        ("data_source", "%ds"),
        ("data_type", "%gt"),
        ("type_of_content", "%gt"),
        ("tooltip", "tooltip"),
        ("at_to_top", "at_to_top"),
        ("cell_min_height", "cell_min_height"),
        ("cell_min_width", "cell_min_width"),
        ("stable_pagination", "stable_pagination"),
        ("float_v_relative", "float_v_relative"),
        ("float_h_relative", "float_h_relative"),
        ("float_zindex", "float_zindex"),
        ("use_aspect_ratio", "use_aspect_ratio"),
        ("aspect_ratio_width", "aspect_ratio_width"),
        ("aspect_ratio_height", "aspect_ratio_height"),
        ("table_direction", "table_direction"),
    ):
        if args.get(source_key) is not None:
            properties[wire_key] = args[source_key]
    if args.get("cell_min_height") is not None:
        properties["cell_min_height_css"] = css_px(args["cell_min_height"])
    if args.get("cell_min_width") is not None:
        properties["cell_min_width_css"] = css_px(args["cell_min_width"])
    if element_type in {"Group", "FloatingGroup", "GroupFocus", "RepeatingGroup", "Table", "Popup"}:
        layout = str(args.get("layout") or "").strip().lower().replace("-", "_").replace(" ", "_")
        if layout:
            if layout == "align_to_parent":
                layout = "relative"
            properties["container_layout"] = layout
        if args.get("row_gap") is not None or args.get("column_gap") is not None:
            properties.setdefault("use_gap", True)
        for source_key, wire_key in (("row_gap", "row_gap"), ("column_gap", "column_gap")):
            if args.get(source_key) is not None:
                properties[wire_key] = args[source_key]


def resolve_element_path(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None = None,
) -> list[str]:
    element_name = str(args.get("element_name") or args.get("name") or args.get("target") or "").strip()
    if not element_name:
        raise ValueError("element_name is required.")
    context_key = resolve_context_key(str(args.get("context") or "index"), context)
    root_path = ["%p3", context_key]
    if context is not None:
        for node in context.nodes:
            if node.type != "element":
                continue
            if node.label == element_name or node.id == element_name or node.id.endswith(f":{element_name}"):
                raw_path = node.metadata.get("path_array")
                if isinstance(raw_path, list) and raw_path:
                    return [str(item) for item in raw_path]
                element_key = str(node.metadata.get("bubble_id") or node.metadata.get("key") or "").strip()
                if element_key:
                    return [*root_path, "%el", element_key]
    return [*root_path, "%el", element_name]


def compile_create_text_step(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
) -> dict[str, Any]:
    args = apply_create_defaults("create_text", args, element_type="Text")
    content = str(args.get("content") or "").strip()
    if not content:
        raise ValueError("create_text requires content.")
    name = str(args.get("name") or "").strip()
    body = ElementBuilder().text(**_aria_builder_args("create_text", args))
    body = _normalize_aria_body(body, element_type="Text", name=name)
    apply_catalog_argument_properties(body["%p"], args, element_type="Text")
    return body


def collect_visual_properties(args: dict[str, Any], *, element_type: str) -> dict[str, Any]:
    name = str(args.get("name") or args.get("element_name") or f"Generated {element_type}").strip()
    properties: dict[str, Any] = {"%nm": name}
    content_key = "%ht" if element_type == "HTML" else "%3"
    label_key = "%lab" if element_type == "Checkbox" else "%3"
    mapping = {
        "content": content_key,
        "html": "%ht",
        "text": "%3",
        "label": label_key,
        "placeholder": "placeholder",
        "initial_content": "initial_content",
        "font_size": "%fs",
        "font_color": "%fc",
        "font_alignment": "%fa",
        "bg_color": "%bgc",
        "background_style": "%bas",
        "border_radius": "%br",
        "url": "url",
        "image_url": "image_url",
        "icon": "%9i",
        "video_id": "video_id",
        "data_source": "%ds",
        "data_type": "%gt",
        "type_of_content": "%gt",
        "style": "%s1",
        "tooltip": "tooltip",
        "at_to_top": "at_to_top",
        "cell_min_height": "cell_min_height",
        "cell_min_width": "cell_min_width",
        "stable_pagination": "stable_pagination",
        "float_v_relative": "float_v_relative",
        "float_h_relative": "float_h_relative",
        "float_zindex": "float_zindex",
        "use_aspect_ratio": "use_aspect_ratio",
        "aspect_ratio_width": "aspect_ratio_width",
        "aspect_ratio_height": "aspect_ratio_height",
        "table_direction": "table_direction",
    }
    for source_key, wire_key in mapping.items():
        if args.get(source_key) is not None:
            value = args[source_key]
            if wire_key in {"%3", "%lab", "%ht"}:
                value = text_expression(value)
            properties[wire_key] = value
    apply_dimension_properties(properties, args)
    if element_type in {"Group", "FloatingGroup", "GroupFocus", "RepeatingGroup", "Table", "Popup"}:
        layout = str(args.get("layout") or "column").strip().lower().replace("-", "_").replace(" ", "_")
        if layout == "align_to_parent":
            layout = "relative"
        properties["container_layout"] = layout
        for source_key, wire_key in (
            ("row_gap", "row_gap"),
            ("column_gap", "column_gap"),
            ("rows", "%rs"),
            ("columns", "columns"),
        ):
            if args.get(source_key) is not None:
                properties[wire_key] = args[source_key]
    return properties


def compile_create_visual_step(
    tool_name: str,
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
) -> dict[str, Any]:
    element_type = VISUAL_CREATE_TYPES[tool_name]
    args = apply_create_defaults(tool_name, args, element_type=element_type)
    builder_method = ARIA_BUILDER_METHODS.get(tool_name)
    if builder_method:
        method = getattr(ElementBuilder(), builder_method)
        body = method(**_aria_builder_args(tool_name, args))
        body = _normalize_aria_body(body, element_type=element_type, name=str(args.get("name") or ""))
        props = body.get("%p")
        if isinstance(props, dict):
            apply_catalog_argument_properties(props, args, element_type=element_type)
        return body
    properties = collect_visual_properties(args, element_type=element_type)
    return {
        "%x": element_type,
        "type": element_type,
        "%dn": str(args.get("name") or ""),
        "%p": properties,
        "id": bubble_element_id(),
    }


def compile_create_group_step(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
) -> dict[str, Any]:
    args = apply_create_defaults("create_group", args, element_type="Group")
    name = str(args.get("name") or "").strip()
    if not name:
        raise ValueError("create_group requires name.")
    body = ElementBuilder().group(**_aria_builder_args("create_group", args))
    body = _normalize_aria_body(body, element_type="Group", name=name)
    apply_catalog_argument_properties(body["%p"], args, element_type="Group")
    return body


def update_element_type_for_tool(tool_name: str) -> str:
    suffix = tool_name.removeprefix("update_")
    if suffix.endswith("_element"):
        suffix = suffix.removesuffix("_element")
    return VISUAL_CREATE_TYPES.get(f"create_{suffix}", "Element")


def compile_update_text_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    content = str(args.get("content") or args.get("new_text") or "").strip()
    if not content:
        raise ValueError("update_text requires content/new_text.")
    path = [*resolve_element_path(args, context=context), "%p", "%3"]
    return [set_data_change(path, text_expression(content), session_id)]


def compile_update_group_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    path = [*resolve_element_path(args, context=context), "%p"]
    properties: dict[str, Any] = {}
    for source_key, wire_key in (
        ("layout", "container_layout"),
        ("row_gap", "row_gap"),
        ("column_gap", "column_gap"),
        ("background_style", "%bas"),
        ("bg_color", "%bgc"),
        ("border_radius", "%br"),
        ("name", "%nm"),
    ):
        if args.get(source_key) is not None:
            value = args[source_key]
            if source_key == "layout":
                value = str(value).strip().lower().replace("-", "_").replace(" ", "_")
                if value == "align_to_parent":
                    value = "relative"
            properties[wire_key] = value
    if not properties:
        raise ValueError("update_group requires at least one supported property.")
    return [set_data_change(path, properties, session_id)]


def compile_update_visual_changes(
    tool_name: str,
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    path = [*resolve_element_path(args, context=context), "%p"]
    element_type = update_element_type_for_tool(tool_name)
    properties = collect_visual_properties(args, element_type=element_type)
    properties = {key: value for key, value in properties.items() if key != "%nm" or args.get("name") is not None}
    if args.get("content") is not None or args.get("new_text") is not None:
        content_key = "%ht" if element_type == "HTML" else "%3"
        properties[content_key] = text_expression(args.get("content") if args.get("content") is not None else args.get("new_text"))
    if not properties:
        raise ValueError("update tool requires at least one supported property.")
    return [set_data_change(path, properties, session_id)]


def compile_delete_element_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    return [delete_change(resolve_element_path(args, context=context), session_id)]


def compile_schema_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    if tool_name == "create_data_type":
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("create_data_type requires name.")
        key = str(args.get("key") or slug_key(name)).strip()
        return [
            set_data_change(
                ["data_types", key],
                {"%nm": name, "name": name, "key": key, "fields": {}},
                session_id,
            )
        ]
    if tool_name == "create_data_field":
        data_type = str(args.get("data_type_key") or args.get("type") or "").strip()
        field_name = str(args.get("field_name") or args.get("name") or "").strip()
        field_type = str(args.get("field_type") or "text").strip()
        if not data_type or not field_name:
            raise ValueError("create_data_field requires data_type_key and field_name.")
        field_key = str(args.get("field_key") or slug_key(field_name)).strip()
        return [
            set_data_change(
                ["data_types", data_type, "fields", field_key],
                {"%nm": field_name, "name": field_name, "type": field_type, "key": field_key},
                session_id,
            )
        ]
    return []


def compile_option_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    if tool_name == "create_option_set":
        name = str(args.get("name") or "").strip()
        if not name:
            raise ValueError("create_option_set requires name.")
        key = str(args.get("key") or slug_key(name, "os_")).strip()
        return [
            set_data_change(
                ["option_sets", key],
                {"%nm": name, "name": name, "key": key, "values": {}},
                session_id,
            )
        ]
    if tool_name == "create_option_value":
        option_set = str(args.get("option_set_key") or "").strip()
        label = str(args.get("label") or args.get("name") or "").strip()
        if not option_set or not label:
            raise ValueError("create_option_value requires option_set_key and label.")
        value_key = str(args.get("value_key") or bubble_element_id()).strip()
        db_value = str(args.get("db_value") or slug_key(label)).strip()
        return [
            set_data_change(
                ["option_sets", option_set, "values", value_key],
                {"%nm": label, "label": label, "db_value": db_value, "key": value_key},
                session_id,
            )
        ]
    return []


def compile_theme_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    if tool_name in {"create_color", "update_color"}:
        name = str(args.get("name") or "").strip()
        rgba = str(args.get("rgba") or args.get("color") or "").strip()
        if not name or not rgba:
            raise ValueError(f"{tool_name} requires name and rgba/color.")
        key = str(args.get("key") or slug_key(name, "color_")).strip()
        return [
            set_data_change(
                ["styles", "colors", key],
                {"%nm": name, "name": name, "rgba": rgba, "description": args.get("description") or ""},
                session_id,
            )
        ]
    if tool_name == "create_style":
        name = str(args.get("name") or "").strip()
        element_type = str(args.get("element_type") or args.get("type") or "").strip()
        if not name or not element_type:
            raise ValueError("create_style requires name and element_type.")
        key = str(args.get("key") or slug_key(name, "style_")).strip()
        properties = {"%nm": name, "name": name, "element_type": element_type}
        for source_key in ("font_size", "font_color", "bg_color", "border_radius", "font_weight"):
            if args.get(source_key) is not None:
                properties[source_key] = args[source_key]
        return [set_data_change(["styles", key], properties, session_id)]
    return []


def compile_workflow_changes(tool_name: str, args: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    context_key = resolve_context_key(str(args.get("context") or "index"))
    if tool_name == "create_workflow":
        event = str(args.get("event") or "click").strip()
        element_name = str(args.get("element_name") or "").strip()
        workflow_id = str(args.get("workflow_id") or bubble_element_id()).strip()
        workflow_body: dict[str, Any] = {
            "%p": {
                "%nm": str(args.get("name") or f"{event} {element_name}".strip()),
                "event": event,
                "element_name": element_name,
            },
            "actions": {},
        }
        return [set_data_change(["%p3", context_key, "%wf", workflow_id], workflow_body, session_id)]
    if tool_name == "add_action":
        workflow_id = str(args.get("workflow_id") or args.get("event_id") or "").strip()
        action_type = str(args.get("action_type") or "navigate").strip()
        if not workflow_id:
            raise ValueError("add_action requires workflow_id/event_id.")
        action_index = str(args.get("action_index") or "0")
        action_body: dict[str, Any] = {
            "%x": action_type,
            "%p": {
                "param": args.get("param"),
                "target": args.get("target"),
                "name": args.get("name") or action_type,
            },
        }
        return [
            set_data_change(
                ["%p3", context_key, "%wf", workflow_id, "actions", action_index],
                action_body,
                session_id,
            )
        ]
    return []


def element_get_data_expression(element_ref: str) -> dict[str, Any]:
    element_id = str(element_ref or "").strip()
    if not element_id:
        raise ValueError("Element reference is required.")
    return {
        "%x": "GetElement",
        "%p": {"%ei": element_id},
        "%n": {
            "%x": "Message",
            "%nm": "get_data",
            "is_slidable": False,
        },
        "is_slidable": False,
    }


def workflow_text_expression(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("%x"):
        return {"%x": "TextExpression", "%e": {"0": value, "1": ""}}
    return {"%x": "TextExpression", "%e": {"0": "" if value is None else value}}


def parse_field_assignments(raw_fields: Any) -> list[dict[str, Any]]:
    if raw_fields is None or raw_fields == "":
        return []
    if isinstance(raw_fields, str):
        stripped = raw_fields.strip()
        if not stripped:
            return []
        try:
            decoded = json.loads(stripped)
            return parse_field_assignments(decoded)
        except Exception:
            fields: list[dict[str, Any]] = []
            for part in stripped.split(";"):
                if not part.strip():
                    continue
                if "=" not in part:
                    raise ValueError(f"Invalid field assignment '{part.strip()}'. Expected field=value.")
                key, value = part.split("=", 1)
                fields.append({"field": key.strip(), "value": value.strip()})
            return fields
    if isinstance(raw_fields, dict):
        if any(key in raw_fields for key in ("field", "key", "%k")):
            return [raw_fields]
        return [{"field": key, "value": value} for key, value in raw_fields.items()]
    if isinstance(raw_fields, list):
        parsed: list[dict[str, Any]] = []
        for item in raw_fields:
            if not isinstance(item, dict):
                raise ValueError("fields array entries must be objects.")
            parsed.extend(parse_field_assignments(item))
        return parsed
    raise ValueError("fields must be a string, object, or array.")


def compile_field_changes(raw_fields: Any) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    for index, item in enumerate(parse_field_assignments(raw_fields)):
        key = str(item.get("field") or item.get("key") or item.get("%k") or "").strip()
        if not key:
            raise ValueError("Field assignment requires field/key.")
        source_ref = str(
            item.get("element_ref")
            or item.get("input_ref")
            or item.get("source_ref")
            or item.get("source")
            or ""
        ).strip()
        if source_ref:
            value = workflow_text_expression(element_get_data_expression(source_ref))
        else:
            raw_value = item.get("value", item.get("%v"))
            value = raw_value if isinstance(raw_value, dict) and raw_value.get("%x") else workflow_text_expression(raw_value)
        assignments[str(index)] = {
            "%k": key,
            "%ak": str(item.get("operator") or item.get("%ak") or "="),
            "%v": value,
        }
    return assignments


def workflow_action_base(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
) -> tuple[str, str, str, str, str]:
    context_name = str(args.get("context") or "").strip()
    if not context_name:
        raise ValueError("context is required for client-side workflow actions.")
    context_key = str(args.get("context_key") or args.get("page_id") or "").strip() or resolve_context_key(
        context_name,
        context,
    )
    root_token = resolve_context_root_token(context_name, context, args)
    workflow_key = resolve_workflow_key({**args, "context": context_name}, context)
    action_index = str(args.get("action_index") if args.get("action_index") is not None else "0")
    action_id = str(args.get("action_id") or bubble_element_id()).strip()
    return root_token, context_key, workflow_key, action_index, action_id


def workflow_action_changes(
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
    action_type: str,
    properties: dict[str, Any],
) -> list[dict[str, Any]]:
    root_token, context_key, workflow_key, action_index, action_id = workflow_action_base(args, context=context)
    action_path = [root_token, context_key, "%wf", workflow_key, "actions", action_index]
    action_body = {
        "%x": action_type,
        "%p": properties,
        "id": action_id,
    }
    changes = [
        update_index_change(["_index", "id_to_path", action_id], ".".join(action_path), session_id),
        create_action_change(action_path[:-1], {action_index: action_body}, session_id),
        update_index_change(["_index", "issues_list", action_id], "[]", session_id),
    ]
    if args.get("id_counter") is not None:
        changes.append({"type": "id_counter", "value": int(args["id_counter"])})
    return changes


def compile_auth_workflow_action_changes(
    tool_name: str,
    args: dict[str, Any],
    *,
    context: BubbleProjectContext | None,
    session_id: str,
) -> list[dict[str, Any]]:
    if tool_name == "log_the_user_in":
        login_properties: dict[str, Any] = {
            "%em": element_get_data_expression(str(args.get("email_input_ref") or "")),
            "%pw": element_get_data_expression(str(args.get("password_input_ref") or "")),
        }
        if args.get("stay_logged_in") is not None:
            login_properties["stay_logged_in"] = bool(args.get("stay_logged_in"))
        if args.get("remember_email") is not None:
            login_properties["remember_email"] = bool(args.get("remember_email"))
        return workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="LogIn",
            properties=login_properties,
        )
    if tool_name == "log_the_user_out":
        return workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="LogOut",
            properties={},
        )
    if tool_name == "sign_the_user_up":
        signup_properties: dict[str, Any] = {
            "%em": element_get_data_expression(str(args.get("email_input_ref") or "")),
            "%pw": element_get_data_expression(str(args.get("password_input_ref") or "")),
        }
        if args.get("require_password_confirmation") is not None:
            signup_properties["%rc"] = bool(args.get("require_password_confirmation"))
        if args.get("password_confirmation_input_ref"):
            signup_properties["%p2"] = element_get_data_expression(str(args.get("password_confirmation_input_ref") or ""))
        if args.get("send_confirm_email") is not None:
            signup_properties["send_confirm_email"] = bool(args.get("send_confirm_email"))
        if args.get("confirmation_page_ref"):
            signup_properties["%pa"] = str(args.get("confirmation_page_ref"))
        if args.get("remember_email") is not None:
            signup_properties["remember_email"] = bool(args.get("remember_email"))
        field_changes = compile_field_changes(args.get("fields"))
        if field_changes:
            signup_properties["%cs"] = field_changes
        return workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="SignUp",
            properties=signup_properties,
        )
    if tool_name == "signup_login_with_a_social_network":
        provider = str(args.get("oauth_provider") or "").strip().lower()
        if provider not in {"google", "facebook"}:
            raise ValueError("signup_login_with_a_social_network requires oauth_provider google or facebook.")
        changes = workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="OAuthLogin",
            properties={"oauth_provider": provider},
        )
        settings_changes: list[dict[str, Any]] = []
        if args.get("provider_app_id"):
            settings_changes.append(
                change_app_setting_change(
                    ["settings", "client_safe", f"{provider}_appid"],
                    args.get("provider_app_id"),
                    session_id,
                )
            )
        if args.get("provider_app_secret"):
            settings_changes.append(
                change_app_setting_change(
                    ["settings", "secure", f"{provider}_appsecret"],
                    args.get("provider_app_secret"),
                    session_id,
                )
            )
        if provider == "facebook":
            scopes = args.get("provider_scopes")
            if isinstance(scopes, list):
                scopes = " ".join(str(item).strip() for item in scopes if str(item).strip())
            if scopes:
                settings_changes.append(
                    change_app_setting_change(
                        ["settings", "client_safe", "facebook_scope"],
                        scopes,
                        session_id,
                    )
                )
            for source_key, setting_key in (
                ("facebook_user_link", "facebook_user_link"),
                ("facebook_server_redirect", "facebook_server_redirect"),
            ):
                if args.get(source_key) is not None:
                    settings_changes.append(
                        change_app_setting_change(
                            ["settings", "client_safe", setting_key],
                            bool(args.get(source_key)),
                            session_id,
                        )
                    )
        return [*changes, *settings_changes]
    if tool_name == "send_confirmation_email":
        confirmation_properties: dict[str, Any] = {"%pa": str(args.get("confirmation_page_ref") or "").strip()}
        if not confirmation_properties["%pa"]:
            raise ValueError("send_confirmation_email requires confirmation_page_ref.")
        if args.get("just_make_token") is not None:
            confirmation_properties["just_make_token"] = bool(args.get("just_make_token"))
        return workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="SendConfirmationEmail",
            properties=confirmation_properties,
        )
    if tool_name == "make_changes_to_current_user":
        field_changes = compile_field_changes(args.get("fields"))
        if not field_changes:
            raise ValueError("make_changes_to_current_user requires fields.")
        return workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="MakeChangeCurrentUser",
            properties={"%cs": field_changes},
        )
    if tool_name == "update_user_credentials":
        credentials_properties: dict[str, Any] = {
            "old_password": element_get_data_expression(str(args.get("old_password_input_ref") or "")),
        }
        if args.get("change_email") is not None:
            credentials_properties["change_email"] = bool(args.get("change_email"))
        if args.get("new_email_input_ref"):
            credentials_properties["%em"] = element_get_data_expression(str(args.get("new_email_input_ref") or ""))
        if args.get("send_confirm_email") is not None:
            credentials_properties["send_confirm_email"] = bool(args.get("send_confirm_email"))
        if args.get("confirmation_page_ref"):
            credentials_properties["%pa"] = str(args.get("confirmation_page_ref"))
        if args.get("change_password") is not None:
            credentials_properties["change_password"] = bool(args.get("change_password"))
        if args.get("new_password_input_ref"):
            credentials_properties["%pw"] = element_get_data_expression(str(args.get("new_password_input_ref") or ""))
        if args.get("require_password_confirmation") is not None:
            credentials_properties["%rc"] = bool(args.get("require_password_confirmation"))
        if args.get("password_confirmation_input_ref"):
            credentials_properties["%p2"] = element_get_data_expression(str(args.get("password_confirmation_input_ref") or ""))
        if args.get("do_not_show_success_alert") is not None:
            credentials_properties["do_not_show_success_alert"] = bool(args.get("do_not_show_success_alert"))
        return workflow_action_changes(
            args,
            context=context,
            session_id=session_id,
            action_type="UpdateCredentials",
            properties=credentials_properties,
        )
    return []


def compile_step_to_payload(
    step: dict[str, Any],
    *,
    app_id: str,
    app_version: str = "test",
    context: BubbleProjectContext | None = None,
) -> dict[str, Any] | None:
    tool_name = str(step.get("tool_name") or "")
    raw_args = step.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}

    existing_payload = args.get("write_payload")
    if isinstance(existing_payload, dict):
        return existing_payload
    changes: list[dict[str, Any]]
    session_id = bubble_session_id()
    if tool_name == "create_text":
        body = compile_create_text_step(args, context=context)
        changes = create_visual_element_changes(args, body, context=context, session_id=session_id)
    elif tool_name == "create_group":
        body = compile_create_group_step(args, context=context)
        changes = create_visual_element_changes(args, body, context=context, session_id=session_id)
    elif tool_name in VISUAL_CREATE_TYPES:
        body = compile_create_visual_step(tool_name, args, context=context)
        changes = create_visual_element_changes(args, body, context=context, session_id=session_id)
    elif tool_name == "update_text":
        changes = compile_update_text_changes(args, context=context, session_id=session_id)
    elif tool_name == "update_group":
        changes = compile_update_group_changes(args, context=context, session_id=session_id)
    elif tool_name in VISUAL_UPDATE_TOOLS:
        changes = compile_update_visual_changes(tool_name, args, context=context, session_id=session_id)
    elif tool_name in VISUAL_DELETE_TOOLS:
        changes = compile_delete_element_changes(args, context=context, session_id=session_id)
    elif tool_name in {"create_data_type", "create_data_field"}:
        changes = compile_schema_changes(tool_name, args, session_id)
    elif tool_name in {"create_option_set", "create_option_value"}:
        changes = compile_option_changes(tool_name, args, session_id)
    elif tool_name in {"create_color", "update_color", "create_style"}:
        changes = compile_theme_changes(tool_name, args, session_id)
    elif tool_name in {"create_workflow", "add_action"}:
        changes = compile_workflow_changes(tool_name, args, session_id)
    elif tool_name in AUTH_WORKFLOW_ACTION_TOOLS:
        changes = compile_auth_workflow_action_changes(tool_name, args, context=context, session_id=session_id)
    else:
        return None

    return {
        "v": 1,
        "appname": app_id,
        "app_version": app_version,
        "changes": changes,
    }


def compile_plan_to_write_payloads(
    plan: dict[str, Any],
    *,
    app_id: str,
    app_version: str = "test",
    context: BubbleProjectContext | None = None,
) -> dict[str, Any]:
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Plan must include a steps array.")

    compiled_steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Plan step {index + 1} must be an object.")
        step = dict(raw_step)
        raw_args = step.get("args")
        args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
        payload = compile_step_to_payload(step, app_id=app_id, app_version=app_version, context=context)
        if payload is not None:
            args["write_payload"] = payload
            step["args"] = args
        compiled_steps.append(step)

    compiled = dict(plan)
    compiled["steps"] = compiled_steps
    compiled["compiled"] = True
    compiled["app_id"] = app_id
    return compiled
