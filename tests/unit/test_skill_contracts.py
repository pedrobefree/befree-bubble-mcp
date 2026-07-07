import json
from pathlib import Path

import pytest

from bubble_mcp.cli.main import main
from bubble_mcp.extensions.store import enable_extension, import_extension
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.stdio import handle_request
from bubble_mcp.skills.authoring import (
    create_skill_authoring_session,
    generate_skill_from_authoring_session,
    update_skill_authoring_session,
)
from bubble_mcp.skills.runner import run_skill
from bubble_mcp.skills.store import (
    disable_skill,
    enable_skill,
    export_skill,
    import_skill,
    list_skills,
)
from bubble_mcp.skills.validator import validate_skill_file


def test_validate_declarative_skill_file() -> None:
    report = validate_skill_file(Path("tests/fixtures/skills/security-review.skill.json"))

    assert report["ok"] is True
    assert report["executable"] is False
    assert report["skill"]["id"] == "security-review"
    assert "bubble_context_detect" in report["skill"]["allowedTools"]


def test_validate_executable_skill_file() -> None:
    report = validate_skill_file(Path("tests/fixtures/skills/executable-security-review.skill.json"))

    assert report["ok"] is True
    assert report["executable"] is True
    assert report["skill"]["id"] == "security-review-executable"
    assert report["skill"]["risk"] == "mutating"
    assert report["skill"]["steps"][0]["tool"] == "bubble_context_detect"


def test_executable_mutating_skill_requires_approval(tmp_path) -> None:
    skill_path = tmp_path / "missing-approval.skill.json"
    payload = _valid_executable_skill_payload()
    payload.pop("approval")
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert "mutating and destructive skills require approval object" in report["errors"]


def test_executable_skill_step_must_be_allowed(tmp_path) -> None:
    skill_path = tmp_path / "step-not-allowed.skill.json"
    payload = _valid_executable_skill_payload()
    payload["steps"] = [
        {
            "id": "bad_step",
            "type": "tool",
            "tool": "bubble_context_find",
            "args": {"profile": "{{inputs.profile}}", "query": "privacy"},
            "mode": "read",
        }
    ]
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert "steps[0].tool is not listed in allowedTools: bubble_context_find" in report["errors"]


def test_unknown_allowed_tool_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "unknown-tool.skill.json"
    payload = _valid_skill_payload()
    payload["allowedTools"] = ["bubble_context_detect", "missing_tool"]
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert "allowedTools references unknown tool: missing_tool" in report["errors"]


def test_forbidden_step_type_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "forbidden-step.skill.json"
    payload = _valid_skill_payload()
    payload["steps"] = [{"type": "shell"}]
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert "steps[0].type is not allowed in skill contract v1: shell" in report["errors"]


@pytest.mark.parametrize(
    "step_type",
    [
        "run_shell",
        "python",
        "bash",
        "sh",
        "eval",
        "python_script",
        "node_script",
        "os.system",
        "pythonScript",
        "nodeScript",
        "runShell",
        "shellCommand",
        "osSystem",
        "subprocessRun",
        "jsEval",
        "nodejs",
        "custom_future_step",
    ],
)
def test_non_allowlisted_step_types_are_rejected_in_v1(tmp_path, step_type: str) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / f"forbidden-{step_type}.skill.json"
    payload = _valid_skill_payload()
    payload["steps"] = [{"type": step_type}]
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert f"steps[0].type is not allowed in skill contract v1: {step_type}" in report["errors"]


def test_missing_outputs_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "missing-outputs.skill.json"
    payload = _valid_skill_payload()
    payload.pop("outputs")
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert "outputs must be a non-empty list of strings" in report["errors"]


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("outputs", [123], "outputs[0] must be a non-empty string"),
        ("inputs", [123], "inputs[0] must be a non-empty string"),
        ("allowedTools", "bubble_context_detect", "allowedTools must be a list of strings"),
        ("allowedTools", ["bubble_context_detect", 123], "allowedTools[1] must be a non-empty string"),
    ],
)
def test_string_list_contract_fields_reject_malformed_items(
    tmp_path,
    field: str,
    value: object,
    expected_error: str,
) -> None:
    skill_path = tmp_path / f"malformed-{field}.skill.json"
    payload = _valid_skill_payload()
    payload[field] = value
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert expected_error in report["errors"]


