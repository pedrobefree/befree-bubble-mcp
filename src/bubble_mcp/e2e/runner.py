"""Running a suite: resolve, verify, then drive a browser once per case.

Isolation is per case, not per suite. Each case gets its own browser and its own context, so a
case that hangs the page, leaves a modal open or crashes the tab costs only itself. That also
gives each case its own video file without having to split one recording afterwards.

Nothing here writes to Bubble on its own - the cases do, by using the app the way a person
would. That is why ``execute`` defaults to false: a preview resolves the suite, checks the
session and reports what would run, without opening a browser or creating a single record.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import traceback
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.e2e import driver
from bubble_mcp.e2e.context import CaseOptions, E2EContext, StepRecord
from bubble_mcp.e2e.paths import (
    case_artifact_dir,
    new_run_id,
    resolve_case_module,
    resolve_fixtures_root,
    result_path,
    run_dir,
    safe_run_id,
)
from bubble_mcp.e2e.suite import E2ECaseSpec, E2ESuite, E2ESuiteError, load_suite
from bubble_mcp.e2e.target import (
    ResolvedTarget,
    SessionStatus,
    check_run_as_session,
    playwright_available,
    resolve_target,
)
from bubble_mcp.execution.run_as import preview_credentials_from_export

CaseCallable = Callable[[E2EContext], None]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_case_callable(
    profile: str,
    spec: E2ECaseSpec,
    config_dir: Path | None = None,
    *,
    cases_root: str = "",
) -> CaseCallable:
    """Import a case module from the suite's cases directory and hand back its ``run``.

    Loaded fresh every time rather than cached: a tester who just changed a case expects the
    next run to use the change, and these modules are not part of the server's import graph.

    While the module executes, its own directory is *appended* to ``sys.path`` so a case can
    import a sibling - the shared navigation helpers of a suite belong in one case file, not
    copied into each. Appended rather than prepended on purpose: a case file called ``json.py``
    then loses to the standard library instead of replacing it for the whole process.
    """

    path = resolve_case_module(profile, spec.module, config_dir, cases_root=cases_root)
    if not path.exists():
        raise E2ESuiteError(
            f"Case {spec.case_id!r} points at {path}, which does not exist. Generate it with "
            "bubble_e2e_scaffold or fix 'module' in the manifest."
        )
    module_name = f"bubble_mcp_e2e_case_{profile}_{spec.case_id}".replace("-", "_")
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise E2ESuiteError(f"Case {spec.case_id!r} at {path} is not an importable Python module.")
    module = importlib.util.module_from_spec(module_spec)
    directory = str(path.parent)
    added = directory not in sys.path
    if added:
        sys.path.append(directory)
    try:
        module_spec.loader.exec_module(module)
    finally:
        if added:
            with suppress(ValueError):
                sys.path.remove(directory)
    runner = getattr(module, "run", None)
    if not callable(runner):
        raise E2ESuiteError(
            f"Case module {path} defines no run(ctx) function. A case module must expose "
            "exactly one entry point: def run(ctx)."
        )
    return cast("CaseCallable", runner)


def _case_plan(
    profile: str, spec: E2ECaseSpec, config_dir: Path | None, cases_root: str = ""
) -> dict[str, Any]:
    """What a preview can say about a case without importing or running it."""

    plan: dict[str, Any] = {
        "case_id": spec.case_id,
        "description": spec.description,
        "module": spec.module,
    }
    if spec.tags:
        plan["tags"] = list(spec.tags)
    if spec.params:
        plan["params"] = dict(spec.params)
    try:
        path = resolve_case_module(profile, spec.module, config_dir, cases_root=cases_root)
    except ValueError as error:
        plan["ok"] = False
        plan["error"] = str(error)
        return plan
    plan["module_path"] = str(path)
    plan["ok"] = path.exists()
    if not path.exists():
        plan["error"] = f"Case module {path} does not exist."
    return plan


def _preflight(
    *,
    suite: E2ESuite,
    target: ResolvedTarget,
    session: SessionStatus,
    plans: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Every reason this run could not start, gathered in one pass instead of one at a time."""

    blockers: list[dict[str, Any]] = []
    if not playwright_available():
        blockers.append(
            {
                "check": "playwright",
                "message": driver.install_error_note(),
                "next_action": {"command": "python -m playwright install chromium"},
            }
        )
    if not session.ok:
        blockers.append(
            {
                "check": "run_as_session",
                "message": session.message,
                "next_action": session.next_action,
            }
        )
    missing = [plan for plan in plans if not plan.get("ok")]
    if missing:
        blockers.append(
            {
                "check": "case_modules",
                "message": "; ".join(str(plan.get("error")) for plan in missing),
                "next_action": {
                    "tool": "bubble_e2e_scaffold",
                    "arguments": {"profile": suite.profile, "suite": suite.name},
                },
            }
        )
    if target.base_url_origin == "app_topdomain_guess":
        blockers.extend(
            {"check": "base_url", "message": warning, "severity": "warning"}
            for warning in target.warnings
        )
    return blockers


