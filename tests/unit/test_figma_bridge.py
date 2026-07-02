import json
from types import SimpleNamespace

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.figma_bridge import _prune_stale_style_cache_for_bubble_file, sync_bridge_payload_file
from bubble_mcp.sessions.store import save_session, session_from_payload


def _configure_smoke_profile(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    bubble_file = config_dir / "contexts" / "smoke" / "synthetic-app.bubble"
    bubble_file.parent.mkdir(parents=True, exist_ok=True)
    bubble_file.write_text(
        json.dumps(
            {
                "pages": {
                    "index": {
                        "id": "index",
                        "name": "index",
                        "type": "Page",
                        "properties": {
                            "element_type": "Page",
                            "default_width": 1200,
                            "height": 800,
                        },
                        "elements": {},
                    }
                },
                "element_definitions": {},
                "styles": {},
                "_index": {"id_to_path": {"index": "pages.index"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(config_dir))
    save_settings(
        BubbleMcpSettings(
            config_dir=config_dir,
            default_profile="smoke",
            profiles={
                "smoke": BubbleProfile(
                    name="smoke",
                    app_id="synthetic-app",
                    appname="synthetic-app",
                    app_version="test",
                    app_json_path=str(bubble_file),
                )
            },
        )
    )
    save_session(
        "smoke",
        session_from_payload(
            {
                "appId": "synthetic-app",
                "appVersion": "test",
                "headers": {"cookie": "sid=secret"},
            }
        ),
    )


def test_figma_bridge_dry_run_uses_aria_runtime(tmp_path, monkeypatch) -> None:
    _configure_smoke_profile(tmp_path, monkeypatch)
    bridge_payload = {
        "action": "sync_component",
        "meta": {
            "profile": "smoke",
            "dry_run": True,
            "import_mode": "reusable",
            "component_name": "mcp-pricing",
            "element_type": "Group",
        },
        "content": {
            "id": "1:1",
            "name": "Pricing card",
            "type": "INSTANCE",
            "width": 384,
            "height": 562,
            "layout": {"mode": "VERTICAL"},
            "children": [
                {"id": "1:2", "name": "Price", "type": "TEXT", "characters": "$10/mth"},
                {"id": "1:3", "name": "CTA Button", "type": "FRAME", "children": []},
            ],
        },
    }
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(bridge_payload), encoding="utf-8")

    result = sync_bridge_payload_file(payload_path)

    assert result["ok"] is True
    assert result["engine"] == "aria_runtime"
    assert result["executed"] is False
    assert result["import_mode"] == "reusable"
    assert result["component_name"] == "mcp_pricing"
    assert "Syncing component: mcp_pricing" in result["logs"]
    assert "Creating Reusable 'mcp_pricing'" in result["logs"]


def test_figma_bridge_preserves_auto_layout_frame_min_height(tmp_path, monkeypatch) -> None:
    _configure_smoke_profile(tmp_path, monkeypatch)
    writes = []

    class FakeBubbleEditorClient:
        def write(self, payload, _session, dry_run=False):
            writes.append(payload)
            return {"ok": True, "status": 200, "dry_run": dry_run}

    monkeypatch.setattr("bubble_mcp.figma_bridge.BubbleEditorClient", FakeBubbleEditorClient)
    bridge_payload = {
        "action": "sync_component",
        "meta": {
            "profile": "smoke",
            "dry_run": False,
            "import_mode": "reusable",
            "component_name": "mcp-pricing",
            "element_type": "Group",
        },
        "content": {
            "id": "1:root",
            "name": "Pricing card",
            "type": "INSTANCE",
            "width": 384,
            "height": 562,
            "layout": {
                "mode": "VERTICAL",
                "primarySizing": "AUTO",
                "counterSizing": "FIXED",
                "primaryAlign": "MIN",
                "counterAlign": "MIN",
                "gap": 0,
                "padding": {"top": 0, "right": 0, "bottom": 0, "left": 0},
            },
            "children": [
                {
                    "id": "1:items",
                    "name": "Check items",
                    "type": "FRAME",
                    "width": 320,
                    "height": 184,
                    "x": 32,
                    "y": 32,
                    "layout": {
                        "mode": "VERTICAL",
                        "primarySizing": "AUTO",
                        "counterSizing": "FIXED",
                        "primaryAlign": "MIN",
                        "counterAlign": "MIN",
                        "gap": 16,
                        "padding": {"top": 0, "right": 0, "bottom": 0, "left": 0},
                    },
                    "children": [
                        {
                            "id": "1:row-a",
                            "name": "Feature row A",
                            "type": "FRAME",
                            "width": 320,
                            "height": 24,
                            "x": 0,
                            "y": 0,
                            "layout": {"mode": "HORIZONTAL", "gap": 12},
                            "children": [
                                {"id": "1:text-a", "name": "Text", "type": "TEXT", "text_content": "Feature A", "width": 284, "height": 24, "x": 36, "y": 0}
                            ],
                        },
                        {
                            "id": "1:row-b",
                            "name": "Feature row B",
                            "type": "FRAME",
                            "width": 320,
                            "height": 24,
                            "x": 0,
                            "y": 40,
                            "layout": {"mode": "HORIZONTAL", "gap": 12},
                            "children": [
                                {"id": "1:text-b", "name": "Text", "type": "TEXT", "text_content": "Feature B", "width": 284, "height": 24, "x": 36, "y": 0}
                            ],
                        },
                    ],
                }
            ],
        },
    }
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(bridge_payload), encoding="utf-8")

    result = sync_bridge_payload_file(payload_path)

    assert result["ok"] is True
    group_bodies = [
        change["body"]
        for payload in writes
        for change in payload.get("changes", [])
        if isinstance(change.get("body"), dict) and change["body"].get("%x") == "Group"
    ]
    check_items = next(body for body in group_bodies if body.get("%dn") == "Check items")
    assert check_items["%p"]["row_gap"] == 16
    assert check_items["%p"]["use_gap"] is True
    assert check_items["%p"]["min_height_css"] == "184px"
    assert check_items["%p"]["max_height_css"] == "184px"
    assert check_items["%p"]["fit_height"] is False
    assert check_items["%p"]["fixed_height"] is True
    assert check_items["%p"]["single_height"] is True
    assert any(
        change.get("path_array", [])[-2:] == ["%p", "fit_height"] and change.get("body") is True
        for payload in writes
        for change in payload.get("changes", [])
    )


def test_figma_bridge_routes_style_sync_to_style_runtime(tmp_path, monkeypatch) -> None:
    _configure_smoke_profile(tmp_path, monkeypatch)
    calls = []

    class FakePayloadBuilder:
        def send_to_webhook(self, _url):
            return {"ok": True}

    class FakeBubbleSdk:
        PayloadBuilder = FakePayloadBuilder

    class FakeBubbleCliModule:
        inquirer = None

        class BubbleCLI:
            def __init__(self, **kwargs):
                calls.append(("init", kwargs))

            def sync_component(self, **_kwargs):
                raise AssertionError("style sync must not use component sync")

            def sync_figma_style(self, **kwargs):
                calls.append(("style", kwargs))
                return kwargs.get("style_name")

    monkeypatch.setattr(
        "bubble_mcp.figma_bridge._load_aria_runtime_modules",
        lambda: (FakeBubbleCliModule, FakeBubbleSdk),
    )
    monkeypatch.setattr(
        "bubble_mcp.figma_bridge.detect_project_context",
        lambda **_kwargs: SimpleNamespace(context_path=tmp_path / "config" / "contexts" / "smoke" / "synthetic-app-context.json"),
    )
    bridge_payload = {
        "action": "sync_component",
        "meta": {
            "profile": "smoke",
            "dry_run": False,
            "sync_type": "style",
            "style_name": "Button / Primary / lg",
            "style_type": "Button",
            "element_type": "",
            "style_state": "Hover",
            "text_alignment": "center",
            "style_default": True,
        },
        "content": {
            "id": "1:button",
            "name": "Size=lg, Hierarchy=Primary, State=Hover, Icon only=False",
            "type": "COMPONENT",
            "width": 177,
            "height": 44,
            "layout": {"mode": "HORIZONTAL"},
            "children": [],
        },
    }
    payload_path = tmp_path / "style-payload.json"
    payload_path.write_text(json.dumps(bridge_payload), encoding="utf-8")

    result = sync_bridge_payload_file(payload_path)

    assert result["ok"] is True
    assert result["action"] == "sync_style"
    style_call = next(call for name, call in calls if name == "style")
    assert style_call["bridge_file"] == str(payload_path)
    assert style_call["style_name"] == "Button / Primary / lg"
    assert style_call["element_type"] == "Button"
    assert style_call["state"] == "Hover"
    assert style_call["text_alignment"] == "center"
    assert style_call["default_style"] is True


def test_figma_bridge_prunes_stale_style_cli_cache(tmp_path) -> None:
    bubble_file = tmp_path / "app.bubble"
    bubble_file.write_text(
        json.dumps(
            {
                "styles": {
                    "Button_existing_": {"%d": "Existing", "%x": "Button", "%p": {}},
                }
            }
        ),
        encoding="utf-8",
    )
    cache_file = tmp_path / ".bubble_cli_cache.json"
    cache_file.write_text(
        json.dumps(
            {
                "styles": {
                    "Existing": {"id": "Button_existing_", "type": "Button"},
                    "Ghost": {"id": "Button_ghost_", "type": "Button"},
                },
                "colors": {},
                "fonts": {},
            }
        ),
        encoding="utf-8",
    )

    removed = _prune_stale_style_cache_for_bubble_file(bubble_file)

    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    assert removed == ["Ghost"]
    assert "Existing" in cache["styles"]
    assert "Ghost" not in cache["styles"]
