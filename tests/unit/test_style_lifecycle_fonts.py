from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import FontBuilder, PayloadBuilder
from bubble_mcp.aria_runtime.style_lifecycle.fonts import FontTokenService


@dataclass
class FontHost:
    discovery: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=lambda: {"fonts": {}})
    appname: str = "font-lifecycle-test"
    fail_dispatch: bool = False
    fail_cache: bool = False
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
            raise RuntimeError("literal font dispatch failure")

    def put_style_token_cache(self, kind: str, token_id: str, data: dict[str, Any]) -> None:
        self.events.append(("put", kind, token_id, dict(data)))
        if self.fail_cache:
            raise RuntimeError("literal font cache failure")
        self.cache.setdefault(kind, {})[token_id] = dict(data)

    def remove_style_token_cache(self, kind: str, token_id: str) -> None:
        self.events.append(("remove", kind, token_id))
        self.cache.setdefault(kind, {}).pop(token_id, None)

    def clear_style_token_cache(self, kind: str) -> None:
        self.events.append(("clear", kind))
        self.cache[kind] = {}


def _host(*, fail_dispatch: bool = False, fail_cache: bool = False) -> FontHost:
    return FontHost(
        discovery={
            "settings": {
                "client_safe": {
                    "font_tokens": {"default": "Inter"},
                    "font_tokens_user": {
                        "%d1": {
                            "fBody": {
                                "default": {
                                    "name": "Body",
                                    "description": "Discovery wins",
                                    "font_family": "Source Sans 3",
                                    "order": 1,
                                    "metadata": {"keep": True},
                                }
                            },
                            "fDisplay": {
                                "%nm": "Display",
                                "%d3": "Headings",
                                "font_family": "Fraunces",
                                "order": 0,
                                "custom_field": "preserve-me",
                            },
                            "fGone": {
                                "%nm": "Retired",
                                "font_family": "Roboto",
                                "order": 8,
                                "%del": True,
                            },
                            "fOpaque": {
                                "plugin_owned": True,
                                "opaque_payload": {"keep": "exactly"},
                            },
                        }
                    },
                }
            }
        },
        cache={
            "fonts": {
                "fBody": {"%nm": "Stale body", "font_family": "Arial", "order": 99},
                "fCache": {"%nm": "Cache only", "font_family": "IBM Plex Sans", "order": 4},
                "invalid": {"%nm": "Missing family"},
            }
        },
        fail_dispatch=fail_dispatch,
        fail_cache=fail_cache,
    )


def _setting_change(payload: PayloadBuilder) -> tuple[list[str], Any]:
    assert len(payload.changes) == 1
    change = payload.changes[0]
    assert change["intent"]["name"] == "ChangeAppSetting"
    return list(change["path_array"]), change["body"]


def test_snapshot_normalizes_app_and_custom_wrappers_with_discovery_precedence() -> None:
    host = _host()

    snapshot = FontTokenService(host).snapshot()

    assert snapshot.app_font == "Inter"
    assert snapshot.custom["fBody"] == {
        "%nm": "Body",
        "%d3": "Discovery wins",
        "%del": False,
        "font_family": "Source Sans 3",
        "order": 1,
        "metadata": {"keep": True},
    }
    assert snapshot.custom["fCache"]["font_family"] == "IBM Plex Sans"
    assert "invalid" not in snapshot.custom
    assert "fOpaque" not in snapshot.custom
    assert snapshot.wire_custom["fOpaque"] == {
        "plugin_owned": True,
        "opaque_payload": {"keep": "exactly"},
    }
    assert host.snapshot_calls == 1


def test_opaque_discovery_font_id_blocks_same_id_valid_cache_supplement() -> None:
    host = _host()
    host.cache["fonts"]["fOpaque"] = {
        "%nm": "Stale cache shadow",
        "font_family": "Comic Sans MS",
        "order": 99,
    }

    snapshot = FontTokenService(host).snapshot()

    assert "fOpaque" not in snapshot.custom
    assert snapshot.wire_custom["fOpaque"] == {
        "plugin_owned": True,
        "opaque_payload": {"keep": "exactly"},
    }


@pytest.mark.parametrize("name", ["App Font", "APP_FONT", "default font", "DEFAULT"])
def test_app_font_lookup_is_case_insensitive(name: str) -> None:
    assert FontTokenService(_host()).find(name) == (
        "app",
        "app_font",
        {"font_family": "Inter"},
    )


def test_custom_lookup_accepts_case_insensitive_name_family_and_id_but_ignores_deleted() -> None:
    service = FontTokenService(_host())

    assert service.find("body")[0:2] == ("custom", "fBody")  # type: ignore[index]
    assert service.find("SOURCE SANS 3")[0:2] == ("custom", "fBody")  # type: ignore[index]
    assert service.find("FCACHE")[0:2] == ("custom", "fCache")  # type: ignore[index]
    assert service.find("Retired") is None
    assert service.find("Roboto") is None


def test_app_font_update_is_targeted_and_dry_run_has_no_side_effects() -> None:
    host = _host()

    result = FontTokenService(host).update("App Font", "DM Sans", dry_run=True)

    assert result.ok is True
    assert result.token_id == "app_font"
    assert result.payload is not None
    assert _setting_change(result.payload) == (
        ["settings", "client_safe", "font_tokens"],
        {"%d1": "DM Sans"},
    )
    assert host.snapshot_calls == 1
    assert host.events == []


