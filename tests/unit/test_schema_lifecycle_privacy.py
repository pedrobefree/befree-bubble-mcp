from __future__ import annotations

import json
import copy
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI, PayloadBuilder


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "app.json"
    app_path.write_text(json.dumps({"user_types": {"account": {"%d": "Account", "%f3": {"email_text": {"%d": "Email", "%v": "text"}, "secret_text": {"%d": "Secret", "%v": "text"}}}}}), encoding="utf-8")
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cache.json"))
    return BubbleCLI(app_json_path=str(app_path), appname="schema-privacy")


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out.split("Payload preview:\n", 1)[1])


def test_privacy_create_preserves_golden_payload_order_and_default_rule(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.create_privacy_rule("account", view_all="false", view_fields="Email,secret_text", condition_json='{"%x":"CurrentUser"}', id_counter=7, dry_run=True)
    changes = _payload(capsys)["changes"]
    assert [change["path_array"] for change in changes[:2]] == [["user_types", "account", "privacy_role", "everyone"], ["user_types", "account", "privacy_role", "new_rule_"]]
    assert changes[0]["body"]["permissions"]["non_filterable_fields"] == {"email_text": True, "secret_text": True, "Created Date": True, "Modified Date": True, "Slug": True, "Created By": True}
    assert changes[1]["body"] == {"%d": "New rule", "permissions": {"view_all": False, "view_attachments": True, "search_for": True, "auto_binding": False, "view_fields": {"0": "email_text", "1": "secret_text"}}, "%c": {"%x": "CurrentUser"}}
    assert changes[2] == {"type": "id_counter", "value": 7}


def test_privacy_field_writes_resolve_current_field_keys_and_reject_cache_only_before_builder(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"permissions": {}}}
    cli._invalidate_schema_reference_index("user_types")
    cli._schema_user_types_cache()["account"] = copy.deepcopy(cli.discovery.data["user_types"]["account"])
    cli._schema_user_types_cache()["account"]["%f3"]["cached_text"] = {"%d": "Cached", "%v": "text"}
    cli._invalidate_schema_reference_index("user_types")
    assert cli.set_privacy_rule_field_visibility("account", "members", view_fields=["Email", "secret_text"], dry_run=True)
    assert _payload(capsys)["changes"][0]["body"] == {"0": "email_text", "1": "secret_text"}

    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload constructed")),
    )
    assert cli.set_privacy_rule_auto_binding("account", "members", True, ["Cached"], dry_run=True) is False


@pytest.mark.parametrize("value, expected", [(True, True), ("yes", True), (1, True), (False, False), ("off", False), (0, False)])
def test_privacy_boolean_parser_accepts_public_inputs(cli: BubbleCLI, capsys: pytest.CaptureFixture[str], value: object, expected: bool) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"permissions": {}}}
    cli._invalidate_schema_reference_index("user_types")
    assert cli.set_privacy_rule_permission("account", "members", "search_for", value, dry_run=True)
    assert _payload(capsys)["changes"][0]["body"] is expected


@pytest.mark.parametrize("operation", [
    lambda instance: instance.create_privacy_rule("account", view_all="maybe", dry_run=True),
    lambda instance: instance.set_privacy_rule_condition("account", "members", "{bad", dry_run=True),
    lambda instance: instance.set_privacy_rule_field_visibility("account", "members", view_fields="[bad", dry_run=True),
])
def test_privacy_rejects_malformed_input_before_payload_construction(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, operation: object) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"permissions": {}}}
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload constructed")),
    )
    with pytest.raises(ValueError):
        operation(cli)  # type: ignore[operator]


def test_privacy_create_rejects_malformed_id_counter_before_host_payload_factory(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload constructed")),
    )

    with pytest.raises(ValueError):
        cli.create_privacy_rule("account", id_counter="not-an-integer", dry_run=True)  # type: ignore[arg-type]


def test_successful_privacy_mutation_projects_only_rule_and_saves_once(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"%d": "Members", "plugin_key": {"safe": True}, "permissions": {"search_for": False, "opaque": {"keep": True}}}, "other": {"%d": "Other", "plugin_key": 1}}
    saves: list[int] = []
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    monkeypatch.setattr(cli, "_save_cli_cache", lambda: saves.append(1))
    assert cli.set_privacy_rule_field_visibility("account", "members", view_all=True, view_fields=["Email"])
    rules = cli.discovery.data["user_types"]["account"]["privacy_role"]
    assert rules["members"] == {"%d": "Members", "plugin_key": {"safe": True}, "permissions": {"search_for": False, "opaque": {"keep": True}, "view_all": True, "view_fields": {"0": "email_text"}}}
    assert rules["other"] == {"%d": "Other", "plugin_key": 1}
    assert saves == [1]


def test_privacy_dry_run_and_dispatch_failure_do_not_project_or_save(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    before = json.loads(json.dumps(cli.discovery.data))
    saves: list[int] = []
    monkeypatch.setattr(cli, "_save_cli_cache", lambda: saves.append(1))
    assert cli.create_privacy_rule("account", dry_run=True)
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: (_ for _ in ()).throw(RuntimeError("offline")))
    assert cli.create_privacy_rule("account") is False
    assert cli.discovery.data == before
    assert saves == []


