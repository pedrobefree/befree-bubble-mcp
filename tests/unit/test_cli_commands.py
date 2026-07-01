import json
from pathlib import Path

from bubble_mcp.cli.main import main


FIXTURE = Path("tests/fixtures/context/synthetic-app-context.json")


def test_cli_context_summary(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["context", "summary", "--file", str(FIXTURE)]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["summary"]["app_id"] == "synthetic-app"


def test_cli_plan_outputs_validated_dry_run(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["plan", 'Create text saying "Hello"']) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["args"]["dry_run"] is True


def test_cli_import_html_outputs_validated_plan(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["import", "html", "--file", "tests/fixtures/html/login-card.html"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["validation"]["ok"] is True
    assert payload["plan"]["steps"][0]["tool_name"] == "create_group"
