# Live Node Read and In-Place Edit Design

**Date:** 2026-08-26
**Status:** Approved. The encoding sections below — `node_keys.py`'s role, and the write
granularity / translation-point argument inside `node_edit.py` — the cycle — were rewritten from
measurement on 2026-08-26, after this design's original load-bearing claim (only the node ROOT
is translated; the interior travels verbatim) was tested against the live editor and found
wrong: the editor also encodes `entries`->`%e`, `next`->`%n`, `name`->`%nm`, and property names
such as `element_id`->`%ei`, well past the root. The corrected design reads and writes the node
in the SAME encoded form throughout (`_raw()`, not `raw()`), with no translation step at all.
Ground truth pair: `tests/fixtures/expressions/action-encoding-pair-golden.json`. See
`docs/session-findings-2026-08-26.md` for the measurements.

## Context

Editing an action inside an existing workflow is unsupported today. Every action tool
composes the node from scratch out of the `.bubble` export, and the export is a decoded
projection of what the editor actually stores: node keys, param ids, and Message tokens are
all translated on the way out, and `src/bubble_mcp/vendor/bubble_modules.py` only splits the export, so
there is no local map to invert. The Orana report measured the consequence — four composed
`ChangeThing` actions, all accepted with HTTP 200, all rendered `[missing: null]` in the
editor. `/appeditor/write` performs no semantic validation, so a 200 is not evidence of
anything.

`docs/session-findings-2026-08-24.md` recovered the canonical raw form by reading the
running editor's own memory through Playwright:
`window.appquery.app().json._child('api')._child('<wf_id>').raw()`. That read is the only
known source of truth for the raw encoding, and it is currently a manual procedure.

Commit `127203a` landed the pure layer for the other route — read, patch one leaf, write
back — as `src/bubble_mcp/execution/raw_node_edit.py`, deliberately unexposed: without a
live read, an edit tool could only operate on a node the agent assembled, which is the path
this work exists to replace. This design closes that gap and ships the tool surface.

## Goals

- Expose the live editor read as `bubble_live_node_read`, so the raw form of any node can be
  obtained on demand without a human in the editor and without the Chrome extension.
- Expose one in-place edit tool, `bubble_node_edit`, that performs the whole
  read → modify → write → re-read → compare cycle in a single call, with `execute=false` as
  the default.
- Make the re-read mandatory and structural: the tool reports where a write diverged from
  intent, never a bare success.
- Keep `raw_node_edit.py` internal; the two tools are the only new public surface.
- Cover the pure layers (key translation, script construction, orchestration) with tests that
  run in CI without a browser and without a Bubble session.

## Non-goals

- Reconstructing expression encodings from the export. This design exists because that is
  not possible; nothing here parses or rebuilds an expression interior.
- Editing elements (`%el`) or any node whose root carries a `name` key. v1 addresses
  workflow action nodes only; the ambiguous cases fail loudly rather than guess.
- Replacing `add_action`, `bubble_editor_write`, or the capture-based tool wizard. Those
  remain the paths for creating new actions.
- Deleting actions. `reorder` refuses an order that would drop a step precisely so deletion
  cannot arrive disguised as a reorder; a real delete stays out of scope.
- Running the browser read in CI. The default evaluator needs Playwright and a stored
  session; tests inject a fake.

## Chosen Architecture

Three new modules under `src/bubble_mcp/execution/`, each depending only downward. None of
them imports the server package.

### The read/write key space — no translation

`window.appquery` exposes each node in BOTH forms: `raw()` returns the DECODED form (`type`,
`properties`, `entries`, `next`, `name`, `element_id`, ...); `_raw()` returns the ENCODED form
(`%x`, `%p`, `%e`, `%n`, `%nm`, `%ei`, ...) that `/appeditor/write` itself expects. Measured
against live editor traffic (`tests/fixtures/expressions/action-encoding-pair-golden.json`),
`_raw()` is byte-identical to the body the editor's own writes POST. So there is no translation
step to design: `live_node_read.py` reads with `_raw()`, `node_edit.py` patches the leaf in
place without touching any key's spelling, and the same encoded bytes go straight back to
`/appeditor/write`.

