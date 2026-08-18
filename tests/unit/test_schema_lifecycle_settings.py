from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI, PayloadBuilder
from bubble_mcp.aria_runtime.schema_lifecycle.settings import PROJECT_SETTING_ALIASES, SettingsLifecycleService
from bubble_mcp.server.schemas import list_tool_schemas


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "favicon": "old.ico",
                "settings": {
                    "client_safe": {
                        "app_rights": "private",
                        "301_redirects": {
                            "redirect_account": {"%fr": "/account", "to": "/profile"},
                            "redirect_docs": {"%fr": "/docs/*", "to": "/help"},
                        },
                    },
                    "secure": {"%pw": "old-secret"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cache.json"))
    return BubbleCLI(app_json_path=str(app_path), appname="schema-settings")


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    preview = capsys.readouterr().out.split("Payload preview:\n", 1)[1]
    return json.JSONDecoder().raw_decode(preview)[0]


def test_registry_captures_all_project_alias_paths_and_declared_types() -> None:
    assert PROJECT_SETTING_ALIASES["favicon"] == {"path": ["favicon"], "value_type": "string"}
    assert PROJECT_SETTING_ALIASES["preview-password-protection"] == {
        "path": ["settings", "client_safe", "pw_protection"], "value_type": "bool"
    }


def test_setting_and_redirect_tool_schemas_keep_existing_required_fields_and_preview_defaults() -> None:
    tools = {tool["name"]: tool for tool in list_tool_schemas()}
    expected_required = {
        "set_app_setting": ["profile"],
        "set_project_setting": ["profile"],
        "list_project_settings": ["profile"],
        "list_301_redirects": ["profile"],
        "create_301_redirect": ["profile", "from_url", "to_url"],
        "delete_301_redirect": ["profile"],
    }
    for name, required in expected_required.items():
        schema = tools[name]["inputSchema"]
        assert schema["required"] == required
        assert schema["properties"]["dry_run"]["default"] is True
    assert PROJECT_SETTING_ALIASES["password-min-length"]["value_type"] == "int"
    assert PROJECT_SETTING_ALIASES["workflow-max-depth-live"]["value_type"] == "auto"
    assert set(PROJECT_SETTING_ALIASES) == {
        "app-rights", "preview-password-protection", "preview-username", "preview-password",
        "preview-password-dev-only", "password-policy-enabled", "password-min-length",
        "password-require-number", "password-require-capital", "password-require-special-char",
        "temp-password-redirect-page", "iframe-policy", "cookie-opt-in", "disable-file-upload-api",
        "favicon", "status-bar-color", "spinner-color", "ios-hide-safari-ui", "ios-prevent-zoom",
        "google-geocode-key", "google-map-key", "advanced-timezone-controls",
        "advanced-timezone-date-time-inputs", "advanced-timezone-page", "advanced-timezone-backend-workflows",
        "advanced-expose-id-option", "advanced-show-parens", "api-backend-workflows-enabled",
        "api-data-enabled", "api-data-use-display-fields", "api-hide-swagger-docs", "workflow-max-depth-dev",
        "workflow-max-depth-live", "meta-title", "meta-site-name", "meta-description", "meta-thumbnail",
        "seo-expose-text-tags", "seo-enable-canonical-url", "seo-customize-robots-txt-enabled",
        "seo-custom-robots-txt", "seo-generate-sitemap", "seo-sitemap-pages", "seo-header-meta-tags",
        "seo-body-scripts", "seo-allow-wildcard-redirects", "app-primary-language", "user-language-field",
    }


@pytest.mark.parametrize(
    ("value_type", "value", "expected"),
    [
        ("string", 4, "4"), ("bool", "yes", True), ("int", "04", 4), ("float", "1.5", 1.5),
        ("auto", "null", None), ("json", '["a", true]', {"0": "a", "1": True}),
    ],
)
def test_set_app_setting_preserves_golden_payload_path_and_type_coercion(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str], value_type: str, value: object, expected: object
) -> None:
    assert cli.set_app_setting("favicon" if value_type == "string" else "settings.client_safe.setting", value, value_type, dry_run=True)
    change = _payload(capsys)["changes"][0]  # type: ignore[index]
    assert change["intent"] == {"name": "ChangeAppSetting", "id": change["intent"]["id"], "source_appname": ""}
    assert change["path_array"] == (["favicon"] if value_type == "string" else ["settings", "client_safe", "setting"])
    assert change["body"] == expected


def test_invalid_setting_values_and_paths_fail_before_payload_creation(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.schema_lifecycle.settings.PayloadBuilder",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")),
    )
    assert cli.set_app_setting([], "x", dry_run=True) is False
    assert cli.set_app_setting("settings.client_safe.flag", "not-bool", "bool", dry_run=True) is False
    assert cli.set_app_setting("settings.client_safe.flag", "x", "unknown", dry_run=True) is False
    assert cli.set_project_setting("unknown", "x", dry_run=True) is False


