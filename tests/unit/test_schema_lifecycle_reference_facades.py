from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI, PayloadBuilder


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "user_types": {"account": {"%d": "Account", "%f3": {"email_text": {"%d": "Email"}}}},
                "option_sets": {"os_status": {"%d": "OS:Status", "values": {"active": {"%d": "Active"}}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cache.json"))
    instance = BubbleCLI(app_json_path=str(app_path), appname="schema-reference-fixture")
    instance._schema_user_types_cache()["cached"] = {"%d": "Cached"}
    instance._schema_option_sets_cache()["os_cached"] = {"%d": "OS:Cached", "values": {"old": {"%d": "Old"}}}
    return instance


def test_schema_reference_facade_signatures_and_literal_results_are_preserved(cli: BubbleCLI) -> None:
    assert list(inspect.signature(BubbleCLI._get_user_types).parameters) == ["self", "include_cache"]
    assert list(inspect.signature(BubbleCLI._resolve_data_type_key).parameters) == ["self", "data_type_ref", "ref_kind", "include_cache"]
    assert list(inspect.signature(BubbleCLI._get_option_sets).parameters) == ["self", "include_cache"]
    assert list(inspect.signature(BubbleCLI._resolve_option_set_key).parameters) == ["self", "option_set_ref", "ref_kind", "include_cache"]
    assert list(inspect.signature(BubbleCLI._get_option_set_values).parameters) == ["self", "option_set_key"]
    assert list(inspect.signature(BubbleCLI._resolve_option_value_key).parameters) == ["self", "option_set_key", "value_ref", "ref_kind"]

    assert cli._get_user_types(include_cache=False) == {"account": {"%d": "Account", "%f3": {"email_text": {"%d": "Email"}}}}
    assert cli._resolve_data_type_key("Account", ref_kind="label", include_cache=False) == "account"
    assert cli._resolve_data_type_key("cached", include_cache=False) is None
    assert cli._get_option_sets(include_cache=False) == {
        "os_status": {"%d": "OS:Status", "values": {"active": {"%d": "Active"}}}
    }
    assert cli._resolve_option_set_key("Status", ref_kind="label", include_cache=False) == "os_status"
    assert cli._get_option_set_values("os_status") == {"active": {"%d": "Active"}}
    assert cli._resolve_option_value_key("os_status", "Active", ref_kind="label") == "active"


def test_schema_reference_facades_delegate_to_the_composed_service(cli: BubbleCLI) -> None:
    class SentinelReferences:
        def user_types(self, *, include_cache: bool) -> dict[str, Any]:
            return {"types": include_cache}

        def resolve_data_type(self, value: str, *, ref_kind: str, include_cache: bool) -> str:
            return f"type:{value}:{ref_kind}:{include_cache}"

        def option_sets(self, *, include_cache: bool) -> dict[str, Any]:
            return {"sets": include_cache}

        def resolve_option_set(self, value: str, *, ref_kind: str, include_cache: bool) -> str:
            return f"set:{value}:{ref_kind}:{include_cache}"

        def option_values(self, value: str, *, include_cache: bool = True) -> dict[str, Any]:
            return {"values": value, "cache": include_cache}

        def resolve_option_value(self, option_set: str, value: str, *, ref_kind: str, include_cache: bool = True) -> str:
            return f"value:{option_set}:{value}:{ref_kind}:{include_cache}"

    cli._schema_lifecycle.references = SentinelReferences()  # type: ignore[assignment]

    assert cli._get_user_types(False) == {"types": False}
    assert cli._resolve_data_type_key("Account", "label", False) == "type:Account:label:False"
    assert cli._get_option_sets(False) == {"sets": False}
    assert cli._resolve_option_set_key("Status", "label", False) == "set:Status:label:False"
    assert cli._get_option_set_values("os_status") == {"values": "os_status", "cache": True}
    assert cli._resolve_option_value_key("os_status", "Active", "label") == "value:os_status:Active:label:True"


def test_successful_schema_dispatch_invalidates_schema_references_but_dry_run_and_failure_do_not(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli._resolve_data_type_key("Account") == "account"
    revision = cli.schema_reference_revision()

    assert cli.rename_data_type("account", "Renamed", dry_run=True) is True
    assert cli.schema_reference_revision() == revision

    monkeypatch.setattr(cli, "_dispatch_payload", lambda payload: (_ for _ in ()).throw(RuntimeError("nope")))
    assert cli.rename_data_type("account", "Renamed", dry_run=False) is False
    assert cli.schema_reference_revision() == revision

    monkeypatch.setattr(cli, "_dispatch_payload", BubbleCLI._dispatch_payload.__get__(cli))
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda payload, url: None)
    assert cli.rename_data_type("account", "Renamed", dry_run=False) is True
    assert cli.schema_reference_revision() == revision + 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda instance: instance.delete_option_value("os_status", "stale", dry_run=True),
        lambda instance: instance.rename_option_value("os_status", "stale", "Renamed", dry_run=True),
        lambda instance: instance.set_option_value_attribute("os_status", "stale", "role", "admin", dry_run=True),
        lambda instance: instance.reorder_option_values("os_status", ["stale:1"], dry_run=True),
    ],
)
def test_option_value_mutations_reject_cache_only_values_before_payload_construction(
    cli: BubbleCLI,
    capsys: pytest.CaptureFixture[str],
    mutation: Any,
) -> None:
    cli.discovery.data["option_sets"]["os_status"] = {"%d": "OS:Status", "values": {}}
    cli._schema_option_sets_cache()["os_status"] = {
        "%d": "OS:Status",
        "values": {"stale": {"%d": "Stale", "db_value": "stale"}},
    }
    cli._invalidate_schema_reference_index("option_sets")

    assert mutation(cli) is False
    assert "DRY RUN - Payload preview:" not in capsys.readouterr().out
