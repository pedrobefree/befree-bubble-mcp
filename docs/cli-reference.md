# CLI Reference

The Python package installs two console scripts:

- `bubble-mcp`
- `bubble-mcp-server`

Use `bubble-mcp` to manage local settings. Use `bubble-mcp-server` from an MCP
client configuration.

## `bubble-mcp init`

Creates a local config directory and empty `settings.json`.

```bash
bubble-mcp init
```

Default path:

```text
~/.config/bubble-mcp/settings.json
```

Options:

```bash
bubble-mcp init --config-dir /path/to/bubble-mcp-config
```

`--config-dir` affects the init command. For later commands and the server, set
`BUBBLE_MCP_CONFIG_DIR` when you want to use a non-default settings directory.

## `bubble-mcp profile add`

Adds or updates a Bubble profile.

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
```

Arguments and options:

- `name`: local profile name, such as `my-app`.
- `--app-id`: required Bubble app id.
- `--appname`: optional Bubble app name. Defaults to `--app-id`.
- `--editor-url`: optional Bubble editor URL for the app.

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url "https://bubble.io/page?id=my-bubble-app" \
  --app-version test
```

The first profile added becomes `default_profile` in `settings.json`.

MCP clients should prefer `bubble_project_bootstrap` when the profile name and
Bubble app id are known; it can create/update the profile and return readiness
next actions in one call. Use `bubble_profile_add` only for the lower-level
local settings write.

## `bubble-mcp profile bootstrap`

Creates or updates a local profile and returns readiness plus the next setup
actions in one response.

```bash
bubble-mcp profile bootstrap my-app --app-id my-bubble-app
```

Optional context refresh:

```bash
bubble-mcp profile bootstrap my-app --app-id my-bubble-app --detect-context --force-context
```

Use this as the preferred CLI setup command when you already know the profile
name and Bubble app id.

## `bubble-mcp profile list`

Lists local profiles.

```bash
bubble-mcp profile list
```

Output is JSON and includes:

- `default_profile`
- `profiles[].name`
- `profiles[].app_id`
- `profiles[].appname`
- `profiles[].editor_url`

## `bubble-mcp profile refresh-cache`

Forces a one-call refresh of the local cache/context artifacts for a configured
profile. This is the CLI equivalent of the `bubble_profile_cache_refresh` MCP
tool and is the preferred path for routine requests such as "refresh cache do
profile cliente2".

```bash
bubble-mcp profile refresh-cache --profile my-app
bubble-mcp profile refresh-cache --profile my-app --app-id my-bubble-app
bubble-mcp profile refresh-cache --profile my-app --no-force
```

The command resolves `app_id` and `app_version` from the profile when omitted,
forces context detection by default, downloads or reuses the `.bubble` export
according to the detector inputs, splits modules, and returns JSON with updated
artifact paths and timestamps. Agents should call this command/tool directly
instead of inspecting cache directories or probing CLI help for low-level
context commands.

## `bubble-mcp profile status`

Returns a read-only readiness snapshot for one profile.

```bash
bubble-mcp profile status --profile my-app
bubble-mcp profile status --profile my-app --max-age-hours 12
```

The response combines profile mapping, stored session metadata, context
loadability/freshness, and next actions. Use it before real writes when the
caller needs to know whether session login or `context detect --force` is still
required.

## `bubble-mcp context summary`

Summarizes a compact Bubble context JSON file.

```bash
bubble-mcp context summary --file /path/to/context.json
```

The response includes `freshness` with source, timestamp source, age, and stale
status. This helps agents decide whether to call `context detect --force` before
a mutation.

## `bubble-mcp context find`

Searches a compact Bubble context from a configured profile or a local JSON file.

```bash
bubble-mcp context find "page:index" --profile my-app --exact --no-include-metadata
bubble-mcp context find "button" --file /path/to/context.json --limit 10
bubble-mcp context find "page:index" --file /path/to/context.json --exact --no-include-metadata
```

Prefer `--profile` for agent workflows so the CLI resolves the current profile
context and mutation overlay without requiring the caller to know local file
paths. Use `--file` for diagnostics or standalone context artifacts.

