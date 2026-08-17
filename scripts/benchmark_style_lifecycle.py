#!/usr/bin/env python3
"""Repeatable, network-free Stage 4.5 style lifecycle benchmarks."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from functools import partial
from io import StringIO
import json
import os
from pathlib import Path
import random
from statistics import median
import tempfile
from time import perf_counter
from typing import Any, Callable, cast, Iterator

from bubble_mcp.aria_runtime import bubble_cli as bubble_cli_module


BubbleCLI = bubble_cli_module.BubbleCLI
PayloadBuilder = bubble_cli_module.PayloadBuilder


@dataclass(frozen=True)
class BenchmarkConfig:
    """Workload sizes shared by baseline and extracted implementations."""

    samples: int = 7
    style_counts: tuple[int, ...] = (500, 5_000)
    warm_lookups: int = 200
    assignment_operations: int = 200
    import_fonts: int = 25
    import_colors: int = 250
    import_styles: int = 100

    def __post_init__(self) -> None:
        values = (
            self.samples,
            *self.style_counts,
            self.warm_lookups,
            self.assignment_operations,
            self.import_fonts,
            self.import_colors,
            self.import_styles,
        )
        if not self.style_counts or any(value <= 0 for value in values):
            raise ValueError("benchmark workloads must be positive")


@dataclass(frozen=True)
class Sample:
    elapsed_seconds: float
    json_bytes: int = 0
    build_count: int = 0
    write_count: int = 0
    cache_save_count: int = 0


@dataclass
class PayloadMetrics:
    json_bytes: int = 0
    build_count: int = 0
    write_count: int = 0
    cache_save_count: int = 0

    def capture(self, payload: Any) -> None:
        """Capture one would-be remote write without sending it."""
        built = payload.build()
        self.json_bytes += len(json.dumps(built, sort_keys=True, separators=(",", ":")).encode())
        self.build_count += 1
        self.write_count += 1

    def capture_build(self, payload: Any) -> None:
        """Capture a local payload build that is intentionally not dispatched."""
        built = payload.build()
        self.json_bytes += len(json.dumps(built, sort_keys=True, separators=(",", ":")).encode())
        self.build_count += 1


@contextmanager
def _silence_runtime_logs() -> Iterator[None]:
    logger_state = dict(bubble_cli_module.logger.__dict__)
    cache_path = os.environ.get("BUBBLE_CLI_CACHE_PATH")
    random_state = random.getstate()

    def quiet(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    try:
        for method in ("debug", "error", "info", "log", "success", "warning"):
            setattr(bubble_cli_module.logger, method, quiet)
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            yield
    finally:
        bubble_cli_module.logger.__dict__.clear()
        bubble_cli_module.logger.__dict__.update(logger_state)
        if cache_path is None:
            os.environ.pop("BUBBLE_CLI_CACHE_PATH", None)
        else:
            os.environ["BUBBLE_CLI_CACHE_PATH"] = cache_path
        random.setstate(random_state)


def _new_cli(root: Path, snapshot: dict[str, Any]) -> Any:
    snapshot_path = root / "app.json"
    snapshot_path.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    os.environ["BUBBLE_CLI_CACHE_PATH"] = str(root / "cli-cache.json")
    return BubbleCLI(app_json_path=str(snapshot_path), appname="style-lifecycle-benchmark")


def _capture_cache_saves(cli: Any, metrics: PayloadMetrics) -> None:
    original_save = cli._save_cli_cache

    def counted_save() -> None:
        metrics.cache_save_count += 1
        original_save()

    cli._save_cli_cache = counted_save


def _style_snapshot(count: int) -> dict[str, Any]:
    return {
        "styles": {
            f"Text_benchmark_{index}_": {
                "%d": f"Benchmark {index}",
                "%x": "Text",
                "%p": {"%fs": 12 + (index % 8)},
            }
            for index in range(count)
        }
    }


def _token_snapshot() -> dict[str, Any]:
    return {
        "settings": {
            "client_safe": {
                "color_tokens": {"primary": {"%d1": "rgba(1, 2, 3, 1)"}},
                "color_tokens_user": {
                    "default": {
                        "cBase": {
                            "%nm": "Base Color",
                            "rgba": "rgba(4, 5, 6, 1)",
                            "order": 0,
                        }
                    }
                },
                "font_tokens": {"%d1": "Inter"},
                "font_tokens_user": {
                    "default": {
                        "fBase": {
                            "%nm": "Base Font",
                            "font_family": "Inter",
                            "order": 0,
                        }
                    }
                },
            }
        }
    }


def _time_samples(samples: int, sample_fn: Callable[[], Sample]) -> dict[str, Any]:
    rows = [sample_fn() for _ in range(samples)]
    elapsed_samples = [row.elapsed_seconds for row in rows]
    return {
        "elapsed_seconds": median(elapsed_samples),
        "elapsed_samples": elapsed_samples,
        "json_bytes": int(median(row.json_bytes for row in rows)),
        "build_count": int(median(row.build_count for row in rows)),
        "write_count": int(median(row.write_count for row in rows)),
        "cache_save_count": int(median(row.cache_save_count for row in rows)),
    }


def _style_resolution_sample(count: int, *, warm_lookups: int | None) -> Sample:
    with tempfile.TemporaryDirectory(prefix="style-resolution-") as temp_name:
        cli = _new_cli(Path(temp_name), _style_snapshot(count))
        expected = f"Text_benchmark_{count - 1}_"
        name = f"Benchmark {count - 1}"
        if warm_lookups is not None:
            if cli.find_style_id(name, element_type="Text") != expected:
                raise RuntimeError("style benchmark warm-up did not resolve the expected style")
        started = perf_counter()
        iterations = warm_lookups or 1
        for _ in range(iterations):
            if cli.find_style_id(name, element_type="Text") != expected:
                raise RuntimeError("style benchmark did not resolve the expected style")
        elapsed = perf_counter() - started
    return Sample(elapsed_seconds=elapsed)


def _assignment_sample(operations: int) -> Sample:
    with tempfile.TemporaryDirectory(prefix="style-assignment-") as temp_name:
        cli = _new_cli(Path(temp_name), {})
        payload = PayloadBuilder(appname="style-lifecycle-benchmark")
        random.seed(45)
        started = perf_counter()
        for index in range(operations):
            cli._queue_style_assignment_changes(
                payload,
                ["%p3", "index", "%el", f"element-{index}"],
                "Text_benchmark_",
                style_props={"%fc": "rgba(1, 2, 3, 1)", "%fs": 16},
            )
        elapsed = perf_counter() - started
        metrics = PayloadMetrics()
        metrics.capture_build(payload)
    return Sample(
        elapsed,
        metrics.json_bytes,
        metrics.build_count,
        metrics.write_count,
        metrics.cache_save_count,
    )


def _color_font_crud_sample() -> Sample:
    with tempfile.TemporaryDirectory(prefix="style-token-crud-") as temp_name:
        cli = _new_cli(Path(temp_name), _token_snapshot())
        metrics = PayloadMetrics()
        cli._dispatch_payload = metrics.capture
        _capture_cache_saves(cli, metrics)
        random.seed(45)
        started = perf_counter()
        results = (
            cli.create_color("Benchmark Color", "rgba(10, 20, 30, 1)"),
            cli.update_color("Benchmark Color", "rgba(30, 20, 10, 1)"),
            cli.delete_color("Benchmark Color"),
            cli.create_font("Benchmark Font", "Source Sans 3"),
            cli.update_font("Benchmark Font", "Roboto"),
            cli.delete_font("Benchmark Font"),
        )
        elapsed = perf_counter() - started
        if not all(results):
            raise RuntimeError(f"color/font CRUD benchmark failed: {results}")
    return Sample(
        elapsed,
        metrics.json_bytes,
        metrics.build_count,
        metrics.write_count,
        metrics.cache_save_count,
    )


def _write_import_fixture(root: Path, fonts: int, colors: int, styles: int) -> tuple[Path, Path]:
    families = [f"Benchmark Font {index}" for index in range(fonts)]
    tokens = {
        "color": {
            "benchmark": {
                f"color_{index}": {
                    "type": "color",
                    "value": f"#{index % 256:02X}{(index * 3) % 256:02X}{(index * 7) % 256:02X}",
                }
                for index in range(colors)
            }
        },
        "typography": {
            f"style_{index}": {
                "type": "typography",
                "value": {
                    "fontFamily": families[index % fonts],
                    "fontSize": 12 + (index % 24),
                    "fontWeight": 400 + ((index % 4) * 100),
                    "lineHeight": 18 + (index % 24),
                    "color": f"#{index % 256:02X}{(index * 3) % 256:02X}{(index * 7) % 256:02X}",
                },
            }
            for index in range(styles)
        },
    }
    config = {
        "naming": {"separator": " ", "case": "title"},
        "filters": {
            "include_color_paths": ["color.*"],
            "include_typography_paths": ["typography.*"],
        },
        "default_color_mapping": {},
    }
    tokens_path = root / "tokens.json"
    config_path = root / "config.json"
    tokens_path.write_text(json.dumps(tokens, sort_keys=True), encoding="utf-8")
    config_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
    return tokens_path, config_path


def _token_import_sample(fonts: int, colors: int, styles: int) -> Sample:
    with tempfile.TemporaryDirectory(prefix="style-token-import-") as temp_name:
        root = Path(temp_name)
        cli = _new_cli(root, _token_snapshot())
        tokens_path, config_path = _write_import_fixture(root, fonts, colors, styles)
        metrics = PayloadMetrics()
        cli._dispatch_payload = metrics.capture
        _capture_cache_saves(cli, metrics)
        random.seed(45)
        started = perf_counter()
        ok = cli.sync_figma_tokens(
            str(tokens_path),
            config_path=str(config_path),
            all_tokens=True,
        )
        elapsed = perf_counter() - started
        if not ok:
            raise RuntimeError("token import benchmark failed")
    return Sample(
        elapsed,
        metrics.json_bytes,
        metrics.build_count,
        metrics.write_count,
        metrics.cache_save_count,
    )


def _definition_sample() -> Sample:
    snapshot = {
        "styles": {
            "Text_body_": {
                "%d": "Body",
                "%x": "Text",
                "%p": {"%fs": 16},
            }
        }
    }
    with tempfile.TemporaryDirectory(prefix="style-definitions-") as temp_name:
        cli = _new_cli(Path(temp_name), snapshot)
        metrics = PayloadMetrics()
        cli._dispatch_payload = metrics.capture
        _capture_cache_saves(cli, metrics)
        random.seed(45)
        started = perf_counter()
        results = (
            cli.create_style(
                "Benchmark New",
                "Text",
                allow_property_match=False,
                font_size=18,
                font_color="rgba(1, 2, 3, 1)",
            ),
            cli.update_style_definition(
                "Benchmark New",
                "Text",
                style_id_override="Text_benchmark_new_",
                font_size=20,
            ),
            cli.rename_style("Text_benchmark_new_", "Benchmark Renamed"),
            cli.delete_style("Text_benchmark_new_", element_type="Text"),
        )
        elapsed = perf_counter() - started
        if not all(results):
            raise RuntimeError(f"definition benchmark failed: {results}")
    return Sample(
        elapsed,
        metrics.json_bytes,
        metrics.build_count,
        metrics.write_count,
        metrics.cache_save_count,
    )


def _run_benchmarks(config: BenchmarkConfig) -> dict[str, Any]:
    benchmarks: dict[str, Any] = {}
    for count in config.style_counts:
        benchmarks[f"style_resolution_{count}_cold"] = _time_samples(
            config.samples,
            partial(_style_resolution_sample, count, warm_lookups=None),
        )
        benchmarks[f"style_resolution_{count}_warm"] = _time_samples(
            config.samples,
            partial(
                _style_resolution_sample,
                count,
                warm_lookups=config.warm_lookups,
            ),
        )
    benchmarks["assignment_payload_construction"] = _time_samples(
        config.samples,
        lambda: _assignment_sample(config.assignment_operations),
    )
    benchmarks["color_font_crud"] = _time_samples(config.samples, _color_font_crud_sample)
    import_name = (
        f"token_import_{config.import_fonts}_{config.import_colors}_{config.import_styles}"
    )
    benchmarks[import_name] = _time_samples(
        config.samples,
        lambda: _token_import_sample(
            config.import_fonts,
            config.import_colors,
            config.import_styles,
        ),
    )
    benchmarks["definition_operations"] = _time_samples(config.samples, _definition_sample)
    return {
        "schema_version": 2,
        "samples": config.samples,
        "workload": {
            "style_counts": list(config.style_counts),
            "warm_lookups": config.warm_lookups,
            "assignment_operations": config.assignment_operations,
            "import_fonts": config.import_fonts,
            "import_colors": config.import_colors,
            "import_styles": config.import_styles,
        },
        "benchmarks": benchmarks,
    }


def run_benchmarks(config: BenchmarkConfig = BenchmarkConfig()) -> dict[str, Any]:
    """Run every Stage 4.5 benchmark without performing a remote Bubble write."""
    with _silence_runtime_logs():
        return _run_benchmarks(config)


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two reports produced with the same workload."""
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
            "before_json_bytes": int(before_row["json_bytes"]),
            "after_json_bytes": int(after_row["json_bytes"]),
            "before_build_count": int(before_row["build_count"]),
            "after_build_count": int(after_row["build_count"]),
            "before_write_count": int(before_row["write_count"]),
            "after_write_count": int(after_row["write_count"]),
            "before_cache_save_count": int(before_row["cache_save_count"]),
            "after_cache_save_count": int(after_row["cache_save_count"]),
        }
    return {"schema_version": 2, "benchmarks": comparison}


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark report must contain a JSON object")
    return cast(dict[str, Any], payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--output")
    parser.add_argument("--compare-before")
    parser.add_argument("--compare-after")
    args = parser.parse_args(argv)
    if bool(args.compare_before) != bool(args.compare_after):
        parser.error("--compare-before and --compare-after must be provided together")
    if args.compare_before:
        report = compare_reports(_load_json(args.compare_before), _load_json(args.compare_after))
    else:
        report = run_benchmarks(BenchmarkConfig(samples=args.samples))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
