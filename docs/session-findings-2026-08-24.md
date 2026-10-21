# Session findings — 2026-08-22 → 2026-08-24

Consolidated record of every problem, bug, and friction point found while testing the MCP
end-to-end: API Connector flow, workflow tools on the client app, and rebuilding the
ChronoTask hero/menu design on `mcp-test-app` (crawler-only, free plan). Fixed items list
their commit on `feat/api-connector-routing`. Open items are the backlog.

---

## 1. Fixed in this branch

### Tool discovery / routing

| # | Bug | Commit |
|---|-----|--------|
| 1 | No API Connector tool existed in the catalog; the `create_api_call` language intent pointed at `create_api_connector_resource`, a name that was never exposed. Agents asked for "create an API call" and got nothing. | `c0af3f7` |
| 2 | Routing actively misled: `bubble_tool_search("create API Connector call")` returned `create_api_token` (Data API token, unrelated); `bubble_task_runbook` routed "criar chamada de API" to the `visual_edit` recipe (`create_text`/`create_group`). | `c0af3f7` |
| 3 | 322 tools shared only 194 descriptions. 13 workflow tools (`create_workflow`, `add_action`, `delete_action`…) had one identical category blurb; 15 data tools ditto; 41 tools said "Operate on Bubble editor metadata or project structure." Agents could not pick tools by description. Now 323/323 unique (`server/tool_descriptions.py`). | `c0af3f7` |
| 4 | Tool-wizard generated tool names were dotted and >64 chars (`local.toolwiz.api_connector.7e667453.create_an_api_connector_call`) — invalid for MCP clients (`^[a-zA-Z0-9_-]{1,64}$`), so the generated tool could never be called directly. Generated descriptions said only "Generated candidate tool from tool-authoring session …" with zero semantics for search. | `c0af3f7` |

### Workflow tools

| # | Bug | Commit |
|---|-----|--------|
| 5 | `add_action` advertised `event_ref`/`event_type`/`ref_kind` in its schema but the runtime signature lacked them; the dispatch layer dropped them **silently**. Element+event matching only covers click/change/load, so appending to a ConditionTrue or another element's workflow was impossible — agents fell back to hand-built `/appeditor/write` payloads (the client report, bug 4). Also: `to` now aliases `to_email`; unsupported `query_result_type` removed from the schema; a contract test now fails if schema args drift from the runtime signature. | `8d1c99e` |
| 6 | Anti-stale guard duplicated workflows: a workflow created via MCP exists only in the local event cache until the `.bubble` export is re-downloaded; the guard treated every cache-only ref as a ghost and auto-created a duplicate trigger on the server. Now cache rows newer than the export mtime (15 min tolerance) are trusted (`_select_trusted_workflow_rows`, both guard copies). | `3e7b402` |

### Crawler-only profiles (free plan, export endpoint returns 401)

| # | Bug | Commit |
|---|-----|--------|
| 7 | `PathDiscovery` used the crawler-index only to *enrich* a `.bubble`/consolelog source; with neither present, every aria tool died with "No app data source found" even though context detection had succeeded via the crawler. Crawler-index is now a primary fallback source. | `c29ff9d` |
| 8 | `create_from_html` hard-required the `.bubble` file; the dispatch layer only accepted `crawler_index_path` as an explicit argument (never resolved the profile default), and a context-detection failure (no session) was fatal even when a crawler index existed. | `8d20b71` |

### Payload fidelity (the client report, bugs 1–3, 7)

