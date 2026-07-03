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

Use `bubble-mcp-server` as the command:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "bubble-mcp-server",
      "args": [],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

If your MCP client does not inherit the activated virtual environment, use the
absolute path to the installed console script:

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

Keep `BUBBLE_MCP_CONFIG_DIR` consistent with the directory used when you ran
`bubble-mcp init` and `bubble-mcp profile add`.

## Quick manual protocol check

You can verify the server responds before adding it to a client:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' | bubble-mcp-server
```

The response should include server info for `befree-bubble-mcp` and the tools
listed below.

## Available tools

The server exposes the complete 196-tool Aria Bubble MCP catalog, plus native
standalone helper tools. Catalog tools accept their original arguments. For
standalone execution, pass `app_id` for compiler-supported families or
`write_payload` for exact Bubble editor writes.

- `bubble_health_check`: reports local server capabilities.
- `bubble_profile_list`: lists configured local Bubble profiles.
- `bubble_context_summary`: summarizes a compact context JSON file.
- `bubble_context_find`: searches a compact context JSON file.
- `bubble_context_import`: imports `.bubble`/consolelog or crawler-index JSON into compact context.
- `bubble_plan`: creates a validated deterministic plan.
- `bubble_plan_dry_run`: compatibility alias for `bubble_plan`.
- `create_from_html`: Aria's advanced HTML importer. Pass `profile`, `app_id`, `context`, `parent`, and `url`, `html_file`, or `html`; set `selector` for targeted imports and `execute=true` to write to Bubble.
- `bubble_compile_plan`: compiles supported abstract plan steps into Bubble write payloads.
- `bubble_eval_run`: runs a deterministic planning eval dataset. Pass `compile=true` and `app_id` to include compiler coverage and token estimates.
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
