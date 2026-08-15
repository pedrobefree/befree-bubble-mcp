from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.setup_smoke import _run_cli, setup_smoke_environment


def test_setup_smoke_environment_prepends_checkout_source(tmp_path: Path) -> None:
    environment = setup_smoke_environment(tmp_path, {"PYTHONPATH": "/existing/source", "LANG": "C"})

    entries = environment["PYTHONPATH"].split(os.pathsep)
    expected_source = Path(__file__).resolve().parents[2] / "src"
    assert entries[0] == str(expected_source)
    assert entries[1] == "/existing/source"
    assert environment["BUBBLE_MCP_CONFIG_DIR"] == str(tmp_path)
    assert environment["LANG"] == "C"


def test_setup_smoke_cli_runs_from_non_editable_checkout(tmp_path: Path) -> None:
    environment = setup_smoke_environment(
        tmp_path,
        {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}},
    )

    result = _run_cli(sys.executable, ["init"], env=environment, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
