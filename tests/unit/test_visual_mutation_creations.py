from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.visual_mutations.service import VisualMutationService


class _CreationDiscovery:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.parent_by_id: dict[str, Any] | None = None
        self.parent_by_name: dict[str, Any] | None = None
        self.injected: list[tuple[Any, ...]] = []
        self.inject_error = False
        self.root_error = False
        self.root: dict[str, Any] = {
            "id": "pg",
            "elements": {"existing": {"id": "existing-id"}},
        }

    def find_element_by_id(
        self, context_id: str, parent_ref: str, *, context_type: str
    ) -> dict[str, Any] | None:
        del context_id, parent_ref, context_type
        return self.parent_by_id

    def find_element_by_name(
        self,
        context_id: str,
        parent_ref: str,
        *,
        context_type: str,
        prefer_last: bool = False,
    ) -> dict[str, Any] | None:
        del context_id, parent_ref, context_type, prefer_last
        return self.parent_by_name

    def _get_context_root(self, context_id: str, context_type: str) -> dict[str, Any]:
        del context_id, context_type
        if self.root_error:
            raise RuntimeError("root unavailable")
        return self.root

    @staticmethod
    def build_path_array(
        context_id: str,
        path: list[str],
        *,
        context_type: str,
    ) -> list[str]:
        prefix = "%ed" if context_type == "reusable" else "%p3"
        return [prefix, context_id, *path]

    def inject_element(
        self,
        context_id: str,
        context_type: str,
        parent_id: str | None,
        body: dict[str, Any],
        *,
        element_key: str,
    ) -> None:
        if self.inject_error:
            raise RuntimeError("inject failed")
        self.injected.append((context_id, context_type, parent_id, body, element_key))


class _CreationHost:
    appname = "visual-create-test"

    def __init__(self) -> None:
        self.discovery = _CreationDiscovery()
        self.ref_parent: dict[str, Any] | None = None
        self.cached_parent: dict[str, Any] | None = None
        self.cache_after_sync: dict[str, Any] | None = None
        self.sync_result = False
        self.synced = False
        self.sent: list[PayloadBuilder] = []
        self.dispatch_error = False
        self.cached_aliases: list[dict[str, Any]] = []

    def _find_context(self, name: str) -> tuple[str | None, str | None]:
        return ("pg", "page") if name == "Home" else (None, None)

    def _find_element_by_ref(
        self,
        context_id: str,
        context_type: str,
        element_ref: str,
        *,
        ref_kind: str,
        match_index: int,
    ) -> dict[str, Any] | None:
        del context_id, context_type, element_ref, ref_kind, match_index
        return self.ref_parent

    def _resolve_cached_element_alias(
        self, context_id: str, context_type: str, element_ref: str
    ) -> dict[str, Any] | None:
        del context_id, context_type, element_ref
        return self.cache_after_sync if self.synced else self.cached_parent

    def _auto_sync_element_ref_aliases(self) -> bool:
        self.synced = True
        return self.sync_result

    def _normalize_payload_path(self, path: Any) -> list[str]:
        aliases = {"pages": "%p3", "element_definitions": "%ed", "elements": "%el"}
        return [aliases.get(str(value), str(value)) for value in path] if isinstance(path, list) else []

    @staticmethod
    def _canonicalize_context_prefix_on_path(
        path: list[str], context_id: str, context_type: str
    ) -> list[str]:
        prefix = "%ed" if context_type == "reusable" else "%p3"
        return [prefix, context_id, *path[2:]]

    @staticmethod
    def _find_last_element_token(path: list[str]) -> tuple[int | None, str | None]:
        indices = [index for index, token in enumerate(path[:-1]) if token == "%el"]
        if not indices:
            return None, None
        index = indices[-1]
        return index + 1, str(path[index + 1])

    @staticmethod
    def _style_override_keys_for_element_type(
        element_type: str | None, *, target_style_id: str | None = None
    ) -> list[str]:
        del element_type, target_style_id
        return ["%fc", "font_family"]

    def _dispatch_payload(self, payload: PayloadBuilder) -> None:
        if self.dispatch_error:
            raise RuntimeError("dispatch failed")
        self.sent.append(payload)

    def _cache_created_element_aliases(self, **kwargs: Any) -> None:
        self.cached_aliases.append(kwargs)