Use `--exact` for verification checks that must match a specific node id,
label, Bubble id, or context reference without fuzzy token matches. Add
`--no-include-metadata` for compact existence/absence checks. Exact results
include `match_field` and `match_value` so agents can distinguish direct node
matches from references such as `context`. The response also includes `count`,
`limit`, `truncated`, `exact`, and `include_metadata` for low-token verification.

## `bubble-mcp transfer`

Plans, previews, and executes project-to-project transfers. Source profiles are
read-only; target profiles need a captured session for preview and execution.

```bash
bubble-mcp transfer inventory --source-profile source-app --source-type reusable --source-ref Header

bubble-mcp transfer plan \
  --source-profile source-app \
  --target-profile target-app \
  --source-type reusable \
  --source-ref Header \
  --target-context index \
  --target-parent root

bubble-mcp transfer preview --transfer-id TRANSFER_ID --include-payloads
bubble-mcp transfer execute --transfer-id TRANSFER_ID --execute --confirm
bubble-mcp transfer status --transfer-id TRANSFER_ID
```

Available source types:

- `page`
- `reusable`
- `element`

Planning policy options:

- `--conflict-policy`: `fail`, `rename`, `replace`, `reuse_existing`
- `--asset-policy`: `reference_url`, `stage_and_upload`, `skip`
- `--dependency-policy`: `map_only`, `map_or_create`, `skip_optional`
- `--collection-policy`: `skip`, `map_existing`, `create_missing`,
  `replace_schema`
- `--api-connector-policy`: `skip`, `map_existing`, `structure_only`
- `--data-records-policy`: `skip`, `export_manifest_only`,
  `data_api_import_preview`

See [Project transfer](transfer.md) for the full workflow and current limits.

## `bubble-mcp plan`

Creates and semantically validates a local Bubble plan from a message.

```bash
bubble-mcp plan "add a button to the index page" --context index --parent index
```

This command does not mutate Bubble by itself. The response includes:

- `routing`/`parser`: whether the packaged example corpus or fallback regex matched.
- `validation`: semantic validation.
- `structural_validation`: step graph and payload readiness.
- `operation_snapshot.next_user_action`: the next action an agent should take.

Use `execute-plan --execute` for plans whose steps include `args.write_payload`.

## `bubble-mcp import html`

Converts an HTML file or hydrated URL into Bubble output. Local files use the conservative plan converter by default; `--url` automatically uses the advanced rendered runtime.

```bash
bubble-mcp import html --file component.html --context index --parent index
```

Add `--compile --app-id` to convert supported generated steps into
`args.write_payload` objects immediately.

```bash
bubble-mcp import html --file component.html --context index --parent index --compile --app-id my-bubble-app
```

Use `--runtime` for Aria's advanced `create-from-html` importer:

```bash
bubble-mcp import html \
  --url https://example.com/page.html \
  --profile smoke \
  --app-id my-bubble-app \
  --context index \
  --parent root \
  --selector '.pricing-card' \
  --translate-to-existing-styles
```

Add `--execute` to apply the generated writes to Bubble.

## `bubble-mcp session import`

Imports local Bubble editor session headers/cookies.

```bash
bubble-mcp session import --profile my-app --file ./bubble-session.json
```

## `bubble-mcp session login`

Opens a local Chromium browser through Playwright and captures Bubble cookies.
The browser profile is persisted under the local Bubble MCP config directory so
subsequent login attempts can reuse the same Bubble browser session.

```bash
python -m pip install "befree-bubble-mcp[browser]"
python -m playwright install chromium
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 120
```

`--wait-seconds` is the maximum time the command keeps polling cookies. After
logging in, leave the Bubble editor open for a few seconds before closing the
browser window. If the process is interrupted after Bubble cookies were
observed, the newest usable session is still saved; if it is interrupted before
login completes, rerun the command.

During capture, the command prints human-readable progress to stderr. When it
prints `Session cookies detected. You can close the browser now`, the session
has enough data to be saved. The final JSON result is still printed to stdout.
Use `--quiet` to suppress progress messages in scripts.

## `bubble-mcp session list`

Lists imported session metadata without printing secrets.

```bash
bubble-mcp session list
```

## `bubble-mcp write`

Sends an exact Bubble `/appeditor/write` payload. Without `--execute`, this
prints the normalized request and redacted headers.

