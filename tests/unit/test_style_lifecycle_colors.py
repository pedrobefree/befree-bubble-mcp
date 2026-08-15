from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import ColorBuilder, PayloadBuilder
from bubble_mcp.aria_runtime.style_lifecycle.colors import ColorTokenService


@dataclass
class ColorHost:
    discovery: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=lambda: {"colors": {}})
    appname: str = "color-lifecycle-test"
    fail_dispatch: bool = False
    snapshot_calls: int = 0
    events: list[tuple[Any, ...]] = field(default_factory=list)

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self.snapshot_calls += 1
        return self.discovery, self.cache

    def new_style_token_payload(self) -> PayloadBuilder:
        return PayloadBuilder(appname=self.appname)

    def dispatch_style_token_payload(self, payload: PayloadBuilder) -> None:
        self.events.append(("dispatch", payload))
        if self.fail_dispatch:
            raise RuntimeError("literal color dispatch failure")

    def put_style_token_cache(self, kind: str, token_id: str, data: dict[str, Any]) -> None:
        self.events.append(("put", kind, token_id, dict(data)))
        self.cache.setdefault(kind, {})[token_id] = dict(data)

    def remove_style_token_cache(self, kind: str, token_id: str) -> None:
        self.events.append(("remove", kind, token_id))
        self.cache.setdefault(kind, {}).pop(token_id, None)

    def clear_style_token_cache(self, kind: str) -> None:
        self.events.append(("clear", kind))
        self.cache[kind] = {}


def _discovery() -> dict[str, Any]:
    return {
        "settings": {
            "client_safe": {
                "color_tokens": {
                    "primary": {"%d1": "rgba(1, 2, 3, 1)"},
                    "surface": {"default": "rgba(4, 5, 6, 1)"},
                    "raw": "rgba(7, 8, 9, 1)",
                },
                "color_tokens_user": {
                    "default": {
                        "cLive": {
                            "default": {
                                "name": "Brand",
                                "description": "Discovery wins",
                                "rgba": "rgba(10, 20, 30, 1)",
                                "order": 2,
                                "plugin_data": {"keep": True},
                            }
                        },
                        "cAccent": {
                            "%nm": "Accent",
                            "%d3": "Secondary",
                            "rgba": "rgba(40, 50, 60, 0.5)",
                            "order": 0,
                            "custom_field": "preserve-me",
                        },
                        "cGone": {
                            "%nm": "Retired",
                            "rgba": "rgba(70, 80, 90, 1)",
                            "order": 7,
                            "%del": True,
                            "tombstone": "keep-me",
                        },
                        "cOpaque": {
                            "plugin_owned": True,
                            "opaque_payload": {"keep": "exactly"},
                        },
                    }
                },
            }
        }
    }


def _host(*, fail_dispatch: bool = False) -> ColorHost:
    return ColorHost(
        discovery=_discovery(),
        cache={
            "colors": {
                "cLive": {
                    "%nm": "Stale brand",
                    "rgba": "rgba(255, 0, 0, 1)",
                    "order": 99,
                },
                "cCache": {
                    "%nm": "Cache only",
                    "rgba": "rgba(100, 110, 120, 1)",
                    "order": 4,
                },
                "invalid": {"rgba": "rgba(0, 0, 0, 1)"},
            }
        },
        fail_dispatch=fail_dispatch,
    )


def _setting_change(payload: PayloadBuilder) -> tuple[list[str], Any]:
    assert len(payload.changes) == 1
    change = payload.changes[0]
    assert change["intent"]["name"] == "ChangeAppSetting"
    return list(change["path_array"]), change["body"]


def test_snapshot_normalizes_wrappers_and_uses_discovery_before_valid_cache_only_entries() -> None:
    host = _host()
    service = ColorTokenService(host)

    snapshot = service.snapshot()

    assert snapshot.defaults == {
        "primary": "rgba(1, 2, 3, 1)",
        "surface": "rgba(4, 5, 6, 1)",
        "raw": "rgba(7, 8, 9, 1)",
    }
    assert snapshot.custom["cLive"] == {
        "%nm": "Brand",
        "%d3": "Discovery wins",
        "%del": False,
        "rgba": "rgba(10, 20, 30, 1)",
        "order": 2,
        "plugin_data": {"keep": True},
    }
    assert snapshot.custom["cCache"]["%nm"] == "Cache only"
    assert "invalid" not in snapshot.custom
    assert "cOpaque" not in snapshot.custom
    assert snapshot.wire_custom["cOpaque"] == {
        "plugin_owned": True,
        "opaque_payload": {"keep": "exactly"},
    }
    assert host.snapshot_calls == 1


