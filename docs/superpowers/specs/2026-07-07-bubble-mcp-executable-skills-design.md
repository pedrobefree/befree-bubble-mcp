# Bubble MCP Executable Skills Design

Date: 2026-07-07
Status: Approved design
Scope: Befree Bubble MCP standalone package

## Problem

The current skill implementation is only a declarative contract validator. It can validate and describe a `.skill.json` file, but it cannot create, import, enable, export, list, or execute skills. That foundation is useful for schema safety, but it is not a usable product capability.

The v1 skill system must let a developer create skills through a friendly MCP-guided flow, execute them through the MCP, and export/import them for reuse with other MCP installations.

## Goals

- Let users create and update skills through natural language, without hand-writing JSON.
- Keep the persisted skill contract structured, explicit, testable, and shareable.
- Support direct skill import/export and skills shipped inside extension packs.
- Run skills through the MCP with a preview-first execution model.
- Allow mutating skills, but only through a complete plan followed by explicit approval.
- Return friendly step summaries to users, not raw Bubble payloads.
- Persist redacted audit data locally for debugging, replay checks, and accountability.

## Non-Goals

- Do not let imported skills execute arbitrary shell, Python, Node, or system commands.
- Do not allow mutating execution without an approved preview run.
- Do not expose raw Bubble payloads, cookies, headers, or editor request internals in normal user-facing responses.
- Do not implement persistent trusted-skill permissions in v1.
- Do not allow skills to create new MCP tools directly. Skills orchestrate existing tools.

## Architecture

The v1 skill system should be a first-class subsystem under `bubble_mcp.skills`, parallel to extension tools but integrated with extension packs.

Core modules:

- `bubble_mcp.skills.models`
  Defines the executable skill v1 contract: metadata, inputs, allowed tools, steps, gates, approval policy, outputs, and audit configuration.

- `bubble_mcp.skills.validator`
  Evolves the existing validation-only module to validate executable contracts. It must verify tool references, step shape, risk policy, approval gates, output requirements, and safe step types.

- `bubble_mcp.skills.store`
  Stores imported local skills, state files, extension-pack skill projections, and run metadata.

- `bubble_mcp.skills.authoring`
  Implements the friendly creation and update sessions. It conducts a natural-language wizard and generates a structured `.skill.json`.

- `bubble_mcp.skills.runner`
  Executes skills in two phases: preview planning and approved execution.

- `bubble_mcp.skills.audit`
  Persists run records with redacted internal payloads and user-facing summaries.

## Skill Contract V1

The user should not need to author this JSON directly, but the MCP should persist skills in a structured contract like this:

```json
{
  "id": "security-review",
  "name": "Security Review",
  "version": "0.1.0",
  "description": "Review Bubble app security posture.",
  "risk": "mutating",
  "inputs": {
    "profile": { "type": "string", "required": true },
    "scope": { "type": "string", "required": false }
  },
  "allowedTools": [
    "bubble_context_detect",
    "bubble_context_find",
    "bubble_privacy_rule_list"
  ],
  "steps": [
    {
      "id": "refresh_context",
      "type": "tool",
      "tool": "bubble_context_detect",
      "args": {
        "profile": "{{inputs.profile}}",
        "force": true
      },
      "mode": "read"
    },
    {
      "id": "inspect_privacy",
      "type": "tool",
      "tool": "bubble_privacy_rule_list",
      "args": {
        "profile": "{{inputs.profile}}"
      },
      "mode": "read",
      "dependsOn": ["refresh_context"]
    }
  ],
  "approval": {
    "requiredFor": ["mutating", "destructive"],
    "mode": "plan_then_approve"
  },
  "gates": [
    {
      "type": "approval_required",
      "whenRisk": ["mutating", "destructive"]
    },
    {
      "type": "evidence_required",
      "outputs": ["plan", "risk_summary"]
    }
  ],
  "outputs": ["plan", "risk_summary", "execution_log"]
}
```

Contract rules:

- `risk` is one of `read_only`, `mutating`, or `destructive`.
- `inputs` define the schema for `bubble_skill_run`.
- `allowedTools` is mandatory and every step tool must be listed there.
- `steps[*].mode` is one of `read`, `preview`, or `write`.
- `write` steps require `risk` to be `mutating` or `destructive`.
- Mutating and destructive skills require `approval.mode = plan_then_approve`.
- Mutating and destructive skills require an `approval_required` gate.
- Outputs are explicit and must include the user-facing artifacts the run promises to return.
- Step types that imply arbitrary code execution remain forbidden.

Legacy validation-only contracts may still validate, but `bubble_skill_run` should return a clear error unless the skill uses the executable v1 contract.

## Friendly Authoring Flow

The persisted contract is technical; the user interaction must be conversational.

New MCP tools:

- `bubble_skill_author_start`
- `bubble_skill_author_update`
- `bubble_skill_author_generate`

Creation flow:

1. User asks naturally, for example: "Create a skill to review Bubble security."
2. MCP starts an authoring session with objective, optional profile, initial scope, and expected risk.
3. The authoring agent asks one focused question at a time until it has enough information.
4. It suggests compatible tools from the current catalog instead of inventing tools.
5. It proposes steps, gates, outputs, and risk level in friendly language.
6. After user approval, it generates `.skill.json`.
7. It validates the contract.
8. It optionally imports and enables the skill.
9. It guides the first preview run.

Update flow:

1. User asks to update an existing skill.
2. MCP loads the current skill contract.
3. The authoring agent asks what should change.
4. It updates the structured contract, validates it, and increments version metadata.
5. It can replace the installed skill with the same `id`.

The authoring agent must never ask the user to write JSON manually. It can show a friendly summary before generation.

## Import, Export, And Storage