```bash
bubble-mcp write --profile my-app --payload ./write-payload.json
bubble-mcp write --profile my-app --payload ./write-payload.json --execute
```

## `bubble-mcp execute-plan`

Executes a plan. If the plan contains abstract `create_text` or `create_group`
steps, pass `--compile` and `--app-id` to compile those steps into
`args.write_payload` before execution. When `--compile` is used and no
`--context-file` is supplied, the CLI detects project context automatically
from the profile/session before compiling.

```bash
bubble-mcp execute-plan --profile my-app --file ./plan.json --execute
bubble-mcp execute-plan --profile my-app --file ./plan.json --app-id my-bubble-app --compile --execute
bubble-mcp execute-plan --profile my-app --file ./plan.json --app-id my-bubble-app --compile --context-file ./my-app-context.json --execute
```

When compiling visual creation steps for a real editor write, pass
`--context-file` or include Bubble internal ids in the step args. The compiler
uses that context to emit the editor index updates Bubble expects:
`_index.id_to_path`, `_index.issues_list`, and `_index.issues_sub`, followed by
the `CreateElement` change at the resolved `%p3.<page-id>.%el.<slot-id>` path.
Bubble can return HTTP 200 for a write that does not appear in the editor when
these index paths target the wrong page or parent.

Use `--no-auto-context` only when deliberately compiling without live project
context.

When a context file is loaded for compile/execute, the runtime also merges the
local mutation overlay for the selected profile/app. This makes pages and
elements created by earlier MCP writes visible even when the cached `.bubble`
export has not been refreshed yet.

## `bubble-mcp branch`

Reads and manages Bubble editor branches through the stored local session.

```bash
bubble-mcp branch list --profile my-app
bubble-mcp branch contributors --profile my-app --app-version test
```

Create a branch from the profile/default version:

```bash
bubble-mcp branch create --profile my-app --name feature-x --description "Feature branch"
```

Add `--execute` to actually create it in Bubble. To create a sub-branch, pass
the parent branch/version id:

```bash
bubble-mcp branch create \
  --profile my-app \
  --name feature-x-child \
  --from-app-version parent-branch-id \
  --execute
```

Delete previews by default. Real deletion requires both `--execute` and
`--confirm`.

```bash
bubble-mcp branch delete --profile my-app --app-version feature-branch-id
bubble-mcp branch delete --profile my-app --app-version feature-branch-id --execute --confirm
```

## `bubble-mcp changelog fetch`

Fetches Bubble editor changelog entries for a profile and branch/version.

```bash
bubble-mcp changelog fetch --profile my-app --app-version test --num-fetch 50
```

Common filters:

```bash
bubble-mcp changelog fetch \
  --profile my-app \
  --app-version test \
  --start-timestamp 1780282800000 \
  --end-timestamp 1783091092976 \
  --change-type Data \
  --change-path user_types.user. \
  --user-id 1234567890x1234567890
```

For advanced Bubble-native filters, pass `--filters` with either a JSON object
or a path to a JSON file.

## `bubble-mcp metrics`

Reads Bubble editor workload, log, usage, workflow, storage, and time-series
data through the stored local session. These commands are read-only. Log and
performance-audit commands default to Bubble `app_version=live` unless an
explicit `--app-version` is provided.

```bash
bubble-mcp metrics audit --profile my-app --start 2026-04-11T00:00:00Z --end 2026-05-10T00:00:00Z
bubble-mcp metrics workload-by-date --profile my-app --start 2026-04-11T00:00:00Z --end 2026-05-10T00:00:00Z --granularity day
bubble-mcp metrics workload-breakdown --profile my-app --start 2026-04-11T00:00:00Z --end 2026-05-10T00:00:00Z --tag1 workflow
bubble-mcp metrics logs --profile my-app --start 2026-04-11T00:00:00Z --end 2026-04-11T01:00:00Z --limit 25
bubble-mcp metrics plan-usage --profile my-app
bubble-mcp metrics workflow-runs --profile my-app
bubble-mcp metrics storage --profile my-app
bubble-mcp metrics time-series --profile my-app --start 1783440000000 --end 1783526400000 --metric page_views
```

