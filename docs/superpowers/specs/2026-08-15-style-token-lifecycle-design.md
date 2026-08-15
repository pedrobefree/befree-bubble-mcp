# Stage 4.5 Style and Token Lifecycle Design

## Context

Stage 4.4 moved visual create, update, and delete orchestration out of
`BubbleCLI`, but the visual boundary still calls style helpers owned by the
legacy class. Style lookup, assignment, definition mutation, color/font token
mutation, and Figma token import remain interleaved across roughly 3,000 lines
of `bubble_cli.py`. The live baseline is 1,317 Python tests, 11 Node tests,
40.6% combined line/branch coverage, 327 MCP tools, and 207 CLI operation
commands with zero missing catalog mappings.

The extraction must preserve public tool names, callable signatures, aliases,
annotations, previews, confirmation behavior, intent ordering, dispatch routes,
cache semantics, and result shapes unless this design explicitly identifies a
broken contract and adds a regression for the correction.

## Goals

- Move style resolution, assignment policy, design-token lifecycle, Figma token
  planning, and style-definition lifecycle behind typed internal boundaries.
- Keep every existing `BubbleCLI` method as a compatibility facade.
- Give new components at least 95% combined branch coverage.
- Replace repeated linear scans and O(N²) token-map writes with normalized
  indexes and grouped payloads without introducing material benchmark regressions.
- Correct catalog schemas that cannot currently express required runtime
  arguments, while retaining every existing alias.
- Preserve the Family 2 callback surface until the new boundaries are stable.

## Non-goals

- Renaming or consolidating CRUD tools solely because their names are similar.
- Extracting the complete Figma bridge, batch bridge, or natural-language layer;
  those remain Family 6 work.
- Changing Bubble wire formats or introducing a new persistence format.
- Replacing SDK `StyleBuilder`, `ColorBuilder`, `FontBuilder`, or
  `PayloadBuilder` wire-format ownership.
- Removing legacy aliases in this release.

## Alternatives considered

### One large `StyleService`

This minimizes constructors but creates another broad object spanning reads,
payload policy, dispatch, cache mutation, and import orchestration. It would be
difficult to review and would reproduce the coupling being removed.

### Independent services wired directly into `BubbleCLI`

This creates clean components, but allows Figma import and visual mutations to
reach arbitrary host methods and encourages circular dependencies between style
resolution and color resolution.

### Composed lifecycle with narrow protocols — selected

Use small services with explicit protocols and one composition root. Reads,
assignment policy, token mutation, import planning, and definition mutation are
separate review units. `BubbleCLI` remains the compatibility facade and supplies
only the callbacks each component needs.

## Package architecture

```text
src/bubble_mcp/aria_runtime/style_lifecycle/
  __init__.py
  protocols.py
  references.py
  assignments.py
  colors.py
  fonts.py
  figma_import.py
  definitions.py
  service.py
```

`StyleLifecycleService` is constructed once by `BubbleCLI` and exposes:

```python
class StyleLifecycleService:
    references: StyleReferenceResolver
    assignments: StyleAssignmentService
    colors: ColorTokenService
    fonts: FontTokenService
    figma_import: FigmaTokenImportService
    definitions: StyleDefinitionService
```

Protocols are split by responsibility. Components may consume SDK builders and
immutable snapshots, but only operation services may dispatch or update cache.
Dry-run planning must not dispatch or mutate cache.

## Phase 4.5a — style references

`StyleReferenceResolver` owns element-type normalization, default-style lookup,
known-style indexes, exact/compact/tokenized name lookup, explicit ID handling,
semantic Button fallback, style-to-element-type inference, and base property
reads. Discovery is authoritative; valid cache-only entries supplement it.

The resolver maintains a normalized index keyed by the identity of the current
discovery/cache snapshots. Refresh or mutation invalidates the index. Strict
resolution rejects unknown IDs; permissive resolution retains the current
pass-through behavior.

`find_style_id`, `find_style_id_by_name`, `_resolve_style_reference`,
`_infer_element_type_from_style_id`, and the normalization/default helpers stay
on `BubbleCLI` as literal facades.

## Phase 4.5b — assignment and override policy

`StyleOverridePolicy` owns the per-element override key sets, marker keys,
protected structural properties, alias equivalence, and redundant-property
pruning. Group, Table, RepeatingGroup, Popup, and DateInput special cases become
named policies rather than duplicated inline heuristics.

`StyleAssignmentService` owns `AssignStyle`, marker clearing, style removal,
optional `%p` `SetData`, and explicit property ordering. The required order is:

1. clear old override properties;
2. clear style marker properties;
3. assign `%s1` and `%p` using the same intent ID where the current contract does;
4. apply explicit properties.

The Family 2 host continues to call the existing `BubbleCLI` methods, which
delegate to this service. `update_style` and `update_style_all` must not emit a
write when resolution fails. The MCP schema for `update_style_all` gains the
existing optional `by_contains` runtime argument.

