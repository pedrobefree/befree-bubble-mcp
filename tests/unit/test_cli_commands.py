import json
from pathlib import Path

from bubble_mcp.cli.main import main
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.sessions.store import session_from_payload


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def test_cli_context_summary(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["context", "summary", "--file", str(FIXTURE)]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["summary"]["app_id"] == "synthetic-app"


def test_cli_context_find_exact_avoids_fuzzy_matches(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["context", "find", "user email", "--file", str(FIXTURE), "--exact"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["results"] == []

    assert main(["context", "find", "page:index", "--file", str(FIXTURE), "--exact", "--no-include-metadata"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["results"][0]["id"] == "page:index"
    assert payload["results"][0]["match"] == "exact"
    assert "metadata" not in payload["results"][0]


def test_cli_profile_status_reports_existing_profile(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile="client",
            profiles={"client": BubbleProfile(name="client", app_id="client-app", appname="client-app")},
        )
    )

    assert main(["profile", "status", "--profile", "client"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert payload["profile"]["app_id"] == "client-app"


def test_cli_plan_outputs_validated_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["plan", 'Create text saying "Hello"']) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["args"]["content"] == "Hello"


def test_cli_import_html_outputs_validated_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["import", "html", "--file", "tests/fixtures/html/login-card.html"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["tool_name"] == "create_group"


def test_cli_import_html_can_compile_to_write_payloads(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "import",
                "html",
                "--file",
                "tests/fixtures/html/login-card.html",
                "--compile",
                "--app-id",
                "synthetic-app",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Group"


def test_cli_import_html_runtime_uses_aria_importer(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "engine": "aria_runtime", "write_count": 1, "executed": kwargs["execute"]}

    monkeypatch.setattr("bubble_mcp.cli.main.create_from_html_runtime", fake_create_from_html_runtime)

    assert (
        main(
            [
                "import",
                "html",
                "--file",
                "tests/fixtures/html/login-card.html",
                "--runtime",
                "--profile",
                "smoke",
                "--context",
                "index",
                "--parent",
                "root",
                "--execute",
                "--selector",
                "section",
                "--translate-to-existing-styles",
                "--refresh-context",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["engine"] == "aria_runtime"
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["html_file"] == "tests/fixtures/html/login-card.html"
    assert calls[0]["execute"] is True
    assert calls[0]["selector"] == "section"
    assert calls[0]["translate_to_existing_styles"] is True
    assert calls[0]["refresh_context"] is True


def test_cli_import_html_runtime_accepts_url(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_from_html_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "engine": "aria_runtime", "write_count": 1, "executed": kwargs["execute"]}

    monkeypatch.setattr("bubble_mcp.cli.main.create_from_html_runtime", fake_create_from_html_runtime)

    assert (
        main(
            [
                "import",
                "html",
                "--url",
                "https://example.test/page.html",
                "--profile",
                "smoke",
                "--context",
                "index",
                "--parent",
                "root",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["engine"] == "aria_runtime"
    assert calls[0]["html_file"] == "https://example.test/page.html"


def test_cli_smoke_runtime_runs_coverage_suite(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["smoke", "runtime", "--suite", "coverage"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["failed"] == 0
    assert [result["tool"] for result in payload["results"]] == [
        "bubble_tool_coverage",
        "bubble_catalog_quality",
    ]


def test_cli_smoke_runtime_writes_report(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    report = tmp_path / "runtime-smoke.json"

    assert main(["smoke", "runtime", "--suite", "coverage", "--report", str(report)]) == 0

    payload = json.loads(capsys.readouterr().out)
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["ok"] is True
    assert saved["summary"] == payload["summary"]


def test_cli_smoke_runtime_execute_write_requires_execute(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["smoke", "runtime", "--suite", "execute-write", "--profile", "cliente2"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "execute-write requires execute=true."


def test_cli_tools_guide_routes_task_without_catalog_dump(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "guide",
                "--task",
                "Convert an HTML selector from a URL into a Bubble page and then inspect the changelog.",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["direct_tool_policy"]["avoid_shell_cli_discovery"] is True
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert "import_html_component" in intents
    assert "branches_or_changelog" in intents


def test_cli_tools_search_returns_compact_matches(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "search", "--query", "html selector import", "--limit", "5"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["limit"] == 5
    names = [match["name"] for match in payload["matches"]]
    assert "create_from_html" in names
    match = next(match for match in payload["matches"] if match["name"] == "create_from_html")
    assert "selector" in match["properties"]
    assert match["required"] == ["profile", "context", "parent"]


def test_cli_tools_recipe_returns_operational_sequence(capsys) -> None:  # type: ignore[no-untyped-def]
    assert (
        main(
            [
                "tools",
                "recipe",
                "--task",
                "Convert #home-area from a URL into page mcp-01",
                "--profile",
                "smoke",
                "--context",
                "mcp-01",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "html_import"
    assert payload["inputs"]["profile"] == "smoke"
    assert payload["inputs"]["context"] == "mcp-01"
    assert [step["tool"] for step in payload["steps"]] == [
        "bubble_context_detect",
        "create_from_html",
        "create_from_html",
    ]


def test_cli_tools_coverage_reports_runtime_paths(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "coverage"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["aria_catalog"]["uncovered_count"] == 0
    assert payload["uncovered_count"] == 0
    assert payload["tool_count"] >= payload["aria_catalog_count"]
    assert "tools" not in payload

    assert main(["tools", "coverage", "--include-tools"]) == 0
    detailed = json.loads(capsys.readouterr().out)
    assert len(detailed["tools"]) == detailed["tool_count"]


def test_cli_tools_quality_reports_catalog_gate(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "quality"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["issue_count"] == 0
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["tool_descriptions"]["ok"] is True
    assert checks["tool_annotations"]["ok"] is True
    assert checks["runtime_coverage"]["aria_uncovered_count"] == 0
    assert checks["runtime_coverage"]["uncovered_count"] == 0


def test_cli_readiness_runs_recommended_sequence(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["readiness"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"] == {"checks": 3, "passed": 3, "failed": 0}
    assert [check["name"] for check in payload["checks"]] == [
        "health",
        "catalog_gate",
        "agent_routing",
    ]


def test_cli_tools_recipe_routes_page_creation_before_generic_create(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["tools", "recipe", "--task", "Create a new page called mcp-02", "--profile", "smoke"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "page_or_reusable"
    assert "create_page" in payload["matched"]["tools"]
    intents = {route["intent"] for route in payload["recommended_routes"]}
    assert "manage_pages_or_reusables" in intents


def test_cli_session_import_and_list(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    session_path = tmp_path / "session.json"
    session_path.write_text(
        json.dumps(
            {
                "appId": "synthetic-app",
                "url": "https://bubble.io/page?name=synthetic-app",
                "headers": {"Cookie": "sid=secret"},
            }
        ),
        encoding="utf-8",
    )

    assert main(["session", "import", "--profile", "dev", "--file", str(session_path)]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["session"]["headers"]["Cookie"] == "[REDACTED]"

    assert main(["session", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["sessions"][0]["profile"] == "dev"

    assert main(["session", "inspect", "--profile", "dev"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["cookie_present"] is True
    assert inspected["session"]["headers"]["Cookie"] == "[REDACTED]"
    assert inspected["computed_write_headers"]["cookie"] == "[REDACTED]"
    assert "x-bubble-appname" in inspected["computed_write_header_keys"]


def test_cli_session_login_reports_progress_on_stderr(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    def fake_capture_session_with_playwright(**kwargs):  # type: ignore[no-untyped-def]
        kwargs["progress"]("Session cookies detected. You can close the browser now.")
        return session_from_payload(
            {
                "appId": kwargs["app_id"],
                "url": "https://bubble.io/page?id=synthetic-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "test"},
                "appVersion": "test",
                "source": "browser",
            }
        )

    monkeypatch.setattr("bubble_mcp.cli.main.capture_session_with_playwright", fake_capture_session_with_playwright)

    assert main(["profile", "add", "dev", "--app-id", "synthetic-app"]) == 0
    capsys.readouterr()
    assert main(["session", "login", "--profile", "dev", "--app-id", "synthetic-app"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["ok"] is True
    assert "[bubble-mcp session] Session cookies detected." in captured.err
    assert "[bubble-mcp session] Session saved for profile 'dev'" in captured.err


def test_cli_session_login_quiet_suppresses_progress(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    def fake_capture_session_with_playwright(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["progress"] is None
        return session_from_payload(
            {
                "appId": kwargs["app_id"],
                "url": "https://bubble.io/page?id=synthetic-app",
                "headers": {"Cookie": "sid=secret", "User-Agent": "test"},
                "appVersion": "test",
                "source": "browser",
            }
        )

    monkeypatch.setattr("bubble_mcp.cli.main.capture_session_with_playwright", fake_capture_session_with_playwright)

    assert main(["profile", "add", "dev", "--app-id", "synthetic-app"]) == 0
    capsys.readouterr()
    assert main(["session", "login", "--profile", "dev", "--app-id", "synthetic-app", "--quiet"]) == 0
    captured = capsys.readouterr()

    assert json.loads(captured.out)["ok"] is True
    assert captured.err == ""


def test_cli_branch_create_passes_sub_branch_source(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_create_bubble_branch(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "request": {"payload": kwargs}}

    monkeypatch.setattr("bubble_mcp.cli.main.create_bubble_branch", fake_create_bubble_branch)

    assert (
        main(
            [
                "branch",
                "create",
                "--profile",
                "smoke",
                "--name",
                "sub-feature",
                "--from-app-version",
                "parent-branch",
                "--description",
                "child branch",
                "--execute",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["name"] == "sub-feature"
    assert calls[0]["from_app_version"] == "parent-branch"
    assert calls[0]["execute"] is True


def test_cli_changelog_fetch_builds_filters(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_fetch_changelog_entries(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "entries": []}

    monkeypatch.setattr("bubble_mcp.cli.main.fetch_changelog_entries", fake_fetch_changelog_entries)

    assert (
        main(
            [
                "changelog",
                "fetch",
                "--profile",
                "smoke",
                "--app-version",
                "test",
                "--start-index",
                "50",
                "--num-fetch",
                "25",
                "--change-type",
                "Data",
                "--change-path",
                "user_types.user.",
                "--user-id",
                "user-1",
                "--user-id",
                "user-2",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["app_version"] == "test"
    assert calls[0]["start_index"] == 50
    assert calls[0]["num_fetch"] == 25
    assert calls[0]["filters"] == {
        "type": "Data",
        "change_path": "user_types.user.",
        "user_id": ["user-1", "user-2"],
    }


def test_cli_compile_plan_outputs_write_payload(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "tool_name": "create_text",
                        "args": {"context": "index", "content": "Hello"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert main(["compile-plan", "--file", str(plan_path), "--app-id", "synthetic-app"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert first_change(payload["plan"]["steps"][0]["args"]["write_payload"], "CreateElement")["body"]["%x"] == "Text"


def test_cli_compile_plan_uses_context_file_for_editor_paths(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    plan_path = tmp_path / "plan.json"
    context_path = tmp_path / "context.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "tool_name": "create_text",
                        "args": {"context": "index", "parent": "Card", "content": "Hello"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    context_path.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "nodes": [
                    {
                        "id": "page:index",
                        "label": "index",
                        "type": "page",
                        "metadata": {"bubble_id": "pgIndex", "path_array": ["%p3", "pgIndex"]},
                    },
                    {
                        "id": "element:elCard",
                        "label": "Card",
                        "type": "element",
                        "metadata": {"bubble_id": "elCard", "path_array": ["%p3", "pgIndex", "%el", "elCard"]},
                    },
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "compile-plan",
                "--file",
                str(plan_path),
                "--app-id",
                "synthetic-app",
                "--context-file",
                str(context_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    write_payload = payload["plan"]["steps"][0]["args"]["write_payload"]
    create_change = first_change(write_payload, "CreateElement")
    assert create_change["path_array"][:4] == ["%p3", "pgIndex", "%el", "elCard"]
    assert write_payload["changes"][0]["body"].startswith("%p3.pgIndex.%el.elCard.%el.")
    assert first_change(write_payload, "Update index")["path_array"][:2] == ["_index", "id_to_path"]
    assert any(change["path_array"] == ["_index", "issues_sub", "elCard"] for change in write_payload["changes"])


def test_cli_execute_plan_compile_uses_context_file_in_preview(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    plan_path = tmp_path / "plan.json"
    context_path = tmp_path / "context.json"
    plan_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "tool_name": "create_text",
                        "args": {"context": "index", "content": "Hello"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    context_path.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "nodes": [
                    {
                        "id": "page:index",
                        "label": "index",
                        "type": "page",
                        "metadata": {"bubble_id": "pgIndex", "path_array": ["%p3", "pgIndex"]},
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "execute-plan",
                "--profile",
                "dev",
                "--file",
                str(plan_path),
                "--app-id",
                "synthetic-app",
                "--compile",
                "--context-file",
                str(context_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    write_payload = payload["results"][0]["payload"]
    create_change = first_change(write_payload, "CreateElement")
    assert create_change["path_array"][:2] == ["%p3", "pgIndex"]