def _change_rows(payload: PayloadBuilder) -> list[tuple[str, list[str], Any]]:
    return [
        (
            str(change.get("intent", {}).get("name")),
            list(change.get("path_array") or []),
            change.get("body"),
        )
        for change in payload.changes
    ]


def test_prepare_resolves_context_and_root_parent() -> None:
    service = VisualMutationService(_CreationHost()).creations
    target = service.prepare("Home", None)
    assert target is not None
    assert target.context_id == "pg"
    assert target.context_type == "page"
    assert target.parent_result == {"path": [], "id": "pg"}
    assert target.parent_path == ["%p3", "pg"]
    assert service.prepare("Missing", None) is None


def test_prepare_resolves_named_parent_and_rejects_missing_parent() -> None:
    host = _CreationHost()
    host.discovery.parent_by_name = {"id": "parent-id", "path": ["%el", "parent-key"]}
    service = VisualMutationService(host).creations

    target = service.prepare("Home", "Parent Card")

    assert target is not None
    assert target.parent_result["id"] == "parent-id"
    assert target.parent_path == ["%p3", "pg", "%el", "parent-key"]
    host.discovery.parent_by_name = None
    assert service.prepare("Home", "Missing Parent") is None


@pytest.mark.parametrize("channel", ["id", "name", "reference", "cache", "sync"])
def test_resolve_parent_preserves_fallback_order(channel: str) -> None:
    host = _CreationHost()
    parent = {"id": "parent-id", "path": ["%el", "parent"]}
    if channel == "id":
        host.discovery.parent_by_id = parent
    elif channel == "name":
        host.discovery.parent_by_name = parent
    elif channel == "reference":
        host.ref_parent = parent
    elif channel == "cache":
        host.cached_parent = parent
    else:
        host.sync_result = True
        host.cache_after_sync = parent

    parent_ref = "parent-id" if channel == "id" else "Parent Card"
    resolved = VisualMutationService(host).creations.resolve_parent(
        "pg", "page", "Home", parent_ref
    )
    assert resolved == parent


def test_resolve_parent_handles_root_empty_and_exhausted_fallbacks() -> None:
    service = VisualMutationService(_CreationHost()).creations

    assert service.resolve_parent("pg", "page", "Home", "root") == {"path": [], "id": "pg"}
    assert service.resolve_parent("pg", "page", "Home", "Home") == {"path": [], "id": "pg"}
    assert service.resolve_parent("pg", "page", "Home", "") is None
    assert service.resolve_parent("pg", "page", "Home", "Unknown Parent") is None


def test_existing_child_ids_handles_raw_aliases_and_malformed_nodes() -> None:
    host = _CreationHost()
    service = VisualMutationService(host).creations
    parent = {
        "id": "parent-id",
        "element": {
            "%el": {
                "length": 4,
                "one": {"id": "child-1"},
                "two": "invalid",
                "three": {"id": ""},
            }
        },
    }

    assert service.existing_child_ids("pg", "page", parent) == ["child-1"]
    assert service.existing_child_ids("pg", "page", {"id": "parent-id"}) == []
    assert service.existing_child_ids("pg", "page", {"id": "pg", "element": []}) == [
        "existing-id"
    ]
    host.discovery.root = {"elements": []}
    assert service.existing_child_ids("pg", "page", {"id": "pg"}) == []
    host.discovery.root_error = True
    assert service.existing_child_ids("pg", "page", {"id": "pg"}) == []


def test_queue_create_emits_literal_editor_order_and_parent_children() -> None:
    host = _CreationHost()
    service = VisualMutationService(host).creations
    payload = PayloadBuilder(appname=host.appname)
    path = ["pages", "pg", "elements", "slot-key"]
    body = {
        "id": "object-id",
        "%x": "Text",
        "%s1": "Text_body_",
        "%p": {"%3": "Hello", "%fc": "#000000", "font_family": None, "margin_top": 8},
    }

    service.queue_create(
        payload,
        "pg",
        "page",
        {"id": "pg", "path": []},
        path,
        body,
        "ignored.legacy.path",
        text_content="Hello",
    )

    rows = _change_rows(payload)
    assert [row[0] for row in rows[:4]] == [
        "Update index",
        "CreateElement",
        "Update index",
        "Update index",
    ]
    assert rows[0][1] == ["_index", "id_to_path", "object-id"]
    assert rows[0][2] == "%p3.pg.%el.slot-key"
    assert rows[1][1] == ["%p3", "pg", "%el", "slot-key"]
    assert rows[2][1] == ["_index", "issues_list", "object-id"]
    assert rows[3][1] == ["_index", "issues_sub", "pg"]
    assert body["%p"] == {"%3": "Hello", "margin_top": 8}
    assert path == ["%p3", "pg", "%el", "slot-key"]


