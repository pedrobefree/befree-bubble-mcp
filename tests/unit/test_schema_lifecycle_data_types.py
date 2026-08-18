from __future__ import annotations

import json
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI, PayloadBuilder


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "user_types": {
                    "account": {
                        "%d": "Account",
                        "%f3": {
                            "email_text": {"%d": "Email", "%v": "text"},
                            "legacy_text": {"%d": "Legacy", "%v": "text"},
                        },
                    },
                    "customer": {"%d": "Customer", "%f3": {}},
                },
                "option_sets": {"os_status": {"%d": "OS:Status", "values": {}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cache.json"))
    return BubbleCLI(app_json_path=str(app_path), appname="schema-data-types")


@pytest.mark.parametrize(
    ("field_type", "expected"),
    [
        ("text", "text"),
        ("list.text", "list.text"),
        ("custom.Customer", "custom.customer"),
        ("option.OS:Status", "option.os_status"),
    ],
)
def test_create_data_field_resolves_real_field_types_current_first(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str], field_type: str, expected: str
) -> None:
    assert cli.create_data_field("account", "Status", field_type, dry_run=True) is True

    payload = json.loads(capsys.readouterr().out.split("Payload preview:\n", 1)[1])
    assert payload["changes"][0]["path_array"] == ["user_types", "account", "%f3", f"status_{expected.replace('.', '_')}"]
    assert payload["changes"][0]["body"] == {"%d": "Status", "%v": expected}


def test_data_type_write_rejects_cache_only_and_ambiguous_references_before_payload_construction(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli._schema_user_types_cache()["cached"] = {"%d": "Cached", "%f3": {}}
    cli.discovery.data["user_types"]["customer"]["%d"] = "Client"
    cli.discovery.data["user_types"]["customer_2"] = {"%d": "Client", "%f3": {}}
    cli._invalidate_schema_reference_index("user_types")

    def unexpected_builder(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("PayloadBuilder constructed before current-only resolution")

    monkeypatch.setattr("bubble_mcp.aria_runtime.schema_lifecycle.data_types.PayloadBuilder", unexpected_builder)

    assert cli.rename_data_type("cached", "Nope", dry_run=True) is False
    assert cli.create_data_field("Account", "Nope", "custom.Client", dry_run=True) is False


def test_successful_field_write_projects_only_its_type_and_invalidates_user_types(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = cli.schema_reference_revision()
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)

    assert cli.create_data_field("account", "Status", "option.OS:Status") is True

    account = cli.discovery.data["user_types"]["account"]
    assert account["%f3"]["status_option_os_status"] == {"%d": "Status", "%v": "option.os_status"}
    assert account["%f3"]["email_text"]["%d"] == "Email"
    assert cli.discovery.data["user_types"]["customer"] == {"%d": "Customer", "%f3": {}}
    assert cli.schema_reference_revision() == revision + 1


def test_dispatch_failure_and_dry_run_leave_projected_data_and_indexes_untouched(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = json.loads(json.dumps(cli.discovery.data))
    revision = cli.schema_reference_revision()

    assert cli.rename_data_type("account", "Renamed", dry_run=True) is True
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: (_ for _ in ()).throw(RuntimeError("offline")))
    assert cli.rename_data_type("account", "Renamed") is False

    assert cli.discovery.data == before
    assert cli.schema_reference_revision() == revision


@pytest.mark.parametrize(
    ("operation", "expected_paths", "expected_bodies"),
    [
        (
            lambda instance: instance.create_data_type("Audit Log", dry_run=True),
            [["user_types", "audit_log"]],
            [{"%d": "Audit Log"}],
        ),
        (
            lambda instance: instance.rename_data_type("account", "Account 2", dry_run=True),
            [["user_types", "account", "%d"]],
            ["Account 2"],
        ),
        (
            lambda instance: instance.delete_data_type("account", dry_run=True),
            [["user_types", "account", "%del"]],
            [True],
        ),
        (
            lambda instance: instance.rename_data_field("account", "Email", "Email 2", dry_run=True),
            [["user_types", "account", "%f3", "email_text", "%d"]],
            ["Email 2"],
        ),
        (
            lambda instance: instance.delete_data_field("account", "Email", dry_run=True),
            [
                ["user_types", "account", "%f3", "email_text", "%del"],
                ["user_types", "account", "%f3", "email_text", "%d"],
            ],
            [True, "Email - deleted"],
        ),
        (
            lambda instance: instance.set_data_type_api_exposure("Account", True, ref_kind="label", dry_run=True),
            [["user_types", "account", "exposed_api"]],
            [True],
        ),
    ],
)
def test_data_type_lifecycle_preserves_golden_schema_payload_order(
    cli: BubbleCLI,
    capsys: pytest.CaptureFixture[str],
    operation: object,
    expected_paths: list[list[str]],
    expected_bodies: list[object],
) -> None:
    assert operation(cli) is True  # type: ignore[operator]
    payload = json.loads(capsys.readouterr().out.split("Payload preview:\n", 1)[1])
    assert [change["path_array"] for change in payload["changes"]] == expected_paths
    assert [change["body"] for change in payload["changes"]] == expected_bodies


def test_cache_callback_failure_keeps_successful_projected_data_and_invalidation(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = cli.schema_reference_revision()
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    monkeypatch.setattr(cli, "_save_cli_cache", lambda: (_ for _ in ()).throw(OSError("disk full")))

    assert cli.rename_data_type("account", "Renamed") is True
    assert cli.discovery.data["user_types"]["account"]["%d"] == "Renamed"
    assert cli.schema_reference_revision() == revision + 1


def test_data_type_service_rejects_empty_field_name_before_payload_construction(cli: BubbleCLI) -> None:
    assert cli.create_data_field("account", "", "text", dry_run=True) is False


def test_data_type_service_covers_private_and_permanent_delete_contracts(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_data_type_is_soft_deleted", lambda _key, require_fresh_schema: True)

    assert cli.create_data_type("Private", private=True, dry_run=True) is True
    assert cli.delete_data_type_permanently("account", data_type_ref_kind="name", dry_run=True) is False
    assert cli.delete_data_type_permanently("", dry_run=True) is False
    monkeypatch.setattr(cli, "_data_type_is_soft_deleted", lambda _key, require_fresh_schema: False)
    assert cli.delete_data_type_permanently("account", dry_run=True) is False
    monkeypatch.setattr(cli, "_data_type_is_soft_deleted", lambda _key, require_fresh_schema: True)
    assert cli.delete_data_type_permanently("account", confirm=False) is False
    assert cli.delete_data_type_permanently("custom.account", confirm=True, dry_run=True) is True


def test_data_type_service_rejects_missing_current_field_and_type_references(cli: BubbleCLI) -> None:
    assert cli.delete_data_type("missing", dry_run=True) is False
    assert cli.rename_data_field("account", "missing", "Nope", dry_run=True) is False
    assert cli.delete_data_field("account", "missing", dry_run=True) is False
    assert cli.create_data_field("account", "Broken", "option.Unknown", dry_run=True) is False
    assert cli.set_data_type_api_exposure("missing", True, dry_run=True) is False


@pytest.mark.parametrize("fresh_schema", [{}, {"user_types": "malformed"}])
def test_type_and_field_writes_fail_closed_without_fresh_user_type_metadata(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, fresh_schema: dict[str, object]
) -> None:
    cli.discovery._data = fresh_schema  # type: ignore[assignment]
    cli._schema_user_types_cache()["account"] = {"%d": "Cached Account", "%f3": {}}
    cli._invalidate_schema_reference_index("user_types")
    before = json.loads(json.dumps(fresh_schema))
    revision = cli.schema_reference_revision()

    def unexpected_builder(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("PayloadBuilder constructed without fresh user_types metadata")

    monkeypatch.setattr(cli, "new_schema_lifecycle_payload", unexpected_builder)

    assert cli.rename_data_type("account", "Renamed", dry_run=True) is False
    assert cli.delete_data_type("account", dry_run=True) is False
    assert cli.create_data_field("account", "Status", "text", dry_run=True) is False
    assert cli.discovery.data == before
    assert cli.schema_reference_revision() == revision


def test_successful_create_attaches_projected_schema_when_discovery_is_malformed(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.discovery._data = "malformed"  # type: ignore[assignment]
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)

    assert cli.create_data_type("Audit") is True
    assert cli.discovery.data == {"user_types": {"audit": {"%d": "Audit"}}}
    assert cli._schema_user_types_cache()["audit"] == {"%d": "Audit"}


def test_type_writes_reject_module_fallback_without_fresh_schema(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modules = tmp_path / "bubble_modules"
    (modules / "user_types").mkdir(parents=True)
    (modules / "user_types" / "__index.json").write_text(json.dumps({"account": "Module Account"}))
    cli.discovery._data = {"user_types": {}}  # type: ignore[assignment]
    monkeypatch.setattr(cli, "_bubble_modules_project_dir", lambda: str(modules))
    cli._invalidate_schema_reference_index("user_types")

    def unexpected_builder(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("PayloadBuilder constructed from module-only schema metadata")

    monkeypatch.setattr(cli, "new_schema_lifecycle_payload", unexpected_builder)

    assert cli.rename_data_type("account", "Renamed", dry_run=True) is False
