# Befree Bubble MCP

Local-first Bubble automation toolkit for developers who want safer, more accurate agent-assisted Bubble work.

This project is being extracted from Befree/Aria as a standalone open source platform. The package is installable and exposes a stdio MCP server with local profiles, context tools, planning tools, and authenticated Bubble editor write execution:

```bash
pipx install befree-bubble-mcp
bubble-mcp init
bubble-mcp-server
```

For local checkout development:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python scripts/install_local.py --extras browser,dev
```

If an editable install is interrupted and the console script can no longer
import `bubble_mcp`, run:

```bash
python scripts/install_local.py --repair --extras browser,dev
```

## Current Capabilities

- Bubble-focused CLI.
- MCP server for agent clients.
- Full Aria Bubble MCP tool catalog exposed over MCP, with catalog calls
  dispatched through the packaged Aria-compatible runtime whenever the matching
  runtime command exists.
- Built-in MCP tool coverage report showing native, direct runtime, runtime
  alias, custom adapter, compiler fallback, and uncovered categories.
- Built-in MCP catalog quality gate for agent-facing descriptions, schemas,
  annotations, resources, prompts, and coverage.
- One-command readiness check for health, coverage, catalog quality,
  agent-routing, and optional profile smoke validation.
- Profile status checks that combine profile mapping, session metadata, context
  freshness, and next actions in one read-only response.
- Safe runtime smoke suites for local catalog coverage, read-only profile
  checks, and representative `execute=false` mutation previews.
- Local profile management.
- Compact context loading, search, import, freshness reporting, and local mutation overlay merge from `.bubble`/consolelog/crawler artifacts plus successful local MCP writes.
- Deterministic planner with packaged routing corpus, semantic validator, structural execution validation, and operation snapshots for agent harnesses.
- HTML-to-Bubble import: conservative plan converter plus Aria's advanced `create-from-html` runtime.
- Local session import/listing for Bubble editor credentials.
- Authenticated `/appeditor/write` execution through CLI and MCP.
- Compiler for supported visual/schema/workflow/style plan steps into executable Bubble write payloads.
- Browser-assisted session login through optional Playwright support.
- Eval harness with focused reruns, parser/fallback diagnostics, token estimates, and redacted expert-capture export.
- Lightweight visual snapshot comparison for HTML/Figma/Bubble conversion regression gates.
- Extension kernel foundation with declarative extension packs, local validation,
  consultative learning records, local Bubble manual knowledge cache, declarative
  skill contract validation, and local tool-authoring sessions.
- Local Figma bridge for the Befree Figma plugin. Figma-side integration code is intentionally outside this repository.

## Planned Capabilities

- Broader public eval corpus across Bubble editor families.
- Contributor-friendly tool-family extension scaffolding beyond the current local declarative foundation.
- More visual parity validators for HTML and design bridge conversions.
- Remote Bubble manual refresh through a sanitized GitBook MCP fallback behind
  the existing knowledge-source interface.

## Extension Kernel Documentation

The extension kernel is documented in focused guides:

- [Extension packs](docs/extension-packs.md): local pack layout, manifest contracts, validation, enable/disable state, and preview/execute boundaries.
- [Learning](docs/learning.md): append-only consultative learning records, scopes, CLI/MCP usage, and safety limits.
- [Knowledge sources](docs/knowledge-sources.md): local Bubble manual cache v1, sanitization, search/fetch/guidance tools, and remote-doc fallback boundaries.
- [Tool authoring](docs/tool-authoring.md): guided tool-authoring sessions, captured write classification, payload examples, and safe test workflow.

## Required Setup For Each Bubble Project

Before an MCP client can safely mutate a Bubble app, every Bubble project needs
a local profile, a captured editor session, and a detected project context. Run
these steps once per Bubble app and repeat `session login` or `context detect`
whenever the Bubble session expires or the app structure changes.

### 1. Initialize Local Settings

```bash
bubble-mcp init
```

This creates the local config directory, by default:

```text
~/.config/bubble-mcp
```

Use `BUBBLE_MCP_CONFIG_DIR` when you need a different config location.

### 2. Add A Project Profile

Choose a short profile name that your MCP client and prompts will use to refer
to the Bubble project.

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
```

Optional metadata:

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url "https://bubble.io/page?id=my-bubble-app" \
  --app-version test
