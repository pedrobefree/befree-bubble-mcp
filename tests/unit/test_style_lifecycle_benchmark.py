from __future__ import annotations

import json
import os
import random

from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module
from scripts.benchmark_style_lifecycle import (
    BenchmarkConfig,
    _assignment_sample,
    compare_reports,
    run_benchmarks,
)


def test_benchmark_suite_reports_repeatable_style_lifecycle_metrics() -> None:
    report = run_benchmarks(
        BenchmarkConfig(
            samples=2,
            style_counts=(5,),
            warm_lookups=3,
            assignment_operations=2,
            import_fonts=1,
            import_colors=2,
            import_styles=1,
        )
    )

    assert report["samples"] == 2
    assert report["workload"] == {
        "style_counts": [5],
        "warm_lookups": 3,
        "assignment_operations": 2,
        "import_fonts": 1,
        "import_colors": 2,
        "import_styles": 1,
    }
    assert set(report["benchmarks"]) == {
        "style_resolution_5_cold",
        "style_resolution_5_warm",
        "assignment_payload_construction",
        "color_font_crud",
        "token_import_1_2_1",
        "definition_operations",
    }
    assert all(row["elapsed_seconds"] > 0 for row in report["benchmarks"].values())
    assert all("cache_save_count" in row for row in report["benchmarks"].values())
    assert report["benchmarks"]["assignment_payload_construction"]["build_count"] == 1
    assert report["benchmarks"]["assignment_payload_construction"]["write_count"] == 0
    assert report["benchmarks"]["assignment_payload_construction"]["cache_save_count"] == 0
    assert report["benchmarks"]["color_font_crud"]["write_count"] == 6
    assert report["benchmarks"]["color_font_crud"]["cache_save_count"] == 6
    assert report["benchmarks"]["token_import_1_2_1"]["write_count"] > 0
    assert report["benchmarks"]["token_import_1_2_1"]["cache_save_count"] == 4
    assert report["benchmarks"]["definition_operations"]["cache_save_count"] == 4
    assert json.loads(json.dumps(report)) == report


def test_benchmark_comparison_reports_absolute_and_percentage_deltas() -> None:
    before = {
        "benchmarks": {
            "style_resolution_500_warm": {
                "elapsed_seconds": 2.0,
                "json_bytes": 10,
                "build_count": 1,
                "write_count": 0,
                "cache_save_count": 0,
            }
        }
    }
    after = {
        "benchmarks": {
            "style_resolution_500_warm": {
                "elapsed_seconds": 1.5,
                "json_bytes": 12,
                "build_count": 1,
                "write_count": 0,
                "cache_save_count": 0,
            }
        }
    }

    comparison = compare_reports(before, after)

    assert comparison["benchmarks"]["style_resolution_500_warm"] == {
        "before_seconds": 2.0,
        "after_seconds": 1.5,
        "absolute_delta_seconds": -0.5,
        "percentage_delta": -25.0,
        "before_json_bytes": 10,
        "after_json_bytes": 12,
        "before_build_count": 1,
        "after_build_count": 1,
        "before_write_count": 0,
        "after_write_count": 0,
        "before_cache_save_count": 0,
        "after_cache_save_count": 0,
    }


def test_assignment_benchmark_payload_metrics_are_repeatable() -> None:
    random.seed(1)

    byte_counts = [_assignment_sample(200).json_bytes for _ in range(5)]

    assert len(set(byte_counts)) == 1


def test_benchmark_suite_restores_runtime_state(monkeypatch) -> None:
    before = dict(bubble_cli_module.logger.__dict__)
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", "literal-existing-cache-path")
    random.seed(8675309)
    random_state = random.getstate()

    run_benchmarks(
        BenchmarkConfig(
            samples=1,
            style_counts=(2,),
            warm_lookups=1,
            assignment_operations=1,
            import_fonts=1,
            import_colors=1,
            import_styles=1,
        )
    )

    assert bubble_cli_module.logger.__dict__ == before
    assert os.environ["BUBBLE_CLI_CACHE_PATH"] == "literal-existing-cache-path"
    assert random.getstate() == random_state
