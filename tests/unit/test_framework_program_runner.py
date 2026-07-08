from bubble_mcp.frameworks.program_runner import execute_framework_program


def test_execute_framework_program_preview_mode_does_not_execute_mutations(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    synced = []
    monkeypatch.setattr(
        "bubble_mcp.frameworks.program_runner.sync_framework_evidence",
        lambda **kwargs: synced.append(kwargs) or {"ok": True, "artifact_dir": str(tmp_path)},
    )

    result = execute_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Preview CTA",
            "execution": {"mode": "preview", "approval": "required"},
            "steps": [
                {
                    "intent": "create_button",
                    "context": "index",
                    "parent": "root",
                    "text": "Start",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    assert result["executed"] is False
    assert result["compiled"]["compiled_calls"][0]["arguments"]["execute"] is False
    assert synced


def test_execute_framework_program_execute_requires_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = execute_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Execute CTA",
            "execution": {"mode": "execute", "approval": "required"},
            "steps": [
                {
                    "intent": "create_button",
                    "context": "index",
                    "parent": "root",
                    "text": "Start",
                }
            ],
        },
        approved=False,
    )

    assert result["ok"] is False
    assert result["error"] == "framework_program_execution_requires_approval"


def test_execute_framework_program_runs_after_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    calls = []

    def fake_call_tool(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "tool": name}

    monkeypatch.setattr("bubble_mcp.frameworks.program_runner.call_tool", fake_call_tool)
    monkeypatch.setattr(
        "bubble_mcp.frameworks.program_runner.sync_framework_evidence",
        lambda **kwargs: {"ok": True, "artifact_dir": str(tmp_path)},
    )

    result = execute_framework_program(
        framework="bmad",
        profile="cliente2",
        program={
            "objective": "Execute CTA",
            "execution": {"mode": "execute", "approval": "required"},
            "steps": [
                {
                    "intent": "create_button",
                    "context": "index",
                    "parent": "root",
                    "text": "Start",
                }
            ],
        },
        approved=True,
    )

    assert result["ok"] is True
    assert result["mode"] == "execute"
    assert result["executed"] is True
    assert calls[0][0] == "create_button"
    assert calls[0][1]["execute"] is True
    assert calls[-1][0] == "bubble_profile_cache_refresh"
