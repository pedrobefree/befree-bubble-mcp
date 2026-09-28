"""Keep test catalogs, profiles and subprocesses independent of personal settings."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture(autouse=True)
def _no_session_check_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the session gate from asking Bubble whether a real stored session is logged in."""

    monkeypatch.setattr(
        "bubble_mcp.server.tools.check_session",
        lambda profile, **kwargs: {"ok": True, "profile": profile, "logged_in": True, "reason": "stubbed_in_tests"},
        raising=False,
    )
