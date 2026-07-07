# Skills

Skills are reusable MCP workflows for Bubble project work. A skill can inspect
project context, run preview-safe MCP tools, prepare a plan, and, when the skill
is mutating, execute only after the user approves the exact planned run.

The user should normally create and run skills through natural-language MCP
interaction. The structured `.skill.json` contract exists so skills are
portable, reviewable, importable, exportable, and safe to validate.

## Storage Layout

Local skills and run audits are stored under the Bubble MCP config directory:

```text
${BUBBLE_MCP_CONFIG_DIR:-~/.config/bubble-mcp}/skills/
  installed/
    <skill-id>/
      skill.json
      state.json
  authoring/
    sessions/
      <session-id>/session.json
    generated/
      <skill-id>.skill.json
  runs/
    skillrun_*.json
```

Importing a standalone skill stores it as `pending`. Enabling validates the
contract before making it runnable. Exporting a skill writes only the skill
contract; run history and audit records are not exported.

Enabled extension packs can also expose skills through `exports.skills`. Those
skills appear in `bubble_skill_list` while the pack is enabled and valid.

## Friendly Authoring Flow

The authoring flow is intentionally conversational. An MCP client should ask the
developer what the skill should do, collect any missing information, generate the
contract, validate it, then offer to import and enable it.

MCP tools:

- `bubble_skill_author_start`
- `bubble_skill_author_update`
- `bubble_skill_author_generate`
- `bubble_skill_import`
- `bubble_skill_enable`
- `bubble_skill_run`

CLI equivalent:

```bash
bubble-mcp skill author start \
  --objective "Review Bubble privacy rules and API Connector risk" \
  --risk read_only \
  --profile cliente2

bubble-mcp skill author update <session-id> \
  --field outputs \
  --answer "Return a concise issue list, severity, and recommended MCP next actions."

bubble-mcp skill author generate <session-id> \
  --skill-id bubble-security-review
```

The generated result includes the path to the `.skill.json`, validation status,
and suggested next MCP calls. The developer does not need to edit JSON for the
normal v1 flow.

## Import, Enable, Export

```bash
bubble-mcp skill import --path ./bubble-security-review.skill.json
bubble-mcp skill enable bubble-security-review
bubble-mcp skill list
bubble-mcp skill export bubble-security-review --output ./bubble-security-review.skill.json
bubble-mcp skill disable bubble-security-review
```

MCP clients should use the equivalent tools:

- `bubble_skill_import`
- `bubble_skill_enable`
- `bubble_skill_list`
- `bubble_skill_export`
- `bubble_skill_disable`

Import is idempotent by skill id. Reimporting a changed skill replaces the local
copy and returns it to `pending`, so the updated contract must pass validation
again before it can run.

## Running A Skill

All runs start as a preview:

```bash
bubble-mcp skill run bubble-security-review \
  --inputs '{"profile":"cliente2"}'
```

The preview validates the enabled skill, checks required inputs, calls read and
preview-safe MCP steps, and returns:

- `run_id`
- skill name and risk level
- human-readable step summaries
- whether approval is required
- next action for the MCP client

For mutating skills, the user approves the previewed run once. The approved call
must pass the returned `run_id`:

```bash
bubble-mcp skill run bubble-security-review \
  --inputs '{"profile":"cliente2"}' \
  --execute \
  --approve-execution \
  --run-id skillrun_20260707_1234567890
```

The runner reloads the saved plan, confirms the skill id and planned tools still
match, and executes only the approved planned steps. If the skill was changed,
disabled, or replaced after preview, the approval is rejected and a new preview
is required.

## User-Facing Output

Skill output is designed for agents and developers, not for payload debugging.
Responses describe the steps, status, result summary, and next action. Raw write
payloads and low-level request bodies are not included in the user-facing
response.

Detailed run records are saved locally under `skills/runs/` with sensitive
values redacted. Use those files only for diagnostics and audit.

## Contract Shape

A minimal executable skill contract looks like this:

```json
{
  "id": "bubble-security-review",
  "name": "Bubble Security Review",
  "version": "0.1.0",
  "description": "Review project context for security-sensitive Bubble settings.",
  "executable": true,
  "risk": "read_only",
  "inputs": {
    "type": "object",
    "properties": {
      "profile": {
        "type": "string",
        "description": "Local Bubble MCP profile."
      }
    },
    "required": ["profile"]
  },
  "allowedTools": ["bubble_profile_status", "bubble_context_find"],
  "steps": [
    {
      "id": "profile_status",
      "tool": "bubble_profile_status",
      "mode": "read",
      "arguments": {
        "profile": "{{inputs.profile}}"
      }
    }
  ],
  "approval": {
    "mode": "none"
  },
  "outputs": {
    "summary": "Return findings and recommended next actions."
  }
}
```

Mutating and destructive skills must use `approval.mode = "plan_then_approve"`
and include an `approval_required` gate. Their write-capable steps must use
`mode = "write"` and still rely on existing MCP tools; skills cannot run shell,
Python, Node, or arbitrary bundled code.

## Extension Pack Skills

An extension pack can ship skills alongside tool schemas:

```json
{
  "exports": {
    "tools": ["tools/create-plugin-widget.tool.json"],
    "skills": ["skills/security-review.skill.json"],
    "evals": []
  }
}
```

Pack validation checks exported skill paths, parses each contract, and rejects
unsafe or invalid definitions. Pack-provided skills become visible only while
the pack is enabled.

## Safety Defaults

- Legacy validation-only skill contracts can still be described, but cannot run.
- Unknown, disabled, or unavailable tools block preview.
- Mutating skills require preview first and approved execution by `run_id`.
- Skill runs use existing MCP tool handlers and safety gates.
- User-facing responses omit raw payloads; audit records are local and redacted.
- Imported skills and extension-pack skills cannot execute arbitrary local code.
