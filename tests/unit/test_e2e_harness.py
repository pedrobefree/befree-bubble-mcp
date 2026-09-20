"""Unit cover for the E2E harness: everything that decides a run, none of the browser.

The point of splitting these off is that the parts most likely to be wrong - a manifest that
lies, a branch that resolves to the wrong version, an expired session reported as healthy, a
cookie leaking into a result - are all decidable offline. A machine with no Playwright still
runs every test in this file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.e2e import paths, report, runner, scaffold, target
from bubble_mcp.e2e import suite as suite_module

KAIMIA_USER = "1784116269914x334073322121781100"


def _settings(tmp_path: Path, *, app_version: str = "93k8b") -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "settings.json").write_text(
        json.dumps(
            {
                "default_profile": "kaimia",
                "profiles": {
                    "kaimia": {
                        "app_id": "kaimia-app",
                        "appname": "kaimia-app",
                        "app_version": app_version,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _manifest(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "kaimia-ks1",
        "profile": "kaimia",
        "base_url": "https://app.kaimia.org.au",
        "run_as": {"user_id": KAIMIA_USER},
        "cases": [
            {"id": "ks1-t23", "description": "Note card layout", "module": "ks1_t23_notes.py",
             "tags": ["notes", "layout"]},
            {"id": "ks1-t29", "description": "Org documents", "module": "ks1_t29_org.py",
             "tags": ["documents"]},
        ],
    }
    payload.update(overrides)
    return payload


def _write_storage_state(config_dir: Path, *, expires: float) -> Path:
    path = config_dir / "run-as" / f"kaimia-kaimia-app-{KAIMIA_USER}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "u0",
                        "value": "super-secret-session-cookie",
                        "domain": "app.kaimia.org.au",
                        "path": "/",
                        "expires": expires,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    return path


# -- manifest parsing ---------------------------------------------------------------


def test_parse_suite_reads_cases_and_defaults() -> None:
    parsed = suite_module.parse_suite(_manifest())

    assert parsed.name == "kaimia-ks1"
    assert [spec.case_id for spec in parsed.cases] == ["ks1-t23", "ks1-t29"]
    assert parsed.base_url == "https://app.kaimia.org.au"
    assert parsed.user_id == KAIMIA_USER
    assert parsed.viewport == (1440, 900)
    assert parsed.headless is True and parsed.video is False and parsed.timeout_ms == 30_000


def test_parse_suite_reads_explicit_defaults() -> None:
    parsed = suite_module.parse_suite(
        _manifest(
            viewport={"width": 1280, "height": 720},
            defaults={"headless": False, "video": True, "cursor": "yes", "slow_mo": 650,
                      "timeout_ms": 60_000},
        )
    )

    assert parsed.viewport == (1280, 720)
    assert (parsed.headless, parsed.video, parsed.cursor) == (False, True, True)
    assert (parsed.slow_mo, parsed.timeout_ms) == (650, 60_000)


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"profile": "kaimia", "cases": [{"id": "a", "module": "a.py"}]}, "missing 'name'"),
        ({"name": "s", "cases": [{"id": "a", "module": "a.py"}]}, "missing 'profile'"),
        ({"name": "s", "profile": "p"}, "non-empty 'cases' list"),
        ({"name": "s", "profile": "p", "cases": []}, "non-empty 'cases' list"),
        ({"name": "s", "profile": "p", "cases": [{"module": "a.py"}]}, "missing 'id'"),
        ({"name": "s", "profile": "p", "cases": [{"id": "a"}]}, "missing 'module'"),
        (
            {"name": "s", "profile": "p", "cases": [{"id": "a", "module": "a.py", "params": []}]},
            "'params' must be an object",
        ),
        (
            {"name": "s", "profile": "p", "cases": [{"id": "a", "module": "a.py", "tags": 3}]},
            "'tags' must be a list",
        ),
        (["not", "an", "object"], "must be a JSON object"),
    ],
)
def test_parse_suite_rejects_broken_manifests(payload: Any, fragment: str) -> None:
    with pytest.raises(suite_module.E2ESuiteError) as error:
        suite_module.parse_suite(payload)

    assert fragment in str(error.value)


def test_parse_suite_rejects_duplicate_case_ids() -> None:
    payload = _manifest(
        cases=[
            {"id": "ks1-t23", "module": "a.py"},
            {"id": "KS1_T23", "module": "b.py"},
        ]
    )

    with pytest.raises(suite_module.E2ESuiteError, match="twice"):
        suite_module.parse_suite(payload)


def test_select_narrows_by_id_then_tag_then_everything() -> None:
    parsed = suite_module.parse_suite(_manifest())

    assert [spec.case_id for spec in parsed.select()] == ["ks1-t23", "ks1-t29"]
    assert [spec.case_id for spec in parsed.select(["ks1-t29"])] == ["ks1-t29"]
    assert [spec.case_id for spec in parsed.select(tags=["LAYOUT"])] == ["ks1-t23"]


def test_select_names_the_known_cases_when_an_id_is_wrong() -> None:
    parsed = suite_module.parse_suite(_manifest())

    with pytest.raises(suite_module.E2ESuiteError) as error:
        parsed.select(["ks1-t99"])

    assert "ks1-t23" in str(error.value) and "ks1-t29" in str(error.value)


def test_load_suite_points_at_the_scaffold_tool_when_nothing_is_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    with pytest.raises(suite_module.E2ESuiteError) as error:
        suite_module.load_suite("kaimia", "kaimia-ks1")

    assert "bubble_e2e_scaffold" in str(error.value)


def test_list_suites_skips_an_unreadable_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    directory = paths.suites_dir("kaimia")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "good.suite.json").write_text(json.dumps(_manifest(name="good")), encoding="utf-8")
    (directory / "broken.suite.json").write_text("{not json", encoding="utf-8")

    assert [item.name for item in suite_module.list_suites("kaimia")] == ["good"]


# -- path safety --------------------------------------------------------------------


def test_resolve_case_module_accepts_a_plain_relative_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    resolved = paths.resolve_case_module("kaimia", "ks1_t23_notes.py")

    assert resolved == paths.cases_dir("kaimia") / "ks1_t23_notes.py"


def test_resolve_case_module_tolerates_a_cases_prefix_and_a_missing_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    assert paths.resolve_case_module("kaimia", "cases/ks1_t23") == (
        paths.cases_dir("kaimia") / "ks1_t23.py"
    )


@pytest.mark.parametrize(
    "module_ref",
    ["../../settings.json", "/etc/passwd", "C:\\Windows\\system32\\evil.py", "a/../../b.py", ""],
)
def test_resolve_case_module_refuses_to_escape_the_cases_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module_ref: str
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    with pytest.raises(ValueError):
        paths.resolve_case_module("kaimia", module_ref)


def test_safe_run_id_strips_anything_that_could_walk_the_runs_directory() -> None:
    assert paths.safe_run_id("../../etc/passwd") == "etc_passwd"
    assert paths.safe_run_id("  ") != ""
    assert len(paths.safe_run_id("x" * 200)) == 40


# -- target resolution --------------------------------------------------------------


def test_resolve_target_prefers_the_suite_base_url_and_the_profile_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)
    parsed = suite_module.parse_suite(_manifest())

    resolved = target.resolve_target(parsed)

    assert resolved.base_url == "https://app.kaimia.org.au/version-93k8b"
    assert (resolved.base_url_origin, resolved.branch_origin) == ("suite", "profile")
    assert resolved.app_id == "kaimia-app"


def test_resolve_target_lets_the_call_override_the_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)
    parsed = suite_module.parse_suite(_manifest(branch="live-check"))

    assert target.resolve_target(parsed).branch == "live-check"
    assert target.resolve_target(parsed, branch="hotfix").branch == "hotfix"
    assert target.resolve_target(parsed, branch="hotfix").branch_origin == "call"


def test_resolve_target_falls_back_to_the_bubbleapps_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path, app_version="")
    parsed = suite_module.parse_suite(_manifest(base_url=""))

    resolved = target.resolve_target(parsed)

    assert resolved.base_url == "https://kaimia-app.bubbleapps.io/version-test"
    assert (resolved.base_url_origin, resolved.branch_origin) == ("bubbleapps", "default")


def test_resolve_target_flags_a_guessed_custom_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)
    export = tmp_path / "config" / "contexts" / "kaimia" / "kaimia-app.bubble"
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_text(
        json.dumps(
            {
                "settings": {
                    "client_safe": {
                        "redirect_all_to_domain": True,
                        "app_topdomain": "kaimia.org.au",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    parsed = suite_module.parse_suite(_manifest(base_url=""))

    resolved = target.resolve_target(parsed)

    assert resolved.base_url == "https://app.kaimia.org.au/version-93k8b"
    assert resolved.base_url_origin == "app_topdomain_guess"
    assert any("base_url" in warning for warning in resolved.warnings)


def test_resolve_target_refuses_a_suite_with_no_app_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "settings.json").write_text(json.dumps({"profiles": {}}), encoding="utf-8")
    parsed = suite_module.parse_suite(_manifest(profile="unknown"))

    with pytest.raises(ValueError, match="bubble_project_bootstrap"):
        target.resolve_target(parsed)


def test_url_building_joins_path_and_query_without_a_hardcoded_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)
    resolved = target.resolve_target(suite_module.parse_suite(_manifest()))

    assert resolved.url("/admin/clients") == "https://app.kaimia.org.au/version-93k8b/admin/clients"
    assert resolved.url() == "https://app.kaimia.org.au/version-93k8b"


# -- session checks -----------------------------------------------------------------


def test_check_run_as_session_accepts_a_live_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    future = (datetime.now(UTC) + timedelta(days=1)).timestamp()
    _write_storage_state(tmp_path / "config", expires=future)

    status = target.check_run_as_session("kaimia", "kaimia-app", KAIMIA_USER)

    assert status.ok is True
    assert status.expires_at is not None


def test_check_run_as_session_reports_an_expired_session_with_the_tool_to_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    past = (datetime.now(UTC) - timedelta(hours=2)).timestamp()
    _write_storage_state(tmp_path / "config", expires=past)

    status = target.check_run_as_session("kaimia", "kaimia-app", KAIMIA_USER)

    assert status.ok is False
    assert status.reason == "expired"
    assert status.next_action["tool"] == "bubble_run_as"
    assert "bubble_run_as" in status.message


def test_check_run_as_session_reports_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    status = target.check_run_as_session("kaimia", "kaimia-app", KAIMIA_USER)

    assert (status.ok, status.reason) == (False, "missing")
    assert status.next_action["arguments"]["user_id"] == KAIMIA_USER


def test_check_run_as_session_reports_an_empty_jar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    path = tmp_path / "config" / "run-as" / f"kaimia-kaimia-app-{KAIMIA_USER}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")

    status = target.check_run_as_session("kaimia", "kaimia-app", KAIMIA_USER)

    assert (status.ok, status.reason) == (False, "empty")


def test_check_run_as_session_reports_an_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    path = tmp_path / "config" / "run-as" / f"kaimia-kaimia-app-{KAIMIA_USER}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ truncated", encoding="utf-8")

    status = target.check_run_as_session("kaimia", "kaimia-app", KAIMIA_USER)

    assert (status.ok, status.reason) == (False, "unreadable")


def test_check_run_as_session_says_which_field_is_missing_when_the_suite_names_no_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    status = target.check_run_as_session("kaimia", "kaimia-app", "")

    assert (status.ok, status.reason) == (False, "no_user")
    assert "run_as" in status.message


def test_a_session_status_never_carries_a_cookie_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    future = (datetime.now(UTC) + timedelta(days=1)).timestamp()
    _write_storage_state(tmp_path / "config", expires=future)

    payload = json.dumps(target.check_run_as_session("kaimia", "kaimia-app", KAIMIA_USER).to_payload())

    assert "super-secret-session-cookie" not in payload


# -- the runner, without a browser --------------------------------------------------


def _install_suite(tmp_path: Path, *, with_modules: bool = True, **overrides: Any) -> None:
    _settings(tmp_path)
    directory = paths.suites_dir("kaimia")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "kaimia-ks1.suite.json").write_text(
        json.dumps(_manifest(**overrides)), encoding="utf-8"
    )
    if with_modules:
        cases = paths.cases_dir("kaimia")
        cases.mkdir(parents=True, exist_ok=True)
        for name in ("ks1_t23_notes.py", "ks1_t29_org.py"):
            (cases / name).write_text("def run(ctx):\n    return None\n", encoding="utf-8")


def test_preview_is_the_default_and_opens_no_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _install_suite(tmp_path)
    _write_storage_state(tmp_path / "config", expires=(datetime.now(UTC) + timedelta(days=1)).timestamp())

    result = runner.run_e2e_suite(profile="kaimia", suite="kaimia-ks1")

    assert result["mode"] == "preview"
    assert result["execute"] is False
    assert result["results"] == []
    assert [plan["case_id"] for plan in result["planned_cases"]] == ["ks1-t23", "ks1-t29"]
    assert all(plan["ok"] for plan in result["planned_cases"])


def test_preview_reports_a_missing_case_module_as_a_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _install_suite(tmp_path, with_modules=False)
    _write_storage_state(tmp_path / "config", expires=(datetime.now(UTC) + timedelta(days=1)).timestamp())

    result = runner.run_e2e_suite(profile="kaimia", suite="kaimia-ks1")

    assert result["ok"] is False
    checks = {blocker["check"] for blocker in result["blockers"]}
    assert "case_modules" in checks


def test_preview_reports_an_expired_session_as_a_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _install_suite(tmp_path)
    _write_storage_state(tmp_path / "config", expires=(datetime.now(UTC) - timedelta(days=1)).timestamp())

    result = runner.run_e2e_suite(profile="kaimia", suite="kaimia-ks1")

    blocker = next(item for item in result["blockers"] if item["check"] == "run_as_session")
    assert blocker["next_action"]["tool"] == "bubble_run_as"
    assert result["ok"] is False


def test_execute_refuses_to_start_while_a_blocker_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _install_suite(tmp_path)

    result = runner.run_e2e_suite(profile="kaimia", suite="kaimia-ks1", execute=True)

    assert result["ok"] is False
    assert result["mode"] == "execute"
    assert "bubble_run_as" in result["error"]
    assert result["results"] == []


def test_a_broken_manifest_comes_back_as_a_result_not_an_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)

    result = runner.run_e2e_suite(profile="kaimia", suite="nope")

    assert result["ok"] is False
    assert "bubble_e2e_scaffold" in result["error"]


def test_selecting_by_tag_narrows_the_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _install_suite(tmp_path)
    _write_storage_state(tmp_path / "config", expires=(datetime.now(UTC) + timedelta(days=1)).timestamp())

    result = runner.run_e2e_suite(profile="kaimia", suite="kaimia-ks1", tags=["documents"])

    assert [plan["case_id"] for plan in result["planned_cases"]] == ["ks1-t29"]


def test_load_case_callable_requires_a_run_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    cases = paths.cases_dir("kaimia")
    cases.mkdir(parents=True, exist_ok=True)
    (cases / "no_entry.py").write_text("VALUE = 1\n", encoding="utf-8")
    spec = suite_module.E2ECaseSpec(case_id="x", description="", module="no_entry.py")

    with pytest.raises(suite_module.E2ESuiteError, match="run\\(ctx\\)"):
        runner.load_case_callable("kaimia", spec)


def test_load_case_callable_reflects_an_edit_between_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    cases = paths.cases_dir("kaimia")
    cases.mkdir(parents=True, exist_ok=True)
    module = cases / "editable.py"
    module.write_text("def run(ctx):\n    return 'first'\n", encoding="utf-8")
    spec = suite_module.E2ECaseSpec(case_id="x", description="", module="editable.py")

    assert runner.load_case_callable("kaimia", spec)(None) == "first"  # type: ignore[arg-type]
    module.write_text("def run(ctx):\n    return 'second'\n", encoding="utf-8")
    assert runner.load_case_callable("kaimia", spec)(None) == "second"  # type: ignore[arg-type]


# -- reports ------------------------------------------------------------------------


def test_report_reads_a_previous_run_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    path = paths.result_path("kaimia", "20260920120000_abc123")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ok": True,
                "suite": "kaimia-ks1",
                "summary": {"cases": 1, "passed": 1, "failed": 0},
                "results": [{"case_id": "ks1-t23", "status": "passed", "detail": "traceback"}],
            }
        ),
        encoding="utf-8",
    )

    result = report.read_e2e_report(profile="kaimia", run_id="20260920120000_abc123")

    assert result["ok"] is True
    assert result["summary"]["passed"] == 1
    assert "detail" not in result["results"][0]
    assert report.read_e2e_report(
        profile="kaimia", run_id="20260920120000_abc123", include_details=True
    )["results"][0]["detail"] == "traceback"


def test_report_lists_recent_runs_when_the_id_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    known = paths.result_path("kaimia", "20260920120000_abc123")
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text(json.dumps({"ok": True, "suite": "kaimia-ks1"}), encoding="utf-8")

    result = report.read_e2e_report(profile="kaimia", run_id="20991231235959_zzzzzz")

    assert result["ok"] is False
    assert "20260920120000_abc123" in result["recent_runs"]


def test_list_reports_suites_cases_and_whether_they_could_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _install_suite(tmp_path)
    _write_storage_state(tmp_path / "config", expires=(datetime.now(UTC) + timedelta(days=1)).timestamp())

    result = report.list_e2e_suites(profile="kaimia")

    assert result["ok"] is True
    entry = result["suites"][0]
    assert entry["name"] == "kaimia-ks1"
    assert [case["id"] for case in entry["cases"]] == ["ks1-t23", "ks1-t29"]
    assert entry["session"]["ok"] is True
    assert entry["target"]["branch"] == "93k8b"


def test_list_says_so_when_a_profile_has_no_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    result = report.list_e2e_suites(profile="kaimia")

    assert result["suites"] == []
    assert "bubble_e2e_scaffold" in result["note"]


def test_list_requires_a_profile() -> None:
    assert report.list_e2e_suites(profile="")["ok"] is False


# -- scaffold -----------------------------------------------------------------------


def test_scaffold_previews_without_writing_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    result = scaffold.scaffold_e2e(
        profile="kaimia", suite="uat", case_id="uat-01", user_id=KAIMIA_USER
    )

    assert result["mode"] == "preview"
    assert not paths.suite_path("kaimia", "uat").exists()
    assert [item["action"] for item in result["files"]] == ["create", "create"]


def test_scaffold_writes_a_runnable_suite_and_a_case_skeleton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)

    result = scaffold.scaffold_e2e(
        profile="kaimia",
        suite="uat",
        case_id="UAT 01",
        description="Tester walks the booking flow",
        tags=["booking"],
        base_url="https://app.kaimia.org.au",
        user_id=KAIMIA_USER,
        execute=True,
    )

    assert result["ok"] is True
    loaded = suite_module.load_suite("kaimia", "uat")
    assert [spec.case_id for spec in loaded.cases] == ["uat-01"]
    assert loaded.cases[0].tags == ("booking",)
    module = paths.cases_dir("kaimia") / "uat_01.py"
    assert "def run(ctx):" in module.read_text(encoding="utf-8")
    assert "bubble_context_find" in module.read_text(encoding="utf-8")


def test_scaffold_refuses_to_clobber_a_case_without_being_told_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)
    common = {
        "profile": "kaimia",
        "suite": "uat",
        "case_id": "uat-01",
        "user_id": KAIMIA_USER,
        "base_url": "https://app.kaimia.org.au",
        "execute": True,
    }
    scaffold.scaffold_e2e(**common)  # type: ignore[arg-type]

    blocked = scaffold.scaffold_e2e(**common)  # type: ignore[arg-type]
    assert blocked["ok"] is False
    assert "overwrite=true" in blocked["error"]

    allowed = scaffold.scaffold_e2e(**common, overwrite=True)  # type: ignore[arg-type]
    assert allowed["ok"] is True


def test_scaffold_adds_a_second_case_to_an_existing_suite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    _settings(tmp_path)
    base = {"profile": "kaimia", "suite": "uat", "user_id": KAIMIA_USER,
            "base_url": "https://app.kaimia.org.au", "execute": True}
    scaffold.scaffold_e2e(**base, case_id="uat-01")  # type: ignore[arg-type]
    scaffold.scaffold_e2e(**base, case_id="uat-02")  # type: ignore[arg-type]

    loaded = suite_module.load_suite("kaimia", "uat")
    assert [spec.case_id for spec in loaded.cases] == ["uat-01", "uat-02"]


def test_scaffold_requires_a_profile_and_a_suite() -> None:
    assert scaffold.scaffold_e2e(profile="", suite="uat")["ok"] is False
    assert scaffold.scaffold_e2e(profile="kaimia", suite="")["ok"] is False


# -- a suite whose cases live in the app's own repository ----------------------------


def test_cases_root_lets_a_suite_point_at_a_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    checkout = tmp_path / "kaimia" / "e2e" / "cases"
    checkout.mkdir(parents=True)
    (checkout / "ks1_t23_notes.py").write_text("def run(ctx):\n    return None\n", encoding="utf-8")

    resolved = paths.resolve_case_module(
        "kaimia", "ks1_t23_notes.py", cases_root=str(checkout)
    )

    assert resolved == checkout / "ks1_t23_notes.py"


def test_cases_root_still_refuses_to_escape_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    checkout = tmp_path / "kaimia" / "e2e" / "cases"
    checkout.mkdir(parents=True)

    with pytest.raises(ValueError, match=r"'\.\.'"):
        paths.resolve_case_module("kaimia", "../../secrets.py", cases_root=str(checkout))


def test_a_missing_cases_root_is_reported_not_silently_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    with pytest.raises(ValueError, match="not an existing directory"):
        paths.resolve_cases_root("kaimia", str(tmp_path / "gone"))


def test_fixtures_follow_the_cases_root_when_one_is_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    checkout = tmp_path / "kaimia" / "e2e" / "cases"
    (checkout / "fixtures").mkdir(parents=True)

    assert paths.resolve_fixtures_root("kaimia", str(checkout)) == checkout / "fixtures"
    assert paths.resolve_fixtures_root("kaimia") == paths.fixtures_dir("kaimia")


def test_a_run_previews_cases_from_the_declared_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    checkout = tmp_path / "kaimia" / "e2e" / "cases"
    checkout.mkdir(parents=True)
    for module in ("ks1_t23_notes.py", "ks1_t29_org.py"):
        (checkout / module).write_text("def run(ctx):\n    return None\n", encoding="utf-8")
    _settings(tmp_path)
    suites = paths.suites_dir("kaimia")
    suites.mkdir(parents=True, exist_ok=True)
    (suites / "kaimia-ks1.suite.json").write_text(
        json.dumps(_manifest(cases_root=str(checkout))), encoding="utf-8"
    )
    _write_storage_state(
        tmp_path / "config", expires=(datetime.now(UTC) + timedelta(days=1)).timestamp()
    )

    result = runner.run_e2e_suite(profile="kaimia", suite="kaimia-ks1")

    assert result["ok"] is True
    assert all(plan["ok"] for plan in result["planned_cases"])
    assert str(checkout) in result["planned_cases"][0]["module_path"]
