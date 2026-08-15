# Visual Mutation Boundary Design

**Date:** 2026-08-14
**Status:** Approved

## Context

Stage 4.1 extracted durable cache persistence, Stage 4.2 extracted alias
lifecycle, and Stage 4.3 extracted discovery-backed context/reference
resolution. Visual element mutation orchestration remains spread across roughly
24,000 lines and 85 candidate methods in `BubbleCLI`. The create, update, and
delete families repeat target discovery, canonical-path selection, payload
dispatch, preview handling, discovery overlay updates, and alias maintenance.

Moving the entire family in one change would obscure contract regressions.
Family 2 will therefore be delivered through three stacked, independently
testable PRs while exposing one composed internal boundary.

## Goals

- Introduce a typed internal boundary for visual element create, update, and
  delete orchestration.
- Consume `ContextReferenceResolver` behavior for deterministic context,
  parent, and existing-element selection.
- Preserve every public `BubbleCLI` signature as a compatibility facade.
- Preserve CLI and MCP tool names, schemas, aliases, annotations, previews,
  confirmation gates, dispatch routes, payload order, logs, return values, and
  discovery/cache side effects.
- Remove duplicated orchestration from `BubbleCLI` without moving style,
  color, font, data-source, workflow, or HTML-import domain behavior into the
  new boundary.
- Cover each extracted component at no less than 95% combined branch coverage
  and raise the global ratchet only with at least 0.1 percentage point of
  measured headroom.

## Non-goals

- Renaming, consolidating, adding, or removing public MCP tools.
- Replacing legacy Bubble payloads with the standalone compiler payloads.
- Changing `execute=false`/`dry_run=true` defaults or destructive annotations.
- Extracting style/color/token logic (Family 3), data/schema logic (Family 4),
  workflows/authentication (Family 5), or Figma/batch/asset bridges (Family 6).
- Moving `create_from_html`, page/reusable creation, or reusable deletion into
  the visual mutation boundary.

## Chosen Architecture

Create `bubble_mcp.aria_runtime.visual_mutations` as a composed package:

- `protocols.py` defines the narrow typed host surface and immutable target
  records. The host exposes existing resolution, payload, discovery, and cache
  operations but does not transfer persistence ownership.
- `targets.py` owns shared context/parent/existing-element resolution and
  canonical element paths. It delegates semantic discovery to the Stage 4.3
  resolver-compatible host methods and hydrates incomplete cached rows before
  mutation.
- `deletions.py` owns type validation, `RemoveElement` payload construction,
  `id_to_path` removal, `issues_sub` maintenance, preview/dispatch behavior,
  discovery alias cleanup, and the generic delete implementation.
- `creations.py` owns context/parent preparation plus common creation
  finalization: preview logging, dispatch, discovery injection, and created
  alias materialization. Element-specific builders and property normalization
  remain in the existing public methods for this stage.
- `updates.py` owns existing-element resolution and common SetData/AssignStyle
  execution. Element-specific property collection remains in public methods;
  style-property semantics continue to be supplied by the host because they
  belong to Family 3.
- `service.py` composes the target, delete, create, and update components.
  `BubbleCLI` constructs one service and retains thin compatibility facades.

This structure avoids a second monolith: each operation can evolve and be
covered independently while callers see one stable family boundary.

## Typed Data Flow

### Existing-element mutations

1. A public `BubbleCLI.update_*` or `delete_*` method receives unchanged
   arguments.
2. The method validates element-specific fields, then delegates orchestration
   to `VisualMutationService`.
3. `VisualMutationTargets` resolves the context and element using exact name,
   label, reference lookup, and alias-cache precedence already established by
   Stage 4.3.
4. The target is hydrated from discovery when cached metadata lacks `%p`.
5. The canonical write path prefers `_index.id_to_path` and falls back to the
   normalized discovery path.
6. The operation-specific service builds the same ordered changes as the
   current implementation.
7. Preview returns without network dispatch. Execute dispatches once and
   applies the same discovery/cache side effects only after success.

### Create mutations

1. The public create method delegates context/parent preparation.
2. The existing element-specific builder produces the unchanged body and
   ordered payload changes.
3. The creation service previews or dispatches the payload, injects the same
   overlay element, and caches the same aliases and canonical path.
4. Return values remain the generated element ID/key or `False`, exactly as
   before extraction.

## Error and Safety Contracts

- Missing or ambiguous targets return `False` with the existing diagnostics.
- Type-specific delete facades reject mismatched hydrated element types; an
  absent type remains compatible with legacy permissive behavior.
- Preview must never call the outbound dispatcher.
- Failed dispatch must not remove aliases or claim success.
- Successful delete removes aliases only after dispatch and updates all known
  parent `issues_sub` rows without mutating unrelated parents.
- Successful or preview creation preserves the legacy local discovery
  injection behavior of each tool.
- Unknown update fields and no-op update payloads retain their current return
  and warning behavior.
- Public MCP delete tools remain destructive and require the existing explicit
  execution gate; this refactor does not weaken annotations or confirmation.

## Delivery Stack

### Stage 4.4a — visual deletions

Branch `codex/visual-mutations-4-4a-delete`, based on `main`. Extract shared
targets needed by deletion and all concrete visual `delete_*` methods while
excluding page, reusable, style, color, font, data, workflow, and API deletion.
Open PR A against `main` as draft.

### Stage 4.4b — visual creations

Branch `codex/visual-mutations-4-4b-create`, based on Stage 4.4a. Extract
creation preparation/finalization for all catalog visual creation methods while
excluding HTML import, page/reusable creation, and style creation. Open PR B
against the Stage 4.4a branch as draft.

### Stage 4.4c — visual updates

Branch `codex/visual-mutations-4-4c-update`, based on Stage 4.4b. Extract shared
update resolution/execution and delegate all visual update families without
absorbing style/token internals. Update the roadmap, global coverage, and
benchmarks. Open PR C against the Stage 4.4b branch as draft.

After all three branches pass full validation and one final independent review,
mark the stack ready. Merge order is A, then B, then C.

## Testing Strategy

- Characterization tests use literal payloads captured from current behavior
  before delegation.
- Component tests exercise real services and in-memory hosts; only outbound
  network dispatch is replaced.
- Real-`BubbleCLI` facade tests prove public signatures, return values, ordered
  payload changes, dry-run isolation, and post-success cache/discovery effects.
- Deletion matrices cover every allowed element type, unknown type, mismatched
  type, root/nested parent cleanup, malformed indices, dispatch failure, and
  alias cleanup ordering.
- Creation matrices cover root/nested parents, readable/raw aliases, preview,
  dispatch failure, discovery injection, created aliases, and returned IDs.
- Update matrices cover name/label/reference/cache resolution, hydration,
  canonical paths, no-op updates, style assignment ordering, preview, and
  dispatch failure.
- Each stacked PR runs focused compatibility suites, Ruff, MyPy, catalog
  quality, CLI/catalog parity, runtime preview smokes, and `git diff --check`.
- The final branch additionally runs all Python and Node tests, package/setup
  smokes, sensitive-path audit, sharded global coverage, and benchmarks.

## Acceptance Criteria

- All visual create/update/delete public methods retain their signatures and
  observable behavior.
- The new package contains no Bubble HTTP/session implementation and owns no
  cache-file persistence.
- `BubbleCLI` contains construction/facade or element-specific property logic,
  not duplicated generic mutation orchestration.
- No MCP catalog/schema/annotation/dispatch diff is introduced.
- All three PRs are pushed, documented, and ready for review only after the
  complete Family 2 stack is validated.
