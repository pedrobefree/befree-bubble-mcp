# Path Discovery Alias Contracts Design

Date: 2026-08-12
Status: Approved design
Scope: PR #17 in the Befree Bubble MCP standalone package

## Problem

`PathDiscovery` accepts both readable and Bubble wire keys, but several methods select aliases with
truthiness expressions such as `elements or %el`. That handles artifacts containing only one shape,
but it loses data when both aliases coexist and are not the same object. Workflow injection can also
create a second bucket that the subsequent lookup path does not inspect. Empty dictionaries in one
alias can mask populated data in the other.

The current tests maximize executed lines but mostly exercise isolated standard or raw fixtures. One
test explicitly treats failed raw context-name lookup as expected behavior, leaving the public
boundary inconsistent.

## Goals

- Give readable and wire aliases one deterministic resolution policy.
- Preserve entries from both aliases when they coexist.
- Synchronize mutable alias buckets before injecting elements or workflows.
- Prefer populated property data over an empty alias without merging property values implicitly.
- Make page and reusable name lookup search both top-level containers.
- Prove injected workflows survive disk-cache readback.
- Preserve path output in canonical Bubble wire tokens.

## Non-Goals

- Do not redesign the context-composition pipeline.
- Do not rewrite the legacy `bubble_sdk.py` module or change public method signatures.
- Do not change source priority between `.bubble`, console, crawler, and mutation overlay.
- Do not merge conflicting property keys across two non-empty property dictionaries.

## Considered Approaches

### 1. Patch each call site independently

Add local conditionals to `list_elements`, workflow lookup, workflow injection, and property access.
This is small but keeps the selection rules duplicated and likely to drift again. Rejected.

### 2. Normalize the entire loaded document eagerly

Rewrite every readable and wire alias after loading a discovery artifact. This provides a canonical
shape but mutates a broad legacy document and risks changing unrelated consumers. Rejected for this
round.

### 3. Focused alias helpers at the discovery boundary

Add small helpers that resolve mappings for reads and synchronize mapping aliases for writes. Update
only the affected `PathDiscovery` methods and cover all shape combinations. Selected.

## Design

### Read resolution

A helper accepts an object and an ordered pair of alias keys. It returns:

1. An empty mapping when neither alias is a dictionary.
2. The available mapping when only one alias is a dictionary.
3. The shared mapping directly when both aliases reference the same object.
4. A deterministic shallow union when both mappings are distinct, preserving entries from the
   preferred readable alias on key conflicts and adding non-conflicting wire entries.

Recursive element and workflow reads use this helper, so mixed containers remain visible without
mutating source data.

Property access uses a narrower rule: return the preferred mapping when it is non-empty, otherwise
fall back to the alternate mapping. Two non-empty property maps are not merged because field-level
precedence is outside this PR.

### Write synchronization

A write helper resolves the two alias buckets and installs one shared dictionary under both keys.
When existing dictionaries are distinct, it combines them using the same deterministic precedence
before assigning the shared result. Workflow and element injection then mutate this shared bucket
and persist the cache once.

The presence of `%x` alone does not choose a write bucket. Existing valid mappings and explicit alias
keys determine the resolved content; both names are synchronized afterward.

### Context-name lookup

`find_page` and `find_reusable` iterate the readable and wire top-level containers in precedence
order, de-duplicating shared containers and IDs. A readable entry wins only when both containers
contain the same ID. A context present solely in the wire bucket remains discoverable.

## Error Handling

- Non-dictionary aliases are treated as absent and repaired only on write.
- A missing context keeps the existing no-op behavior for injection and empty-result behavior for
  reads.
- Cache persistence failures retain the existing boolean/logging semantics and do not roll back the
  in-memory update.

## Testing

- Table-driven standard-only, raw-only, shared-alias, and divergent-alias element listings.
- Nested divergent element aliases preserve both subtrees.
- Page and reusable name lookup finds raw-only entries alongside populated readable containers.
- Workflow injection into a hybrid root is immediately discoverable.
- Workflow event properties fall back from empty `%p` to populated `properties`.
- Element properties fall back from empty `properties` to populated `%p`.
- Real disk-cache round trip: inject, construct a fresh `PathDiscovery`, and find the workflow.
- Existing standard/raw path expectations remain unchanged.

## Validation

- Focused PathDiscovery and runtime-discovery tests.
- Full Python test suite and coverage ratchet.
- Ruff for changed tests, `git diff --check`, runtime coverage smoke, and agent-routing smoke.
- Direct production-file lint findings are reported separately because `aria_runtime` is excluded by
  the repository Ruff and MyPy configuration.
