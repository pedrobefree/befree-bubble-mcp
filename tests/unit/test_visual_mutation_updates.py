from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
from bubble_mcp.aria_runtime.visual_mutations.protocols import VisualElementTarget
from bubble_mcp.aria_runtime.visual_mutations.updates import VisualUpdateService


class _UpdateDiscovery:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {
            "_index": {"id_to_path": {"element-id": "%p3.pg.%el.element-key"}}
        }
        self.named: dict[str, Any] | None = {
            "id": "element-id",
            "key": "element-key",
            "path": ["%el", "element-key"],
            "element": {"id": "element-id", "%x": "Text", "%p": {"%3": "Before"}},
        }

    def find_element_by_name(
        self,
        context_id: str,
        element_name: str,
        *,
        context_type: str,
        prefer_last: bool = False,
    ) -> dict[str, Any] | None:
        del context_id, element_name, context_type, prefer_last
        return self.named

    @staticmethod
    def build_path_array(
        context_id: str,
        path: list[str],
        *,
        context_type: str,
    ) -> list[str]:
        del context_type
        return ["%p3", context_id, *path]

    @staticmethod
    def list_elements(context_id: str, *, context_type: str) -> list[dict[str, Any]]:
        del context_id, context_type
        return []


class _UpdateHost:
    appname = "visual-update-test"

    def __init__(self) -> None:
        self.discovery = _UpdateDiscovery()
        self.sent: list[PayloadBuilder] = []
        self.dispatch_error = False
        self.style_id: str | None = "Text_heading_"
        self.style_looks_like_id = False
        self.inferred_type: str | None = None
        self.marker_calls: list[tuple[list[str], dict[str, Any]]] = []
        self.assignment_calls: list[dict[str, Any]] = []

    @staticmethod
    def _find_context(name: str) -> tuple[str | None, str | None]:
        return ("pg", "page") if name == "Home" else (None, None)

    @staticmethod
    def _find_button_by_label(
        context_id: str, context_type: str, label: str
    ) -> dict[str, Any] | None:
        del context_id, context_type, label
        return None

    @staticmethod
    def _find_element_by_ref(
        context_id: str,
        context_type: str,
        element_ref: str,
        *,
        ref_kind: str,
        match_index: int,
    ) -> dict[str, Any] | None:
        del context_id, context_type, element_ref, ref_kind, match_index
        return None

    @staticmethod
    def _resolve_cached_element_alias(
        context_id: str, context_type: str, element_ref: str
    ) -> dict[str, Any] | None:
        del context_id, context_type, element_ref
        return None

    @staticmethod
    def _get_value_at_path(path: list[str]) -> Any:
        del path
        return None

    @staticmethod
    def _normalize_capture_path(path: Any) -> list[str]:
        return str(path or "").split(".") if path else []

    @staticmethod
    def _normalize_payload_path(path: Any) -> list[str]:
        return list(path) if isinstance(path, list) else []

    @staticmethod
    def _workflow_prefix(context_type: str) -> str:
        return "%ed" if context_type == "reusable" else "%p3"

    @staticmethod
    def _canonicalize_context_prefix_on_path(
        path: list[str], context_id: str, context_type: str
    ) -> list[str]:
        del context_id, context_type
        return path

    def _looks_like_style_id(self, value: Any, element_type: str | None = None) -> bool:
        del value, element_type
        return self.style_looks_like_id

    def _resolve_style_reference(
        self,
        style_value: str | None,
        *,
        element_type: str | None = None,
        strict: bool = False,
    ) -> str | None:
        del style_value, element_type, strict
        return self.style_id

    def _infer_element_type_from_style_id(self, style_id: str | None) -> str | None:
        del style_id
        return self.inferred_type

    @staticmethod
    def _style_override_keys_for_element_type(
        element_type: str | None, *, target_style_id: str | None = None
    ) -> list[str]:
        del element_type, target_style_id
        return ["%fc", "%fs"]

    def _queue_clear_style_marker_props(
        self,
        payload: PayloadBuilder,
        element_path: list[str],
        *,
        prop_updates: dict[str, Any] | None = None,
        extra_keys: list[str] | None = None,
    ) -> None:
        del extra_keys
        updates = dict(prop_updates or {})
        self.marker_calls.append((element_path, updates))
        payload.add_set_data(element_path + ["%p", "style_marker"], None)

    def _queue_style_assignment_changes(
        self,
        payload: PayloadBuilder,
        element_path: list[str],
        style_id: str | None,
        style_props: dict[str, Any] | None = None,
        include_set_data: bool = True,
    ) -> None:
        self.assignment_calls.append(
            {
                "path": element_path,
                "style_id": style_id,
                "style_props": style_props,
                "include_set_data": include_set_data,
            }
        )
        payload.add_set_data(element_path + ["%s1"], style_id)

    def _dispatch_payload(self, payload: PayloadBuilder) -> None:
        if self.dispatch_error:
            raise RuntimeError("dispatch failed")
        self.sent.append(payload)


def _target(*, element_type: str = "text") -> VisualElementTarget:
    result = {
        "id": "element-id",
        "key": "element-key",
        "path": ["%el", "element-key"],
        "element": {"id": "element-id", "%x": element_type.title(), "%p": {}},
    }
    return VisualElementTarget(
        context_id="pg",
        context_type="page",
        result=result,
        element_id="element-id",
        element_type=element_type,
        path=["%p3", "pg", "%el", "element-key"],
    )


