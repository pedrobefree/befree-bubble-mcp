# Framework Adapters

Framework adapters connect real Bubble MCP context to external development
methods without making those methods hard dependencies of the MCP core.

The v1 adapters generate local artifacts and synchronize evidence for:

- `bmad`: project brief, PRD, architecture, epics, stories, and validation evidence.
- `superpowers`: spec, implementation plan, execution gates, and verification checklist.
- `sdd`: behavioral specification, fixtures, acceptance tests, and traceability.

These adapters do not execute Bubble writes. Implementation still goes through
normal Bubble MCP tools or executable skills with preview-first validation and
explicit approval for mutations.

## MCP Flow

List available adapters:

```json
{
  "tool": "bubble_framework_list",
  "arguments": {}
}
```

Generate artifacts:

```json
{
  "tool": "bubble_framework_generate_artifacts",
  "arguments": {
    "framework": "bmad",
    "profile": "cliente2",
    "objective": "Plan the checkout flow",
    "scope": "checkout page",
    "context_summary": {
      "pages": 5,
      "workflows": 12,
      "data_types": 7
    }
  }
}
```

Append evidence after a preview, execution, context refresh, or validation:

```json
{
  "tool": "bubble_framework_sync_evidence",
  "arguments": {
    "framework": "bmad",
    "profile": "cliente2",
    "artifact_dir": "/Users/me/.config/bubble-mcp/frameworks/bmad/cliente2/20260707-120000-checkout",
    "evidence": {
      "summary": "Preview passed and context refresh confirmed the target page.",
      "run_id": "skillrun_20260707_123456"
    }
  }
}
```

Inspect generated artifacts:

```json
{
  "tool": "bubble_framework_status",
  "arguments": {
    "framework": "bmad",
    "profile": "cliente2"
  }
}
```

## V2 Program Runtime

The V2 runtime lets BMAD, Superpowers, SDD, and other framework adapters treat
Bubble MCP as a dynamic implementation language without loading the full tool
catalog for every step.

The runtime flow is:

1. `bubble_framework_plan_from_text` converts framework text artifacts such as
   stories, PRDs, specs, and acceptance notes into a structured framework
   program when the framework does not already provide one.
2. `bubble_framework_compile_program` validates program syntax, resolves intent
   aliases, applies step dependencies and placeholders, injects the active
   profile where supported, adds preview flags, and runs deterministic quality
   gates before any execution.
3. `bubble_framework_execute_program` runs the compiled call sequence in
   preview mode or in approved execution mode.
4. After approved mutations, the runner refreshes the profile cache and records
   evidence with `bubble_framework_sync_evidence`.
5. `bubble_framework_workspace_sync` copies generated artifacts into an
   external BMAD, Superpowers, or SDD workspace when the caller wants framework
   files updated in place.

For incremental language updates, frameworks should use
`bubble_language_cache_status`, `bubble_language_diff`, and
`bubble_language_query` to refresh only the registry slices needed for the
current objective instead of requesting the complete catalog.

Frameworks should not use `tools/list` as their primary Bubble MCP language
source. Use `bubble_language_index`, `bubble_language_query`,
`bubble_language_tool_detail`, and `bubble_language_diff` for low-token
discovery, targeted lookup, lazy schema detail, and cache-aware updates.

## Dynamic Language Registry

Framework adapters should not request the full MCP catalog by default. The
Bubble MCP language is dynamic because native tools, enabled extension-pack
tools, installed skills, learning records, and runtime coverage can change over
time.

Use the low-token language APIs in this order:

1. `bubble_language_index` returns `registry_version`, family counts, source
   counts, risk counts, compact installed-skill digest, and runtime rules.
2. `bubble_language_query` returns scoped tools for the current objective,
   family, source, or risk. Each match includes compact capability and status
   signals such as preview support, execution support, approval requirement,
   execution surface, and enabled extension metadata when applicable.
3. `bubble_language_tool_detail` lazy-loads schema details only for selected
   tools.
4. `bubble_language_diff` returns added, changed, and removed entries since a
   previous `registry_version`.
5. `bubble_framework_language_pack` returns a BMAD, Superpowers, or SDD shaped
   low-token package.
6. `bubble_framework_compile_program` turns framework-authored compact programs
   into preview-safe MCP calls.

Frameworks should treat `bubble_framework_compile_program` as a syntax checker
for the Bubble MCP language. It maps common high-level intents such as
`create_container`, `headline`, `cta_button`, `create_input`,
`verify_context`, `query_language`, and `sync_evidence` to concrete MCP tools,
injects the active `profile` where the schema supports it, and adds
`execute=false` only for tools that actually expose that argument. If a compiled
step is missing required schema arguments, the compiler returns
`framework_program_missing_required_arguments` with the exact step, tool, and
missing fields instead of producing an unsafe plan.

Example:

```json
{
  "tool": "bubble_framework_language_pack",
  "arguments": {
    "framework": "bmad",
    "profile": "cliente2",
    "scope": "create checkout button",
    "limit": 12
  }
}
```

Compile a framework program:

```json
{
  "tool": "bubble_framework_compile_program",
  "arguments": {
    "framework": "superpowers",
    "profile": "cliente2",
    "program": {
      "objective": "Create checkout CTA",
      "steps": [
        {"intent": "resolve_context", "query": "page checkout"},
        {"intent": "create_container", "context": "checkout", "parent": "root", "label": "Checkout controls"},
        {"intent": "cta_button", "context": "checkout", "parent": "<created_group_id>", "text": "Start checkout"}
      ]
    }
  }
}
```

## CLI Flow

```bash
bubble-mcp framework list

bubble-mcp framework generate \
  --framework bmad \
  --profile cliente2 \
  --objective "Plan the checkout flow" \
  --scope "checkout page" \
  --context-summary '{"pages":5,"workflows":12}'

bubble-mcp framework status \
  --framework bmad \
  --profile cliente2
```

## Storage

Artifacts are stored under:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/frameworks/
  <framework>/
    <profile>/
      <timestamp>-<objective>/
        framework.json
        *.md
        evidence.jsonl
        evidence.md
```

The generated `framework.json` stores the objective, scope, framework id,
context summary, and execution policy. Evidence records are redacted before
being persisted.

## Current Boundary

V1 is artifact-first:

- It gives BMAD, Superpowers, and SDD a stable MCP entrypoint.
- It keeps generated plans grounded in Bubble context supplied by the agent.
- It lets later MCP runs append validation and implementation evidence.
- It does not yet update an existing external framework repository layout in
  place.
- It does not auto-transform stories into mutations; use executable skills or
  regular MCP tools for implementation.