def test_lookup_and_resolution_ignore_deleted_entries_and_emit_canonical_custom_variables() -> None:
    service = ColorTokenService(_host())

    assert service.find("PRIMARY") == ("default", "primary", "rgba(1, 2, 3, 1)")
    assert service.find("brand color")[0:2] == ("custom", "cLive")  # type: ignore[index]
    assert service.find("cCache")[0:2] == ("custom", "cCache")  # type: ignore[index]
    assert service.find("Retired") is None
    assert service.resolve("Brand") == "var(--color_cLive_default)"
    assert service.resolve("Primary") == "var(--color_primary_default)"
    assert service.resolve("white") == "#FFFFFF"
    assert service.resolve("#123456") == "#123456"
    assert service.resolve("rgba(1,2,3,0.5)") == "rgba(1,2,3,0.5)"
    assert service.resolve("unknown token") == "unknown token"


def test_resolution_preserves_custom_name_precedence_over_default_tokens() -> None:
    host = _host()
    host.discovery["settings"]["client_safe"]["color_tokens_user"]["default"]["cPrimary"] = {
        "%nm": "Primary",
        "rgba": "rgba(200, 100, 50, 1)",
        "order": 5,
    }
    service = ColorTokenService(host)

    assert service.resolve("Primary") == "var(--color_cPrimary_default)"
    assert service.find("Primary") == ("default", "primary", "rgba(1, 2, 3, 1)")


def test_default_update_is_targeted_and_dry_run_returns_complete_plan_without_side_effects() -> None:
    host = _host()
    result = ColorTokenService(host).update("Primary", "rgba(9, 8, 7, 1)", dry_run=True)

    assert result.ok is True
    assert result.token_id == "primary"
    assert result.payload is not None
    assert _setting_change(result.payload) == (
        ["settings", "client_safe", "color_tokens", "primary"],
        {"%d1": "rgba(9, 8, 7, 1)"},
    )
    assert host.snapshot_calls == 1
    assert host.events == []


def test_custom_update_sends_one_preserved_group_and_updates_cache_after_dispatch() -> None:
    host = _host()
    result = ColorTokenService(host).update("Accent", "rgba(1, 1, 1, 1)")

    assert result.ok is True
    assert result.payload is not None
    path, body = _setting_change(result.payload)
    assert path == ["settings", "client_safe", "color_tokens_user"]
    assert body["%d1"]["cAccent"] == {
        "%nm": "Accent",
        "%d3": "Secondary",
        "%del": False,
        "rgba": "rgba(1, 1, 1, 1)",
        "order": 0,
        "custom_field": "preserve-me",
    }
    assert body["%d1"]["cLive"]["plugin_data"] == {"keep": True}
    assert body["%d1"]["cGone"]["%del"] is True
    assert body["%d1"]["cCache"]["%nm"] == "Cache only"
    assert body["%d1"]["cOpaque"] == {
        "plugin_owned": True,
        "opaque_payload": {"keep": "exactly"},
    }
    assert [event[0] for event in host.events] == ["dispatch", "put"]
    assert host.events[1][1:3] == ("colors", "cAccent")
    assert host.snapshot_calls == 1