| # | Bug | Commit |
|---|-----|--------|
| 9 | `create_reusable_instance` wrote `%p.custom_id` = the `element_definitions` dict key instead of the definition's inner `.id` — instance pointed at a nonexistent reusable. | `a5dd94c` |
| 10 | Created elements carried no element-level `%nm` and no `%p.order` → accepted by the server but invisible in the editor's Elements Tree and search. `%nm` write added to the shared create queue (benefits every `create_*`); order = max(sibling)+1. | `a5dd94c` |
| 11 | `reusable_name` was required by the runtime but absent from the schema → raw `TypeError` leaked to the agent. `source` is now required in the schema and aliases to `reusable_name`; missing value returns a structured error. | `a5dd94c` |
| 12 | `bubble_editor_write` accepted node bodies with decoded export keys (`type`/`properties` instead of `%x`/`%p`). Server returns 200, the exporter round-trips them ("false green"), but the editor renders `[missing: null]`. New lint rejects these with an explanation; `allow_decoded_keys=true` overrides. | `a5dd94c` |

### Ergonomics

| # | Bug | Commit |
|---|-----|--------|
| 13 | `bubble_context_detect` returned ~75k chars every call (blows client token budgets). Compact response is now the default; `include_details=true` restores the full payload. | `a5dd94c` |
| 14 | `bubble_session_login` with missing Playwright browsers printed a generic "run playwright install" — installing in the wrong Python (global vs the MCP venv, different Playwright versions/builds) doesn't help. Error now prints the MCP venv's own `python -m playwright install chromium` command. | `a5dd94c` |
| 15 | `update_layout` silently rejected (`return False`, no reason in the MCP result) the properties agents actually need: `font_size`, `font_color`, `font_family`, `order`, `rotation_angle`, `opacity`, `background style/color`, `border_roundness`. Whitelist + coercion extended (colors resolve through app tokens; ints parse from px strings). | `f2520b9` |

---

## 2. Open bugs (backlog, roughly by priority)