Use `metrics audit` for broad questions such as "what should I improve for app
performance?". It combines workload by date, workload breakdown, workflow runs,
plan usage, storage, and optionally logs into compact recommendations for an
agent. Use the lower-level commands when the caller needs a specific Bubble
editor endpoint.

## `bubble-mcp compile-plan`

Compiles supported abstract plan steps into Bubble write payloads.

```bash
bubble-mcp compile-plan --file ./plan.json --app-id my-bubble-app --output ./compiled-plan.json
bubble-mcp compile-plan --file ./plan.json --app-id my-bubble-app --context-file ./my-app-context.json
```

## `bubble-mcp context detect`

Detects and materializes project context. It tries local `.bubble` or
`console.log(app)` artifacts when provided, then downloads Bubble's authenticated
export endpoint (`/appeditor/export/{version}/{appId}.bubble`) before falling
back to the editor crawler. Successful downloads are cached under
`~/.config/bubble-mcp/contexts/{profile}/` and split into
`bubble_modules/{appId}/` next to the compact context.

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --force
bubble-mcp context detect --profile my-app --app-id my-bubble-app --bubble-file ./app.bubble
bubble-mcp context detect --profile my-app --app-id my-bubble-app --consolelog-file ./consolelog-app.txt
```

## `bubble-mcp eval run`

Runs a deterministic planning dataset. Use `--compile --app-id` to require
compiler coverage and include write-payload/token metrics in the report. The
report includes matched/tool/args/missing/validation/warning metrics plus
`parser_summary` and `fallback_summary` for agent-routing diagnostics.
Datasets may include structured visual snapshots; use `expected_visual_ok=false`
with `expected_visual_issues` to assert that known visual regressions are
detected by issue code.
Use `--filter`, `--failed-from`, `--offset`, and `--limit` for cheap focused
reruns instead of reprocessing a large dataset.

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --compile --app-id my-bubble-app --report reports/basic-compiled.json
bubble-mcp eval run --dataset tests/fixtures/evals/visual-regression.json
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --failed-from reports/basic-compiled.json
```

## `bubble-mcp eval export-expert`

Exports local captured Bubble editor writes into redacted eval cases with family
classification, tool hints, basic expected arguments, and visual references
when supported. Use it to grow the eval corpus from known-good examples without
committing sessions, cookies, or raw secrets.

```bash
bubble-mcp eval export-expert \
  --input /tmp/captured-writes.json \
  --output /tmp/bubble-expert-evals.json
```

## `bubble-mcp eval visual`

Compares two structured visual snapshots for layout, text, image, typography,
max-width, and gradient drift. This is a lightweight visual/perceptual harness
for conversion regressions and does not contact Bubble.

```bash
bubble-mcp eval visual \
  --reference tests/fixtures/visual-snapshots/hero-reference.json \
  --actual tests/fixtures/visual-snapshots/hero-actual-ok.json \
  --require-images
```

## `bubble-mcp eval visual-audit`

Audits visual drift and turns supported issues into an executable Bubble repair
plan. It accepts saved snapshots, URL/HTML sources, rendered Bubble actual
captures, and optional screenshots for LLM-based comparison review.

Preview the repair plan from saved snapshots:

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

Capture the reference from a URL and the actual output from Bubble, then audit:

```bash
bubble-mcp eval visual-audit \
  --reference-source https://example.com/page.html \
  --actual-profile my-app \
  --actual-page mcp-01 \
  --selector '#hero' \
  --profile my-app \
  --context mcp-01 \
  --app-id my-bubble-app
```

Add `--execute` only after reviewing the returned `repair_plan`; execution uses
the stored Bubble session and the normal compiler/structural validation path.
Screenshot inputs are also accepted:

```bash
bubble-mcp eval visual-audit \
  --reference-screenshot /tmp/reference.png \
  --actual-screenshot /tmp/actual.png \
  --screenshot-task "Focus on typography, image sizing, gradient direction, and max-width."
```

Screenshot-only audits return `llm_screenshot_review` with base64 image content
and a strict JSON prompt for a multimodal LLM client. They do not mutate Bubble
by themselves because screenshots alone do not carry stable Bubble element
targets.

## `bubble-mcp eval capture-visual`

Captures a structured visual snapshot from a URL, local HTML file, or raw HTML
string. Use this before `eval visual` when the reference or actual snapshot
should come from rendered source material instead of hand-authored JSON.

