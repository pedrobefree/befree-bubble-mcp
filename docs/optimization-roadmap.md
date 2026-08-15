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
- added the 1,182-line resolver boundary with 586 executable statements and 56
  focused behavior/facade tests;
- `context_reference_resolver.py`: 96.4% focused combined branch coverage;
- full suite: 1,240 Python and 11 Node tests passed;
- global combined coverage: 38.9001%;
- global ratchet: 38.8%, retaining 0.1001 percentage point of headroom;
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
The closing review also restored generic property observations such as
`%p3.pg.%el.hero.%p.%3` as valid cache evidence while continuing to reject a
later/interleaved `%el` restart, with a real-`BubbleCLI` persistence regression.

#### Family 2: visual mutations

Family 2 is delivered as a composed boundary through deletion, creation, and
update stages. The services consume the Stage 4.3 resolver-compatible host for
target selection while preserving every preview default, confirmation gate,
payload shape, dispatch route, and CLI/MCP result contract.

**Stage 4.4a — visual deletions: completed on 2026-08-14.** The typed target
and deletion services now own existing-element hydration, canonical-path
selection, type validation, `RemoveElement` construction, parent `issues_sub`
maintenance, dispatch, and post-success alias cleanup. All 26 concrete visual
`delete_*` methods remain explicit `BubbleCLI` compatibility facades; deletion
of pages, reusables, styles, colors, fonts, data, workflows, and API objects is
unchanged and remains outside this boundary.

Stage 4.4a results:

- removed 2,750 lines of duplicated visual deletion bodies from `bubble_cli.py`
  and retained 392 lines of explicit signatures/facades (net reduction: 2,358
  physical lines);
- added a 584-line composed package and 45 literal behavior/facade tests;
- `deletions.py`: 96.7% focused combined branch coverage;
- `targets.py` plus `deletions.py`: 96.7% focused combined branch coverage;
- full suite: 1,285 Python and 11 Node tests passed;
- catalog remained at 327 MCP tools and CLI parity remained 207 commands with
  zero missing mappings;
- Ruff, MyPy, preview-write, family-preview, and `git diff --check` passed;
- no tool names, schemas, aliases, annotations, previews, confirmations,
  dispatch routes, payload ordering, or result shapes changed.

The post-review repair restored table descendant cleanup, the captured
`issues_list` sequences for links and uploaders, and cached context-object
fallback for parent `issues_sub` updates. Six literal regressions cover these
compatibility paths, including malformed nested table snapshots.

**Stage 4.4b — visual creations: completed on 2026-08-14.** The creation
service now owns context/parent preparation, parent fallback resolution,
canonical create/index sequencing, parent-child index maintenance, preview and
dispatch finalization, discovery injection, and created-alias caching. The
element-specific builders and public `BubbleCLI` signatures remain in place.

Stage 4.4b results:

- replaced 904 lines of repeated creation orchestration in `bubble_cli.py`
  with 328 lines of explicit facades and builder-specific behavior;
- added a 301-line creation service and 24 literal behavior/facade tests;
- `creations.py`: 97.6% focused branch coverage;
- full suite: 1,309 Python and 11 Node tests passed;
- catalog remained at 327 MCP tools and CLI parity remained 207 commands with
  zero missing mappings;
- Ruff, MyPy, catalog quality, preview-write, and `git diff --check` passed;
- the refreshed local Bubble test profile passed all 16 preview-write cases;
- no tool names, schemas, aliases, annotations, preview defaults, dispatch
  routes, payload ordering, or result shapes changed.

The post-review repair routed reusable-instance and icon finalization through
the shared creation service, preserved normalized icon slot targeting, and
gated icon sizing updates to successful non-preview creation. Five literal
regressions cover these facade contracts.

**Stage 4.4c — visual updates: completed on 2026-08-14.** The update service
now owns canonical target reuse, property/style payload sequencing, preview,
dispatch, and failure handling. `_resolve_element_for_updates`,
`_apply_element_updates`, `update_text`, and `update_layout_property` delegate
to the shared boundary. Element-specific property collection and all Family 3
style lookup/assignment helpers remain on the host.

Stage 4.4c and final Family 2 results:

