# Savepoints and the deploy diff

Two capabilities, one shared discovery: Bubble's version control and node reads are both plain
HTTP endpoints usable with the stored session. Neither needs a browser.

1. **A return point before work starts.** The MCP creates a native Bubble savepoint before the
   first write of a session, so a session that went wrong can be rolled back.
2. **A deploy report.** Before deploying, show everything that differs between the deployed
   `live` version and the `test` version about to replace it.

Endpoints captured 2026-08-27 by driving the editor with Playwright and recording every
`/appeditor/*` call while a human created a savepoint and restored it. Raw requests are kept as
`docs/capture-version-control-*.json`.

| operation | endpoint | body |
|---|---|---|
| create savepoint | `POST /appeditor/commit_test_version` | `{appname, app_version, message, session_id}` |
| list savepoints | `POST /appeditor/get_restore_history` | `{appname, app_version}` |
| restore | `POST /appeditor/restore_to` | `{appname, app_version, timestamp}` |
| read nodes | `POST /appeditor/load_multiple_paths/<app>/<version>` | `{path_arrays, no_chunking}` |
| deploy needed? | `POST /appeditor/version_was_updated_since_last_deploy` | `{appname, app_version}` |

## Two facts that shape everything

**`restore_to` is whole-app time travel.** It takes a timestamp - the same epoch-ms value the path
API returns at `["last_change_date"]` - and reverts the entire `test` version to that instant,
including work after it that you wanted to keep. It is not "undo this edit". Any tool exposing it
must say so and must require explicit confirmation.

**Node reads do not need a browser.** `POST /appeditor/load_multiple_paths` returns nodes in the
ENCODED key space (`%p`, `%x`, `%ei`, `APIEventParameter`) - the same space
`read_live_node` reads through `window.appquery._raw()`. Verified against `api.bTGOS` on
`mcp-test-app`. `BubblePathApiClient` in `context/path_api.py` already wraps it, including the
`type: "hash"` chunk indirection, via `resolve_path`.

Two differences remain, and the second one is a trap.

The path API reads the SERVER's persisted state; the browser reads the editor's in-memory tree.
They diverge only while a human has unsynced changes in an open editor tab.

**The path API DROPS null-valued keys.** Measured after this spec was first written: the node at
`api.bTGOj` was written with `%n`, `optional` and `in_url` all null and reads back through the
path API without any of them. So it is a LOSSY read for anything that will be written back - a
clone sourced from it would silently delete every null-valued key and `/appeditor/write` would
answer 200. It is safe for a deploy diff only because both sides are read the same way, so the
loss is symmetric. Anything that rewrites a node must use `read_live_node`.

Because `live` answers the same endpoint, there is no local copy of live to maintain. The baseline
is read on demand. `live` changes only when someone deploys.

## Section 1 - the return point

New module `execution/version_control.py`, three thin functions shaped like `editor_api.py`
(`_load_session_for_profile`, `_resolve_app_id`, `dry_run=not execute`):

- `create_savepoint(profile, message, ...)` -> `commit_test_version`
- `list_restore_history(profile, ...)` -> `get_restore_history`
- `restore_to_timestamp(profile, timestamp, ..., confirm)` -> `restore_to`

Exposed as `bubble_savepoint_create`, `bubble_savepoint_list`, `bubble_savepoint_restore`.
`bubble_savepoint_restore` requires `confirm=true` on top of `execute=true`, matching
`bubble_branch_delete`, and its description states the whole-version blast radius.

**The automatic part.** A guard in `server/tools.py`, sibling to `_attach_write_verification` but
running BEFORE dispatch: on the first executed write of a session for a given profile+app, call
`commit_test_version` with a message describing the task. A marker file under
`<config>/savepoints/<profile>-<app>.json` records the editor session id, the savepoint timestamp,
and when it was taken. Later writes in the same session create nothing.

Session boundary: `process_session_id()`, one id minted once for the life of the MCP process.
`bubble_session_id()` mints a fresh timestamp-based id on every call, so keying the marker on it
would make every write look like a new session and take its own savepoint - the exact flooding
this design avoids. Plus an idle expiry measured from the LAST write that reused the savepoint,
not from when it was created, so a long stretch of steady work stays one session. Previews
(`execute=false`) touch nothing and get no savepoint.

A savepoint marks the start of a working session; it is not a precondition for each write. When
one cannot be taken, the failure is reported under `session_savepoint` and the work goes ahead - a
hiccup on `commit_test_version` must not stop an author from editing their own app. The agent can
also take an explicit one at any point with `bubble_savepoint_create` ("starting a new feature"),
which is the other half of how savepoints are meant to be used.

Granularity is deliberately one savepoint per session, not per edit. Per-edit savepoints would put
40 entries in the restore history for a 40-write session, making the history unreadable exactly
when it is needed. Per-edit undo is Section 2's job.

## Section 2 - the before-snapshot

`restore_to` is blunt. Undoing one edit needs the previous body of the paths that edit touched.

Before each executed write, read the pointers the payload will touch and store the result with the
mutation overlay entry as `before`. The pointers are already derivable: every change entry is
self-describing (`path_array` + `body`), and `write_verify._plan_change` already extracts them for
post-write verification. The read is one HTTP call through `BubblePathApiClient`, not a browser
launch, which is what makes this affordable at all.

This buys two things: a per-edit diff (what did this call actually change), and the raw material
for a fine-grained undo - rewrite the recorded `before` body at its path.

## Section 3 - the deploy report

`bubble_deploy_preview`: what differs between `live` and `test`.

Two sources for the path list, chosen by the caller, because they have different blind spots:

- `source="overlay"` (default) - the paths in the local mutation overlay since the last deploy.
  Precise and free. Blind to changes a human made directly in the editor.
- `source="full_scan"` - walk both versions through the path API and diff. Sees everything
  regardless of origin. Slow on a large app.

The agent asks the user which to use when the choice matters.

`bubble_changelog_fetch` would have been the ideal source - server-side, per-change, with paths -
but `/appeditor/fetch_changelog_entries` returns HTTP 200 with an empty list on `mcp-test-app`,
so it cannot be relied on. Not designed against.

For each path: read `live` (before) and `test` (after) through the path API and diff with
`raw_node_edit.all_divergences`, which names EVERY dotted path where two encoded nodes differ.
`first_divergence` is the wrong tool here: it stops at the first mismatch, which is enough to
answer "did this write land" but under-reports "what would this deploy change" - two edits under
one root would be shown as one.

A report also carries `complete`, true only for a full scan. An overlay-sourced report covers what
this MCP wrote and nothing else, so an empty result means "nothing was recorded", never "nothing
would change". `version_was_updated_since_last_deploy` answers the cheap precondition - whether there is
anything to report at all.

## Testing

The pure layer (path collection, diff shaping, savepoint marker lifecycle) is tested directly with
no network. The endpoint wrappers are tested through an injected client the way `editor_api.py`
tests already do, asserting the exact payload shape against the captured requests in
`docs/capture-version-control-*.json` - the same golden-test approach that pinned
`clone_workflow_changes` to real editor traffic.