```bash
bubble-mcp eval capture-visual \
  --source https://example.com/page.html \
  --selector '#hero' \
  --output /tmp/hero-reference.json
```

For deterministic local corpus tests, use `--no-rendered-html` with a fixture
file. For URL fidelity checks, keep the default rendered browser capture.

## `bubble-mcp eval capture-bubble-visual`

Captures the actual rendered Bubble app/preview output for a configured profile,
app, page, or explicit URL. Use it after an authenticated write/import to create
the actual snapshot that will be compared against the source/reference.

```bash
bubble-mcp eval capture-bubble-visual \
  --profile my-app \
  --page mcp-01 \
  --selector '#hero' \
  --output /tmp/hero-actual.json
```

By default `app_version=test` maps to `/version-test`. Use `--url` for a fully
explicit app URL, or `--public-base-url` for custom Bubble app domains.

## `bubble-mcp validate-plan`

Validates a plan JSON file.

```bash
bubble-mcp validate-plan --file /path/to/plan.json
bubble-mcp validate-plan --file /path/to/plan.json --execute
```

Pass `--execute` to require executable write payloads and destructive-operation
confirmation checks.

## `bubble-mcp skill`

Manages executable Bubble MCP skills. Skills are reusable MCP workflows that can
be authored conversationally, imported, exported, enabled, previewed, and run
through the same MCP safety model used by native tools.

Validate or describe a standalone skill contract:

```bash
bubble-mcp skill validate --path ./bubble-security-review.skill.json
bubble-mcp skill describe --path ./bubble-security-review.skill.json
bubble-mcp skill describe --skill-id bubble-security-review
```

Import, enable, list, export, or disable a skill:

```bash
bubble-mcp skill import --path ./bubble-security-review.skill.json
bubble-mcp skill enable bubble-security-review
bubble-mcp skill list
bubble-mcp skill export bubble-security-review --output ./bubble-security-review.skill.json
bubble-mcp skill disable bubble-security-review
```

Create a skill through the local authoring session flow:

```bash
bubble-mcp skill author start \
  --objective "Review Bubble privacy rules and API Connector risk" \
  --risk read_only \
  --profile my-app

bubble-mcp skill author update <session-id> \
  --field outputs \
  --answer "Return findings, severity, and recommended next MCP actions."

bubble-mcp skill author generate <session-id> \
  --skill-id bubble-security-review
```

Run a preview:

```bash
bubble-mcp skill run bubble-security-review \
  --inputs '{"profile":"my-app"}'
```

For mutating skills, execute only after reviewing the preview and reusing its
returned `run_id`:

```bash
bubble-mcp skill run bubble-security-review \
  --inputs '{"profile":"my-app"}' \
  --execute \
  --approve-execution \
  --run-id skillrun_20260707_1234567890
```

Skill run responses summarize steps and next actions for the user. Raw write
payloads are not included in the user-facing response; redacted audit records
are stored locally under `skills/runs/`.

## `bubble-mcp language`

Diagnostic commands for the dynamic Bubble MCP language registry. Frameworks
should use the equivalent MCP tools instead of reading the full `tools/list`
catalog.

```bash
bubble-mcp language index --profile my-app
bubble-mcp language query "create checkout button" --family visual_editor --limit 8
bubble-mcp language detail create_button bubble_context_find --detail full
bubble-mcp language framework-pack --framework bmad --profile my-app --scope "checkout flow"
```

## `bubble-mcp framework`

Generates local BMAD, Superpowers, or SDD artifacts from Bubble MCP context and
keeps framework evidence synchronized with MCP runs. Framework commands create
planning/spec/evidence files only; Bubble writes still go through normal MCP
tools or executable skills.

List supported adapters:

```bash
bubble-mcp framework list
```

Generate artifacts:

```bash
bubble-mcp framework generate \
  --framework bmad \
  --profile my-app \
  --objective "Plan checkout" \
  --scope "checkout page" \
  --context-summary '{"pages":5,"workflows":12}'
```

Inspect generated artifacts:

```bash
bubble-mcp framework status --framework bmad --profile my-app
```

## `bubble-mcp tools runbook`

