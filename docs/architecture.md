# Architecture

Befree Bubble MCP is organized around standalone, headless modules:

- `bubble_mcp.core`: configuration, redaction, shared errors, and Bubble command contracts.
- `bubble_mcp.cli`: user-facing command line interface.
- `bubble_mcp.server`: MCP protocol surface.
- `bubble_mcp.sessions`: local session capture and volatile session storage.
- `bubble_mcp.context`: `.bubble` parsing, crawler indexes, and project graph context.
- `bubble_mcp.planner`: intent planning and execution-plan construction.
- `bubble_mcp.validators`: semantic validation and safety gates.
- `bubble_mcp.converters`: HTML and Figma conversion flows.
- `bubble_mcp.harness`: evals, replay, and accuracy/token reports.
- `bubble_mcp.extensions`: declarative extension pack storage, validation, state,
  and enabled schema loading.
- `bubble_mcp.learning`: append-only consultative learning records.
- `bubble_mcp.knowledge`: local Bubble manual cache and sanitized query helpers
  for future remote fallback.
- `bubble_mcp.skills`: executable skill contracts, local import/export state,
  authoring sessions, preview/approved execution, and redacted run audits.
- `bubble_mcp.tool_authoring`: local sessions that classify captured Bubble
  editor writes for future tool-authoring flows.

These modules form the extension kernel. See
[extension packs](extension-packs.md), [learning](learning.md),
[knowledge sources](knowledge-sources.md), and
[tool authoring](tool-authoring.md), and [skills](skills.md) for operational
details.

Aria should consume this project as a downstream adapter. The open source package must not depend on Electron, Aria IPC, Aria databases, or Aria UI components.

## Extension Kernel Boundary

The extension kernel foundation keeps the standalone package local-first,
declarative, and additive:

- Extension packs are JSON contracts. v1 does not execute arbitrary Python,
  Node, shell, or bundled extension code.
- Imported packs are stored under `BUBBLE_MCP_CONFIG_DIR/extensions/packs` and
  start in `pending`.
- Pack activation is validation-gated. Validation rejects unsafe paths,
  symlinks, unsupported risk levels, missing exported tool files, tool name
  collisions with built-in/native tools, duplicate tool names inside a pack, and
  likely secrets.
- Enabled extension schemas are loaded additively into the MCP catalog only when
  the local pack still validates; importing or enabling a pack never replays a
  captured write by itself.
- Mutating extension tools must keep the native preview-first behavior: default
  `execute=false`, require explicit `execute=true` for writes, and remain
  subject to existing profile/session/context validation.
- Skills are JSON workflow contracts that orchestrate existing MCP tools. They
  can be imported, exported, enabled, previewed, and executed after approval,
  but they cannot run arbitrary local code.
- All extension, learning, knowledge, skill, and tool-authoring state lives under
  `BUBBLE_MCP_CONFIG_DIR` or the default `~/.config/bubble-mcp`.

The Chrome extension companion is shipped in `chrome-extension/`. It is a
separate browser integration surface from declarative extension packs, not an
Aria extension. It must not use Aria email/password auth, must not depend on an
Aria remote relay or auth server, and should expose only local service status,
event summary, local port/key configuration, and a local enable/disable toggle.

## Knowledge And Learning

Knowledge and learning are advisory layers over the existing local context and
execution model:

- `bubble_mcp.knowledge` imports normalized local JSONL records with
  `bubble_knowledge_refresh_source` / `bubble-mcp knowledge refresh-source`.
  Explicit search/fetch calls are cache-only; agent-facing guidance uses the
  selective KnowledgeAdvisor, which searches local cache first and may fetch a
  small number of official Bubble manual pages and Bubble Forum topics.
- Remote selective fetch is enabled by default, can be disabled with
  `BUBBLE_MCP_KNOWLEDGE_REMOTE=0`, and must sanitize queries before any network
  call.
- Official Bubble manual guidance can explain platform behavior, but it never
  proves the current project state. Project state still comes from local
  profiles, captured sessions, detected context, mutation overlays, and fresh
  Bubble reads.
- `bubble_mcp.learning` stores consultative records scoped to `global`,
  `profile`, `project`, or `extension`. These records can influence planning,
  ranking, warnings, and documentation only; they cannot perform writes, bypass
  validation, or confirm destructive actions.

## Tool Authoring Foundation

The tool-authoring foundation stores local sessions under
`BUBBLE_MCP_CONFIG_DIR/tool-authoring/sessions`. Sessions collect captured
Bubble editor write JSON files and classify their write payloads using the
existing expert-capture classifier.

Reviewed sessions can generate candidate declarative extension packs. Generated
packs still pass through the extension-pack validation, import, and enable flow
before their schemas are exposed. Declarative extension tool schemas do not run
arbitrary code, and generic execution remains unavailable until a reviewed
runner exists for the generated template family.

## Executable Skills

Executable skills live under `bubble_mcp.skills` and use existing MCP tool
handlers rather than a separate automation runtime. The skill store manages
standalone imports and enabled extension-pack skills. The authoring module keeps
conversational session state and generates validated `.skill.json` contracts.
The runner always starts with preview, saves a redacted `skillrun_*.json` audit
record, and requires `execute=true`, `approve_execution=true`, and the saved
`run_id` before applying mutating steps.