@pytest.mark.parametrize(
    ("steps", "expected_error"),
    [
        ("refresh_context", "steps must be a non-empty list"),
        (["bad"], "steps[0] must be an object"),
    ],
)
def test_steps_reject_malformed_shape(tmp_path, steps: object, expected_error: str) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "malformed-steps.skill.json"
    payload = _valid_skill_payload()
    payload["steps"] = steps
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert expected_error in report["errors"]


@pytest.mark.parametrize(
    ("gates", "expected_error"),
    [
        (["bad"], "gates[0] must be an object"),
        ([{}], "gates[0].type is required"),
    ],
)
def test_gates_reject_malformed_shape(tmp_path, gates: object, expected_error: str) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "malformed-gates.skill.json"
    payload = _valid_skill_payload()
    payload["gates"] = gates
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert expected_error in report["errors"]


@pytest.mark.parametrize(
    ("gate", "expected_error"),
    [
        ({"type": "evidence_required", "outputs": [123]}, "gates[0].outputs[0] must be a non-empty string"),
        ({"type": "evidence_required", "outputs": []}, "gates[0].outputs must be a non-empty list of strings"),
    ],
)
def test_evidence_required_gate_outputs_are_validated(
    tmp_path,
    gate: dict[str, object],
    expected_error: str,
) -> None:
    skill_path = tmp_path / "malformed-evidence-gate.skill.json"
    payload = _valid_skill_payload()
    payload["gates"] = [gate]
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert expected_error in report["errors"]


def test_read_only_gate_extra_fields_and_unknown_gate_types_are_allowed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "future-gates.skill.json"
    payload = _valid_skill_payload()
    payload["gates"] = [
        {"type": "read_only_only", "note": "extra fields are advisory"},
        {"type": "future_gate", "payload": {"mode": "advisory"}},
    ]
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is True


