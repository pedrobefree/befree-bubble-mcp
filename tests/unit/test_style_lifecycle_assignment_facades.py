from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    snapshot_path = tmp_path / "app.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "styles": {
                    "Text_body_": {"%d": "Body", "%x": "Text", "%p": {"%fs": 16}},
                    "Text_heading_": {"%d": "Heading", "%x": "Text", "%p": {"%fs": 32}},
                },
                "pages": {
                    "index": {
                        "id": "index",
                        "name": "index",
                        "elements": {
                            "hero": {
                                "id": "hero-id",
                                "%x": "Text",
                                "%dn": "Hero",
                                "%s1": "Text_body_",
                                "%p": {"%3": "Hello", "%fs": 18},
                            }
                        },
                    }
                },
                "_index": {"id_to_path": {"hero-id": "%p3.index.%el.hero"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    return BubbleCLI(app_json_path=str(snapshot_path), appname="assignment-facade-test")


class _SentinelOverrides:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def override_keys(
        self,
        element_type: str | None,
        *,
        target_style_id: str | None = None,
    ) -> list[str]:
        self.calls.append(("override_keys", element_type, target_style_id))
        return ["delegated-key"]

    def marker_keys(self) -> list[str]:
        self.calls.append(("marker_keys",))
        return ["delegated-marker"]

    def base_override_keys(self) -> list[str]:
        self.calls.append(("base_override_keys",))
        return ["delegated-base-key"]

    def prune(
        self,
        properties: dict[str, Any],
        *,
        element_type: str | None,
        style_id: str | None,
        sdk_properties: bool = False,
    ) -> None:
        self.calls.append(("prune", element_type, style_id, sdk_properties, dict(properties)))
        properties.clear()
        properties["delegated"] = True


class _SentinelAssignments:
    def __init__(self) -> None:
        self.overrides = _SentinelOverrides()
        self.calls: list[tuple[Any, ...]] = []

    def clear_markers(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("clear_markers", args, kwargs))

    def assign(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("assign", args, kwargs))

    def clear(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("clear", args, kwargs))


def test_bubble_cli_family_two_callbacks_delegate_without_signature_changes(cli: BubbleCLI) -> None:
    sentinel = _SentinelAssignments()
    cli._style_lifecycle.assignments = sentinel  # type: ignore[assignment]
    payload = PayloadBuilder(appname=cli.appname)
    path = ["%p3", "index", "%el", "hero"]

    assert cli._style_override_keys_for_element_type("Text", target_style_id="Text_heading_") == [
        "delegated-key"
    ]
    assert cli._style_marker_prop_keys() == ["delegated-marker"]
    assert cli._alert_style_override_keys() == ["delegated-base-key"]
    wire_updates = {"%fs": 32}
    sdk_updates = {"font_size": 32}
    cli._prune_style_redundant_prop_updates(
        wire_updates,
        element_type="Text",
        style_id="Text_heading_",
    )
    cli._prune_redundant_properties(sdk_updates, "Text_heading_", element_type="Text")
    cli._queue_clear_style_marker_props(payload, path, prop_updates={"style": "keep"})
    cli._queue_style_assignment_changes(
        payload,
        path,
        "Text_heading_",
        style_props={"%fs": 32},
        include_set_data=False,
    )
    cli._queue_clear_style_assignment_changes(payload, path, include_set_data=False)

    assert wire_updates == {"delegated": True}
    assert sdk_updates == {"delegated": True}
    assert sentinel.overrides.calls == [
        ("override_keys", "Text", "Text_heading_"),
        ("marker_keys",),
        ("base_override_keys",),
        ("prune", "Text", "Text_heading_", False, {"%fs": 32}),
        ("prune", "Text", "Text_heading_", True, {"font_size": 32}),
    ]
    assert [call[0] for call in sentinel.calls] == ["clear_markers", "assign", "clear"]
    assert sentinel.calls[1][2] == {
        "style_props": {"%fs": 32},
        "include_set_data": False,
    }
    assert sentinel.calls[2][2] == {"include_set_data": False}


def test_real_bubble_cli_assignment_facades_accept_runtime_payload_builder(cli: BubbleCLI) -> None:
    payload = bubble_cli_module.PayloadBuilder(appname=cli.appname)
    path = ["%p3", "index", "%el", "hero"]

    cli._queue_clear_style_marker_props(payload, path, prop_updates={"style": "keep"})
    cli._queue_style_assignment_changes(
        payload,
        path,
        "Text_heading_",
        style_props={"%fs": 32, "%fc": None},
        include_set_data=False,
    )

    rows = [
        (
            change.get("intent", {}).get("name"),
            change.get("path_array"),
            change.get("body"),
        )
        for change in payload.changes
    ]
    assert rows == [
        ("SetData", path + ["%p", "%s1"], None),
        ("SetData", path + ["%p", "style_id"], None),
        ("SetData", path + ["%p", "style_name"], None),
        ("SetData", path + ["%p", "style_ref"], None),
        ("SetData", path + ["%p", "style_reference"], None),
        ("AssignStyle", path + ["%s1"], "Text_heading_"),
        ("AssignStyle", path + ["%p"], {"%fs": 32}),
    ]


def test_update_style_and_update_style_all_emit_no_write_for_unresolved_styles(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sends: list[str] = []
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: sends.append(url),
    )

    assert cli.update_style("index", "Hero", "Missing style") is False
    assert cli.update_style_all("index", "Text", "Body", "Missing style") is False
    assert sends == []


def test_failed_style_dispatch_does_not_mutate_discovery_or_cli_cache(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery_before = copy.deepcopy(cli.discovery.data)
    assert cli._find_context("index") == ("index", "page")
    assert cli.find_style_id_by_name("Heading") == "Text_heading_"
    cache_before = copy.deepcopy(cli._cli_cache)

    def fail_send(self: Any, url: str) -> None:
        del self, url
        raise RuntimeError("literal assignment dispatch failure")

    monkeypatch.setattr(bubble_cli_module.PayloadBuilder, "send_to_webhook", fail_send)

    assert cli.update_style("index", "Hero", "Heading") is False
    assert cli.discovery.data == discovery_before
    assert cli._cli_cache == cache_before
