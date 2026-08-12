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

### Stage 2: SDK contracts

Target `aria_runtime/bubble_sdk.py`, currently 49.6% with 1,520 missing
statements. Test loaders, payload builders, identifiers, style/action builders,
and error paths as separate contracts. Extract cohesive boundaries when tests
need excessive object construction or monkeypatching.

Exit criteria:

- each extracted boundary is at least 90%;
- `bubble_sdk.py` reaches at least 70%;
- the global ratchet is raised to the highest stable value with at least 0.1
  percentage point of headroom.

### Stage 3: HTML import pipeline

Target the legacy HTML mapper, source parser, and parser. The mapper is the
second-largest debt block, with 3,317 missing statements. Organize fixtures by
layout, typography, responsive constraints, media, reusable components, and
malformed source.

Exit criteria:

- parser modules reach at least 85%;
- mapper families have deterministic golden payloads and failure contracts;
- HTML conversion benchmarks show no material regression.

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
