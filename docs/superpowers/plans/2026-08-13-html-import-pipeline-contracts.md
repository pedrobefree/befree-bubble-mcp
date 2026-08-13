# HTML Import Pipeline Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the HTML import pipeline with explicit parser contracts, deterministic mapper goldens, linear-time geometry normalization, and a repeatable performance guard.

**Architecture:** Keep the public `HTMLParser` and `HTMLToBubbleMapper` interfaces stable. Strengthen the two parser layers at their input boundaries, exercise mapper behavior through representative source fixtures instead of coupling tests to private implementation, and add a benchmark command that compares the same fixture corpus before and after future changes.

**Tech Stack:** Python 3.11, BeautifulSoup, pytest, coverage.py, JSON golden fixtures, `time.perf_counter`.

**Spec:** `docs/optimization-roadmap.md`, Stage 3: HTML import pipeline.

## Global Constraints

- Preserve the existing `HTMLParser.parse`, `HTMLParser.parse_snapshot`, and `HTMLToBubbleMapper.map_tree` public contracts.
- Parser modules must reach at least 85% statement coverage with branch coverage enabled.
- Mapper fixtures must cover layout, typography, responsive constraints, media, reusable visual containers, controls, and malformed or hidden source.
- Golden outputs must be deterministic JSON and reviewable without a browser or network.
- The benchmark corpus must show no material regression relative to the pre-change local baseline.
- The repository coverage ratchet may only move upward and must retain at least 0.1 percentage point of headroom.

---

### Task 1: Normalize parser boundaries and geometry in linear time

**Files:**
- Modify: `src/bubble_mcp/aria_runtime/html_to_bubble/source_parser.py`
- Modify: `src/bubble_mcp/aria_runtime/html_to_bubble/parser.py`
- Create: `tests/unit/test_html_source_parser_contracts.py`
- Create: `tests/unit/test_html_rendered_parser_contracts.py`

**Interfaces:**
- Consumes: BeautifulSoup `Tag` objects and renderer snapshot dictionaries.
- Produces: normalized semantic nodes whose `attributes["class"]` is always `list[str]`, whose media URL is safe and absolute when possible, and whose missing geometry can be hydrated from inline/computed pixel styles.

- [x] **Step 1: Write failing source-parser tests**

Cover HTML fragments, CSS rules and selector precedence, Tailwind/Bootstrap inference, text segments, URL normalization, snapshot attributes, invalid snapshot nodes, and whitespace handling. Include a snapshot with `"class": "cs_progressbar d-flex"` and assert the class value becomes `['cs_progressbar', 'd-flex']`.

- [x] **Step 2: Run the source-parser tests and verify the snapshot class contract fails**

Run: `rtk ./.venv/bin/python -m pytest tests/unit/test_html_source_parser_contracts.py -q`

Expected: at least the snapshot class normalization assertion fails because string classes are currently preserved as one string.

- [x] **Step 3: Normalize class and boolean attribute values at the parser boundary**

Update `_normalize_attrs` so string class attributes split on whitespace, list classes remain normalized lists, absent classes become `[]`, and `None` boolean attributes become an empty string instead of the literal `"None"`.

- [x] **Step 4: Write failing rendered-parser tests**

Cover progressbar labels, interactive containers containing mixed media/structural content, pixel parsing, invalid pixel values, and geometry hydration on both raw HTML and renderer snapshots. Instrument `_hydrate_rendered_inline_geometry` and assert one call per semantic node.

- [x] **Step 5: Remove recursive reprocessing and hydrate snapshot geometry**

Make `_hydrate_rendered_inline_geometry` operate on exactly one node. Rely on recursive `parse_element` dispatch to process descendants once, and invoke the same one-node hydration from `_parse_snapshot_node` so both parser entrypoints share the geometry contract.

- [x] **Step 6: Run parser tests and measure focused coverage**

Run the two new files plus `tests/unit/test_html_converter.py` under branch coverage, then report only `parser.py` and `source_parser.py`. Expected: both modules at or above 85% statement coverage.

- [x] **Step 7: Commit the parser boundary**

Commit message: `refactor: harden HTML parser contracts`

---

### Task 2: Lock mapper families with deterministic golden payloads

**Files:**
- Create: `tests/fixtures/html/import-pipeline-contracts.html`
- Create: `tests/fixtures/golden/html-import-pipeline.json`
- Create: `tests/unit/test_html_mapper_contracts.py`