Returns a one-call compact agent runbook for a Bubble task: route intents,
ordered recipe steps, safeguards, relevant tool matches, and optional profile
readiness.

```bash
bubble-mcp tools runbook --task "convert an HTML selector from a URL into a Bubble page" --profile my-app --context index
bubble-mcp tools runbook --task "create a text in page index" --profile my-app --context index --include-profile-status
```

Use this as the preferred first discovery command for agents. It avoids reading
CLI help, repository code, or the full MCP `tools/list` response.

## `bubble-mcp tools guide`

Returns compact routing guidance for agents or humans that need to choose the
right MCP tool family without reading the full catalog.

```bash
bubble-mcp tools guide --task "convert an HTML selector from a URL into a Bubble page"
```

Use this when the request is natural language and the caller needs the likely
route, setup requirements, execution policy, and next tool families.

## `bubble-mcp tools search`

Searches the exposed MCP catalog and returns compact matching tool metadata.

```bash
bubble-mcp tools search --query "html selector import" --limit 5
bubble-mcp tools search --query "workflow page load action"
```

Use this instead of dumping `tools/list` when an agent only needs a small,
relevant subset of names, required fields, properties, and annotations.

## `bubble-mcp tools recipe`

Returns an ordered MCP execution recipe for a natural-language Bubble task.

```bash
bubble-mcp tools recipe --task "convert an HTML selector from a URL into a Bubble page" --profile my-app --context index
bubble-mcp tools recipe --task "create a page-load workflow action" --recipe workflow
```

Use this when the caller already understands the user intent but needs the
right preflight checks, tool sequence, arguments to fill, safeguards, and
verification path. It is read-only and does not mutate Bubble.

## `bubble-mcp tools coverage`

Reports how every exposed MCP tool is handled: standalone native code, direct
Aria-runtime dispatch, runtime alias dispatch, custom runtime adapter, compiler
fallback, or uncovered.

```bash
bubble-mcp tools coverage
bubble-mcp tools coverage --include-tools
```

Use this as a fast local parity check. The full exposed catalog and the
Aria-compatible subset are expected to report `uncovered_count: 0`. The default
output is compact; pass `--include-tools` only when you need per-tool
classifications.

## `bubble-mcp tools quality`

Audits the exposed MCP catalog for agent usability.

```bash
bubble-mcp tools quality
```

The report checks tool/resource/prompt identifiers, tool descriptions, input
schemas, property descriptions, annotations, resource metadata, prompt
arguments, and runtime coverage. Use it as a CI-friendly gate before claiming
catalog or harness work is complete.

## `bubble-mcp readiness`

Runs the recommended MCP readiness sequence in one command.

```bash
bubble-mcp readiness
bubble-mcp readiness --profile my-app --context index
bubble-mcp readiness --profile my-app --context index --include-family-preview
bubble-mcp readiness --include-details
```

The check runs server health, the compact coverage/catalog-quality smoke, and
agent-routing. When `--profile` is provided it also requires
`bubble_profile_status.ready=true` and runs read-only profile checks.
`--include-family-preview` adds the broader execute=false family smoke. The
default output is compact; pass `--include-details` only when debugging a
failed nested smoke result.

## `bubble-mcp smoke runtime`

Runs safe runtime smoke suites through the same tool handlers used by MCP
clients.

```bash
bubble-mcp smoke runtime --suite coverage
bubble-mcp smoke runtime --suite agent-routing
bubble-mcp smoke runtime --suite visual-repair
bubble-mcp smoke runtime --suite safe-read --profile my-app
bubble-mcp smoke runtime --suite preview-write --profile my-app --context index --parent root
bubble-mcp smoke runtime --suite family-preview --profile my-app --context index --parent root
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --verify-context
```

Suites:

- `coverage`: local-only catalog coverage and catalog quality checks.
- `agent-routing`: local-only natural-language routing check that validates
  `bubble_task_runbook`, `bubble_agent_guide`, `bubble_task_recipe`, and
  `bubble_tool_search` against representative user prompts without writes.
- `visual-repair`: local-only visual audit check that validates
  `bubble_visual_audit` can turn structured visual drift into a specific repair
  plan without posting changes to Bubble.