This supersedes the original plan to translate node ROOT keys (`type`→`%x`, `properties`→`%p`,
`default_name`→`%dn`) while copying the interior verbatim. That plan assumed the interior stayed
decoded regardless of depth; measured, it does not — the editor also encodes `entries`→`%e`,
`next`→`%n`, `name`→`%nm`, and per-action-type property names such as `element_id`→`%ei`, well
past the root. A root-only translation therefore produced a body encoded at the root and
decoded everywhere else, which is exactly the shape that rendered `[missing: null]` or an
empty, "should be text but is empty" field when written to the live editor — see
`docs/session-findings-2026-08-26.md` §2 for the three failed attempts and the render evidence.

`src/bubble_mcp/execution/node_keys.py` still exists (`encode_node_root` / `decode_node_root`,
root-only translation) but is **not part of the live read/write path any more**. It stays useful
for the one case where a decoded-only form is unavoidable: a `.bubble` export, which only ever
carries the decoded projection Bubble's export step produces, never the encoded form. Anything
reading a node out of an export — not out of the live editor — still needs it.

### `live_node_read.py` — the read

- `build_appquery_script(pointer)` is pure: `["api", "<wf_id>"]` becomes a script that reads
  `window.appquery.app().json._child('api')._child('<wf_id>')` AND the app it came from, in
  one atomic evaluation: `() => { const root = window.appquery.app().json; const node =
  root._child('api')._child('<wf_id>'); return {appname: root.appname(), app_version:
  root.app_version(), node: node ? node.raw() : node}; }`. An empty pointer raises — `app.raw()`
  on the root is blocked by Bubble itself "for performance reasons". Pointer segments are
  JSON-escaped into the script. See "Identity is verified in the same evaluation as the read"
  below for why the identity is folded into this one script instead of a second `page.evaluate`.
- `read_live_node(profile, pointer, *, evaluator=None, app_id=None, headless=True,
  timeout_sec=...)` returns `{"ok": True, "pointer": [...], "node": {...}, "app_id": ...}` once
  it has confirmed the envelope's `appname`/`app_version` match what was requested; otherwise
  `{"ok": False, "error": "wrong_app", ...}` (see the Error Taxonomy).
- The default evaluator uses `playwright.sync_api.sync_playwright` with
  `launch_persistent_context(settings.config_dir / "browser-profiles" / profile)`, the same
  pattern already in production in `browser_automation/scheduled_deploy.py`. Readiness is
  gated on a functional probe — `Boolean(window.appquery && window.appquery.app &&
  window.appquery.app().json)` wrapped in a try/catch that returns `false` on error — not on
  `typeof window.appquery !== 'undefined'`. `window.appquery` is a getter that exists (so
  `typeof` reports `'function'`) well before it is usable; on the real editor `typeof` passes
  the wait while the getter still throws "The variable appquery is not fully initialized yet",
  and the very next `page.evaluate` of the read script throws that same error. The probe must
  call all the way through to `.json` so it stays `false` until the editor can actually serve
  it, and the try/catch is load-bearing: without it, the getter's exception propagates out of
  `wait_for_function` and fails the wait instead of letting it keep polling.
