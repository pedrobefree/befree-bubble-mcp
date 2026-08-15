from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.aria_runtime.bubble_sdk import PayloadBuilder
from bubble_mcp.aria_runtime.figma_bridge.transform_tokens import TokenTransformer
from bubble_mcp.aria_runtime.style_lifecycle.colors import ColorSnapshot, ColorTokenService
from bubble_mcp.aria_runtime.style_lifecycle.figma_import import FigmaTokenImportService
from bubble_mcp.aria_runtime.style_lifecycle.figma_import import (
    DefaultColorUpdate,
    FigmaTokenCounts,
    FigmaTokenPlan,
    FigmaTokenSyncResult,
    StyleDefinitionOperation,
)
from bubble_mcp.aria_runtime.style_lifecycle.fonts import FontSnapshot, FontTokenService


@dataclass
class ImportHost:
    discovery: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=lambda: {"colors": {}, "fonts": {}})
    appname: str = "figma-import-test"
    app_version: str = "version-stage"
    fail_phase: str | None = None
    fail_cache: bool = False
    events: list[tuple[Any, ...]] = field(default_factory=list)

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.discovery, self.cache

    def new_style_token_payload(self) -> PayloadBuilder:
        return PayloadBuilder(appname=self.appname, app_version=self.app_version)

    def dispatch_style_token_payload(self, payload: PayloadBuilder) -> None:
        phase = _payload_phase(payload)
        self.events.append(("dispatch", phase, payload.build()))
        if self.fail_phase == phase:
            raise RuntimeError(f"literal {phase} failure")
        client_safe = self.discovery.setdefault("settings", {}).setdefault("client_safe", {})
        for change in payload.changes:
            path = change["path_array"]
            if path[:3] != ["settings", "client_safe", path[2]]:
                continue
            setting = path[2]
            if len(path) == 3:
                client_safe[setting] = change["body"]
            else:
                current = client_safe.setdefault(setting, {})
                current[path[3]] = change["body"]

    def put_style_token_cache(self, kind: str, token_id: str, data: dict[str, Any]) -> None:
        self.events.append(("cache", kind, token_id))
        if self.fail_cache:
            raise RuntimeError("literal cache failure")
        self.cache.setdefault(kind, {})[token_id] = dict(data)

    def remove_style_token_cache(self, kind: str, token_id: str) -> None:
        self.cache.setdefault(kind, {}).pop(token_id, None)

    def clear_style_token_cache(self, kind: str) -> None:
        self.cache[kind] = {}

    def create_style(
        self,
        name: str,
        element_type: str,
        dry_run: bool = False,
        allow_property_match: bool = True,
        **properties: Any,
    ) -> bool:
        self.events.append(("style", name, element_type, dry_run, dict(properties)))
        if self.fail_phase == "styles-raise":
            raise RuntimeError("literal style exception")
        return self.fail_phase != "styles"


def _payload_phase(payload: PayloadBuilder) -> str:
    paths = [change.get("path_array", []) for change in payload.changes]
    if any(path[2:3] == ["font_tokens_user"] for path in paths):
        return "fonts"
    return "colors"