def test_queue_create_covers_style_layout_and_pending_parent_state() -> None:
    host = _CreationHost()
    service = VisualMutationService(host).creations
    payload = PayloadBuilder(appname=host.appname)
    path = ["pages", "pg", "elements", "object-id"]
    body = {
        "id": "object-id",
        "%x": "DateInput",
        "%s1": "DateInput_standard_",
        "%p": {
            "%c1": "Current date/time",
            "%fc": "#000000",
            "nonant_alignment": "top-left",
            "margin_left": 0,
            "margin_right": 12,
        },
    }
    pending = {"parent-id": ["older-child"]}

    service.queue_create(
        payload,
        "pg",
        "page",
        {"id": "parent-id", "path": ["%el", "parent"]},
        path,
        body,
        "ignored",
        pending_child_ids_by_parent=pending,
    )

    assert path[-1] != "object-id"
    assert body["%p"]["%c1"] == "Current date/time"
    assert "%fc" not in body["%p"]
    assert pending == {"parent-id": ["older-child", "object-id"]}
    rows = _change_rows(payload)
    assert any(row[1][-2:] == ["%p", "nonant_alignment"] for row in rows)
    assert any(row[1][-2:] == ["%p", "align_to_parent_pos"] for row in rows)
    assert any(row[1][-2:] == ["%p", "margin_right"] for row in rows)
    assert not any(row[1][-2:] == ["%p", "margin_left"] for row in rows)


def test_queue_create_rejects_invalid_identity_and_path() -> None:
    service = VisualMutationService(_CreationHost()).creations
    payload = PayloadBuilder(appname="visual-create-test")

    with pytest.raises(ValueError, match="valid 'id'"):
        service.queue_create(payload, "pg", "page", {}, ["%p3", "pg"], {}, "ignored")
    with pytest.raises(ValueError, match="valid slot key"):
        service.queue_create(
            payload,
            "pg",
            "page",
            {},
            ["%p3", "pg"],
            {"id": "object-id"},
            "ignored",
        )


def test_queue_create_without_parent_or_optional_properties() -> None:
    service = VisualMutationService(_CreationHost()).creations
    payload = PayloadBuilder(appname="visual-create-test")
    path = ["%p3", "pg", "%el", "slot"]

    service.queue_create(
        payload,
        "pg",
        "page",
        {},
        path,
        {"id": "object-id"},
        "ignored",
    )

    assert [row[0] for row in _change_rows(payload)] == [
        "Update index",
        "CreateElement",
        "Update index",
    ]


def test_finish_preview_injects_without_dispatch_or_alias_cache() -> None:
    host = _CreationHost()
    service = VisualMutationService(host).creations
    payload = PayloadBuilder(appname=host.appname)
    body = {"id": "object-id", "%dn": "Hero"}

    assert (
        service.finish(
            payload,
            context_id="pg",
            context_type="page",
            parent_result={"id": "pg", "path": []},
            body=body,
            element_key="hero",
            aliases=["Hero"],
            result_value="object-id",
            success_message="created hero",
            dry_run=True,
        )
        == "object-id"
    )
    assert host.sent == []
    assert host.discovery.injected == [("pg", "page", "pg", body, "hero")]
    assert host.cached_aliases == []


def test_finish_dispatches_before_injection_and_alias_cache() -> None:
    host = _CreationHost()
    service = VisualMutationService(host).creations
    payload = PayloadBuilder(appname=host.appname)
    body = {"id": "object-id", "%dn": "Hero"}

    assert service.finish(
        payload,
        context_id="pg",
        context_type="page",
        parent_result={"id": "parent-id", "path": ["%el", "parent"]},
        body=body,
        element_key="hero",
        aliases=["Hero", "", "Hero"],
        result_value="hero",
        success_message="created hero",
        dry_run=False,
    ) == "hero"
    assert host.sent == [payload]
    assert host.discovery.injected[-1][:3] == ("pg", "page", "parent-id")
    assert host.cached_aliases == [
        {
            "context_id": "pg",
            "context_type": "page",
            "aliases": ["Hero"],
            "element_id": "object-id",
            "element_key": "hero",
            "parent_path": ["%el", "parent"],
        }
    ]


