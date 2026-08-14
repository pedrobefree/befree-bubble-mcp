from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.visual_mutations import VisualMutationService


class _Discovery:
    def __init__(self, result: dict[str, Any] | None, data: dict[str, Any]) -> None:
        self.result = result
        self.data = data
        self.list_results: list[Any] | None = None
        self.list_error = False

    def find_element_by_name(
        self,
        context_id: str,
        element_name: str,
        *,
        context_type: str,
        prefer_last: bool,
    ) -> dict[str, Any] | None:
        del context_id, element_name, context_type, prefer_last
        return self.result

    def list_elements(self, context_id: str, *, context_type: str) -> list[dict[str, Any]]:
        del context_id, context_type
        if self.list_error:
            raise RuntimeError("list failed")
        if self.list_results is not None:
            return self.list_results  # type: ignore[return-value]
        return [self.result] if isinstance(self.result, dict) else []

    def build_path_array(
        self,
        context_id: str,
        path: list[str],
        *,
        context_type: str,
    ) -> list[str]:
        prefix = "%ed" if context_type == "reusable" else "%p3"
        return [prefix, context_id, *path]

    def _get_context_root(self, context_id: str, context_type: str) -> dict[str, Any] | None:
        key = "element_definitions" if context_type == "reusable" else "pages"
        bucket = self.data.get(key)
        return bucket.get(context_id) if isinstance(bucket, dict) else None


class _Host:
    appname = "visual-delete-test"

    def __init__(
        self,
        *,
        element_type: str | None = "Text",
        include_index_path: bool = True,
        dispatch_error: bool = False,
    ) -> None:
        element = {"id": "hero-id", "%dn": "Hero", "%p": {"%3": "Welcome"}}
        if element_type is not None:
            element["%x"] = element_type
        result = {
            "id": "hero-id",
            "key": "hero",
            "name": "Hero",
            "path": ["%el", "hero"],
            "element": element,
        }
        id_to_path = {"hero-id": "%p3.pg.%el.hero"} if include_index_path else {}
        self.discovery = _Discovery(
            result,
            {
                "pages": {
                    "pg": {
                        "id": "root-id",
                        "elements": {"hero": element},
                    }
                },
                "_index": {
                    "id_to_path": id_to_path,
                    "issues_sub": {
                        "root-id": json.dumps(["hero-id", "sibling-id"]),
                        "other-parent": ["hero-id"],
                    },
                },
            },
        )
        self.dispatch_error = dispatch_error
        self.sent_payloads: list[Any] = []
        self.removed_aliases: list[dict[str, Any]] = []
        self.context_found = True
        self.button_result: dict[str, Any] | None = None
        self.ref_result: dict[str, Any] | None = None
        self.cache_result: dict[str, Any] | None = None
        self.path_values: dict[tuple[str, ...], Any] = {}

    def _find_context(self, name: str) -> tuple[str | None, str | None]:
        return ("pg", "page") if self.context_found and name == "Home" else (None, None)

    def _find_button_by_label(
        self, context_id: str, context_type: str, label: str
    ) -> dict[str, Any] | None:
        del context_id, context_type, label
        return self.button_result

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
        return self.ref_result

    def _resolve_cached_element_alias(
        self, context_id: str, context_type: str, element_ref: str
    ) -> dict[str, Any] | None:
        del context_id, context_type, element_ref
        return self.cache_result

    def _get_value_at_path(self, path: list[str]) -> Any:
        path_key = tuple(path)
        if path_key in self.path_values:
            return self.path_values[path_key]
        if path == ["%p3", "pg"]:
            return self.discovery.data["pages"]["pg"]
        if path == ["%p3", "pg", "%el", "hero"]:
            return self.discovery.result["element"] if self.discovery.result else None
        return None

    @staticmethod
    def _normalize_payload_path(path: Any) -> list[str]:
        return [str(token) for token in path] if isinstance(path, list) else []

    @staticmethod
    def _parse_path_array(path: Any) -> list[str]:
        if isinstance(path, list):
            return [str(token) for token in path]
        return [token for token in str(path or "").split(".") if token]

    def _normalize_capture_path(self, path: Any) -> list[str]:
        return self._parse_path_array(path)

    @staticmethod
    def _workflow_prefix(context_type: str) -> str:
        return "%ed" if context_type == "reusable" else "%p3"

    @staticmethod
    def _resolve_context_write_root_token(context_id: str, context_type: str) -> str:
        del context_type
        return context_id

    @staticmethod
    def _canonicalize_context_prefix_on_path(
        path: list[str], context_id: str, context_type: str
    ) -> list[str]:
        prefix = "%ed" if context_type == "reusable" else "%p3"
        return [prefix, context_id, *path[2:]] if len(path) >= 2 else [prefix, context_id]

    def _dispatch_payload(self, payload: Any) -> None:
        if self.dispatch_error:
            raise RuntimeError("dispatch failed")
        self.sent_payloads.append(payload)

    def _remove_cached_element_aliases(self, **kwargs: Any) -> None:
        self.removed_aliases.append(kwargs)


