# MCP Clients

`bubble-mcp-server` is a stdio MCP server. It is meant to be started by an MCP
client, not kept running as a separate HTTP service.

## Before connecting

Install the Python package and create at least one local Bubble profile:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install ".[browser]"
python -m playwright install chromium
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
bubble-mcp profile list
```

## Codex or other stdio MCP clients

Use the virtualenv Python executable as the command and run the MCP server
module:

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

The `bubble-mcp-server` console script is also installed and works in normal
shell environments:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/bubble-mcp-server",
      "args": [],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

Prefer the Python module form for desktop clients that do not inherit your
activated shell or when local macOS execution policy blocks generated console
scripts.

Keep `BUBBLE_MCP_CONFIG_DIR` consistent with the directory used when you ran
`bubble-mcp init` and `bubble-mcp profile add`.

## Quick manual protocol check

You can verify the server responds before adding it to a client:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' | python -m bubble_mcp.server.stdio
```

The response should include server info for `befree-bubble-mcp`, tools,
resources, and prompts.

Tool call responses include both a JSON text fallback and `structuredContent`
with the same redacted payload for clients that can consume structured MCP
results directly. Tool execution failures are returned as MCP tool results with
`isError: true` and `structuredContent.ok: false`; protocol errors are reserved
for invalid JSON-RPC requests or unsupported MCP methods.

## Resources and Prompts

The server exposes read-only resources for clients that support MCP
`resources/list`, `resources/templates/list`, and `resources/read`:

- `bubble://docs/agent-quickstart`: shortest operating sequence for agents.
- `bubble://docs/agent-runtime`: compact operating rules for agents.
- `bubble://catalog/summary`: JSON summary of catalog size and agent entrypoints.
- `bubble://recipes/summary`: JSON summary of available task recipes.
- `bubble://recipes/{recipe_id}`: complete JSON recipe for one task family,
  such as `bubble://recipes/html_import` or
  `bubble://recipes/page_or_reusable`.

The server also exposes reusable prompts through `prompts/list` and
`prompts/get`:

- `bubble-task-runbook`: turns a user task/profile/context into a short
  execution runbook.
- `bubble-html-import`: guides URL/selector imports through the advanced HTML
  runtime.
- `bubble-quality-gate`: lists the smoke and coverage checks to run before
  claiming MCP work is complete.

Agents should prefer these resources/prompts over inspecting repository docs
when the client supports them.

Clients that support `completion/complete` can autocomplete recipe resource
template variables, such as `recipe_id` for `bubble://recipes/{recipe_id}`, and
common prompt arguments such as `profile`, `context`, `parent`, and `execute`.

## Available tools

The server exposes the complete 196-tool Aria Bubble MCP catalog, plus native
standalone helper tools. Catalog tools accept their original arguments. Agents
should call these tools directly instead of discovering equivalent CLI commands.
Use `bubble_tool_coverage` to audit how every exposed tool is handled.
Use `bubble_runtime_smoke` when the user asks whether the MCP is operational
against a local install or profile.

For profile-based Bubble work, pass `profile` and the tool-specific arguments.
The server resolves the stored Bubble session and context, then routes catalog
tools through the packaged Aria-compatible runtime when a matching runtime
method exists. Without `execute=true`, mutating tools return a compiled preview.
With `execute=true`, they write using the local captured session.

For lower-level standalone execution, pass `app_id` for compiler-supported
families or `write_payload` for exact Bubble editor writes.

- `bubble_health_check`: reports local server capabilities.
- `bubble_agent_guide`: returns a compact routing guide for agents. Call it
  with the user task when the client is unsure which Bubble MCP tool family to
  use; it is read-only and avoids CLI/repository discovery.
- `bubble_tool_search`: searches the exposed MCP tool catalog and returns
  compact matching metadata. Use it for narrow discovery such as `html selector`,
  `workflow action`, or `branch changelog` instead of loading the full catalog.
- `bubble_task_recipe`: returns a compact ordered recipe for a task, including
  preflight checks, tool sequence, arguments to fill, safeguards, and
  verification guidance. Use it when the agent knows the intent but needs the
  execution sequence.