- replaced another 348 lines of update/creation orchestration in `bubble_cli.py`
  with 142 lines of compatibility facades and special-resolution behavior;
- across Family 2, removed 3,944 legacy lines and retained/added 800 facade and
  element-specific lines in `bubble_cli.py` (net reduction: 3,144 lines);
- the composed package is 1,022 physical lines and is covered by 69 focused
  behavior/facade tests;
- `updates.py` plus `targets.py`: 96.5% focused branch coverage;
- the complete visual-mutation package: 97.2% combined branch coverage;
- full suite: 1,309 Python and 11 Node tests passed;
- global combined branch coverage: 40.6111%; the repository ratchet is 40.5%,
  retaining 0.111 percentage point of measured headroom;
- catalog remained at 327 MCP tools and 207 CLI operation commands with zero
  missing mappings;
- runtime smokes passed coverage 2/2, agent routing 9/9, visual repair 1/1,
  preview-write 16/16, and family-preview 32/32 after correcting its stale
  `show_message` fixture to the supported `show_alert` action;
- Ruff, MyPy, package/setup smokes, sensitive-path audit, catalog quality,
  CLI parity, and `git diff --check` passed.

Representative dry-run payload benchmarks (median of seven 200-operation
runs, same literal fixture before/after extraction) measured:

- create: 626.22 µs → 637.54 µs (+11.32 µs, +1.8%);
- update: 108.09 µs → 109.77 µs (+1.68 µs, +1.6%);
- delete: 3,342.45 µs → 3,065.62 µs (-276.83 µs, -8.3%).

The small create/update deltas are immaterial relative to editor/network I/O;
deletion improved. No MCP names, schemas, aliases, annotations, confirmation
gates, preview defaults, payload ordering, dispatch routes, or result shapes
changed.

The final independent review found and closed two Important gaps before
publication: sparse cache hydration now prefers the embedded element ID and
recovers the candidate path so updates/deletions cannot fall back to the
context root; reusable-instance and icon finalization now also delegate to the
creation service, with icon post-create sizing retained after successful
execution only.

#### Family 3: style, color, font, and token lifecycle

Family 3 was delivered as the six-part Stage 4.5 stack on 2026-08-15. Public
CLI/MCP names, schemas, aliases, signatures, preview/confirmation behavior,
dispatch order, and result shapes remain unchanged throughout the stack.

