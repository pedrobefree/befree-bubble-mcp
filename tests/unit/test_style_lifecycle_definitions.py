from __future__ import annotations

import copy
import re
from typing import Any

import pytest

from bubble_mcp.aria_runtime.style_lifecycle.definitions import StyleDefinitionService
from bubble_mcp.aria_runtime.style_lifecycle.references import StyleReferenceResolver


class _FixedIds:
    def element_id(self) -> str:
        return "bSTYLE"


class _Colors:
    def resolve(self, value: str) -> str:
        return {
            "Brand": "var(--color_brand_default)",
            "Danger": "var(--color_danger_default)",
        }.get(value, value)


class _Host:
    appname = "definition-service-test"
    dry_run = False
    id_gen = _FixedIds()

    def __init__(self, styles: dict[str, dict[str, Any]] | None = None) -> None:
        self.discovery: dict[str, Any] = {"styles": copy.deepcopy(styles or {})}
        self.cache: dict[str, Any] = {"styles": {}}
        self.revision = 0
        self.dispatches: list[list[tuple[str | None, list[str], Any]]] = []
        self.events: list[tuple[Any, ...]] = []
        self.fail_dispatch_at: int | None = None
        self.fail_cache: str | None = None

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.discovery, self.cache

    def style_reference_revision(self) -> int:
        return self.revision

    def list_style_references(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for style_id, raw in self.discovery["styles"].items():
            if not isinstance(raw, dict):
                continue
            rows.append(
                {
                    "id": style_id,
                    "name": raw.get("%d") or raw.get("name") or style_id,
                    "type": raw.get("%x") or raw.get("type"),
                    "is_default": bool(raw.get("is_default")),
                }
            )
        return rows

    def list_style_reference_elements(self) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def normalize_style_reference(value: Any) -> str:
        return " ".join(str(value or "").strip().casefold().replace("_", " ").split())

    @staticmethod
    def compact_style_reference(value: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

    @staticmethod
    def plain_style_reference_text(value: Any) -> str:
        return str(value or "")

    def dispatch_style_definition_payload(self, payload: Any) -> None:
        rows = [
            (
                change.get("intent", {}).get("name"),
                list(change.get("path_array") or []),
                copy.deepcopy(change.get("body")),
            )
            for change in payload.changes
        ]
        attempt = len(self.dispatches) + 1
        self.events.append(("dispatch", attempt, [row[0] for row in rows]))
        if self.fail_dispatch_at == attempt:
            raise RuntimeError(f"literal dispatch failure {attempt}")
        self.dispatches.append(rows)

    def put_style_definition_cache(self, name: str, data: dict[str, Any]) -> None:
        if self.fail_cache == "put":
            raise RuntimeError("literal cache put failure")
        self.events.append(("cache-put", name, copy.deepcopy(data)))
        self.cache.setdefault("styles", {})[name] = copy.deepcopy(data)
        self.revision += 1

    def remove_style_definition_cache(self, name: str) -> None:
        if self.fail_cache == "remove":
            raise RuntimeError("literal cache remove failure")
        self.events.append(("cache-remove", name))
        self.cache.setdefault("styles", {}).pop(name, None)
        self.revision += 1

    def save_style_definition_cache(self) -> None:
        if self.fail_cache == "save":
            raise RuntimeError("literal cache save failure")
        self.events.append(("cache-save",))

    def hydrate_style_definition(
        self,
        style_id: str,
        name: str,
        element_type: str,
        properties: dict[str, Any],
        *,
        clear_properties: tuple[str, ...] = (),
    ) -> None:
        self.events.append(("hydrate", style_id, copy.deepcopy(properties)))
        current = self.discovery.setdefault("styles", {}).setdefault(style_id, {})
        current.update({"%d": name, "%x": element_type})
        current_props = current.get("%p")
        if not isinstance(current_props, dict):
            current_props = {}
            current["%p"] = current_props
        current_props.update(copy.deepcopy(properties))
        for property_name in clear_properties:
            current_props.pop(property_name, None)
        self.revision += 1

    def base_style_properties(self, style_id: str) -> dict[str, Any]:
        raw = self.discovery.get("styles", {}).get(style_id, {})
        properties = raw.get("%p") if isinstance(raw, dict) else None
        return dict(properties) if isinstance(properties, dict) else {}

    def compensate_style_state_padding(
        self,
        style_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        del style_id
        return dict(properties)

    def augment_disabled_style_state(
        self,
        style_id: str,
        properties: dict[str, Any],
        comparison_map: dict[str, str],
        base_properties: dict[str, Any],
    ) -> dict[str, Any]:
        del style_id, comparison_map
        augmented = dict(properties)
        if "border_color" not in augmented and "%bc" in base_properties:
            augmented["border_color"] = base_properties["%bc"]
        return augmented


def _service(host: _Host) -> StyleDefinitionService:
    return StyleDefinitionService(host, StyleReferenceResolver(host), _Colors())


def _style(
    name: str,
    element_type: str,
    properties: dict[str, Any] | None = None,
    states: dict[str, Any] | None = None,
    *,
    is_default: bool = False,
) -> dict[str, Any]:
    return {
        "%d": name,
        "%x": element_type,
        "%p": dict(properties or {}),
        "%s": copy.deepcopy(states or {}),
        "is_default": is_default,
    }


def test_state_definition_normalization_preserves_literal_order_and_rejects_invalid_rows() -> None:
    assert StyleDefinitionService.normalize_state_definitions(
        '{"hover":{"font_color":"red"},"disabled":{"opacity":0.5}}'
    ) == [
        ("hover", {"font_color": "red"}),
        ("disabled", {"opacity": 0.5}),
    ]
    assert StyleDefinitionService.normalize_state_definitions(
        [{"state": "focus", "props": {"border_color": "blue"}}]
    ) == [("focus", {"border_color": "blue"})]

    with pytest.raises(ValueError, match="must map to an object"):
        StyleDefinitionService.normalize_state_definitions({"hover": "red"})


def test_style_kwarg_normalization_covers_aliases_and_independent_border_defaults() -> None:
    assert StyleDefinitionService.normalize_kwargs(
        {
            "bg_style": "flat-color",
            "gradient_color1": "one",
            "gradient_color2": "two",
            "padding": 12,
            "border_type": "all 4 borders",
            "border_style_top": "solid",
            "style_json": "literal-map-style",
        }
    ) == {
        "background_style": "bgcolor",
        "gradient_start_color": "one",
        "gradient_end_color": "two",
        "padding_top": 12,
        "padding_bottom": 12,
        "padding_left": 12,
        "padding_right": 12,
        "border_type": "independent",
        "border_style_top": "solid",
        "border_style_bottom": "none",
        "border_style_left": "none",
        "border_style_right": "none",
        "border_width_right": 0,
        "border_width_bottom": 0,
        "border_width_left": 0,
        "border_roundness_right": 0,
        "border_roundness_bottom": 0,
        "border_roundness_left": 0,
        "custom_style": "literal-map-style",
    }


def test_create_style_preserves_literal_payload_order_and_caches_only_after_dispatch() -> None:
    host = _Host()

    assert _service(host).create_style(
        "Primary Card",
        "group",
        allow_property_match=False,
        default_style=True,
        bg_style="flat color",
        bg_color="Brand",
    ) is True

    assert [row[0] for row in host.dispatches[0]] == [
        "Update index",
        "CreateStyle",
        "IdToPathFixer",
        "ChangeAppSetting",
        None,
    ]
    assert [row[1] for row in host.dispatches[0][:4]] == [
        ["_index", "id_to_path", "Group_primary_card_"],
        ["styles", "Group_primary_card_"],
        ["_index", "id_to_path", "Group_primary_card_"],
        ["settings", "client_safe", "default_styles"],
    ]
    assert host.dispatches[0][3][2] == {"Group": "Group_primary_card_"}
    assert [row[1][-1] for row in host.dispatches[1]] == ["%bas", "%bgc"]
    assert host.dispatches[1][1][2] == "var(--color_brand_default)"
    assert [event[0] for event in host.events] == [
        "dispatch",
        "cache-put",
        "cache-save",
        "hydrate",
        "dispatch",
        "cache-put",
        "cache-save",
    ]
    assert host.cache["styles"]["Primary Card"]["id"] == "Group_primary_card_"


def test_create_dry_run_explicitly_hydrates_discovery_without_dispatch_or_cache() -> None:
    host = _Host()

    assert _service(host).create_style(
        "Preview",
        "Text",
        dry_run=True,
        allow_property_match=False,
        font_color="Danger",
        font_size=18,
    ) is True

    assert host.dispatches == []
    assert host.cache == {"styles": {}}
    assert host.discovery["styles"]["Text_preview_"]["%p"] == {
        "%fc": "var(--color_danger_default)",
        "%ic": "var(--color_danger_default)",
        "%fs": 18,
    }
    assert [event[0] for event in host.events] == ["hydrate", "hydrate"]


def test_create_dispatch_failure_does_not_mutate_cache_or_hydrate_discovery() -> None:
    host = _Host()
    host.fail_dispatch_at = 1

    assert _service(host).create_style(
        "Failure",
        "Button",
        allow_property_match=False,
    ) is False

    assert host.cache == {"styles": {}}
    assert host.discovery == {"styles": {}}
    assert [event[0] for event in host.events] == ["dispatch"]


def test_update_rename_and_default_operations_keep_wire_order_and_failure_semantics() -> None:
    host = _Host({"Text_body_": _style("Body", "Text", {"%fs": 14})})
    service = _service(host)

    assert service.update_style_definition(
        "Body",
        "text",
        bg_style="gradient",
        bg_color="Brand",
        default_style=True,
    ) is True
    assert [row[0] for row in host.dispatches[0]] == [
        "SetStyleData",
        "SetStyleData",
        "ChangeAppSetting",
    ]
    assert [row[1][-1] for row in host.dispatches[0]] == [
        "%bas",
        "%bgc",
        "default_styles",
    ]
    assert host.events[0][0] == "dispatch"
    assert host.events[1][0] == "cache-put"

    assert service.rename_style("Text_body_", "Body copy") is True
    assert host.dispatches[1] == [
        ("SetStyleData", ["styles", "Text_body_", "%d"], "Body copy")
    ]
    assert service.set_default_style("search box", "SearchBox_primary_") is True
    assert host.dispatches[2][0][2] == {"AutocompleteDropdown": "SearchBox_primary_"}

    failed_host = _Host({"Text_body_": _style("Body", "Text", {"%fs": 14})})
    failed_host.fail_dispatch_at = 1
    before = copy.deepcopy(failed_host.cache)
    assert _service(failed_host).update_style_definition("Body", "Text", font_size=16) is False
    assert failed_host.cache == before


def test_state_operation_preserves_transition_create_property_stage_order_and_cache_boundary() -> None:
    host = _Host(
        {"Button_primary_": _style("Primary", "Button", {"%bc": "black", "%fc": "white"})}
    )

    assert _service(host).add_style_condition(
        "Primary",
        "invalid + hover, focus",
        index="state0",
        bg_color="Brand",
        font_color="Danger",
    ) is True

    assert [row[0] for row in host.dispatches[0]] == ["AddTransition", "AddTransition"]
    assert [row[1][-1] for row in host.dispatches[0]] == ["%bas", "%fc"]
    assert host.dispatches[1][0][0] == "NewStyleState"
    assert host.dispatches[1][-1][0] is None
    assert [row[0] for row in host.dispatches[2]][:2] == [
        "SetStyleStateCondition",
        "SetStyleStateCondition",
    ]
    assert host.cache["styles"]["Primary"]["conditions"] == {
        "invalid + hover, focus": "state0"
    }
    assert host.events[-2:] == [
        (
            "cache-put",
            "Primary",
            {
                "id": "Button_primary_",
                "type": "Button",
                "%p": {"%bc": "black", "%fc": "white"},
                "conditions": {"invalid + hover, focus": "state0"},
            },
        ),
        ("cache-save",),
    ]

    failed = _Host(
        {"Button_primary_": _style("Primary", "Button", {"%bc": "black", "%fc": "white"})}
    )
    failed.fail_dispatch_at = 2
    assert _service(failed).add_style_condition(
        "Primary",
        "hover",
        index="state0",
        font_color="Danger",
    ) is False
    assert failed.cache == {"styles": {}}


def test_transition_intents_and_order_parser_are_deterministic() -> None:
    assert StyleDefinitionService.build_transition_intents(
        "Button_primary_",
        {"bg_color": "red", "font_color": "white", "background_color": "blue"},
    ) == [
        {
            "intent": "AddTransition",
            "path": ["styles", "Button_primary_", "transitions", "%bas"],
            "body": {"duration": 200, "fn": "ease"},
        },
        {
            "intent": "AddTransition",
            "path": ["styles", "Button_primary_", "transitions", "%fc"],
            "body": {"duration": 200, "fn": "ease"},
        },
    ]
    assert StyleDefinitionService.parse_reorder_order("disabled stronger than hover") == [
        "hover",
        "disabled",
    ]
    assert StyleDefinitionService.parse_reorder_order(["hover", "disabled", "hover"]) == [
        "hover",
        "disabled",
    ]


def test_reorder_states_reindexes_literal_order_and_updates_cache_only_after_dispatch() -> None:
    hover = {"%c": {"%n": {"%nm": "is_hovered"}}, "%p": {"%fc": "red"}}
    disabled = {"%x": "State", "%c": {"%n": {"%nm": "isnt_clickable"}}, "%p": {}}
    host = _Host(
        {"Button_primary_": _style("Primary", "Button", states={"8": disabled, "2": hover})}
    )
    host.cache["styles"]["Primary"] = {
        "id": "Button_primary_",
        "type": "Button",
        "%s": {"8": disabled, "2": hover},
    }

    assert _service(host).reorder_style_states(
        "Primary",
        "disabled stronger than hover",
    ) is True

    assert [row[0] for row in host.dispatches[0]] == ["SetStyleData", "ReorderState"]
    ordered = host.dispatches[0][0][2]
    assert list(ordered) == ["0", "1"]
    assert ordered["0"]["%c"]["%n"]["%nm"] == "is_hovered"
    assert ordered["0"]["%x"] == "State"
    assert ordered["1"]["%c"]["%n"]["%nm"] == "isnt_clickable"
    assert host.cache["styles"]["Primary"]["conditions"] == {
        "hover": "0",
        "not_clickable": "1",
    }


def test_delete_bulk_and_clear_remove_cache_only_after_successful_dispatch() -> None:
    styles = {
        "Text_body_": _style("Body", "Text"),
        "Text_caption_": _style("Caption", "Text"),
        "Text_default_": _style("Default", "Text", is_default=True),
    }
    host = _Host(styles)
    host.cache["styles"] = {
        "Body": {"id": "Text_body_", "type": "Text"},
        "Body alias": {"id": "Text_body_", "type": "Text"},
        "Caption": {"id": "Text_caption_", "type": "Text"},
        "Cached only": {"id": "Text_cached_", "type": "Text"},
    }
    service = _service(host)

    assert service.delete_style("Body", "text") is True
    assert [row[0] for row in host.dispatches[0]] == ["DeleteStyle", "IdToPathFixer"]
    assert set(host.cache["styles"]) == {"Caption", "Cached only"}

    assert service.delete_styles(pattern="caption|cached") is True
    assert [row[1][1] for row in host.dispatches[1][::2]] == [
        "Text_caption_",
        "Text_cached_",
    ]
    assert host.cache["styles"] == {}

    clear_host = _Host(styles)
    clear_host.cache["styles"]["Cached only"] = {"id": "Text_cached_", "type": "Text"}
    assert _service(clear_host).clear_custom_styles() is True
    deleted_ids = [row[1][1] for row in clear_host.dispatches[0][::2]]
    assert deleted_ids == ["Text_body_", "Text_caption_", "Text_cached_"]
    assert all("Text_default_" not in row[1] for row in clear_host.dispatches[0])

    failed = _Host(styles)
    failed.cache["styles"]["Body"] = {"id": "Text_body_", "type": "Text"}
    failed.fail_dispatch_at = 1
    assert _service(failed).delete_style("Body") is False
    assert "Body" in failed.cache["styles"]


def test_create_button_style_keeps_sdk_theme_builder_and_host_dry_run_semantics() -> None:
    host = _Host()

    assert _service(host).create_button_style(
        "Primary",
        '{"base":{"font_size":16},"hover":{"bg_color":"Brand"}}',
    ) is True
    assert [row[0] for row in host.dispatches[0]][:2] == ["Update index", "CreateStyle"]
    assert "NewStyleState" in [row[0] for row in host.dispatches[0]]
    assert host.cache["styles"]["Primary"] == {"id": "Button_bSTYLE", "type": "Button"}

    preview = _Host()
    preview.dry_run = True
    assert _service(preview).create_button_style("Preview", '{"base":{"font_size":16}}') is True
    assert preview.dispatches == []
    assert preview.cache == {"styles": {}}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, {}),
        ({"background_style": "image", "bg_color": "red"}, {"background_style": "image", "background_color_if_empty_image": "red"}),
        (
            {
                "background_style": "image",
                "background_color": "red",
                "background_color_if_empty_image": "blue",
            },
            {"background_style": "image", "background_color_if_empty_image": "blue"},
        ),
        ({"gradient_mid": "mid", "gradient_type": "radial"}, {"gradient_mid_color": "mid", "gradient_style": "radial"}),
        ({"map_type": "road", "map_style": "custom style"}, {"map_type": "ROADMAP", "map_style": "_custom"}),
        ({"map_type": "", "map_style": ""}, {}),
        ({"range_type": " SIMPLE ", "separator_width": "2"}, {"range_type": "simple", "separator_width": 2}),
        ({"range_type": "", "separator_width": "auto"}, {"separator_width": "auto"}),
        ({"grayout_color": "gray", "grayout_blur": "4"}, {"greyout_color": "gray", "greyout_blur": 4}),
        ({"greyout_color": "gray", "grayout_color": "drop"}, {"greyout_color": "gray"}),
        ({"greyout_blur": "auto", "grayout_blur": 2}, {"greyout_blur": "auto"}),
        (
            {"border_type": "independent", "radius_top_left": 8},
            {
                "border_type": "independent",
                "radius_top_left": 8,
                "radius_top_right": 0,
                "radius_bottom_right": 0,
                "radius_bottom_left": 0,
            },
        ),
        ({"border_type": "shared", "padding": 3, "padding_left": 5}, {"border_type": "shared", "padding_top": 3, "padding_bottom": 3, "padding_left": 5, "padding_right": 3}),
    ],
)
def test_normalize_kwargs_preserves_legacy_alias_and_validation_branches(
    raw: dict[str, Any] | None,
    expected: dict[str, Any],
) -> None:
    normalized = StyleDefinitionService.normalize_kwargs(raw)
    assert normalized == expected


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{", "Invalid states_json payload"),
        (["hover"], "entry #1 must be an object"),
        ([{"properties": {}}], "missing 'condition'"),
        ([{"condition": "hover", "properties": "red"}], "must include 'properties'"),
        (42, "must be a JSON object or array"),
    ],
)
def test_state_definition_normalization_rejects_each_malformed_shape(raw: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        StyleDefinitionService.normalize_state_definitions(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("is_hovered", "hover"),
        ("isn't clickable", "disabled"),
        ("actively pressed", "pressed"),
        ("keyboard focus ring", "focus"),
        ("not valid input", "invalid"),
        ("currently visible", "visible"),
        ("not currently visible", "not_visible"),
        ("fully hidden", "not_visible"),
        ("custom state", None),
    ],
)
def test_trigger_normalization_covers_exact_and_fuzzy_inputs(raw: str, expected: str | None) -> None:
    assert StyleDefinitionService.normalize_trigger_alias(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hover weaker than disabled", ["hover", "disabled"]),
        ("hover before disabled", ["hover", "disabled"]),
        ("hover / focus > disabled", ["hover", "focus", "disabled"]),
        ("hover, focus, disabled", ["hover", "focus", "disabled"]),
        ("", []),
        ("custom only", []),
    ],
)
def test_order_parser_covers_relation_sequence_fallback_and_empty_inputs(
    raw: str,
    expected: list[str],
) -> None:
    assert StyleDefinitionService.parse_reorder_order(raw) == expected


