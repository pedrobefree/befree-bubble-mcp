import json
from types import SimpleNamespace

import pytest

from bubble_mcp.aria_dispatch import (
    AriaRuntimeEnvironment,
    _delete_data_type_follow_up,
    _method_kwargs,
    _requires_calculate_derived,
    _resolve_runtime_environment,
    dispatch_aria_runtime_tool,
)
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.sessions.store import save_session, session_from_payload


def test_method_kwargs_maps_public_schema_aliases_to_aria_runtime_args() -> None:
    def create_data_field(
        data_type_key: str,
        field_name: str,
        field_type: str,
        dry_run: bool = False,
    ) -> bool:
        return True

    kwargs = _method_kwargs(
        create_data_field,
        {
            "profile": "smoke",
            "data_type_ref": "user",
            "name": "company",
            "type": "text",
            "execute": False,
        },
        execute=False,
    )

    assert kwargs == {
        "data_type_key": "user",
        "field_name": "company",
        "field_type": "text",
        "dry_run": True,
    }


@pytest.mark.parametrize("arguments", [{"enabled": True}, {"value": True}])
def test_method_kwargs_maps_canonical_and_legacy_api_exposure_flags_to_enabled(
    arguments: dict[str, bool],
) -> None:
    def set_data_type_api_exposure(
        data_type_ref: str,
        enabled: bool,
        ref_kind: str = "key",
        dry_run: bool = False,
    ) -> bool:
        return True

    kwargs = _method_kwargs(
        set_data_type_api_exposure,
        {"profile": "smoke", "data_type_ref": "user", **arguments, "execute": False},
        execute=False,
    )

    assert kwargs == {
        "data_type_ref": "user",
        "enabled": True,
        "dry_run": True,
    }


def test_method_kwargs_scopes_family_four_name_aliases_without_changing_unrelated_defaults() -> None:
    def create_button(
        name: str,
        label: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        return True

    def create_option_attribute(
        option_set_key: str,
        name: str,
        value_type: str,
        attribute_key: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        return True

    def create_option_value(
        option_set_key: str,
        label: str,
        value_key: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        return True

    def reorder_option_values(
        option_set_key: str,
        assignments: list[str],
        ref_kind: str = "key",
        dry_run: bool = False,
    ) -> bool:
        return True

    assert _method_kwargs(
        create_button,
        {"profile": "smoke", "name": "Submit", "execute": False},
        execute=False,
    ) == {"name": "Submit", "dry_run": True}
    assert _method_kwargs(
        create_option_attribute,
        {
            "profile": "smoke",
            "option_set_ref": "os_status",
            "name": "Display Attribute",
            "type": "text",
            "execute": False,
        },
        execute=False,
    ) == {
        "option_set_key": "os_status",
        "name": "Display Attribute",
        "value_type": "text",
        "dry_run": True,
    }
    assert _method_kwargs(
        create_option_value,
        {
            "profile": "smoke",
            "option_set_ref": "os_status",
            "name": "Pending",
            "value_key": "pending",
            "execute": False,
        },
        execute=False,
    ) == {
        "option_set_key": "os_status",
        "label": "Pending",
        "value_key": "pending",
        "dry_run": True,
    }
    assert _method_kwargs(
        reorder_option_values,
        {
            "profile": "smoke",
            "option_set_ref": "os_status",
            "order": ["pending:1"],
            "ref_kind": "auto",
            "execute": False,
        },
        execute=False,
    ) == {
        "option_set_key": "os_status",
        "assignments": ["pending:1"],
        "ref_kind": "auto",
        "dry_run": True,
    }


def test_method_kwargs_maps_email_recipient_alias() -> None:
    def add_event_action(
        context_name: str,
        action_type: str,
        to_email: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        return True

    kwargs = _method_kwargs(
        add_event_action,
        {
            "context": "index",
            "action_type": "send_email",
            "to": "person@example.com",
            "execute": False,
        },
        execute=False,
    )

    assert kwargs == {
        "context_name": "index",
        "action_type": "send_email",
        "to_email": "person@example.com",
        "dry_run": True,
    }


def test_method_kwargs_maps_delete_data_field_name_to_field_key() -> None:
    def delete_data_field(
        data_type_key: str,
        field_key: str,
        dry_run: bool = False,
    ) -> bool:
        return True

    kwargs = _method_kwargs(
        delete_data_field,
        {
            "profile": "smoke",
            "data_type_ref": "user",
            "name": "campo_novo_text",
            "execute": False,
        },
        execute=False,
    )

    assert kwargs == {
        "data_type_key": "user",
        "field_key": "campo_novo_text",
        "dry_run": True,
    }


def test_method_kwargs_maps_permanent_data_type_delete_confirmation() -> None:
    def delete_data_type_permanently(
        data_type_key: str,
        data_type_ref_kind: str = "auto",
        confirm: bool = False,
        dry_run: bool = False,
    ) -> bool:
        return True

    kwargs = _method_kwargs(
        delete_data_type_permanently,
        {
            "profile": "smoke",
            "data_type_ref": "Cliente",
            "data_type_ref_kind": "name",
            "confirm": True,
            "execute": True,
        },
        execute=True,
    )

    assert kwargs == {
        "data_type_key": "Cliente",
        "data_type_ref_kind": "name",
        "confirm": True,
        "dry_run": False,
    }


def test_sensitive_mcp_dispatch_preserves_remote_request_without_local_secret_egress(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    secret = "literal-sensitive-mcp-username"
    export_path = tmp_path / "current.bubble"
    export_path.write_text(json.dumps({"settings": {"secure": {}}}), encoding="utf-8")
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="literal-app",
                    appname="literal-app",
                    app_version="test",
                    app_json_path=str(export_path),
                )
            },
        )
    )
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "literal-app",
                "appVersion": "test",
                "headers": {"Cookie": "sid=" + "synthetic-session"},
            }
        ),
    )
    remote_payloads: list[dict[str, object]] = []

    def fake_write(_self, payload, _session, **_kwargs):  # type: ignore[no-untyped-def]
        remote_payloads.append(json.loads(json.dumps(payload)))
        return {
            "ok": True,
            "request": {"payload": payload},
            "response": {"debug": f"remote echoed {secret}"},
        }

    monkeypatch.setattr("bubble_mcp.aria_dispatch.BubbleEditorClient.write", fake_write)
    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch.record_mutation_overlay",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("sensitive overlay persisted")),
    )

    result = dispatch_aria_runtime_tool(
        "set_project_setting",
        {
            "profile": "smoke",
            "name": "preview-username",
            "value": secret,
            "execute": True,
        },
    )

    assert result is not None
    assert result["ok"] is True
    assert remote_payloads[0]["changes"][0]["path_array"] == ["settings", "secure", "username"]  # type: ignore[index]
    assert remote_payloads[0]["changes"][0]["body"] == secret  # type: ignore[index]
    assert secret not in json.dumps(result, sort_keys=True)
    assert not any(
        secret.encode() in path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )


def test_sensitive_mcp_dispatch_with_short_secret_preserves_trusted_response_metadata(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    secret = "a"
    export_path = tmp_path / "current.bubble"
    export_path.write_text(json.dumps({"settings": {"secure": {}}}), encoding="utf-8")
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="literal-app",
                    appname="literal-app",
                    app_version="test",
                    app_json_path=str(export_path),
                )
            },
        )
    )
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "literal-app",
                "appVersion": "test",
                "headers": {"Cookie": "sid=" + "synthetic-session"},
            }
        ),
    )

    def fake_write(_self, payload, _session, **_kwargs):  # type: ignore[no-untyped-def]
        print(f"echo::{secret}")
        return {
            "ok": True,
            "request": {"payload": payload},
            "response": {"debug": f"echo::{secret}"},
        }

    monkeypatch.setattr("bubble_mcp.aria_dispatch.BubbleEditorClient.write", fake_write)

    result = dispatch_aria_runtime_tool(
        "set_project_setting",
        {
            "profile": "smoke",
            "name": "preview-username",
            "value": secret,
            "execute": True,
        },
    )

    assert result is not None
    assert result["engine"] == "aria_runtime"
    assert result["app_id"] == "literal-app"
    assert result["tool_name"] == "set_project_setting"
    assert result["profile"] == "smoke"
    assert result["ok"] is True
    assert result["executed"] is True
    assert result["compiled"] is True
    assert result["write_count"] == 1
    assert result["return_value"] is True
    editor_result = result["results"][0]["result"]
    assert editor_result["request"]["payload"]["changes"][0]["body"] == "[REDACTED]"
    assert editor_result["response"]["debug"] == "echo::[REDACTED]"
    assert "echo::[REDACTED]" in result["logs"]


def test_sensitive_batch_sends_secret_once_without_returning_or_persisting_it(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    secret = "literal-sensitive-batch-private-key"
    export_path = tmp_path / "current.bubble"
    export_path.write_text(json.dumps({"settings": {"secure": {"api_tokens": {}}}}), encoding="utf-8")
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="literal-app",
                    appname="literal-app",
                    app_version="test",
                    app_json_path=str(export_path),
                )
            },
        )
    )
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "literal-app",
                "appVersion": "test",
                "headers": {"Cookie": "sid=synthetic-session"},
            }
        ),
    )
    remote_payloads: list[dict[str, object]] = []

    def fake_write(_self, payload, _session, **_kwargs):  # type: ignore[no-untyped-def]
        remote_payloads.append(json.loads(json.dumps(payload)))
        return {
            "ok": True,
            "request": {"payload": payload},
            "response": {"debug": f"remote echoed {secret}"},
        }

    monkeypatch.setattr("bubble_mcp.aria_dispatch.BubbleEditorClient.write", fake_write)
    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch.record_mutation_overlay",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("sensitive overlay persisted")),
    )

    result = dispatch_aria_runtime_tool(
        "batch",
        {
            "profile": "smoke",
            "commands": [
                {
                    "command": "create-api-token",
                    "token_id": "token-1",
                    "private_key": secret,
                    "label": "Regression token",
                }
            ],
            "execute": True,
        },
    )

    assert result is not None
    assert result["ok"] is True
    assert len(remote_payloads) == 1
    assert secret in json.dumps(remote_payloads[0], sort_keys=True)
    assert secret not in json.dumps(result, sort_keys=True)
    assert not any(
        secret.encode() in path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )


def test_batch_reports_remote_success_when_overlay_persistence_fails(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    export_path = tmp_path / "current.bubble"
    export_path.write_text(json.dumps({"settings": {"client_safe": {}}}), encoding="utf-8")
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="literal-app",
                    appname="literal-app",
                    app_version="test",
                    app_json_path=str(export_path),
                )
            },
        )
    )
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "literal-app",
                "appVersion": "test",
                "headers": {"Cookie": "sid=synthetic-session"},
            }
        ),
    )

    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch.BubbleEditorClient.write",
        lambda _self, payload, _session, **_kwargs: {
            "ok": True,
            "request": {"payload": payload},
            "response": {"status": 200},
        },
    )

    def fail_overlay(**_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr("bubble_mcp.aria_dispatch.record_mutation_overlay", fail_overlay)

    result = dispatch_aria_runtime_tool(
        "batch",
        {
            "profile": "smoke",
            "commands": [
                {
                    "command": "set-project-setting",
                    "setting_key": "app-rights",
                    "value": "private",
                }
            ],
            "execute": True,
        },
    )

    assert result is not None
    assert result["ok"] is True
    assert "Remote write succeeded" in result["results"][0]["local_state_warning"]
    assert "Remote write succeeded" in result["warnings"][0]


def test_delete_data_field_requires_calculate_derived_refresh() -> None:
    assert _requires_calculate_derived("delete_data_field") is True
    assert _requires_calculate_derived("delete_data_type_permanently") is False
    assert _requires_calculate_derived("create_privacy_rule") is True
    assert _requires_calculate_derived("set_privacy_rule_field_visibility") is True
    assert _requires_calculate_derived("delete_privacy_rule") is True
    assert _requires_calculate_derived("create_data_field") is False


def test_soft_delete_returns_separate_permanent_delete_confirmation_follow_up() -> None:
    follow_up = _delete_data_type_follow_up(
        "delete_data_type",
        ok=True,
        execute=True,
        profile="smoke",
        app_id="bovichain-g3",
        app_version="23347",
        data_type_ref="del_analytics_sat",
    )

    assert follow_up == {
        "action": "ask_whether_to_delete_data_type_permanently",
        "question": (
            "Data type 'del_analytics_sat' was soft-deleted in branch '23347'. "
            "Do you want to delete this exact data type permanently? "
            "Permanent deletion cannot be undone."
        ),
        "tool_name": "delete_data_type_permanently",
        "requires_new_confirmation": True,
        "target": {
            "profile": "smoke",
            "app_id": "bovichain-g3",
            "app_version": "23347",
            "data_type_ref": "del_analytics_sat",
        },
    }
    assert _delete_data_type_follow_up("delete_data_type", ok=True, execute=False) is None
    assert _delete_data_type_follow_up("delete_data_type", ok=False, execute=True) is None
    assert _delete_data_type_follow_up("delete_data_type_permanently", ok=True, execute=True) is None


def test_permanent_delete_environment_refreshes_authoritative_export(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="bovichain-g3",
                    appname="bovichain-g3",
                    app_version="23347",
                )
            },
        )
    )
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "bovichain-g3",
                "appVersion": "23347",
                "headers": {"Cookie": "sid=secret"},
            }
        ),
    )
    refreshed = tmp_path / "bovichain-g3.bubble"
    refreshed.write_text(json.dumps({"user_types": {}}), encoding="utf-8")
    calls = []

    def fake_refresh(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return refreshed

    monkeypatch.setattr("bubble_mcp.aria_dispatch.refresh_bubble_export", fake_refresh)

    env = _resolve_runtime_environment({"profile": "smoke"}, authoritative_refresh=True)

    assert calls == [{"profile": "smoke", "app_id": "bovichain-g3", "app_version": "23347"}]
    assert env.app_json_path == str(refreshed)


def test_permanent_delete_environment_rejects_caller_context_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="bovichain-g3",
                    appname="bovichain-g3",
                    app_version="23347",
                )
            },
        )
    )

    with pytest.raises(ValueError, match="does not accept caller-supplied context artifacts"):
        _resolve_runtime_environment(
            {"profile": "smoke", "bubble_file": str(tmp_path / "forged.bubble")},
            authoritative_refresh=True,
        )


