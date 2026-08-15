from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.bubble_sdk import ColorBuilder, FontBuilder


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    snapshot_path = tmp_path / "app.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "settings": {
                    "client_safe": {
                        "color_tokens": {"primary": {"%d1": "rgba(1, 2, 3, 1)"}},
                        "color_tokens_user": {
                            "default": {
                                "cBrand": {
                                    "%nm": "Brand",
                                    "rgba": "rgba(4, 5, 6, 1)",
                                    "order": 0,
                                }
                            }
                        },
                        "font_tokens": {"%d1": "Inter"},
                        "font_tokens_user": {
                            "default": {
                                "fBody": {
                                    "%nm": "Body",
                                    "font_family": "Source Sans 3",
                                    "order": 0,
                                }
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cli-cache.json"))
    return BubbleCLI(app_json_path=str(snapshot_path), appname="token-facade-test")


def _signature(method: Any) -> list[tuple[str, Any]]:
    return [
        (name, parameter.default)
        for name, parameter in inspect.signature(method).parameters.items()
        if name != "self"
    ]


def test_public_color_and_font_boolean_signatures_are_stable() -> None:
    assert _signature(BubbleCLI.create_color) == [
        ("name", inspect.Parameter.empty),
        ("rgba", inspect.Parameter.empty),
        ("description", ""),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.update_color) == [
        ("name", inspect.Parameter.empty),
        ("rgba", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.delete_color) == [
        ("name", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.delete_colors) == [("names", None), ("pattern", None), ("dry_run", False)]
    assert _signature(BubbleCLI.reorder_colors) == [
        ("mode", inspect.Parameter.empty),
        ("color_name", None),
        ("target", None),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.create_font) == [
        ("name", inspect.Parameter.empty),
        ("font_family", inspect.Parameter.empty),
        ("description", ""),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.update_font) == [
        ("name", inspect.Parameter.empty),
        ("font_family", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert _signature(BubbleCLI.delete_font) == [
        ("name", inspect.Parameter.empty),
        ("dry_run", False),
    ]
    assert inspect.signature(BubbleCLI.create_color).return_annotation in {bool, "bool"}
    assert inspect.signature(BubbleCLI.create_font).return_annotation in {bool, "bool"}


def test_color_read_facades_share_canonical_lifecycle_resolution(cli: BubbleCLI) -> None:
    assert cli._get_current_default_colors() == {"primary": "rgba(1, 2, 3, 1)"}
    assert cli._get_current_custom_colors()["cBrand"]["%nm"] == "Brand"
    assert cli._get_active_custom_colors()["cBrand"]["rgba"] == "rgba(4, 5, 6, 1)"
    assert cli._find_color_by_name("BRAND")[0:2] == ("custom", "cBrand")  # type: ignore[index]
    assert cli.resolve_color_variable("Brand") == "var(--color_cBrand_default)"
    assert cli.resolve_color_variable("Primary") == "var(--color_primary_default)"


def test_public_color_create_returns_bool_while_internal_service_returns_real_id(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []
    generated = iter(["cInternal", "cPublic"])
    monkeypatch.setattr(ColorBuilder, "generate_color_id", lambda self: next(generated))
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: sent.append(self.build()),
    )

    internal = cli._style_lifecycle.colors.create("Internal", "rgba(7, 8, 9, 1)")
    public = cli.create_color("Public", "rgba(10, 11, 12, 1)")

    assert internal.ok is True
    assert internal.token_id == "cInternal"
    assert public is True
    assert type(public) is bool
    assert set(cli._cli_cache["colors"]) == {"cInternal", "cPublic"}
    assert len(sent) == 2


def test_color_dry_run_and_failed_dispatch_do_not_mutate_cache(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = copy.deepcopy(cli._cli_cache)
    sends: list[str] = []
    monkeypatch.setattr(ColorBuilder, "generate_color_id", lambda self: "cPreview")
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: sends.append(url),
    )

    assert cli.create_color("Preview", "rgba(1, 1, 1, 1)", dry_run=True) is True
    assert sends == []
    assert cli._cli_cache == before

    def fail_send(self: Any, url: str) -> None:
        del self, url
        raise RuntimeError("facade color failure")

    monkeypatch.setattr(bubble_cli_module.PayloadBuilder, "send_to_webhook", fail_send)
    assert cli.update_color("Brand", "rgba(9, 9, 9, 1)") is False
    assert cli._cli_cache == before


def test_font_read_and_mutation_facades_use_lifecycle_service(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: "fActual")
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: sent.append(self.build()),
    )

    assert cli._get_current_app_font() == "Inter"
    assert cli._get_current_custom_fonts()["fBody"]["font_family"] == "Source Sans 3"
    assert cli._find_font_by_name("source sans 3")[0:2] == ("custom", "fBody")  # type: ignore[index]
    internal = cli._style_lifecycle.fonts.create("Mono", "DM Mono")

    assert internal.ok is True
    assert internal.token_id == "fActual"
    assert cli.update_font("Body", "Noto Sans") is True
    assert cli.delete_font("App Font") is False
    assert cli.delete_font("Mono") is True
    assert [change["intent"]["name"] for payload in sent for change in payload["changes"]] == [
        "ChangeAppSetting",
        "ChangeAppSetting",
        "ChangeAppSetting",
    ]
    assert "fActual" not in cli._cli_cache["fonts"]


def test_font_dry_run_and_failed_dispatch_do_not_mutate_cache(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = copy.deepcopy(cli._cli_cache)
    sends: list[str] = []
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: "fPreview")
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: sends.append(url),
    )

    assert cli.create_font("Preview", "Inter Tight", dry_run=True) is True
    assert sends == []
    assert cli._cli_cache == before

    def fail_send(self: Any, url: str) -> None:
        del self, url
        raise RuntimeError("facade font failure")

    monkeypatch.setattr(bubble_cli_module.PayloadBuilder, "send_to_webhook", fail_send)
    assert cli.update_font("Body", "Noto Sans") is False
    assert cli._cli_cache == before


def test_successive_token_writes_read_the_real_host_updated_discovery(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []
    color_ids = iter(["cSecond", "cThird"])
    font_ids = iter(["fSecond"])
    monkeypatch.setattr(ColorBuilder, "generate_color_id", lambda self: next(color_ids))
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: next(font_ids))
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: sent.append(self.build()),
    )

    assert cli.update_color("Brand", "rgba(90, 91, 92, 1)") is True
    assert cli.create_color("Second", "rgba(20, 21, 22, 1)") is True
    assert cli.delete_color("Brand") is True
    assert cli.create_color("Third", "rgba(30, 31, 32, 1)") is True
    assert cli.update_font("Body", "Noto Sans") is True
    assert cli.create_font("Second font", "Literata") is True

    second_color_map = sent[1]["changes"][0]["body"]["%d1"]
    third_color_map = sent[3]["changes"][0]["body"]["%d1"]
    second_font_map = sent[5]["changes"][0]["body"]["%d1"]
    assert second_color_map["cBrand"]["rgba"] == "rgba(90, 91, 92, 1)"
    assert third_color_map["cBrand"]["%del"] is True
    assert second_font_map["fBody"]["font_family"] == "Noto Sans"


def test_reorder_500_colors_persists_real_cli_cache_once(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colors = {
        f"c{index:03d}": {
            "%nm": f"Color {499 - index:03d}",
            "rgba": f"rgba({index % 256}, 0, 0, 1)",
            "order": index,
        }
        for index in range(500)
    }
    cli.discovery.data["settings"]["client_safe"]["color_tokens_user"] = {
        "default": copy.deepcopy(colors)
    }
    cli._cli_cache["colors"] = copy.deepcopy(colors)
    save_count = 0

    def save_cache() -> None:
        nonlocal save_count
        save_count += 1

    monkeypatch.setattr(cli, "_save_cli_cache", save_cache)
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: None,
    )

    assert cli.reorder_colors("sort-az") is True
    assert save_count == 1
    assert sorted(entry["order"] for entry in cli._cli_cache["colors"].values()) == list(
        range(500)
    )


def test_bulk_color_delete_persists_real_cli_cache_once(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colors = {
        f"c{index:02d}": {
            "%nm": f"Delete {index:02d}",
            "rgba": f"rgba({index}, 0, 0, 1)",
            "order": index,
        }
        for index in range(12)
    }
    cli.discovery.data["settings"]["client_safe"]["color_tokens_user"] = {
        "default": copy.deepcopy(colors)
    }
    cli._cli_cache["colors"] = copy.deepcopy(colors)
    save_count = 0

    def save_cache() -> None:
        nonlocal save_count
        save_count += 1

    monkeypatch.setattr(cli, "_save_cli_cache", save_cache)
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: None,
    )

    assert cli.delete_colors(names=[f"Delete {index:02d}" for index in range(12)]) is True
    assert save_count == 1
    assert cli._cli_cache["colors"] == {}


def test_named_shared_color_resolution_uses_recreated_discovery_id(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ColorBuilder, "generate_color_id", lambda self: "cReborn")
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: None,
    )

    assert cli.delete_color("Brand") is True
    assert cli.create_color("Brand", "rgba(44, 45, 46, 1)") is True
    assert cli.color_mapper.find_variable_by_name("Brand") == "var(--color_cBrand_default)"
    assert cli._resolve_color_arg("Brand") == "var(--color_cReborn_default)"
    assert cli._coerce_layout_value("%bc", "Brand") == "var(--color_cReborn_default)"
    assert cli._resolve_color_arg("Primary") == "var(--color_primary_default)"
    assert cli._resolve_color_arg("#123456") == "#123456"


@pytest.mark.parametrize(
    ("kind", "builder", "method_name", "arguments", "token_id"),
    [
        ("color", ColorBuilder, "create_color", ("Remote", "rgba(1, 2, 3, 1)"), "cRemote"),
        ("font", FontBuilder, "create_font", ("Remote", "Atkinson Hyperlegible"), "fRemote"),
    ],
)
def test_public_token_facades_stay_true_after_post_write_cache_failure(
    cli: BubbleCLI,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    builder: type[Any],
    method_name: str,
    arguments: tuple[str, str],
    token_id: str,
) -> None:
    generator_name = "generate_color_id" if kind == "color" else "generate_font_id"
    monkeypatch.setattr(builder, generator_name, lambda self: token_id)
    monkeypatch.setattr(
        bubble_cli_module.PayloadBuilder,
        "send_to_webhook",
        lambda self, url: None,
    )
    monkeypatch.setattr(
        cli,
        "put_style_token_cache",
        lambda cache_kind, cache_token_id, data: (_ for _ in ()).throw(
            RuntimeError(f"literal {kind} cache failure")
        ),
    )

    assert getattr(cli, method_name)(*arguments) is True
