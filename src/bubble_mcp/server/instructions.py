"""Compact MCP server instructions returned during initialize."""

SERVER_INSTRUCTIONS = (
    "Use Befree Bubble MCP tools directly; do not inspect repository code or CLI help unless a capability is missing. "
    "For Bubble work, call bubble_profile_status for the target profile, then bubble_agent_guide or "
    "bubble_task_recipe to choose the right tool sequence. Leave execute=false for previews unless the user explicitly "
    "asked to apply changes. Use bubble_context_find with exact=true and include_metadata=false for compact target "
    "resolution or verification. Use bubble_readiness_check before broad work or after installation."
)
