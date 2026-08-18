from __future__ import annotations

import json
import os
import random

import pytest

from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module
from scripts.benchmark_schema_lifecycle import BenchmarkConfig, compare_reports, run_benchmarks


def test_schema_benchmark_reports_resolution_crud_and_reorder_metrics() -> None:
    report = run_benchmarks(
        BenchmarkConfig(samples=2, resolution_counts=(5,), warm_lookups=3, reorder_values=5)
    )

    assert report["samples"] == 2
    assert report["workload"] == {
        "resolution_counts": [5],
        "warm_lookups": 3,
        "reorder_values": 5,
    }
    assert set(report["benchmarks"]) == {
        "data_type_resolution_5_cold",
        "data_type_resolution_5_warm",
        "schema_crud",
        "option_reorder_5",
    }
    assert all(row["elapsed_seconds"] > 0 for row in report["benchmarks"].values())
    assert all(row["external_writes"] == 0 for row in report["benchmarks"].values())
    assert report["benchmarks"]["schema_crud"]["dispatch_attempts"] == 7
    assert report["benchmarks"]["option_reorder_5"]["dispatch_attempts"] == 1
    assert report["benchmarks"]["schema_crud"]["payload_builds"] == 7
    assert report["benchmarks"]["schema_crud"]["cli_cache_saves"] == 7
    assert report["benchmarks"]["schema_crud"]["discovery_cache_saves"] == 14
    assert report["benchmarks"]["schema_crud"]["cache_saves"] == 21
    assert report["benchmarks"]["schema_crud"]["payload_bytes"] > 0
    assert report["benchmarks"]["option_reorder_5"]["payload_builds"] == 1
    assert report["benchmarks"]["option_reorder_5"]["cli_cache_saves"] == 1
    assert report["benchmarks"]["option_reorder_5"]["discovery_cache_saves"] == 2
    assert report["benchmarks"]["option_reorder_5"]["cache_saves"] == 3
    assert report["benchmarks"]["option_reorder_5"]["payload_bytes"] > 0
    assert json.loads(json.dumps(report)) == report


def test_schema_benchmark_comparison_records_absolute_percent_and_payload_deltas() -> None:
    before = {
        "schema_version": 2,
        "python": "3.13.7",
        "samples": 7,
        "workload": {"resolution_counts": [5], "warm_lookups": 3, "reorder_values": 5},
        "benchmarks": {
            "schema_crud": {
                "elapsed_seconds": 2.0,
                "payload_bytes": 100,
                "payload_builds": 7,
                "cli_cache_saves": 7,
                "discovery_cache_saves": 7,
                "cache_saves": 14,
                "external_writes": 0,
                "dispatch_attempts": 7,
            }
        },
    }
    after = {
        "schema_version": 2,
        "python": "3.13.7",
        "samples": 7,
        "workload": {"resolution_counts": [5], "warm_lookups": 3, "reorder_values": 5},
        "benchmarks": {
            "schema_crud": {
                "elapsed_seconds": 1.5,
                "payload_bytes": 96,
                "payload_builds": 7,
                "cli_cache_saves": 7,
                "discovery_cache_saves": 8,
                "cache_saves": 15,
                "external_writes": 0,
                "dispatch_attempts": 7,
            }
        },
    }

    comparison = compare_reports(before, after)

    assert comparison["benchmarks"]["schema_crud"] == {
        "before_seconds": 2.0,
        "after_seconds": 1.5,
        "absolute_delta_seconds": -0.5,
        "percentage_delta": -25.0,
        "before_payload_bytes": 100,
        "after_payload_bytes": 96,
        "payload_bytes_delta": -4,
        "before_payload_builds": 7,
        "after_payload_builds": 7,
        "payload_builds_delta": 0,
        "before_cache_saves": 14,
        "after_cache_saves": 15,
        "cache_saves_delta": 1,
        "before_cli_cache_saves": 7,
        "after_cli_cache_saves": 7,
        "cli_cache_saves_delta": 0,
        "before_discovery_cache_saves": 7,
        "after_discovery_cache_saves": 8,
        "discovery_cache_saves_delta": 1,
        "before_external_writes": 0,
        "after_external_writes": 0,
        "before_dispatch_attempts": 7,
        "after_dispatch_attempts": 7,
        "dispatch_attempts_delta": 0,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("python", "different-python"),
        ("samples", 8),
        ("schema_version", 1),
        ("workload", {"resolution_counts": [6], "warm_lookups": 3, "reorder_values": 5}),
    ],
)
def test_schema_benchmark_comparison_rejects_non_equivalent_runs(
    field: str, value: object
) -> None:
    report = {
        "schema_version": 2,
        "python": "same-python",
        "samples": 7,
        "workload": {"resolution_counts": [5], "warm_lookups": 3, "reorder_values": 5},
        "benchmarks": {},
    }
    changed = json.loads(json.dumps(report))
    changed[field] = value

    with pytest.raises(ValueError, match="same schema version, Python, samples and workload"):
        compare_reports(report, changed)


def test_schema_benchmark_restores_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    logger_before = dict(bubble_cli_module.logger.__dict__)
    send_before = bubble_cli_module.PayloadBuilder.send_to_webhook
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", "literal-existing-schema-benchmark-cache")
    random.seed(8675309)
    random_before = random.getstate()

    run_benchmarks(
        BenchmarkConfig(samples=1, resolution_counts=(2,), warm_lookups=1, reorder_values=2)
    )

    assert bubble_cli_module.logger.__dict__ == logger_before
    assert bubble_cli_module.PayloadBuilder.send_to_webhook is send_before
    assert os.environ["BUBBLE_CLI_CACHE_PATH"] == "literal-existing-schema-benchmark-cache"
    assert random.getstate() == random_before