def test_create_validation_existing_and_property_match_branches() -> None:
    host = _Host({"Text_body_": _style("Body", "Text", {"%fs": 16})})
    service = _service(host)

    assert service.create_style("Missing", "", allow_property_match=False) is False
    assert service.create_style("Bad states", "Text", states_json="{") is False
    assert service.create_style("Body", "Text") is True
    assert host.dispatches == []
    assert service.create_style("Alias", "Text", font_size=16) is True
    assert [row[0] for row in host.dispatches[0]] == ["SetStyleData"]
    assert all(row[0] != "CreateStyle" for row in host.dispatches[0])

    host.fail_dispatch_at = 2
    assert service.create_style(
        "Body",
        "Text",
        default_style=True,
        allow_property_match=False,
    ) is False


def test_create_popup_states_and_post_create_failures_remain_false() -> None:
    host = _Host()
    service = _service(host)

    assert service.create_style(
        "Dialog",
        "Popup",
        allow_property_match=False,
        states={"hover": {"font_color": "Brand"}},
    ) is True
    assert host.dispatches[1][0][2] == "none"
    assert len(host.dispatches) == 5

    update_failure = _Host()
    update_failure.fail_dispatch_at = 2
    assert _service(update_failure).create_style(
        "Uploader",
        "FileInput",
        allow_property_match=False,
        font_weight="400",
    ) is False
    assert update_failure.cache["styles"]["Uploader"]["id"] == "FileInput_uploader_"

    cache_failure = _Host()
    cache_failure.fail_cache = "put"
    assert _service(cache_failure).create_style(
        "Remote",
        "Text",
        allow_property_match=False,
    ) is False


