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
- full suite: 1,100 Python and 11 Node tests passed;
- global combined coverage: 37.0441%;
- global ratchet: 36.8%, retaining 0.24 percentage point of headroom;
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

#### Family 1: profile, cache, context, and reference resolution

This family is being delivered through three bounded internal extractions:

1. **Stage 4.1 — durable cache store: completed in PR #19.**
   `BubbleCLICacheStore` now owns normalized JSON persistence, crash-safe atomic
   replacement, legacy migration, and unreadable-cache recovery. The boundary
   reached 95.3% focused combined branch coverage; the complete suite contained
   1,131 Python and 11 Node tests. A 100-cycle load/save benchmark completed in
   0.0286 second.
2. **Stage 4.2 — context/element/workflow alias registry: completed on
   2026-08-13.** `ContextAliasRegistry` now owns canonical profile buckets,
   context alias fan-out and precedence, element enrichment and legacy payloads,
   workflow aliases, defensive lookups, cross-process refresh, and scoped
   cleanup. `BubbleCLI` retains its prior methods as compatibility facades.
3. **Stage 4.3 — discovery-backed reference resolution: completed on
   2026-08-14.** `ContextReferenceResolver` now owns context discovery
   traversal, cached element materialization, capture parsing, element
   matching/selection, `inspect_context`, and `resolve_refs`. It consumes the
   cache store and alias registry through a typed host without owning
   persistence or alias lifecycle.

Stage 4.2 results:

- removed 393 lines of direct alias lifecycle logic from `bubble_cli.py` and
  replaced them with 108 lines of construction, facades, and shared-cache
  reconciliation (net reduction: 285);
- added a 553-line focused registry boundary with 317 executable statements;
- added 53 behavior, real-`BubbleCLI`, and spawned-process concurrency tests;
- `context_alias_registry.py`: 97.1% combined branch coverage in the full run;
- full suite: 1,184 Python and 11 Node tests passed;
- global combined coverage: 38.1217%;
- global ratchet: 38.0%, retaining 0.12 percentage point of headroom;
- catalog remained at 327 MCP tools, with zero uncovered tools and no changes
  to schemas, aliases, dispatch routes, previews, or result shapes;
- benchmark: 1,000 registry lookups in 0.002996 second and 100 in-memory alias
  mutations in 0.000264 second.

Stage 4.2 also closes three reliability gaps inherited from the direct
implementation: concurrent workflow writers no longer overwrite sibling
updates, returned element/workflow payloads cannot mutate cached state by
reference, and context cleanup removes both modern scoped workflow buckets and
historical flat keys. The cache store now holds an inter-process lock across
read-modify-write transactions and legacy migration; legacy whole-cache writers
apply only their local three-way delta to the latest shared payload, and a
post-clear transaction cannot resurrect stale state.

Stage 4.3 results:

- removed 910 lines of direct discovery/reference logic from `bubble_cli.py`
  and retained 52 lines of resolver construction and compatibility facades
  (net reduction: 858 lines in the legacy class);
- added the 1,172-line resolver boundary with 578 executable statements and 55
  focused behavior/facade tests;
- `context_reference_resolver.py`: 96.3% focused combined branch coverage;
- full suite: 1,239 Python and 11 Node tests passed;
- global combined coverage: 38.8893%;
- global ratchet: 38.7%, retaining 0.1893 percentage point of headroom; raising
  it to 38.8% would leave only 0.0893 point and violate the 0.1-point policy;
- catalog remained at 327 MCP tools, with zero uncovered tools and no changes
  to schemas, aliases, annotations, dispatch routes, previews, or result
  shapes;
- median benchmark on the same literal synthetic dataset: 1,000 context
  enumerations took 0.002088 second versus 0.001749 second before extraction
  (+0.000339 second); 1,000 element resolutions took 0.009162 second versus
  0.008161 second (+0.001001 second); and 100 context inspections took
  0.001513 second versus 0.001441 second (+0.000072 second). The percentage
  deltas are visible at this microsecond scale, but the absolute facade cost is
  below 1.1 microseconds per operation and is not a material regression.

Implementer self-review and completed independent review hardened malformed
source rows and resolved the first three Important findings: hybrid index
aliases receive their canonical ID/key score before lower-priority embedded
name/text matches; literal tests cover raw, readable, missing, malformed, and
non-mapping text-property payloads; and the review record distinguishes the
implementer pass from independent review. A final branch review then identified
two further Important gaps. Production-shaped regressions now prove the real
index `id`/`alias_id` row contract, highest-score logical deduplication, and
durable row-local capture handling that skips both deep recursion failures and
noncanonical interior path segments while preserving valid siblings.

**Next boundary — Family 2 visual mutations.** Extract visual element
create/update/delete orchestration behind a typed boundary that consumes the
Stage 4.3 resolver for target selection while preserving every existing
preview default, confirmation gate, payload shape, dispatch route, and CLI/MCP
result contract.

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
