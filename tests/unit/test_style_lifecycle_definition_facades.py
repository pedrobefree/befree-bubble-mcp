from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.style_import.runtime import create_styles_from_html_runtime


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    snapshot = tmp_path / "app.json"
    snapshot.write_text(
        json.dumps(
            {
                "styles": {
                    "Text_body_": {
                        "%d": "Body",
                        "%x": "Text",
                        "%p": {"%fs": 16},
                        "%s": {},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    return BubbleCLI(app_json_path=str(snapshot), appname="definition-facade-test")


def _signature(method: Any) -> list[tuple[str, Any]]:
    return [
        (name, parameter.default)
        for name, parameter in inspect.signature(method).parameters.items()
        if name != "self"
    ]


def test_public_definition_boolean_signatures_are_stable() -> None:
    assert _signature(BubbleCLI.create_style) == [
        ("name", inspect.Parameter.empty),
        ("element_type", inspect.Parameter.empty),
        ("dry_run", False),
        ("allow_property_match", True),
        ("kwargs", inspect.Parameter.empty),
    ]
    assert _signature(BubbleCLI.update_style_definition) == [
        ("name", inspect.Parameter.empty),
        ("element_type", inspect.Parameter.empty),
        ("dry_run", False),
        ("style_id_override", None),
        ("kwargs", inspect.Parameter.empty),
    ]
    assert _signature(BubbleCLI.add_style_condition) == [
        ("style_name", inspect.Parameter.empty),
        ("condition", inspect.Parameter.empty),
        ("dry_run", False),
        ("index", None),
        ("props", inspect.Parameter.empty),
    ]
    assert _signature(BubbleCLI.reorder_style_states) == [
        ("style_name", inspect.Parameter.empty),
        ("order_list", inspect.Parameter.empty),
        ("dry_run", False),
        ("prune_missing", False),
    ]
    assert _signature(BubbleCLI.set_default_style) == [
        ("element_type", inspect.Parameter.empty),
        ("style_id", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.rename_style) == [
        ("style_id", inspect.Parameter.empty),
        ("new_name", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.create_button_style) == [
        ("name", inspect.Parameter.empty),
        ("theme_json", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.delete_style) == [
        ("name", inspect.Parameter.empty),
        ("element_type", None),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.delete_styles) == [
        ("names", None),
        ("pattern", None),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.clear_custom_styles) == [("dry_run", False)]
    assert all(
        inspect.signature(method).return_annotation in {bool, "bool"}
        for method in (
            BubbleCLI.create_style,
            BubbleCLI.update_style_definition,
            BubbleCLI.add_style_condition,
            BubbleCLI.reorder_style_states,
            BubbleCLI.set_default_style,
            BubbleCLI.rename_style,
            BubbleCLI.create_button_style,
            BubbleCLI.delete_style,
            BubbleCLI.delete_styles,
            BubbleCLI.clear_custom_styles,
        )
    )


class _SentinelDefinitions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _call(self, name: str, *args: Any, result: Any = True, **kwargs: Any) -> Any:
        self.calls.append((name, args, kwargs))
        return result

    def create_style(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("create_style", *args, **kwargs)

    def update_style_definition(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("update_style_definition", *args, **kwargs)

    def add_style_condition(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("add_style_condition", *args, **kwargs)

    def reorder_style_states(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("reorder_style_states", *args, **kwargs)

    def set_default_style(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("set_default_style", *args, **kwargs)

    def rename_style(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("rename_style", *args, **kwargs)

    def create_button_style(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("create_button_style", *args, **kwargs)

    def delete_style(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("delete_style", *args, **kwargs)

    def delete_styles(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("delete_styles", *args, **kwargs)

    def clear_custom_styles(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("clear_custom_styles", *args, **kwargs)

    def find_style_condition_id(self, *args: Any, **kwargs: Any) -> str:
        return self._call("find_style_condition_id", *args, result="delegated-condition", **kwargs)

    def apply_state_definitions(self, *args: Any, **kwargs: Any) -> bool:
        return self._call("apply_state_definitions", *args, **kwargs)

    def normalize_state_definitions(self, *args: Any, **kwargs: Any) -> list[Any]:
        return self._call("normalize_state_definitions", *args, result=[("delegated", {})], **kwargs)

    def normalize_kwargs(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._call("normalize_kwargs", *args, result={"delegated": True}, **kwargs)

    def state_property_wire_map(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return self._call("state_property_wire_map", *args, result={"delegated": "%d"}, **kwargs)

    def build_transition_intents(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self._call("build_transition_intents", *args, result=[{"intent": "delegated"}], **kwargs)

    def normalize_trigger_alias(self, *args: Any, **kwargs: Any) -> str:
        return self._call("normalize_trigger_alias", *args, result="delegated-trigger", **kwargs)

    def parse_reorder_order(self, *args: Any, **kwargs: Any) -> list[str]:
        return self._call("parse_reorder_order", *args, result=["delegated-order"], **kwargs)


def test_all_definition_and_state_facades_delegate_without_result_translation(cli: BubbleCLI) -> None:
    sentinel = _SentinelDefinitions()
    cli._style_lifecycle.definitions = sentinel  # type: ignore[assignment]

    assert cli.create_style("New", "Text", dry_run=True, font_size=18) is True
    assert cli.update_style_definition("Body", "Text", dry_run=True, font_size=20) is True
    assert cli.add_style_condition("Body", "hover", dry_run=True, font_color="red") is True
    assert cli.reorder_style_states("Body", "hover", dry_run=True, prune_missing=True) is True
    assert cli.set_default_style("Text", "Text_body_", dry_run=True) is True
    assert cli.rename_style("Text_body_", "Renamed", dry_run=True) is True
    assert cli.create_button_style("Primary", "{}", dry_run=True) is True
    assert cli.delete_style("Body", "Text", dry_run=True) is True
    assert cli.delete_styles(names=["Body"], pattern="body", dry_run=True) is True
    assert cli.clear_custom_styles(dry_run=True) is True

    assert [call[0] for call in sentinel.calls] == [
        "create_style",
        "update_style_definition",
        "add_style_condition",
        "reorder_style_states",
        "set_default_style",
        "rename_style",
        "create_button_style",
        "delete_style",
        "delete_styles",
        "clear_custom_styles",
    ]
    assert sentinel.calls[0][1] == ("New", "Text")
    assert sentinel.calls[0][2] == {
        "dry_run": True,
        "allow_property_match": True,
        "font_size": 18,
    }


def test_legacy_helper_facades_and_condition_lookup_share_definition_service(cli: BubbleCLI) -> None:
    sentinel = _SentinelDefinitions()
    cli._style_lifecycle.definitions = sentinel  # type: ignore[assignment]

    assert cli._normalize_style_kwargs({"bg_style": "flat"}) == {"delegated": True}
    assert cli._normalize_style_state_definitions({"hover": {}}) == [("delegated", {})]
    assert cli._style_state_prop_wire_map() == {"delegated": "%d"}
    assert cli._build_style_transition_intents("Text_body_", {"font_color": "red"}) == [
        {"intent": "delegated"}
    ]
    assert cli._apply_style_state_definitions("Body", [("hover", {})], dry_run=True) is True
    assert cli._normalize_style_trigger_alias("hover") == "delegated-trigger"
    assert cli._parse_reorder_style_order("hover") == ["delegated-order"]
    assert cli.find_style_condition_id("Text_body_", "hover") == "delegated-condition"

    assert [call[0] for call in sentinel.calls] == [
        "normalize_kwargs",
        "normalize_state_definitions",
        "state_property_wire_map",
        "build_transition_intents",
        "apply_state_definitions",
        "normalize_trigger_alias",
        "parse_reorder_order",
        "find_style_condition_id",
    ]


def test_figma_import_uses_definition_service_as_compatibility_sink(cli: BubbleCLI) -> None:
    assert cli._style_lifecycle.figma_import._styles is cli._style_lifecycle.definitions


def test_successful_rename_rebuilds_long_lived_real_cli_reference_index(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli.discovery.data["styles"]["Text_opaque_"] = {
        "%d": "Article Copy",
        "%x": "Text",
        "%p": {},
        "%s": {},
    }
    assert cli.find_style_id("Article Copy", "Text") == "Text_opaque_"

    def dispatch(_payload: Any) -> None:
        cli.discovery.data["styles"]["Text_opaque_"].update(
            {"%d": "Renamed Body", "name": "Renamed Body", "display": "Renamed Body"}
        )

    monkeypatch.setattr(cli, "dispatch_style_definition_payload", dispatch)

    assert cli.rename_style("Text_opaque_", "Renamed Body") is True
    assert cli.find_style_id("Article Copy", "Text") is None
    assert cli.find_style_id("Renamed Body", "Text") == "Text_opaque_"


def test_successful_set_default_protects_new_default_during_sequential_clear(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli.discovery.data["styles"].update(
        {
            "Text_system_": {"%d": "System Body", "%x": "Text", "%p": {}, "%s": {}},
            "Text_caption_": {"%d": "Caption", "%x": "Text", "%p": {}, "%s": {}},
            "Button_system_": {
                "%d": "System Button",
                "%x": "Button",
                "%p": {},
                "%s": {},
            },
        }
    )
    cli.discovery.data["settings"] = {
        "client_safe": {
            "default_styles": {
                "Text": "Text_system_",
                "Button": "Button_system_",
            }
        }
    }
    assert cli.find_style_id("default", "Text") == "Text_system_"
    assert cli.find_style_id("default", "Button") == "Button_system_"
    dispatched: list[list[dict[str, Any]]] = []

    def capture_webhook(payload: Any, _url: str) -> None:
        dispatched.append(list(payload.changes))

    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.style_lifecycle.definitions.PayloadBuilder.send_to_webhook",
        capture_webhook,
    )

    assert cli.set_default_style("Text", "Text_body_") is True
    assert cli.discovery.data["settings"]["client_safe"]["default_styles"] == {
        "Text": "Text_body_",
        "Button": "Button_system_",
    }
    assert cli.find_style_id("default", "Button") == "Button_system_"
    assert cli.clear_custom_styles() is True

    deleted_ids = [
        change["path_array"][1]
        for change in dispatched[1]
        if change.get("intent", {}).get("name") == "DeleteStyle"
    ]
    assert deleted_ids == ["Text_system_", "Text_caption_"]
    assert "Text_body_" not in deleted_ids
    assert "Button_system_" not in deleted_ids


def test_html_style_execution_remains_failed_when_definition_sink_returns_false(
    cli: BubbleCLI,
) -> None:
    sentinel = _SentinelDefinitions()
    sentinel.create_style = lambda *args, **kwargs: False  # type: ignore[method-assign]
    cli._style_lifecycle.definitions = sentinel  # type: ignore[assignment]

    def execute(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert tool == "create_style"
        forwarded = dict(arguments)
        forwarded.pop("profile")
        forwarded.pop("execute")
        name = str(forwarded.pop("name"))
        element_type = str(forwarded.pop("element_type"))
        return {"ok": cli.create_style(name, element_type, **forwarded)}

    result = create_styles_from_html_runtime(
        profile="smoke",
        style_name="Broken HTML Button",
        element_type="Button",
        html='<button class="broken" style="color: #111111">Broken</button>',
        selector=".broken",
        execute=True,
        include_states=False,
        executor=execute,
        verifier=lambda candidate: {"ok": True, "style_name": candidate["name"]},
    )

    assert result["ok"] is False
    assert result["executed"] is False
    assert result["execution_results"] == [
        {"tool": "create_style", "ok": False, "result": {"ok": False}}
    ]


def test_figma_sync_remains_failed_when_definition_sink_returns_false(
    cli: BubbleCLI,
    tmp_path: Path,
) -> None:
    tokens = tmp_path / "tokens.json"
    tokens.write_text(
        json.dumps(
            {
                "typography": {
                    "body": {
                        "regular": {
                            "type": "typography",
                            "value": {
                                "fontFamily": "Inter",
                                "fontSize": 16,
                                "fontWeight": 400,
                                "color": "#111111",
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "naming": {"separator": " ", "case": "title"},
                "filters": {
                    "include_color_paths": [],
                    "exclude_color_paths": [],
                    "include_typography_paths": ["typography.*"],
                },
            }
        ),
        encoding="utf-8",
    )
    sentinel = _SentinelDefinitions()
    sentinel.create_style = lambda *args, **kwargs: False  # type: ignore[method-assign]
    cli._style_lifecycle.definitions = sentinel  # type: ignore[assignment]
    cli._style_lifecycle.figma_import._styles = sentinel

    assert cli.sync_figma_tokens(
        str(tokens),
        config_path=str(config),
        types="style",
    ) is False
    assert cli._last_figma_token_sync_result["ok"] is False
    assert cli._last_figma_token_sync_result["applied_counts"] == {
        "fonts": 0,
        "colors": 0,
        "styles": 0,
    }
    assert cli._last_figma_token_sync_result["errors"] == [
        "styles[0] Body Regular: style definition returned false"
    ]
