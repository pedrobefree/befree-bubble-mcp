import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from bubble_mcp.aria_runtime import bubble_sdk
from bubble_mcp.aria_runtime.bubble_sdk import (
    BubbleAppMapper,
    BubbleClient,
    BubbleIDGenerator,
    ColorBuilder,
    DynamicTextBuilder,
    FontBuilder,
    PageBuilder,
    PathBuilder,
    WebhookClient,
    WorkflowBuilder,
)


class FixedIds:
    def element_id(self) -> str:
        return "bFIXED"


class FakeResponse:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.text = "response-body"

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error


def test_id_generator_contracts_are_stable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class FixedDatetime:
        @classmethod
        def now(cls):  # type: ignore[no-untyped-def]
            return SimpleNamespace(timestamp=lambda: 1234.567)

    monkeypatch.setattr(bubble_sdk, "datetime", FixedDatetime)
    monkeypatch.setattr(bubble_sdk.random, "choices", lambda _chars, k: list("A" * k))
    values = iter([123456789012345678, 42])
    monkeypatch.setattr(bubble_sdk.random, "randint", lambda _start, _end: next(values))

    assert BubbleIDGenerator.element_id() == "bAAAA"
    assert BubbleIDGenerator.element_id(2) == "bA"
    assert BubbleIDGenerator.fiber_id() == "1234567x123456789012345678"
    assert BubbleIDGenerator.session_id() == "1234567x42"

    monkeypatch.setattr(BubbleIDGenerator, "session_id", staticmethod(lambda: "session"))
    assert BubbleIDGenerator.pl_id() == "session"


def test_path_builder_builds_and_validates_create_paths() -> None:
    assert PathBuilder.build_for_structure("page", "group", "nested") == [
        "%ed",
        "page",
        "%el",
        "group",
        "%el",
        "nested",
    ]
    assert PathBuilder.build_for_elements("page", "group") == ["%p3", "page", "%el", "group"]
    assert PathBuilder.build_for_workflow("page", "wf") == ["%p3", "page", "%wf", "wf"]

    assert PathBuilder.validate_create_path("invalid") == (False, "Path deve ser uma lista")
    assert PathBuilder.validate_create_path([]) == (False, "Path vazio")
    assert PathBuilder.validate_create_path(["other", "page"])[0] is False
    assert PathBuilder.validate_create_path(["%p3"])[0] is False
    assert PathBuilder.validate_create_path(["CustomDefinition"])[0] is True
    assert PathBuilder.validate_create_path(["%p3", "page", "%p"])[0] is False
    assert PathBuilder.validate_create_path(["%p3", "page"])[0] is True


def test_path_builder_validates_edit_paths() -> None:
    assert PathBuilder.validate_edit_path("invalid") == (False, "Path deve ser uma lista")
    assert PathBuilder.validate_edit_path(["%p3", "page"])[0] is False
    assert PathBuilder.validate_edit_path(["%p3", "page", "%el", "button"])[0] is False
    assert PathBuilder.validate_edit_path(["%p3", "page", "%el", "button", "%p", "text"])[0] is True


def test_page_builder_emits_minimal_and_enriched_pages() -> None:
    builder = PageBuilder(FixedIds())

    minimal = builder.page("index", layout="")
    assert minimal["id"] == "bFIXED"
    assert minimal["%p"]["%t1"]["%e"] == {"0": "index"}
    assert "container_layout" not in minimal["%p"]

    page = builder.page(
        "dashboard",
        title="Dashboard",
        meta_title="SEO",
        meta_description="Description",
        html_header="<meta>",
        row_gap=8,
        column_gap=12,
        use_gap=True,
        container_vert_alignment="center",
        container_horiz_alignment="stretch",
        default_width=1200,
        min_height_px=640,
        style="Page_custom",
        background="white",
        ignored=None,
        extra_props={"fixed_width": False, "custom": True},
    )
    props = page["%p"]
    assert page["%s1"] == "Page_custom"
    assert props["%t1"]["%e"] == {"0": "Dashboard"}
    assert props["meta_title"]["%e"] == {"0": "SEO"}
    assert props["%md"]["%e"] == {"0": "Description"}
    assert props["html_header"]["%e"] == {"0": "<meta>"}
    assert props["row_gap"] == 8
    assert props["column_gap"] == 12
    assert props["use_gap"] is True
    assert props["default_width"] == 1200
    assert props["min_height_px"] == 640
    assert props["container_vert_alignment"] == "center"
    assert props["container_horiz_alignment"] == "stretch"
    assert props["background"] == "white"
    assert props["fixed_width"] is False
    assert props["custom"] is True