def _rows(payload: PayloadBuilder) -> list[tuple[str, list[str], Any]]:
    return [
        (
            str(change.get("intent", {}).get("name")),
            list(change.get("path_array") or []),
            change.get("body"),
        )
        for change in payload.changes
    ]


def test_apply_emits_plain_updates_in_literal_order() -> None:
    host = _UpdateHost()
    service = VisualUpdateService(host, SimpleNamespace(resolve_existing=lambda *a, **k: _target()))

    assert service.apply(
        "Home",
        "Hero",
        prop_updates={"%3": "After", "%fc": None, "%fs": 18},
    )

    assert len(host.sent) == 1
    assert _rows(host.sent[0]) == [
        ("SetData", ["%p3", "pg", "%el", "element-key", "%p", "%3"], "After"),
        ("SetData", ["%p3", "pg", "%el", "element-key", "%p", "%fs"], 18),
    ]


def test_apply_style_preserves_clear_marker_assignment_and_prop_order() -> None:
    host = _UpdateHost()
    service = VisualUpdateService(host, SimpleNamespace(resolve_existing=lambda *a, **k: _target()))

    assert service.apply(
        "Home",
        "Hero",
        prop_updates={"%fc": "#ffffff"},
        style="Heading",
        clear_style_override_keys=["%fc", "%fs"],
        force_style_assign=True,
        style_assign_props={"%fc": "#ffffff"},
        style_assign_with_set_data=False,
    )

    rows = _rows(host.sent[0])
    assert [row[1][-1] for row in rows] == ["%fs", "style_marker", "%s1", "%fc"]
    assert rows[0][2] is None
    assert host.assignment_calls[0]["include_set_data"] is False


def test_apply_accepts_explicit_style_id_and_infers_missing_element_type() -> None:
    host = _UpdateHost()
    host.style_looks_like_id = True
    host.inferred_type = "Button"
    target = _target(element_type="")
    target.result["element"]["%x"] = ""
    service = VisualUpdateService(host, SimpleNamespace(resolve_existing=lambda *a, **k: target))

    assert service.apply("Home", "Hero", prop_updates={}, style="Button_primary_")
    assert _rows(host.sent[0])[-1][1][-1] == "%s1"


def test_apply_handles_missing_target_style_noop_preview_and_dispatch_failure() -> None:
    host = _UpdateHost()
    targets = SimpleNamespace(resolve_existing=lambda *a, **k: None)
    service = VisualUpdateService(host, targets)
    assert service.apply("Missing", "Hero", prop_updates={"%3": "After"}) is False

    service = VisualUpdateService(host, SimpleNamespace(resolve_existing=lambda *a, **k: _target()))
    host.style_id = None
    assert service.apply("Home", "Hero", prop_updates={}, style="Unknown") is False
    assert service.apply("Home", "Hero", prop_updates={}) is True
    assert service.apply("Home", "Hero", prop_updates={"%3": "Preview"}, dry_run=True) is True
    assert host.sent == []
    host.dispatch_error = True
    assert service.apply("Home", "Hero", prop_updates={"%3": "After"}) is False


def test_apply_reuses_resolved_target_and_supports_direct_root_updates() -> None:
    host = _UpdateHost()

    class _Targets:
        def resolve_existing(self, *args: Any, **kwargs: Any) -> VisualElementTarget:
            raise AssertionError("resolved target should be reused")

    service = VisualUpdateService(host, _Targets())
    assert service.apply(
        "Home",
        "Hero",
        prop_updates={},
        direct_updates=[(["%s1"], None), (["%p", "use_gap"], True)],
        resolved_target=_target(),
        success_message="updated directly",
    )
    assert _rows(host.sent[0]) == [
        ("SetData", ["%p3", "pg", "%el", "element-key", "%s1"], None),
        ("SetData", ["%p3", "pg", "%el", "element-key", "%p", "use_gap"], True),
    ]


def test_bubble_cli_update_helpers_are_compatibility_facades() -> None:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    class _TargetsSpy:
        def resolve_existing_tuple(self, *args: Any, **kwargs: Any) -> tuple[str, str, dict[str, Any]]:
            calls.append(("resolve", args, kwargs))
            return ("pg", "page", {"id": "element-id"})

        def from_result(self, *args: Any, **kwargs: Any) -> VisualElementTarget:
            calls.append(("from_result", args, kwargs))
            return _target()

    class _UpdatesSpy:
        def apply(self, *args: Any, **kwargs: Any) -> bool:
            calls.append(("apply", args, kwargs))
            return True

    cli = object.__new__(BubbleCLI)
    cli._visual_mutations = SimpleNamespace(targets=_TargetsSpy(), updates=_UpdatesSpy())
    resolved = ("pg", "page", {"id": "element-id"})

    assert cli._resolve_element_for_updates("Home", "Hero") == resolved
    assert cli._apply_element_updates(
        "Home",
        "Hero",
        prop_updates={"%3": "After"},
        resolved_target=resolved,
    )
    assert [call[0] for call in calls] == ["resolve", "from_result", "apply"]
