from pathlib import Path

from bubble_mcp.harness.eval_runner import run_eval


def test_run_eval_reports_all_cases_passing() -> None:
    report = run_eval(Path("tests/fixtures/evals/basic-routing.json"))

    assert report["summary"]["cases"] == 2
    assert report["summary"]["passed"] == 2
    assert report["failures"] == []
