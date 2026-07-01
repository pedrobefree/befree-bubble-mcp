import json
from pathlib import Path

from bubble_mcp.cli.main import main


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


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