def test_list_privacy_rules_keeps_sorted_legacy_shape(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"z": {"%d": "Zulu", "permissions": {"search_for": True}}, "a": {"permissions": {}}}
    assert cli.list_privacy_rules("account", dry_run=True) == [{"data_type_key": "account", "rule_key": "a", "name": "a", "has_condition": False, "permissions": {}}, {"data_type_key": "account", "rule_key": "z", "name": "Zulu", "has_condition": False, "permissions": {"search_for": True}}]
    assert json.loads(capsys.readouterr().out) == {"ok": True, "data_type_key": "account", "privacy_rules": cli.list_privacy_rules("account")}


def test_create_privacy_rule_uses_next_key_without_default_and_serializes_indexed_binding_fields(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"new_rule_": {}, "new_rule_1": {}}
    cli._invalidate_schema_reference_index("user_types")

    assert cli.create_privacy_rule(
        "account", auto_binding=True, binding_fields={"10": "secret_text", "2": "Email"},
        include_everyone_default=False, dry_run=True,
    )

    changes = _payload(capsys)["changes"]
    assert len(changes) == 1
    assert changes[0]["path_array"][-1] == "new_rule_2"
    assert changes[0]["body"]["permissions"]["binding_fields"] == {"0": "email_text", "1": "secret_text"}


def test_privacy_setters_and_delete_keep_golden_payload_paths(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"permissions": {}}}
    cli._invalidate_schema_reference_index("user_types")
    assert cli.set_privacy_rule_name("account", "members", "Members", dry_run=True)
    assert _payload(capsys)["changes"][0]["path_array"][-1] == "%d"
    assert cli.set_privacy_rule_condition("account", "members", '{"%x":"CurrentUser"}', dry_run=True)
    assert _payload(capsys)["changes"][0]["body"] == {"%x": "CurrentUser"}
    assert cli.set_privacy_rule_auto_binding("account", "members", False, binding_fields=["Email"], dry_run=True)
    assert [change["body"] for change in _payload(capsys)["changes"]] == [False, None]
    assert cli.delete_privacy_rule("account", "members", dry_run=True)
    assert _payload(capsys)["changes"][0] ["body"] is None


def test_privacy_rejects_invalid_permission_empty_change_and_missing_fresh_schema_before_builder(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli.set_privacy_rule_permission("account", "members", "unknown", True, dry_run=True) is False
    assert cli.set_privacy_rule_field_visibility("account", "members", dry_run=True) is False
    cli.discovery._data = {"user_types": {}}  # type: ignore[assignment]
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload constructed")),
    )
    assert cli.set_privacy_rule_field_visibility("account", "members", view_fields=["Email"], dry_run=True) is False
    assert cli.set_privacy_rule_auto_binding("account", "members", True, dry_run=True) is False
    assert cli.set_privacy_rule_field_visibility("account", "members", view_all=True, dry_run=True) is False
    assert cli.set_privacy_rule_auto_binding("account", "members", False, dry_run=True) is False


def test_privacy_field_payload_accepts_system_fields_and_rejects_wrong_json_and_field_shapes(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"permissions": {}}}
    cli._invalidate_schema_reference_index("user_types")
    assert cli.set_privacy_rule_field_visibility("account", "members", view_fields=["Created Date", "Email"], dry_run=True)
    assert _payload(capsys)["changes"][0]["body"] == {"0": "Created Date", "1": "email_text"}
    with pytest.raises(ValueError, match="fields must be"):
        cli.set_privacy_rule_field_visibility("account", "members", view_fields=object(), dry_run=True)
    with pytest.raises(ValueError, match="Invalid condition_json"):
        cli.set_privacy_rule_condition("account", "members", "null", dry_run=True)


def test_privacy_successful_create_delete_and_warning_project_only_affected_rule(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"other": {"plugin": {"keep": True}}}
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    assert cli.create_privacy_rule("account", rule_key="members")
    assert cli.discovery.data["user_types"]["account"]["privacy_role"] == {
        "other": {"plugin": {"keep": True}},
        "members": {"%d": "New rule", "permissions": {"view_all": True, "view_attachments": True, "search_for": True, "auto_binding": False}},
    }
    assert cli.delete_privacy_rule("account", "members")
    assert cli.discovery.data["user_types"]["account"]["privacy_role"] == {"other": {"plugin": {"keep": True}}}
    monkeypatch.setattr(cli, "project_schema_data_type", lambda _key, _entry: "cache warning")
    assert cli.set_privacy_rule_name("account", "other", "Other")


