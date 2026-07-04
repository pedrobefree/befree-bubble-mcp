#!/usr/bin/env python3
"""Smoke-test first-run CLI setup in an isolated config directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, env=env, text=True, check=check, capture_output=True)


def _run_cli(python: str, args: list[str], *, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run([python, "-m", "bubble_mcp.cli.main", *args], env=env, check=check)


def _json_stdout(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(result.stdout)


def _assert_next_actions(status: dict[str, Any]) -> None:
    actions = status.get("next_actions")
    if not isinstance(actions, list):
        raise AssertionError("profile status did not include next_actions")
    tools = [action.get("tool") for action in actions if isinstance(action, dict)]
    if tools != ["bubble_session_import", "bubble_context_detect"]:
        raise AssertionError(f"unexpected next action tools: {tools!r}")


def run_setup_smoke(*, python: str, keep_artifacts: bool) -> dict[str, Any]:
    config_dir = Path(tempfile.mkdtemp(prefix="befree-bubble-mcp-setup-smoke."))
    env = {**os.environ, "BUBBLE_MCP_CONFIG_DIR": str(config_dir)}
    profile = "release-smoke"
    app_id = "example-app"

    try:
        init_payload = _json_stdout(_run_cli(python, ["init"], env=env))
        if init_payload.get("ok") is not True:
            raise AssertionError("init did not return ok=true")

        add_payload = _json_stdout(
            _run_cli(
                python,
                ["profile", "add", profile, "--app-id", app_id, "--app-version", "test"],
                env=env,
            )
        )
        if add_payload.get("ok") is not True or add_payload.get("profile") != profile:
            raise AssertionError("profile add did not create the expected profile")

        status_payload = _json_stdout(_run_cli(python, ["profile", "status", "--profile", profile], env=env))
        if status_payload.get("ok") is not True:
            raise AssertionError("profile status did not return ok=true")
        if status_payload.get("ready") is not False:
            raise AssertionError("fresh profile should not be ready before session/context setup")
        if status_payload.get("profile", {}).get("app_id") != app_id:
            raise AssertionError("profile status returned the wrong app id")
        _assert_next_actions(status_payload)

        readiness_result = _run_cli(
            python,
            ["readiness", "--profile", profile, "--context", "index", "--parent", "root"],
            env=env,
            check=False,
        )
        readiness_payload = _json_stdout(readiness_result)
        if readiness_result.returncode != 1:
            raise AssertionError(f"fresh profile readiness should fail with exit 1, got {readiness_result.returncode}")
        if readiness_payload.get("ok") is not False:
            raise AssertionError("fresh profile readiness should report ok=false")
        failed = readiness_payload.get("summary", {}).get("failed")
        if failed != 2:
            raise AssertionError(f"fresh profile readiness should have 2 expected failures, got {failed!r}")

        return {
            "ok": True,
            "python": python,
            "config_dir": str(config_dir) if keep_artifacts else None,
            "profile": profile,
            "app_id": app_id,
            "profile_ready": status_payload["ready"],
            "next_action_tools": [action["tool"] for action in status_payload["next_actions"]],
            "readiness_exit_code": readiness_result.returncode,
            "readiness_summary": readiness_payload["summary"],
        }
    finally:
        if not keep_artifacts:
            shutil.rmtree(config_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test first-run Bubble MCP setup in a temporary config dir.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to invoke bubble_mcp.cli.main.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep the temporary config directory for inspection.")
    args = parser.parse_args()

    report = run_setup_smoke(python=args.python, keep_artifacts=args.keep_artifacts)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