def test_create_returns_real_id_and_preserves_complete_map(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _host()
    monkeypatch.setattr(ColorBuilder, "generate_color_id", lambda self: "cActual")

    result = ColorTokenService(host).create(
        "New color",
        "rgba(12, 34, 56, 1)",
        description="Created",
    )

    assert result.ok is True
    assert result.token_id == "cActual"
    assert result.payload is not None
    _, body = _setting_change(result.payload)
    assert body["%d1"]["cActual"] == ColorBuilder.build_color_entry(
        "New color",
        "rgba(12, 34, 56, 1)",
        order=8,
        description="Created",
    )
    assert body["%d1"]["cGone"]["tombstone"] == "keep-me"
    assert body["%d1"]["cOpaque"]["opaque_payload"] == {"keep": "exactly"}
    assert [event[0] for event in host.events] == ["dispatch", "put"]


def test_deleted_color_name_does_not_block_recreation(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _host()
    monkeypatch.setattr(ColorBuilder, "generate_color_id", lambda self: "cReborn")

    result = ColorTokenService(host).create("Retired", "rgba(90, 80, 70, 1)", dry_run=True)

    assert result.ok is True
    assert result.token_id == "cReborn"
    assert result.payload is not None
    _, body = _setting_change(result.payload)
    assert body["%d1"]["cGone"]["%del"] is True
    assert body["%d1"]["cReborn"]["%nm"] == "Retired"
    assert host.events == []


def test_soft_and_hard_delete_preserve_wire_contract_and_mutate_cache_only_after_success() -> None:
    host = _host()
    service = ColorTokenService(host)

    deleted = service.delete("Cache only")
    assert deleted.ok is True
    assert deleted.payload is not None
    _, delete_body = _setting_change(deleted.payload)
    assert delete_body["%d1"]["cCache"]["%del"] is True
    assert delete_body["%d1"]["cOpaque"]["plugin_owned"] is True
    assert [event[0] for event in host.events] == ["dispatch", "remove"]
    assert "cCache" not in host.cache["colors"]

    host.events.clear()
    cleared = service.clear()
    assert cleared.ok is True
    assert cleared.payload is not None
    assert _setting_change(cleared.payload) == (
        ["settings", "client_safe", "color_tokens_user"],
        {"%d1": {}},
    )
    assert [event[0] for event in host.events] == ["dispatch", "clear"]
    assert host.cache["colors"] == {}


def test_bulk_delete_rejects_invalid_regex_without_dispatch_or_cache_changes() -> None:
    host = _host()
    before = dict(host.cache["colors"])

    result = ColorTokenService(host).delete_many(pattern="[")

    assert result.ok is False
    assert "unterminated character set" in (result.error or "")
    assert result.payload is None
    assert host.events == []
    assert host.cache["colors"] == before


def test_bulk_delete_deduplicates_targets_and_removes_cache_after_one_grouped_dispatch() -> None:
    host = _host()

    result = ColorTokenService(host).delete_many(
        names=["Accent", "Cache only"],
        pattern="accent|cache",
    )

    assert result.ok is True
    assert result.payload is not None
    _, body = _setting_change(result.payload)
    assert body["%d1"]["cAccent"]["%del"] is True
    assert body["%d1"]["cCache"]["%del"] is True
    assert body["%d1"]["cOpaque"]["opaque_payload"] == {"keep": "exactly"}
    assert [event[0] for event in host.events] == ["dispatch", "remove", "remove"]


@pytest.mark.parametrize(
    ("mode", "color_name", "target", "orders"),
    [
        ("sort-az", None, None, {"cAccent": 0, "cLive": 1, "cCache": 2}),
        ("sort-za", None, None, {"cCache": 0, "cLive": 1, "cAccent": 2}),
        ("move", "Brand", "0", {"cLive": 0, "cAccent": 1, "cCache": 2}),
        ("swap", "Accent", "Cache only", {"cAccent": 4, "cLive": 2, "cCache": 0}),
    ],
)
def test_reorder_preserves_tombstones(
    mode: str,
    color_name: str | None,
    target: str | None,
    orders: dict[str, int],
) -> None:
    host = _host()

    result = ColorTokenService(host).reorder(mode, color_name=color_name, target=target)

    assert result.ok is True
    assert result.payload is not None
    _, body = _setting_change(result.payload)
    assert {key: body["%d1"][key]["order"] for key in orders} == orders
    assert body["%d1"]["cGone"] == {
        "%nm": "Retired",
        "%d3": "",
        "%del": True,
        "rgba": "rgba(70, 80, 90, 1)",
        "order": 7,
        "tombstone": "keep-me",
    }
    assert body["%d1"]["cOpaque"] == {
        "plugin_owned": True,
        "opaque_payload": {"keep": "exactly"},
    }
    assert [event[0] for event in host.events] == ["dispatch", "put", "put", "put"]
    assert {
        (event[2], event[3]["order"])
        for event in host.events[1:]
    } == set(orders.items())


@pytest.mark.parametrize(
    ("mode", "color_name", "target"),
    [
        ("unknown", None, None),
        ("move", None, "0"),
        ("move", "Brand", "not-an-int"),
        ("swap", "Brand", "Missing"),
    ],
)
def test_reorder_validation_failures_do_not_dispatch(
    mode: str,
    color_name: str | None,
    target: str | None,
) -> None:
    host = _host()

    result = ColorTokenService(host).reorder(mode, color_name=color_name, target=target)

    assert result.ok is False
    assert result.payload is None
    assert host.events == []


def test_dispatch_failure_keeps_color_cache_unchanged() -> None:
    host = _host(fail_dispatch=True)
    before = {key: dict(value) for key, value in host.cache["colors"].items()}

    result = ColorTokenService(host).update("Cache only", "rgba(0, 0, 0, 1)")

    assert result.ok is False
    assert result.error == "literal color dispatch failure"
    assert [event[0] for event in host.events] == ["dispatch"]
    assert host.cache["colors"] == before


def test_empty_and_malformed_snapshots_fail_closed_without_writes() -> None:
    host = ColorHost(
        discovery={"settings": {"client_safe": {"color_tokens": "bad", "color_tokens_user": "bad"}}},
        cache={"colors": "bad"},
    )
    service = ColorTokenService(host)

    assert service.snapshot().defaults == {}
    assert service.snapshot().custom == {}
    assert service.active_custom() == {}
    assert service.next_order() == 0
    assert service.resolve("") == ""
    assert service.find("") is None
    assert service.update("Missing", "rgba(0,0,0,1)").ok is False
    assert service.delete("Missing").ok is False
    assert service.delete_many(names=["Missing"]).ok is False
    assert service.reorder("sort-az").ok is True
    assert host.events == []


def test_duplicate_and_default_delete_validation_do_not_build_payloads() -> None:
    host = _host()
    service = ColorTokenService(host)

    assert service.create("Brand", "rgba(0,0,0,1)").error == "Color 'Brand' already exists"
    assert service.delete("Primary").error == "Cannot delete default colors"
    assert service.delete_many(names=["Missing"]).error == "No matching colors found to delete"
    assert host.events == []


def test_default_execute_has_no_cache_delta_and_reorder_dry_run_has_no_side_effects() -> None:
    host = _host()
    service = ColorTokenService(host)

    updated = service.update("Primary", "rgba(8, 8, 8, 1)")
    assert updated.ok is True
    assert [event[0] for event in host.events] == ["dispatch"]

    host.events.clear()
    reordered = service.reorder("sort-az", dry_run=True)
    assert reordered.ok is True
    assert reordered.payload is not None
    assert host.events == []


def test_normalizers_skip_blank_invalid_entries_and_tolerate_non_numeric_order() -> None:
    host = ColorHost(
        discovery={
            "settings": {
                "client_safe": {
                    "color_tokens": {"": "ignored", "raw": "rgba(1,1,1,1)"},
                    "color_tokens_user": {
                        "%d1": {
                            "": {"%nm": "Blank", "rgba": "rgba(1,1,1,1)"},
                            "invalid": "not-a-map",
                            "bad-order": {
                                "%nm": "Bad order",
                                "rgba": "rgba(2,2,2,1)",
                                "order": "not-an-int",
                            },
                        }
                    },
                }
            }
        },
        cache={},
    )
    service = ColorTokenService(host)

    snapshot = service.snapshot()
    assert snapshot.defaults == {"raw": "rgba(1,1,1,1)"}
    assert set(snapshot.custom) == {"bad-order"}
    assert service.next_order() == 1


def test_reorder_dependency_failures_are_returned_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _host()
    service = ColorTokenService(host)
    monkeypatch.setattr(
        ColorBuilder,
        "swap_colors",
        lambda colors, first, second: (_ for _ in ()).throw(ValueError("literal swap failure")),
    )

    assert service.reorder("swap", "Primary", "Brand").ok is False
    result = service.reorder("swap", "Brand", "Accent")
    assert result.error == "literal swap failure"
    assert host.events == []
