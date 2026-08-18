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
                "headers": {"Cookie": "sid=" + "session-only"},
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
                "headers": {"Cookie": "sid=" + "session-only"},
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