def test_custom_update_preserves_group_and_updates_cache_after_dispatch() -> None:
    host = _host()

    result = FontTokenService(host).update("Display", "Literata")

    assert result.ok is True
    assert result.payload is not None
    path, body = _setting_change(result.payload)
    assert path == ["settings", "client_safe", "font_tokens_user"]
    assert body["%d1"]["fDisplay"] == {
        "%nm": "Display",
        "%d3": "Headings",
        "%del": False,
        "font_family": "Literata",
        "order": 0,
        "custom_field": "preserve-me",
    }
    assert body["%d1"]["fBody"]["metadata"] == {"keep": True}
    assert body["%d1"]["fGone"]["%del"] is True
    assert body["%d1"]["fOpaque"] == {
        "plugin_owned": True,
        "opaque_payload": {"keep": "exactly"},
    }
    assert [event[0] for event in host.events] == ["dispatch", "put"]
    assert host.events[1][1:3] == ("fonts", "fDisplay")


def test_create_returns_real_id_and_uses_font_builder_wire_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _host()
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: "fActual")

    result = FontTokenService(host).create("Mono", "DM Mono", description="Code")

    assert result.ok is True
    assert result.token_id == "fActual"
    assert result.payload is not None
    _, body = _setting_change(result.payload)
    assert body["%d1"]["fActual"] == FontBuilder.build_font_entry(
        "Mono",
        "DM Mono",
        order=9,
        description="Code",
    )
    assert body["%d1"]["fOpaque"]["opaque_payload"] == {"keep": "exactly"}
    assert [event[0] for event in host.events] == ["dispatch", "put"]


def test_successful_font_write_preserves_result_when_cache_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _host(fail_cache=True)
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: "fRemote")

    result = FontTokenService(host).create("Remote", "Atkinson Hyperlegible")

    assert result.ok is True
    assert result.token_id == "fRemote"
    assert result.error == "Post-write token cache update failed: literal font cache failure"
    assert [event[0] for event in host.events] == ["dispatch", "put"]


def test_deleted_font_name_and_family_do_not_block_recreation(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _host()
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: "fReborn")

    by_name = FontTokenService(host).create("Retired", "Roboto Slab", dry_run=True)
    by_family = FontTokenService(host).create("New body", "Roboto", dry_run=True)

    assert by_name.ok is True
    assert by_name.token_id == "fReborn"
    assert by_family.ok is True
    assert by_family.token_id == "fReborn"
    assert host.events == []


def test_delete_protects_app_font_and_soft_deletes_custom_with_cache_coherence() -> None:
    host = _host()
    service = FontTokenService(host)

    protected = service.delete("App Font")
    assert protected.ok is False
    assert protected.error == "Cannot delete the App Font"
    assert host.events == []

    deleted = service.delete("Cache only")
    assert deleted.ok is True
    assert deleted.payload is not None
    _, body = _setting_change(deleted.payload)
    assert body["%d1"]["fCache"]["%del"] is True
    assert body["%d1"]["fOpaque"]["plugin_owned"] is True
    assert [event[0] for event in host.events] == ["dispatch", "remove"]
    assert "fCache" not in host.cache["fonts"]


def test_create_dry_run_returns_complete_plan_without_dispatch_or_cache_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _host()
    before = {key: dict(value) for key, value in host.cache["fonts"].items()}
    monkeypatch.setattr(FontBuilder, "generate_font_id", lambda self: "fPreview")

    result = FontTokenService(host).create("Preview", "Inter Tight", dry_run=True)

    assert result.ok is True
    assert result.token_id == "fPreview"
    assert result.payload is not None
    _, body = _setting_change(result.payload)
    assert body["%d1"]["fPreview"]["font_family"] == "Inter Tight"
    assert host.events == []
    assert host.cache["fonts"] == before


def test_dispatch_failure_keeps_font_cache_unchanged() -> None:
    host = _host(fail_dispatch=True)
    before = {key: dict(value) for key, value in host.cache["fonts"].items()}

    result = FontTokenService(host).update("Cache only", "Noto Sans")

    assert result.ok is False
    assert result.error == "literal font dispatch failure"
    assert [event[0] for event in host.events] == ["dispatch"]
    assert host.cache["fonts"] == before


def test_missing_and_duplicate_fonts_fail_without_building_or_dispatching() -> None:
    host = _host()
    service = FontTokenService(host)

    assert service.update("Missing", "Inter").ok is False
    assert service.delete("Missing").ok is False
    assert service.create("BODY", "Another family").ok is False
    assert service.create("Another name", "source sans 3").ok is False
    assert host.events == []


def test_empty_and_malformed_font_snapshots_fail_closed() -> None:
    host = FontHost(
        discovery={"settings": {"client_safe": {"font_tokens": "Arial", "font_tokens_user": "bad"}}},
        cache={"fonts": "bad"},
    )
    service = FontTokenService(host)

    snapshot = service.snapshot()
    assert snapshot.app_font == "Arial"
    assert snapshot.custom == {}
    assert service.find("") is None
    assert service.next_order() == 0
    assert host.events == []


def test_app_font_execute_has_no_cache_delta() -> None:
    host = _host()

    result = FontTokenService(host).update("App Font", "DM Sans")

    assert result.ok is True
    assert [event[0] for event in host.events] == ["dispatch"]


def test_font_normalizers_skip_invalid_entries_and_tolerate_non_numeric_order() -> None:
    host = FontHost(
        discovery={
            "settings": {
                "client_safe": {
                    "font_tokens": {},
                    "font_tokens_user": {
                        "default": {
                            "": {"%nm": "Blank", "font_family": "Inter"},
                            "invalid": "not-a-map",
                            "bad-order": {
                                "%nm": "Bad order",
                                "font_family": "Literata",
                                "order": "not-an-int",
                            },
                        }
                    },
                }
            }
        },
        cache={},
    )
    service = FontTokenService(host)

    snapshot = service.snapshot()
    assert snapshot.app_font == "not set"
    assert set(snapshot.custom) == {"bad-order"}
    assert service.next_order() == 1
