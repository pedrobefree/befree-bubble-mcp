from pathlib import Path

from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
import bubble_mcp.harness.visual_bubble as visual_bubble
from bubble_mcp.harness.visual_bubble import (
    bubble_preview_version_segment,
    build_bubble_preview_url,
    capture_bubble_visual_snapshot,
)


def test_bubble_preview_version_segment_normalizes_common_versions() -> None:
    assert bubble_preview_version_segment("test") == "version-test"
    assert bubble_preview_version_segment("version-test") == "version-test"
    assert bubble_preview_version_segment("feature-one") == "version-feature-one"
    assert bubble_preview_version_segment("live") == ""


def test_build_bubble_preview_url_handles_page_version_and_query() -> None:
    assert build_bubble_preview_url(app_id="demo", app_version="test", page="index") == (
        "https://demo.bubbleapps.io/version-test"
    )
    assert build_bubble_preview_url(app_id="demo", app_version="test", page="mcp-01") == (
        "https://demo.bubbleapps.io/version-test/mcp-01"
    )
    assert build_bubble_preview_url(
        app_id="demo",
        app_version="live",
        page="pricing",
        public_base_url="https://app.example.com/",
        query={"debug": "true"},
    ) == "https://app.example.com/pricing?debug=true"


def test_capture_bubble_visual_snapshot_resolves_profile_and_delegates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="demo",
            profiles={
                "demo": BubbleProfile(
                    name="demo",
                    app_id="demo-app",
                    appname="demo-app",
                    app_version="test",
                )
            },
        )
    )
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls = []

    def fake_capture(source, **kwargs):
        calls.append({"source": source, **kwargs})
        return {"ok": True, "root": {"id": "hero"}, "nodes": [], "warnings": []}

    monkeypatch.setattr(visual_bubble, "capture_visual_snapshot", fake_capture)

    snapshot = capture_bubble_visual_snapshot(
        profile="demo",
        page="mcp-01",
        selector="#hero",
    )

    assert snapshot["ok"] is True
    assert snapshot["bubble"]["url"] == "https://demo-app.bubbleapps.io/version-test/mcp-01"
    assert calls[0]["source"] == "https://demo-app.bubbleapps.io/version-test/mcp-01"
    assert calls[0]["selector"] == "#hero"
    assert calls[0]["allow_raw_fallback"] is False
