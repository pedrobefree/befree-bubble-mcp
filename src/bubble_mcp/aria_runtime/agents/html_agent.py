from typing import Any, Dict

from .base_agent import BaseAgent


class HTMLAgent(BaseAgent):
    """
    Agent specialized in HTML -> Bubble conversion commands.
    """

    SYSTEM_PROMPT = """
    You convert HTML sources into Bubble element trees through create-from-html.
    Rules:
    1. Keep conversion generic and selector-driven.
    2. Respect placement, style translation, and style-match threshold parameters.
    3. Never build raw webhook payloads manually; rely on BubbleCLI conversion flow.
    """

    SUPPORTED_COMMANDS = {"create-from-html"}

    def can_handle(self, intent: str) -> bool:
        return intent in self.SUPPORTED_COMMANDS

    def execute(self, command: Dict[str, Any], dry_run: bool = False) -> bool:
        command_type = command.get("command")
        if command_type != "create-from-html":
            return False
        try:
            return self.sdk.create_from_html(
                command["context"],
                command["parent"],
                command["html_file"],
                selector=command.get("selector"),
                dry_run=dry_run,
                placement=command.get("placement"),
                floating_group=bool(command.get("floating_group", False)),
                translate_to_existing_styles=bool(
                    command.get("translate_to_existing_styles", False)
                ),
                style_match_threshold=float(command.get("style_match_threshold", 0.78)),
                rendered_html=command.get("rendered_html"),
                strict_validate=bool(command.get("strict_validate", False)),
                validation_out_dir=command.get("validation_out_dir"),
            )
        except KeyError as exc:
            print(f"❌ Missing required argument: {exc}")
            return False
        except Exception as exc:
            print(f"❌ Error executing command: {exc}")
            return False