Skills should work as both standalone files and extension-pack resources.

Standalone local storage:

```text
~/.config/bubble-mcp/
  skills/
    installed/
      security-review/
        skill.json
        state.json
    runs/
      skillrun_...json
```

Extension pack integration:

- `extension.json` already has `exports.skills`.
- Enabled extension packs can expose skill contracts.
- `bubble_skill_list` should include local installed skills and enabled extension-pack skills.
- Local override of extension-pack skills is out of scope for v1.

New MCP tools:

- `bubble_skill_import`
- `bubble_skill_export`
- `bubble_skill_list`
- `bubble_skill_enable`
- `bubble_skill_disable`
- `bubble_skill_describe`
- `bubble_skill_run`

Rules:

- Import is idempotent by `skill_id`; replacing a skill returns it to `pending`.
- Enable validates the skill before making it runnable.
- Export includes the skill contract but excludes run history and audit records.
- A skill can reference extension tools only if those tools are enabled in the destination environment.

## Execution Model

Skills execute in two phases.

### Phase 1: Preview

Request shape:

```json
{
  "skill_id": "security-review",
  "inputs": { "profile": "cliente2" },
  "execute": false
}
```

The runner:

- validates the skill;
- resolves inputs;
- confirms allowed tools exist;
- executes `read` steps when safe;
- calls `preview` and `write` steps in preview mode only;
- creates a complete execution plan;
- computes user-facing risks and affected entities;
- saves a `run_id`;
- returns a safe, friendly summary.

The preview response should show step information, not raw payloads:

```json
{
  "ok": true,
  "mode": "preview",
  "run_id": "skillrun_...",
  "summary": "The skill will inspect privacy rules and prepare 3 corrections.",
  "steps": [
    {
      "id": "inspect_privacy",
      "action": "List privacy rules",
      "mode": "read",
      "status": "ready"
    },
    {
      "id": "fix_user_rule",
      "action": "Update User privacy rule",
      "mode": "write",
      "status": "needs_approval",
      "risk": "mutating",
      "affected_entities": ["Data type: User"]
    }
  ],
  "approval_required": true,
  "next_action": "Review the steps and call again with execute=true and approve_execution=true."
}
```

### Phase 2: Approved Execution

Request shape:

```json
{
  "skill_id": "security-review",
  "run_id": "skillrun_...",
  "execute": true,
  "approve_execution": true
}
```

The runner:

- loads the preview run;
- confirms the skill and plan have not changed;
- executes only the approved planned steps;
- blocks tools outside `allowedTools`;
- blocks writes not present in the approved preview plan;
- records audit data;
- returns friendly final outputs.

Hard safety rules:

- No mutation without `execute=true`.
- No mutation without `approve_execution=true`.
- No mutation without a prior `run_id`.
- No mutation outside the approved plan.
- No tool call outside `allowedTools`.
- No normal user-facing response should include raw payloads.

## User-Facing Response Versus Audit

Normal responses should be clean and high-level.

Allowed in user-facing responses:

- step ids;
- action names;
- status;
- affected entities;
- risk summaries;
- output summaries;
- error summaries;
- next action.

Not shown by default:

- raw Bubble write payloads;
- cookies;
- headers;
- path arrays;
- editor request bodies;
- sensitive context internals.

Audit records should store enough detail for debugging and replay checks, with sensitive values redacted.

Audit record fields:

- `run_id`
- `skill_id`
- `inputs`
- `preview_plan`
- `approval`
- `tool_calls`
- `results`
- `outputs`
- `errors`
- timestamps
- redacted internal payloads

## Error Handling

- Invalid skill contracts return validation errors before any run starts.
- Missing inputs return a structured missing-input error.
- Unknown tools or disabled extension tools block preview.
- A failed `read` step stops the run by default.
- A failed `write` step stops execution and writes an audit record.
- Retry from a failed step is allowed only if the approved plan is unchanged.
- Legacy validation-only skills return an explicit `skill_contract_not_executable` error when run.

## Testing Plan

Contract tests:

- valid executable skill;
- unknown tool;
- step tool not listed in `allowedTools`;
- mutating skill without approval policy;
- mutating skill without approval gate;
- missing outputs;
- forbidden executable step types;
- legacy validation-only contract cannot run.

Store/import/export tests:

- import standalone skill;
- list installed skill;
- enable and disable skill;
- export and reimport skill;
- replace skill with same `id`;
- list skill from enabled extension pack.

Authoring tests:

- start authoring session;
- update session from user answers;
- generate valid contract;
- update existing skill;
- preserve skill id while incrementing version metadata;
- reject generated contracts that reference unavailable tools.

Runner preview tests:

- `bubble_skill_run execute=false`;
- read steps execute safely;
- write steps run only as preview;
- user-facing response omits raw payloads;
- internal audit contains redacted details.

Runner execute tests:

- `execute=true` without `approve_execution` fails;
- `execute=true` without `run_id` fails;
- approved run executes planned steps;
- unplanned mutation is blocked;
- tool outside `allowedTools` is blocked;
- failed step stops run and persists audit.

MCP dispatch tests:

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

## Acceptance Criteria

- A user can create a skill through natural-language MCP interaction without writing JSON.
- A user can import and export skills.
- A user can list, enable, disable, and describe skills.
- A user can run a skill preview through MCP.
- A user can approve and execute a mutating skill through MCP.
- Mutating execution requires preview, run id, `execute=true`, and `approve_execution=true`.
- Normal responses show friendly step summaries, not raw payloads.
- Local audit stores redacted internal details.
- Skills can be shipped through extension packs using `exports.skills`.
- Tests cover contract validation, storage, authoring, runner preview, approved execution, MCP dispatch, and safety failures.