def _changes_without_random_ids(payload: Any) -> list[dict[str, Any]]:
    return [
        {
            "intent": change.get("intent", {}).get("name"),
            "path": change.get("path_array"),
            "body": change.get("body"),
        }
        for change in payload.changes
    ]


def test_delete_nested_element_uses_canonical_path_and_updates_all_parents() -> None:
    host = _Host()
    service = VisualMutationService(host)

    assert service.deletions.delete(
        "Home",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
    )

    assert len(host.sent_payloads) == 1
    assert _changes_without_random_ids(host.sent_payloads[0]) == [
        {
            "intent": "Update index",
            "path": ["_index", "id_to_path", "hero-id"],
            "body": None,
        },
        {
            "intent": "RemoveElement",
            "path": ["%p3", "pg", "%el", "hero"],
            "body": None,
        },
        {
            "intent": "Update index",
            "path": ["_index", "issues_sub", "root-id"],
            "body": json.dumps(["sibling-id"]),
        },
        {
            "intent": "Update index",
            "path": ["_index", "issues_sub", "other-parent"],
            "body": json.dumps([]),
        },
    ]
    assert host.removed_aliases == [
        {
            "context_id": "pg",
            "context_type": "page",
            "element_id": "hero-id",
            "element_path": ["%el", "hero"],
        }
    ]


def test_delete_preview_builds_payload_without_dispatch_or_alias_cleanup() -> None:
    host = _Host()
    service = VisualMutationService(host)

    assert service.deletions.delete(
        "Home",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
        dry_run=True,
    )
    assert host.sent_payloads == []
    assert host.removed_aliases == []


def test_delete_dispatch_failure_keeps_aliases() -> None:
    host = _Host(dispatch_error=True)
    service = VisualMutationService(host)

    assert not service.deletions.delete(
        "Home",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
    )
    assert host.sent_payloads == []
    assert host.removed_aliases == []


@pytest.mark.parametrize(
    ("element_type", "allowed", "expected"),
    [
        ("Button", frozenset({"text"}), False),
        (None, frozenset({"text"}), True),
        ("Custom_Type", frozenset({"group", "custom_type"}), True),
    ],
)
def test_delete_preserves_type_validation_contract(
    element_type: str | None,
    allowed: frozenset[str],
    expected: bool,
) -> None:
    host = _Host(element_type=element_type)
    service = VisualMutationService(host)

    assert (
        service.deletions.delete(
            "Home",
            "Hero",
            allowed_types=allowed,
            expected_label="expected type",
            success_label="element",
            dry_run=True,
        )
        is expected
    )


def test_delete_falls_back_to_discovery_path_when_index_path_is_missing() -> None:
    host = _Host(include_index_path=False)
    service = VisualMutationService(host)

    assert service.deletions.delete(
        "Home",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
    )
    remove = _changes_without_random_ids(host.sent_payloads[0])[1]
    assert remove["path"] == ["%p3", "pg", "%el", "hero"]