def test_update_validation_noop_dry_run_state_and_cache_failure_branches() -> None:
    host = _Host({"Text_body_": _style("Body", "Text", {"font_family": "Inter"})})
    service = _service(host)

    assert service.update_style_definition("Body", "Text", states_json="{") is False
    assert service.update_style_definition("Missing", "Text", font_size=12) is False
    assert service.update_style_definition("Body", "Text") is True
    assert service.update_style_definition(
        "Body",
        "Text",
        dry_run=True,
        font_face="var(--font_body_default):::regular",
    ) is True
    assert "font_family" not in host.discovery["styles"]["Text_body_"]["%p"]

    state_failure = _Host({"Text_body_": _style("Body", "Text")})
    assert _service(state_failure).update_style_definition(
        "Body",
        "Text",
        states={"": {"font_color": "red"}},
    ) is True

    cache_failure = _Host({"Text_body_": _style("Body", "Text")})
    cache_failure.fail_cache = "save"
    assert _service(cache_failure).update_style_definition("Body", "Text", font_size=18) is False


def test_rename_default_and_button_failure_branches() -> None:
    host = _Host()
    service = _service(host)
    assert service.rename_style("Text_body_", "Body 2", dry_run=True) is True
    assert service.set_default_style("Text", "Text_body_", dry_run=True) is True
    host.fail_dispatch_at = 1
    assert service.rename_style("Text_body_", "Body 2") is False

    assert service.create_button_style("Invalid", "{") is False
    assert service.create_button_style("Invalid", "[]") is False

    dispatch_failure = _Host()
    dispatch_failure.fail_dispatch_at = 1
    assert _service(dispatch_failure).create_button_style(
        "Primary",
        '{"base":{"font_color":"#ffffff"}}',
    ) is False

    existing = _Host({"Button_primary_": _style("Primary", "Button")})
    existing.fail_cache = "put"
    assert _service(existing).create_button_style("Primary", "{}") is False