- `bubble_tool_coverage`: reports whether each exposed tool is handled by standalone native code, direct Aria-runtime dispatch, runtime alias dispatch, a custom runtime adapter, compiler fallback, or is uncovered.
- `bubble_runtime_smoke`: runs an operational smoke suite. `coverage` is local-only, `safe-read` performs read-only checks, `preview-write` compiles representative mutations with `execute=false`, `family-preview` exercises representative visual/container/input/schema/workflow/style/HTML/branch/changelog paths without writes, and `execute-write` performs authenticated temporary writes only when `execute=true`. Use `verify_context=true` for real-write smokes that must refresh the Bubble context and confirm the temporary objects materialized.
- `bubble_profile_list`: lists configured local Bubble profiles.
- `bubble_context_summary`: summarizes a compact context JSON file.
- `bubble_context_find`: searches a compact context JSON file.
- `bubble_context_import`: imports `.bubble`/consolelog or crawler-index JSON into compact context.
- `bubble_plan`: creates a validated deterministic plan.
- `bubble_plan_dry_run`: compatibility alias for `bubble_plan`.
- `create_from_html`: Aria's advanced HTML importer. Pass `profile`, `app_id`, `context`, `parent`, and `url`, `html_file`, or `html`; set `selector` for targeted imports and `execute=true` to write to Bubble.
- `bubble_compile_plan`: compiles supported abstract plan steps into Bubble write payloads.
- `bubble_eval_run`: runs a deterministic planning eval dataset. Pass `compile=true` and `app_id` to include compiler coverage, token estimates, parser summary, and fallback reasons; pass `filter`, `failed_from`, `offset`, or `limit` for focused reruns.
- `bubble_session_list`: lists locally imported Bubble editor sessions.
- `bubble_session_import`: imports session headers/cookies into local storage.
- `bubble_editor_write`: posts an exact Bubble `/appeditor/write` payload. Set `execute=true` to mutate Bubble.
- `bubble_execute_plan`: executes plan steps. Set `compile=true` with `app_id` to compile supported abstract steps before execution. Set `execute=true` to mutate Bubble.
- `bubble_branch_list`: lists Bubble editor branches/versions for the selected profile.
- `bubble_branch_contributors`: lists collaborators who contributed to a branch/version.
- `bubble_changelog_fetch`: fetches editor changelog entries with optional date, user, category, root, identifier, and path filters.
- `bubble_branch_create`: creates a Bubble branch or sub-branch. Pass `from_app_version` for sub-branches and `execute=true` to apply it.
- `bubble_branch_delete`: soft-deletes a Bubble branch/version. Requires `execute=true` and `confirm=true` to apply it.

Mutating calls require a stored local session. Calls without `execute=true`
return a preview instead of posting to Bubble.

## Agent Selection Rules

- If the user names a profile and asks for Bubble app work, call the MCP tool
  that matches the requested capability.
- If the client supports MCP resources, read `bubble://docs/agent-quickstart`
  before the first Bubble task in a session.
- If the correct tool family is unclear, call `bubble_agent_guide` with the
  user's task and use its recommended route before inspecting CLI help.
- If the client supports MCP resources, read `bubble://docs/agent-runtime`
  before broad Bubble work.
- If the client supports MCP prompts, use `bubble-task-runbook` for ambiguous
  user tasks that require a multi-step execution sequence.
- If the client only needs candidate tools for a narrow capability, call
  `bubble_tool_search` with a short query instead of reasoning over the full
  `tools/list` payload.
- If the client knows the capability but not the order of operations, call
  `bubble_task_recipe` with the user task, profile, and context before
  executing mutating tools.
- Do not ask the user to memorize internal tool names; infer the right tool
  from the intent, then pass the visible app/page/element names as arguments.
- Do not shell out to inspect CLI help unless a required capability is missing
  from `tools/list`.
- Prefer profile-based calls over manual `app_id` payload construction because
  profile calls can use the stored `.bubble` context, mutation overlay, session,
  and Aria-compatible runtime.
- Use `execute=false` for previews and `execute=true` only when the user asked
  to apply the change.

For schema maintenance and adding new tool families, see
[`tool-schema-development.md`](tool-schema-development.md).