def test_targets_resolve_button_reference_cache_and_missing_context_paths() -> None:
    result = _Host().discovery.result
    assert isinstance(result, dict)

    button_host = _Host()
    button_host.discovery.result = None
    button_host.button_result = result
    button_target = VisualMutationService(button_host).targets.resolve_existing(
        "Home", "Button Save"
    )
    assert button_target is not None and button_target.element_id == "hero-id"

    ref_host = _Host()
    ref_host.discovery.result = None
    ref_host.ref_result = result
    ref_target = VisualMutationService(ref_host).targets.resolve_existing("Home", "hero-id")
    assert ref_target is not None and ref_target.element_type == "text"

    cache_host = _Host()
    cache_host.discovery.result = None
    cache_host.cache_result = result
    cache_target = VisualMutationService(cache_host).targets.resolve_existing_tuple("Home", "Hero")
    assert cache_target is not None and cache_target[:2] == ("pg", "page")

    missing_host = _Host()
    missing_host.context_found = False
    assert VisualMutationService(missing_host).targets.resolve_existing("Missing", "Hero") is None

    missing_element_host = _Host()
    missing_element_host.discovery.result = None
    assert (
        VisualMutationService(missing_element_host).targets.resolve_existing_tuple("Home", "Missing")
        is None
    )


def test_targets_hydrate_path_and_secondary_list_rows() -> None:
    path_host = _Host()
    assert isinstance(path_host.discovery.result, dict)
    path_host.discovery.result = {
        "key": "hero",
        "path": ["%el", "hero"],
        "element": {},
    }
    path_host.path_values[("%p3", "pg", "%el", "hero")] = {
        "id": "hydrated-id",
        "%x": "Image",
        "%p": {"src": "hero.png"},
    }
    target = VisualMutationService(path_host).targets.resolve_existing("Home", "Hero")
    assert target is not None
    assert target.element_id == "hydrated-id"
    assert target.element_type == "image"

    list_host = _Host()
    list_host.discovery.result = {
        "id": "hero-id",
        "path": ["%el", "hero"],
        "element": {"id": "hero-id"},
    }
    list_host.path_values[("%p3", "pg", "%el", "hero")] = None
    list_host.discovery.list_results = [
        None,
        {"id": "ignored", "element": None},
        {
            "id": "hero-id",
            "path": ["%el", "hero"],
            "element": {"id": "hero-id", "%x": "Shape", "properties": {}},
        },
    ]
    target = VisualMutationService(list_host).targets.resolve_existing("Home", "Hero")
    assert target is not None and target.element_type == "shape"


def test_targets_recover_id_from_path_and_reject_unidentified_result() -> None:
    path_id_host = _Host()
    path_id_host.discovery.result = {
        "path": ["%el", "hero"],
        "element": {"%x": "Text", "%p": {}},
    }
    path_id_host.discovery.data["_index"]["id_to_path"] = {}
    target = VisualMutationService(path_id_host).targets.resolve_existing("Home", "Hero")
    assert target is not None and target.element_id == "hero"

    missing_id_host = _Host()
    missing_id_host.discovery.result = {"path": [], "element": {"%x": "Text", "%p": {}}}
    missing_id_host.discovery.data["_index"]["id_to_path"] = {}
    assert VisualMutationService(missing_id_host).targets.resolve_existing("Home", "Hero") is None


def test_delete_parent_fallback_uses_root_node_and_index_variants() -> None:
    root_host = _Host()
    root_host.discovery.data["_index"]["issues_sub"] = {}
    assert VisualMutationService(root_host).deletions.delete(
        "Home",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
    )
    assert _changes_without_random_ids(root_host.sent_payloads[0])[-1] == {
        "intent": "Update index",
        "path": ["_index", "issues_sub", "root-id"],
        "body": json.dumps([]),
    }

    index_host = _Host()
    index_host.discovery.data["pages"]["pg"] = {"elements": {}}
    index_host.discovery.data["_index"] = {
        "id_to_path": {
            "page-object": "%p3.pg",
            "hero-id": "%p3.pg.%el.hero",
            "nested-id": "%p3.pg.%el.hero.%el.nested",
            "bad-id": "%ed.pg.%el.bad",
        },
        "issues_sub": {},
    }
    index_host.path_values[("%p3", "pg")] = None
    assert VisualMutationService(index_host).deletions.delete(
        "Home",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
    )
    assert _changes_without_random_ids(index_host.sent_payloads[0])[-1] == {
        "intent": "Update index",
        "path": ["_index", "issues_sub", "page-object"],
        "body": json.dumps([]),
    }