def test_state_validation_existing_dry_run_and_each_staged_failure() -> None:
    missing = _Host()
    assert _service(missing).add_style_condition("Missing", "hover") is False

    host = _Host({"Button_primary_": _style("Primary", "Button")})
    service = _service(host)
    assert service.add_style_condition("Primary", "") is False
    assert service.add_style_condition("Primary", "+,") is False
    assert service.add_style_condition(
        "Primary",
        "hover",
        dry_run=True,
        font_color=False,
        border_width=None,
        opacity=0.5,
    ) is True
    assert host.dispatches == []

    existing_state = {
        "%x": "State",
        "%c": {"%n": {"%nm": "is_hovered"}},
        "%p": {"%fc": "red"},
    }
    existing = _Host(
        {"Button_primary_": _style("Primary", "Button", states={"old": existing_state})}
    )
    assert _service(existing).add_style_condition(
        "Primary",
        "hover",
        font_color="Danger",
    ) is True
    assert all(row[0] != "NewStyleState" for rows in existing.dispatches for row in rows)

    for fail_at in (1, 2, 3):
        failed = _Host({"Button_primary_": _style("Primary", "Button")})
        failed.fail_dispatch_at = fail_at
        assert _service(failed).add_style_condition(
            "Primary",
            "hover",
            index="new",
            font_color="Danger",
        ) is False
        assert failed.cache == {"styles": {}}


