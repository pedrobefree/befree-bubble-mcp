"""Run one short flow, declared inline, on one or more versions and hand back video side by side.

A suite case is Python on purpose (see ``suite.py``): the reference cases assert on computed font
weight and on the order of strings inside a card. But most checks an agent needs while working
are not that. On the team server "open client X as admin, click the button, confirm, check the
badge" had no suite to live in, so the agent wrote ~10 Playwright scripts from scratch and spent
~40 of an ~80-minute task on them, to get before/after evidence of one change.

A flow is that check, passed in the call as a short list of steps. It is turned into a case and
run by the suite runner itself - same URL resolution per version, same impersonated session,
same per-step screenshots and video - once per version. The versions' recordings are then put
side by side: always as ``compare.html`` (both videos, one play button, plus each step's
screenshots and status), and as ``side_by_side.webm`` when a full ffmpeg is on PATH (Playwright's
own build has no stacking filter).

Flows act on the app for real - they click and confirm - so ``live`` is refused: that is
production data. Development data (test and every branch) is what E2E runs are for.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, cast

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.e2e.context import CaseOptions, E2EContext
from bubble_mcp.e2e.paths import case_artifact_dir, new_run_id, run_dir, safe_run_id, safe_slug
from bubble_mcp.e2e.suite import E2ECaseSpec, E2ESuite
from bubble_mcp.e2e.target import (
    SessionStatus,
    check_run_as_session,
    playwright_available,
    resolve_target,
)

ACTIONS = ("goto", "click", "fill", "expect_text", "expect_no_text", "wait", "screenshot")
STEP_OPTIONS = ("name", "value", "exact", "timeout_ms")
SELECTOR_PREFIXES = ("#", ".", "[", "css=", "xpath=", "//", "text=", "role=")
MAX_VERSIONS = 4

RunAs = Callable[..., dict[str, Any]]


class FlowError(ValueError):
    """A flow that cannot run as written, with a message that says how to fix it."""


def validate_steps(steps: Any) -> list[dict[str, Any]]:
    """Each step names exactly one action; anything else is refused before a browser opens."""

    if not isinstance(steps, list) or not steps:
        raise FlowError("steps must be a non-empty list, e.g. [{'goto': 'index'}, {'click': 'Save'}].")
    checked: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise FlowError(f"Step {index} must be an object such as {{'click': 'Save'}}.")
        actions = [key for key in step if key in ACTIONS]
        unknown = [key for key in step if key not in ACTIONS and key not in STEP_OPTIONS]
        if len(actions) != 1 or unknown:
            raise FlowError(
                f"Step {index} {json.dumps(step)} must name exactly one action ({', '.join(ACTIONS)}) "
                f"plus optional {', '.join(STEP_OPTIONS)}."
            )
        action = actions[0]
        if action == "fill" and not isinstance(step.get("value"), str):
            raise FlowError(f"Step {index}: fill needs 'value', the text to type.")
        if action == "wait" and not isinstance(step["wait"], int):
            raise FlowError(f"Step {index}: wait takes milliseconds as a number.")
        if action != "wait" and action != "screenshot" and not str(step[action] or "").strip():
            raise FlowError(f"Step {index}: {action} needs a target.")
        checked.append(dict(step))
    return checked


def _step_name(index: int, step: dict[str, Any]) -> str:
    if step.get("name"):
        return str(step["name"])
    action = next(key for key in step if key in ACTIONS)
    return safe_slug(f"{index:02d}-{action}-{step[action] if action != 'wait' else step['wait']}")[:60]


def _is_selector(value: str) -> bool:
    return value.startswith(SELECTOR_PREFIXES)


def _target(ctx: E2EContext, value: str, *, exact: bool) -> Any:
    """A selector when it reads like one, otherwise the visible text a person would click."""

    if _is_selector(value):
        return ctx.page.locator(value).first
    return ctx.page.get_by_text(value, exact=exact).first


def _field(ctx: E2EContext, value: str) -> Any:
    """An input by selector, placeholder or label - the three ways a person names a field."""

    if _is_selector(value):
        return ctx.page.locator(value).first
    by_placeholder = ctx.page.get_by_placeholder(value)
    if by_placeholder.count():
        return by_placeholder.first
    return ctx.page.get_by_label(value).first


def flow_case(steps: Sequence[dict[str, Any]]) -> Callable[[E2EContext], None]:
    """The steps as a case callable the suite runner can run."""

    def run(ctx: E2EContext) -> None:
        for index, step in enumerate(steps, start=1):
            action = next(key for key in step if key in ACTIONS)
            value = step[action]
            timeout = int(step.get("timeout_ms") or ctx.options.default_timeout_ms)
            exact = bool(step.get("exact", False))
            with ctx.step(_step_name(index, step)):
                if action == "goto":
                    path = str(value)
                    if path.startswith("http"):
                        ctx.page.goto(path, wait_until="domcontentloaded")
                    else:
                        ctx.goto(path)
                    ctx.page.wait_for_load_state("networkidle", timeout=timeout)
                    ctx.mark_ready()
                elif action == "click":
                    target = _target(ctx, str(value), exact=exact)
                    target.wait_for(state="visible", timeout=timeout)
                    ctx.click(target)
                elif action == "fill":
                    ctx.fill(_field(ctx, str(value)), str(step["value"]))
                elif action == "expect_text":
                    ctx.expect(_target(ctx, str(value), exact=exact)).to_be_visible(timeout=timeout)
                elif action == "expect_no_text":
                    ctx.expect(ctx.page.get_by_text(str(value), exact=exact)).to_have_count(0, timeout=timeout)
                elif action == "wait":
                    ctx.wait(int(value))
                elif action == "screenshot":
                    ctx.shot(str(value or step.get("name") or f"step-{index}"))

    return run


def run_e2e_flow(
    *,
    profile: str,
    steps: Any,
    versions: Iterable[str],
    user_id: str = "",
    email: str = "",
    name: str = "flow",
    execute: bool = False,
    headless: bool = True,
    video: bool = True,
    cursor: bool = True,
    timeout_ms: int = 30_000,
    base_url: str = "",
    run_id: str = "",
    config_dir: Path | None = None,
    run_as: RunAs | None = None,
    run_case: Callable[..., dict[str, Any]] | None = None,
    compose_video: Callable[[Sequence[tuple[str, str]], Path], str | None] | None = None,
) -> dict[str, Any]:
    """Preview, or run, ``steps`` on each version and return per-version results and the comparison."""

    wanted = [str(item).strip() for item in versions if str(item).strip()]
    wanted = list(dict.fromkeys(wanted))
    base: dict[str, Any] = {"profile": profile, "name": name, "versions": wanted, "execute": bool(execute)}
    try:
        checked = validate_steps(steps)
        if not wanted or len(wanted) > MAX_VERSIONS:
            raise FlowError(f"versions must name 1 to {MAX_VERSIONS} versions, e.g. ['test', '<branch id>'].")
        if "live" in wanted:
            raise FlowError(
                "A flow clicks and confirms for real, and live is production data. Run it on test or a "
                "branch; they share the development database."
            )
        if not (user_id or email):
            raise FlowError("Pass user_id or email: the app user the flow runs as (bubble_run_as).")
        suite = E2ESuite(
            name=safe_slug(name) or "flow",
            profile=profile,
            cases=(),
            user_id=user_id,
            base_url=base_url,
            video=video,
            cursor=cursor,
            timeout_ms=timeout_ms,
            headless=headless,
        )
        targets = {version: resolve_target(suite, branch=version) for version in wanted}
    except (FlowError, ValueError) as error:
        return {**base, "ok": False, "error": str(error)}

    base["steps"] = checked
    base["targets"] = {version: target.to_payload() for version, target in targets.items()}
    if not execute:
        return {
            **base,
            "ok": True,
            "mode": "preview",
            "note": (
                "Preview only: no browser was opened and nothing was clicked. Call again with "
                "execute=true to run the flow on each version and record it."
            ),
        }
    if run_case is None and not playwright_available():
        from bubble_mcp.e2e import driver

        return {**base, "ok": False, "error": driver.install_error_note()}

    effective_run_id = safe_run_id(run_id) if run_id else new_run_id()
    directory = run_dir(profile, effective_run_id, config_dir)
    directory.mkdir(parents=True, exist_ok=True)
    spec = E2ECaseSpec(case_id=suite.name, description=f"Inline flow '{name}'", module="<inline flow>")
    options = CaseOptions(video=video, cursor=cursor, default_timeout_ms=timeout_ms)
    options.animate_waits = video
    case = flow_case(checked)

    results: dict[str, dict[str, Any]] = {}
    for version, target in targets.items():
        session = _session_for(profile, target.app_id, version, user_id, email, directory, run_as)
        if not session.ok:
            results[version] = {
                "ok": False,
                "status": "errored",
                "message": session.message,
                "session": session.to_payload(),
            }
            continue
        results[version] = (run_case or _run_case)(
            suite=suite,
            spec=spec,
            target=target,
            session=session,
            options=options,
            artifact_dir=case_artifact_dir(profile, effective_run_id, f"{suite.name}-{version}", config_dir),
            headless=headless,
            config_dir=config_dir,
            case_callable=case,
        )

    comparison = _compare(results, directory, compose_video or _side_by_side_video)
    payload = {
        **base,
        "ok": all(result.get("ok") for result in results.values()),
        "mode": "execute",
        "run_id": effective_run_id,
        "artifacts_dir": str(directory),
        "results": results,
        "comparison": comparison,
    }
    redacted = cast("dict[str, Any]", redact_sensitive(payload))
    (directory / "flow-result.json").write_text(json.dumps(redacted, indent=2, ensure_ascii=False), encoding="utf-8")
    return redacted


def _session_for(
    profile: str,
    app_id: str,
    version: str,
    user_id: str,
    email: str,
    directory: Path,
    run_as: RunAs | None,
) -> SessionStatus:
    """An impersonated session for this version, kept in the run so the next version cannot
    overwrite it: Bubble's user session cookie is per version, the storage file is per user."""

    if run_as is None:
        from bubble_mcp.execution.run_as import run_as_user

        run_as = run_as_user
    result = run_as(profile, user_id, email=email or None, app_id=app_id, app_version=version)
    if not result.get("ok") or not result.get("storage_state_path"):
        return SessionStatus(
            ok=False,
            path=Path(),
            user_id=user_id,
            reason=str(result.get("error") or "run_as_failed"),
            message=f"Could not run as the user on '{version}': {result.get('message') or result.get('error')}",
        )
    resolved_user = str(result.get("user_id") or user_id)
    kept = directory / f"storage-{safe_slug(version)}.json"
    shutil.copyfile(str(result["storage_state_path"]), kept)
    status = check_run_as_session(profile, app_id, resolved_user)
    return SessionStatus(ok=status.ok, path=kept, user_id=resolved_user, reason=status.reason, message=status.message)