- **The context is seeded from the stored session's cookies, not from whatever the
  browser-profile directory already holds.** Root cause of the wrong-app read documented below:
  `_playwright_evaluator` used to trust the persistent-context directory's own cookies, and a
  directory can be partially authenticated — logged in to Bubble's own `meta` app in `live`
  without ever having a valid cookie for the requested app. Measured on this machine, the
  profile directory's bubble.io cookies were `_ga`, `_ga_BFPVR2DEE2`, `_tt_enable_cookie`,
  `ajs_user_id`, `meta-firebase_workflow`, `meta_live_u2main`, `meta_live_u2main.sig` — the
  stored session's `Cookie` header carried all of those plus `meta_u1main` and 20 others. That
  partial authentication is exactly why the editor served a *working* `meta` app instead of a
  login page: the `page.url` app-id check (below) never fires, because nothing about the load
  looks broken from that check's point of view. The fix: before `page.goto`, the evaluator
  loads the session via `load_session(profile)` (already used for `_resolve_app_id`), reads its
  `Cookie` header case-insensitively (`_session_cookie_header`), parses it with
  `parse_cookie_header` — split on `;`, trim whitespace, skip any fragment without `=`, split
  each fragment on the FIRST `=` only since signature cookies like `meta_live_u2main.sig`
  legitimately contain `=` inside the value — and adds the results via `context.add_cookies(...)`
  with `domain=".bubble.io"`, `path="/"`. Proof, same URL and profile, cookie injection the only
  variable: without it, `appname="mcp-test-app"` at t=0s degrades to `appname="meta"` at t=3s
  (`url` now `https://bubble.io/`); with it, `appname="mcp-test-app"`, `version="test"` holds
  unchanged through t=21s. A missing session, or one with no cookie header, is not raised here —
  navigation proceeds and the existing `not_logged_in` / `wrong_app` checks report it at the
  layer that already owns that message, rather than adding a second, competing one.