def test_condition_lookup_reorder_and_apply_state_error_branches() -> None:
    malformed = {"%x": "State", "%c": "bad", "%p": {}}
    focus = {"%x": "State", "%c": {"%n": {"%nm": "is_focused"}}, "%p": {}}
    host = _Host(
        {"Button_primary_": _style("Primary", "Button", states={"bad": malformed, "focus": focus})}
    )
    service = _service(host)
    assert service.find_style_condition_id("Button_primary_", "") is None
    assert service.find_style_condition_id("Button_primary_", "focus") == "focus"
    assert service.find_style_condition_id("Button_primary_", "hover") is None
    assert service.reorder_style_states("Missing", "hover") is False
    assert service.reorder_style_states("Primary", "custom") is False
    assert service.reorder_style_states("Primary", "focus", dry_run=True, prune_missing=True) is True
    assert host.dispatches == []

    dispatch_failure = _Host(
        {"Button_primary_": _style("Primary", "Button", states={"focus": focus})}
    )
    dispatch_failure.fail_dispatch_at = 1
    assert _service(dispatch_failure).reorder_style_states("Primary", "focus") is False

    cache_failure = _Host(
        {"Button_primary_": _style("Primary", "Button", states={"focus": focus})}
    )
    cache_failure.fail_cache = "save"
    assert _service(cache_failure).reorder_style_states("Primary", "focus") is False

    assert service.apply_state_definitions("Primary", [("", {})]) is False


