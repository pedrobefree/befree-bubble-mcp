import json

from bubble_mcp.catalog_inventory import (
    build_catalog_inventory,
    serialize_catalog_inventory,
)
from bubble_mcp.server.schemas import list_tool_schemas


def test_current_catalog_inventory_is_complete_and_explicit() -> None:
    records = build_catalog_inventory(list_tool_schemas())
    mcp_records = [record for record in records if record.mcp_tool is not None]

    assert len(mcp_records) == 328
    assert len({record.mcp_tool for record in mcp_records}) == 327
    assert sum(record.relationship == "direct" for record in records) == 205
    assert sum(record.relationship == "alias" for record in records) == 1
    assert sum(record.relationship == "excluded" for record in records) == 1
    assert sum(record.relationship == "mcp_only" for record in records) == 122
    assert (
        next(
            record
            for record in records
            if record.legacy_command == "create-reusable-type"
        ).mcp_tool
        == "create_reusable"
    )
    assert (
        next(record for record in records if record.legacy_command == "reset-tmp").mcp_tool
        is None
    )
    assert all(record.selection_case_id for record in mcp_records)
    assert all(record.selection_query for record in mcp_records)


def test_inventory_order_and_serialization_ignore_input_order() -> None:
    schemas = list_tool_schemas()
    forward = build_catalog_inventory(schemas)
    reversed_input = build_catalog_inventory(
        list(reversed(schemas)),
        cli_commands=reversed(
            tuple(record.legacy_command for record in forward if record.legacy_command)
        ),
    )

    assert forward == reversed_input
    assert serialize_catalog_inventory(forward) == serialize_catalog_inventory(reversed_input)
    assert json.loads(serialize_catalog_inventory(forward))[0]["relationship"] in {
        "alias",
        "direct",
        "excluded",
        "mcp_only",
    }