```

Confirm the profile exists:

```bash
bubble-mcp profile list
```

For a one-call CLI setup/readiness response, use:

```bash
bubble-mcp profile bootstrap my-app --app-id my-bubble-app
```

MCP clients can do the same setup without shelling out by calling
`bubble_project_bootstrap` with `profile`, `app_id`, and optional
`app_version`, `appname`, `editor_url`, `app_json_path`, or
`consolelog_json_path`. Use `bubble_profile_add` only when the client needs the
lower-level local settings write.

### 3. Capture A Bubble Editor Session

Install the browser extra if it is not already installed:

```bash
python -m pip install "befree-bubble-mcp[browser]"
python -m playwright install chromium
```

For a local checkout, prefer:

```bash
python scripts/install_local.py --repair --extras browser,dev
python -m playwright install chromium
```

Then capture the session:

```bash
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 180
```

MCP clients can trigger the same interactive browser capture with
`bubble_session_login` when a readiness check reports that a profile has no
stored session.

The command opens a local Chromium window. Log in to Bubble and keep the editor
tab open until the terminal prints:

```text
[bubble-mcp session] Session cookies detected. You can close the browser now; the CLI will save the newest captured session.
```

After this message appears, it is safe to close the browser. The final command
output is a redacted JSON object. For automated scripts, pass `--quiet` to hide
progress messages while keeping the JSON output:

```bash
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 180 --quiet
```

Manage captured sessions:

```bash
bubble-mcp session list
bubble-mcp session inspect --profile my-app
```

`session inspect` never prints raw cookies. Use it to confirm that cookies are
present and Bubble write headers can be computed. MCP clients can perform the
same read-only check with `bubble_session_inspect`.

### 4. Detect Project Context

This step is required before asking an agent to create, update, import, or
inspect app structure through the MCP. It downloads/processes the Bubble project
context and stores it locally for the selected profile.

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --force
```

To save the compact context in a known path for inspection:

```bash
bubble-mcp context detect \
  --profile my-app \
  --app-id my-bubble-app \
  --force \
  --output ./my-bubble-app.context.json

bubble-mcp context summary --file ./my-bubble-app.context.json
```

If your app uses a non-default Bubble version, include it:

```bash
bubble-mcp context detect \
  --profile my-app \
  --app-id my-bubble-app \
  --app-version test \
  --force
```

Refresh context after creating pages/elements outside this MCP, after importing
from another tool, or when an agent cannot resolve a page, reusable element,
style, workflow, data type, or path.

### 5. Verify Profile Readiness

Confirm profile, session, and context readiness before using the profile from an
MCP client:

```bash
bubble-mcp profile status --profile my-app
```

The `ready` flag is true when the profile exists, the stored session targets
the same Bubble app, and the compact context is loadable and fresh. If setup is
incomplete, `next_actions` tells you whether to run interactive session login,
explicit session import, or context detection.

### 6. Use The Profile From Your MCP Client

After `profile add`, `session login`, and `context detect` complete, refer to
the profile name in your MCP client prompts:

```text
Using befree-bubble-mcp with profile my-app, create a page called mcp-01.
```

For direct CLI checks:

```bash
bubble-mcp plan "create a text saying Hello on index" --context index
bubble-mcp session inspect --profile my-app
```

## Agent Runtime Behavior

MCP clients should call the exposed MCP tools directly. They do not need to
discover shell commands, inspect the repository, or reconstruct Bubble payloads
manually for normal Bubble editor work.

The stdio server returns compact operating instructions during MCP
`initialize`, so clients that honor server instructions are steered toward
`bubble_profile_status`, `bubble_task_runbook`, and `execute=false` previews
before real writes.

When the client has a user task and needs the next MCP calls, call
`bubble_task_runbook` with the task/profile/context/parent/execute values. It
returns route intents, ordered recipe steps, safeguards, compact matching tool
metadata, and optional profile readiness in one call. Use `bubble_agent_guide`,
`bubble_task_recipe`, and `bubble_tool_search` only when the client needs those
smaller pieces for diagnosis or a narrow follow-up.

The CLI exposes the same compact discovery layer for terminals and agents that
only have shell access:

```bash
bubble-mcp tools runbook --task "convert an HTML selector from a URL into a Bubble page" --profile my-app --context index
bubble-mcp tools guide --task "convert an HTML selector from a URL into a Bubble page"
bubble-mcp tools search --query "html selector import" --limit 5
bubble-mcp tools recipe --task "convert an HTML selector from a URL into a Bubble page" --profile my-app --context index
bubble-mcp tools coverage
bubble-mcp tools quality
bubble-mcp readiness --profile my-app --context index
bubble-mcp profile status --profile my-app
```

