"""Reusable MCP prompts for Bubble MCP clients."""

from __future__ import annotations

from typing import Any


PROMPTS: dict[str, dict[str, Any]] = {
    "bubble-task-runbook": {
        "name": "bubble-task-runbook",
        "description": "Create a concise execution runbook for a Bubble task using this MCP server.",
        "arguments": [
            {"name": "task", "description": "User's Bubble task.", "required": True},
            {"name": "profile", "description": "Local Bubble MCP profile.", "required": False},
            {"name": "context", "description": "Target Bubble page/reusable/context.", "required": False},
            {"name": "parent", "description": "Target parent container. Defaults to root.", "required": False},
            {"name": "execute", "description": "Whether the user explicitly asked to apply the change.", "required": False},
        ],
    },
    "bubble-html-import": {
        "name": "bubble-html-import",
        "description": "Plan an advanced HTML selector/URL import into Bubble using the MCP runtime.",
        "arguments": [
            {"name": "profile", "description": "Local Bubble MCP profile.", "required": True},
            {"name": "context", "description": "Target Bubble page or reusable.", "required": True},
            {"name": "parent", "description": "Target parent container. Defaults to root.", "required": False},
            {"name": "url", "description": "Source URL to import from.", "required": False},
            {"name": "selector", "description": "CSS selector for the target section/component.", "required": False},
            {"name": "execute", "description": "Whether the user explicitly asked to apply the import.", "required": False},
        ],
    },
    "bubble-quality-gate": {
        "name": "bubble-quality-gate",
        "description": "Generate a quality gate checklist for validating this MCP server/profile.",
        "arguments": [
            {"name": "profile", "description": "Local Bubble MCP profile.", "required": False},
            {"name": "context", "description": "Target Bubble context for preview/family smoke.", "required": False},
        ],
    },
}


def list_prompts() -> list[dict[str, Any]]:
    """Return MCP prompt descriptors."""

    return list(PROMPTS.values())


def get_prompt(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Render one MCP prompt by name."""

    args = arguments or {}
    if name == "bubble-task-runbook":
        task = str(args.get("task") or "<task>")
        profile = str(args.get("profile") or "<profile>")
        context = str(args.get("context") or "<context>")
        parent = str(args.get("parent") or "root")
        execute = str(args.get("execute") or "false").lower()
        text = (
            f"Use the Befree Bubble MCP to execute this Bubble task: {task}\n\n"
            f"Target profile: {profile}\n"
            f"Target context: {context}\n"
            f"Target parent: {parent}\n"
            f"Execute requested: {execute}\n\n"
            "Do not inspect repository code, CLI help, or shell commands when the MCP catalog already exposes the "
            "needed capability. Do not ask the user to memorize internal tool names; infer the tool family from "
            "the task.\n\n"
            "First call `bubble_task_recipe` with the task/profile/context/parent/execute values. "
            "Use the returned preflight and steps as the source of truth. Preview before real writes unless "
            "execute was explicitly requested, and verify real writes with context refresh, changelog, or smoke."
        )
    elif name == "bubble-html-import":
        profile = str(args.get("profile") or "<profile>")
        context = str(args.get("context") or "<context>")
        parent = str(args.get("parent") or "root")
        url = str(args.get("url") or "<url-or-html-source>")
        selector = str(args.get("selector") or "<selector>")
        execute = str(args.get("execute") or "false").lower()
        text = (
            "Import an HTML component into Bubble through the advanced MCP runtime.\n\n"
            f"Use profile `{profile}`, context `{context}`, parent `{parent}`, source `{url}`, selector `{selector}`, "
            f"and execute={execute}.\n\n"
            "Do not search CLI help or repository code for this flow. Call `bubble_task_recipe` first. "
            "Then call `create_from_html` with rendered_html=true, "
            "refresh_context=true, and execute=false for preview. Repeat with execute=true only if the user asked "
            "to apply the import and the preview is valid."
        )
    elif name == "bubble-quality-gate":
        profile = str(args.get("profile") or "<profile>")
        context = str(args.get("context") or "index")
        text = (
            "Validate the Befree Bubble MCP before claiming the work is complete.\n\n"
            "Run or call these checks:\n"
            "1. `bubble_health_check`.\n"
            "2. `bubble_tool_coverage` and confirm no Aria catalog tools are uncovered.\n"
            "3. `bubble_runtime_smoke` with suite=coverage.\n"
            "4. `bubble_runtime_smoke` with suite=agent-routing.\n"
            f"5. `bubble_runtime_smoke` with suite=family-preview, profile={profile}, context={context}, parent=root.\n"
            "6. For real writes, use execute-write only when explicitly allowed and verify context afterward."
        )
    else:
        raise ValueError(f"Unknown Bubble MCP prompt: {name}")

    return {
        "description": str(PROMPTS[name]["description"]),
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": text},
            }
        ],
    }