def _case_result(
    spec: E2ECaseSpec,
    *,
    status: str,
    duration_ms: int,
    steps: Sequence[StepRecord],
    artifacts: dict[str, Any],
    message: str | None = None,
    failed_step: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": spec.case_id,
        "description": spec.description,
        "status": status,
        "ok": status in {"passed", "skipped"},
        "duration_ms": duration_ms,
        "steps": [record.to_payload() for record in steps],
        "artifacts": artifacts,
    }
    if message:
        payload["message"] = message
    if failed_step:
        payload["failed_step"] = failed_step
    if detail:
        payload["detail"] = detail
    return payload


def _finalize_video(context_video_dir: Path, ctx: E2EContext, started: float) -> str | None:
    """Rename Playwright's random video name to something a report can quote, and trim it."""

    video = driver.latest_video(context_video_dir)
    if video is None:
        return None
    target = context_video_dir / "video.webm"
    if video != target:
        with suppress(OSError):
            video.replace(target)
            video = target
    skip = (ctx.ready_at - started - 1.5) if ctx.ready_at else 0.0
    return str(driver.trim_video(video, skip, destination=context_video_dir / "video-trimmed.webm"))


def _run_one_case(
    playwright: Any,
    *,
    suite: E2ESuite,
    spec: E2ECaseSpec,
    target: ResolvedTarget,
    session: SessionStatus,
    options: CaseOptions,
    artifact_dir: Path,
    headless: bool,
    slow_mo: int,
    config_dir: Path | None,
) -> dict[str, Any]:
    """One case, one browser. Every failure mode lands in the result instead of propagating."""

    artifact_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    steps: list[StepRecord] = []
    artifacts: dict[str, Any] = {"dir": str(artifact_dir)}

    try:
        case_callable = load_case_callable(
            suite.profile, spec, config_dir, cases_root=suite.cases_root
        )
    except (E2ESuiteError, OSError, SyntaxError, ValueError) as error:
        return _case_result(
            spec,
            status="errored",
            duration_ms=int((time.monotonic() - started) * 1000),
            steps=steps,
            artifacts=artifacts,
            message=str(error),
        )
    except Exception as error:  # noqa: BLE001 - a case module runs arbitrary import-time code
        return _case_result(
            spec,
            status="errored",
            duration_ms=int((time.monotonic() - started) * 1000),
            steps=steps,
            artifacts=artifacts,
            message=f"Importing the case module raised {type(error).__name__}: {error}",
            detail=traceback.format_exc(limit=6),
        )

    credentials = preview_credentials_from_export(suite.profile, target.app_id)
    http_credentials = (
        {"username": credentials[0], "password": credentials[1]} if credentials else None
    )
    context_kwargs: dict[str, Any] = {
        "storage_state": str(session.path),
        "viewport": {"width": suite.viewport[0], "height": suite.viewport[1]},
        "http_credentials": http_credentials,
    }
    if options.video:
        context_kwargs["record_video_dir"] = str(artifact_dir)
        context_kwargs["record_video_size"] = {
            "width": suite.viewport[0],
            "height": suite.viewport[1],
        }

    browser = None
    context = None
    ctx: E2EContext | None = None
    status = "passed"
    message: str | None = None
    detail: str | None = None
    try:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(**context_kwargs)
        if options.cursor:
            context.add_init_script(driver.CURSOR_SCRIPT)
        page = context.new_page()
        page.set_default_timeout(options.default_timeout_ms)
        ctx = E2EContext(
            page=page,
            target=target,
            case_id=spec.case_id,
            artifact_dir=artifact_dir,
            fixtures_dir=resolve_fixtures_root(suite.profile, suite.cases_root, config_dir),
            params=dict(spec.params),
            options=options,
        )
        steps = ctx.steps
        case_callable(ctx)
    except AssertionError as error:
        status = "failed"
        message = str(error) or "Assertion failed."
        detail = traceback.format_exc(limit=8)
    except Exception as error:  # noqa: BLE001 - one broken case must not end the suite
        status = "errored"
        message = f"{type(error).__name__}: {error}"
        detail = traceback.format_exc(limit=8)
    finally:
        if context is not None:
            with suppress(Exception):
                context.close()
        if browser is not None:
            with suppress(Exception):
                browser.close()

    if ctx is not None:
        steps = ctx.steps
        screenshots = sorted(str(item) for item in artifact_dir.glob("*.png"))
        if screenshots:
            artifacts["screenshots"] = screenshots
        if options.video:
            video = _finalize_video(artifact_dir, ctx, started)
            if video:
                artifacts["video"] = video

    failed_step = next(
        (record.name for record in steps if record.status == "failed"),
        None,
    )
    return _case_result(
        spec,
        status=status,
        duration_ms=int((time.monotonic() - started) * 1000),
        steps=steps,
        artifacts=artifacts,
        message=message,
        failed_step=failed_step,
        detail=detail,
    )