def test_delete_validation_dry_run_default_regex_dispatch_and_cache_failures() -> None:
    empty = _Host()
    service = _service(empty)
    assert service.delete_style("Missing") is False
    assert service.delete_styles(names=["Missing"]) is False
    assert service.clear_custom_styles() is True

    host = _Host(
        {
            "Text_body_": _style("Body", "Text"),
            "Text_default_": _style("Default", "Text", is_default=True),
        }
    )
    service = _service(host)
    assert service.delete_style("Text_direct_", dry_run=True) is True
    assert service.delete_styles(pattern="[") is False
    assert service.delete_styles(names=["Missing"]) is False
    assert service.delete_styles(names=["Default"]) is False
    assert service.delete_styles(names=["Body"], dry_run=True) is True
    assert host.dispatches == []

    dispatch_failure = _Host({"Text_body_": _style("Body", "Text")})
    dispatch_failure.fail_dispatch_at = 1
    assert _service(dispatch_failure).delete_styles(names=["Body"]) is False

    cache_failure = _Host({"Text_body_": _style("Body", "Text")})
    cache_failure.cache["styles"]["Body"] = {"id": "Text_body_", "type": "Text"}
    cache_failure.fail_cache = "remove"
    assert _service(cache_failure).delete_style("Body") is False


