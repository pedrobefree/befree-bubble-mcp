from typing import Any, Dict

from .base_agent import BaseAgent


class ElementAgent(BaseAgent):
    """
    Agent specialized in element CRUD/update commands.

    This agent intentionally delegates execution to the existing BubbleCLI
    methods, keeping current behavior while isolating routing concerns.
    """

    SYSTEM_PROMPT = """
    You create and update Bubble visual elements using BubbleCLI methods.
    Rules:
    1. Resolve context/parent before mutation.
    2. Respect width/height fit controls and css min/max sizing when provided.
    3. Keep style-driven elements non-overridden unless explicitly requested.
    """

    VISUAL_KEYS = {
        "margin_top",
        "margin_bottom",
        "margin_left",
        "margin_right",
        "padding_top",
        "padding_bottom",
        "padding_left",
        "padding_right",
        "bg_color",
        "text_color",
        "border_radius",
        "border_color",
        "border_width",
        "border_style",
        "shadow_style",
        "shadow_h",
        "shadow_v",
        "shadow_blur",
        "shadow_spread",
        "shadow_color",
        "min_width_css",
        "max_width_css",
        "min_height_css",
        "max_height_css",
        "fit_width",
        "fit_height",
        "overflow_scroll",
    }

    SUPPORTED_COMMANDS = {
        "update-text",
        "update-name",
        "update-placeholder",
        "update-style",
        "update-image",
        "update-icon",
        "update-layout",
        "update-style-all",
        "create-button",
        "create-text",
        "create-group",
        "create-repeating-group",
        "create-checkbox",
        "create-datepicker",
        "create-radio",
        "create-slider",
        "create-file-uploader",
        "create-picture-uploader",
        "create-shape",
        "create-video",
        "create-input",
        "create-dropdown",
        "create-popup",
    }

    def can_handle(self, intent: str) -> bool:
        return intent in self.SUPPORTED_COMMANDS

    def execute(self, command: Dict[str, Any], dry_run: bool = False) -> bool:
        command_type = command.get("command")
        if not self.can_handle(command_type):
            return False

        visual_kwargs = self._extract_visual_kwargs(command)
        width_unset = self._should_unset_width(command)

        try:
            if command_type == "update-text":
                return self.sdk.update_text(
                    command["context"],
                    command["search_text"],
                    command["new_text"],
                    dry_run,
                )

            if command_type == "update-name":
                return self.sdk.update_name(
                    command["context"],
                    command["element_name"],
                    command["new_name"],
                    dry_run,
                )

            if command_type == "update-placeholder":
                return self.sdk.update_placeholder(
                    command["context"],
                    command["element_name"],
                    command["new_placeholder"],
                    dry_run,
                )

            if command_type == "update-style":
                return self.sdk.update_style(
                    command["context"],
                    command["element_name"],
                    command["new_style"],
                    dry_run,
                    search_by_text=command.get("search_by_text", False),
                    keep_overrides=command.get("keep_overrides", False),
                )

            if command_type == "create-button":
                return self.sdk.create_button(
                    command["context"],
                    command["parent"],
                    command.get("name", command.get("label", "Button")),
                    command["label"],
                    style=command.get("style", "Button_primary_button_"),
                    icon=command.get("icon"),
                    button_type=command.get("type", "label"),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-text":
                return self.sdk.create_text(
                    command["context"],
                    command.get("name", command.get("content", "Text")),
                    command["content"],
                    parent_name=command.get("parent"),
                    horiz_alignment=command.get("horiz_alignment"),
                    style=command.get("style"),
                    keep_overrides=command.get("keep_overrides", False),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-group":
                return self.sdk.create_group(
                    command["context"],
                    command["parent"],
                    command["name"],
                    layout=command.get("layout", "column"),
                    width=command.get("width", 280),
                    height=command.get("height", 280),
                    gap=command.get("gap", 0),
                    data_class=command.get("data_class"),
                    data_source=command.get("data_source"),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-repeating-group":
                return self.sdk.create_repeating_group(
                    command["context"],
                    command["parent"],
                    command["name"],
                    command["data_type"],
                    layout=command.get("layout", "column"),
                    rows=command.get("rows", 0),
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-checkbox":
                return self.sdk.create_checkbox(
                    command["context"],
                    command["parent"],
                    command.get("name", command.get("label", "Checkbox")),
                    label=command.get("label", "Checkbox"),
                    checked=command.get("checked", False),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-datepicker":
                return self.sdk.create_datepicker(
                    command["context"],
                    command["parent"],
                    command["name"],
                    show_time=command.get("show_time", False),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-radio":
                return self.sdk.create_radio(
                    command["context"],
                    command["parent"],
                    command.get("name", command.get("label", "Radio")),
                    label=command.get("label", "Radio"),
                    group_name=command["group_name"],
                    selected=command.get("selected", False),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-slider":
                return self.sdk.create_slider(
                    command["context"],
                    command["parent"],
                    command["name"],
                    min_value=command.get("min", 0),
                    max_value=command.get("max", 100),
                    initial_value=command.get("val", 50),
                    step=command.get("step", 1),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-file-uploader":
                return self.sdk.create_file_uploader(
                    command["context"],
                    command["parent"],
                    command["name"],
                    label=command.get("label", "Upload file"),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-picture-uploader":
                return self.sdk.create_picture_uploader(
                    command["context"],
                    command["parent"],
                    command["name"],
                    label=command.get("label", "Upload picture"),
                    width_unset=False,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-shape":
                return self.sdk.create_shape(
                    command["context"],
                    command["parent"],
                    command["name"],
                    shape_type=command.get("type", "rectangle"),
                    width=command.get("width", 100),
                    height=command.get("height", 100),
                    color=command.get("color", "#000000"),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-video":
                return self.sdk.create_video(
                    command["context"],
                    command["parent"],
                    command["name"],
                    video_url=command.get("url", ""),
                    width=command.get("width", 560),
                    height=command.get("height", 315),
                    autoplay=command.get("autoplay", False),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-input":
                return self.sdk.create_input(
                    command["context"],
                    command["parent"],
                    command["name"],
                    placeholder=command.get("placeholder", ""),
                    content_format=command.get("format", "text"),
                    required=command.get("required", False),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-dropdown":
                return self.sdk.create_dropdown(
                    command["context"],
                    command["parent"],
                    command["name"],
                    placeholder=command.get("placeholder", "Choose..."),
                    choices_str=command.get("choices"),
                    dynamic_type=command.get("dynamic_type"),
                    width_unset=width_unset,
                    dry_run=dry_run,
                    **visual_kwargs,
                )

            if command_type == "create-popup":
                return self.sdk.create_popup(
                    command["context"],
                    command["title"],
                    dry_run=dry_run,
                    horiz_alignment=command.get("popup_horiz_alignment"),
                    vert_alignment=command.get("popup_vert_alignment"),
                    **visual_kwargs,
                )

            if command_type == "update-image":
                return self.sdk.update_image(
                    command["context"],
                    command["element_name"],
                    command["new_source"],
                    dry_run=dry_run,
                    prefer_last=command.get("prefer_last", False),
                )

            if command_type == "update-icon":
                return self.sdk.update_icon(
                    command["context"],
                    command["element_name"],
                    command["new_icon"],
                    dry_run=dry_run,
                    prefer_last=command.get("prefer_last", False),
                )

            if command_type == "update-layout":
                return self.sdk.update_layout_property(
                    command["context"],
                    command["element_name"],
                    command["property"],
                    command.get("value"),
                    dry_run=dry_run,
                    prefer_last=command.get("prefer_last", False),
                )

            if command_type == "update-style-all":
                return self.sdk.update_style_all(
                    command["context"],
                    command.get("element_type", "Text"),
                    command["from_style"],
                    command["to_style"],
                    dry_run=dry_run,
                    keep_overrides=command.get("keep_overrides", False),
                )

            return False
        except KeyError as exc:
            print(f"❌ Missing required argument: {exc}")
            return False
        except Exception as exc:
            print(f"❌ Error executing command: {exc}")
            return False

    def _extract_visual_kwargs(self, command: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in command.items() if k in self.VISUAL_KEYS}

    def _should_unset_width(self, command: Dict[str, Any]) -> bool:
        checker = getattr(self.sdk, "_has_explicit_width_controls", None)
        if callable(checker):
            return not checker(command)
        return True
