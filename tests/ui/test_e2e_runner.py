"""The one path of the E2E harness that needs a real browser and a real app.

Everything else about the harness is decided offline and covered in tests/unit: manifest
parsing, branch and base-URL resolution, session validation, result assembly, redaction. What
is left here is the part no stub can prove - that the runner actually opens a browser, loads
the impersonated session, runs a case and writes artifacts.

It skips itself unless a profile and a suite are named, because pointing this file at a
hardcoded app would send every other installation at somebody else's Bubble account. It is not
part of the default suite's contract and must not run in CI: a green run creates real records
in the app it drives.
"""

from __future__ import annotations

import os

import pytest

from bubble_mcp.e2e.report import read_e2e_report
from bubble_mcp.e2e.runner import run_e2e_suite

PROFILE_ENV = "BUBBLE_UI_PROFILE"
SUITE_ENV = "BUBBLE_UI_E2E_SUITE"
CASE_ENV = "BUBBLE_UI_E2E_CASE"
EXECUTE_ENV = "BUBBLE_UI_E2E_EXECUTE"


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


@pytest.fixture
def configured_suite() -> tuple[str, str]:
    profile = _env(PROFILE_ENV)
    suite = _env(SUITE_ENV)
    if not profile or not suite:
        pytest.skip(f"Set {PROFILE_ENV} and {SUITE_ENV} to run the E2E harness against an app.")
    return profile, suite


def test_preview_resolves_a_real_suite_without_opening_a_browser(
    configured_suite: tuple[str, str],
) -> None:
    """The preview path, which is safe to run anywhere the suite is declared."""

    profile, suite = configured_suite

    result = run_e2e_suite(profile=profile, suite=suite)

    assert result["mode"] == "preview"
    assert result["results"] == []
    assert result["target"]["base_url"].startswith("http")
    assert result["planned_cases"], "a declared suite should plan at least one case"
    blocking = [item for item in result["blockers"] if item.get("severity") != "warning"]
    assert not blocking, f"suite cannot run: {blocking}"


def test_a_case_runs_in_a_browser_and_leaves_readable_artifacts(
    configured_suite: tuple[str, str],
) -> None:
    """The real thing. Opt-in twice over, because passing cases write to the app."""

    if _env(EXECUTE_ENV).lower() not in {"1", "true", "yes"}:
        pytest.skip(
            f"Set {EXECUTE_ENV}=true to drive the browser. This creates real records in the "
            "app under test."
        )
    pytest.importorskip(
        "playwright.sync_api",
        reason='Install with: pip install "befree-bubble-mcp[browser]" && playwright install chromium',
    )
    profile, suite = configured_suite
    case = _env(CASE_ENV)

    result = run_e2e_suite(
        profile=profile,
        suite=suite,
        cases=[case] if case else (),
        execute=True,
        headless=True,
        video=False,
        cursor=False,
    )

    assert result["ok"], result
    assert result["summary"]["passed"] >= 1
    first = result["results"][0]
    assert first["status"] == "passed"
    assert first["steps"], "a case should report at least one named step"
    assert first["artifacts"]["dir"]

    # The report must recover the same run without running anything again.
    replayed = read_e2e_report(profile=profile, run_id=result["run_id"])
    assert replayed["ok"] is True
    assert replayed["summary"] == result["summary"]
    assert [item["case_id"] for item in replayed["results"]] == [
        item["case_id"] for item in result["results"]
    ]