def test_finish_failure_has_no_injection_or_alias_side_effect() -> None:
    host = _CreationHost()
    host.dispatch_error = True
    service = VisualMutationService(host).creations

    assert not service.finish(
        PayloadBuilder(appname=host.appname),
        context_id="pg",
        context_type="page",
        parent_result={"id": "pg", "path": []},
        body={"id": "object-id"},
        element_key="hero",
        aliases=["Hero"],
        result_value="hero",
        success_message="created hero",
        dry_run=False,
    )
    assert host.discovery.injected == []
    assert host.cached_aliases == []


def test_finish_tolerates_injection_errors_and_supports_parent_override() -> None:
    host = _CreationHost()
    host.discovery.inject_error = True
    service = VisualMutationService(host).creations
    kwargs = {
        "context_id": "pg",
        "context_type": "page",
        "parent_result": {"id": "parent-id", "path": []},
        "body": {"id": "object-id"},
        "element_key": "hero",
        "aliases": ["Hero"],
        "result_value": "hero",
        "success_message": "created hero",
        "tolerate_injection_error": True,
        "parent_id": "override-parent",
    }

    assert service.finish(PayloadBuilder(appname=host.appname), dry_run=True, **kwargs) == "hero"
    assert service.finish(PayloadBuilder(appname=host.appname), dry_run=False, **kwargs) == "hero"
    assert len(host.sent) == 1
    assert len(host.cached_aliases) == 1


def test_finish_strict_injection_error_and_print_failure(capsys: pytest.CaptureFixture[str]) -> None:
    host = _CreationHost()
    host.discovery.inject_error = True
    service = VisualMutationService(host).creations
    kwargs = {
        "context_id": "pg",
        "context_type": "page",
        "parent_result": {"id": "parent-id", "path": []},
        "body": {"id": ""},
        "element_key": "hero",
        "aliases": [],
        "result_value": "hero",
        "success_message": "created hero",
        "cache_aliases": False,
        "use_parent_result_id": False,
    }

    with pytest.raises(RuntimeError, match="inject failed"):
        service.finish(PayloadBuilder(appname=host.appname), dry_run=True, **kwargs)
    assert service.finish(PayloadBuilder(appname=host.appname), dry_run=False, **kwargs) is False

    host.discovery.inject_error = False
    host.dispatch_error = True
    assert service.finish(
        PayloadBuilder(appname=host.appname),
        dry_run=False,
        error_via_print=True,
        **kwargs,
    ) is False
    assert "Failed to send: dispatch failed" in capsys.readouterr().out


def test_bubble_cli_creation_helpers_are_compatibility_facades() -> None:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    class _CreationSpy:
        def resolve_parent(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append(("resolve_parent", args, kwargs))
            return {"id": "parent-id", "path": []}

        def existing_child_ids(self, *args: Any, **kwargs: Any) -> list[str]:
            calls.append(("existing_child_ids", args, kwargs))
            return ["child-id"]

        def queue_create(self, *args: Any, **kwargs: Any) -> None:
            calls.append(("queue_create", args, kwargs))

    cli = object.__new__(BubbleCLI)
    cli._visual_mutations = SimpleNamespace(creations=_CreationSpy())
    parent = {"id": "parent-id", "path": []}
    payload = PayloadBuilder(appname="facade-test")
    path = ["%p3", "pg", "%el", "hero"]
    body = {"id": "hero-id", "%p": {}}

    assert cli._resolve_parent_element("pg", "page", "Home", "Parent") == parent
    assert cli._existing_child_ids_for_parent("pg", "page", parent) == ["child-id"]
    assert (
        cli._queue_create_element_with_index_updates(
            payload,
            "pg",
            "page",
            parent,
            path,
            body,
            "%p3.pg.%el.hero",
            name_value="Hero",
            text_content="Hello",
            pending_child_ids_by_parent={"parent-id": []},
        )
        is None
    )
    assert [row[0] for row in calls] == [
        "resolve_parent",
        "existing_child_ids",
        "queue_create",
    ]