def test_project_alias_list_and_root_setting_paths_keep_legacy_output(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.set_project_setting("password-min-length", "12", dry_run=True)
    assert _payload(capsys)["changes"][0]["path_array"] == ["settings", "client_safe", "pw_length"]  # type: ignore[index]
    assert cli.set_project_setting("favicon", "new.ico", dry_run=True)
    assert _payload(capsys)["changes"][0]["path_array"] == ["favicon"]  # type: ignore[index]
    assert cli.list_project_settings(as_json=True)
    rows = json.loads(capsys.readouterr().out)
    assert rows == sorted(rows, key=lambda row: row["alias"])
    assert next(row for row in rows if row["alias"] == "favicon") == {"alias": "favicon", "path": "favicon", "value_type": "string"}


def test_project_setting_text_list_and_redirect_lists_keep_legacy_output(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.list_project_settings()
    project_output = capsys.readouterr().out
    assert project_output.startswith("📋 Project setting aliases (48):\n")
    assert "- favicon (string): favicon\n" in project_output
    assert cli.list_301_redirects()
    assert capsys.readouterr().out == (
        "📋 301 redirects (2):\n"
        "- redirect_account: /account -> /profile\n"
        "- redirect_docs: /docs/* -> /help\n"
    )
    assert cli.list_301_redirects(as_json=True)
    assert json.loads(capsys.readouterr().out) == [
        {"key": "redirect_account", "from": "/account", "to": "/profile"},
        {"key": "redirect_docs", "from": "/docs/*", "to": "/help"},
    ]


def test_redirect_payloads_use_deterministic_rule_keys_and_preserve_siblings(cli: BubbleCLI, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.create_301_redirect("/new/*", "/destination", rule_key="redirect_new", id_counter=8, dry_run=True)
    payload = _payload(capsys)
    assert [change["path_array"] for change in payload["changes"] if "path_array" in change] == [  # type: ignore[index]
        ["settings", "client_safe", "301_redirects", "redirect_new"]
    ]
    assert payload["changes"][0]["body"] == {"%fr": "/new/*", "to": "/destination"}  # type: ignore[index]
    assert payload["changes"][1] == {"type": "id_counter", "value": 8}  # type: ignore[index]
    assert cli.delete_301_redirect("redirect_account", dry_run=True)
    assert _payload(capsys)["changes"][0]["body"] is None  # type: ignore[index]


def test_redirects_are_current_only_and_malformed_or_duplicate_writes_fail_closed(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    cli._cli_cache.setdefault("schema", {}).setdefault("profiles", {}).setdefault(cli._schema_profile_key(), {})["redirects"] = {
        "cached": {"%fr": "/cached", "to": "/nope"}
    }
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.schema_lifecycle.settings.PayloadBuilder",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")),
    )
    assert cli.delete_301_redirect("cached", dry_run=True) is False
    assert cli.create_301_redirect("/account", "/other", rule_key="redirect_other", dry_run=True) is False
    cli.discovery._data["settings"]["client_safe"]["301_redirects"] = {"bad": "not-a-rule"}  # type: ignore[index]
    cli._invalidate_schema_reference_index("redirects")
    assert cli.delete_301_redirect("bad", dry_run=True) is False


@pytest.mark.parametrize(
    ("settings", "operation"),
    [
        (None, lambda instance: instance.create_301_redirect("/new", "/destination", rule_key="new", dry_run=True)),
        ({}, lambda instance: instance.create_301_redirect("/new", "/destination", rule_key="new", dry_run=True)),
        ({"client_safe": {}}, lambda instance: instance.create_301_redirect("/new", "/destination", rule_key="new", dry_run=True)),
    ],
)
def test_redirect_create_allows_missing_current_containers(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str], settings: object, operation: object
) -> None:
    if settings is None:
        cli.discovery._data.pop("settings")  # type: ignore[union-attr]
    else:
        cli.discovery._data["settings"] = settings  # type: ignore[index]
    cli._invalidate_schema_reference_index("redirects")
    assert operation(cli)  # type: ignore[operator]
    assert _payload(capsys)["changes"][0]["path_array"][-1] == "new"  # type: ignore[index]