@pytest.mark.parametrize(("parallax", "expected"), [("2", 2), ("1.5", 1.5)])
def test_page_builder_reusable_normalizes_layout_properties(
    parallax: str,
    expected: int | float,
) -> None:
    reusable = PageBuilder(FixedIds()).reusable(
        "Header",
        width="320",  # type: ignore[arg-type]
        height="80",  # type: ignore[arg-type]
        layout="row",
        element_type="FloatingGroup",
        min_height_px="40",
        default_width="320",
        row_gap="4",
        column_gap="6",
        use_gap=1,
        float_v_relative="TOP",
        float_h_relative="Right",
        float_zindex="front",
        parallax=parallax,
        data_class="custom.user",
        data_source={"%x": "CurrentUser"},
        parameters={"title": "text"},
        visible=True,
        ignored=None,
        extra_props={"visible": False, "custom": "value"},
    )
    props = reusable["%p"]
    assert props["%w"] == 320
    assert props["%h"] == 80
    assert props["%et"] == "FloatingGroup"
    assert props["%3f"] == "top"
    assert props["floating_reference_horizontal_resp"] == "right"
    assert props["%b4"] == "right"
    assert props["parallax"] == expected
    assert props["%gt"] == "custom.user"
    assert props["%ds"] == {"%x": "CurrentUser"}
    assert props["parameters"] == {"title": "text"}
    assert props["visible"] is False
    assert props["custom"] == "value"


def test_page_builder_reusable_drops_invalid_parallax() -> None:
    reusable = PageBuilder(FixedIds()).reusable("Header", layout="", parallax="invalid")
    assert "container_layout" not in reusable["%p"]
    assert "parallax" not in reusable["%p"]


def test_dynamic_text_and_workflow_builders_preserve_wire_shapes() -> None:
    current_user = DynamicTextBuilder.current_user("name", "text")
    assert DynamicTextBuilder.current_user()["%n"] is None
    assert current_user["%n"]["%nm"] == "name_text"
    assert DynamicTextBuilder.build(["Hello ", current_user]) == {
        "%x": "TextExpression",
        "%e": {"0": "Hello ", "1": current_user},
    }

    workflows = WorkflowBuilder(FixedIds())
    assert workflows.button_clicked("button") == {
        "id": "bFIXED",
        "%x": "ButtonClicked",
        "%p": {"%ei": "button"},
        "actions": {},
    }
    assert workflows.element_event("input", "change")["%p"] == {
        "%ei": "input",
        "%et": "change",
        "%eC": True,
    }


def test_color_builder_contracts_and_reordering() -> None:
    builder = ColorBuilder(FixedIds())
    colors = {
        "b": ColorBuilder.build_color_entry("Beta", "rgba(2,2,2,1)", order=1),
        "a": ColorBuilder.build_color_entry("Alpha", "rgba(1,1,1,1)", order=0),
    }

    assert builder.generate_color_id() == "bFIXED"
    assert ColorBuilder.build_default_colors_body({"primary": "rgba(1,2,3,1)"}) == {
        "primary": {"%d1": "rgba(1,2,3,1)"}
    }
    assert ColorBuilder.build_custom_colors_body(colors) == {"%d1": colors}
    assert ColorBuilder.get_default_color_path()[-1] == "color_tokens"
    assert ColorBuilder.get_custom_color_path()[-1] == "color_tokens_user"
    assert list(ColorBuilder.sort_colors_by_name(colors)) == ["a", "b"]
    assert list(ColorBuilder.sort_colors_by_name(colors, reverse=True)) == ["b", "a"]
    assert list(ColorBuilder.move_color_to_position(colors, "a", 1)) == ["b", "a"]
    assert ColorBuilder.swap_colors(colors, "a", "b")["a"]["order"] == 1
    assert ColorBuilder.swap_colors(colors, "a", "b")["b"]["order"] == 0
    with pytest.raises(ValueError, match="not found"):
        ColorBuilder.move_color_to_position(colors, "missing", 0)
    with pytest.raises(ValueError, match="One or both"):
        ColorBuilder.swap_colors(colors, "a", "missing")


