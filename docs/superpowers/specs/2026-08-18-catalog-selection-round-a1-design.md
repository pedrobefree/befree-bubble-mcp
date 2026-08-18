# Round A.1 Catalog Selection Design

## Goal

Establish a complete, deterministic selection baseline for the public MCP
catalog and the packaged legacy Bubble CLI before any catalog consolidation or
alias migration begins.

Round A.1 has two sequential stages:

1. complete deterministic coverage for every in-scope MCP tool and legacy CLI
   operation command;
2. a deeper natural-language ambiguity matrix for closely related tool
   families.

This specification starts with stage 1. Stage 2 remains part of Round A.1 but
must begin only after stage 1 is complete and reviewed.

## Scope

Stage 1 covers:

- all 327 public MCP tools exposed by the current catalog;
- all 207 operation commands exposed by the packaged legacy Bubble CLI;
- the 205 direct CLI-to-MCP mappings;
- the `create-reusable-type` to `create_reusable` canonical alias;
- the intentional CLI-only `reset-tmp` exclusion;
- deterministic tool and essential-argument selection evidence for every
  in-scope catalog entry;
- stable inventory serialization and coverage diagnostics;
- reuse of the inventory by the existing CLI/catalog parity audit.

Stage 1 does not cover:

- the modern nested `bubble-mcp` CLI leaf-command surface, which moves to Round
  A.2;
- alias consolidation, deprecation, ranking changes, or public renames;
- changes to tool schemas, dispatch behavior, preview defaults, confirmation
  gates, payload construction, or result contracts;
- LLM-backed, network-backed, authenticated, or live Bubble selection tests;
- the richer ambiguity matrix reserved for stage 2 of Round A.1.

## Architecture

### Shared command inventory

Add one typed inventory boundary that derives its data from the authoritative
MCP schema registry and packaged legacy CLI parser. It must not maintain a
second handwritten list of catalog or command names.

Each inventory record exposes only the metadata needed by parity and selection
coverage:

- MCP tool name;
- legacy CLI operation command, when applicable;
- relationship status: `direct`, `alias`, `excluded`, or `mcp_only`;
- canonical MCP tool name for aliases;
- deterministic selection case identifier or an explicit uncovered state;
- minimal selection metadata needed to construct or locate the case.

The inventory is sorted by stable keys before it is returned or serialized.
The same repository state must therefore produce byte-stable JSON regardless
of registry or parser iteration order.

The existing `scripts/audit_cli_catalog.py` must consume this inventory instead
of reimplementing the mapping rules. Catalog-quality checks and the audit must
continue to report the same current counts and zero missing legacy mappings.

### Deterministic selection corpus

Every MCP tool receives a deterministic selection case. A case contains:

- a stable case ID;
- a deterministic prompt or selector input;
- the expected MCP tool;
- the essential expected arguments, which may be empty when selection does not
  require arguments;
- the inventory source or family needed for diagnostics.

Cases may be derived from authoritative schema metadata when that produces an
unambiguous input. Exceptional cases may use explicit fixtures, but those
fixtures must be small, reviewable, and keyed by canonical tool name. The
implementation must fail closed when a tool has neither a derivable case nor
an explicit fixture.

The selection evaluation is local and deterministic. It must not use an LLM,
network access, a Bubble profile, catalog search ranking that depends on input
order, or application state. The same cases must be evaluated against at least
two catalog orderings, including the canonical order and a deterministic
reordering, and must produce identical selections and essential arguments.

This stage proves complete deterministic coverage. It does not claim that each
synthetic prompt represents realistic ambiguous human phrasing; that semantic
depth belongs to stage 2.

## Data Flow

1. Load the public MCP schemas from the authoritative catalog registry.
2. Discover packaged legacy CLI operation commands from the authoritative
   parser.
3. Apply the two explicit compatibility rules: the reusable-type alias and the
   local reset exclusion.
4. Produce the sorted shared inventory.
5. Resolve exactly one deterministic selection case for every MCP inventory
   record.
6. Run the selector against canonical and deterministically reordered catalog
   inputs.
7. Compare the selected tool and essential arguments with the case
   expectations.
8. Emit per-case and aggregate coverage diagnostics.

## Failure Contracts

The tests and audit must distinguish these failures:

- an MCP tool absent from the inventory;
- an operation command without a direct, alias, or excluded relationship;
- an unexpected exclusion or alias;
- a catalog tool without a deterministic selection case;
- selection of the wrong tool;
- mismatch in essential arguments;
- output that changes when catalog order changes;
- unstable inventory ordering or serialization;
- drift between the inventory, audit, and catalog-quality reports.

Diagnostics must name the affected MCP tool, legacy command when present, case
ID, expected selection, and actual selection. Aggregate counts alone are not
sufficient evidence.

## Compatibility Constraints

- Preserve all public MCP names and schemas.
- Preserve legacy CLI commands and parser behavior.
- Preserve `create-reusable-type` as an alias of `create_reusable`.
- Preserve `reset-tmp` as intentional CLI-only local housekeeping.
- Preserve preview-by-default and confirmation behavior for mutations.
- Preserve catalog dispatch and result shapes.
- Do not add the modern nested CLI to the inventory during Round A.1.

## Test Strategy

Implementation follows RED/GREEN:

1. Add failing tests for full MCP and legacy CLI inventory coverage, the
   explicit alias and exclusion, stable ordering, and stable serialization.
2. Add failing selection tests that require one case per MCP tool and verify
   the expected tool and essential arguments.
3. Add a deterministic reorder regression proving selection is independent of
   catalog enumeration order.
4. Implement the smallest shared inventory and selection-case boundary needed
   to make those tests pass.
5. Refactor the existing parity audit to use the shared inventory.

Focused completion gates are:

- the new inventory and deterministic selection tests;
- `tests/unit/test_eval_runner.py`;
- catalog audit and catalog-quality tests;
- `PYTHONPATH=src ./.venv/bin/python scripts/audit_cli_catalog.py`;
- Ruff on changed Python files;
- MyPy on changed production modules;
- `git diff --check`.

The broader suite is required if the implementation touches shared catalog,
parser, or harness behavior beyond the new read-only inventory boundary.

## Delivery

Work proceeds in the isolated worktree
`.worktrees/catalog-selection-round-a1` on branch
`codex/catalog-selection-round-a1`.

Stage 1 is complete when every in-scope MCP tool has deterministic selection
evidence, every legacy CLI operation command has an explicit mapping status,
the audit consumes the shared inventory, all required gates pass, and an
independent review finds no unresolved load-bearing issue.

After stage 1 is finalized, Round A.1 continues with a separately planned
ambiguity-matrix stage. Round A.2 owns the modern nested CLI leaf-command map.