> Update (same day): items 1, 2, and 6 below are DONE. `create_shape` sizes were actually
> rewritten by `_normalize_fixed_size_properties` in the dispatch layer, which preferred the
> builder's legacy `%w/%h` default (100) over explicit `min_width_css` — priority flipped so
> explicit CSS wins. `create_group` backgrounds compiled an invalid `%bas: "color"` (valid:
> none/bgcolor/image/gradient) — values are now normalized (`color` -> `bgcolor`) with a clear
> error for junk. The schema-vs-runtime contract snapshot test now covers the whole catalog
> (124 tools with known gaps frozen in `tests/fixtures/schema_runtime_contract_gaps.json`;
> regressions and stale entries both fail). Note: the audit reports `sign_the_user_up`,
> `signup_login_with_a_social_network`, and `update_user_credentials` as "<NO RUNTIME METHOD>"
> — dispatch reaches them through a special path (they validate `event_ref` at runtime), so
> treat those three entries as needing verification, not as hard failures.
> Later same day: items 3, 4, and 5 are DONE too — auto-order stamped in the shared create
> queue (max sibling + 1; dry-runs still don't persist sibling state between calls by design),
> icon libraries validated with dashed-prefix mapping (ion-checkmark -> "ion checkmark"), and
> ok=false results now carry a structured `error` extracted from the runtime failure line.

1. **`create_shape` ignores size args.** `min_width`/`min_height`/`fixed_*` are accepted by the
   schema but the body is written with legacy `%w: 100, %h: 100`; the responsive engine ignores
   `%w/%h`, so every shape renders ~100×100. Workaround: `update_layout min/max width/height`
   after creation. Same schema↔runtime contract class as bug 5.
2. **`create_group` ignores `bg_style`/`bg_color`.** Groups are created transparent; background
   only sticks via `update_layout "background style"/"background color"` afterwards.
3. **Child auto-order ties at 0 and renders reversed.** `_next_child_order` reads the parent's
   children from discovery, which does not yet contain siblings created earlier in the same
   batch — every new child gets the same order and Bubble renders them in reverse creation
   order. Needs a per-request pending-children counter (the create queue already threads
   `pending_child_ids_by_parent`; order should ride the same mechanism).
4. **`create_icon` accepts invalid icon libraries silently.** `ion-*` values are written as-is
   and render nothing. Valid formats are `fa fa-*` / `fas|far|fab *` / `phosphor <variant> <name>`.
   Should validate and error with the accepted formats.
5. **Silent `False` returns.** Many aria tools fail with `ok: false` and *no* `error` field in
   the MCP result — the reason is buried in `logs`. Every failure path should surface a
   structured `error`/`message` (bug 15 was invisible for exactly this reason).
6. **Schema↔runtime contract test covers only `add_action`.** Generalizing
   `test_add_action_schema_args_are_accepted_by_runtime_signature` to every catalog tool would
   have caught open bugs 1–2 and fixed bugs 5 and 11 automatically.
7. **`create_event` in dry-run pollutes the event cache** (observed: dry-run repro inserted
   `bcHeO` into `.bubble_cli_cache.json`; same class as auton commit `4dd72c0` for
   `set_event_element`). Dry runs must be side-effect free.
8. **Workflow auto-creation still has no explicit opt-in** (the client report 4.2). `add_action`
   auto-creates a trigger when element+event matching finds nothing; report proposes
   `create_event_if_missing=true` and an error listing available workflows otherwise. Mitigated
   by the recency guard + `event_ref` path, not eliminated.
9. **`add_action` trigger vs target ambiguity** (the client report 4.3). With `event_ref` the action
   target goes in `param` (works, now documented in the description); without it,
   `element_name` means "trigger". Dedicated `target_element` arg would remove the ambiguity.
10. **`rotation_angle` is accepted but Bubble has no native element rotation.** Create schemas
    expose it (style vocabulary leak); writes succeed and do nothing. Should warn or be removed
    from element schemas.
11. **`list_styles` fails on crawler-only profiles** (`return_value: false`; not investigated).
    Probably another consumer that assumes `.bubble`-shaped data.
12. **Routing smoke test count is stale** (pre-existing): expects 8 cases,
    `AGENT_ROUTING_CASES` has 9. Also: no routing smoke case covers the new `api_connector`
    recipe yet.
13. **Windows dev baseline**: 14 unit tests fail on this machine regardless of changes
    (symlink privilege ×6, console-script/chmod ×5, path separators ×2, the count above ×1).

---

### the client report, bug 8 (2026-08-24, evening): expression encodings are not derivable from the export

Three empirical attempts to write "Make changes to thing" actions with conditions via
`bubble_editor_write`, all HTTP 200, all broken differently in the editor: decoded node keys →
`[missing: null]`; encoded node + export-style `param_id` ("Client") → unresolved parameter;
real `param_id` (`bTbgp`) → `[not found: namefull_text] [not found: is_not_empty]`. Conclusion:
the export decodes at least three layers (node keys, param ids, message tokens); the raw
expression encoding cannot be reconstructed from it, and the endpoint performs no semantic
validation (200 for any JSON). Confirmed in-code: `vendor/bubble_modules.py` only splits the
export — the decoding happens server-side, so there is no local map to invert.

Delivered now: `lint_expression_warnings` in `bubble_editor_write` (non-blocking `warnings` on
expression-bearing action bodies, explaining that 200 is not success and pointing to captured
traffic / add_action / Copy/Paste), plus warnings in the tool description and workflow routing
notes. Still open (needs real editor captures, which require a human in the editor):
1. Capture-based add-action runner (api_connector-pack pattern) — capture sessions via
   `bubble_tool_wizard_start` (target: workflow_action) per action type, then template+id
   substitution.
2. Official encoder/decoder with editor round-trip tests — only feasible on top of those
   captured pairs, not the export.

### Bug 8 RESOLVED at the knowledge level (2026-08-24, night): canonical expression form recovered from live editor memory

The Chrome-extension capture path stalled (extension context invalidated after reload), so the
raw form was extracted directly from the running editor instead: Playwright + the the stored client
session, then `window.appquery.app().json._child('api')._child('<wf_id>').raw()` in the page.
(`app.raw()` on the root is blocked "for performance reasons" — child nodes fetch fine.)

Canonical form of the failing case (all 18 steps, editor-serialized, structurally identical —
frozen as `tests/fixtures/expressions/api-event-parameter-golden.json`):

- `APIEventParameter.properties` requires **all four**: `btype_id` ("custom.<type>"),
  `event_id` (the API event id), `param_id` (**the parameter KEY, e.g. "Client"** — not the
  internal `bTbgp` id), `param_name` (same key). Every failed attempt in the report sent only
  `param_id` in isolation — without the type context nothing resolves, which also explains the
  `[not found: ...]` Message tokens (they resolve against `btype_id`).
- Every expression node carries `is_slidable: false`; chains link via nested `next` Messages
  whose `name` is the internal field name or operator (`is_true`, `is_not_empty`).
- Editor memory reads expose nodes with decoded `type`/`properties` keys; write payloads use
  `%x`/`%p` at the node level with this same interior.

Delivered: `lint_expression_warnings` now flags APIEventParameter nodes missing any of the four
context fields with the exact fix. Remaining to harden: a `bubble_live_node_read` tool wrapping
the appquery extraction (golden samples on demand without the Chrome extension), and one
verification write of a fully-formed action to confirm the editor renders it.

## 3. Frictions and platform limits (not code bugs)

- **Three checkouts, two config dirs.** `~/.claude.json` runs the `auton` checkout with
  `~/.config/bubble-mcp`; the client project runs its own checkout with `~/.bubble-mcp`; this repo is a
  third. Half the initial confusion ("fix doesn't work") was testing the wrong copy. One clone
  + one config dir, or a versioned package, would eliminate the class.
- **Playwright browser builds are per-venv-version.** Chromium 1134/1228/1234 confusion; a
  global `playwright install` does not help the MCP's venv (now at least the error says so).
- **Bubble preview caches hard.** After writes, `version-test` shows a "please refresh" banner
  and stale rendering; a screenshot-driven visual loop must reload twice before capturing, or
  it diagnoses ghosts (cost me one full wrong iteration).
- **The Bubble debugger bar** on `version-test` adds page height below the design (white area)
  — harmless, but must be ignored when comparing screenshots.
- **No "move element" tool.** Reparenting an existing element (e.g., pulling the CTA into a new
  row group) has no direct tool; only create/delete or raw payloads.
- **No font-weight control.** Text styling exposes `font_family`/`font_size`/`font_color`; bold
  requires a family variant string; plain `font_weight` isn't a Text property in Bubble.
- **Icon brand assets.** Gmail/Slack/GCal logos need `upload_asset` + `create_image`; text
  glyph approximations only go so far.
- **`create_from_html` first pass lands ~70% fidelity.** Structure, names, and text are
  excellent (clean `gp_*`/`tx_*` tree), but flex alignment, fit-to-content, and gaps drift; the
  screenshot → inspect tree → `update_*` loop is what closed the gap to ~90%. This loop
  (`bubble_visual_capture` + `bubble_visual_audit`) is the highest-value thing to automate.
- **Element self-alignment beats container alignment.** Imported children carry
  `horiz_alignment: flex-start`, so centering the parent container does nothing until each
  child is fitted/aligned — non-obvious, cost two iterations.

## 4. Recommendations (next work)

1. Generalize the schema↔runtime contract test to the whole catalog (kills a whole bug class).
2. Fix `create_shape` sizes and `create_group` backgrounds at the create layer.
3. Thread explicit order through batch creates (pending-children mechanism).
4. Structured errors on every `ok: false` path.
5. Golden-sample validation (the client report's closing suggestion): before writing a node, diff
   its key set against a native sibling of the same type from the app tree; warn on missing
   keys (`%nm`, `order`, encoded-key check already landed as the editor-write lint).
6. Automate the visual loop: import → capture → audit → auto-fix (`fit_width`, alignment,
   order) — the manual version of this took ~250 calls for one hero section.
