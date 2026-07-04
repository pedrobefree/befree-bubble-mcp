#!/usr/bin/env python3
"""Build and install a wheel in a clean venv, then smoke CLI/MCP entrypoints."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, cwd: Path = ROOT, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, input=input_text, text=True, check=True, capture_output=True)


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _venv_script(venv: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return venv / ("Scripts" if sys.platform == "win32" else "bin") / f"{name}{suffix}"


def _latest_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("befree_bubble_mcp-*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise RuntimeError(f"No befree_bubble_mcp wheel found in {wheel_dir}")
    return wheels[-1]


def run_package_smoke(*, python: str, keep_artifacts: bool) -> dict[str, object]:
    artifact_root = Path(tempfile.mkdtemp(prefix="befree-bubble-mcp-package-smoke."))
    wheel_dir = artifact_root / "wheelhouse"
    venv = artifact_root / "venv"
    wheel_dir.mkdir(parents=True)

    try:
        _run([sys.executable, "-m", "pip", "wheel", "--no-deps", ".", "-w", str(wheel_dir)])
        wheel = _latest_wheel(wheel_dir)

        _run([python, "-m", "venv", str(venv)])
        venv_python = _venv_python(venv)
        _run([str(venv_python), "-m", "pip", "install", str(wheel)])

        import_result = _run(
            [
                str(venv_python),
                "-c",
                (
                    "import bubble_mcp; "
                    "from bubble_mcp.server.stdio import handle_request; "
                    "payload=handle_request({'jsonrpc':'2.0','id':1,'method':'initialize'}); "
                    "assert payload['result']['serverInfo']['name']=='befree-bubble-mcp'; "
                    "assert 'instructions' in payload['result']; "
                    "print(bubble_mcp.__version__)"
                ),
            ]
        )

        _run([str(_venv_script(venv, "bubble-mcp")), "--help"])
        server_result = _run(
            [str(_venv_script(venv, "bubble-mcp-server"))],
            input_text='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
        )
        server_payload = json.loads(server_result.stdout)
        if "instructions" not in server_payload.get("result", {}):
            raise RuntimeError("bubble-mcp-server initialize response did not include instructions")

        return {
            "ok": True,
            "python": python,
            "wheel": str(wheel),
            "version": import_result.stdout.strip(),
            "server": server_payload["result"]["serverInfo"],
            "has_instructions": True,
            "artifacts": str(artifact_root) if keep_artifacts else None,
        }
    finally:
        if not keep_artifacts:
            shutil.rmtree(artifact_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test package wheel install and MCP entrypoints.")
    parser.add_argument("--python", default="python3.11", help="Python executable used for the clean install venv.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep temporary wheel/venv artifacts for inspection.")
    args = parser.parse_args()

    report = run_package_smoke(python=args.python, keep_artifacts=args.keep_artifacts)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
