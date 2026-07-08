"""Framework adapter support for Bubble MCP."""

from typing import TYPE_CHECKING, Any

from bubble_mcp.frameworks.artifacts import (
    framework_status,
    generate_framework_artifacts,
    list_frameworks,
    sync_framework_evidence,
)

if TYPE_CHECKING:
    from bubble_mcp.frameworks.program_runner import execute_framework_program

__all__ = [
    "execute_framework_program",
    "framework_status",
    "generate_framework_artifacts",
    "list_frameworks",
    "sync_framework_evidence",
]


def __getattr__(name: str) -> Any:
    if name == "execute_framework_program":
        from bubble_mcp.frameworks.program_runner import execute_framework_program

        return execute_framework_program
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
