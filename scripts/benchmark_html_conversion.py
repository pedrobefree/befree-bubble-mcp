#!/usr/bin/env python3
"""Benchmark the deterministic HTML parser-to-mapper conversion pipeline."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from bubble_mcp.aria_runtime.html_to_bubble import HTMLParser, HTMLToBubbleMapper  # noqa: E402


DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/html/import-pipeline-contracts.html"


def _positive(name: str, value: int) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def convert_html(html: str, *, base_url: str = "https://benchmark.invalid/") -> dict[str, Any]:
    """Convert one HTML document with fresh public pipeline objects."""
    parsed = HTMLParser(base_url=base_url).parse(html)
    mapped = HTMLToBubbleMapper(base_url=base_url).map_tree(parsed)
    if mapped is None:
        raise ValueError("fixture did not produce a Bubble mapping")
    return mapped


def benchmark_fixture(
    fixture: Path,
    *,
    warmups: int = 5,
    iterations: int = 50,
    samples: int = 7,
    base_url: str = "https://benchmark.invalid/",
) -> dict[str, Any]:
    """Measure a fixture and return a JSON-compatible timing report."""
    _positive("warmups", warmups)
    _positive("iterations", iterations)
    _positive("samples", samples)
    fixture_path = Path(fixture).resolve()
    html = fixture_path.read_text(encoding="utf-8")

    for _ in range(warmups):
        convert_html(html, base_url=base_url)

    timings: list[float] = []
    for _ in range(samples):
        started = perf_counter()
        for _ in range(iterations):
            convert_html(html, base_url=base_url)
        timings.append(perf_counter() - started)

    median_seconds = statistics.median(timings)
    best_seconds = min(timings)
    seconds_per_conversion = median_seconds / iterations
    return {
        "fixture": fixture_path.name,
        "warmups": warmups,
        "iterations_per_sample": iterations,
        "samples": samples,
        "median_seconds": median_seconds,
        "best_seconds": best_seconds,
        "seconds_per_conversion": seconds_per_conversion,
        "conversions_per_second": 1.0 / seconds_per_conversion,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--base-url", default="https://benchmark.invalid/")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = benchmark_fixture(
            args.fixture,
            warmups=args.warmups,
            iterations=args.iterations,
            samples=args.samples,
            base_url=args.base_url,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
