from __future__ import annotations

import inspect
from typing import Any

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


def test_option_facades_keep_public_signatures_and_delegate_to_composed_service() -> None:
    expected = {
        "create_option_set": ["self", "name", "key", "dry_run"],
        "rename_option_set": ["self", "option_set_key", "new_name", "dry_run"],
        "delete_option_set": ["self", "option_set_key", "dry_run"],
        "create_option_attribute": ["self", "option_set_key", "name", "value_type", "attribute_key", "dry_run"],
        "create_option_value": ["self", "option_set_key", "label", "value_key", "db_value", "sort_factor", "id_counter", "dry_run"],
        "delete_option_value": ["self", "option_set_key", "value_ref", "ref_kind", "dry_run"],
        "rename_option_value": ["self", "option_set_key", "value_ref", "new_label", "ref_kind", "dry_run"],
        "set_option_value_attribute": ["self", "option_set_key", "value_ref", "attribute_key", "value", "ref_kind", "parse_json", "dry_run"],
        "reorder_option_values": ["self", "option_set_key", "assignments", "ref_kind", "dry_run"],
        "list_option_values": ["self", "option_set_key", "as_json"],
    }
    for method, parameters in expected.items():
        assert list(inspect.signature(getattr(BubbleCLI, method)).parameters) == parameters

    cli = object.__new__(BubbleCLI)

    class SentinelOptions:
        def __getattr__(self, name: str) -> Any:
            return lambda *args, **kwargs: (name, args, kwargs)

    class SentinelService:
        options = SentinelOptions()

    cli._schema_lifecycle = SentinelService()  # type: ignore[assignment]

    assert cli.create_option_set("Status", "os_status", True) == ("create_option_set", ("Status", "os_status", True), {})
    assert cli.rename_option_set("os_status", "Status 2", True) == ("rename_option_set", ("os_status", "Status 2", True), {})
    assert cli.delete_option_set("os_status", True) == ("delete_option_set", ("os_status", True), {})
    assert cli.create_option_attribute("os_status", "Color", "text", "color", True) == ("create_option_attribute", ("os_status", "Color", "text", "color", True), {})
    assert cli.create_option_value("os_status", "Open", "open", "open", 1, 4, True) == ("create_option_value", ("os_status", "Open", "open", "open", 1, 4, True), {})
    assert cli.delete_option_value("os_status", "open", "label", True) == ("delete_option_value", ("os_status", "open", "label", True), {})
    assert cli.rename_option_value("os_status", "open", "Opened", "label", True) == ("rename_option_value", ("os_status", "open", "Opened", "label", True), {})
    assert cli.set_option_value_attribute("os_status", "open", "color", "blue", "label", True, True) == ("set_option_value_attribute", ("os_status", "open", "color", "blue", "label", True, True), {})
    assert cli.reorder_option_values("os_status", ["open:1"], "label", True) == ("reorder_option_values", ("os_status", ["open:1"], "label", True), {})
    assert cli.list_option_values("os_status", True) == ("list_option_values", ("os_status", True), {})
