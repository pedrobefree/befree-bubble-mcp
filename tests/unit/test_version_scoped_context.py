"""Names are resolved against the version being edited.

Team server, 2026-09-25: delete_event on branch 93k8b reported "Workflow 'bTraB0' not found":
the local export was main's, and nothing checked which version it was.
"""

from __future__ import annotations

import json

import pytest

from bubble_mcp.aria_dispatch import _resolve_runtime_environment
from bubble_mcp.context.detector import cached_bubble_export_version, default_bubble_export_path
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.runtime_discovery import DiscoveryDataBoundary
from bubble_mcp.sessions.store import save_session, session_from_payload


class _Logger:
    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass


def _team_profile(tmp_path, monkeypatch, *, export_version: str | None):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="team",
            profiles={
                "team": BubbleProfile(name="team", app_id="kaimia-app", appname="kaimia-app", app_version="test")
            },
        )
    )
    save_session(
        "team",
        session_from_payload({"appId": "kaimia-app", "appVersion": "test", "headers": {"Cookie": "sid=secret"}}),
    )
    export = default_bubble_export_path("team", "kaimia-app")
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_text(json.dumps({"_version": "main"}), encoding="utf-8")
    if export_version is not None:
        export.with_name(export.name + ".meta.json").write_text(
            json.dumps({"app_version": export_version}), encoding="utf-8"
        )
    return export


def test_an_export_of_main_is_refreshed_before_resolving_names_on_a_branch(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    export = _team_profile(tmp_path, monkeypatch, export_version="test")
    calls: list[dict] = []

    def fake_detect(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        export.write_text(json.dumps({"_version": kwargs["app_version"]}), encoding="utf-8")
        export.with_name(export.name + ".meta.json").write_text(
            json.dumps({"app_version": kwargs["app_version"]}), encoding="utf-8"
        )

    monkeypatch.setattr("bubble_mcp.aria_dispatch.detect_project_context", fake_detect)

    env = _resolve_runtime_environment({"profile": "team", "app_version": "93k8b"})

    assert [(call["app_version"], call["force"]) for call in calls] == [("93k8b", True)]
    assert env.app_version == "93k8b"
    assert cached_bubble_export_version(export) == "93k8b"


def test_an_export_of_the_same_version_is_used_as_is(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _team_profile(tmp_path, monkeypatch, export_version="93k8b")
    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch.detect_project_context",
        lambda **_kwargs: pytest.fail("a matching export must not be downloaded again"),
    )

    env = _resolve_runtime_environment({"profile": "team", "app_version": "93k8b"})

    assert env.app_version == "93k8b"


def test_a_failed_refresh_refuses_instead_of_using_the_other_version(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _team_profile(tmp_path, monkeypatch, export_version="test")

    def failing_detect(**_kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("download failed")

    monkeypatch.setattr("bubble_mcp.aria_dispatch.detect_project_context", failing_detect)

    with pytest.raises(ValueError, match="export of version 'test'"):
        _resolve_runtime_environment({"profile": "team", "app_version": "93k8b"})


def test_mutation_overlay_applies_only_the_entries_of_the_described_version(tmp_path) -> None:  # type: ignore[no-untyped-def]
    overlay = tmp_path / "overlay.json"
    overlay.write_text(
        json.dumps(
            {
                "entries": [
                    {"app_version": "test", "changes": [{"path_array": ["a"], "body": 1}]},
                    {"app_version": "93k8b", "changes": [{"path_array": ["b"], "body": 2}]},
                    {"changes": [{"path_array": ["c"], "body": 3}]},
                ]
            }
        ),
        encoding="utf-8",
    )
    discovery = DiscoveryDataBoundary(logger=_Logger())

    assert len(discovery._load_mutation_overlay(str(overlay))) == 3
    discovery.app_version = "93k8b"
    assert [entry["changes"][0]["path_array"] for entry in discovery._load_mutation_overlay(str(overlay))] == [["b"]]
    discovery.app_version = "test"
    assert [entry["changes"][0]["path_array"] for entry in discovery._load_mutation_overlay(str(overlay))] == [
        ["a"],
        ["c"],
    ]