def _summary(results: Sequence[dict[str, Any]], duration_ms: int) -> dict[str, Any]:
    return {
        "cases": len(results),
        "passed": sum(1 for item in results if item["status"] == "passed"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "errored": sum(1 for item in results if item["status"] == "errored"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
        "duration_ms": duration_ms,
    }


def _write_result(profile: str, run_id: str, payload: dict[str, Any], config_dir: Path | None) -> str:
    path = result_path(profile, run_id, config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def run_e2e_suite(
    *,
    profile: str,
    suite: str,
    cases: Iterable[str] = (),
    tags: Iterable[str] = (),
    branch: str = "",
    execute: bool = False,
    headless: bool | None = None,
    video: bool | None = None,
    cursor: bool | None = None,
    slow_mo: int | None = None,
    timeout_ms: int | None = None,
    run_id: str = "",
    stop_on_failure: bool = False,
    include_details: bool = False,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    """Run a suite, or preview what it would run. Returns the structured result either way."""

    effective_run_id = safe_run_id(run_id) if run_id else new_run_id()
    base: dict[str, Any] = {
        "suite": suite,
        "profile": profile,
        "run_id": effective_run_id,
        "execute": bool(execute),
        "started_at": _now(),
    }

    try:
        loaded = load_suite(profile, suite, config_dir)
        selected = loaded.select(cases, tags)
        target = resolve_target(loaded, branch=branch)
    except (E2ESuiteError, ValueError) as error:
        return {**base, "ok": False, "error": str(error), "summary": _summary([], 0), "results": []}

    session = check_run_as_session(profile, target.app_id, loaded.user_id)
    plans = [_case_plan(profile, spec, config_dir, loaded.cases_root) for spec in selected]
    blockers = _preflight(suite=loaded, target=target, session=session, plans=plans)
    fatal = [item for item in blockers if item.get("severity") != "warning"]

    base.update(
        {
            "suite_path": str(loaded.path) if loaded.path else None,
            "target": target.to_payload(),
            "session": session.to_payload(),
        }
    )

    if not execute:
        payload = {
            **base,
            "ok": not fatal,
            "mode": "preview",
            "note": (
                "Preview only: nothing was opened and no record was created in the app. "
                "Call again with execute=true to run the cases for real."
            ),
            "blockers": blockers,
            "planned_cases": plans,
            "summary": _summary([], 0),
            "results": [],
        }
        return cast("dict[str, Any]", redact_sensitive(payload))

    if fatal:
        payload = {
            **base,
            "ok": False,
            "mode": "execute",
            "error": "; ".join(str(item["message"]) for item in fatal),
            "blockers": blockers,
            "planned_cases": plans,
            "summary": _summary([], 0),
            "results": [],
        }
        return cast("dict[str, Any]", redact_sensitive(payload))

    options = CaseOptions(
        video=loaded.video if video is None else bool(video),
        cursor=loaded.cursor if cursor is None else bool(cursor),
        default_timeout_ms=loaded.timeout_ms if timeout_ms is None else int(timeout_ms),
    )
    options.animate_waits = options.video
    effective_headless = loaded.headless if headless is None else bool(headless)
    effective_slow_mo = loaded.slow_mo if slow_mo is None else int(slow_mo)

    from playwright.sync_api import sync_playwright

    results: list[dict[str, Any]] = []
    started = time.monotonic()
    with sync_playwright() as playwright:
        for spec in selected:
            result = _run_one_case(
                playwright,
                suite=loaded,
                spec=spec,
                target=target,
                session=session,
                options=options,
                artifact_dir=case_artifact_dir(profile, effective_run_id, spec.case_id, config_dir),
                headless=effective_headless,
                slow_mo=effective_slow_mo,
                config_dir=config_dir,
            )
            results.append(result)
            if stop_on_failure and not result["ok"]:
                skipped = selected[selected.index(spec) + 1 :]
                results.extend(
                    _case_result(
                        item,
                        status="skipped",
                        duration_ms=0,
                        steps=[],
                        artifacts={},
                        message="Skipped because an earlier case failed and stop_on_failure was set.",
                    )
                    for item in skipped
                )
                break

    summary = _summary(results, int((time.monotonic() - started) * 1000))
    payload = {
        **base,
        "ok": summary["failed"] == 0 and summary["errored"] == 0,
        "mode": "execute",
        "finished_at": _now(),
        "options": {
            "headless": effective_headless,
            "video": options.video,
            "cursor": options.cursor,
            "slow_mo": effective_slow_mo,
            "timeout_ms": options.default_timeout_ms,
        },
        "blockers": [item for item in blockers if item.get("severity") == "warning"],
        "artifacts_dir": str(run_dir(profile, effective_run_id, config_dir)),
        "summary": summary,
        "results": results,
    }
    if not include_details:
        for item in payload["results"]:
            item.pop("detail", None)
    redacted = cast("dict[str, Any]", redact_sensitive(payload))
    redacted["result_path"] = _write_result(profile, effective_run_id, redacted, config_dir)
    return redacted