@pytest.mark.parametrize(
    ("settings", "operation"),
    [
        ("bad", lambda instance: instance.create_301_redirect("/new", "/destination", rule_key="new", dry_run=True)),
        ({"client_safe": "bad"}, lambda instance: instance.create_301_redirect("/new", "/destination", rule_key="new", dry_run=True)),
        ({"client_safe": {"301_redirects": []}}, lambda instance: instance.delete_301_redirect("missing", dry_run=True)),
    ],
)
def test_redirect_writes_reject_malformed_current_containers_before_payload(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, settings: object, operation: object
) -> None:
    cli.discovery._data["settings"] = settings  # type: ignore[index]
    cli._invalidate_schema_reference_index("redirects")
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.schema_lifecycle.settings.PayloadBuilder",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")),
    )
    assert operation(cli) is False  # type: ignore[operator]


@pytest.mark.parametrize(
    "operation",
    [
        lambda instance: instance.create_301_redirect("", "/destination", rule_key="new", dry_run=True),
        lambda instance: instance.create_301_redirect("/new", "", rule_key="new", dry_run=True),
        lambda instance: instance.create_301_redirect("/new", "/destination", rule_key=" ", dry_run=True),
        lambda instance: instance.create_301_redirect("/new", "/destination", rule_key="new", id_counter="bad", dry_run=True),
        lambda instance: instance.delete_301_redirect("missing", dry_run=True),
    ],
)
def test_redirect_validation_fails_before_payload(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, operation: object) -> None:
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.schema_lifecycle.settings.PayloadBuilder",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")),
    )
    assert operation(cli) is False  # type: ignore[operator]


def test_settings_and_redirect_success_projects_atomically_without_general_schema_cache(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    before_cache = copy.deepcopy(cli._cli_cache)
    revision = cli.schema_reference_revision()
    saves = 0
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    original_save = cli._save_cli_cache

    def count_save() -> None:
        nonlocal saves
        saves += 1
        original_save()

    monkeypatch.setattr(cli, "_save_cli_cache", count_save)
    assert cli.set_project_setting("preview-password", "updated-secret")
    assert cli.create_301_redirect("/new", "/destination", rule_key="redirect_new")
    assert cli.delete_301_redirect("redirect_account")
    assert cli.discovery.data["settings"]["secure"]["%pw"] == "updated-secret"
    redirects = cli.discovery.data["settings"]["client_safe"]["301_redirects"]
    assert redirects["redirect_new"] == {"%fr": "/new", "to": "/destination"}
    assert "redirect_account" not in redirects and "redirect_docs" in redirects
    assert cli._cli_cache == before_cache
    assert cli.schema_reference_revision() == revision + 2
    assert saves == 0


def test_settings_dry_run_and_dispatch_failure_do_not_project_or_save(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    before = copy.deepcopy(cli.discovery.data)
    revision = cli.schema_reference_revision()
    monkeypatch.setattr(cli, "_save_cli_cache", lambda: (_ for _ in ()).throw(AssertionError("cache saved")))
    assert cli.set_project_setting("app-rights", "public", dry_run=True)
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: (_ for _ in ()).throw(RuntimeError("offline")))
    assert cli.create_301_redirect("/new", "/destination", rule_key="redirect_new") is False
    assert cli.discovery.data == before
    assert cli.schema_reference_revision() == revision


def test_setting_path_validation_and_post_success_warning_are_preserved(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.schema_lifecycle.settings.PayloadBuilder",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")),
    )
    assert cli.set_app_setting('["settings", ""]', "x", dry_run=True) is False
    monkeypatch.undo()
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    monkeypatch.setattr(cli, "project_schema_settings", lambda _updates: "projection warning")
    assert cli.set_project_setting("app-rights", "public")


def test_sensitive_setting_messages_do_not_contain_values(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: (_ for _ in ()).throw(RuntimeError("offline")))
    assert cli.set_project_setting("preview-password", "very-secret") is False
    assert "very-secret" not in capsys.readouterr().out
    assert SettingsLifecycleService._is_sensitive_path(["settings", "secure", "%pw"])
    assert not SettingsLifecycleService._is_sensitive_path(["favicon"])
    assert not SettingsLifecycleService._is_sensitive_path("settings.secure.%pw")
    assert cli.set_project_setting("preview-password", "very-secret", dry_run=True)
    preview = capsys.readouterr().out
    assert "very-secret" not in preview and "[REDACTED]" in preview
