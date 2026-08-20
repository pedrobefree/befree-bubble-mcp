# Catalog Precision Round A.3: Data Schema Design

## Context

Round A.1 closed deterministic MCP and legacy-CLI selection coverage. Round A.2
then classified every modern nested CLI leaf against its handler and MCP
relationship. The next catalog stage is a targeted schema-precision pass before
any public-tool consolidation.

The first A.3 target is the `data_schema` family because its schemas guide
structural and destructive Bubble changes. A read-only comparison of the
published MCP schemas, `aria_dispatch._method_kwargs`, and the public
`BubbleCLI` signatures found concrete drift:

- `create_data_type` publishes `fields` and `exposed_api`, which its runtime
  handler does not consume, while omitting the supported `key` and `private`;
- `create_data_field` publishes `is_list` and `optional`, which are discarded,
  while omitting the supported `field_key`;
- `create_option_set` publishes `values` and `attributes`, although creation is
  intentionally a single option-set write;
- `set_data_type_api_exposure` does not require the runtime-required boolean
  operation value;
- several reference-kind and formatting fields are advertised on handlers that
  always resolve automatically or never receive those values; and
- current tests cover selected privacy and permanent-delete schemas, but no
  family-wide check prevents a new published argument from being silently
  dropped before the runtime call.

The clean base at merge commit `d4bb0f0` passes 1,909 Python tests and 11 Node
tests. These results establish the pre-change baseline, not A.3 closing
evidence.

## Goals

1. Make every public operational argument in the targeted family reach a
   documented runtime parameter or an explicit compatibility alias.
2. Make every required runtime parameter reachable through the public schema.
3. Encode the real types, enums, defaults, and conditional requirements agents
   need before dispatch.
4. Preserve established preview, confirmation, payload, dispatch, and result
   behavior for valid calls.
5. Add a deterministic, checkout-runnable audit that fails closed when these
   contracts drift.

## Non-goals

- Renaming, consolidating, deprecating, or removing MCP tools.
- Adding multi-write convenience behavior such as creating a data type together
  with fields or API exposure, or creating an option set together with values
  and attributes.
- Changing Bubble write payloads for already valid operations.
- Weakening current-first reference resolution, soft-delete prerequisites, or
  destructive confirmation gates.
- Expanding A.3 to workflows, visual elements, styles, settings, redirects, or
  unrelated catalog families.
- Using an LLM, network access, a Bubble profile, or authenticated editor state
  in the deterministic audit.

## Target Surface

The stage owns 28 public tools in four bounded groups:

- type and field discovery/lifecycle: `scan_types`, `list_data_types`,
  `create_data_type`, `rename_data_type`, `delete_data_type`,
  `delete_data_type_permanently`, `create_data_field`, `rename_data_field`,
  `delete_data_field`, and `set_data_type_api_exposure`;
- privacy lifecycle: `list_privacy_rules`, `create_privacy_rule`,
  `delete_privacy_rule`, `set_privacy_rule_name`,
  `set_privacy_rule_condition`, `set_privacy_rule_permission`,
  `set_privacy_rule_field_visibility`, and
  `set_privacy_rule_auto_binding`;
- option-set lifecycle: `create_option_set`, `rename_option_set`,
  `delete_option_set`, and `create_option_attribute`;
- option-value lifecycle: `create_option_value`, `delete_option_value`,
  `list_option_values`, `rename_option_value`,
  `set_option_value_attribute`, and `reorder_option_values`.

The list is explicit. Prefix discovery alone must not silently add a future tool
to this round.

## Recommended Design

### Explicit precision inventory

Add a small catalog-precision module containing one immutable record per target
tool. Each record names its runtime handler and classifies schema properties as
one of:

- **runtime**: maps directly to a public handler parameter;
- **alias**: maps deterministically to a named runtime parameter;
- **control**: is consumed by the MCP execution boundary rather than
  `BubbleCLI`, such as `profile`, `app_id`, `app_version`, `context_file`,
  `execute`, `dry_run`, `confirm`, `write_payload`, or `payload`.

Alias records must name their target parameter. Control records must come from
an explicit allowlist rather than being ignored generically. The inventory is
the reviewable policy boundary; runtime signatures and public schemas remain
the authoritative facts checked against it.

### Deterministic audit

Expose a checkout-runnable `scripts/audit_catalog_schema_precision.py`. The
audit loads the authoritative tool schemas, the explicit 28-tool inventory,
the runtime alias tables, and `inspect.signature` output for the corresponding
`BubbleCLI` methods. It fails when:

- a target tool or handler is missing;
- the explicit target set changes unexpectedly;
- a public operational property has no runtime, alias, or control consumer;
- an alias points to a missing runtime parameter;
- a required runtime parameter has no public schema path;
- schema requiredness disagrees with the canonical contract;
- a precision-critical type, enum, default, or conditional rule drifts; or
- a report is non-OK without actionable per-tool failures.

Output is deterministic and sorted by tool and field. It reports counts for
tools, runtime properties, aliases, controls, required parameters, and failures.
It performs no Bubble reads or writes.