def test_runtime_environment_resolves_profile_artifacts_from_config_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    bubble_file = tmp_path / "contexts" / "smoke" / "bovichain-g3.bubble"
    consolelog_file = tmp_path / "contexts" / "smoke" / "consolelog.json"
    bubble_file.parent.mkdir(parents=True)
    bubble_file.write_text("{}", encoding="utf-8")
    consolelog_file.write_text("{}", encoding="utf-8")
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="bovichain-g3",
                    appname="bovichain-g3",
                    app_version="23347",
                    app_json_path="contexts/smoke/bovichain-g3.bubble",
                    consolelog_json_path="contexts/smoke/consolelog.json",
                )
            },
        )
    )

    def unexpected_detect(**_kwargs):
        raise AssertionError("existing configured artifacts must not trigger context detection")

    monkeypatch.setattr("bubble_mcp.aria_dispatch.detect_project_context", unexpected_detect)

    env = _resolve_runtime_environment({"profile": "smoke"})

    assert env.app_json_path == str(bubble_file)
    assert env.consolelog_json_path == str(consolelog_file)


def test_permanent_delete_reports_remote_success_when_overlay_fails_and_verifies_readback(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "bovichain-g3",
                "appVersion": "23347",
                "headers": {"Cookie": "sid=secret"},
            }
        ),
    )
    refreshed = tmp_path / "bovichain-g3.bubble"
    refreshed.write_text(json.dumps({"user_types": {}}), encoding="utf-8")

    class FakePayloadBuilder:
        def __init__(self, appname="synthetic-page", app_version="test", metadata=None):  # type: ignore[no-untyped-def]
            self.appname = appname
            self.app_version = app_version

        def build(self):  # type: ignore[no-untyped-def]
            return {
                "appname": self.appname,
                "app_version": self.app_version,
                "changes": [
                    {
                        "intent": {"name": "CleanApp"},
                        "path_array": ["user_types", "cliente"],
                        "body": None,
                    }
                ],
            }

        def send_to_webhook(self, _url=""):  # type: ignore[no-untyped-def]
            return {"ok": True}

        def to_json(self, indent=2):  # type: ignore[no-untyped-def]
            return json.dumps(self.build(), indent=indent)

    class FakePathDiscovery:
        def __init__(self, _app_path, *_args):  # type: ignore[no-untyped-def]
            self.data = json.loads(refreshed.read_text(encoding="utf-8"))

    fake_sdk = SimpleNamespace(PayloadBuilder=FakePayloadBuilder)

    class FakeBubbleCLI:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.appname = kwargs["appname"]
            self.app_version = kwargs["app_version"]

        def delete_data_type_permanently(self, **_kwargs):  # type: ignore[no-untyped-def]
            return fake_sdk.PayloadBuilder(
                appname=self.appname,
                app_version=self.app_version,
            ).send_to_webhook()

    fake_cli = SimpleNamespace(BubbleCLI=FakeBubbleCLI, PathDiscovery=FakePathDiscovery)
    monkeypatch.setattr("bubble_mcp.aria_dispatch._load_aria_runtime_modules", lambda: (fake_cli, fake_sdk))
    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch._resolve_runtime_environment",
        lambda _args, **_kwargs: AriaRuntimeEnvironment(
            profile="smoke",
            app_id="bovichain-g3",
            app_version="23347",
            app_json_path=str(refreshed),
            consolelog_json_path=None,
            crawler_index_path=None,
            mutation_overlay_path=str(tmp_path / "overlay.json"),
        ),
    )
    monkeypatch.setattr("bubble_mcp.aria_dispatch.refresh_bubble_export", lambda **_kwargs: refreshed)
    def fail_overlay(**_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr("bubble_mcp.aria_dispatch.record_mutation_overlay", fail_overlay)
    monkeypatch.setattr(
        "bubble_mcp.aria_dispatch.BubbleEditorClient.write",
        lambda _self, payload, _session, **_kwargs: {
            "ok": True,
            "request": {"payload": payload},
            "response": {"status": 200},
        },
    )

    result = dispatch_aria_runtime_tool(
        "delete_data_type_permanently",
        {
            "profile": "smoke",
            "data_type_ref": "cliente",
            "execute": True,
            "confirm": True,
        },
    )

    assert result is not None
    assert result["ok"] is True
    assert "Remote write succeeded" in result["results"][0]["local_state_warning"]
    assert "Remote write succeeded" in result["warnings"][0]
    assert result["verification"]["status"] == "verified"
    assert result["verification"]["absent_from_fresh_export"] is True


def test_method_kwargs_maps_style_condition_aliases() -> None:
    def add_style_condition(
        style_name: str,
        condition: str,
        dry_run: bool = False,
    ) -> bool:
        return True

    def reorder_style_states(
        style_name: str,
        order_list: str,
        dry_run: bool = False,
        prune_missing: bool = False,
    ) -> bool:
        return True

    condition_kwargs = _method_kwargs(
        add_style_condition,
        {"name": "HTML Button Primary", "condition": "hover"},
        execute=True,
    )
    reorder_kwargs = _method_kwargs(
        reorder_style_states,
        {"name": "HTML Button Primary", "order": "hover,focus", "prune_missing": True},
        execute=True,
    )

    assert condition_kwargs == {
        "style_name": "HTML Button Primary",
        "condition": "hover",
        "dry_run": False,
    }
    assert reorder_kwargs == {
        "style_name": "HTML Button Primary",
        "order_list": "hover,focus",
        "dry_run": False,
        "prune_missing": True,
    }


def test_method_kwargs_maps_visual_and_workflow_aliases() -> None:
    def create_image(context_name: str, parent_name: str, name: str, source: str, dry_run: bool = False) -> bool:
        return True

    image_kwargs = _method_kwargs(
        create_image,
        {
            "context": "index",
            "parent": "root",
            "name": "im_logo",
            "image_url": "https://example.com/logo.png",
            "execute": False,
        },
        execute=False,
    )

    assert image_kwargs == {
        "context_name": "index",
        "parent_name": "root",
        "name": "im_logo",
        "source": "https://example.com/logo.png",
        "dry_run": True,
    }

    def create_workflow(context_name: str, element_name: str, event_type: str = "click", dry_run: bool = False) -> bool:
        return True

    workflow_kwargs = _method_kwargs(
        create_workflow,
        {
            "context": "index",
            "element_name": "Page",
            "event": "PageLoaded",
            "execute": False,
        },
        execute=False,
    )

    assert workflow_kwargs == {
        "context_name": "index",
        "element_name": "Page",
        "event_type": "PageLoaded",
        "dry_run": True,
    }

    def add_action(
        context_name: str,
        element_name: str,
        action_type: str,
        action_param: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        return True

    action_kwargs = _method_kwargs(
        add_action,
        {
            "context": "index",
            "element_name": "bt_save",
            "action_type": "hide",
            "param": "bt_save",
            "execute": True,
        },
        execute=True,
    )

    assert action_kwargs == {
        "context_name": "index",
        "element_name": "bt_save",
        "action_type": "hide",
        "action_param": "bt_save",
        "dry_run": False,
    }


def test_aria_runtime_payload_builder_inherits_profile_app_version(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    bubble_file = tmp_path / "app.bubble"
    bubble_file.write_text("{}", encoding="utf-8")
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="branch-profile",
            profiles={
                "branch-profile": BubbleProfile(
                    name="branch-profile",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="feature-branch",
                    app_json_path=str(bubble_file),
                )
            },
        )
    )

    class FakePayloadBuilder:
        def __init__(self, appname="synthetic-page", app_version="test", metadata=None):  # type: ignore[no-untyped-def]
            self.appname = appname
            self.app_version = app_version
            self.metadata = metadata or {}

        def build(self):  # type: ignore[no-untyped-def]
            return {
                "appname": self.appname,
                "app_version": self.app_version,
                "changes": [
                    {
                        "intent": {"name": "CreateElement"},
                        "body": {
                            "%p": {
                                "%w": 320,
                                "%h": 180,
                                "fixed_width": True,
                                "fixed_height": True,
                            }
                        },
                    }
                ],
            }

        def send_to_webhook(self, _url=""):  # type: ignore[no-untyped-def]
            return {"ok": True}

        def to_json(self, indent=2):  # type: ignore[no-untyped-def]
            return json.dumps(self.build(), indent=indent)

    fake_sdk = SimpleNamespace(PayloadBuilder=FakePayloadBuilder)

    class FakeBubbleCLI:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.appname = kwargs["appname"]

        def create_text(self, dry_run=False):  # type: ignore[no-untyped-def]
            builder = fake_sdk.PayloadBuilder(appname=self.appname)
            return builder.to_json()

    fake_cli = SimpleNamespace(BubbleCLI=FakeBubbleCLI)
    monkeypatch.setattr("bubble_mcp.aria_dispatch._load_aria_runtime_modules", lambda: (fake_cli, fake_sdk))

    result = dispatch_aria_runtime_tool("create_text", {"profile": "branch-profile"})

    assert result is not None
    assert result["ok"] is True
    assert result["app_version"] == "feature-branch"
    payload = result["results"][0]["payload"]
    assert payload["app_version"] == "feature-branch"
    properties = payload["changes"][0]["body"]["%p"]
    assert properties["min_width_css"] == "320px"
    assert properties["max_width_css"] == "320px"
    assert properties["min_height_css"] == "180px"
    assert properties["max_height_css"] == "180px"


def test_aria_runtime_applies_project_default_styles_to_created_elements(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    bubble_file = tmp_path / "app.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "app": {
                    "settings": {
                        "client_safe": {
                            "default_styles": {
                                "Group": "Group_runtime_default",
                                "Text": "Text_runtime_default",
                                "Button": "Button_runtime_default",
                                "Input": "Input_runtime_default",
                                "RadioButtons": "Radio_runtime_default",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="runtime-profile",
            profiles={
                "runtime-profile": BubbleProfile(
                    name="runtime-profile",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="test",
                    app_json_path=str(bubble_file),
                )
            },
        )
    )

    class FakePayloadBuilder:
        def __init__(self, appname="synthetic-page", app_version="test", metadata=None):  # type: ignore[no-untyped-def]
            self.appname = appname
            self.app_version = app_version
            self.metadata = metadata or {}

        def build(self):  # type: ignore[no-untyped-def]
            return {
                "appname": self.appname,
                "app_version": self.app_version,
                "changes": [
                    {
                        "intent": {"name": "CreateElement"},
                        "body": {
                            "%x": "Group",
                            "%p": {},
                        },
                    },
                    {
                        "intent": {"name": "CreateElement"},
                        "body": {
                            "%x": "Text",
                            "%p": {},
                        },
                    },
                    {
                        "intent": {"name": "CreateElement"},
                        "body": {
                            "%x": "Button",
                            "%p": {
                                "fit_height": True,
                                "fit_width": True,
                                "single_width": False,
                            },
                        },
                    },
                    {
                        "intent": {"name": "CreateElement"},
                        "body": {
                            "%x": "Input",
                            "%s1": "Input_std_dash_",
                            "%p": {
                                "%h": 44,
                            },
                        },
                    },
                    {
                        "intent": {"name": "CreateElement"},
                        "body": {
                            "%x": "RadioButtons",
                            "%p": {
                                "fit_height": True,
                            },
                        },
                    }
                ],
            }

        def send_to_webhook(self, _url=""):  # type: ignore[no-untyped-def]
            return {"ok": True}

        def to_json(self, indent=2):  # type: ignore[no-untyped-def]
            return json.dumps(self.build(), indent=indent)

    fake_sdk = SimpleNamespace(PayloadBuilder=FakePayloadBuilder)

    class FakeBubbleCLI:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.appname = kwargs["appname"]
            self.discovery = SimpleNamespace(data=json.loads(bubble_file.read_text(encoding="utf-8")))

        def create_button(self, dry_run=False):  # type: ignore[no-untyped-def]
            builder = fake_sdk.PayloadBuilder(appname=self.appname)
            return builder.to_json()

    fake_cli = SimpleNamespace(BubbleCLI=FakeBubbleCLI)
    monkeypatch.setattr("bubble_mcp.aria_dispatch._load_aria_runtime_modules", lambda: (fake_cli, fake_sdk))

    def unexpected_artifact_read(_path):  # type: ignore[no-untyped-def]
        raise AssertionError("loaded runtime discovery data should be reused for style metadata")

    monkeypatch.setattr("bubble_mcp.aria_dispatch.style_metadata_from_artifact", unexpected_artifact_read)

    result = dispatch_aria_runtime_tool("create_button", {"profile": "runtime-profile"})

    assert result is not None
    payload = result["results"][0]["payload"]
    group_body = payload["changes"][0]["body"]
    text_body = payload["changes"][1]["body"]
    body = payload["changes"][2]["body"]
    properties = body["%p"]
    assert group_body["%s1"] == "Group_runtime_default"
    assert text_body["%s1"] == "Text_runtime_default"
    assert body["%s1"] == "Button_runtime_default"
    assert properties["fit_height"] is True
    assert properties["fit_width"] is True
    input_body = payload["changes"][3]["body"]
    radio_body = payload["changes"][4]["body"]
    assert input_body["%s1"] == "Input_runtime_default"
    assert radio_body["%s1"] == "Radio_runtime_default"


def test_add_action_schema_args_are_accepted_by_runtime_signature() -> None:
    """Every arg the MCP schema advertises for add_action must reach BubbleCLI.add_action.

    Regression: the schema advertised event_ref/event_type/ref_kind but the runtime
    signature lacked them, so _method_kwargs silently dropped the workflow reference
    and add_action fell back to element/event matching (auto-creating duplicates).
    """

    import inspect

    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
    from bubble_mcp.server.agent_catalog import _legacy_fields_for_name
    from bubble_mcp.aria_dispatch import ARG_ALIASES, CONTROL_ARG_KEYS

    fields = _legacy_fields_for_name("add_action")
    assert fields is not None
    required, optional = fields
    signature = inspect.signature(BubbleCLI.add_action)
    accepted = set(signature.parameters)
    alias_targets = {alias: param for param, aliases in ARG_ALIASES.items() for alias in aliases}
    ignorable = set(CONTROL_ARG_KEYS) | {"profile", "context", "dry_run", "settings_path"}

    missing = []
    for field in (*required, *optional):
        if field in ignorable:
            continue
        if field in accepted:
            continue
        if alias_targets.get(field) in accepted:
            continue
        missing.append(field)
    assert missing == [], f"schema args dropped by BubbleCLI.add_action: {missing}"


def test_add_action_delegates_to_add_event_action_for_event_ref() -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    cli = object.__new__(BubbleCLI)
    captured: dict = {}

    def fake_add_event_action(**kwargs):
        captured.update(kwargs)
        return True

    cli.add_event_action = fake_add_event_action

    ok = BubbleCLI.add_action(
        cli,
        "dashboard",
        None,
        "show_alert",
        event_ref="bTYJT0",
        ref_kind="key",
        message="hello",
        dry_run=True,
    )

    assert ok is True
    assert captured["context_name"] == "dashboard"
    assert captured["event_ref"] == "bTYJT0"
    assert captured["ref_kind"] == "key"
    assert captured["action_type"] == "show_alert"
    assert captured["message"] == "hello"
    assert captured["dry_run"] is True


def test_add_action_without_element_or_ref_fails_with_guidance(capsys) -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    cli = object.__new__(BubbleCLI)
    ok = BubbleCLI.add_action(cli, "dashboard", None, "show_alert", message="x", dry_run=True)

    assert ok is False
    out = capsys.readouterr().out
    assert "event_ref" in out


def test_select_trusted_workflow_rows_prefers_noncache_then_root_then_recent_cache() -> None:
    """Guard regression: a workflow created via MCP lives only in the local cache until the
    .bubble export is re-downloaded. The old guard discarded such rows and auto-created a
    duplicate workflow. Cached rows newer than (root mtime - tolerance) must be trusted."""

    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    noncache = {"key": "a", "from_cache": False, "updated_at": 10}
    cached_in_root = {"key": "b", "from_cache": True, "updated_at": 20}
    cached_recent = {"key": "c", "from_cache": True, "updated_at": 1_000_000}
    cached_stale = {"key": "d", "from_cache": True, "updated_at": 100}

    # 1. Non-cache rows always win.
    pool = BubbleCLI._select_trusted_workflow_rows(
        [noncache, cached_recent], exists_in_root=lambda row: False, root_source_mtime_ms=2_000_000
    )
    assert pool == [noncache]

    # 2. Cache-only rows that the root confirms are kept.
    pool = BubbleCLI._select_trusted_workflow_rows(
        [cached_in_root, cached_stale], exists_in_root=lambda row: row is cached_in_root, root_source_mtime_ms=2_000_000
    )
    assert pool == [cached_in_root]

    # 3. Cache-only rows newer than the root snapshot (minus tolerance) are trusted even when
    #    the root does not (yet) contain them — the root cannot refute what it predates.
    tolerance = BubbleCLI._WORKFLOW_CACHE_ROOT_TOLERANCE_MS
    pool = BubbleCLI._select_trusted_workflow_rows(
        [cached_recent, cached_stale],
        exists_in_root=lambda row: False,
        root_source_mtime_ms=1_000_000 + tolerance - 1,
    )
    assert pool == [cached_recent]

    # 4. Cache-only rows older than the root snapshot stay untrusted (deleted/ghost refs).
    pool = BubbleCLI._select_trusted_workflow_rows(
        [cached_stale], exists_in_root=lambda row: False, root_source_mtime_ms=10_000_000
    )
    assert pool == []

    # 5. Unknown root mtime: trust only rows that are recent relative to the current time.
    cached_recent_now = {"key": "e", "from_cache": True, "updated_at": int(__import__("time").time() * 1000)}
    pool = BubbleCLI._select_trusted_workflow_rows(
        [cached_recent_now, cached_stale], exists_in_root=lambda row: False, root_source_mtime_ms=None
    )
    assert pool == [cached_recent_now]


def test_context_root_source_mtime_uses_existing_crawler_when_bubble_export_is_absent(tmp_path) -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    crawler_path = tmp_path / "crawler.json"
    crawler_path.write_text("{}", encoding="utf-8")
    cli = object.__new__(BubbleCLI)
    cli.discovery = SimpleNamespace(
        app_json_path=None,
        consolelog_json_path=None,
        crawler_index_path=str(crawler_path),
    )

    assert BubbleCLI._context_root_source_mtime_ms(cli) == int(crawler_path.stat().st_mtime * 1000)


def test_runtime_environment_falls_back_to_profile_default_crawler_index(tmp_path, monkeypatch) -> None:
    """Crawler-only profiles must work without an explicit crawler_index_path argument."""

    import json as _json

    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="crawler-profile",
            profiles={
                "crawler-profile": BubbleProfile(
                    name="crawler-profile",
                    app_id="crawler-app",
                    appname="crawler-app",
                    app_version="test",
                )
            },
        )
    )
    from bubble_mcp.context.detector import default_crawler_index_path

    crawler_path = default_crawler_index_path("crawler-profile", "crawler-app")
    crawler_path.parent.mkdir(parents=True, exist_ok=True)
    crawler_path.write_text(_json.dumps({"pages": [{"id": "p1", "name": "index", "elements": {}}]}), encoding="utf-8")

    from bubble_mcp.aria_dispatch import _resolve_runtime_environment

    env = _resolve_runtime_environment({"profile": "crawler-profile"})
    assert env.crawler_index_path == str(crawler_path)


def test_update_layout_whitelist_covers_font_order_rotation() -> None:
    """update_layout silently returned False for font_size/order/rotation, forcing agents
    into style workarounds. The whitelist must accept these common element properties."""

    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    cli = object.__new__(BubbleCLI)
    cases = {
        "font_size": "font_size",
        "font color": "font_color",
        "font_family": "font_family",
        "order": "order",
        "rotation_angle": "rotation_angle",
        "border_roundness": "%br",
    }
    for raw, expected in cases.items():
        assert BubbleCLI._normalize_layout_property(cli, raw) == expected, raw
    assert BubbleCLI._coerce_layout_value(cli, "font_size", "15px") == 15
    assert BubbleCLI._coerce_layout_value(cli, "font_family", "Comic Sans MS") == "Comic Sans MS"
    cli._resolve_color_arg = lambda value: value  # color resolution needs app context
    assert BubbleCLI._coerce_layout_value(cli, "font_color", "#8A8A8A") == "#8A8A8A"
    assert BubbleCLI._coerce_layout_value(cli, "order", "3") == 3
    assert BubbleCLI._coerce_layout_value(cli, "rotation_angle", -3) == -3


def test_fixed_size_normalizer_prefers_explicit_css_over_legacy_width() -> None:
    """A shape created with min_width='19px', fixed_width=True was rewritten to 100px
    because the normalizer preferred the builder's default %w=100 over the explicit CSS."""

    from bubble_mcp.aria_dispatch import _normalize_fixed_size_properties

    props = {"fixed_width": True, "single_width": True, "%w": 100, "min_width_css": "19px"}
    _normalize_fixed_size_properties(props)
    assert props["min_width_css"] == "19px"
    assert props["max_width_css"] == "19px"

    legacy = {"fixed_width": True, "%w": 40}
    _normalize_fixed_size_properties(legacy)
    assert legacy["min_width_css"] == "40px"
    assert legacy["max_width_css"] == "40px"

    height = {"fixed_height": True, "%h": 100, "min_height_css": "4px"}
    _normalize_fixed_size_properties(height)
    assert height["min_height_css"] == "4px"
    assert height["max_height_css"] == "4px"


def test_create_queue_assigns_incremental_child_order() -> None:
    """Batch-created siblings all got order 0 (renderer showed them reversed): the
    create queue must stamp %p.order = max(sibling)+1 when the body has none."""

    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
    from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
    from bubble_mcp.aria_runtime.visual_mutations import VisualMutationService

    cli = object.__new__(BubbleCLI)
    cli._canonicalize_context_prefix_on_path = lambda path, context_id, context_type: path
    cli._visual_mutations = VisualMutationService(cli)
    parent = {"id": "pg1", "element": {"id": "pg1", "%el": {"a": {"id": "a", "%p": {"order": 4}}}}}
    pb = PayloadBuilder(appname="t")
    body = {"id": "n1", "%x": "Shape", "%dn": "s", "%p": {"%w": 10}}
    BubbleCLI._queue_create_element_with_index_updates(
        cli, pb=pb, context_id="pg1", context_type="page", parent_result=parent,
        create_path=["%p3", "pg1", "%el", "k1"], create_body=body, full_path_str="x",
    )
    assert body["%p"]["order"] == 5

    # explicit order is preserved
    pb2 = PayloadBuilder(appname="t")
    body2 = {"id": "n2", "%x": "Shape", "%dn": "s2", "%p": {"order": 9}}
    BubbleCLI._queue_create_element_with_index_updates(
        cli, pb=pb2, context_id="pg1", context_type="page", parent_result=parent,
        create_path=["%p3", "pg1", "%el", "k2"], create_body=body2, full_path_str="x",
    )
    assert body2["%p"]["order"] == 9


def test_icon_normalization_maps_dashed_libs_and_rejects_unknown() -> None:
    """ion-checkmark was written verbatim and rendered nothing. Dashed library prefixes
    must map to the canonical '<lib> <name>' form; unknown libraries must return None so
    callers can fail with the accepted formats instead of writing a dead glyph."""

    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    cli = object.__new__(BubbleCLI)
    def norm(value):  # type: ignore[no-untyped-def]
        return BubbleCLI._normalize_icon_value_for_write(cli, value)

    assert norm("ion-checkmark") == "ion checkmark"
    assert norm("feather-check") == "feather check"
    assert norm("fa fa-check") == "fa fa-check"
    assert norm("phosphor regular check-circle") == "phosphor regular check-circle"
    assert norm("wingdings-star") is None
    assert norm("checkmark") is None


def test_extract_error_from_logs_surfaces_last_failure_line() -> None:
    from bubble_mcp.aria_dispatch import _extract_error_from_logs

    logs = "Searching for context: index\n\u274c Element 'foo' not found\nSearching again"
    assert _extract_error_from_logs(logs) == "Element 'foo' not found"
    assert _extract_error_from_logs("all fine here") is None
    assert _extract_error_from_logs("") is None
    assert "Unsupported layout property" in _extract_error_from_logs(
        "info line\nUnsupported layout property: 'bogus'"
    )