MCP clients that support resources and prompts can also read
`bubble://docs/agent-runtime`, `bubble://catalog/summary`, and
`bubble://recipes/summary`, read a specific recipe such as
`bubble://recipes/html_import`, read profile readiness such as
`bubble://profiles/my-app/status`, read one complete tool schema such as
`bubble://tools/create_from_html`, or request the `bubble-task-runbook`,
`bubble-html-import`, and `bubble-quality-gate` prompts. Use the one-tool
schema resource instead of loading the full `tools/list` response after the
agent already selected a tool.

When a catalog tool is called with a `profile`, the server resolves the stored
profile, session, context, and local mutation overlay, then tries to execute the
matching packaged Aria-compatible runtime method. This keeps element creation,
updates, style sync, workflow, data, branch, changelog, Figma bridge, and HTML
import behavior aligned with the mature Bubble payload conventions used by
Aria.

Calls with `execute=false` or without `execute` still compile through the same
runtime path when possible, but the Bubble write is intercepted and returned as
a preview. Calls with `execute=true` use the captured local Bubble session and
write to `/appeditor/write`.

Use `bubble_tool_coverage` from an MCP client, or `bubble-mcp tools coverage`
from the CLI, to verify current catalog coverage. The full exposed catalog and
the Aria-compatible subset are expected to report `uncovered_count: 0`. Coverage
is compact by default; use `include_details=true` in MCP or `--include-tools`
in the CLI only when per-tool classifications are needed.

Use `bubble_catalog_quality` from an MCP client, or `bubble-mcp tools quality`
from the CLI, to verify that the catalog remains efficient for agents: no
missing descriptions, undocumented input fields, invalid annotations, broken
resources/prompts, or uncovered exposed tools.

Use `bubble_runtime_smoke` or `bubble-mcp smoke runtime` for operational checks.
The `coverage` suite runs local catalog coverage and catalog quality checks.
The `agent-routing` suite validates representative natural-language Bubble
requests against `bubble_task_runbook`, `bubble_agent_guide`,
`bubble_task_recipe`, and `bubble_tool_search`; it includes HTML import, page
creation, Figma/style sync, branches/changelog, setup/context refresh,
interactive session login, and workflow prompts, and it does not post changes
to Bubble.
The `visual-repair` suite validates that visual parity requests produce an
actionable `bubble_visual_audit` repair plan without posting changes to Bubble.
The `preview-write` suite compiles representative mutations with
`execute=false`; it does not post changes to Bubble.
The `family-preview` suite exercises representative visual, container, input,
schema, workflow, style, HTML import, branch, and changelog paths without
posting changes.

Use `bubble_readiness_check` from an MCP client, or `bubble-mcp readiness` from
the CLI, when you want the recommended compact sequence in one call: health,
coverage/catalog quality, agent-routing, profile-status readiness when a
profile is provided, and optional profile safe-read or family-preview smoke.
Detailed nested smoke output is opt-in with
`include_details=true` or `--include-details`.

For an authenticated real-write smoke test, use the explicit `execute-write`
suite. It creates a temporary page and representative elements only when
`--execute` is present:

```bash
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --report ./runtime-smoke.json
```

Add `--verify-context` when you want the smoke to refresh the Bubble context
after the write and fail if the temporary page/elements are not present with
the expected defaults. If `--cleanup` is also set, verification runs before the
temporary page is deleted, then the context is refreshed again after cleanup.

For conversion fidelity checks, use structured visual snapshots:

```bash
bubble-mcp eval capture-visual \
  --source https://example.com/page.html \
  --selector '#hero' \
  --output /tmp/hero-reference.json

bubble-mcp eval capture-bubble-visual \
  --profile my-app \
  --page mcp-01 \
  --selector '#hero' \
  --output /tmp/hero-actual.json

bubble-mcp eval visual \
  --reference /tmp/hero-reference.json \
  --actual /tmp/hero-actual.json \
  --require-images
```

When the agent should diagnose and fix supported visual drift, use the
actionable audit instead of plain comparison:

```bash
bubble-mcp eval visual-audit \
  --reference /tmp/hero-reference.json \
  --actual /tmp/hero-actual.json \
  --profile my-app \
  --context mcp-01 \
  --parent gp_home \
  --app-id my-bubble-app \
  --require-images \
  --output-plan /tmp/hero-repair-plan.json
```