def test_privacy_create_rejects_missing_current_type_and_keeps_optional_binding_fields(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.create_privacy_rule("missing", view_fields=["Email"], dry_run=True) is False
    assert cli.create_privacy_rule("account", auto_binding=False, binding_fields='["Email"]', view_fields="", dry_run=True)
    permissions = _payload(capsys)["changes"][-1]["body"]["permissions"]
    assert permissions["view_fields"] == {}
    assert permissions["binding_fields"] == {"0": "email_text"}


def test_privacy_field_resolution_failure_and_nested_permission_projection_are_atomic(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": {"permissions": "opaque"}}
    cli._invalidate_schema_reference_index("user_types")
    assert cli.set_privacy_rule_field_visibility("account", "members", view_fields=["Missing"], dry_run=True) is False
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    assert cli.set_privacy_rule_permission("account", "members", "view_all", True)
    assert cli.discovery.data["user_types"]["account"]["privacy_role"]["members"] == {"permissions": {"view_all": True}}


def test_privacy_parser_handles_none_and_rejects_non_array_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.aria_runtime.schema_lifecycle.privacy import PrivacyLifecycleService

    assert PrivacyLifecycleService._parse_field_values(None) == []
    monkeypatch.setattr("bubble_mcp.aria_runtime.schema_lifecycle.privacy.json.loads", lambda _value: {"not": "a list"})
    with pytest.raises(ValueError, match="fields JSON must be an array"):
        PrivacyLifecycleService._parse_field_values("[]")


@pytest.mark.parametrize(
    "operation",
    [
        lambda instance: instance.create_privacy_rule("account", dry_run=True),
        lambda instance: instance.delete_privacy_rule("account", "members", dry_run=True),
        lambda instance: instance.set_privacy_rule_name("account", "members", "Members", dry_run=True),
        lambda instance: instance.set_privacy_rule_condition("account", "members", {"%x": "CurrentUser"}, dry_run=True),
        lambda instance: instance.set_privacy_rule_permission("account", "members", "search_for", True, dry_run=True),
        lambda instance: instance.set_privacy_rule_field_visibility("account", "members", view_all=True, dry_run=True),
        lambda instance: instance.set_privacy_rule_auto_binding("account", "members", False, dry_run=True),
    ],
)
def test_every_privacy_mutation_rejects_cache_only_type_before_payload(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, operation: object
) -> None:
    cached = copy.deepcopy(cli.discovery.data["user_types"]["account"])
    cached["privacy_role"] = {"members": {"permissions": {}}}
    cli.discovery._data = {"user_types": {}}  # type: ignore[assignment]
    cli._schema_user_types_cache()["account"] = cached
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built from cache-only privacy target")),
    )

    assert operation(cli) is False  # type: ignore[operator]


@pytest.mark.parametrize(
    ("user_types", "reference"),
    [
        ("malformed", "account"),
        ({"account": {"%d": "Account", "%del": True}}, "account"),
        ({"first": {"%d": "Duplicate"}, "second": {"%d": "Duplicate"}}, "Duplicate"),
    ],
)
def test_privacy_create_rejects_malformed_stale_and_ambiguous_current_types_before_payload(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
    user_types: object,
    reference: str,
) -> None:
    cli.discovery._data = {"user_types": user_types}  # type: ignore[assignment]
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built from invalid current privacy target")),
    )

    assert cli.create_privacy_rule(reference, dry_run=True) is False


def test_privacy_create_rejects_module_only_type_before_payload(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modules = tmp_path / "bubble_modules"
    (modules / "user_types").mkdir(parents=True)
    (modules / "user_types" / "__index.json").write_text(
        json.dumps({"module_account": "Module Account"}), encoding="utf-8"
    )
    cli.discovery._data = {"user_types": {}}  # type: ignore[assignment]
    monkeypatch.setattr(cli, "_bubble_modules_project_dir", lambda: str(modules))
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built from module-only privacy target")),
    )

    assert cli.create_privacy_rule("module_account", dry_run=True) is False


@pytest.mark.parametrize(
    "operation",
    [
        lambda instance: instance.delete_privacy_rule("account", "missing", dry_run=True),
        lambda instance: instance.set_privacy_rule_name("account", "missing", "Missing", dry_run=True),
        lambda instance: instance.set_privacy_rule_condition("account", "missing", {"%x": "CurrentUser"}, dry_run=True),
        lambda instance: instance.set_privacy_rule_permission("account", "missing", "search_for", True, dry_run=True),
        lambda instance: instance.set_privacy_rule_field_visibility("account", "missing", view_all=True, dry_run=True),
        lambda instance: instance.set_privacy_rule_auto_binding("account", "missing", False, dry_run=True),
    ],
)
def test_existing_privacy_rule_mutations_reject_missing_rule_before_payload(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, operation: object
) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {}
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built for missing privacy rule")),
    )

    assert operation(cli) is False  # type: ignore[operator]


@pytest.mark.parametrize("rule", ["malformed", {"%del": True}])
def test_existing_privacy_rule_mutations_reject_malformed_or_stale_rule_before_payload(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, rule: object
) -> None:
    cli.discovery.data["user_types"]["account"]["privacy_role"] = {"members": rule}
    cli._invalidate_schema_reference_index("user_types")
    monkeypatch.setattr(
        cli,
        "new_schema_lifecycle_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built for invalid privacy rule")),
    )

    assert cli.set_privacy_rule_name("account", "members", "Members", dry_run=True) is False
