from typing import Any, Dict, List

from .base_agent import BaseAgent


class ValidatorAgent(BaseAgent):
    """Lightweight pre-execution validator for normalized CLI commands."""

    REQUIRED_FIELDS: Dict[str, List[str]] = {
        "update-text": ["context", "search_text", "new_text"],
        "update-name": ["context", "element_name", "new_name"],
        "update-placeholder": ["context", "element_name", "new_placeholder"],
        "update-style": ["context", "element_name", "new_style"],
        "update-image": ["context", "element_name", "new_source"],
        "update-icon": ["context", "element_name", "new_icon"],
        "update-layout": ["context", "element_name", "property"],
        "update-style-all": ["context", "from_style", "to_style"],
        "create-button": ["context", "parent", "name", "label"],
        "create-text": ["context", "name", "content"],
        "create-group": ["context", "parent", "name"],
        "create-repeating-group": ["context", "parent", "name", "data_type"],
        "create-checkbox": ["context", "parent", "label"],
        "create-datepicker": ["context", "parent", "name"],
        "create-radio": ["context", "parent", "label", "group_name"],
        "create-slider": ["context", "parent", "name"],
        "create-file-uploader": ["context", "parent", "name"],
        "create-picture-uploader": ["context", "parent", "name"],
        "update-picture-uploader": ["context", "element_name"],
        "delete-picture-uploader": ["context", "element_name"],
        "create-shape": ["context", "parent", "name"],
        "create-video": ["context", "parent", "name"],
        "create-input": ["context", "parent", "name"],
        "create-dropdown": ["context", "parent", "name"],
        "create-popup": ["context", "title"],
        "create-from-html": ["context", "parent", "html_file"],
    }

    def can_handle(self, intent: str) -> bool:
        return intent == "validate"

    def execute(self, command: Dict[str, Any], dry_run: bool = False) -> bool:
        command_type = command.get("command")
        return self.validate(command_type, command)

    def validate(self, command_type: str, command: Dict[str, Any]) -> bool:
        required = self.REQUIRED_FIELDS.get(command_type)
        if not required:
            return True
        missing = [
            field
            for field in required
            if field not in command or command.get(field) in (None, "")
        ]
        if missing:
            print(
                f"❌ Validation failed for '{command_type}': missing {', '.join(missing)}"
            )
            return False
        return True
