from pathlib import Path

from bubble_mcp.harness.eval_runner import run_eval


def test_run_eval_reports_all_cases_passing() -> None:
    report = run_eval(Path("tests/fixtures/evals/basic-routing.json"))

    assert report["summary"]["cases"] == 2
    assert report["summary"]["passed"] == 2
    assert report["failures"] == []


def test_run_eval_can_compile_plans_and_report_token_estimates() -> None:
    report = run_eval(
        Path("tests/fixtures/evals/basic-routing.json"),
        app_id="synthetic-app",
        compile_plans=True,
    )

    assert report["summary"]["cases"] == 2
    assert report["summary"]["passed"] == 2
    assert report["summary"]["compile_ok"] == 2
    assert report["summary"]["estimated_tokens"] > 0
    assert all(result["compiled"] is True for result in report["results"])
    assert all(result["has_write_payload"] is True for result in report["results"])