### Schema corrections

Correct the family schemas to describe only supported capabilities:

- expose `key` and `private` for `create_data_type`; remove the unsupported
  `fields`, `exposed_api`, and non-destructive `confirm` properties;
- expose `field_key` for `create_data_field`; represent list fields through the
  runtime-supported `list.<type>` value and remove the ignored `is_list` and
  `optional` properties;
- preserve `name` as the public field-reference compatibility spelling for
  rename/delete through its existing deterministic `field_key` mapping;
- make `enabled` the canonical required boolean for
  `set_data_type_api_exposure`; keep the existing `value` input as an explicitly
  classified compatibility alias at dispatch rather than a second semantic
  field;
- expose `key` for `create_option_set` and remove unsupported inline `values`
  and `attributes`; callers use the existing focused attribute/value tools;
- retain `confirm` only on destructive tools and only as an MCP control field;
- remove reference-kind fields from operations whose runtime always performs
  current-first automatic resolution, while retaining and correcting them on
  option-value operations that genuinely accept a mode;
- align option-value reference modes with the resolver's accepted canonical
  spellings and compatibility spellings;
- require at least one actual update for privacy field-visibility changes; and
- apply minimum lengths, non-empty arrays, boolean types, integer constraints,
  and defaults only where the runtime has the same contract.

Descriptions must identify exact-key requirements, current-first lookup,
preview defaults, recoverable deletion, permanent-deletion prerequisites, and
the focused follow-up tools for fields, exposure, option attributes, and option
values. `set_data_type_api_exposure` must join the existing `data_schema`
documentation-enrichment family.

### Compatibility and failure behavior

Existing valid calls continue through the same handlers. Public compatibility
spellings already normalized by `ARG_ALIASES`, `OPERATION_ARG_ALIASES`, or the
field-reference special case remain functional and are recorded in the
inventory.

Previously published inputs that had no consumer are removed from discovery;
they do not gain speculative behavior. For targeted tools, the boundary must
reject an unknown operational argument with a field-specific error instead of
silently discarding it. MCP control fields remain accepted according to their
existing execution semantics. Preview stays the default, and executing a
destructive operation still requires `confirm=true`.

## Data Flow

1. The MCP catalog builds and enriches the public schema.
2. The precision audit joins the schema to the explicit target record.
3. The record resolves each public property to a runtime parameter, a named
   compatibility alias, or an MCP control consumer.
4. On a real call, the existing server safety gates process execution and
   confirmation controls.
5. `_method_kwargs` maps canonical properties and aliases to the unchanged
   `BubbleCLI` facade.
6. The existing schema-lifecycle service resolves current references, builds a
   preview or write payload, and returns through the existing response shape.

No new execution path or payload builder is introduced.

## Testing Strategy

### Focused tests

- Inventory completeness, duplicate detection, stable ordering, and diagnostic
  conversion.
- One schema-to-signature contract case for each of the 28 tools.
- Direct, alias, and control-property classification.
- Detection of unknown published properties, missing required runtime
  parameters, stale aliases, schema type/enum drift, and unexpected target-set
  changes.
- Literal regressions for `create_data_type`, `create_data_field`,
  `set_data_type_api_exposure`, option-set creation, option-value reference
  modes, privacy conditional updates, and destructive confirmation.
- Representative schema-to-dispatch dry runs proving unchanged payloads for
  valid data type, field, privacy, option-set, and option-value operations.
- Rejection of formerly silent unsupported operational arguments.

### Repository gates

- focused unit tests for the inventory, catalog, dispatch, and schema lifecycle;
- `PYTHONPATH=src:. pytest -q`;
- `npm test`;
- Ruff and MyPy;
- catalog quality, A.1 selection, A.1 ambiguity, legacy CLI parity, and A.2
  modern CLI leaf-map audits;
- the new A.3 precision audit;
- sensitive-path and diff-hygiene checks;
- Python 3.11 clean-wheel package smoke, including the new audit; and
- profile-independent runtime coverage and agent-routing smokes.

Authenticated Bubble execution is not required because this round changes
catalog and argument-boundary contracts, not editor payload semantics.

## Release Integration

The new audit runs as a separate release/package-smoke gate, matching the A.2
leaf-map precedent and preserving the successful `bubble_catalog_quality`
response shape. Documentation records the command, exact target count, removed
dead fields, retained compatibility aliases, and fresh validation evidence.

## Acceptance Criteria

Round A.3 data-schema precision closes when:

1. all 28 target tools pass the deterministic precision audit;
2. zero published operational properties are silently discarded;
3. every required runtime parameter has a canonical public schema path;
4. the documented schema corrections and conditional contracts are covered by
   literal tests;
5. valid preview, confirmation, dispatch, payload, and response contracts remain
   unchanged;
6. all repository, audit, wheel, and profile-independent smoke gates pass; and
7. independent review finds no unresolved load-bearing issue.

Broad catalog consolidation remains deferred until this evidence shows that a
specific tool family benefits from consolidation rather than merely sharing
similar names.