def test_numeric_name_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "numeric-name.skill.json"
    payload = _valid_skill_payload()
    payload["name"] = 123
    skill_path.write_text(json.dumps(payload), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert "name must be a string" in report["errors"]


def test_root_json_array_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "array-root.skill.json"
    skill_path.write_text(json.dumps([_valid_skill_payload()]), encoding="utf-8")

    report = validate_skill_file(skill_path)

    assert report["ok"] is False
    assert report["skill"] is None
    assert report["errors"] == ["skill file must contain a JSON object"]


def test_skill_import_enable_disable_export_and_list(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    source = Path("tests/fixtures/skills/executable-security-review.skill.json")

    imported = import_skill(source)
    assert imported["ok"] is True
    assert imported["skill_id"] == "security-review-executable"
    assert imported["state"] == "pending"

    enabled = enable_skill("security-review-executable")
    assert enabled["ok"] is True
    assert enabled["state"] == "enabled"
    assert [skill.skill_id for skill in list_skills()] == ["security-review-executable"]
    assert list_skills()[0].state == "enabled"

    exported = export_skill("security-review-executable", tmp_path / "exported")
    assert exported["ok"] is True
    assert Path(str(exported["path"])).exists()

    disabled = disable_skill("security-review-executable")
    assert disabled["ok"] is True
    assert disabled["state"] == "disabled"


def test_enabled_extension_pack_skills_are_listed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    import_extension(Path("tests/fixtures/extensions/simple-pack"))
    enable_extension("local.simple-pack")

    skills = {skill.skill_id: skill for skill in list_skills()}

    assert "simple-pack-security-review" in skills
    assert skills["simple-pack-security-review"].source == "extension"
    assert skills["simple-pack-security-review"].extension_id == "local.simple-pack"


def test_skill_authoring_session_generates_valid_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    started = create_skill_authoring_session(
        objective="Review API Connector security",
        risk="mutating",
        profile="client",
    )
    session_id = str(started["session"]["id"])
    updated = update_skill_authoring_session(
        session_id,
        answer="Return a plan, risk summary, and inspect API Connector calls before any changes.",
        field="outputs",
    )
    generated = generate_skill_from_authoring_session(
        session_id,
        skill_id="api-connector-security-review",
        output_dir=tmp_path / "generated",
    )

    assert updated["ready_to_generate"] is True
    assert generated["ok"] is True
    assert generated["skill_id"] == "api-connector-security-review"
    assert Path(str(generated["path"])).exists()
    assert generated["validation"]["executable"] is True
    assert generated["validation"]["skill"]["approval"]["mode"] == "plan_then_approve"
    assert generated["next_mcp_calls"][1]["tool"] == "bubble_skill_import"


def test_skill_run_preview_returns_friendly_steps_without_raw_payloads(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    import_skill(Path("tests/fixtures/skills/executable-security-review.skill.json"))
    enable_skill("security-review-executable")

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call(tool_name: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool_name, args))
        return {"ok": True, "compiled_payload": {"secret": "not-for-user"}}

    monkeypatch.setattr("bubble_mcp.skills.runner._call_mcp_tool", fake_call)
    result = run_skill(
        "security-review-executable",
        inputs={"profile": "client", "scope": "privacy"},
        execute=False,
    )

    assert result["ok"] is True
    assert result["mode"] == "preview"
    assert str(result["run_id"]).startswith("skillrun_")
    assert result["steps"][0]["tool"] == "bubble_context_detect"
    assert "compiled_payload" not in json.dumps(result)
    assert calls[0][1]["profile"] == "client"


def test_skill_run_execute_requires_approval_and_preview_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    import_skill(Path("tests/fixtures/skills/executable-security-review.skill.json"))
    enable_skill("security-review-executable")

    no_approval = run_skill("security-review-executable", execute=True)
    no_run = run_skill("security-review-executable", execute=True, approve_execution=True)

    assert no_approval["error"] == "skill_execution_requires_approval"
    assert no_run["error"] == "skill_execution_requires_preview_run"


def test_skill_run_executes_approved_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    skill_path = tmp_path / "write.skill.json"
    skill_path.write_text(json.dumps(_valid_write_skill_payload()), encoding="utf-8")
    import_skill(skill_path)
    enable_skill("write-skill")

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call(tool_name: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool_name, args))
        return {"ok": True}

    monkeypatch.setattr("bubble_mcp.skills.runner._call_mcp_tool", fake_call)
    preview = run_skill("write-skill", inputs={"profile": "client"}, execute=False)
    executed = run_skill(
        "write-skill",
        execute=True,
        approve_execution=True,
        run_id=str(preview["run_id"]),
    )

    assert preview["ok"] is True
    assert preview["approval_required"] is True
    assert executed["ok"] is True
    assert executed["mode"] == "executed"
    assert calls[0][1]["arguments"]["execute"] is False
    assert calls[1][1]["arguments"]["execute"] is True


def test_skill_mcp_tools_are_listed_and_dispatch_validate() -> None:
    tools = {tool["name"]: tool for tool in list_tool_schemas()}

    assert tools["bubble_skill_validate"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_skill_validate"]["annotations"]["idempotentHint"] is True
    assert tools["bubble_skill_validate"]["inputSchema"]["required"] == ["path"]
    assert tools["bubble_skill_describe"]["annotations"]["readOnlyHint"] is True
    assert tools["bubble_skill_import"]["inputSchema"]["required"] == ["path"]
    assert tools["bubble_skill_run"]["inputSchema"]["required"] == ["skill_id"]
    assert tools["bubble_skill_author_start"]["inputSchema"]["required"] == ["objective"]

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "bubble_skill_validate",
                "arguments": {"path": "tests/fixtures/skills/security-review.skill.json"},
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["skill"]["id"] == "security-review"


def test_skill_mcp_import_enable_list_and_run_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    def fake_call(tool_name: str, args: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "tool": tool_name, "profile": args.get("profile")}

    monkeypatch.setattr("bubble_mcp.skills.runner._call_mcp_tool", fake_call)

    for request_id, name, arguments in (
        (
            10,
            "bubble_skill_import",
            {"path": "tests/fixtures/skills/executable-security-review.skill.json"},
        ),
        (11, "bubble_skill_enable", {"skill_id": "security-review-executable"}),
        (12, "bubble_skill_list", {}),
        (
            13,
            "bubble_skill_run",
            {
                "skill_id": "security-review-executable",
                "inputs": {"profile": "client"},
                "execute": False,
            },
        ),
    ):
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert response is not None
        payload = json.loads(response["result"]["content"][0]["text"])
        assert payload["ok"] is True


def test_skill_cli_import_enable_list_and_run(tmp_path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))

    def fake_call(tool_name: str, args: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "tool": tool_name, "profile": args.get("profile")}

    monkeypatch.setattr("bubble_mcp.skills.runner._call_mcp_tool", fake_call)

    assert main(["skill", "import", "--path", "tests/fixtures/skills/executable-security-review.skill.json"]) == 0
    assert json.loads(capsys.readouterr().out)["skill_id"] == "security-review-executable"
    assert main(["skill", "enable", "security-review-executable"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "enabled"
    assert main(["skill", "list"]) == 0
    assert json.loads(capsys.readouterr().out)["skills"][0]["skill_id"] == "security-review-executable"
    assert main(["skill", "run", "security-review-executable", "--inputs", '{"profile":"client"}']) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "preview"


def test_skill_mcp_authoring_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    start_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {
                "name": "bubble_skill_author_start",
                "arguments": {
                    "objective": "Review API Connector security",
                    "risk": "mutating",
                    "profile": "client",
                },
            },
        }
    )
    assert start_response is not None
    start_payload = json.loads(start_response["result"]["content"][0]["text"])
    session_id = start_payload["session"]["id"]

    update_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "bubble_skill_author_update",
                "arguments": {
                    "session_id": session_id,
                    "answer": "Return a plan and risk summary.",
                    "field": "outputs",
                },
            },
        }
    )
    assert update_response is not None
    assert json.loads(update_response["result"]["content"][0]["text"])["ok"] is True

    generate_response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {
                "name": "bubble_skill_author_generate",
                "arguments": {"session_id": session_id, "skill_id": "api-security-review"},
            },
        }
    )
    assert generate_response is not None
    generate_payload = json.loads(generate_response["result"]["content"][0]["text"])
    assert generate_payload["ok"] is True
    assert generate_payload["validation"]["executable"] is True


