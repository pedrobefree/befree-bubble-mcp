"""External framework workspace sync helpers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypedDict


class FrameworkLayout(TypedDict):
    marker: str
    targets: dict[str, str]


FRAMEWORK_LAYOUTS: dict[str, FrameworkLayout] = {
    "bmad": {
        "marker": "_bmad-output",
        "targets": {
            "project-brief.md": "_bmad-output/planning-artifacts/project-brief.md",
            "prd.md": "_bmad-output/planning-artifacts/prd.md",
            "architecture.md": "_bmad-output/planning-artifacts/architecture.md",
            "epics.md": "_bmad-output/planning-artifacts/epics.md",
            "stories.md": "_bmad-output/implementation-artifacts/stories.md",
            "validation-evidence.md": "_bmad-output/implementation-artifacts/validation-evidence.md",
        },
    },
    "superpowers": {
        "marker": "docs/superpowers",
        "targets": {
            "spec.md": "docs/superpowers/spec.md",
            "implementation-plan.md": "docs/superpowers/implementation-plan.md",
            "execution-gates.md": "docs/superpowers/execution-gates.md",
            "verification-checklist.md": "docs/superpowers/verification-checklist.md",
        },
    },
    "sdd": {
        "marker": "docs/sdd",
        "targets": {
            "specification.md": "docs/sdd/specification.md",
            "fixtures.md": "docs/sdd/fixtures.md",
            "acceptance-tests.md": "docs/sdd/acceptance-tests.md",
            "traceability.md": "docs/sdd/traceability.md",
        },
    },
}


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def detect_framework_workspace(workspace_dir: Path) -> dict[str, object]:
    root = _resolve_path(workspace_dir)
    for framework, layout in FRAMEWORK_LAYOUTS.items():
        if (root / layout["marker"]).exists():
            return {"ok": True, "framework": framework, "workspace_dir": str(root)}
    return {"ok": False, "error": "framework_workspace_not_detected", "workspace_dir": str(root)}


def sync_artifacts_to_workspace(*, framework: str, artifact_dir: Path, workspace_dir: Path) -> dict[str, object]:
    normalized = str(framework or "").strip().lower()
    if normalized not in FRAMEWORK_LAYOUTS:
        raise ValueError(f"Unsupported framework workspace: {framework}")

    root = _resolve_path(workspace_dir)
    source_root = artifact_dir.expanduser().resolve(strict=True)
    copied: list[str] = []

    for source_name, target_relative in FRAMEWORK_LAYOUTS[normalized]["targets"].items():
        source = source_root / source_name
        if not source.exists():
            continue
        target = root / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(target))

    return {"ok": True, "framework": normalized, "workspace_dir": str(root), "copied": copied}
