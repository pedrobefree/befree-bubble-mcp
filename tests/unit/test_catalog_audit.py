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
