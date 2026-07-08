from pathlib import Path

import pytest

from bubble_mcp.frameworks.workspace import detect_framework_workspace, sync_artifacts_to_workspace


def test_detect_framework_workspace_identifies_bmad(tmp_path: Path) -> None:
    (tmp_path / "_bmad-output" / "planning-artifacts").mkdir(parents=True)

    result = detect_framework_workspace(tmp_path)

    assert result["ok"] is True
    assert result["framework"] == "bmad"


def test_detect_framework_workspace_returns_error_for_unknown_layout(tmp_path: Path) -> None:
    result = detect_framework_workspace(tmp_path / "missing-workspace")

    assert result["ok"] is False
    assert result["error"] == "framework_workspace_not_detected"


def test_sync_artifacts_to_workspace_writes_existing_framework_files(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (artifact_dir / "architecture.md").write_text("# Architecture\n", encoding="utf-8")

    result = sync_artifacts_to_workspace(
        framework="bmad",
        artifact_dir=artifact_dir,
        workspace_dir=workspace,
    )

    assert result["ok"] is True
    assert result["framework"] == "bmad"
    assert (workspace / "_bmad-output" / "planning-artifacts" / "prd.md").read_text(encoding="utf-8") == "# PRD\n"
    assert (workspace / "_bmad-output" / "planning-artifacts" / "architecture.md").read_text(encoding="utf-8") == "# Architecture\n"
    assert not (workspace / "_bmad-output" / "planning-artifacts" / "epics.md").exists()


def test_sync_artifacts_to_workspace_rejects_unknown_framework(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()

    with pytest.raises(ValueError, match="Unsupported framework workspace"):
        sync_artifacts_to_workspace(
            framework="unknown",
            artifact_dir=artifact_dir,
            workspace_dir=tmp_path / "repo",
        )