- `safe-read`: read-only profile/session/project checks.
- `preview-write`: representative create/import mutations compiled with
  `execute=false`; this does not post changes to Bubble.
- `family-preview`: representative visual, container, input, schema, workflow,
  style, HTML import, branch, and changelog paths with `execute=false` or
  read-only editor calls.
- `execute-write`: authenticated real-write smoke that creates a temporary
  page and representative elements. This suite requires `--execute`.
  Add `--verify-context` to refresh the `.bubble` context after the writes and
  assert that the temporary page, group, text, button, and input materialized
  with required defaults. When combined with `--cleanup`, verification runs
  before the temporary page is deleted, then the context is refreshed again
  after cleanup.

Optional report file:

```bash
bubble-mcp smoke runtime --suite preview-write --profile my-app --report ./runtime-smoke.json
```

Optional real-write cleanup:

```bash
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --cleanup
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --verify-context --cleanup
```

## `bubble-mcp-server`

Starts the stdio MCP server.

```bash
bubble-mcp-server
```

This command waits for newline-delimited JSON-RPC messages on standard input and
writes JSON-RPC responses to standard output. MCP clients usually launch it for
you. For desktop MCP client configuration from a local editable checkout, the
equivalent `python -m bubble_mcp.server.stdio` module command is often the most
reliable launch form.

Implemented MCP methods:

- `initialize`
- `ping`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/templates/list`
- `resources/read`
- `prompts/list`
- `prompts/get`
- `completion/complete`

`tools/call` responses include JSON text content and matching
`structuredContent` for clients that can consume structured tool results. Tool
execution failures return `isError: true` tool results instead of JSON-RPC
errors.

Implemented resources:

- `bubble://docs/agent-quickstart`
- `bubble://docs/agent-runtime`
- `bubble://catalog/summary`
- `bubble://recipes/summary`
- `bubble://recipes/{recipe_id}`
- `bubble://tools/{tool_name}`
- `bubble://profiles/{profile}/status`

Implemented prompts:

- `bubble-task-runbook`
- `bubble-html-import`
- `bubble-quality-gate`

Implemented completions:

- `bubble://recipes/{recipe_id}`: recipe ids such as `html_import`.
- `bubble://tools/{tool_name}`: exposed MCP tool names such as
  `create_from_html`.
- `bubble://profiles/{profile}/status`: configured profile names.
- Prompt arguments: `profile`, `context`, `parent`, and common boolean
  arguments such as `execute` where applicable.
- Tool arguments: `profile`, `context`, `parent`, common boolean arguments such
  as `execute`, `force`, `exact`, `include_metadata`,
  `include_profile_status`, `rendered_html`, and `refresh_context`,
  declared schema enums/examples/defaults such as `kind`, `app_version`,
  `from_app_version`, `bubble_runtime_smoke.suite`, and
  `bubble_task_recipe.recipe` where applicable.

Implemented tools:

- `bubble_health_check`
- `bubble_profile_status`
- `bubble_session_inspect`
- `bubble_session_login`
- `bubble_readiness_check`
- `bubble_task_runbook`
- `bubble_agent_guide`
- `bubble_tool_search`
- `bubble_task_recipe`
- `bubble_tool_coverage`
- `bubble_catalog_quality`
- `bubble_runtime_smoke`
- `bubble_project_bootstrap`
- `bubble_profile_add`
- `bubble_profile_list`
- `bubble_context_summary`
- `bubble_context_find`
- `bubble_plan`
- `create_from_html`
- `bubble_compile_plan`
- `bubble_eval_run`
- `bubble_eval_export_expert`
- `bubble_visual_compare`
- `bubble_visual_capture`
- `bubble_visual_capture_actual`
- `bubble_session_list`
- `bubble_session_import`
- `bubble_editor_write`
- `bubble_execute_plan`
- `bubble_skill_author_start`
- `bubble_skill_author_update`
- `bubble_skill_author_generate`
- `bubble_skill_import`
- `bubble_skill_export`
- `bubble_skill_list`
- `bubble_skill_enable`
- `bubble_skill_disable`
- `bubble_skill_describe`
- `bubble_skill_run`
- `bubble_framework_list`
- `bubble_framework_generate_artifacts`
- `bubble_framework_sync_evidence`
- `bubble_framework_status`
