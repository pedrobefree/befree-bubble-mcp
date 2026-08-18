#!/usr/bin/env python3
"""Network-free Stage 4.6 schema lifecycle before/after benchmarks."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from functools import partial
from io import StringIO
import json
import os
from pathlib import Path
import platform
import random
from statistics import median
import sys
import tempfile
from time import perf_counter
from typing import Any, Callable, Iterator, cast

from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module


BubbleCLI = bubble_cli_module.BubbleCLI
PayloadBuilder = bubble_cli_module.PayloadBuilder


@dataclass(frozen=True)
class BenchmarkConfig:
    """Workload sizes shared by the Stage 4.6 baseline and extracted implementation."""

    samples: int = 7
    resolution_counts: tuple[int, ...] = (500, 5_000)
    warm_lookups: int = 200
    reorder_values: int = 500

    def __post_init__(self) -> None:
        values = (self.samples, *self.resolution_counts, self.warm_lookups, self.reorder_values)
        if not self.resolution_counts or any(value <= 0 for value in values):
            raise ValueError("benchmark workloads must be positive")


@dataclass(frozen=True)
class Sample:
    elapsed_seconds: float
    payload_bytes: int = 0
    payload_builds: int = 0
    cache_saves: int = 0
    external_writes: int = 0
    dispatch_attempts: int = 0


@dataclass
class Metrics:
    payload_bytes: int = 0
    payload_builds: int = 0
    cache_saves: int = 0
    external_writes: int = 0
    dispatch_attempts: int = 0

    def capture_payload(self, payload: Any) -> None:
        built = payload.build()
        rendered = json.dumps(built, sort_keys=True, separators=(",", ":")).encode()
        self.payload_bytes += len(rendered)
        self.payload_builds += 1


@contextmanager
def _isolated_runtime() -> Iterator[None]:
    logger_state = dict(bubble_cli_module.logger.__dict__)
    cache_path = os.environ.get("BUBBLE_CLI_CACHE_PATH")
    random_state = random.getstate()
    original_send = PayloadBuilder.send_to_webhook

    def quiet(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    try:
        for method in ("debug", "error", "info", "log", "success", "warning"):
            setattr(bubble_cli_module.logger, method, quiet)
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            yield
    finally:
        PayloadBuilder.send_to_webhook = original_send
        bubble_cli_module.logger.__dict__.clear()
        bubble_cli_module.logger.__dict__.update(logger_state)
        if cache_path is None:
            os.environ.pop("BUBBLE_CLI_CACHE_PATH", None)
        else:
            os.environ["BUBBLE_CLI_CACHE_PATH"] = cache_path
        random.setstate(random_state)


@contextmanager
def _capture_dispatches(metrics: Metrics) -> Iterator[None]:
    original_send = PayloadBuilder.send_to_webhook

    def capture(payload: Any, _url: str = "local://bubble-mcp", **_kwargs: Any) -> None:
        metrics.dispatch_attempts += 1
        metrics.capture_payload(payload)

    PayloadBuilder.send_to_webhook = capture
    try:
        yield
    finally:
        PayloadBuilder.send_to_webhook = original_send


def _new_cli(root: Path, snapshot: dict[str, Any]) -> Any:
    snapshot_path = root / "app.json"
    snapshot_path.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    os.environ["BUBBLE_CLI_CACHE_PATH"] = str(root / "cli-cache.json")
    return BubbleCLI(app_json_path=str(snapshot_path), appname="schema-lifecycle-benchmark")


def _capture_cache_saves(cli: Any, metrics: Metrics) -> None:
    original_save = cli._save_cli_cache

    def counted_save() -> None:
        metrics.cache_saves += 1
        original_save()

    cli._save_cli_cache = counted_save


def _resolution_snapshot(count: int) -> dict[str, Any]:
    return {
        "user_types": {
            f"benchmark_type_{index}": {
                "%d": f"Benchmark Type {index}",
                "%f3": {"title_text": {"%d": "Title", "%v": "text"}},
            }
            for index in range(count)
        }
    }


def _schema_snapshot(*, reorder_values: int = 3) -> dict[str, Any]:
    values = {
        f"value_{index:04d}": {
            "%d": f"Value {index}",
            "db_value": f"value_{index}",
            "sort_factor": index + 1,
        }
        for index in range(reorder_values)
    }
    return {
        "user_types": {
            "account": {
                "%d": "Account",
                "%f3": {"title_text": {"%d": "Title", "%v": "text"}},
                "privacy_role": {},
            }
        },
        "option_sets": {
            "os_status": {
                "%d": "OS:status",
                "attributes": {},
                "values": values,
            }
        },
    }


def _time_samples(samples: int, sample_fn: Callable[[], Sample]) -> dict[str, Any]:
    rows = [sample_fn() for _ in range(samples)]
    elapsed_samples = [row.elapsed_seconds for row in rows]
    return {
        "elapsed_seconds": median(elapsed_samples),
        "elapsed_samples": elapsed_samples,
        "payload_bytes": int(median(row.payload_bytes for row in rows)),
        "payload_builds": int(median(row.payload_builds for row in rows)),
        "cache_saves": int(median(row.cache_saves for row in rows)),
        "external_writes": int(median(row.external_writes for row in rows)),
        "dispatch_attempts": int(median(row.dispatch_attempts for row in rows)),
    }


def _resolution_sample(count: int, *, warm_lookups: int | None) -> Sample:
    with tempfile.TemporaryDirectory(prefix="schema-resolution-") as temp_name:
        cli = _new_cli(Path(temp_name), _resolution_snapshot(count))
        expected = f"benchmark_type_{count - 1}"
        label = f"Benchmark Type {count - 1}"
        if warm_lookups is not None and cli._resolve_data_type_key(label, "label", False) != expected:
            raise RuntimeError("schema resolution warm-up did not resolve the expected type")
        iterations = warm_lookups or 1
        started = perf_counter()
        for _ in range(iterations):
            if cli._resolve_data_type_key(label, "label", False) != expected:
                raise RuntimeError("schema benchmark did not resolve the expected type")
        elapsed = perf_counter() - started
    return Sample(elapsed_seconds=elapsed)


def _crud_sample() -> Sample:
    with tempfile.TemporaryDirectory(prefix="schema-crud-") as temp_name:
        cli = _new_cli(Path(temp_name), _schema_snapshot())
        metrics = Metrics()
        _capture_cache_saves(cli, metrics)
        random.seed(46)
        with _capture_dispatches(metrics):
            started = perf_counter()
            results = (
                cli.create_data_type("Benchmark New", key="benchmark_new"),
                cli.rename_data_type("account", "Account Renamed"),
                cli.create_data_field(
                    "account", "Benchmark Field", "text", field_key="benchmark_text"
                ),
                cli.rename_data_field("account", "benchmark_text", "Benchmark Renamed"),
                cli.delete_data_field("account", "benchmark_text"),
                cli.set_data_type_api_exposure("account", True),
                cli.delete_data_type("benchmark_new"),
            )
            elapsed = perf_counter() - started
        if not all(results):
            raise RuntimeError(f"schema CRUD benchmark failed: {results}")
    return Sample(
        elapsed_seconds=elapsed,
        payload_bytes=metrics.payload_bytes,
        payload_builds=metrics.payload_builds,
        cache_saves=metrics.cache_saves,
        external_writes=metrics.external_writes,
        dispatch_attempts=metrics.dispatch_attempts,
    )


def _reorder_sample(count: int) -> Sample:
    with tempfile.TemporaryDirectory(prefix="schema-reorder-") as temp_name:
        cli = _new_cli(Path(temp_name), _schema_snapshot(reorder_values=count))
        metrics = Metrics()
        _capture_cache_saves(cli, metrics)
        assignments = [f"value_{index:04d}:{count - index}" for index in range(count)]
        random.seed(46)
        with _capture_dispatches(metrics):
            started = perf_counter()
            result = cli.reorder_option_values("os_status", assignments)
            elapsed = perf_counter() - started
        if not result:
            raise RuntimeError("option reorder benchmark failed")
    return Sample(
        elapsed_seconds=elapsed,
        payload_bytes=metrics.payload_bytes,
        payload_builds=metrics.payload_builds,
        cache_saves=metrics.cache_saves,
        external_writes=metrics.external_writes,
        dispatch_attempts=metrics.dispatch_attempts,
    )


def _run_benchmarks(config: BenchmarkConfig) -> dict[str, Any]:
    benchmarks: dict[str, Any] = {}
    for count in config.resolution_counts:
        benchmarks[f"data_type_resolution_{count}_cold"] = _time_samples(
            config.samples,
            partial(_resolution_sample, count, warm_lookups=None),
        )
        benchmarks[f"data_type_resolution_{count}_warm"] = _time_samples(
            config.samples,
            partial(_resolution_sample, count, warm_lookups=config.warm_lookups),
        )
    benchmarks["schema_crud"] = _time_samples(config.samples, _crud_sample)
    benchmarks[f"option_reorder_{config.reorder_values}"] = _time_samples(
        config.samples, partial(_reorder_sample, config.reorder_values)
    )
    return {
        "schema_version": 1,
        "python": (
            f"{platform.python_implementation()} {platform.python_version()} ({sys.executable})"
        ),
        "samples": config.samples,
        "workload": {
            "resolution_counts": list(config.resolution_counts),
            "warm_lookups": config.warm_lookups,
            "reorder_values": config.reorder_values,
        },
        "benchmarks": benchmarks,
    }


def run_benchmarks(config: BenchmarkConfig = BenchmarkConfig()) -> dict[str, Any]:
    """Run deterministic fixtures without performing a remote Bubble write."""
    with _isolated_runtime():
        return _run_benchmarks(config)


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare reports only when schema, Python, sample count, workload and cases match."""
    if any(
        before.get(field) != after.get(field)
        for field in ("schema_version", "python", "samples", "workload")
    ):
        raise ValueError(
            "benchmark reports must use the same schema version, Python, samples and workload"
        )
    before_rows = before.get("benchmarks", {})
    after_rows = after.get("benchmarks", {})
    if set(before_rows) != set(after_rows):
        raise ValueError("benchmark reports contain different case sets")
    comparison: dict[str, Any] = {}
    for name in before_rows:
        before_row = before_rows[name]
        after_row = after_rows[name]
        before_seconds = float(before_row["elapsed_seconds"])
        after_seconds = float(after_row["elapsed_seconds"])
        delta = after_seconds - before_seconds
        percentage = None if before_seconds == 0 else (delta / before_seconds) * 100
        comparison[name] = {
            "before_seconds": before_seconds,
            "after_seconds": after_seconds,
            "absolute_delta_seconds": round(delta, 12),
            "percentage_delta": None if percentage is None else round(percentage, 3),
            "before_payload_bytes": int(before_row["payload_bytes"]),
            "after_payload_bytes": int(after_row["payload_bytes"]),
            "payload_bytes_delta": int(after_row["payload_bytes"])
            - int(before_row["payload_bytes"]),
            "before_payload_builds": int(before_row["payload_builds"]),
            "after_payload_builds": int(after_row["payload_builds"]),
            "payload_builds_delta": int(after_row["payload_builds"])
            - int(before_row["payload_builds"]),
            "before_cache_saves": int(before_row["cache_saves"]),
            "after_cache_saves": int(after_row["cache_saves"]),
            "cache_saves_delta": int(after_row["cache_saves"])
            - int(before_row["cache_saves"]),
            "before_external_writes": int(before_row["external_writes"]),
            "after_external_writes": int(after_row["external_writes"]),
            "before_dispatch_attempts": int(before_row.get("dispatch_attempts", 0)),
            "after_dispatch_attempts": int(after_row.get("dispatch_attempts", 0)),
            "dispatch_attempts_delta": int(after_row.get("dispatch_attempts", 0))
            - int(before_row.get("dispatch_attempts", 0)),
        }
    return {
        "schema_version": 1,
        "python": before.get("python"),
        "samples": before.get("samples"),
        "workload": before.get("workload"),
        "benchmarks": comparison,
    }


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark report must contain a JSON object")
    return cast(dict[str, Any], payload)


def _parse_counts(value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--resolution-counts", default="500,5000")
    parser.add_argument("--warm-lookups", type=int, default=200)
    parser.add_argument("--reorder-values", type=int, default=500)
    parser.add_argument("--output")
    parser.add_argument("--compare-before")
    parser.add_argument("--compare-after")
    args = parser.parse_args(argv)
    if bool(args.compare_before) != bool(args.compare_after):
        parser.error("--compare-before and --compare-after must be provided together")
    if args.compare_before:
        report = compare_reports(_load_json(args.compare_before), _load_json(args.compare_after))
    else:
        report = run_benchmarks(
            BenchmarkConfig(
                samples=args.samples,
                resolution_counts=_parse_counts(args.resolution_counts),
                warm_lookups=args.warm_lookups,
                reorder_values=args.reorder_values,
            )
        )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
