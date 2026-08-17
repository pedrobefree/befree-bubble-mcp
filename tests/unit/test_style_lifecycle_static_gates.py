from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_ruff_gate_enumerates_every_style_lifecycle_module() -> None:
    root = Path(__file__).parents[2]
    lifecycle = root / "src" / "bubble_mcp" / "aria_runtime" / "style_lifecycle"
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("ruff")),
            "check",
            "--no-cache",
            "--show-files",
            str(lifecycle),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    enumerated = {Path(line).resolve() for line in result.stdout.splitlines() if line}
    expected = set(lifecycle.glob("*.py"))
    assert enumerated == expected
