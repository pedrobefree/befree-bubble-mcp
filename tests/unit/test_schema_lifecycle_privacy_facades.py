from __future__ import annotations

import inspect
from typing import Any

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


def test_privacy_facades_keep_public_signatures_and_delegate_to_composed_service() -> None:
    expected = {
        "list_privacy_rules": ["self", "data_type_key", "dry_run"],
        "create_privacy_rule": ["self", "data_type_key", "rule_name", "rule_key", "view_all", "view_attachments", "search_for", "auto_binding", "view_fields", "binding_fields", "condition_json", "include_everyone_default", "id_counter", "dry_run"],
        "delete_privacy_rule": ["self", "data_type_key", "rule_key", "dry_run"],
        "set_privacy_rule_name": ["self", "data_type_key", "rule_key", "new_name", "dry_run"],
        "set_privacy_rule_condition": ["self", "data_type_key", "rule_key", "condition_json", "dry_run"],
        "set_privacy_rule_permission": ["self", "data_type_key", "rule_key", "permission", "value", "dry_run"],
        "set_privacy_rule_field_visibility": ["self", "data_type_key", "rule_key", "view_all", "view_fields", "dry_run"],
        "set_privacy_rule_auto_binding": ["self", "data_type_key", "rule_key", "auto_binding", "binding_fields", "dry_run"],
    }
    for method, parameters in expected.items():
        assert list(inspect.signature(getattr(BubbleCLI, method)).parameters) == parameters

    cli = object.__new__(BubbleCLI)

    class SentinelPrivacy:
        def __getattr__(self, name: str) -> Any:
            return lambda *args, **kwargs: (name, args, kwargs)

    class SentinelService:
        privacy = SentinelPrivacy()

    cli._schema_lifecycle = SentinelService()  # type: ignore[assignment]

    assert cli.list_privacy_rules("account", True) == ("list_privacy_rules", ("account", True), {})
    assert cli.create_privacy_rule("account", "Members", "members", False, False, False, True, ["Email"], ["Email"], {"x": 1}, False, 3, True) == ("create_privacy_rule", ("account", "Members", "members", False, False, False, True, ["Email"], ["Email"], {"x": 1}, False, 3, True), {})
    assert cli.delete_privacy_rule("account", "members", True) == ("delete_privacy_rule", ("account", "members", True), {})
    assert cli.set_privacy_rule_name("account", "members", "Members", True) == ("set_privacy_rule_name", ("account", "members", "Members", True), {})
    assert cli.set_privacy_rule_condition("account", "members", {"x": 1}, True) == ("set_privacy_rule_condition", ("account", "members", {"x": 1}, True), {})
    assert cli.set_privacy_rule_permission("account", "members", "search_for", 1, True) == ("set_privacy_rule_permission", ("account", "members", "search_for", 1, True), {})
    assert cli.set_privacy_rule_field_visibility("account", "members", False, ["Email"], True) == ("set_privacy_rule_field_visibility", ("account", "members", False, ["Email"], True), {})
    assert cli.set_privacy_rule_auto_binding("account", "members", True, ["Email"], True) == ("set_privacy_rule_auto_binding", ("account", "members", True, ["Email"], True), {})
