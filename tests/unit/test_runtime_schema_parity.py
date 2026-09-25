"""Catalog schemas match the runtime methods they dispatch to.

Team server, 2026-09-25: create_button failed with "BubbleCLI.create_button() missing 1 required
positional argument: 'name'" - the schema let `name` be omitted and nothing filled it in.
"""

from __future__ import annotations

import json

import pytest

from bubble_mcp.aria_dispatch import dispatch_aria_runtime_tool, runtime_schema_gaps
from bubble_mcp.catalog_quality import catalog_quality_report
from bubble_mcp.context.detector import default_bubble_export_path
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.sessions.store import save_session, session_from_payload


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


def test_create_button_without_a_name_gets_one_derived_from_its_label() -> None:
    schema = next(tool for tool in list_tool_schemas() if tool["name"] == "create_button")

    assert "name" not in schema["inputSchema"]["required"]
    assert schema["inputSchema"]["x-bubble-name-prefix"] == "bt_"


def test_every_catalog_schema_matches_its_runtime_signature() -> None:
    gaps = {
        tool["name"]: gap
        for tool in list_tool_schemas()
        if (gap := runtime_schema_gaps(tool["name"], tool))["not_required"] or gap["unreachable"]
    }

    assert gaps == {}


def test_catalog_quality_reports_runtime_signature_parity() -> None:
    report = catalog_quality_report()
    checks = {check["name"]: check for check in report["checks"]}

    assert "runtime_signature_parity" in checks
    assert not [issue for issue in report["issues"] if issue["check"] == "runtime_signature_parity"]


def test_a_missing_runtime_argument_is_named_instead_of_raising_type_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _team_profile(tmp_path, monkeypatch, export_version="93k8b")

    with pytest.raises(ValueError, match=r"create_image is missing required argument\(s\): source"):
        dispatch_aria_runtime_tool(
            "create_image",
            {"profile": "team", "app_version": "93k8b", "context": "index", "parent": "root", "name": "im_logo"},
        )
