# Optimization and Coverage Roadmap

This roadmap keeps coverage growth honest: production code stays in scope, every
ratchet increase is backed by behavior-focused tests, and large legacy modules
are decomposed before exhaustive branch coverage is attempted.

## Round 3 Baseline

The sharded branch-coverage run on 2026-08-12 executed 802 tests and measured:

- 32.6486% combined line and branch coverage;
- 35.5821% statement coverage;
- 26.4764% branch coverage;
- 65,696 statements in scope;
- 42,320 missing statements.

The repository ratchet is 32.5%. It must only move upward.

Completed in this round:

- extracted `DiscoveryDataBoundary` from the legacy SDK and covered it at 100%;
- made wheel smoke tests independent from checkout `PYTHONPATH`/`PYTHONHOME`;
- raised five low-risk runtime modules to 91% combined branch coverage;
- added a repeatable CLI-to-MCP parity audit;
- added the missing `add_event_action` and `set_comment` MCP capabilities;
- replaced five generic legacy schemas with explicit required/optional fields;
- split element-targeted `add_action` from event-targeted `add_event_action` in
  the agent-facing contract.

## Coverage Stages

### Stage 2: SDK contracts — completed

PRs #15 through #17 covered loaders, payload builders, identifiers,
style/action builders, discovery aliases, and error paths as separate
contracts. `bubble_sdk.py` reached 100% of its 3,311 executable lines and 94.0%
branch coverage; the extracted discovery boundary and app mapper also reached
100% line coverage.

The stage completed with 973 passing tests and a 35.0% global ratchet. The
illustrative `bubble_sdk.py` `__main__` block remains excluded from executable
coverage.

### Stage 3: HTML import pipeline — completed

The stage started with 3,317 missing mapper statements and parser coverage of
38.1% (`parser.py`) and 35.5% (`source_parser.py`). The implementation added
boundary-focused parser tests, deterministic layout/typography/responsive/media/
control goldens, malformed-source contracts, and a repeatable JSON benchmark.

Results on 2026-08-13:

- `parser.py`: 93.3% combined branch coverage;
- `source_parser.py`: 93.9% combined branch coverage;
- `mapper.py`: 46.0%, up from 30.1% in the focused baseline;
- full suite: 1,097 Python and 11 Node tests passed;
- global combined coverage: 37.0621%;
- global ratchet: 36.8%, retaining 0.26 percentage point of headroom;
- `hero.html` benchmark: 0.016024 seconds per 20 conversions versus the
  0.015476-second pre-change baseline (+3.5%, no material regression).

Production hardening in this stage normalized renderer snapshot classes and
boolean attributes, made geometry hydration linear in the parsed tree, applied
the same geometry contract to rendered snapshots, preserved semantic controls
with child options, enforced CSS cascade and `!important` precedence, rejected
unsafe URL schemes, and limited SVG data URLs to a strict passive XML allowlist.
Percentage dimensions are no longer interpreted as pixels. Two unused
Bootstrap stub helpers were removed.

Exit criteria:

- parser modules reach at least 85%;
- mapper families have deterministic golden payloads and failure contracts;
- HTML conversion benchmarks show no material regression.

All Stage 3 exit criteria are satisfied. Remaining mapper branches stay in
scope for future coverage growth when their behavior is exercised by real HTML
families rather than private-method-only tests.

### Stage 4: Bubble CLI decomposition

`aria_runtime/bubble_cli.py` contains 33,626 missing statements and dominates
the remaining debt. Covering it in place would create slow, brittle tests.
Extract and test one functional family at a time:

1. profile/cache/context and reference resolution;
2. visual create/update/delete operations;
3. styles, colors, fonts, and token import;
4. data types, fields, privacy, options, settings, and redirects;
5. workflows, events, actions, and authentication;
6. Figma, batch, natural-language, and asset bridges.

Each extraction must preserve the existing `BubbleCLI` method as a compatibility
facade until callers and catalog dispatch use the new boundary.

### Stage 5: Supporting debt

After the three dominant blocks, prioritize modules by risk and missing lines:
`vendor/bubble_modules.py`, context detection/path APIs, server dispatch,
compiler payloads, session/browser automation, and remote knowledge access.

The long-term target is near 100%, but the last branches must represent useful
behavior. Defensive branches that cannot occur should be removed or proven
unreachable, not hidden with coverage exclusions.

## Tool Catalog Findings

The packaged legacy Bubble CLI currently exposes 207 operation commands:

- 205 map directly to MCP tool names;
- `create-reusable-type` maps to canonical `create_reusable`;
- `reset-tmp` is intentionally CLI-only local housekeeping;
- zero operation commands are unmapped.

Run the parity audit with:

```bash
PYTHONPATH=src python scripts/audit_cli_catalog.py
```

`bubble_catalog_quality` also enforces this parity and verifies that all
Aria-compatible tools declare explicit agent-required fields.

The modern nested `bubble-mcp` CLI is an orchestration and administration
surface, so words such as `list`, `run`, and `status` are not one-to-one MCP
capabilities. A later catalog round should add an explicit leaf-command map
(`profile add`, `tools quality`, and so on) to its handler and corresponding MCP
tool where applicable.

## Consolidation and Alias Policy

Catalog consolidation is a compatibility migration, not a bulk rename:

1. choose one intent-focused canonical tool name and schema;
2. keep every public old name as an alias to the same handler;
3. generate alias schemas from the canonical schema to prevent drift;
4. mark aliases as deprecated in descriptions and exclude them from default
   search ranking while keeping direct calls functional;
5. test canonical/alias argument and result parity;
6. retain aliases for at least two minor releases;
7. remove an alias only in an explicitly documented major release.

Candidate families for semantic review include cache refresh/sync, visual
element update variants, query/data-source builders, and Figma component sync.
Similar names alone are not evidence of redundancy: consolidation requires
matching intent, required inputs, safety semantics, payload behavior, and
result contracts.

Before consolidation, capture tool-selection evals for ambiguous prompts and
record whether the canonical tool reduces discovery loops. Public mutation
tools must continue to default to preview and preserve confirmation gates.
