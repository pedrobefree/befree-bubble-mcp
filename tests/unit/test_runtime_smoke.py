from bubble_mcp.runtime_smoke import build_runtime_smoke_cases, run_runtime_smoke


def test_execute_write_requires_explicit_execute() -> None:
    report = run_runtime_smoke(lambda _tool, _args: {"ok": True}, suite="execute-write", profile="cliente2")

    assert report["ok"] is False
    assert report["error"] == "execute-write requires execute=true."
    assert report["summary"]["failed"] == 1
    assert report["results"] == []


def test_execute_write_cases_use_unique_target_page_and_execute_flag() -> None:
    cases = build_runtime_smoke_cases(
        suite="execute-write",
        profile="cliente2",
        app_id="courselaunch",
        app_version="test",
        execute=True,
        run_id="manual run",
    )

    write_cases = [case for case in cases if case.suite == "execute-write"]
    assert [case.tool for case in write_cases[:5]] == [
        "create_page",
        "create_group",
        "create_text",
        "create_button",
        "create_input",
    ]
    assert write_cases[0].arguments["name"] == "mcp_smoke_manual_run"
    assert all(case.arguments["execute"] is True for case in write_cases)
    assert all(case.arguments.get("app_id") == "courselaunch" for case in write_cases)
    assert write_cases[1].arguments["context"] == "mcp_smoke_manual_run"
    assert write_cases[1].arguments["parent"] == "root"
    assert write_cases[2].arguments["name"] == "tx_mcp_smoke_manual_run"
    assert write_cases[2].arguments["fit_height"] is True
    assert write_cases[3].arguments["fit_width"] is True
    assert write_cases[3].arguments["fit_height"] is True


def test_execute_write_can_append_cleanup_case() -> None:
    cases = build_runtime_smoke_cases(
        suite="execute-write",
        profile="cliente2",
        execute=True,
        cleanup=True,
        run_id="cleanup",
    )

    cleanup = cases[-1]
    assert cleanup.tool == "delete_page"
    assert cleanup.arguments["name"] == "mcp_smoke_cleanup"
    assert cleanup.arguments["execute"] is True
    assert cleanup.arguments["confirm"] is True


def test_execute_write_runs_call_sequence() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        return {"ok": True, "executed": args.get("execute"), "write_count": 1}

    report = run_runtime_smoke(
        fake_tool,
        suite="execute-write",
        profile="cliente2",
        execute=True,
        run_id="sequence",
    )

    assert report["ok"] is True
    assert report["execute"] is True
    assert report["run_id"] == "sequence"
    assert report["summary"]["failed"] == 0
    assert [tool for tool, _args in calls[:6]] == [
        "bubble_tool_coverage",
        "bubble_health_check",
        "bubble_profile_list",
        "bubble_session_list",
        "list_data_types",
        "list_styles",
    ]
    assert calls[-4][1]["context"] == "mcp_smoke_sequence"
    assert all(args.get("execute") is True for _tool, args in calls[-5:])
