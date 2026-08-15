# Stage 4.5 style/token lifecycle — reproducible closing evidence

Date: 2026-08-15  
Stage base: `50c81f3` (`origin/main` at Stage start)  
Closing base: `e080e2e` (`codex/style-token-lifecycle-4-5e-definitions`)  
Closing branch: `codex/style-token-lifecycle-4-5f-final-evidence`

## Scope and compatibility result

Stage 4.5 extracts style references, assignment/override policy, color/font
tokens, deterministic Figma token import, and style definitions/states from the
legacy `BubbleCLI` orchestration surface. `StyleLifecycleService` composes those
boundaries while the existing public CLI/MCP names, aliases, signatures,
schemas, result shapes, preview/confirmation behavior, dispatch order, and SDK
wire builders remain stable.

The final catalog contains 327 MCP tools and 207 CLI operation commands. The
audit reports 205 direct matches, one alias, one intentional CLI-only command,
and zero missing mappings.

## Deferred findings resolved in Stage 4.5f

### Finite deterministic-ID namespace

A literal regression forced every one of the 16^4 four-hex collision suffixes
to collide and rejected any probe beyond that finite namespace.

RED:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_figma_import.py::test_stable_token_id_fails_explicitly_when_suffix_namespace_is_exhausted
FAILED ... AssertionError: searched past the finite four-hex suffix namespace
1 failed
```

Minimal fix: replace the unbounded collision loop with `range(16**4)` and raise
`RuntimeError("deterministic token ID namespace exhausted")` after all suffixes
are occupied.

GREEN:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/unit/test_style_lifecycle_figma_import.py::test_stable_token_id_fails_explicitly_when_suffix_namespace_is_exhausted tests/unit/test_style_lifecycle_figma_import.py::test_stable_token_id_adds_deterministic_suffix_on_collision
2 passed in 0.20s
```

### Static-gate debt

The prior repository configuration excluded all of `aria_runtime` from Ruff
and MyPy, so the prescribed directory lifecycle gate inspected nothing. The
configuration now excludes only named inherited runtime debt and deliberately
includes `aria_runtime/style_lifecycle`. Narrow `TYPE_CHECKING` imports preserve
the legacy direct-execution fallback without suppressing new lifecycle code.
The only MyPy overrides are exact inherited dependencies
`bubble_mcp.aria_runtime.bubble_sdk` and
`bubble_mcp.aria_runtime.figma_bridge.*`; there is no lifecycle blanket ignore.

```text
rtk ./.venv/bin/ruff check src tests scripts
All checks passed!

rtk ./.venv/bin/mypy src
Success: no issues found in 141 source files

rtk ./.venv/bin/mypy src/bubble_mcp/aria_runtime/style_lifecycle
Success: no issues found in 9 source files
```

The inherited root `aria_runtime/*.py` monolith and named runtime subpackages
remain excluded from Ruff. Absorbing that historical backlog is intentionally
outside this stage; new lifecycle code is no longer hidden by it.

## Benchmark method

`scripts/benchmark_style_lifecycle.py` is deterministic and network-free. It
uses public `BubbleCLI` facades and replaces dispatch with an in-memory payload
capture, recording median elapsed time, JSON bytes, payload build count, and
captured write count. The same harness and seven samples run in isolated Python
3.11 virtual environments against:

- before: detached checkout of Stage base `50c81f3`;
- after: the completed Stage 4.5 branch.

The harness itself has three tests covering deterministic output/comparison,
zero real dispatch, and restoration of the legacy runtime logger, cache-path
environment, and PRNG state after the run. The runtime-state test captured
three literal REDs:
the first full-suite run exposed a leaked logger monkeypatch, and self-review
then exposed a leaked `BUBBLE_CLI_CACHE_PATH` and PRNG seed. All pass after the
context-manager fix.

Reproduction:

```text
rtk env PYTHONPATH=<baseline-checkout>/src <baseline-venv>/bin/python scripts/benchmark_style_lifecycle.py --samples 7 --output before.json
rtk env PYTHONPATH=src <current-venv>/bin/python scripts/benchmark_style_lifecycle.py --samples 7 --output after.json
rtk env PYTHONPATH=src <current-venv>/bin/python scripts/benchmark_style_lifecycle.py --compare-before before.json --compare-after after.json --output comparison.json
```

Seven-run medians:

| Workload | Before (s) | After (s) | Absolute delta (s) | Delta | Bytes before/after | Builds before/after | Writes before/after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 styles, cold | 0.000449959 | 0.002548833 | +0.002098874 | +466.459% | n/a | n/a | n/a |
| 500 styles, 200 warm lookups | 0.088234375 | 0.001281083 | -0.086953292 | -98.548% | n/a | n/a | n/a |
| 5,000 styles, cold | 0.004457417 | 0.034625292 | +0.030167875 | +676.802% | n/a | n/a | n/a |
| 5,000 styles, 200 warm lookups | 0.893181042 | 0.001340500 | -0.891840542 | -99.850% | n/a | n/a | n/a |
| 200 assignments | 0.000677792 | 0.000787292 | +0.000109500 | +16.155% | 140294/140294 | 1/1 | 0/0 |
| color/font CRUD | 0.001237500 | 0.002406583 | +0.001169083 | +94.471% | 2939/2899 | 6/6 | 6/6 |
| 25 fonts, 250 colors, 100 styles | 2.812254833 | 2.537125042 | -0.275129791 | -9.783% | 3605189/293916 | 475/202 | 475/202 |
| definition operations | 0.002079542 | 0.001826041 | -0.000253501 | -12.190% | 2623/2623 | 5/5 | 5/5 |

