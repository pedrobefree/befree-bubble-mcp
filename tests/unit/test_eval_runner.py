from pathlib import Path

from bubble_mcp.harness.eval_runner import run_eval


def test_run_eval_reports_all_cases_passing() -> None:
    report = run_eval(Path("tests/fixtures/evals/basic-routing.json"))

    assert report["summary"]["cases"] == 2
    assert report["summary"]["passed"] == 2
    assert report["failures"] == []
    assert report["summary"]["matched"] == 2
    assert report["summary"]["missing_ok"] == 2
    assert report["summary"]["warnings_ok"] == 2
    assert report["summary"]["parser_summary"] == {"deterministic": 2}
    assert report["summary"]["fallback_summary"] == {"none": 2}


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


def test_run_eval_accepts_aria_style_camelcase_expectations() -> None:
    report = run_eval(Path("tests/fixtures/evals/aria-style-routing.json"))

    assert report["summary"]["cases"] == 2
    assert report["summary"]["passed"] == 2
    assert report["failures"] == []
    assert [result["expected_tool"] for result in report["results"]] == [
        "create_text",
        "create_group",
    ]


def test_run_eval_reports_failure_reasons_for_agent_harness_debugging() -> None:
    report = run_eval(Path("tests/fixtures/evals/failure-routing.json"))

    assert report["summary"]["cases"] == 2
    assert report["summary"]["passed"] == 0
    assert report["summary"]["matched"] == 1
    assert report["summary"]["parser_summary"] == {"deterministic": 1, "none": 1}
    assert report["summary"]["fallback_summary"]["tool_mismatch"] == 1
    assert report["summary"]["fallback_summary"]["args_mismatch"] == 1
    assert report["summary"]["fallback_summary"]["no_plan_steps"] == 1

    failures = {result["id"]: result for result in report["failures"]}
    assert failures["wrong_tool"]["fallback_reason"] == "tool_mismatch"
    assert failures["wrong_tool"]["fallback_reasons"] == ["tool_mismatch", "args_mismatch"]
    assert failures["unmatched"]["parser"] == "none"
    assert failures["unmatched"]["warnings"] == ["No deterministic Bubble plan matched this request."]