**Interfaces:**
- Consumes: semantic trees from the public `HTMLParser` interface.
- Produces: stable generic Bubble component trees from `HTMLToBubbleMapper.map_tree`.

- [x] **Step 1: Add a representative HTML fixture**

Include a responsive row/column layout, nested headings and inline emphasis, a link/button, form controls, an image with a relative URL, a gradient visual container, and hidden/noise source. Keep the fixture self-contained and deterministic.

- [x] **Step 2: Write the golden comparison test**

Parse the fixture with a fixed HTTPS base URL, map the semantic tree, recursively remove only explicitly documented volatile diagnostic keys, and compare the result with `tests/fixtures/golden/html-import-pipeline.json`.

- [x] **Step 3: Add mapper failure and helper contracts**

Assert empty nodes, hidden elements, skipped tags, unsafe media URLs, malformed dimensions, color/gradient parsing, transform offsets, and rich-text normalization return stable values without exceptions.

- [x] **Step 4: Generate and inspect the golden payload**

Generate the golden once from the public pipeline, inspect the full JSON diff, and retain only source-derived deterministic fields.

- [x] **Step 5: Run mapper and existing HTML tests**

Run: `rtk ./.venv/bin/python -m pytest tests/unit/test_html_mapper_contracts.py tests/unit/test_html_converter.py -q`

Expected: all tests pass and the existing fixture behavior remains unchanged.

- [x] **Step 6: Commit the mapper contracts**

Commit message: `test: lock HTML mapper golden contracts`

---

### Task 3: Add a repeatable conversion benchmark and update the roadmap

**Files:**
- Create: `scripts/benchmark_html_conversion.py`
- Create: `tests/unit/test_html_conversion_benchmark.py`
- Modify: `docs/optimization-roadmap.md`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: JSON with fixture name, warmups, iterations, sample count, median seconds, best seconds, and conversions per second.

- [x] **Step 1: Write benchmark API tests**

Import the benchmark module, run a two-sample smoke configuration against the fixture corpus, and assert its JSON-compatible schema and positive timings. Reject zero or negative iteration/sample arguments with `ValueError`.

- [x] **Step 2: Implement the benchmark runner**

Use `perf_counter`, warm up before measurement, construct fresh parser/mapper objects per conversion, and expose deterministic CLI arguments for fixture, warmups, iterations, and samples. Do not make timing assertions in pytest.

- [x] **Step 3: Compare pre-change and post-change performance**

Run the same `hero.html` corpus with 20 conversions across seven samples. Compare the post-change median with the recorded pre-change median `0.015476292` seconds per 20 conversions and document the ratio.

- [x] **Step 4: Update roadmap progress and the coverage ratchet**

Mark Stage 2 complete, record Stage 3 parser and mapper-contract results, and raise `fail_under` to the highest stable tenth that retains at least 0.1 percentage point of headroom after a full sharded branch-coverage run.

- [x] **Step 5: Run static and focused quality checks**

Run Ruff, MyPy, the benchmark smoke, `git diff --check`, and the focused HTML suite.

- [x] **Step 6: Commit benchmark and roadmap updates**

Commit message: `chore: add HTML conversion performance guard`

---

### Task 4: Full validation, code review, and publication

**Files:**
- Review all files changed since `origin/main`.

**Interfaces:**
- Produces: a locally validated draft pull request with review findings resolved.

- [x] **Step 1: Run the complete Python and Node test suites**

Run the repository's full pytest suite, Node tests, runtime coverage checks, catalog quality checks, package/install smoke tests, sensitive-data audit, Ruff, MyPy, and `git diff --check`.

- [x] **Step 2: Run full branch coverage and confirm the ratchet**

Use the established coverage shards, combine them, and confirm the report clears the updated `fail_under` with at least 0.1 point of headroom.

- [x] **Step 3: Request independent code review**

Review `origin/main..HEAD` against this plan. Fix every Critical and Important finding, rerun affected checks, and commit fixes separately.

- [x] **Step 4: Push and open a draft PR**

Push `codex/html-import-contracts-round-3-stage-3`, open a draft PR against `main`, and include the implementation summary, coverage deltas, benchmark ratio, validation evidence, and any infrastructure-only CI limitation.

## Self-Review

- Spec coverage: parser coverage, mapper families, malformed input, benchmark comparison, roadmap status, ratchet, review, and publication each map to a task above.
- Placeholder scan: no deferred implementation placeholders are present.
- Type consistency: both parsers continue returning `dict[str, Any]`; mapper and benchmark consume the same public tree contract.
