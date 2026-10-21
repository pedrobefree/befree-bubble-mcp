import json
import os
from pathlib import Path
import subprocess
import sys

from bubble_mcp.catalog_audit import _literal_add_parser_names, cli_catalog_parity_report
from bubble_mcp.server.schemas import list_tool_schemas


def test_literal_add_parser_names_only_collects_static_commands() -> None:
    assert _literal_add_parser_names(
        """
parser.add_parser("first")
parser.add_parser(
    'second',
    help='Second command',
)
parser.add_parser(dynamic_name)
"""
    ) == ("first", "second")


def test_packaged_cli_has_no_unmapped_bubble_operation_commands() -> None:
    report = cli_catalog_parity_report(tool["name"] for tool in list_tool_schemas())

    assert report["ok"] is True
    assert report["cli_command_count"] == 207
    assert report["missing"] == []
    assert report["aliases"] == [
        {"command": "create-reusable-type", "tool": "create_reusable"}
    ]
    assert report["excluded"] == [
        {
            "command": "reset-tmp",
            "reason": "Local developer housekeeping; it does not operate on a Bubble project.",
        }
    ]


def test_parity_report_is_derived_from_complete_inventory() -> None:
    report = cli_catalog_parity_report(tool["name"] for tool in list_tool_schemas())

    assert report["mcp_tool_count"] == 327
    assert report["direct_match_count"] == 205
    assert report["alias_count"] == 1
    assert report["excluded_count"] == 1
    assert report["mcp_only_count"] == 122


def test_parity_report_reports_an_incomplete_catalog_without_raising() -> None:
    report = cli_catalog_parity_report(
        tool["name"] for tool in list_tool_schemas() if tool["name"] != "add_action"
    )

    assert report["ok"] is False
    assert report["missing_count"] == 1
    assert report["missing"] == [{"command": "add-action", "candidate_tool": "add_action"}]
    assert report["direct_match_count"] == 204


def test_audit_script_runs_from_checkout_without_pythonpath() -> None:
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "scripts/audit_cli_catalog.py"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout)["ok"] is True
