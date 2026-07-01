"""Tool implementations for the initial MCP server."""

from __future__ import annotations

from typing import Any

from bubble_mcp import __version__
from bubble_mcp.core.config import load_settings


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a supported tool and return a JSON-serializable payload."""

    _ = arguments or {}
    if name == "bubble_health_check":
        return {
            "ok": True,
            "version": __version__,
            "capabilities": {
                "profiles": True,
                "session_capture": False,
                "context_engine": False,
                "planner": False,
                "mutations": False,
            },
        }
    if name == "bubble_profile_list":
        settings = load_settings()
        return {
            "ok": True,
            "default_profile": settings.default_profile,
            "profiles": [
                {
                    "name": profile.name,
                    "app_id": profile.app_id,
                    "appname": profile.appname,
                    "editor_url": profile.editor_url,
                }
                for profile in settings.profiles.values()
            ],
        }
    raise ValueError(f"Unknown Bubble MCP tool: {name}")