def test_constructor_and_empty_plans_reject_invalid_inputs_without_side_effects() -> None:
    host = _Host()
    with pytest.raises(TypeError, match="resolve_color"):
        StyleDefinitionService(host, StyleReferenceResolver(host), object())
    assert StyleDefinitionService.normalize_state_definitions("") == []
    assert StyleDefinitionService.build_transition_intents("Text_body_", {}) == []
    assert _service(host).create_style("", "Text", allow_property_match=False) is False


def test_normalizers_preserve_blank_image_colors_and_nonstandard_style_values() -> None:
    assert StyleDefinitionService.normalize_kwargs(
        {
            "background_style": "image",
            "background_color": "",
            "bg_color": "red",
            "map_style": "vendor custom",
            "separator_style": " DASHED ",
            "border_type": "other",
        }
    ) == {
        "background_style": "image",
        "background_color_if_empty_image": "red",
        "map_style": "vendor_custom",
        "separator_style": "dashed",
        "border_type": "other",
    }
    assert StyleDefinitionService.normalize_trigger_alias("not actually clickable") == "disabled"
    assert StyleDefinitionService.normalize_trigger_alias("card hover state") == "hover"
    assert StyleDefinitionService.parse_reorder_order("make disabled the terminal state") == [
        "disabled"
    ]
    assert StyleDefinitionService.parse_reorder_order("custom stronger than hover") == ["hover"]


def test_existing_create_dry_run_and_update_failure_do_not_report_success() -> None:
    host = _Host({"Text_body_": _style("Body", "Text", {"%fs": 16})})
    service = _service(host)
    assert service.create_style(
        "Body",
        "Text",
        dry_run=True,
        allow_property_match=False,
    ) is True
    assert [event[0] for event in host.events] == ["hydrate"]

    failing = _Host({"Text_body_": _style("Body", "Text", {"%fs": 16})})
    failing.fail_dispatch_at = 1
    assert _service(failing).create_style(
        "Body",
        "Text",
        allow_property_match=False,
        font_size=18,
    ) is False
    assert failing.cache == {"styles": {}}


def test_create_file_style_without_typography_and_live_font_clear_preserve_properties() -> None:
    host = _Host()
    assert _service(host).create_style(
        "Upload",
        "FileInput",
        allow_property_match=False,
        background_style="none",
    ) is True
    assert all(row[1][-1] != "%b" for row in host.dispatches[1])

    update = _Host(
        {"Text_body_": _style("Body", "Text", {"font_family": "Inter", "%fs": 16})}
    )
    assert _service(update).update_style_definition(
        "Body",
        "Text",
        font_face="var(--font_body_default):::regular",
    ) is True
    assert "font_family" not in update.cache["styles"]["Body"]["%p"]


def test_button_theme_skips_non_object_states_and_uses_cached_style_id() -> None:
    host = _Host()
    host.cache["styles"]["Cached"] = {"id": "Button_cached_", "type": "Button"}
    assert _service(host).create_button_style(
        "Cached",
        '{"base":{"font_color":"var(--color_primary_default)"},"label":"ignored"}',
    ) is True
    assert all(row[0] != "CreateStyle" for row in host.dispatches[0])
    assert host.cache["styles"]["Cached"]["id"] == "Button_cached_"