def _host() -> ImportHost:
    return ImportHost(
        discovery={
            "settings": {
                "client_safe": {
                    "font_tokens": {"default": "Inter"},
                    "font_tokens_user": {
                        "%d1": {
                            "fExisting": {
                                "%nm": "Existing",
                                "font_family": "Source Sans 3",
                                "order": 0,
                            }
                        }
                    },
                    "color_tokens": {
                        "primary": {"%d1": "rgba(1, 1, 1, 1)"},
                        "primary_contrast": {"%d1": "rgba(2, 2, 2, 1)"},
                        "surface": {"%d1": "rgba(3, 3, 3, 1)"},
                        "background": {"%d1": "rgba(4, 4, 4, 1)"},
                        "%3": {"%d1": "rgba(0, 0, 0, 1)"},
                    },
                    "color_tokens_user": {
                        "%d1": {
                            "cExisting": {
                                "%nm": "Existing Accent",
                                "rgba": "rgba(9, 9, 9, 1)",
                                "order": 0,
                            }
                        }
                    },
                }
            }
        }
    )


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "naming": {"separator": " ", "case": "title"},
                "filters": {
                    "include_color_paths": ["color.*"],
                    "exclude_color_paths": ["color.ignore.*"],
                    "include_typography_paths": ["typography.*"],
                },
                "default_color_mapping": {
                    "brand.600": "Primary",
                    "base.white": ["Primary Contrast", "Surface", "Background"],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _tokens(tmp_path: Path) -> Path:
    path = tmp_path / "tokens.json"
    path.write_text(
        json.dumps(
            {
                "color": {
                    "accent": {"500": {"type": "color", "value": "#123456"}},
                    "base": {"white": {"type": "color", "value": "#FFFFFF"}},
                    "brand": {"600": {"type": "color", "value": "#445566"}},
                    "ignore": {"100": {"type": "color", "value": "#ABCDEF"}},
                },
                "typography": {
                    "body": {
                        "regular": {
                            "type": "typography",
                            "value": {
                                "fontFamily": {"value": "Roboto"},
                                "fontSize": {"value": "16px"},
                                "fontWeight": {"value": "Regular"},
                                "lineHeight": {"value": "24px"},
                                "color": {"value": "#123456"},
                            },
                        },
                        "strong": {
                            "type": "typography",
                            "value": {
                                "fontFamily": "Roboto",
                                "fontSize": 16,
                                "fontWeight": "Semi Bold",
                                "color": "#123456",
                            },
                        },
                    },
                    "display": {
                        "large": {
                            "type": "typography",
                            "value": {
                                "fontFamily": "Inter",
                                "fontSize": 48,
                                "fontWeight": 700,
                                "color": "#445566",
                            },
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _service(
    host: ImportHost,
    *,
    max_bytes: int = 5_000_000,
    max_depth: int = 64,
    max_nodes: int = 100_000,
) -> FigmaTokenImportService:
    return FigmaTokenImportService(
        host,
        ColorTokenService(host),
        FontTokenService(host),
        transformer_factory=TokenTransformer,
        max_json_bytes=max_bytes,
        max_json_depth=max_depth,
        max_json_nodes=max_nodes,
    )


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{not-json", "valid JSON"),
        (json.dumps([{"type": "color", "value": "#000000"}]), "JSON object"),
        (json.dumps({"action": "sync_tokens", "content": []}), "content must be a JSON object"),
    ],
)
def test_bounded_loader_rejects_malformed_and_invalid_shapes(
    tmp_path: Path,
    contents: str,
    message: str,
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _service(_host()).load_document(path)


def test_bounded_loader_rejects_oversized_and_deep_documents(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_text(json.dumps({"value": "x" * 100}), encoding="utf-8")
    deep = tmp_path / "deep.json"
    deep.write_text(json.dumps({"a": {"b": {"c": {"d": {}}}}}), encoding="utf-8")

    with pytest.raises(ValueError, match="maximum size"):
        _service(_host(), max_bytes=32).load_document(oversized)
    with pytest.raises(ValueError, match="maximum depth"):
        _service(_host(), max_depth=4).load_document(deep)


def test_bounded_loader_rejects_missing_growing_and_node_heavy_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(_host(), max_bytes=32, max_nodes=3)
    with pytest.raises(ValueError, match="Unable to read"):
        service.load_document(tmp_path / "missing.json")

    growing = tmp_path / "growing.json"
    growing.write_text("{}", encoding="utf-8")
    read_sizes: list[int] = []

    class GrowingStream(BytesIO):
        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            if size != 33:
                raise AssertionError("Figma token reads must be capped at max_json_bytes + 1")
            return super().read(size)

    monkeypatch.setattr(
        Path,
        "open",
        lambda _self, *args, **kwargs: GrowingStream(b"{" + b" " * 40 + b"}"),
    )
    with pytest.raises(ValueError, match="maximum size"):
        service.load_document(growing)
    assert read_sizes == [33]
    monkeypatch.undo()

    node_heavy = tmp_path / "nodes.json"
    node_heavy.write_text(json.dumps({"a": [1, 2, 3]}), encoding="utf-8")
    with pytest.raises(ValueError, match="maximum node count"):
        service.load_document(node_heavy)


def test_bounded_loader_rejects_non_regular_inputs(tmp_path: Path) -> None:
    token_directory = tmp_path / "tokens-directory"
    token_directory.mkdir()

    with pytest.raises(ValueError, match="regular file"):
        _service(_host()).load_document(token_directory)


def test_bounded_loader_extracts_valid_bridge_content(tmp_path: Path) -> None:
    path = tmp_path / "bridge.json"
    path.write_text(
        json.dumps({"action": "sync_tokens", "content": {"color": {}}}),
        encoding="utf-8",
    )

    assert _service(_host()).load_document(path) == {"color": {}}


def test_plan_is_deterministic_deduplicated_filtered_and_fonts_colors_styles_ordered(tmp_path: Path) -> None:
    service = _service(_host())

    first = service.plan(_tokens(tmp_path), config_path=_config(tmp_path))
    second = service.plan(_tokens(tmp_path), config_path=_config(tmp_path))

    assert first == second
    assert first.phases == ("fonts", "colors", "styles")
    assert first.counts.as_dict() == {
        "fonts": 1,
        "created": 1,
        "updated": 4,
        "skipped": 1,
        "styles": 3,
    }
    assert first.font_map is not None
    assert [entry["font_family"] for entry in first.font_map.values() if isinstance(entry, dict)] == [
        "Source Sans 3",
        "Roboto",
    ]
    assert first.color_map is not None
    imported_names = [entry.get("%nm") for entry in first.color_map.values() if isinstance(entry, dict)]
    assert imported_names.count("Accent 500") == 1
    assert "Ignore 100" not in imported_names
    assert [update.token_id for update in first.default_color_updates] == [
        "background",
        "primary_contrast",
        "surface",
        "primary",
    ]
    assert [style.name for style in first.styles] == ["Body Regular", "Body Strong", "Display Large"]


def test_plan_honors_type_base_and_style_filters(tmp_path: Path) -> None:
    plan = _service(_host()).plan(
        _tokens(tmp_path),
        config_path=_config(tmp_path),
        types="color,style",
        color_bases="brand",
        filter_text="strong",
    )

    assert plan.font_map is None
    assert plan.color_map is None
    assert [update.token_id for update in plan.default_color_updates] == ["primary"]
    assert [style.name for style in plan.styles] == ["Body Strong"]
    assert plan.phases == ("colors", "styles")


def test_dry_run_returns_complete_payloads_without_dispatch_cache_or_style_side_effects(tmp_path: Path) -> None:
    host = _host()
    service = _service(host)
    before_discovery = json.dumps(host.discovery, sort_keys=True)
    before_cache = json.dumps(host.cache, sort_keys=True)

    result = service.sync(_tokens(tmp_path), config_path=_config(tmp_path), dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert [payload["phase"] for payload in result.payloads] == [
        "fonts",
        "colors",
        "styles",
        "styles",
        "styles",
    ]
    assert result.applied_counts == {"fonts": 0, "colors": 0, "styles": 0}
    assert host.events == []
    assert json.dumps(host.discovery, sort_keys=True) == before_discovery
    assert json.dumps(host.cache, sort_keys=True) == before_cache
    assert "var(--color_True_default)" not in json.dumps(result.as_dict(), sort_keys=True)
    style_payload = next(payload for payload in result.payloads if payload["phase"] == "styles")
    assert style_payload["properties"]["font_color"].startswith("var(--color_b")
    assert style_payload["properties"]["font_face"].startswith("var(--font_b")


def test_apply_groups_token_maps_once_then_applies_styles_and_is_idempotent(tmp_path: Path) -> None:
    host = _host()
    service = _service(host)

    result = service.sync(_tokens(tmp_path), config_path=_config(tmp_path), dry_run=False)

    assert result.ok is True
    assert [event[0:2] for event in host.events if event[0] in {"dispatch", "style"}] == [
        ("dispatch", "fonts"),
        ("dispatch", "colors"),
        ("style", "Body Regular"),
        ("style", "Body Strong"),
        ("style", "Display Large"),
    ]
    assert sum(
        path[2] == "font_tokens_user"
        for event in host.events
        if event[0] == "dispatch"
        for path in (change["path_array"] for change in event[2]["changes"])
    ) == 1
    assert sum(
        path[2] == "color_tokens_user"
        for event in host.events
        if event[0] == "dispatch"
        for path in (change["path_array"] for change in event[2]["changes"])
    ) == 1

    host.events.clear()
    repeated = service.sync(_tokens(tmp_path), config_path=_config(tmp_path), types="font,color", dry_run=False)

    assert repeated.ok is True
    assert repeated.counts.fonts == 0
    assert repeated.counts.created == 0
    assert repeated.counts.updated == 0
    assert repeated.counts.skipped == 7
    assert not any(event[0] == "dispatch" for event in host.events)


def test_partial_failure_reports_applied_counts_and_stops_later_phases(tmp_path: Path) -> None:
    host = _host()
    host.fail_phase = "colors"

    result = _service(host).sync(_tokens(tmp_path), config_path=_config(tmp_path), dry_run=False)

    assert result.ok is False
    assert result.applied_counts == {"fonts": 1, "colors": 0, "styles": 0}
    assert result.errors == ("colors: literal colors failure",)
    assert not any(event[0] == "style" for event in host.events)


def test_later_style_failure_reports_each_applied_custom_color_mutation(tmp_path: Path) -> None:
    token_path = tmp_path / "multiple-custom-colors.json"
    token_path.write_text(
        json.dumps(
            {
                "color": {
                    "brand": {
                        "100": {"type": "color", "value": "#111111"},
                        "200": {"type": "color", "value": "#222222"},
                        "300": {"type": "color", "value": "#333333"},
                    }
                },
                "typography": {
                    "body": {
                        "type": "typography",
                        "value": {"fontFamily": "Inter", "fontSize": 16},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "multiple-custom-colors-config.json"
    config_path.write_text(
        json.dumps(
            {
                "filters": {
                    "include_color_paths": ["color.*"],
                    "include_typography_paths": ["typography.*"],
                }
            }
        ),
        encoding="utf-8",
    )
    host = _host()
    host.fail_phase = "styles"

    result = _service(host).sync(
        token_path,
        config_path=str(config_path),
        types="color,style",
    )

    assert result.ok is False
    assert result.counts.created == 3
    assert result.applied_counts == {"fonts": 0, "colors": 3, "styles": 0}
    color_dispatches = [event for event in host.events if event[0:2] == ("dispatch", "colors")]
    assert len(color_dispatches) == 1
    assert result.errors == ("styles[0] Body: style definition returned false",)


def test_planning_cache_and_style_failures_are_structured(tmp_path: Path) -> None:
    planning = _service(_host()).sync(
        _tokens(tmp_path),
        config_path=_config(tmp_path),
        types="unsupported",
    )
    assert planning.ok is False
    assert planning.errors[0].startswith("planning: Unsupported Figma token types")

    cache_host = _host()
    cache_host.fail_cache = True
    cached = _service(cache_host).sync(
        _tokens(tmp_path),
        config_path=_config(tmp_path),
        types="font",
    )
    assert cached.ok is True
    assert cached.warnings == ("fonts cache: literal cache failure",)

    for failure, detail in (
        ("styles", "style definition returned false"),
        ("styles-raise", "literal style exception"),
    ):
        style_host = _host()
        style_host.fail_phase = failure
        failed = _service(style_host).sync(
            _tokens(tmp_path),
            config_path=_config(tmp_path),
            types="style",
        )
        assert failed.ok is False
        assert detail in failed.errors[0]


def test_custom_color_updates_and_duplicate_targets_are_planned_once(tmp_path: Path) -> None:
    token_path = tmp_path / "custom.json"
    token_path.write_text(
        json.dumps(
            {
                "color": {
                    "existing": {"accent": {"type": "color", "value": "#010203"}},
                    "alias": {"one": {"type": "color", "value": "#111111"}},
                    "alias_two": {"one": {"type": "color", "value": "#222222"}},
                }
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "custom-config.json"
    config_path.write_text(
        json.dumps(
            {
                "filters": {"include_color_paths": ["color.*"]},
                "default_color_mapping": {"alias.one": "Primary", "alias_two.one": "Primary"},
            }
        ),
        encoding="utf-8",
    )

    plan = _service(_host()).plan(token_path, config_path=str(config_path))

    assert plan.counts.updated == 2
    assert len(plan.default_color_updates) == 1
    assert plan.color_map is not None
    assert plan.color_map["cExisting"]["rgba"] == "rgba(1, 2, 3, 1)"


def test_plan_helpers_cover_empty_optional_and_collision_boundaries(tmp_path: Path) -> None:
    service = _service(_host())
    transformer = TokenTransformer(str(_config(tmp_path)))
    empty = FigmaTokenPlan(None, (), (), None, (), (), FigmaTokenCounts())
    only_color = FigmaTokenPlan(
        None,
        (),
        (DefaultColorUpdate("primary", "rgba(1, 2, 3, 1)"),),
        None,
        (),
        (),
        FigmaTokenCounts(updated=1),
    )
    only_style = FigmaTokenPlan(
        None,
        (),
        (),
        None,
        (),
        (StyleDefinitionOperation("Body", "Text", {}),),
        FigmaTokenCounts(styles=1),
    )
    assert empty.phases == ()
    assert only_color.phases == ("colors",)
    assert only_style.phases == ("styles",)

    no_font_snapshot = FontSnapshot(
        app_font="not set",
        custom={
            "deleted": {"%nm": "Gone", "font_family": "Gone", "%del": True},
            "blank": {"%nm": "", "font_family": "", "%del": False},
        },
        wire_custom={},
    )
    font_plan = service._plan_fonts(
        [{"value": ""}, {"value": {"value": "Mono"}}],
        no_font_snapshot,
        include=True,
    )
    assert font_plan[3:] == (1, 0)

    color_snapshot = ColorSnapshot(
        defaults={"primary": ""},
        custom={
            "gone": {"%nm": "Gone", "rgba": "rgba(1, 1, 1, 1)", "%del": True},
            "blank": {"%nm": "Blank", "rgba": "", "%del": False},
        },
        wire_custom={},
    )
    assert service._existing_color_variables(color_snapshot, transformer) == {}
    assert service._find_color(color_snapshot, "Gone", prefer_default=False) is None
    assert service._plan_colors([], color_snapshot, transformer, include=False, bases=(), all_tokens=False)[0:3] == (
        (),
        None,
        (),
    )

    first_id = service._stable_token_id("font", "Collision", set())
    assert service._stable_token_id("font", "Collision", {first_id}) != first_id
    assert service._next_order({"bad": {"order": "not-a-number"}}) == 1
    assert service._font_size(None) is None
    assert service._font_size("invalid") is None
    assert service._font_size("12.5px") == 12.5
    assert service._line_height(None, 16) is None
    assert service._line_height("120%", 16) == 1.2
    assert service._line_height(1.5, 16) == 1.5
    assert service._line_height(24, None) is None
    assert service._line_height("invalid", 16) is None


def test_stable_token_id_fails_explicitly_when_suffix_namespace_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeterministicDigest:
        def __init__(self, attempt: int) -> None:
            self._attempt = attempt

        def hexdigest(self) -> str:
            return f"{self._attempt:04x}" + ("0" * 60)

    def bounded_sha256(seed: bytes) -> DeterministicDigest:
        attempt = int(seed.rsplit(b":", 1)[1])
        if attempt >= 16**4:
            raise AssertionError("searched past the finite four-hex suffix namespace")
        return DeterministicDigest(attempt)

    monkeypatch.setattr(
        "bubble_mcp.aria_runtime.style_lifecycle.figma_import.hashlib.sha256",
        bounded_sha256,
    )
    used_ids = {f"b{suffix:04x}" for suffix in range(16**4)}

    with pytest.raises(RuntimeError, match="deterministic token ID namespace exhausted"):
        _service(_host())._stable_token_id("font", "Collision", used_ids)


def test_list_options_uses_the_same_bounded_document_and_transformer(tmp_path: Path) -> None:
    result = _service(_host()).list_options(_tokens(tmp_path), config_path=_config(tmp_path))

    assert result == {"color": ["accent", "base", "brand", "ignore"], "style": ["body", "display"]}


def test_bubble_cli_boolean_facade_preserves_result_and_never_mutates_sys_path_from_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI

    calls: list[tuple[str, dict[str, Any]]] = []
    structured = FigmaTokenSyncResult(
        ok=True,
        dry_run=True,
        counts=FigmaTokenCounts(fonts=1, styles=2),
        applied_counts={"fonts": 0, "colors": 0, "styles": 0},
        payloads=({"phase": "fonts", "payload": {"changes": []}},),
    )

    class FakeImport:
        def sync(self, tokens_path: str, **kwargs: Any) -> FigmaTokenSyncResult:
            calls.append((tokens_path, dict(kwargs)))
            return structured

        def list_options(self, tokens_path: str, **kwargs: Any) -> dict[str, list[str]]:
            calls.append((tokens_path, dict(kwargs)))
            return {"color": ["brand"], "style": ["body"]}

    cli = BubbleCLI.__new__(BubbleCLI)
    cli._style_lifecycle = type("Lifecycle", (), {"figma_import": FakeImport()})()
    monkeypatch.chdir(tmp_path)
    before = list(__import__("sys").path)

    assert cli.sync_figma_tokens(
        "tokens.json",
        config_path="config.json",
        dry_run=True,
        types="font,style",
        filter="body",
    ) is True
    assert cli._last_figma_token_sync_result == structured.as_dict()
    assert calls[-1][1]["filter_text"] == "body"
    assert list(__import__("sys").path) == before

    assert cli.sync_figma_tokens("tokens.json", config_path="config.json", list_options=True) is True
    assert cli._last_figma_token_sync_result["groups"] == {"color": ["brand"], "style": ["body"]}
    assert "COLOR BASES" in capsys.readouterr().out
