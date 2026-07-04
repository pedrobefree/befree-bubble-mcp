from bubble_mcp.readiness import run_readiness_check


def test_readiness_check_runs_compact_default_sequence() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": True, "tool": tool}
        return {"ok": True, "tool": tool}

    report = run_readiness_check(fake_tool)

    assert report["ok"] is True
    assert report["summary"] == {"checks": 3, "passed": 3, "failed": 0}
    assert [tool for tool, _args in calls] == [
        "bubble_health_check",
        "bubble_runtime_smoke",
        "bubble_runtime_smoke",
    ]
    assert calls[1][1]["suite"] == "coverage"
    assert calls[2][1]["suite"] == "agent-routing"
    assert "result" not in report["checks"][0]
    assert report["checks"][0]["summary"]["ok"] is True


def test_readiness_check_can_include_profile_smokes() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_tool(tool: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool, args))
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": True, "tool": tool}
        return {"ok": True, "tool": tool}

    report = run_readiness_check(
        fake_tool,
        profile="cliente2",
        context="index",
        app_id="courselaunch",
        include_family_preview=True,
    )

    assert report["ok"] is True
    assert report["summary"] == {"checks": 6, "passed": 6, "failed": 0}
    assert calls[3] == ("bubble_profile_status", {"profile": "cliente2", "max_age_hours": 24})
    assert [args["suite"] for tool, args in calls if tool == "bubble_runtime_smoke"] == [
        "coverage",
        "agent-routing",
        "safe-read",
        "family-preview",
    ]


def test_readiness_check_fails_when_profile_is_not_ready() -> None:
    def fake_tool(tool: str, _args: dict[str, object]) -> dict[str, object]:
        if tool == "bubble_profile_status":
            return {"ok": True, "ready": False, "next_actions": [{"tool": "bubble_context_detect"}]}
        return {"ok": True, "tool": tool}

    report = run_readiness_check(fake_tool, profile="cliente2", stop_on_failure=True)

    assert report["ok"] is False
    assert report["summary"] == {"checks": 4, "passed": 3, "failed": 1}
    assert report["checks"][-1]["name"] == "profile_status"
    assert report["checks"][-1]["summary"]["ready"] is False
    assert report["checks"][-1]["summary"]["next_action_count"] == 1


def test_readiness_check_can_stop_on_failure() -> None:
    calls: list[str] = []

    def fake_tool(tool: str, _args: dict[str, object]) -> dict[str, object]:
        calls.append(tool)
        return {"ok": tool != "bubble_runtime_smoke"}

    report = run_readiness_check(fake_tool, stop_on_failure=True)

    assert report["ok"] is False
    assert report["summary"] == {"checks": 2, "passed": 1, "failed": 1}
    assert calls == ["bubble_health_check", "bubble_runtime_smoke"]


def test_readiness_check_can_include_details() -> None:
    def fake_tool(tool: str, _args: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "tool": tool}

    report = run_readiness_check(fake_tool, include_details=True)

    assert report["include_details"] is True
    assert report["checks"][0]["result"] == {"ok": True, "tool": "bubble_health_check"}
