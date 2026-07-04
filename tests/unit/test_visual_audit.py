from __future__ import annotations

import base64
from pathlib import Path

import bubble_mcp.harness.visual_audit as visual_audit
from bubble_mcp.harness.visual_audit import audit_visual_from_inputs, build_screenshot_llm_review


FIXTURES = Path("tests/fixtures/visual-snapshots")


def test_visual_audit_returns_actionable_repair_plan() -> None:
    result = audit_visual_from_inputs(
        {
            "reference": str(FIXTURES / "hero-reference.json"),
            "actual": str(FIXTURES / "hero-actual-bad.json"),
            "profile": "smoke",
            "context": "mcp-01",
            "parent": "gp_home",
            "app_id": "demo-app",
            "require_images": True,
        }
    )

    assert result["ok"] is False
    codes = {issue["code"] for issue in result["issues"]}
    assert "gradient_direction_mismatch" in codes
    assert "root_max_width_drift" in codes
    assert "font_family_mismatch" in codes
    assert "image_width_drift" in codes
    assert result["repair_plan"]["executable"] is True
    steps = result["repair_plan"]["plan"]["steps"]
    assert any(step["tool_name"] == "update_text_element" for step in steps)
    assert any(step["tool_name"] == "update_image_element" for step in steps)
    assert any(step["tool_name"] == "update_layout" for step in steps)
    assert any(step["tool_name"] == "update_group" for step in steps)
    assert all(step["args"]["context"] == "mcp-01" for step in steps)


def test_visual_audit_can_execute_generated_plan(monkeypatch) -> None:
    calls = []

    def fake_execute_plan(plan, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"plan": plan, "kwargs": kwargs})
        return {"ok": True, "executed": True, "step_count": len(plan["steps"])}

    monkeypatch.setattr(visual_audit, "execute_plan", fake_execute_plan)
    result = audit_visual_from_inputs(
        {
            "reference": str(FIXTURES / "hero-reference.json"),
            "actual": str(FIXTURES / "hero-actual-bad.json"),
            "profile": "smoke",
            "context": "mcp-01",
            "parent": "gp_home",
            "app_id": "demo-app",
            "execute": True,
            "require_images": True,
        }
    )

    assert result["ok"] is True
    assert result["execution"]["executed"] is True
    assert calls[0]["kwargs"]["compile_missing"] is True
    assert calls[0]["kwargs"]["profile"] == "smoke"


def test_screenshot_review_payload_is_llm_ready(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    actual = tmp_path / "actual.png"
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/az8hM8AAAAASUVORK5CYII="
    )
    reference.write_bytes(png_bytes)
    actual.write_bytes(png_bytes)

    review = build_screenshot_llm_review(
        reference_screenshot=reference,
        actual_screenshot=actual,
        task="Compare typography and image sizing.",
    )

    assert review["available"] is True
    assert review["requires_llm"] is True
    assert len(review["images"]) == 2
    assert review["images"][0]["mime_type"] == "image/png"
    assert review["images"][0]["base64"]
    assert "strict JSON" in review["prompt"]


def test_visual_audit_accepts_screenshots_without_structured_snapshots(tmp_path: Path) -> None:
    reference = tmp_path / "reference.png"
    actual = tmp_path / "actual.png"
    reference.write_bytes(b"fake-image")
    actual.write_bytes(b"fake-image")

    result = audit_visual_from_inputs(
        {
            "reference_screenshot": str(reference),
            "actual_screenshot": str(actual),
            "screenshot_task": "Find layout regressions.",
        }
    )

    assert result["ok"] is True
    assert result["repair_plan"]["executable"] is False
    assert result["llm_screenshot_review"]["available"] is True
