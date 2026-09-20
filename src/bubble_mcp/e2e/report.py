"""Reading back a finished run, and listing what a profile has to run.

A run writes its result next to its artifacts, so the report is a read of that file rather
than a second execution. That is the whole point: an agent that wants to know why a case
failed yesterday must not have to create yesterday's records again.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.e2e.paths import RESULT_FILENAME, result_path, runs_dir
from bubble_mcp.e2e.suite import E2ESuiteError, list_suites, load_suite
from bubble_mcp.e2e.target import check_run_as_session, playwright_available, resolve_target


def list_runs(profile: str, limit: int = 20, config_dir: Path | None = None) -> list[dict[str, Any]]:
    """Recent runs for a profile, newest first, read from each run's own result file."""

    directory = runs_dir(profile, config_dir)
    if not directory.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for run_path in sorted(directory.iterdir(), reverse=True):
        if not run_path.is_dir():
            continue
        payload_path = run_path / RESULT_FILENAME
        entry: dict[str, Any] = {"run_id": run_path.name, "artifacts_dir": str(run_path)}
        if payload_path.exists():
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = {}
            if isinstance(payload, dict):
                entry.update(
                    {
                        "suite": payload.get("suite"),
                        "ok": payload.get("ok"),
                        "mode": payload.get("mode"),
                        "started_at": payload.get("started_at"),
                        "summary": payload.get("summary"),
                    }
                )
        else:
            entry["note"] = "No result.json: the run did not finish writing its report."
        entries.append({key: value for key, value in entry.items() if value is not None})
        if len(entries) >= max(1, limit):
            break
    return entries


def read_e2e_report(
    *,
    profile: str,
    run_id: str,
    include_details: bool = False,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a previous run's structured result without re-running anything."""

    path = result_path(profile, run_id, config_dir)
    if not path.exists():
        recent = [entry["run_id"] for entry in list_runs(profile, 10, config_dir)]
        return {
            "ok": False,
            "profile": profile,
            "run_id": run_id,
            "error": (
                f"No run {run_id!r} for profile {profile!r} at {path}. "
                f"Recent runs: {', '.join(recent) or 'none'}."
            ),
            "recent_runs": recent,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {
            "ok": False,
            "profile": profile,
            "run_id": run_id,
            "error": f"The result file {path} could not be read: {error}",
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "profile": profile,
            "run_id": run_id,
            "error": f"The result file {path} does not hold a run result object.",
        }
    payload["result_path"] = str(path)
    if not include_details:
        for item in payload.get("results") or []:
            if isinstance(item, dict):
                item.pop("detail", None)
    return cast("dict[str, Any]", redact_sensitive(payload))


def list_e2e_suites(
    *,
    profile: str,
    suite: str = "",
    include_runs: bool = True,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    """Every suite and case a profile can run, plus whether it could run them right now."""

    if not profile:
        return {"ok": False, "error": "bubble_e2e_list requires a profile."}

    try:
        suites = [load_suite(profile, suite, config_dir)] if suite else list_suites(profile, config_dir)
    except E2ESuiteError as error:
        return {"ok": False, "profile": profile, "error": str(error)}

    entries: list[dict[str, Any]] = []
    for item in suites:
        entry: dict[str, Any] = {
            "name": item.name,
            "path": str(item.path) if item.path else None,
            "cases": [spec.to_payload() for spec in item.cases],
            "defaults": {
                "headless": item.headless,
                "video": item.video,
                "cursor": item.cursor,
                "slow_mo": item.slow_mo,
                "timeout_ms": item.timeout_ms,
            },
        }
        try:
            target = resolve_target(item)
        except ValueError as error:
            entry["ok"] = False
            entry["error"] = str(error)
            entries.append(entry)
            continue
        session = check_run_as_session(profile, target.app_id, item.user_id)
        entry["target"] = target.to_payload()
        entry["session"] = session.to_payload()
        entry["ok"] = session.ok
        entries.append(entry)

    payload: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "playwright_installed": playwright_available(),
        "suites": entries,
    }
    if not entries:
        payload["note"] = (
            f"No E2E suite is declared for profile {profile!r}. Create one with "
            "bubble_e2e_scaffold."
        )
    if include_runs:
        payload["recent_runs"] = list_runs(profile, 10, config_dir)
    return cast("dict[str, Any]", redact_sensitive(payload))
