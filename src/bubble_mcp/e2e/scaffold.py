"""Creating a suite and a case from nothing, so the next one needs no source reading.

This is the tool an agent reaches for when a tester describes a test in plain language: it
lays out the directories, writes or extends the manifest, and drops a case module whose
skeleton already shows the whole context API in use. What the agent then fills in is the
selectors and the assertions - the parts only the app can answer.

Selectors are deliberately not guessed here. An element's exposed id lives in the app export
for the *version under test*, so the honest move is to point at the tools that read it rather
than to invent a plausible ``#some-id``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.e2e.paths import (
    case_key,
    cases_dir,
    fixtures_dir,
    resolve_case_module,
    resolve_cases_root,
    runs_dir,
    suite_path,
    suites_dir,
)
from bubble_mcp.e2e.suite import DEFAULT_VIEWPORT, E2ESuiteError, load_suite, parse_suite

CASE_TEMPLATE = '''"""{description}

Case {case_id} of the {suite} suite.

Runs under the MCP E2E runner: by the time run(ctx) is called the browser is open, the
run-as session is loaded, and ctx.base_url already points at the branch under test.

Fill in the selectors below. To find an element's exposed id, refresh the app context for the
branch you are testing (bubble_context_detect with that app_version) and look it up with
bubble_context_find - do not guess an id.
"""


def run(ctx):
    # Every `with ctx.step(...)` block is timed, screenshotted and named in the run report,
    # so a failure says which step broke rather than only that the case did.
    with ctx.step("open"):
        ctx.goto("{start_path}")
        ctx.mark_ready()  # marks the end of app boot, so the video gets trimmed to here

    with ctx.step("act"):
        # ctx.unique(...) stamps a value with the time, so the assertion below can name
        # exactly what this run typed and not something left by an earlier one.
        ctx.data["label"] = ctx.unique("E2E {case_id}")
        # ctx.type("#your-input-id", ctx.data["label"])
        # ctx.click("#your-save-button-id")

    with ctx.step("assert"):
        # ctx.expect(...) is Playwright's expect, already pointed at the locator.
        # ctx.expect("#your-list-id").to_contain_text(ctx.data["label"])
        raise AssertionError("Replace this with the real assertion for {case_id}.")
'''


def _default_manifest(
    *,
    suite: str,
    profile: str,
    app_id: str,
    branch: str,
    base_url: str,
    user_id: str,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {"name": suite, "profile": profile, "cases": []}
    for key, value in (("app_id", app_id), ("branch", branch), ("base_url", base_url)):
        if value:
            manifest[key] = value
    manifest["run_as"] = {"user_id": user_id}
    manifest["viewport"] = {"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]}
    manifest["defaults"] = {
        "headless": True,
        "video": False,
        "cursor": False,
        "slow_mo": 0,
        "timeout_ms": 30_000,
    }
    return manifest


def scaffold_e2e(
    *,
    profile: str,
    suite: str,
    case_id: str = "",
    description: str = "",
    tags: list[str] | None = None,
    start_path: str = "index",
    app_id: str = "",
    branch: str = "",
    base_url: str = "",
    cases_root: str = "",
    user_id: str = "",
    execute: bool = False,
    overwrite: bool = False,
    config_dir: Path | None = None,
) -> dict[str, Any]:
    """Create or extend a suite. With ``execute=false`` it only reports what it would write."""

    if not profile:
        return {"ok": False, "error": "bubble_e2e_scaffold requires a profile."}
    if not suite:
        return {"ok": False, "error": "bubble_e2e_scaffold requires a suite name."}

    manifest_path = suite_path(profile, suite, config_dir)
    existing: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return {
                "ok": False,
                "error": f"Suite manifest {manifest_path} exists but cannot be read: {error}",
            }

    manifest = (
        dict(existing)
        if isinstance(existing, dict)
        else _default_manifest(
            suite=suite,
            profile=profile,
            app_id=app_id,
            branch=branch,
            base_url=base_url,
            user_id=user_id,
        )
    )
    for key, value in (
        ("app_id", app_id),
        ("branch", branch),
        ("base_url", base_url),
        ("cases_root", cases_root),
    ):
        if value:
            manifest[key] = value
    if user_id:
        manifest["run_as"] = {"user_id": user_id}
    manifest.setdefault("cases", [])

    planned_files: list[dict[str, Any]] = []
    module_path: Path | None = None
    resolved_case = case_key(case_id)
    if resolved_case:
        module_ref = f"{resolved_case.replace('-', '_')}.py"
        module_path = resolve_case_module(
            profile, module_ref, config_dir, cases_root=str(manifest.get("cases_root") or "")
        )
        already = [
            entry
            for entry in manifest["cases"]
            if isinstance(entry, dict) and case_key(str(entry.get("id"))) == resolved_case
        ]
        if already and not overwrite:
            return {
                "ok": False,
                "error": (
                    f"Suite {suite!r} already declares case {case_id!r}. Pass overwrite=true to "
                    "replace its manifest entry and module."
                ),
            }
        entry: dict[str, Any] = {
            "id": resolved_case,
            "description": description or f"Case {resolved_case}",
            "module": module_ref,
        }
        if tags:
            entry["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        manifest["cases"] = [
            item
            for item in manifest["cases"]
            if not (
                isinstance(item, dict) and case_key(str(item.get("id"))) == resolved_case
            )
        ] + [entry]
        planned_files.append(
            {
                "path": str(module_path),
                "kind": "case_module",
                "exists": module_path.exists(),
                "action": "overwrite" if module_path.exists() and overwrite else "create",
            }
        )

    planned_files.insert(
        0,
        {
            "path": str(manifest_path),
            "kind": "suite_manifest",
            "exists": manifest_path.exists(),
            "action": "update" if manifest_path.exists() else "create",
        },
    )

    if manifest["cases"]:
        try:
            parse_suite(manifest, path=manifest_path, profile=profile)
        except E2ESuiteError as error:
            return {"ok": False, "error": f"The manifest this would write is invalid: {error}"}

    payload: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "suite": suite,
        "case_id": resolved_case or None,
        "execute": bool(execute),
        "files": planned_files,
        "directories": {
            "suites": str(suites_dir(profile, config_dir)),
            "cases": str(
                resolve_cases_root(profile, str(manifest.get("cases_root") or ""), config_dir)
            ),
            "fixtures": str(fixtures_dir(profile, config_dir)),
            "runs": str(runs_dir(profile, config_dir)),
        },
        "manifest": manifest,
        "next_steps": [
            (
                "Refresh the app context for the branch under test so element ids are current: "
                "bubble_context_detect with that app_version."
            ),
            "Look each element up with bubble_context_find instead of guessing a selector.",
            "Capture the impersonated session with bubble_run_as if run_as.user_id is new.",
            "Preview with bubble_e2e_run (execute=false), then run it with execute=true.",
        ],
    }

    if not execute:
        payload["mode"] = "preview"
        payload["note"] = "Nothing was written. Call again with execute=true to create the files."
        return cast("dict[str, Any]", redact_sensitive(payload))

    for directory in (
        suites_dir(profile, config_dir),
        module_path.parent if module_path is not None else cases_dir(profile, config_dir),
        fixtures_dir(profile, config_dir),
    ):
        directory.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if module_path is not None and (overwrite or not module_path.exists()):
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text(
            CASE_TEMPLATE.format(
                description=description or f"E2E case {resolved_case}.",
                case_id=resolved_case,
                suite=suite,
                start_path=start_path,
            ),
            encoding="utf-8",
        )
    payload["mode"] = "execute"
    payload["suite_path"] = str(manifest_path)
    if module_path is not None:
        payload["module_path"] = str(module_path)
    if manifest["cases"]:
        payload["cases"] = [spec.to_payload() for spec in load_suite(profile, suite, config_dir).cases]
    else:
        # A suite shell with no case yet is a legitimate halfway point - the caller is about
        # to add the first one. It just cannot be loaded as a runnable suite.
        payload["cases"] = []
        payload["note"] = (
            f"Suite {suite!r} exists but declares no case yet. Call bubble_e2e_scaffold again "
            "with case_id to add the first one."
        )
    return cast("dict[str, Any]", redact_sensitive(payload))
