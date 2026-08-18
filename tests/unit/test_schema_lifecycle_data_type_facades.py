from __future__ import annotations

import inspect
from typing import Any

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


def test_data_type_facades_keep_public_signatures_and_delegate_to_composed_service() -> None:
    expected = {
        "create_data_type": ["self", "name", "key", "private", "dry_run"],
        "rename_data_type": ["self", "data_type_key", "new_name", "dry_run"],
        "delete_data_type": ["self", "data_type_key", "dry_run"],
        "delete_data_type_permanently": ["self", "data_type_key", "data_type_ref_kind", "confirm", "dry_run"],
        "create_data_field": ["self", "data_type_key", "field_name", "field_type", "field_key", "dry_run"],
        "rename_data_field": ["self", "data_type_key", "field_key", "new_name", "dry_run"],
        "delete_data_field": ["self", "data_type_key", "field_key", "dry_run"],
        "set_data_type_api_exposure": ["self", "data_type_ref", "enabled", "ref_kind", "dry_run"],
    }
    for method, parameters in expected.items():
        assert list(inspect.signature(getattr(BubbleCLI, method)).parameters) == parameters

    cli = object.__new__(BubbleCLI)

    class SentinelDataTypes:
        def create_data_type(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("create", args, kwargs)

        def rename_data_type(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("rename", args, kwargs)

        def delete_data_type(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("delete", args, kwargs)

        def delete_data_type_permanently(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("permanent", args, kwargs)

        def create_data_field(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("field-create", args, kwargs)

        def rename_data_field(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("field-rename", args, kwargs)

        def delete_data_field(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("field-delete", args, kwargs)

        def set_data_type_api_exposure(self, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
            return ("exposure", args, kwargs)

    class SentinelService:
        data_types = SentinelDataTypes()

    cli._schema_lifecycle = SentinelService()  # type: ignore[assignment]

    assert cli.create_data_type("Account", private=True, dry_run=True) == ("create", ("Account", None, True, True), {})
    assert cli.rename_data_type("account", "Account 2", True) == ("rename", ("account", "Account 2", True), {})
    assert cli.delete_data_type("account", True) == ("delete", ("account", True), {})
    assert cli.delete_data_type_permanently("account", "id", True, True) == ("permanent", ("account", "id", True, True), {})
    assert cli.create_data_field("account", "Email", "text", None, True) == ("field-create", ("account", "Email", "text", None, True), {})
    assert cli.rename_data_field("account", "email_text", "Email 2", True) == ("field-rename", ("account", "email_text", "Email 2", True), {})
    assert cli.delete_data_field("account", "email_text", True) == ("field-delete", ("account", "email_text", True), {})
    assert cli.set_data_type_api_exposure("account", True, "key", True) == ("exposure", ("account", True, "key", True), {})