def test_malformed_skill_json_returns_useful_cli_and_mcp_errors(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    skill_path = tmp_path / "malformed.skill.json"
    skill_path.write_text("{not-json", encoding="utf-8")

    assert main(["skill", "validate", "--path", str(skill_path)]) == 1
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["ok"] is False
    assert "invalid JSON" in cli_payload["errors"][0]

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "bubble_skill_describe", "arguments": {"path": str(skill_path)}},
        }
    )

    assert response is not None
    mcp_payload = json.loads(response["result"]["content"][0]["text"])
    assert mcp_payload["ok"] is False
    assert "invalid JSON" in mcp_payload["errors"][0]
    assert mcp_payload["description"].startswith("Declarative skill contract validation only")


def _valid_skill_payload() -> dict[str, object]:
    return {
        "id": "security-review",
        "name": "Security Review",
        "inputs": ["profile", "app_id", "scope"],
        "allowedTools": ["bubble_context_detect"],
        "steps": [{"type": "refresh_context"}],
        "gates": [{"type": "read_only_only"}],
        "outputs": ["markdown_report"],
    }


def _valid_executable_skill_payload() -> dict[str, object]:
    return {
        "id": "security-review-executable",
        "name": "Security Review Executable",
        "version": "0.1.0",
        "description": "Review Bubble app security posture.",
        "risk": "mutating",
        "inputs": {
            "profile": {"type": "string", "required": True},
        },
        "allowedTools": ["bubble_context_detect"],
        "steps": [
            {
                "id": "refresh_context",
                "type": "tool",
                "tool": "bubble_context_detect",
                "args": {"profile": "{{inputs.profile}}", "force": True},
                "mode": "read",
            }
        ],
        "approval": {
            "requiredFor": ["mutating", "destructive"],
            "mode": "plan_then_approve",
        },
        "gates": [
            {"type": "approval_required", "whenRisk": ["mutating", "destructive"]},
            {"type": "evidence_required", "outputs": ["plan", "risk_summary"]},
        ],
        "outputs": ["plan", "risk_summary", "execution_log"],
    }


def _valid_write_skill_payload() -> dict[str, object]:
    return {
        "id": "write-skill",
        "name": "Write Skill",
        "version": "0.1.0",
        "risk": "mutating",
        "inputs": {"profile": {"type": "string", "required": True}},
        "allowedTools": ["bubble_extension_call"],
        "steps": [
            {
                "id": "write_preview",
                "type": "tool",
                "tool": "bubble_extension_call",
                "args": {
                    "tool": "local.example.write",
                    "arguments": {"profile": "{{inputs.profile}}", "execute": False},
                },
                "mode": "write",
            }
        ],
        "approval": {"requiredFor": ["mutating"], "mode": "plan_then_approve"},
        "gates": [{"type": "approval_required", "whenRisk": ["mutating"]}],
        "outputs": ["plan"],
    }
