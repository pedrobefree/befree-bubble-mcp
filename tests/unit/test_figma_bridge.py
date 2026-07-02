import json

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.figma_bridge import sync_bridge_payload_file
from bubble_mcp.sessions.store import save_session, session_from_payload


def test_figma_bridge_dry_run_builds_reusable_payloads(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
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
    assert result["executed"] is False
    assert result["import_mode"] == "reusable"
    assert result["rendered_nodes"] == 2
    root_payload = result["results"][0]["payload"]
    assert root_payload["changes"][1]["path_array"][0] == "%ed"
    assert root_payload["changes"][1]["body"]["%x"] == "CustomDefinition"
    assert root_payload["changes"][1]["body"]["%nm"] == "mcp_pricing"
    assert root_payload["changes"][1]["body"]["%p"]["custom_element_platform"] == "web"
    text_payload = result["results"][1]["payload"]
    assert text_payload["changes"][0]["body"].startswith("%ed.")
    assert text_payload["changes"][1]["body"]["%x"] == "Text"
