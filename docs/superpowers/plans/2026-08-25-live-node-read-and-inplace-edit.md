# Plan — Live raw node read and in-place workflow editing (Orana report bug 8)

**Date:** 2026-08-25
**Status:** proposed — step 1 needs a human logged into the Bubble editor
**Depends on:** the workflow-root merge fix (`fix/workflow-root-overlay-shadowing`), which is a
hard prerequisite: with the overlay root shadowing the export root, a reusable with 33 workflows
lists 1, so nothing downstream can even enumerate the action to edit.

## Problem

Editing an existing workflow action is unsupported today. The three shapes the Orana session
needed are all blocked:

- swap a Message token in an expression (`last item` -> `first item`);
- reorder steps in a workflow;
- retarget the source of a field inside an action.

Every existing tool (`add_action`, `replace_action`, `delete_action`) *composes* the action node
from scratch, and composition is exactly the path the report proved broken: four attempts, all
accepted with HTTP 200, all rendered differently broken in the editor. `/appeditor/write` performs
no semantic validation, so a 200 is not evidence of anything.

What landed so far are guardrails, not a fix: `lint_expression_warnings` warns on expression-bearing
bodies, `bubble_editor_write` rejects decoded node keys, and the canonical `APIEventParameter` form
is frozen in `tests/fixtures/expressions/api-event-parameter-golden.json`.

## Key insight

The 2026-08-24 night session established that the raw form is *readable* even though it is not
*derivable*. Reading a child node from the running editor returns the editor's own serialization:

```js
window.appquery.app().json._child('api')._child('<wf_id>').raw()
```

(`app.raw()` on the root is refused for performance reasons; child nodes fetch fine.)

That turns the whole problem from "reconstruct the encoding" into "read, patch one leaf, write
back". No encoder is needed, because nothing gets re-encoded — the bytes that were already correct
stay correct, and only the leaf under edit changes. It is the `delete + Ctrl+Z` workaround from bug 7
turned into an operation, without the human in the loop.

## Steps

### 1. `bubble_live_node_read(path)` — read-only

Wrap the appquery extraction behind Playwright and the stored session (`sessions/browser.py`
already drives Playwright and calls `page.evaluate`). Input: a raw path array
(`["%p3", "<page>", "%wf", "<wf>"]` or `["api", "<wf_id>"]`). Output: the node exactly as the editor
holds it, plus the path it was read from.

Constraints:

- read-only, never writes;
- requires a valid editor session — fail with the existing session-expired guidance, never silently
  fall back to the export, since falling back to the export is the bug;
- cache per (app, path, session) for the duration of one MCP call only.

This step needs a human logged into the editor at least once to validate against a known-good node
(the golden fixture is the assertion target).

### 2. In-place edit operations on top of step 1

Each operation is read -> patch -> write, and touches exactly one subtree:

- **`edit_action_expression`** — patch a leaf of the expression chain (Message `name`, operator,
  literal). Everything above and below the patched leaf is written back byte-identical.
- **`reorder_actions`** — actions are a `actions.<index>` map. Reordering rewrites the index keys and
  moves whole raw bodies verbatim; no interior is parsed, so no expression can be corrupted.
- **`retarget_action_field`** — replace one subtree, sourcing the replacement from the live raw of an
  action that already works, rather than composing it.

### 3. Round-trip verification gate

After any write produced by step 2: re-read the node through step 1 and diff against the intended
result. Report success only on a match. This replaces the current false-green — where HTTP 200 plus a
re-downloaded export "confirmed" a write the editor could not render, because the export decodes the
very layers that were wrong.

## Tests

- Step 1: unit tests with the Playwright page mocked at the `evaluate` boundary, asserting the path
  array to appquery expression mapping and the session-expired path; one live check against the
  golden fixture, run by hand when a human is in the editor.
- Step 2: fixture-driven — take the golden node, apply each operation, assert that every byte outside
  the patched subtree is unchanged. That invariant is the whole safety argument and deserves to be
  asserted directly.
- Step 3: assert that a mismatched re-read is reported as failure, not success.

## Explicitly out of scope

An export -> raw encoder. The report's three layers of decoding (node keys, param ids, message
tokens) make it unreliable, and step 1 removes the need for it. Golden samples stay what they are
today: content validation, never a source for deriving raw form.