Resolution deliberately separates the one-time index build from repeated
lookups. Cold plus warm improves from 88.684 ms to 3.830 ms at 500 styles and
from 897.638 ms to 35.966 ms at 5,000 styles, about 96% end-to-end in both
cases. Assignment and CRUD percentage deltas represent only 0.110–1.169 ms of
local orchestration and are immaterial beside editor/network I/O. Import
improves 9.8% and reduces JSON bytes by 91.8% and build/write count by 57.5%.
No benchmark performed a remote Bubble write.

## Final local validation matrix

### Full suites and coverage

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest -q
1567 passed in 21.11s

rtk npm test
11 passed

rtk env PYTHONPATH=src ./.venv/bin/python -m coverage erase
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage run --branch -m pytest -q
1567 passed in 41.67s

rtk env PYTHONPATH=src ./.venv/bin/python -m coverage report
TOTAL: 65240 statements, 34962 missed, 30676 branches, 3613 partial, 43.7%
```

The coverage JSON gives the non-rounded combined result:

```text
covered_lines: 30278
num_statements: 65240
covered_branches: 11665
num_branches: 30676
percent_covered: 43.728887776804704
```

The ratchet moved from 40.5% to 43.6%, retaining 0.1288877768 percentage point
of measured headroom, more than the required 0.1 point.

Focused lifecycle coverage:

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m coverage report --include='src/bubble_mcp/aria_runtime/style_lifecycle/*.py' --fail-under=95
assignments.py 95.4%
colors.py 98.2%
definitions.py 95.2%
figma_import.py 98.7%
fonts.py 98.6%
references.py 96.2%
TOTAL 96.6%
```

### Packaging, audit, catalog, and no-profile smokes

```text
rtk env PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/test_package_smoke.py tests/unit/test_setup_smoke.py tests/unit/test_sensitive_audit.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_audit.py -q
16 passed in 3.40s

rtk env PYTHONPATH=src ./.venv/bin/python scripts/audit_sensitive_paths.py .
Sensitive public-source audit passed.

rtk env PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py
CLI commands 207; direct matches 205; aliases 1; excluded 1; missing 0; ok true

rtk env PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite coverage
2/2 passed

rtk env PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite agent-routing
9/9 passed

rtk env PYTHONPATH=src ./.venv/bin/python -m bubble_mcp.cli.main smoke runtime --suite visual-repair
1/1 passed
```

The server tool-list probe returned 327 tools.

### Authorized profile-dependent previews

The authorized installation at
`/Users/pedroduarte/Documents/Development/Custom/teste-mcp/befree-bubble-mcp`
was clean on `main...origin/main`. Its isolated virtual environment was updated
to an editable install of the closing worktree without changing that checkout.
Profile `smoke`, app `bovichain-g3`, context `index` was available. The cached
context was loadable, complete, and write-ready (43 pages, 440 reusables,
13,129 elements, 266 workflows), but its freshness preflight was stale. A
refresh was unnecessary for safe reads/previews and would have changed external
profile state.

```text
safe-read run 20260815191214_8a7854: 10 passed, 1 failed
preview-write run 20260815191229_379d89: 15 passed, 1 failed
family-preview run 20260815191229_78ad6a: 31 passed, 1 failed
```

All functional cases passed: 10/10 safe reads, 5/5 preview mutations, and 21/21
family previews. Every preview reported `executed=false`. Each suite's only
failure is the same `bubble_profile_status` preflight (`ok=true`, `ready=false`,
`next_action_count=1`) caused solely by context staleness. No real write or
cleanup was requested.

## Review outcome

Stages 4.5a–4.5e were independently reviewed against their immediate base.
Every Critical/Important finding was addressed with literal regressions before
the next stage; the SDD task reports preserve each RED/GREEN and follow-up
review result. The two deferred Minor findings were resolved above.

The final Stage 4.5f diff was self-reviewed and independently reviewed against
`e080e2e`. The independent pass found two Important gaps and no Critical gaps:

1. Ruff's glob semantics made the attempted root-only `aria_runtime/*.py`
   exclusion match the nested lifecycle package, leaving the gate vacuous. A
   literal regression invoking `ruff check --no-cache --show-files` failed with
   zero enumerated files before the configuration was replaced by exact legacy
   root-file exclusions; it now enumerates and checks all nine lifecycle files.
2. Assignment payload byte metrics used unseeded random intent IDs. The literal
   RED produced `[140288, 140272, 140281, 140289, 140289]` across five identical
   samples. Seeding that workload locally produces `[140294] * 5`; isolated
   before/after runs now both report exactly 140,294 bytes.

