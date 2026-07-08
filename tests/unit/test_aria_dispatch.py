import json
from types import SimpleNamespace

from bubble_mcp.aria_dispatch import (
    _method_kwargs,
    _requires_calculate_derived,
    dispatch_aria_runtime_tool,
)
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings


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


def test_delete_data_field_requires_calculate_derived_refresh() -> None:
    assert _requires_calculate_derived("delete_data_field") is True
    assert _requires_calculate_derived("create_privacy_rule") is True
    assert _requires_calculate_derived("set_privacy_rule_field_visibility") is True
    assert _requires_calculate_derived("delete_privacy_rule") is True
    assert _requires_calculate_derived("create_data_field") is False


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
    ) -> bool:
        return True

    condition_kwargs = _method_kwargs(
        add_style_condition,
        {"name": "HTML Button Primary", "condition": "hover"},
        execute=True,
    )
    reorder_kwargs = _method_kwargs(
        reorder_style_states,
        {"name": "HTML Button Primary", "order": "hover,focus"},
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

        def create_button(self, dry_run=False):  # type: ignore[no-untyped-def]
            builder = fake_sdk.PayloadBuilder(appname=self.appname)
            return builder.to_json()

    fake_cli = SimpleNamespace(BubbleCLI=FakeBubbleCLI)
    monkeypatch.setattr("bubble_mcp.aria_dispatch._load_aria_runtime_modules", lambda: (fake_cli, fake_sdk))

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
