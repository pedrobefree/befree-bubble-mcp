from pathlib import Path

from bubble_mcp.harness.visual import compare_visual_snapshot_files


FIXTURES = Path("tests/fixtures/visual-snapshots")


def test_visual_compare_accepts_within_tolerance_snapshot() -> None:
    report = compare_visual_snapshot_files(
        FIXTURES / "hero-reference.json",
        FIXTURES / "hero-actual-ok.json",
        require_images=True,
    )

    assert report["ok"] is True
    assert report["score"] == 1.0
    assert report["summary"]["reference_image_count"] == 1
    assert report["issues"] == []


def test_visual_compare_reports_layout_style_and_image_drift() -> None:
    report = compare_visual_snapshot_files(
        FIXTURES / "hero-reference.json",
        FIXTURES / "hero-actual-bad.json",
        require_images=True,
    )

    assert report["ok"] is False
    rendered_issues = "\n".join(report["issues"])
    assert "gradient" in rendered_issues
    assert "max_width" in rendered_issues
    assert "font_family" in rendered_issues
    assert "image[0].width" in rendered_issues