def test_font_builder_contracts() -> None:
    builder = FontBuilder(FixedIds())
    entry = FontBuilder.build_font_entry("Body", "Inter", 2, "Main", True)

    assert entry == {
        "%d3": "Main",
        "%nm": "Body",
        "%del": True,
        "font_family": "Inter",
        "order": 2,
    }
    assert builder.generate_font_id() == "bFIXED"
    assert FontBuilder.build_app_font_body("Inter") == {"%d1": "Inter"}
    assert FontBuilder.build_custom_fonts_body({"font": entry}) == {"%d1": {"font": entry}}
    assert FontBuilder.get_app_font_path()[-1] == "font_tokens"
    assert FontBuilder.get_custom_font_path()[-1] == "font_tokens_user"


def test_app_mapper_reads_native_nested_pages_and_reusables(tmp_path: Path) -> None:
    source = tmp_path / "app.bubble"
    source.write_text(
        json.dumps(
            {
                "pages": {
                    "page-id": {
                        "name": "index",
                        "elements": {
                            "group-id": {
                                "default_name": "Group A",
                                "elements": {"text-id": {"name": "Title"}},
                            },
                            "invalid": "ignored",
                        },
                    },
                    "invalid": "ignored",
                },
                "element_definitions": {
                    "reusable-id": {
                        "default_name": "Header",
                        "elements": {"button-id": {"name": "CTA"}},
                    },
                    "invalid": "ignored",
                },
            }
        ),
        encoding="utf-8",
    )

    mapper = BubbleAppMapper(str(source))

    assert mapper.get_page_id("index") == "page-id"
    assert mapper.get_element_id("index", "Group A") == "group-id"
    assert mapper.get_element_id("index", "Title") == "text-id"
    assert mapper.get_page_id("Header") == "reusable-id"
    assert mapper.get_element_id("Header", "CTA") == "button-id"
    assert mapper.get_element_id("missing", "CTA") is None