Add `--execute` only when you want the generated repair plan to be compiled and
written to Bubble through the stored session. The audit can also include
screenshots for multimodal LLM review:

```bash
bubble-mcp eval visual-audit \
  --reference-screenshot /tmp/source.png \
  --actual-screenshot /tmp/bubble.png \
  --screenshot-task "Check typography, image sizing, gradient direction, and max-width."
```

Screenshot-only input produces an LLM-ready comparison payload and does not
mutate Bubble. Use structured snapshots when you want executable repair steps.

## Codex MCP Setup

Use the virtualenv Python module path in your MCP config:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/python",
      "args": ["-m", "bubble_mcp.server.stdio"],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

The `bubble-mcp-server` console script is also installed, but the Python module
form is the most reliable option for desktop MCP clients that do not inherit an
activated virtual environment or are affected by local macOS execution policy.

## Figma Bridge

Start the local bridge from the repository clone when using the Befree Figma plugin:

```bash
BUBBLE_MCP_CONFIG_DIR=/Users/me/.config/bubble-mcp npm run figma:bridge
```

The bridge listens on `http://localhost:3333`, exposes `/health`, `/profiles`,
and `/sync`, saves incoming plugin payloads under `tmp/bridge_data`, and runs
the Aria-derived Figma-to-Bubble runtime through the local Bubble session before
returning success.

## Extension Kernel Foundation

The extension kernel v1 is local-first and declarative. Extension packs, learning
records, cached knowledge records, skill contracts, and tool-authoring captures
are stored under `BUBBLE_MCP_CONFIG_DIR` or the default
`~/.config/bubble-mcp` directory.

Extension packs are imported into a `pending` state. A pack may be enabled only
after local validation succeeds, and enabled extension tool schemas are
revalidated before they are exposed through the MCP tool catalog. Validation
rejects tool name collisions with built-in/native tools, duplicate names inside
the pack, symlinks or path escapes, and likely secrets. Extension packs are JSON
contracts only; v1 does not execute arbitrary Python, Node, shell, or bundled
code from a pack. Declarative extension tool schemas are catalog-visible in v1,
but their recipe/template execution runner is intentionally not implemented yet;
calling one returns `extension_tool_execution_not_implemented`.

When declarative execution is added, mutating extension tools must inherit the
same preview-first contract as the native Bubble MCP catalog. They should
default to `execute=false`; callers must explicitly opt in to `execute=true`
before any Bubble write.

Local learning records are consultative only. They can inform planning, ranking,
warnings, and documentation, but they cannot execute writes, bypass validation,
or auto-confirm destructive actions. Local knowledge guidance is also advisory:
official Bubble docs can explain Bubble concepts, but they never prove the
current project state. Project state still comes from the local profile,
captured session, detected context, and fresh Bubble reads.

The Chrome extension companion is shipped in `chrome-extension/`. It must stay
local-only, must not use Aria email/password auth, must not depend on an Aria
remote relay or auth server, and its UI should be limited to service status,
event summary, local port/key configuration, and a local enable/disable toggle.
Run its local listener with `bubble-mcp extension companion serve --port 3847`
or, from this checkout, `npm run chrome:companion`.

Focused docs:

- [Extension packs](docs/extension-packs.md)
- [Learning](docs/learning.md)
- [Knowledge sources](docs/knowledge-sources.md)
- [Tool authoring](docs/tool-authoring.md)
- [Chrome extension companion](chrome-extension/README.md)

## Safety Defaults

- No real project data is included in this repository.
- Mutating commands require a local session and explicit `execute=true`/`--execute`.
- Without execution opt-in, write commands preview the normalized request.
- `bubble_execute_plan` runs structural validation before writes and returns `operation_snapshot.next_user_action` for agents.
- Session credentials stay local.
- Sensitive values are redacted before logs or reports.
- Extension packs are declarative only and do not run arbitrary code in v1.
- Imported extension packs start pending; activation requires local validation.
- Local extension, learning, knowledge, and tool-authoring state stays under
  `BUBBLE_MCP_CONFIG_DIR`.

## Status

Early alpha. Real Bubble editor writes are supported when you provide a valid local session and an exact Bubble `/appeditor/write` payload. Generated plans that do not yet contain a `write_payload` are previewable but not automatically applied. Extension kernel v1 is a foundation for declarative local packs, advisory records, and captured-write classification; it does not generate, activate, replay, or execute new tools automatically.
