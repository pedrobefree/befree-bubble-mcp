"""End-to-end browser suites for Bubble apps, declared per profile and run by the MCP."""

from __future__ import annotations

from bubble_mcp.e2e.paths import new_run_id, safe_run_id
from bubble_mcp.e2e.suite import (
    E2ECaseSpec,
    E2ESuite,
    E2ESuiteError,
    list_suites,
    load_suite,
    parse_suite,
)
from bubble_mcp.e2e.target import (
    ResolvedTarget,
    SessionStatus,
    check_run_as_session,
    resolve_target,
)

__all__ = [
    "E2ECaseSpec",
    "E2ESuite",
    "E2ESuiteError",
    "ResolvedTarget",
    "SessionStatus",
    "check_run_as_session",
    "list_suites",
    "load_suite",
    "new_run_id",
    "parse_suite",
    "resolve_target",
    "safe_run_id",
]