def test_app_mapper_falls_back_from_corrupt_primary_to_legacy_console(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    primary = tmp_path / "app.bubble"
    primary.write_text("{", encoding="utf-8")
    console = tmp_path / "console.json"
    console.write_text(
        json.dumps(
            {
                "%p3": {
                    "page": {
                        "%x": "Page",
                        "%dn": "legacy",
                        "%el": {"text": {"%dn": "Legacy title"}},
                    },
                    "ignored": {"%x": "Other"},
                }
            }
        ),
        encoding="utf-8",
    )

    mapper = BubbleAppMapper(str(primary), str(console))

    assert mapper.get_page_id("legacy") == "page"
    assert mapper.get_element_id("legacy", "Legacy title") == "text"
    assert "Could not read app mapping source" in capsys.readouterr().out


@pytest.mark.parametrize(
    "primary_payload",
    [
        {},
        {"other": True},
        {"pages": []},
        {"pages": {"broken": "not-an-object"}},
        {"%p3": []},
    ],
)
def test_app_mapper_falls_back_from_structurally_unusable_primary(
    tmp_path: Path,
    primary_payload: dict[str, Any],
) -> None:
    primary = tmp_path / "app.bubble"
    primary.write_text(json.dumps(primary_payload), encoding="utf-8")
    console = tmp_path / "console.json"
    console.write_text(
        json.dumps(
            {
                "%p3": {
                    "page": {
                        "%x": "Page",
                        "%dn": "fallback",
                        "%el": {"text": {"%dn": "Fallback title"}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    mapper = BubbleAppMapper(str(primary), str(console))

    assert mapper.get_page_id("fallback") == "page"
    assert mapper.get_element_id("fallback", "Fallback title") == "text"


def test_app_mapper_rejects_non_object_and_unknown_sources(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert BubbleAppMapper._read_mapping_source(None) is None

    non_object = tmp_path / "list.json"
    non_object.write_text("[]", encoding="utf-8")
    assert BubbleAppMapper(str(non_object)).pages == {}
    output = capsys.readouterr().out
    assert "must contain a JSON object" in output
    assert "No app data found" in output

    unknown = tmp_path / "unknown.json"
    unknown.write_text('{"other": true}', encoding="utf-8")
    unknown_mapper = BubbleAppMapper(str(unknown))
    assert "Unknown app format" in capsys.readouterr().out
    unknown_mapper.elements["index"] = {}
    unknown_mapper._map_elements_recursive("index", [])  # type: ignore[arg-type]
    assert unknown_mapper.elements["index"] == {}


def test_app_mapper_legacy_loader_ignores_invalid_pages_and_elements(tmp_path: Path) -> None:
    source = tmp_path / "legacy.json"
    source.write_text(
        json.dumps(
            {
                "%p3": {
                    "invalid-page": "invalid",
                    "invalid-elements": {
                        "%x": "Page",
                        "%nm": "Invalid elements",
                        "%el": "invalid",
                    },
                    "mixed-elements": {
                        "%x": "ReusableElement",
                        "%nm": "Mixed elements",
                        "%el": {
                            "invalid": "invalid",
                            "valid": {"%dn": "Valid"},
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    mapper = BubbleAppMapper(str(source))

    assert mapper.get_page_id("Invalid elements") == "invalid-elements"
    assert mapper.get_page_id("Mixed elements") == "mixed-elements"
    assert mapper.get_element_id("Mixed elements", "Valid") == "valid"


def test_bubble_client_requires_authentication_and_sends_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="Cookies"):
        BubbleClient().send({})

    captured: dict[str, Any] = {}
    response = FakeResponse()

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return response

    client = BubbleClient("my-app", "session=secret")
    monkeypatch.setattr(client.id_gen, "fiber_id", lambda: "fiber")
    monkeypatch.setattr(client.id_gen, "pl_id", lambda: "pl")
    monkeypatch.setattr(bubble_sdk.requests, "post", fake_post)

    assert client.send({"changes": []}) is response
    assert captured["headers"]["x-bubble-appname"] == "my-app"
    assert captured["headers"]["x-bubble-fiber-id"] == "fiber"
    assert captured["headers"]["Cookie"] == "session=secret"
    assert captured["json"] == {"changes": []}


def test_bubble_client_logs_http_and_generic_failures(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    http_response = requests.Response()
    http_response.status_code = 500
    http_response._content = b"failure"
    http_error = requests.HTTPError("bad status", response=http_response)
    monkeypatch.setattr(
        bubble_sdk.requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(error=http_error),
    )
    with pytest.raises(requests.HTTPError):
        BubbleClient(cookies="session").send({})
    output = capsys.readouterr().out
    assert "Erro HTTP" in output
    assert "failure" in output

    monkeypatch.setattr(
        bubble_sdk.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    with pytest.raises(RuntimeError, match="offline"):
        BubbleClient(cookies="session").send({})
    assert "Erro: offline" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("body", {"app-name": "app", "appname": "app", "body": {"changes": [1]}}),
        (
            "both",
            {"app-name": "app", "appname": "app", "body": {"changes": [1]}, "changes": [1]},
        ),
        ("root", {"app-name": "app", "appname": "app", "changes": [1]}),
        ("invalid", {"app-name": "app", "appname": "app", "changes": [1]}),
    ],
)
def test_webhook_client_envelope_modes(
    tmp_path: Path,
    monkeypatch,
    mode: str,
    expected: dict[str, Any],
) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, Any] = {}
    response = FakeResponse()
    monkeypatch.setenv("BUBBLE_CLI_WEBHOOK_ENVELOPE_MODE", mode)
    monkeypatch.setenv("BUBBLE_CLI_WEBHOOK_TIMEOUT_SEC", "7")
    monkeypatch.setattr(bubble_sdk.tempfile, "gettempdir", lambda: str(tmp_path))

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return response

    monkeypatch.setattr(bubble_sdk.requests, "post", fake_post)
    client = WebhookClient("https://example.test/hook", "app")

    assert client.send({"changes": [1]}) is response
    assert captured == {
        "url": "https://example.test/hook",
        "json": expected,
        "timeout": 7,
    }
    debug_dir = tmp_path / "bubble-webhook-debug"
    assert json.loads((debug_dir / "last_payload.json").read_text(encoding="utf-8")) == {
        "changes": [1]
    }
    assert json.loads((debug_dir / "last_envelope.json").read_text(encoding="utf-8")) == expected


@pytest.mark.parametrize("value", ["invalid", "0", "-2"])
def test_webhook_client_normalizes_invalid_timeouts(monkeypatch, value: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_CLI_WEBHOOK_TIMEOUT_SEC", value)
    assert WebhookClient().timeout_seconds == 15


def test_webhook_client_ignores_debug_write_failures_and_reports_http_failure(
    monkeypatch,
    capsys,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        bubble_sdk.os,
        "makedirs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("readonly")),
    )
    response = requests.Response()
    response.status_code = 503
    response._content = b"unavailable"
    error = requests.HTTPError("failed", response=response)
    monkeypatch.setattr(
        bubble_sdk.requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(error=error),
    )

    with pytest.raises(requests.HTTPError):
        WebhookClient().send({"changes": []})
    output = capsys.readouterr().out
    assert "Erro ao enviar para Webhook" in output
    assert "Response: unavailable" in output
