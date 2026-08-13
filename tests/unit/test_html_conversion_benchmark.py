from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.benchmark_html_conversion import benchmark_fixture, convert_html, main


FIXTURE = Path("tests/fixtures/html/import-pipeline-contracts.html")


def test_benchmark_fixture_returns_json_compatible_positive_metrics() -> None:
    report = benchmark_fixture(FIXTURE, warmups=1, iterations=2, samples=2)

    assert report["fixture"] == FIXTURE.name
    assert report["warmups"] == 1
    assert report["iterations_per_sample"] == 2
    assert report["samples"] == 2
    assert report["median_seconds"] > 0
    assert report["best_seconds"] > 0
    assert report["seconds_per_conversion"] > 0
    assert report["conversions_per_second"] > 0
    json.dumps(report)


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("warmups", {"warmups": 0}),
        ("iterations", {"iterations": 0}),
        ("samples", {"samples": -1}),
    ],
)
def test_benchmark_fixture_rejects_non_positive_work(field: str, kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError, match=rf"{field} must be greater than zero"):
        benchmark_fixture(FIXTURE, **kwargs)


def test_convert_html_rejects_empty_fixture() -> None:
    with pytest.raises(ValueError, match="did not produce a Bubble mapping"):
        convert_html("")


def test_benchmark_cli_prints_json_report(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(FIXTURE), "--warmups", "1", "--iterations", "1", "--samples", "1"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["fixture"] == FIXTURE.name


def test_benchmark_cli_reports_invalid_fixture(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    exit_code = main([str(tmp_path / "missing.html")])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "missing.html" in payload["error"]