The follow-up review reran the real Ruff gate, lifecycle MyPy, diff hygiene,
assignment repeatability, and all four harness tests. All Critical/Important
findings are addressed with no new Critical/Important breakage.

## Known CI infrastructure state

Draft PRs #25–#30 remain stacked and open. Their current GitHub `test` checks
fail in two to four seconds with empty `steps` arrays, so no test step runs.
Live representative runs `31898623436` (PR #29) and `31902065247` (PR #30)
both report `jobs[0].steps: []`. This is the known billing/infrastructure
failure signature, not a code failure; workflows were not changed. The full
local matrix above is green.

## Consolidated final-review fix wave

This section supersedes the earlier closing verdict where the evidence differs.
The final review against `bddec9c` found four Important and two Minor issues.
All six were reproduced literally before implementation and fixed together on
`codex/style-token-lifecycle-4-5f-final-evidence` in
`99f3b87a65cb113a904f9bb76b0de14e849dc8b0`:

1. **Important — successful definition mutations left stale references.** A
   real-CLI rename RED still resolved `Article Copy` after the mocked successful
   dispatch mutated discovery to `Renamed Body`; a sequential set-default/clear
   RED deleted the newly configured default. Successful rename and set-default
   dispatches now invalidate the reference snapshot only after dispatch. Dry
   runs and failures retain the previous snapshot. Four focused regressions pass.
2. **Important — Figma import reused stale projected RGBA aliases.** Updating an
   existing custom color from red to blue while importing typography explicitly
   referencing red produced `var(--color_cExisting_default)` in RED. Variables
   are now recomputed from the post-update projected color defaults, so the
   typography preserves literal red RGBA. Five focused regressions pass.
3. **Important — bulk token cache persistence was O(N^2).** The literal REDs
   observed 500 saves for a 500-color reorder, 12 saves for a 12-color bulk
   delete, and four saves for a two-phase Figma import. The typed host protocol
   now exposes one atomic in-memory cache delta per successful token phase.
   Counts are 1, 1, and 2 respectively; ten focused regressions pass.
4. **Important — delete/reorder input schemas admitted runtime-invalid shapes.**
   Semantic tests against the actual MCP `tools/list` response showed that
   delete accepted no selector and reorder move/swap accepted missing operands.
   Conditional schemas now encode those runtime contracts while sort modes keep
   their operand-free form. The complete 24-test server slice passes and the
   catalog remains at 327 MCP tools.
5. **Minor — the finite deterministic-ID allocator could report false
   exhaustion.** With suffixes `b00ff` and `b0100` occupied, repeated digesting
   did not reach free suffix `b0101`. The allocator now hashes once, preserves
   attempt-zero compatibility, and linearly probes all 65,536 suffixes modulo
   the namespace before explicit exhaustion. Four allocator regressions pass.
6. **Minor — `filter` metadata was semantically vague.** The published schema
   now states that it is a case-insensitive substring filter over generated
   typography style names during Figma token import. The exact tools-list
   metadata regression passes.

The affected matrix passed 360 tests. Fresh closing gates produced:

```text
full Python: 1576 passed in 22.13s
full Node: 11 passed
coverage run: 1576 passed in 42.58s
global combined coverage: 43.75762123628177%
lifecycle combined branch coverage: 96.6%
package/setup/sensitive/catalog tests: 16 passed in 3.95s
catalog: 327 tools; 207 commands; 205 direct; 1 alias; 1 excluded; 0 missing
Ruff src/tests/scripts: passed
MyPy src: 141 files passed
```

Coverage contains 65,265 statements, 30,310 covered lines, 30,684 branches,
and 11,675 covered branches. The ratchet remains at 43.6%; 43.7% would retain
only 0.057621 point, below the prescribed 0.1-point headroom.

Seven-run sequential medians compare the isolated Stage base `50c81f3` with
the final worktree. Cache-save counts are observed calls to
`BubbleCLI._save_cli_cache`; no remote Bubble write was executed.

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

Warm resolution improves 98.6-99.9%. Positive deltas are 0.075-23.714 ms of
local orchestration; token import improves 33.5% while reducing both serialized
bytes and cache saves. The CRUD benchmark intentionally covers six independent
successful mutations, hence six after-stack saves; the new literal bulk tests
prove one save per reorder/delete phase.

Fresh no-profile smoke runs passed coverage 2/2 (`20260815203116_eceb9e`),
agent routing 9/9 (`20260815203116_d84944`), and visual repair 1/1
(`20260815203116_5b4ea6`). Authorized-profile safe reads, preview writes, and
family previews ran as `20260815203147_60fe1d`, `20260815203156_45ebd0`, and
`20260815203212_17479b`. Functional cases passed 10/10, 5/5, and 21/21; every
preview reported `executed=false`. Each suite's sole failure remained the same
stale-context profile-status preflight. No external write ran.

The inherited unbounded configuration loader in
`aria_runtime/figma_bridge/transform_tokens.py` is outside this lifecycle fix
wave and remains explicit follow-up debt. It does not weaken any of the six
closed review findings above.
