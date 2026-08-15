from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
from bubble_mcp.aria_runtime.style_lifecycle.assignments import (
    StyleAssignmentService,
    StyleOverridePolicy,
)
from bubble_mcp.aria_runtime.style_lifecycle.references import StyleReferenceResolver


class _AssignmentHost:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {
            "styles": {
                "Text_body_": {"%x": "Text", "%p": {"%fs": 16, "%fc": "#101828"}},
                "Button_primary_": {"%x": "Button", "%p": {"%bgc": "#155eef", "%br": 8}},
                "Group_card_": {
                    "%x": "Group",
                    "%p": {"%bgc": "#ffffff", "container_layout": "column"},
                },
                "Table_plain_": {"%x": "Table", "%p": {"%bc": "#d0d5dd"}},
                "RepeatingGroup_list_": {
                    "%x": "RepeatingGroup",
                    "%p": {"%ss": "solid", "%sw": 1, "%sc": "#d0d5dd"},
                },
                "Popup_modal_": {
                    "%x": "Popup",
                    "%p": {"greyout_color": "#00000080", "button_gap": 12},
                },
                "DateInput_default_": {
                    "%x": "DateInput",
                    "%p": {"%fc": "#344054", "date_format": "us_short"},
                },
            }
        }
        self.cache: dict[str, Any] = {
            "styles": {
                "Cached text": {
                    "id": "Text_cached_",
                    "type": "Text",
                    "%p": {"%lh": 1.5},
                }
            }
        }
        self.revision = 0

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.data, self.cache

    def style_reference_revision(self) -> int:
        return self.revision

    def list_style_references(self) -> list[dict[str, Any]]:
        return []

    def list_style_reference_elements(self) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def normalize_style_reference(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def compact_style_reference(value: Any) -> str:
        return "".join(character for character in str(value or "").lower() if character.isalnum())

    @staticmethod
    def plain_style_reference_text(value: Any) -> str:
        return str(value or "").strip()


@pytest.fixture
def services() -> tuple[StyleOverridePolicy, StyleAssignmentService]:
    host = _AssignmentHost()
    references = StyleReferenceResolver(host)
    policy = StyleOverridePolicy(host, references)
    return policy, StyleAssignmentService(policy)


@pytest.mark.parametrize(
    ("element_type", "style_id", "required_keys"),
    [
        ("Text", "Text_body_", {"%fs", "font_size", "%fc", "font_color", "%lh"}),
        ("Button", "Button_primary_", {"%bgc", "background_color", "%br", "border_radius"}),
        ("Group", "Group_card_", {"%bgc", "container_layout"}),
        ("Table", "Table_plain_", {"%bc", "border_color"}),
        (
            "RepeatingGroup",
            "RepeatingGroup_list_",
            {"%ss", "%sw", "%sc", "separator_style", "separator_width", "separator_color"},
        ),
        ("Popup", "Popup_modal_", {"greyout_color", "grayout_color", "button_gap"}),
        ("DateInput", "DateInput_default_", {"%fc", "font_color", "date_format"}),
    ],
)
def test_override_keys_cover_literal_element_policies(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
    element_type: str,
    style_id: str,
    required_keys: set[str],
) -> None:
    policy, _ = services

    assert required_keys <= set(policy.override_keys(element_type, target_style_id=style_id))


def test_prune_removes_alias_equivalent_defaults_and_keeps_differences_and_structure(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
) -> None:
    policy, _ = services
    updates: dict[str, Any] = {
        "background_color": "#ffffff",
        "border_width": 2,
        "center_background": False,
        "container_layout": "column",
        "%3": "Card title",
    }

    policy.prune(updates, element_type="Group", style_id="Group_card_")

    assert updates == {
        "border_width": 2,
        "container_layout": "column",
        "%3": "Card title",
    }


def test_prune_removes_default_false_overrides_when_style_properties_are_empty(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
) -> None:
    policy, _ = services
    updates: dict[str, Any] = {"center_background": False, "%3": "Title"}

    policy.prune(updates, element_type="Group", style_id="Group_empty_")

    assert updates == {"%3": "Title"}

@pytest.mark.parametrize(
    ("element_type", "required_keys"),
    [
        ("Group", {"%ds", "%gt", "container_layout", "%w", "%t", "unique_id"}),
        ("FloatingGroup", {"container_layout", "%3f", "float_zindex", "parallax"}),
        ("GroupFocus", {"container_layout", "reference", "offset_top", "offset_left"}),
        ("Table", {"%ds", "%gt", "%rs", "container_layout"}),
        ("RepeatingGroup", {"%ds", "%gt", "%rs", "fixed_rows", "cell_min_width_css"}),
        ("Popup", {"%ds", "%gt", "container_layout", "%w", "%h"}),
        ("DateInput", {"date_format", "custom_format", "initial_content", "bind_field"}),
    ],
)
def test_protected_structural_properties_are_named_by_element_policy(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
    element_type: str,
    required_keys: set[str],
) -> None:
    policy, _ = services

    assert required_keys <= policy.protected_keys(element_type)


def test_popup_assignment_drops_stale_alignment_override_from_carried_properties(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
) -> None:
    policy, assignment = services
    path = ["%p3", "index", "%el", "modal"]
    current_props: dict[str, Any] = {
        "%b4": "center",
        "container_layout": "column",
        "%w": 640,
        "%h": 480,
        "%ds": {"%x": "CurrentPage"},
    }
    override_keys = set(policy.override_keys("Popup", target_style_id="Popup_modal_"))
    protected_keys = policy.protected_keys("Popup")
    carried_props = {
        key: value
        for key, value in current_props.items()
        if key in protected_keys or key not in override_keys
    }
    payload = PayloadBuilder(appname="assignment-test")

    assignment.assign(
        payload,
        path,
        "Popup_modal_",
        style_props=carried_props,
        include_set_data=False,
    )

    popup_body = next(
        row[2]
        for row in _rows(payload)
        if row[0] == "AssignStyle" and row[1][-1] == "%p"
    )
    assert popup_body == {
        "container_layout": "column",
        "%w": 640,
        "%h": 480,
        "%ds": {"%x": "CurrentPage"},
    }


def test_prune_sdk_properties_preserves_independent_borders_and_normalizes_px(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
) -> None:
    policy, _ = services
    properties: dict[str, Any] = {
        "bg_color": "#155eef",
        "border_radius": "8px",
        "border_roundness_top_left": 8,
        "font_size": 18,
        "fit_width": True,
        "max_width_css": "320px",
        "four_border_style": True,
        "border_width_top": 4,
    }

    policy.prune(
        properties,
        element_type="Button",
        style_id="Button_primary_",
        sdk_properties=True,
    )

    assert properties == {
        "font_size": 18,
        "fit_width": True,
        "four_border_style": True,
        "border_width_top": 4,
    }


def _rows(payload: PayloadBuilder) -> list[tuple[str, list[str], Any]]:
    return [
        (
            str(change.get("intent", {}).get("name")),
            list(change.get("path_array") or []),
            change.get("body"),
        )
        for change in payload.changes
    ]


def test_assign_emits_clear_override_marker_shared_intents_and_explicit_props_in_order(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, assignment = services
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.style_lifecycle.assignments.random.randint",
        lambda start, end: 4242,
    )
    payload = PayloadBuilder(appname="assignment-test")
    path = ["%p3", "index", "%el", "hero"]

    assignment.assign(
        payload,
        path,
        "Text_body_",
        style_props={"%fs": 18, "%fc": None},
        include_set_data=False,
        clear_override_keys=["%fc", "%fs"],
        marker_prop_updates={"style": "explicit-marker"},
        extra_marker_keys=["legacy_style"],
        explicit_props={"%3": "Hello", "%fs": 18, "%fc": None},
    )

    rows = _rows(payload)
    assert rows == [
        ("SetData", path + ["%p", "%fc"], None),
        ("SetData", path + ["%p", "%s1"], None),
        ("SetData", path + ["%p", "style_id"], None),
        ("SetData", path + ["%p", "style_name"], None),
        ("SetData", path + ["%p", "style_ref"], None),
        ("SetData", path + ["%p", "style_reference"], None),
        ("SetData", path + ["%p", "legacy_style"], None),
        ("AssignStyle", path + ["%s1"], "Text_body_"),
        ("AssignStyle", path + ["%p"], {"%fs": 18}),
        ("SetData", path + ["%p", "%3"], "Hello"),
        ("SetData", path + ["%p", "%fs"], 18),
    ]
    assign_ids = [
        change["intent"]["id"]
        for change in payload.changes
        if change.get("intent", {}).get("name") == "AssignStyle"
    ]
    assert assign_ids == [4242, 4242]


@pytest.mark.parametrize(
    ("element_type", "style_id", "explicit_key"),
    [
        ("Text", "Text_body_", "%3"),
        ("Button", "Button_primary_", "%3"),
        ("Group", "Group_card_", "container_layout"),
        ("Table", "Table_plain_", "%ds"),
        ("RepeatingGroup", "RepeatingGroup_list_", "%rs"),
        ("Popup", "Popup_modal_", "container_layout"),
        ("DateInput", "DateInput_default_", "date_format"),
    ],
)
def test_assign_preserves_explicit_element_properties_after_style_intents(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
    element_type: str,
    style_id: str,
    explicit_key: str,
) -> None:
    policy, assignment = services
    payload = PayloadBuilder(appname="assignment-test")
    path = ["%p3", "index", "%el", element_type.lower()]

    assignment.assign(
        payload,
        path,
        style_id,
        clear_override_keys=policy.override_keys(element_type, target_style_id=style_id),
        explicit_props={explicit_key: "explicit"},
    )

    rows = _rows(payload)
    assert rows[-1] == ("SetData", path + ["%p", explicit_key], "explicit")
    assert next(index for index, row in enumerate(rows) if row[0] == "AssignStyle") < len(rows) - 1


def test_clear_style_supports_removal_with_and_without_set_data(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, assignment = services
    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.style_lifecycle.assignments.random.randint",
        lambda start, end: 31337,
    )
    path = ["%p3", "index", "%el", "hero"]
    with_set_data = PayloadBuilder(appname="assignment-test")
    without_set_data = PayloadBuilder(appname="assignment-test")

    assignment.clear(with_set_data, path)
    assignment.clear(without_set_data, path, include_set_data=False)

    assert _rows(with_set_data) == [
        ("SetData", path + ["%s1"], None),
        ("AssignStyle", path + ["%s1"], None),
    ]
    assert _rows(without_set_data) == [("AssignStyle", path + ["%s1"], None)]
    assert with_set_data.changes[-1]["intent"]["id"] == 31337
    assert without_set_data.changes[-1]["intent"]["id"] == 31337


def test_invalid_payloads_and_blank_styles_are_noops(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
) -> None:
    policy, assignment = services
    payload = PayloadBuilder(appname="assignment-test")

    assignment.assign(object(), [], "Text_body_")  # type: ignore[arg-type]
    assignment.assign(payload, [], " ")
    assignment.clear(object(), [])  # type: ignore[arg-type]
    assignment.clear_markers(object(), [])  # type: ignore[arg-type]
    assignment.clear_overrides(object(), [], [])  # type: ignore[arg-type]
    policy.prune(object(), element_type="Text", style_id="Text_body_")  # type: ignore[arg-type]
    policy.prune({}, element_type="Text", style_id="")
    policy.prune({}, element_type="Text", style_id="Text_missing_")
    assert policy.override_keys(None) == []
    assert payload.changes == []


def test_override_policy_tolerates_malformed_snapshot_entries() -> None:
    host = _AssignmentHost()
    host.data = {"styles": []}
    host.cache = {
        "styles": {
            "not-an-object": None,
            "wrong-type": {"%x": "Button", "%p": {"%custom": True}},
            "props-not-object": {"%x": "Text", "%p": []},
        }
    }
    references = StyleReferenceResolver(host)
    policy = StyleOverridePolicy(host, references)

    keys = policy.override_keys("Text")

    assert "%fs" in keys
    assert "%custom" not in keys


def test_sdk_pruning_covers_height_background_difference_and_non_numeric_values() -> None:
    host = _AssignmentHost()
    host.data["styles"]["Group_none_"] = {
        "%x": "Group",
        "%p": {"%bas": "none", "%br": "not-a-number-px", "%fs": 16},
    }
    references = StyleReferenceResolver(host)
    policy = StyleOverridePolicy(host, references)
    opaque = object()
    properties: dict[str, Any] = {
        "fit_height": True,
        "max_height_css": "480px",
        "bg_color": "#ffffff",
        "border_radius": "NOT-A-NUMBER-PX",
        "font_size": 18,
        "unknown": opaque,
    }

    policy.prune(
        properties,
        element_type="Group",
        style_id="Group_none_",
        sdk_properties=True,
    )

    assert properties == {
        "fit_height": True,
        "bg_color": "#ffffff",
        "background_style": "bgcolor",
        "font_size": 18,
        "unknown": opaque,
    }


def test_marker_and_override_cleanup_deduplicates_blanks_and_blocked_keys(
    services: tuple[StyleOverridePolicy, StyleAssignmentService],
) -> None:
    _, assignment = services
    payload = PayloadBuilder(appname="assignment-test")
    path = ["%p3", "index", "%el", "hero"]

    assignment.clear_markers(
        payload,
        path,
        prop_updates={"style": "keep"},
        extra_keys=["", "style_id", "legacy", "legacy"],
    )
    assignment.clear_overrides(
        payload,
        path,
        ["", "%fc", "%fc", "%fs"],
        blocked_keys={"%fs"},
    )

    suffixes = [row[1][-1] for row in _rows(payload)]
    assert suffixes == [
        "%s1",
        "style_id",
        "style_name",
        "style_ref",
        "style_reference",
        "legacy",
        "%fc",
    ]