def test_delete_helpers_isolate_malformed_index_payloads() -> None:
    host = _Host()
    service = VisualMutationService(host).deletions
    assert service._parse_children(None) == []
    assert service._parse_children("") == []
    assert service._parse_children("not-json") == []
    assert service._parse_children('{"not": "a-list"}') == []
    assert service._parse_children(["hero", "", None]) == ["hero", "None"]
    assert service._child_ids(None) == []
    assert service._child_ids({"elements": None}) == []
    assert service._child_ids(
        {"%el": {"length": 2, "bad": None, "fallback-key": {}, "child": {"id": "child-id"}}}
    ) == ["fallback-key", "child-id"]
    host.discovery.data["_index"]["id_to_path"] = {
        "wrong-context": "%p3.other",
        "wrong-depth": "%p3.pg.%el.hero.%el.nested",
        "empty-id": "%p3.pg.%el.empty",
    }
    assert service._context_object_id("pg", "page") == ""
    assert service._root_children_from_index("pg", "page") == ["empty-id"]


def test_delete_returns_false_when_target_resolution_fails() -> None:
    host = _Host()
    host.context_found = False
    assert not VisualMutationService(host).deletions.delete(
        "Missing",
        "Hero",
        allowed_types=frozenset({"text"}),
        expected_label="text",
        success_label="text",
    )


DELETE_FACADE_CONTRACTS = [
    ("delete_text", frozenset({"text"}), "text", "group"),
    ("delete_group", frozenset({"group", "custom_type"}), "group or custom_type", "group"),
    ("delete_floating_group", frozenset({"floatinggroup"}), "floatinggroup", "floating group"),
    ("delete_group_focus", frozenset({"groupfocus"}), "groupfocus", "group focus"),
    ("delete_repeating_group", frozenset({"repeatinggroup"}), "repeatinggroup", "repeating group"),
    ("delete_table", frozenset({"table"}), "table", "table"),
    ("delete_button", frozenset({"button"}), "button", "button"),
    ("delete_input", frozenset({"input"}), "input", "input"),
    ("delete_checkbox", frozenset({"checkbox"}), "checkbox", "checkbox"),
    ("delete_multiline_input", frozenset({"multilineinput"}), "multilineinput", "multiline input"),
    ("delete_dropdown", frozenset({"dropdown"}), "dropdown", "dropdown"),
    ("delete_datepicker", frozenset({"dateinput"}), "dateinput", "datepicker"),
    (
        "delete_searchbox",
        frozenset({"autocompletedropdown", "searchbox"}),
        "autocompletedropdown/searchbox",
        "searchbox",
    ),
    ("delete_icon", frozenset({"icon"}), "icon", "icon"),
    ("delete_image", frozenset({"image"}), "image", "image"),
    ("delete_link", frozenset({"link"}), "link", "link"),
    ("delete_shape", frozenset({"shape"}), "shape", "shape"),
    ("delete_alert", frozenset({"alert"}), "alert", "alert"),
    ("delete_video", frozenset({"video"}), "video", "video"),
    ("delete_html", frozenset({"html"}), "html", "html"),
    ("delete_map", frozenset({"map"}), "map", "map"),
    ("delete_radio", frozenset({"radiobuttons"}), "radiobuttons", "radio"),
    ("delete_slider", frozenset({"sliderinput"}), "sliderinput", "slider"),
    ("delete_file_uploader", frozenset({"fileinput"}), "fileinput", "file uploader"),
    (
        "delete_picture_uploader",
        frozenset({"pictureinput"}),
        "pictureinput",
        "picture uploader",
    ),
    ("delete_popup", frozenset(), "popup", "popup"),
]


@pytest.mark.parametrize(
    ("method_name", "allowed_types", "expected_label", "success_label"),
    DELETE_FACADE_CONTRACTS,
)
def test_bubble_cli_visual_delete_facades_delegate_literal_contract(
    method_name: str,
    allowed_types: frozenset[str],
    expected_label: str,
    success_label: str,
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _DeletionSpy:
        def delete(self, *args: Any, **kwargs: Any) -> bool:
            calls.append((args, kwargs))
            return True

    cli = object.__new__(BubbleCLI)
    cli._visual_mutations = SimpleNamespace(deletions=_DeletionSpy())

    assert getattr(BubbleCLI, method_name)(
        cli,
        "Home",
        "Hero",
        dry_run=True,
        prefer_last=True,
    )
    assert calls == [
        (
            ("Home", "Hero"),
            {
                "allowed_types": allowed_types,
                "expected_label": expected_label,
                "success_label": success_label,
                "dry_run": True,
                "prefer_last": True,
            },
        )
    ]