def _run_case(**kwargs: Any) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    from bubble_mcp.e2e.runner import _run_one_case

    with sync_playwright() as playwright:
        return _run_one_case(playwright, slow_mo=0, **kwargs)


def _compare(
    results: dict[str, dict[str, Any]],
    directory: Path,
    compose_video: Callable[[Sequence[tuple[str, str]], Path], str | None],
) -> dict[str, Any]:
    videos = [
        (version, str((result.get("artifacts") or {}).get("video")))
        for version, result in results.items()
        if (result.get("artifacts") or {}).get("video")
    ]
    page = directory / "compare.html"
    page.write_text(_compare_html(results, directory), encoding="utf-8")
    comparison: dict[str, Any] = {"html": str(page), "videos": dict(videos)}
    if len(videos) >= 2:
        composed = compose_video(videos, directory / "side_by_side.webm")
        if composed:
            comparison["side_by_side_video"] = composed
        else:
            comparison["side_by_side_video_note"] = (
                "No full ffmpeg on PATH (Playwright's own build cannot stack videos); compare.html "
                "plays both recordings side by side instead."
            )
    return comparison


def _side_by_side_video(videos: Sequence[tuple[str, str]], output: Path) -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    inputs: list[str] = []
    scaled: list[str] = []
    for index, (_, path) in enumerate(videos):
        inputs += ["-i", path]
        scaled.append(f"[{index}:v]scale=-2:720,setsar=1[v{index}]")
    stack = "".join(f"[v{index}]" for index in range(len(videos))) + f"hstack=inputs={len(videos)}"
    command = [
        ffmpeg,
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(scaled) + ";" + stack,
        "-c:v",
        "libvpx",
        "-b:v",
        "2M",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    return str(output) if output.exists() else None


def _relative(path: str, directory: Path) -> str:
    try:
        return Path(path).resolve().relative_to(directory.resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_uri()


def _compare_html(results: dict[str, dict[str, Any]], directory: Path) -> str:
    columns = []
    for version, result in results.items():
        artifacts = result.get("artifacts") or {}
        video = artifacts.get("video")
        video_tag = (
            f'<video src="{html.escape(_relative(str(video), directory))}" controls muted></video>'
            if video
            else "<p class=missing>No recording.</p>"
        )
        steps = "".join(
            "<li class='{status}'><b>{name}</b> - {status}{message}{shot}</li>".format(
                status=html.escape(str(step.get("status"))),
                name=html.escape(str(step.get("name"))),
                message=f"<br><small>{html.escape(str(step['message']))}</small>" if step.get("message") else "",
                shot=(
                    f"<br><img src='{html.escape(_relative(str(step['screenshot']), directory))}'>"
                    if step.get("screenshot")
                    else ""
                ),
            )
            for step in result.get("steps") or []
        )
        status = html.escape(str(result.get("status")))
        message = f"<p>{html.escape(str(result['message']))}</p>" if result.get("message") else ""
        columns.append(
            f"<section><h2>{html.escape(version)} <span class='{status}'>{status}</span></h2>"
            f"{video_tag}{message}<ol>{steps}</ol></section>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Flow comparison</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; background: #fff; color: #111; }}
main {{ display: grid; grid-template-columns: repeat({max(len(columns), 1)}, minmax(0, 1fr)); gap: 16px; }}
video, img {{ width: 100%; border: 1px solid #ccc; }}
.passed {{ color: #137333; }} .failed, .errored {{ color: #b3261e; }}
button {{ font-size: 16px; padding: 6px 14px; margin-bottom: 12px; }}
</style></head><body>
<button onclick="document.querySelectorAll('video').forEach(v => {{ v.currentTime = 0; v.play(); }})">Play both from the start</button>
<main>{''.join(columns)}</main>
</body></html>
"""
