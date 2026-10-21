"""The dev version's preview password page is answered by every browser tool from one resolver.

On the team server E2E and visual capture got 401 on the dev version until the agent typed the
preview login in by hand. The pair can now live on the profile, and every browser tool tries,
in order: the call's own arguments, the profile, the environment, the app's export, and
Bubble's seeded default.
"""

from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.execution import run_as
from bubble_mcp.execution.run_as import playwright_http_credentials, resolve_preview_credentials
from bubble_mcp.server.tools import call_tool


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("BUBBLE_PREVIEW_USER", raising=False)
    monkeypatch.delenv("BUBBLE_PREVIEW_PW", raising=False)
    monkeypatch.setattr(run_as, "preview_credentials_from_export", lambda profile, app_id: None)


def _profile_with_pair() -> dict[str, Any]:
    return call_tool(
        "bubble_profile_add",
        {"name": "kaimia", "app_id": "kaimia-app", "preview_username": "team", "preview_password": "s3cr3t"},
    )


def test_the_profile_stores_the_pair_and_never_echoes_the_password() -> None:
    result = _profile_with_pair()

    assert result["stored"]["preview_username"] == "team"
    assert result["stored"]["preview_password"] == "[REDACTED]"
    assert "s3cr3t" not in str(result)


def test_the_profile_pair_is_used_when_the_call_names_none() -> None:
    _profile_with_pair()

    assert resolve_preview_credentials("kaimia", "kaimia-app") == (("team", "s3cr3t"), "profile")
    assert playwright_http_credentials("kaimia", "kaimia-app") == {"username": "team", "password": "s3cr3t"}


def test_arguments_beat_the_profile_and_the_profile_beats_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _profile_with_pair()
    monkeypatch.setenv("BUBBLE_PREVIEW_USER", "env")
    monkeypatch.setenv("BUBBLE_PREVIEW_PW", "envpw")

    assert resolve_preview_credentials("kaimia", "kaimia-app", username="a", password="b")[1] == "argument"
    assert resolve_preview_credentials("kaimia", "kaimia-app")[1] == "profile"
    assert resolve_preview_credentials("other", "other-app")[1] == "environment"


def test_with_nothing_configured_the_seeded_default_is_offered() -> None:
    assert resolve_preview_credentials("nobody", "some-app") == (("username", "password"), "default")
    assert resolve_preview_credentials("nobody", "some-app", include_default=False) is None


def test_the_e2e_runner_and_visual_capture_use_the_resolver() -> None:
    import inspect

    from bubble_mcp.e2e import runner
    from bubble_mcp.harness import visual_bubble

    assert "playwright_http_credentials(" in inspect.getsource(runner)
    assert "playwright_http_credentials(" in inspect.getsource(visual_bubble.capture_bubble_visual_snapshot)


def test_visual_capture_actual_sends_the_pair_to_the_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.harness import visual_bubble

    _profile_with_pair()
    seen: dict[str, Any] = {}

    def fake_capture(url: str, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs, url=url)
        return {"ok": True}

    monkeypatch.setattr(visual_bubble, "capture_visual_snapshot", fake_capture)

    visual_bubble.capture_bubble_visual_snapshot(profile="kaimia", app_id="kaimia-app", app_version="93k8b")

    assert seen["http_credentials"] == {"username": "team", "password": "s3cr3t"}
