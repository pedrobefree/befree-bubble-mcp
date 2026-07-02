import json

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.figma_bridge import sync_bridge_payload_file
from bubble_mcp.sessions.store import save_session, session_from_payload


def test_figma_bridge_dry_run_uses_aria_runtime(tmp_path, monkeypatch) -> None:
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
