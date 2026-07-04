import json
from pathlib import Path

from bubble_mcp.server.tools import call_tool
from bubble_mcp.runtime_smoke import build_runtime_smoke_cases, run_runtime_smoke


def _write_execute_context(context_file: Path, run_id: str) -> None:
    page_name = f"mcp_smoke_{run_id}"
    context_file.write_text(
        json.dumps(
            {
                "app_id": "synthetic-app",
                "source": "test",
                "nodes": [
                    {
                        "id": f"page:{page_name}",
                        "label": page_name,
                        "type": "page",
                        "metadata": {"children": ["gp1", "tx1", "bt1", "in1"]},
                    },
                    {
                        "id": "element:gp1",
                        "label": "gp1",
                        "type": "element",
                        "metadata": {
                            "bubble_id": "gp1",
                            "context": f"page:{page_name}",
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
                            "context": f"page:{page_name}",
                            "element_type": "Text",
                            "properties": {"fit_height": True, "text": {"entries": {"0": f"Runtime smoke {run_id}"}}},
                        },
                    },
                    {
                        "id": "element:bt1",
                        "label": "bt1",
                        "type": "element",
                        "metadata": {
                            "bubble_id": "bt1",
                            "context": f"page:{page_name}",
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
                            "context": f"page:{page_name}",
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


def test_safe_read_includes_profile_status_and_fails_when_not_ready() -> None:
    calls: list[str] = []

    def fake_tool(tool: str, _args: dict[str, object]) -> dict[str, object]:
        calls.append(tool)
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": False, "next_actions": [{"tool": "bubble_context_detect"}]}
        return {"ok": True, "tool": tool}

    report = run_runtime_smoke(fake_tool, suite="safe-read", profile="cliente2")

    assert "bubble_profile_status" in calls
    profile_result = next(item for item in report["results"] if item["tool"] == "bubble_profile_status")
    assert profile_result["status"] == "failed"
    assert profile_result["result"]["ready"] is False
    assert profile_result["result"]["next_action_count"] == 1
    assert report["ok"] is False


def test_family_preview_covers_representative_tool_families_without_execute() -> None:
    cases = build_runtime_smoke_cases(
        suite="family-preview",
        profile="cliente2",
        app_id="courselaunch",
        app_version="test",
        run_id="families",
    )

    tools = {case.tool for case in cases if case.suite == "family-preview"}
    assert {
        "create_text",
        "create_button",
        "create_icon",
        "create_image",
        "create_html",
        "create_group",
        "create_repeating_group",
        "create_input",
        "create_dropdown",
        "create_checkbox",
        "create_data_type",
        "create_data_field",
        "create_option_set",
        "create_option_value",
        "create_color",
        "create_style",
        "create_workflow",
        "add_action",
        "create_from_html",
        "bubble_branch_list",
        "bubble_changelog_fetch",
    }.issubset(tools)
    assert all(case.arguments.get("execute") is not True for case in cases if case.suite == "family-preview")
    assert all(case.arguments.get("app_id") == "courselaunch" for case in cases if case.tool.startswith("create_"))


def test_family_preview_runs_call_sequence() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": True}
        return {"ok": True, "executed": bool(args.get("execute")), "write_count": int(tool.startswith("create_"))}

    report = run_runtime_smoke(
        fake_tool,
        suite="family-preview",
        profile="cliente2",
        app_id="courselaunch",
        run_id="families",
    )

    assert report["ok"] is True
    assert report["execute"] is False
    assert report["summary"]["failed"] == 0
    assert any(tool == "create_data_type" for tool, _args in calls)
    assert any(tool == "create_workflow" for tool, _args in calls)
    assert any(tool == "create_from_html" for tool, _args in calls)
    assert any(tool == "bubble_branch_list" for tool, _args in calls)
    assert all(args.get("execute") is not True for _tool, args in calls)


def test_agent_routing_smoke_validates_natural_language_tool_selection() -> None:
    report = run_runtime_smoke(
        call_tool,
        suite="agent-routing",
        profile="cliente2",
        context="mcp-01",
        parent="root",
    )

    assert report["ok"] is True
    assert report["execute"] is False
    assert report["summary"] == {"cases": 6, "passed": 6, "failed": 0, "skipped": 0}
    assert {result["status"] for result in report["results"]} == {"passed"}
    assert all(result["suite"] == "agent-routing" for result in report["results"])


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
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": True}
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
    assert [tool for tool, _args in calls[:8]] == [
        "bubble_tool_coverage",
        "bubble_catalog_quality",
        "bubble_health_check",
        "bubble_profile_list",
        "bubble_session_list",
        "bubble_profile_status",
        "list_data_types",
        "list_styles",
    ]
    assert calls[-4][1]["context"] == "mcp_smoke_sequence"
    assert all(args.get("execute") is True for _tool, args in calls[-5:])


def test_execute_write_can_verify_refreshed_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context_file = tmp_path / "context.json"
    _write_execute_context(context_file, "verify")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        if tool == "bubble_context_detect":
            return {"ok": True, "context_path": str(context_file)}
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": True}
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
    assert report["summary"]["passed"] == 17
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


def test_execute_write_verifies_before_cleanup(tmp_path) -> None:  # type: ignore[no-untyped-def]
    context_file = tmp_path / "context.json"
    _write_execute_context(context_file, "verify_cleanup")
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        if tool == "bubble_context_detect":
            return {"ok": True, "context_path": str(context_file)}
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": True}
        return {"ok": True, "executed": args.get("execute"), "write_count": 1}

    report = run_runtime_smoke(
        fake_tool,
        suite="execute-write",
        profile="cliente2",
        execute=True,
        cleanup=True,
        run_id="verify cleanup",
        verify_context=True,
    )

    assert report["ok"] is True
    assert report["summary"]["failed"] == 0
    assert [result["tool"] for result in report["results"][-3:]] == [
        "bubble_context_detect",
        "delete_page",
        "bubble_context_detect",
    ]
    assert [result["suite"] for result in report["results"][-3:]] == [
        "post-write-verify",
        "execute-write",
        "post-cleanup-refresh",
    ]
    assert [tool for tool, _args in calls[-3:]] == ["bubble_context_detect", "delete_page", "bubble_context_detect"]
    assert calls[-2][1]["name"] == "mcp_smoke_verify_cleanup"
    assert calls[-2][1]["confirm"] is True
    assert report["results"][-1]["status"] == "passed"
