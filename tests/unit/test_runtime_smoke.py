import json

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


def test_execute_write_can_verify_refreshed_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context_file = tmp_path / "context.json"
    context_file.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "nodes": [
                    {
                        "id": "page:mcp_smoke_verify",
                        "label": "mcp_smoke_verify",
                        "type": "page",
                        "metadata": {"children": ["gp1", "tx1", "bt1", "in1"]},
                    },
                    {
                        "id": "element:gp1",
                        "label": "gp1",
                        "type": "element",
                        "metadata": {
                            "bubble_id": "gp1",
                            "context": "page:mcp_smoke_verify",
                            "element_type": "Group",
                            "properties": {"container_layout": "column", "fit_height": True},
                        },
                    },
                    {
                        "id": "element:tx1",
                        "label": "tx1",
                        "type": "element",
                        "metadata": {
                            "bubble_id": "tx1",
                            "context": "page:mcp_smoke_verify",
                            "element_type": "Text",
                            "properties": {"fit_height": True, "text": {"entries": {"0": "Runtime smoke verify"}}},
                        },
                    },
                    {
                        "id": "element:bt1",
                        "label": "bt1",
                        "type": "element",
                        "metadata": {
                            "bubble_id": "bt1",
                            "context": "page:mcp_smoke_verify",
                            "element_type": "Button",
                            "properties": {
                                "fit_width": True,
                                "fit_height": True,
                                "text": {"entries": {"0": "Runtime smoke"}},
                            },
                        },
                    },
                    {
                        "id": "element:in1",
                        "label": "in1",
                        "type": "element",
                        "metadata": {
                            "bubble_id": "in1",
                            "context": "page:mcp_smoke_verify",
                            "element_type": "Input",
                            "properties": {
                                "fixed_height": True,
                                "placeholder": {"entries": {"0": "Runtime smoke"}},
                            },
                        },
                    },
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        if tool == "bubble_context_detect":
            return {"ok": True, "context_path": str(context_file)}
        return {"ok": True, "executed": args.get("execute"), "write_count": 1}

    report = run_runtime_smoke(
        fake_tool,
        suite="execute-write",
        profile="cliente2",
        execute=True,
        run_id="verify",
        verify_context=True,
        verification_output=str(tmp_path / "detected-context.json"),
    )

    assert report["ok"] is True
    assert report["summary"]["passed"] == 15
    assert calls[-1] == (
        "bubble_context_detect",
        {
            "profile": "cliente2",
            "app_version": "test",
            "force": True,
            "output": str(tmp_path / "detected-context.json"),
        },
    )
    assert report["results"][-1]["suite"] == "post-write-verify"
    assert report["results"][-1]["status"] == "passed"
