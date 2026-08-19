# Round A.1 Natural-Language Ambiguity Matrix Design

## Goal

Close Round A.1 with a deterministic, local evaluation matrix proving that
natural-language requests select the intended MCP tool among closely related
catalog entries. This stage builds on the complete exact-name and legacy CLI
inventory baseline delivered in stage 1.

## Scope

The matrix covers the ambiguity families identified by the Round A.1 roadmap:

- routine profile refresh versus legacy cache refresh and specialized cache
  synchronization;
- source-query construction versus data-source normalization;
- Figma-specific component, style, and token synchronization versus generic
  component synchronization;
- focused visual content replacement versus general element-property updates;
- reusable definitions versus reusable instances;
- safe versus permanent schema deletion and singular versus bulk design-token
  deletion;
- workflow, event, and empty-event creation;
- HTML element import versus HTML-derived style import.

Each family has at least two natural-language cases and at least one named
nearby rival. The initial corpus has exactly 27 cases across eight families.
English is the baseline
language; existing Portuguese routing regressions remain in the server tests
but multilingual expansion is not required to close A.1.

This stage does not:

- add the modern nested CLI map reserved for Round A.2;
- rename, consolidate, deprecate, or remove public MCP tools;
- change handler dispatch, schemas, payloads, preview defaults, confirmation
  gates, or result shapes;
- call an LLM, the network, a Bubble profile, or authenticated editor state;
- assert that ambiguous tools are behaviorally equivalent.

## Selected Approach

Use a checked-in JSON corpus plus a dedicated read-only ambiguity runner. Each
case declares a stable ID, family, natural-language query, expected tool, and
one or more contrast tools. Expected required arguments are derived from the
authoritative schema registry at runtime rather than duplicated in the fixture.

This is preferred to generated pairwise cases because generated names do not
prove natural-language routing. It is also preferred to the general planning
eval runner because that planner intentionally recognizes a narrower set of
mutation requests and would broaden A.1 into planning and payload behavior.

## Architecture

### Curated corpus

`tests/fixtures/evals/catalog-ambiguity.json` is the reviewable source of
natural-language intent. The loader fails closed on malformed records,
duplicate IDs, duplicate queries, missing tools, an expected tool repeated as a
contrast tool, empty contrast sets, or unknown families.

The corpus uses distinguishing outcome language rather than internal tool names
where possible. Cases that intentionally distinguish legacy compatibility
surfaces may mention their public option vocabulary, such as `capture_file`,
`query_source_type`, or `tokens_path`, because those fields express the actual
contract difference.

### Deterministic runner

`bubble_mcp.harness.catalog_ambiguity` loads the authoritative catalog and runs
every case through `search_tool_catalog(query, limit=5)` against three schema
orders: sorted canonical order, reversed order, and a stable one-position
rotation. A case passes only when:

1. the expected tool is the first match in all three orders;
2. its reported required arguments match the authoritative schema;
3. the complete top-match names and scores are identical across orders;
4. all declared contrast tools exist in the authoritative catalog.

Results are sorted by case ID and include the family, query, expected tool,
actual tool, contrast tools, required arguments, all order-specific top matches,
and a precise failure type. The aggregate report includes case and family
counts, pass counts for every ordering, order-independent count, and failed
case count.

### Ranking changes

RED cases may expose lexical ties or incorrect generic matches. Fixes stay in
the catalog search scorer and use small, declarative semantic signals shared by
all queries. They must not special-case complete fixture sentences or change
the exact-name fast path. Existing search, runbook, exact-name, and catalog
coverage tests remain green.

### Audit and quality gate

`scripts/audit_catalog_ambiguity.py` prints the report as stable JSON and exits
non-zero on any failure. `bubble_catalog_quality` adds a
`deterministic_ambiguity_matrix` check so catalog or ranking drift fails closed
in the normal quality gate. The stage-1 exact-name check remains separate.

## Failure Contracts

Diagnostics distinguish:

- invalid or duplicate corpus records;
- missing expected or contrast schemas;
- wrong top-ranked tool;
- required-argument contract mismatch;
- ranking or score changes caused by catalog order;
- a report marked non-OK without convertible per-case failures.

Every failure names the case ID, family, query, expected tool, actual tool, and
contrast set when available.

## Test Strategy

Implementation follows RED/GREEN:

1. add corpus-validation and runner tests before the runner exists;
2. verify the curated matrix fails on the current scorer for known ambiguity
   families;
3. implement the loader and runner without changing ranking;
4. add the smallest semantic scoring signals needed to make every case pass;
5. add order, schema-contract, diagnostic, checkout-script, and catalog-quality
   regressions;
6. run focused tests, the complete Python and Node suites, Ruff, MyPy, both A.1
   audits, runtime coverage, agent routing, the sensitive-path audit, and
   `git diff --check`.

## Completion

Round A.1 is closed when the stage-1 327-tool exact-name audit and the new
natural-language matrix are both green, all declared ambiguity families have
passing order-independent evidence, full local verification is green, the
roadmap records fresh evidence, and independent review finds no unresolved
load-bearing issue. Round A.2 begins from a new branch and owns the modern
nested CLI leaf-command map.