## Phase 4.5c — color and font lifecycle

`ColorTokenService` and `FontTokenService` normalize raw/readable discovery and
cache snapshots, then own list, resolve, create, update, delete, bulk delete,
clear, and reorder behavior. Discovery wins ID collisions; non-stale cache-only
entries remain visible. Soft-deleted entries cannot block recreation. Reorders
preserve tombstones.

Create operations return the actual token ID internally. The public
`BubbleCLI.create_color` and `create_font` facades keep their boolean result
contract. Cache updates occur only after successful dispatch and apply equally
to discovery-backed and cache-only entries.

Custom color references use one canonical form:
`var(--color_<id>_default)`. Literal RGBA/hex resolution and default/custom name
precedence are shared by element and style consumers.

Catalog schemas are corrected to expose the real signatures of color/font CRUD,
bulk delete, reorder, and list filtering. Destructive execution enforces the
existing `confirm` contract while dry-run remains available without dispatch.

## Phase 4.5d — Figma token import

`FigmaTokenImportService` validates a bounded JSON document and builds a
deterministic `FigmaTokenPlan`. It consumes color/font services and a narrow
`StyleDefinitionSink`; it does not depend on all of `BubbleCLI`.

The plan applies fonts, colors, then typography styles. Custom font and color
maps are emitted at most once each; default color changes remain individually
ordered. Dry-run returns the complete planned payloads with no side effects.
The import never treats a boolean facade result as a color ID, preventing
`var(--color_True_default)` references.

`sync_figma_tokens` keeps its public name and legacy `list_options` mode. A new
read-only `list_figma_token_options` capability is canonical for discovery;
`list_options=true` remains a compatibility alias path. The mutation schema
exposes `tokens_path`, `config_path`, `types`, `color_bases`, `all_tokens`, and
`filter`. Import resolution never mutates `sys.path` from the process CWD.

## Phase 4.5e — style definitions and states

`StyleDefinitionService` owns create, update, rename, delete, bulk delete,
clear, defaults, conditional states, transition intents, and state ordering.
It consumes `StyleReferenceResolver`, `ColorTokenService`, and SDK
`StyleBuilder`. It performs dispatch and cache mutation through a narrow host.

The service retains current preview payloads and cache behavior, but cache
updates happen only after successful dispatch. Existing public methods remain
facades. HTML import and the Figma adapter call the same facades/sink and retain
their result shapes.

## Phase 4.5f — final evidence

The final branch contains no new lifecycle behavior. It closes coverage gaps,
runs before/after benchmarks, raises the global ratchet only with at least 0.1
percentage point of measured headroom, updates the optimization roadmap, and
records the independent review result.

## Tool-contract policy

One tool continues to represent one capability. CRUD tools are not consolidated.
When a canonical capability is added, old names or modes remain aliases to the
same handler and receive canonical-schema parity tests. Every changed tool gets
a literal schema-to-dispatch-to-runtime-signature test.

Known schema corrections in this stage:

- `create_color` and `update_color`: required `profile`, `name`, `rgba`;
- `create_font` and `update_font`: required `profile`, `name`, `font_family`;
- `delete_color` and `delete_font`: required `profile`, `name`;
- `delete_colors`: `names` or `pattern`;
- `reorder_colors`: `mode` plus conditional `color_name`/`target`;
- `list_colors` and `list_fonts`: their real filter flags;
- `sync_figma_tokens`: the real import fields;
- `update_style_all`: optional `by_contains`.

## Error and side-effect contracts

- Preview never dispatches or mutates cache.
- Dispatch failure never mutates cache or logs success.
- Malformed, oversized, or excessively deep token JSON fails before planning.
- Invalid regex and unsupported reorder modes fail without partial writes.
- Destructive execution requires explicit confirmation at the MCP boundary.
- Bulk writes preserve existing tombstones and unrelated entries.
- Result shapes and boolean facade contracts remain stable.

## Validation and exit criteria

Each functional phase requires focused behavior tests, real-`BubbleCLI` facade
tests, prior-phase tests, Ruff, MyPy, `git diff --check`, catalog quality, CLI
parity, and the relevant runtime smokes. Each new component must reach at least
95% combined branch coverage.

The final stack requires:

- complete Python and Node suites;
- package/setup smokes and sensitive-path audit;
- catalog quality and CLI parity with zero missing mappings;
- coverage, agent-routing, visual-repair, preview-write, family-preview, and
  safe-read runtime smokes where the local profile is available;
- benchmark medians over seven runs for cold/warm style resolution, assignment,
  token CRUD, grouped import, and style definitions;
- no material regression above 5%, interpreted together with absolute cost;
- independent review of every PR and literal RED/GREEN regressions for all
  Critical or Important findings.

