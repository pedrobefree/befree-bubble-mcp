import json
from pathlib import Path

from bubble_mcp.cli.main import main


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


def first_change(payload: dict, intent_name: str) -> dict:  # type: ignore[type-arg]
    return next(change for change in payload["changes"] if change.get("intent", {}).get("name") == intent_name)


def test_cli_context_summary(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["context", "summary", "--file", str(FIXTURE)]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["summary"]["app_id"] == "synthetic-app"


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