1. **Stage 4.5a — style references (PR #26):** `StyleReferenceResolver` owns
   normalized snapshots, settings-backed defaults, ID/name/type matching,
   deterministic ambiguity handling, cache aliases, and raw/cache merge rules.
2. **Stage 4.5b — assignments and override policy (PR #27):**
   `StyleAssignmentService` owns style application, style removal, override
   pruning/clearing, property matching, and shared dry-run/dispatch behavior.
3. **Stage 4.5c — colors and fonts (PR #28):** `ColorTokenService` and
   `FontTokenService` own CRUD, canonical IDs, reference lookup, cache
   reconciliation, and preview/dispatch behavior for design tokens.
4. **Stage 4.5d — deterministic Figma import (PR #29):**
   `FigmaTokenImportService` owns normalized token ingestion, deterministic IDs,
   references, deduplication, result accounting, and definition-sink routing.
5. **Stage 4.5e — definitions and states (PR #30):**
   `StyleDefinitionService` owns definition CRUD, defaults, themes, states,
   transitions, order, and fail-closed cache/dispatch orchestration.
6. **Stage 4.5f — final evidence:** the finite 16^4 deterministic-ID suffix
   namespace now uses exhaustive deterministic probing and terminates explicitly
   on exhaustion; successful definition mutations invalidate stale references;
   Figma RGBA aliases use the projected color state; bulk token phases persist
   cache once; conditional MCP schemas match runtime operands; filter metadata
   is precise; and real Ruff/MyPy gates plus reproducible evidence close the
   stage.

Final Stage 4.5 results:

- full local suites: 1,576 Python and 11 Node tests passed;
- global combined line/branch coverage: 43.7576%; the ratchet remains 43.6%,
  leaving 0.1576 percentage point of measured headroom (43.7% would retain less
  than the prescribed 0.1 point);
- the complete `style_lifecycle` package: 96.6% combined branch coverage, with
  each behavior-bearing lifecycle module above 95%;
- catalog parity: 327 MCP tools and 207 CLI operation commands, with zero
  missing mappings;
- profile-independent smokes passed coverage 2/2, agent routing 9/9, and visual
  repair 1/1;
- an authorized local `smoke` profile compiled every safe read and preview:
  safe-read functionality 10/10, preview mutations 5/5, and family previews
  21/21, all with `executed=false`. The suite totals were 10/11, 15/16, and
  31/32 only because each includes the same `bubble_profile_status` preflight;
  its locally cached context was loadable and write-ready but stale;
- full Ruff (`src tests scripts`), MyPy (`src`, 141 files), package/setup,
  sensitive-path, catalog, and diff-hygiene gates passed.

Seven-run medians below compare the isolated Stage base `50c81f3` with the
completed stack. Payload build/write and cache-save counts are local captures;
no remote Bubble write was executed. Resolution has no payload metrics.

| Workload | Before | After | Delta | JSON bytes | Builds / writes | Cache saves |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 styles, cold index | 0.446 ms | 2.627 ms | +2.181 ms (+489.159%) | n/a | n/a | 0 -> 0 |
| 500 styles, 200 warm lookups | 88.110 ms | 1.209 ms | -86.900 ms (-98.628%) | n/a | n/a | 0 -> 0 |
| 5,000 styles, cold index | 4.928 ms | 28.642 ms | +23.714 ms (+481.243%) | n/a | n/a | 0 -> 0 |
| 5,000 styles, 200 warm lookups | 902.056 ms | 1.326 ms | -900.730 ms (-99.853%) | n/a | n/a | 0 -> 0 |
| 200 assignment payloads | 0.678 ms | 0.753 ms | +0.075 ms (+11.056%) | 140,294 -> 140,294 | 1/0 -> 1/0 | 0 -> 0 |
| color/font CRUD | 1.386 ms | 2.841 ms | +1.455 ms (+105.012%) | 2,939 -> 2,899 | 6/6 -> 6/6 | 3 -> 6 |
| 25/250/100 token import | 2,301.017 ms | 1,531.266 ms | -769.751 ms (-33.453%) | 3,605,189 -> 293,916 | 475/475 -> 202/202 | 475 -> 202 |
| definition operations | 1.773 ms | 1.977 ms | +0.204 ms (+11.531%) | 2,623 -> 2,623 | 5/5 -> 5/5 | 4 -> 4 |

The cold cost builds the reusable index once; the warm workload improves
98.6-99.9%. Positive deltas are 0.075-23.714 ms of local orchestration. Token
import improves 33.5%, reduces serialized bytes by 91.8%, and reduces cache
saves by 57.5%. Literal bulk regressions separately prove one save for a
500-color reorder, one for a 12-color delete, and two for a two-phase import.

Every staged PR received independent review against its base. The consolidated
final-review wave closed four additional Important and two Minor findings with
literal RED/GREEN regressions: post-success reference invalidation, projected
RGBA aliases, batched token-cache persistence, conditional runtime schemas,
exhaustive finite-ID probing, and exact filter metadata. Earlier findings also
remain covered, including default-style protection, stale-cache rejection,
builder-owned transitions, real HTML/Figma failure propagation, deterministic
ID collision handling, and static-gate enforcement. The consolidated evidence
and closing review are recorded in
`docs/superpowers/reviews/2026-08-15-style-token-lifecycle-review.md`.

GitHub CI for PRs #25–#30 remains infrastructure-blocked. The current check
jobs complete in two to four seconds with `steps: []`, so no workflow test step
runs; representative live runs `31898623436` and `31902065247` show the same
billing/infrastructure signature. The complete local validation matrix above is
the executable code evidence.

**Next Stage 4 boundary — Family 4 data/schema/settings lifecycle.** Extract
data types, fields, privacy, option sets/values, project settings, and redirects
behind typed services while retaining the public `BubbleCLI` facades and the
same catalog, preview, confirmation, payload, and dispatch contracts.

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