- After `page.goto`, the evaluator checks that the app id is still present in `page.url` before
  waiting on readiness. A profile directory that exists but never logged in (Chrome creates the
  directory shell on first launch, before any session cookie is written into it) gets
  redirected by bubble.io to its marketing page or a `/login`-ish path, and the app id drops
  out of the URL; this is the reliable, cheap signal, since the alternative failures
  (`evaluator_failed` for "Execution context was destroyed, most likely because of a
  navigation", or the getter error above at `https://bubble.io/` instead of the editor URL)
  read like unrelated bugs. A mismatch raises `NotLoggedIn`, reported as `not_logged_in`. This
  check is necessary but not sufficient: it only catches a profile with *no* valid cookie for
  any app, not one (see above) with a valid cookie for the *wrong* app, which keeps `app_id` out
  of the URL entirely and reads as a normal-looking load.
- **Identity is verified in the same evaluation as the read, to close the redirect race.**
  Measured on the live editor, the requested app is not stable: it loads correctly, then the
  page redirects to `https://bubble.io/` on a timer.
  ```
  t= 0s  url=https://bubble.io/page?id=mcp-test-app&...   appname="mcp-test-app"  version="test"
  t= 3s  url=https://bubble.io/                            appname="meta"          version="live"
  ```
  At `https://bubble.io/`, `window.appquery` serves Bubble's own internal `meta` app, not the
  requested one. Both readiness gates can pass while the correct app is still loaded — they say
  nothing about which app answers by the time the read script actually runs — so a check placed
  before or after the read, as a second `page.evaluate`, would still leave a window for the
  redirect to land in between the two calls; it narrows the race instead of closing it. This is
  why `build_appquery_script` reads `root.appname()` and `root.app_version()` in the exact same
  expression that produces `node.raw()`: one JS call is atomic with respect to the redirect, two
  calls are not. `read_live_node` compares the envelope's `appname`/`app_version` against the
  app and version it was asked for and only unwraps `node` when both match; a mismatch is
  reported as `{"ok": False, "error": "wrong_app", ...}` (`WrongApp` in the raising path), naming
  both the expected and the actual app/version, and calling out that `meta` specifically means
  the editor navigated away to Bubble's own dashboard. **A false `verified: true` was actually
  produced this way before this check existed:** an edit ran with the correct `appname` in the
  write payload, but the pre-write read and the post-write re-read had both landed after the
  redirect, so the comparison was decoded-`meta`-tree to decoded-`meta`-tree and reported
  `verified: true` for a write that had never actually been checked against the target app —
  the exact failure this design promises never to produce, so the check stays.
- **The readiness gate is app-aware too, not just tree-aware.** `build_pointer_ready_script`
  takes the expected `app_id` as a parameter and returns `false` (not ready) when
  `root.appname()` does not match it, before even attempting to walk the pointer. Without this,
  the retry loop would happily settle for a subtree that is perfectly "ready" — just in the
  wrong app, since the `meta` app's own tree loads and answers normally once the redirect has
  happened.
- **A wrong-app identity mismatch is treated as transient for retry purposes.** `WrongApp`'s
  message is matched by `is_transient_editor_error` (via the `"navigated away"` marker), so
  the bounded 3-attempt loop in `_playwright_evaluator` gives the read another chance rather
  than failing on the first mismatch. If every attempt still reads the wrong app, the evaluator
  raises `WrongApp` itself rather than folding it into `EditorUnstable` — `read_live_node` must
  still surface `wrong_app` specifically, because that names the real problem, and an
  undifferentiated `editor_unstable` is not actionable in the same way.
- The evaluator is a parameter so tests supply a fake and never launch a browser.
- The editor's app tree loads lazily and progressively: `window.appquery` answering says
  nothing about whether any particular subtree has arrived. Measured on the live editor, the
  same pointer's `._child_names()` threw `NotReadyError` right after the appquery gate passed
  (Workflow-tab load) and then worked once the Design tab had loaded. So readiness is
  pointer-scoped, not app-wide: the wait is two-stage. First, the cheap app-wide gate —
  `APPQUERY_READY_SCRIPT` — must pass, since it is what makes the pointer walk possible at
  all. Second, `build_pointer_ready_script(pointer)` walks the same chain the read itself will
  walk (one `._child(...)` per segment, calling `ensure_loading()` on each node it passes
  through when that method exists) and reports whether the pointer's own `raw()` can be called
  yet; `_playwright_evaluator` waits on this second script, after the appquery wait and before
  evaluating the read script. `raw()` returning `undefined` still counts as ready — an absent
  node is `pointer_not_found`, the read's business to report, not something to wait for.
  Detecting `NotReadyError` is structural, not textual. Measured on the live editor, the
  thrown object is **not an `Error`**: `error.name` and `error.message` are both `null`,
  `error instanceof Error` is `false`, and `String(error)` is `"[object Object]"`; the
  `console.error`-visible fields are `constructor.name === "NotReadyError"` and an own key
  `not_ready_key` (alongside `suppress_dependency_error` and `stack`). A first version of this
  gate matched on `error.name === 'NotReadyError'` or `message` containing `NotReady`, which
  can never fire against that shape — every NotReadyError read as "some other error", the gate
  returned `true` immediately, and the tool proceeded to read a subtree that had not loaded.
  The catch therefore checks `'not_ready_key' in error` first (an own data field the editor
  sets deliberately, stable) and falls back to `error.constructor.name === 'NotReadyError'`
  (a class name, and so the one a future minifier pass could rename). Any other error returns
  `true`, so a genuinely broken pointer surfaces its real error from the read instead of
  hanging until the timeout. If the pointer's subtree never reports ready in time, the
  evaluator raises `PointerNotReady`, reported as `pointer_not_ready` — distinct from
  `editor_not_ready` (the editor is up) and from `pointer_not_found` (something was actually
  read and was absent).
- **Readiness is not a single moment: the editor page reloads underneath the session.** Two
  consecutive live runs a minute apart reported different `run_js` bundle hashes
  (`806773c5…` then `f57b23ef…`), proving the page had reinitialized in between. Both
  readiness gates passing once is therefore not proof they still hold by the time
  `page.evaluate(script)` actually runs — the page can regress past them in the gap. Measured
  live, consecutive identical reads of the same valid pointer gave `evaluator_failed` on
  attempt 1 and the correct node on attempt 2, both errors thrown by `appquery.app()` itself
  or by the page navigating out from under the evaluate, *after* both gates had already
  passed. The two observed transient messages, verbatim:
  ```
  UnexpectedError: Missing Lib!
      at Lib.or_throw (https://bubble.io/package/run_js/<hash>/xfalse/x30/run.js:50:5782)
      at appquery.<computed> [as app] (.../run.js:136:134238)
  ```
  ```
  Execution context was destroyed, most likely because of a navigation
  ```
  `is_transient_editor_error(message)` classifies a failure text as one of these
  reinitialization symptoms via a case-insensitive substring test against a fixed tuple of
  markers (`Missing Lib`, `Execution context was destroyed`, `NotReadyError`, `not fully
  initialized`); it does not match an ordinary failure (a `TypeError`, a pointer problem, an
  empty string). `_playwright_evaluator` wraps the whole per-attempt sequence — wait on
  `APPQUERY_READY_SCRIPT`, wait on the pointer-ready script, then `page.evaluate(script)` — in
  a bounded loop of up to 3 attempts, reusing the same browser context and page throughout
  (never relaunching the browser). On a transient failure it sleeps about a second and retries
  the FULL sequence, re-waiting both gates rather than just re-evaluating, since the page — not
  just the read — is what regressed. A non-transient failure raises immediately without
  burning further attempts. When all attempts are exhausted on transient errors, the evaluator
  raises `EditorUnstable` (carrying the attempt count and the last underlying message),
  reported as `editor_unstable` — distinct from `evaluator_failed` in that it names the actual,
  actionable cause (the editor page kept reinitializing) instead of surfacing whatever
  transient JS error happened to be current on the final attempt. This retry lives entirely
  inside `_playwright_evaluator`; the injected `Evaluator` type is unchanged (still a callable
  taking the single read script), so tests that supply a fake evaluator never exercise the
  retry loop and continue to work untouched.
- Pointers must be derived from the *live* tree, via `_child_names()` on the loaded nodes, not
  from the cached crawler index. Measured against this app, the cached `idToPath` named
  `%p3.AAW.%wf.bTHDJ`, while the live `%p3` had an entirely different id set with no `AAW` at
  all. A stale pointer built from the cache reads as `pointer_not_found`, which is a correct
  result but easy to misread as a tool failure rather than as "the pointer was wrong".

### `node_edit.py` — the cycle

`edit_live_node(...)` runs five steps:

1. read the node at `pointer`, in the encoded key space (`_raw()` — see above);
2. apply exactly one operation, delegating to the untouched primitives in `raw_node_edit.py`
   — `patch_expression_leaf` for `patch`, `reorder_actions` for `reorder` — directly on the
   encoded node, since neither primitive inspects or depends on how a key is spelled;
3. build the `changes` entries, intent `SetData`, matching the shape
   `PayloadBuilder.add_change` already produces, with the body being the patched node exactly
   as it now stands — no encode step;
4. `BubbleEditorClient().write(payload, session, dry_run=not execute)`;
5. when `execute` is true, re-read the same pointer and call `first_divergence(intended,
   actual)`.

**The write granularity is the whole node at `pointer`, never the patched leaf.** Writing the
leaf directly would put an expression interior in the body at a path containing `actions`,
which `_is_node_position` classifies as a node position, so `lint_editor_write_changes` would
reject it — correctly by its own rules, and wrongly for this case, since that interior is a
legitimate part of a node body, not free-floating decoded content. Sending the whole node also
keeps the write and the re-read comparison in the same, single key space with nothing
transforming the body in between. For `patch`, `pointer` therefore addresses the action node
(`["api", "<wf_id>", "actions", "3"]`) and `leaf_pointer` is relative to it. For `reorder`,
`pointer` addresses the actions map (`["api", "<wf_id>", "actions"]`) and every action body in
that map is written back exactly as read.

**A container pointer is refused for `patch`, and every written body is walked.** `patch`
resolves `leaf_pointer` against a single node's own fields; a `pointer` that addresses a
container instead — the actions map `["api", "<wf>", "actions"]`, or a workflow root
`["api", "<wf>"]` whose own `actions` holds several sibling nodes — does not name one node to
patch. Two defences, kept from the original design because they catch different callers, not
because either still proves a translation ran:

- `_apply` refuses `op == "patch"` unless the node it read is a node (`type` or `%x` at its
  root), raising `patch requires a pointer to a node, not a container`.
- `_assert_encoded_node_roots` walks every assembled change body before it is sent, from
  both `build_patch_changes` and `build_reorder_changes`, descending only through the
  container keys `actions` / `%el` / `%wf`, and refuses any dict carrying `type` or
  `properties` without `%x` or `%p`. Its role changed with this rewrite: it used to prove that
  `encode_node_root` had run; now nothing here translates anything, so a node reaching this
  guard already decoded means a caller built it from somewhere other than a live read — most
  plausibly a `.bubble` export, which only ever carries the decoded form (see `node_keys.py`
  above). It never descends into a node's `%p`, because the expression interior can
  legitimately contain decoded-looking keys and is the one part nothing here may inspect.

These two catch different halves of the container-pointer case: the actions map has no root
`type`/`%x`, so `_apply`'s root-type check catches a `patch` aimed at it directly. A workflow
root does have one, so it passes that check; it is the recursive `_assert_encoded_node_roots`
guard, descending into `actions`, that catches the WORKFLOW-root case instead.

`lint_editor_write_changes` cannot stand in for either: it is path-shaped, and
`_is_node_position(["api", "<wf>", "actions"])` is false, so the whole container write passes
it unexamined.

**A reorder also rewrites the index.** Renumbering moves each action to a new path while
`_index.id_to_path` still points at the old one. Alongside the `SetData` change, `reorder`
emits one `Update index` change per action — `path_array` `["_index", "id_to_path",
"<action_id>"]`, body the dotted new path (`"api.<wf_id>.actions.1"`) — the same pairing
`bubble_cli` already uses when it writes an action. An action with no `id` raises: skipping
its index entry silently would leave `_index.id_to_path` pointing at whatever now occupies
its old position, which is the same class of quiet damage `reorder_actions` refuses when an
order would drop a step.

**The comparison lives in the same encoded key space as the write, and that is fine.** The
original design compared in the decoded key space specifically to avoid measuring an encoding
step with the ruler it produced: if the write body were derived from the compared value by a
translation, an error in that translation could cancel itself out in the comparison and certify
a broken node. That risk is gone because its cause is gone — there is no translation between
"what gets written" and "what gets compared" any more; the write body IS the node,
byte-for-byte, and the re-read comes back in that same form. Comparing intended-encoded to
actual-encoded is therefore not the self-confirming case the original design warned against; it
is the same check, just with no transformation in the middle for a bug to hide behind.

## Tool Surface

### `bubble_live_node_read`

| arg | required | meaning |
|---|---|---|
| `profile` | yes | stored profile whose session and browser profile are used |
| `pointer` | yes | array of child keys from the app tree root, e.g. `["api", "<wf_id>"]` |
| `app_id` | no | overrides the profile's app id |
| `headless` | no | default `true` |
| `read_timeout_sec` | no | editor-ready and evaluate timeout |

Returns `{ok, pointer, node, app_id, read_at}`. Read-only: `readOnlyHint` true,
`openWorldHint` true (it drives a browser).

### `bubble_node_edit`

| arg | required | meaning |
|---|---|---|
| `profile` | yes | as above |
| `pointer` | yes | for `patch`, the action node; for `reorder`, the actions map holding it |
| `op` | yes | `"patch"` or `"reorder"` |
| `leaf_pointer` | for `patch` | address of the dict to patch, relative to the node |
| `patch` | for `patch` | object merged into that dict; a value may be a whole subtree |
| `order` | for `reorder` | every existing action key, exactly once, in the new order |
| `execute` | no | default `false` — previews the write and stops |
| `app_id` | no | as above |

Returns `{ok, execute, verified, render_unverified, verified_meaning, divergence, pointer,
before, intended, write, after}`. `verified` is only `true` after a successful re-read whose
`first_divergence` is `None`; with `execute=false` it is absent, never `true`. A failed
re-read reports the read result under `after_read`, never under `after`, which always holds
the node itself.

**`verified: true` is a byte check, not a render check.** `/appeditor/write` stores any body
and `.raw()` returns what is stored, so a body whose interior was wrongly decoded round-trips
byte-identically and `first_divergence` returns `None`. Every executed result therefore also
carries `render_unverified: true` and a `verified_meaning` string saying so; only step 4 of
Manual Validation clears it. Reporting `verified: true` alone would be exactly the bare
success this design promised never to report. Destructive-ish: `readOnlyHint` false,
`openWorldHint` true, and it joins the write-annotated set in `agent_catalog.py`.

A false `verified: true` was not a hypothetical risk: before the same-evaluation identity
check existed, an edit ran with the correct `appname` in the write payload while both the
pre-write read and the post-write re-read had landed after the editor's redirect to
`https://bubble.io/`, so the comparison was decoded-`meta`-tree to decoded-`meta`-tree and
came back `verified: true` for a write that had never been checked against the target app at
all — see "Identity is verified in the same evaluation as the read" above. That is the
strongest argument for keeping the check: it is not a defense against a theoretical failure
mode, it is a fix for one already observed.

`app_version` is threaded through both reads and into the write payload. Without it the read
would hard-default to `?version=test` while the write went to the session's version, so a
branch-configured profile would read `test`, write the branch, and verify against `test`.

## Error Taxonomy

Every failure is a structured result, not a stack trace:

| condition | signal |
|---|---|
| Playwright not installed | `ok: false`, `error: "playwright_missing"`, with the `pip install "befree-bubble-mcp[browser]"` instruction already used by scheduled deploy |
| no stored session for profile | `ValueError`, matching `bubble_editor_write` |
| profile has no `browser-profiles/<profile>` directory at all | `ok: false`, `error: "browser_profile_missing"`, naming `bubble_session_login`. A session stored by `bubble_session_import` is valid for writes but never creates this directory; without the check, Playwright creates an empty one, loads a logged-out bubble.io, and fails 90s later as `editor_not_ready`. This check only covers an absent directory — it does not detect a directory that exists but was never logged in |
| profile directory exists but never logged in (no session cookie; the editor URL redirects off the app id) | `ok: false`, `error: "not_logged_in"`, naming `bubble_session_login` and the profile |
| editor never becomes ready | `ok: false`, `error: "editor_not_ready"` |
| pointer's subtree never finishes loading within the timeout (a valid pointer, but that part of the tree has not arrived — the editor loads lazily and progressively) | `ok: false`, `error: "pointer_not_ready"`, naming the pointer and the timeout, saying the subtree never finished loading |
| the editor page kept reinitializing across every retry attempt (it reloads underneath the session — see above — and every attempt still hit a transient error such as `Missing Lib` or a destroyed execution context) | `ok: false`, `error: "editor_unstable"`, naming the attempt count and the last underlying message, saying the editor page kept reinitializing |
| the tree read back belongs to a different app or version than requested (the editor page redirected away — most commonly to `https://bubble.io/`, where `window.appquery` serves Bubble's own internal `meta` app instead) | `ok: false`, `error: "wrong_app"`, naming both the expected and the actual app id/version and, when the actual app is `meta`, saying the editor navigated away to Bubble's own dashboard |
| pointer does not resolve in the live tree | `ok: false`, `error: "pointer_not_found"`, naming the deepest segment that did resolve |
| `leaf_pointer` addresses a missing key | `KeyError` from `patch_expression_leaf` — creating the key is how a node ends up rendering `[missing: null]` |
| `order` drops or invents an action | `ValueError` from `reorder_actions` |
| node root carries `name` (or `%nm` on decode) | `ValueError` from `encode_node_root` / `decode_node_root`, checked before the already-encoded passthrough |
| node root mixes decoded and encoded members of the mapping | `ValueError` from `encode_node_root` / `decode_node_root`: a half-translated root is either an uncovered node shape or a hand-assembled body |
| `patch` pointer addresses a container | `ok: false`, `error: "invalid_edit"`, `patch requires a pointer to a node, not a container` |
| any body carries an untranslated node root | `ok: false`, `error: "invalid_edit"`, naming the dotted position inside the body |
| `read_timeout_sec` is not numeric | `ok: false`, `error: "invalid_read_timeout_sec"` |
| write returns 401/403 | the existing `auth_blocked` result from `BubbleEditorClient.write` |
| re-read differs from intent | `ok: true`, `verified: false`, `divergence: "<dotted.path>"` |

## Testing

Automated, in CI, with no browser and no Bubble session:

- `node_keys`: root-only translation; interior left byte-identical (asserted against
  `tests/fixtures/expressions/api-event-parameter-golden.json`, a real editor capture);
  `encode`/`decode` round trip; `ValueError` on a root `name`.
- `live_node_read`: `build_appquery_script` output for a nested pointer; refusal of an empty
  pointer; segment escaping.
- `node_edit`: the full cycle against a fake evaluator and a fake write transport — one case
  where the re-read matches (`verified: true`), and one where the fake write drops a byte,
  asserting the exact dotted path in `divergence` rather than merely that it failed;
  `execute=false` produces a preview and performs no re-read.
- `reorder` through the tool: the refusal that would drop a step, and the `Update index`
  change emitted per action with its new dotted path.
- the container-pointer hazard: a `patch` at the actions map and at a workflow root are both
  refused, the recursive guard refuses a decoded action nested under an encoded node, and the
  guard leaves an expression interior spelled `"type": "APIEventParameter"` alone.
- `app_version` reaches both reads and `payload["app_version"]`; an executed result carries
  `render_unverified`; a preview carries neither `verified` nor `render_unverified`.
- `browser_profile_missing` is returned before any browser is launched.
- `APPQUERY_READY_SCRIPT` is asserted, as text, to be a functional probe with a try/catch and
  to not use the bare `typeof window.appquery !== 'undefined'` form — pinning the regression
  where that race passed the readiness gate before `appquery` was actually usable.
- `not_logged_in`, raised by a fake evaluator, comes back as `{"ok": False, "error":
  "not_logged_in", ...}` with a message naming `bubble_session_login` and the profile.
- Existing `tests/unit/test_raw_node_edit.py` is untouched.

This machine has 14 unit tests that fail on Windows regardless of this change
(symlink/chmod/path separator/routing count). Verification compares against the pre-change
baseline on the same machine, not an absolute pass count.

## Manual Validation

Against profile `mcp-test` (`mcp-test-app`) only — never `orana` (`~/.bubble-mcp`) and never
`auto-on`:

1. `bubble_live_node_read` on a workflow that already exists and works; keep the raw node.
2. `bubble_node_edit` with `execute=false`, confirm the previewed payload.
3. Re-run with `execute=true` on one small, reversible change; the tool re-reads and reports
   `verified`.
4. A human opens the Bubble editor and confirms the step renders correctly.

Step 4 cannot be automated and cannot be skipped: identical bytes can still render broken,
and that is the exact failure class this work exists to eliminate. A failure at step 4
invalidates the encoding contract in `node_keys.py`, which is cheaper to learn now than
after the tools ship.

## Registration Checklist

- `server/schema_families.py`: new `FIELD_LIBRARY` entries (`pointer`, `leaf_pointer`,
  `patch`, `order`, `op`, `headless`, `read_timeout_sec`) and two `tool_schema` entries.
- `server/tools.py`: two handlers alongside the `bubble_editor_write` branch. The edit handler
  records a mutation overlay after a successful executed write, exactly as `bubble_editor_write`
  does, so `bubble_context_summary` does not keep serving pre-edit state. The overlay call stays
  in the server layer; `node_edit.py` must not import the context package.
- `server/tool_descriptions.py` and `server/agent_catalog.py`: descriptions, plus
  `bubble_node_edit` in the write-annotated and `openWorldHint` sets.
- `runtime_coverage.py`: both names in `NATIVE_SPECIAL_TOOLS`.
- `server/agent_guide.py`: point the workflow-editing note at `bubble_node_edit` for editing
  an existing action, keeping `add_action` for creating one.

## Risks

- **The encoding contract is unproven.** Root-only translation is inferred from one capture
  and one lint. Step 4 of manual validation is the only thing that confirms it.
- **Browser cost per read.** Each `bubble_live_node_read` launches a persistent context.
  Acceptable for an edit workflow; a session-reuse cache is deliberately deferred until
  there is evidence the cost matters.
- **Editor internals are unversioned.** `window.appquery` is Bubble's private surface and can
  change without notice. The failure is loud (`editor_not_ready` / `pointer_not_found`), not
  silent.
