"""Suite-wide guards.

The session savepoint guard runs before every executed write (`server/tools.call_tool`), and its
real path POSTs to `/appeditor/commit_test_version`. Left alone, the unit suite would reach the
network on every write test: slow, dependent on an external app's state, and broken with no
connection. Stub it here rather than marking each write test, so a new write test inherits the
isolation instead of having to remember it.

Tests that exercise the guard itself monkeypatch the same name inside the test body, which takes
effect after this fixture and therefore wins.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_savepoint_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the savepoint guard from reaching Bubble, and from writing a marker file."""

    monkeypatch.setattr(
        "bubble_mcp.server.tools.ensure_session_savepoint",
        lambda **kwargs: {"created": False, "reason": "savepoint_disabled_in_tests"},
        raising=False,
    )
