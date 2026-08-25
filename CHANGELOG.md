# Changelog

## Unreleased

- Workflow listing merges every context root instead of stopping at the first one: the
  mutation overlay injects raw roots (%ed for reusables, %p3 for pages) carrying ONLY the
  workflows a write touched, and that partial root used to shadow the .bubble export root
  entirely. On a reusable with 33 workflows, list_events and inspect_context reported 1 as
  soon as any write had touched the context - and because the same listing feeds workflow
  matching by event type, add_action could no longer see the existing workflow and would
  auto-create a duplicate. Reads now union the raw, discovery and module roots (raw first,
  so overlay rows still win per key); writes keep resolving a single root through the write
  root token.
- Canonical raw form of APIEventParameter expressions recovered from live editor memory
  (Playwright + appquery child-node raw()): the parameter only resolves with btype_id +
  event_id + param_id (the parameter KEY, not the internal id) + param_name together, with
  is_slidable: false on every expression node. Frozen as a golden fixture
  (tests/fixtures/expressions/api-event-parameter-golden.json), and bubble_editor_write now
  flags APIEventParameter nodes missing any of the four context fields with the exact fix.
- bubble_editor_write warns on hand-composed expression nodes in workflow actions (Orana report
  bug 8): expression encodings (APIEventParameter, Message chains, param ids) are not derivable
  from the .bubble export, and /appeditor/write returns HTTP 200 for any body — results now
  carry `warnings` steering agents to captured editor traffic (bubble_tool_wizard_start),
  add_action, or in-editor Copy/Paste. Tool descriptions and workflow routing notes state that
  a 200 from the endpoint is not success.
- Every created element gets %p.order = max(sibling)+1 stamped in the shared create queue when
  the tool did not set one — batch-created siblings used to tie at no order and render in
  reverse creation order.
- Icon values are validated: dashed library prefixes (ion-checkmark, feather-check) map to the
  canonical "<library> <name>" form, and unknown libraries fail with the accepted formats
  instead of writing a glyph the editor cannot render.
- Aria tool failures now carry a structured `error` field in the MCP result (extracted from the
  runtime failure line) instead of burying the reason in `logs` with a bare ok=false.
- Catalog-wide schema-vs-runtime contract snapshot test: every argument a tool schema
  advertises must reach the runtime (name, alias, or **kwargs). Known gaps for 124 tools are
  frozen in tests/fixtures/schema_runtime_contract_gaps.json; new drops and stale entries both
  fail, so the baseline can only shrink.
- create_shape sizes are honored: the dispatch fixed-size normalizer preferred the builder's
  legacy %w/%h default (100) over explicit min/max_width_css, silently rewriting a 19px dot to
  a 100px square. Explicit CSS lengths now win; %w/%h stay as the legacy fallback.
- create_group normalizes bg_style values (color -> bgcolor) instead of compiling an invalid
  %bas that the editor ignores (transparent group), and rejects junk values with a clear error.
- update_layout accepts the common element properties agents actually need: font_size, font_color,
  font_family, order, rotation_angle, opacity, background style/color (bgcolor), and border
  roundness — previously these failed silently as "unsupported layout property", forcing manual
  payloads. Color values resolve through the app color tokens; sizes/orders coerce from px strings.
- Crawler-only profiles work across the whole runtime: create_from_html no longer hard-requires a
  .bubble export (it falls back to the crawler-index primary source), and the aria dispatch layer
  resolves the profile's default crawler-index artifact automatically instead of requiring an
  explicit crawler_index_path argument on every call. Context-detection failures are non-fatal
  when a previously detected crawler index exists.
- create_reusable_instance now mirrors editor serialization (2026-08-24 Orana bug report #1-#3):
  %p.custom_id uses the definition's inner .id (never the element_definitions dict key), created
  elements get an element-level %nm write and a computed %p.order (max sibling order + 1) so they
  show up in the editor's Elements Tree, and a missing reusable name returns a clear structured
  error instead of a Python TypeError (`source` is now required in the schema and aliases to
  reusable_name). The %nm write applies to every create_* tool via the shared create queue.
- bubble_editor_write lints node bodies for decoded export keys (report #7): a body under
  %el/%wf/actions using type/properties instead of %x/%p is rejected with an explanation (the
  server accepts such nodes but the editor renders "[missing: null]"); allow_decoded_keys=true
  overrides.
- bubble_context_detect returns a compact response by default (report #6); include_details=true
  restores the full summary/attempt payloads.
- bubble_session_login reports the MCP venv's own Python path when Playwright browser binaries
  are missing (report #5), instead of a generic "playwright install" hint.
- PathDiscovery now uses the editor crawler-index as a PRIMARY data source when no .bubble
  export or consolelog is available (the .bubble export endpoint returns 401 on some plans).
  Crawler-only profiles previously failed every aria-runtime tool with "No app data source
  found" even though context detection had succeeded via the crawler.
- The anti-stale workflow guard in add_action/replace_action no longer discards workflows that
  were created via MCP and exist only in the local cache (created after the last .bubble
  download): cache rows newer than the root snapshot (15 min tolerance) are trusted instead of
  auto-creating a duplicate workflow. Cache rows older than the root (deleted/ghost refs) are
  still ignored. The decision lives in BubbleCLI._select_trusted_workflow_rows with unit tests.
- add_action honors the event_ref/event_type/ref_kind arguments its MCP schema always advertised
  (they were silently dropped by the dispatch layer): when given, it delegates to the existing
  add_event_action by-ref path, so actions can be appended to any existing workflow — including
  ConditionTrue, CustomEvent, and DoEvery — without element+event matching, duplicate auto-created
  workflows, or manual /appeditor/write payloads. `to` now aliases to `to_email`, and the
  unsupported query_result_type argument was removed from the add_action schema. A contract test
  guards schema-vs-runtime argument drift.
- Catalog: every exposed tool now has its own description (323 unique / 323 tools, was 194 unique
  with 13 workflow tools, 15 data tools, 41 metadata tools sharing one category blurb). Legacy
  boilerplate ("This is an Aria-compatible Bubble MCP tool. Use it when the user's intent matches...")
  was dropped; per-tool text lives in `server/tool_descriptions.py`.
- API Connector routing: `bubble_agent_guide`, `bubble_task_recipe`, `bubble_task_runbook`, and
  `bubble_tool_search` now route "API call / API Connector call / chamada de API" requests to the
  `create_api_connector_call` extension tool (new `manage_api_connector` route and `api_connector`
  recipe), report whether it is enabled, and explicitly steer away from `create_api_token`
  (Data API tokens) and visual element tools. The `create_api_call` language intent resolves to
  `create_api_connector_call`.
- Tool wizard: generated tool names are flat and MCP-client safe (`^[a-zA-Z0-9_-]{1,64}$`, no dots)
  so clients can expose them as direct callables; generated descriptions state the intent, family
  hint, arguments, and preview contract instead of "Generated candidate tool from session ...".
- API token tools state they manage Data API tokens, not API Connector calls.

## 0.1.0

- Bootstrap package metadata.
- Add local profile CLI.
- Add sensitive-source audit.
- Add minimal read-only MCP stdio server.
- Add compact context summary/search.
- Add deterministic dry-run planner and validator.
- Add basic HTML-to-Bubble dry-run converter.
- Add eval harness.
- Add local Figma bridge skeleton.
