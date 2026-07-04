from pathlib import Path

from bubble_mcp.harness.visual import compare_visual_snapshots
from bubble_mcp.harness.visual_capture import capture_visual_snapshot


FIXTURE = Path("tests/fixtures/html/hero.html")


def test_capture_visual_snapshot_from_raw_html_file() -> None:
    snapshot = capture_visual_snapshot(
        str(FIXTURE),
        selector="#hero",
        rendered_html=False,
    )

    assert snapshot["ok"] is True
    assert snapshot["rendered"] is False
    assert snapshot["root"]["id"] == "hero"
    assert any("The best landing page" in node.get("text", "") for node in snapshot["nodes"])
    assert any(node.get("type") == "image" for node in snapshot["nodes"])


def test_capture_visual_snapshot_can_write_output(tmp_path: Path) -> None:
    output = tmp_path / "hero-snapshot.json"
    snapshot = capture_visual_snapshot(
        str(FIXTURE),
        selector="#hero",
        rendered_html=False,
        output=output,
    )

    assert snapshot["output"] == str(output)
    assert output.exists()


def test_captured_snapshot_compares_against_itself() -> None:
    snapshot = capture_visual_snapshot(
        str(FIXTURE),
        selector="#hero",
        rendered_html=False,
    )

    report = compare_visual_snapshots(snapshot, snapshot, require_images=True)

    assert report["ok"] is True
    assert report["summary"]["reference_text_count"] > 0
    assert report["summary"]["reference_image_count"] == 1