def test_condition_lookup_uses_cached_states_and_recursive_compound_conditions() -> None:
    first = {
        "%x": "ThisElement",
        "%n": {
            "%x": "Message",
            "%nm": "is_hovered",
            "%n": {
                "%nm": "and_",
                "%a": {"%n": {"%nm": "is_focused"}},
            },
        },
    }
    host = _Host({"Button_primary_": _style("Primary", "Button")})
    host.cache["styles"]["Primary"] = {
        "id": "Button_primary_",
        "type": "Button",
        "%s": {"compound": {"%c": first, "%p": {}}},
    }
    service = _service(host)
    assert service.find_style_condition_id(
        "Button_primary_",
        [("hover", "and_"), ("focus", None)],
    ) == "compound"
    assert service.find_style_condition_id("Button_primary_", [("hover", None)]) is None


def test_reorder_reports_missing_or_unknown_states_and_prunes_unrequested_states() -> None:
    no_states = _Host({"Button_primary_": _style("Primary", "Button")})
    assert _service(no_states).reorder_style_states("Primary", "hover") is False

    malformed = _Host(
        {
            "Button_primary_": _style(
                "Primary",
                "Button",
                states={"bad": {"%c": "bad", "%p": {}}},
            )
        }
    )
    assert _service(malformed).reorder_style_states("Primary", "hover") is False

    hover = {"%c": {"%n": {"%nm": "is_hovered"}}, "%p": {}}
    focus = {"%c": {"%n": {"%nm": "is_focused"}}, "%p": {}}
    host = _Host(
        {"Button_primary_": _style("Primary", "Button", states={"h": hover, "f": focus})}
    )
    assert _service(host).reorder_style_states(
        "Primary",
        "hover",
        prune_missing=True,
    ) is True
    assert list(host.dispatches[0][0][2]) == ["0"]


def test_property_matching_rejects_wrong_types_generic_aliases_and_image_collisions() -> None:
    host = _Host(
        {
            "Group_card_": _style("Card", "Group", {"%fs": 16}),
            "Text_text_": _style("Text", "Text", {"%fs": 16}),
            "Image_content_": _style("Content", "Image", {"%fs": 16}),
            "Text_empty_": _style("Empty", "Text"),
        }
    )
    service = _service(host)
    assert service.create_style("Semantic", "Text", font_size=16) is True
    assert any(row[0] == "CreateStyle" for row in host.dispatches[0])

    image_host = _Host(
        {"Image_content_": _style("Content", "Image", {"%fs": 16})}
    )
    assert _service(image_host).create_style("Gallery / Hero", "Image", font_size=16) is True
    assert any(row[0] == "CreateStyle" for row in image_host.dispatches[0])


def test_property_matching_only_tolerates_missing_true_for_mobile_shadow_flag() -> None:
    shadow_host = _Host(
        {"Text_raised_existing_": _style("Raised Existing", "Text", {"%bs": "outset"})}
    )
    assert _service(shadow_host).create_style(
        "Raised",
        "Text",
        shadow_style="outset",
    ) is True
    assert all(row[0] != "CreateStyle" for rows in shadow_host.dispatches for row in rows)

    boolean_host = _Host(
        {"Text_plain_": _style("Plain", "Text", {"%fs": 16})}
    )
    assert _service(boolean_host).create_style(
        "Underlined",
        "Text",
        font_size=16,
        underline=True,
    ) is True
    assert any(row[0] == "CreateStyle" for row in boolean_host.dispatches[0])


def test_update_accepts_legacy_and_direct_ids_but_rejects_unknown_prefixes() -> None:
    legacy = _Host({"legacy": _style("Body", "Text")})
    assert _service(legacy).update_style_definition("Body", "Text", font_size=18) is True
    assert legacy.dispatches[0][0][1][1] == "legacy"

    direct = _Host()
    assert _service(direct).update_style_definition("Text_direct_", "Text", font_size=18) is True
    assert _service(direct).update_style_definition("Unknown_direct_", "Text", font_size=18) is False


def test_style_candidate_and_cache_cleanup_ignore_malformed_and_blank_aliases() -> None:
    host = _Host({"Text_body_": _style("Body", "Text")})
    host.discovery["styles"]["malformed"] = "bad"
    host.cache["styles"].update(
        {
            "Body": {"id": "Text_body_", "type": "Text"},
            "": {"id": "Text_body_", "type": "Text"},
            "Malformed": "bad",
        }
    )
    assert _service(host).delete_style("Body") is True
    assert "" in host.cache["styles"]
