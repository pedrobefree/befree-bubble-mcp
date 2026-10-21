# Captured: how the Bubble editor duplicates a workflow

Captured 2026-08-27 against `mcp-test-app` (version `test`) by driving the editor with
Playwright on the persistent browser profile `mcp-test` and recording every
`POST https://bubble.io/appeditor/write` while the user duplicated workflows by hand.

Four duplications were captured:

| case | what | file |
|------|------|------|
| A | page workflow, `ButtonClicked` -> `ShowElement`, no expressions | `capture-duplicate-workflow-simple.json` |
| B | page workflow, `LogIn` (email/password bound to element data) + `ChangePage` | `capture-duplicate-workflow-expression.json` |
| C | backend workflow (`api` root), `NewThing` with a text expression | `capture-duplicate-workflow-backend.json` |
| D | backend workflow that triggers a custom event **passing a parameter** | `capture-duplicate-workflow-custom-event.json` |

Case D's source workflow was built in the same editor session, so its pre-duplication state was
captured too (`capture-duplicate-workflow-custom-event-source.json`). That gives an exact
source-vs-copy diff, which is what pins down the remapping rule below.

## The rule

**The editor does not recompose the workflow. It deep-copies the raw node body and applies one
id mapping recursively over the whole thing - expressions included.**

The mapping contains exactly:

- the event's own `id` -> a new id
- each action's `id` -> a new id

Nothing else. Every other id in the body is a reference to something *outside* the node and is
carried over untouched.

This is decisive for tooling. Paired with `bubble_live_node_read`, which returns the node in its
encoded form, a `clone_workflow` derives *nothing*: the expression encoding that is not derivable
from the `.bubble` export never has to be derived, only walked and id-substituted.

### Expressions are not opaque blobs

An earlier reading of cases A-C suggested expressions could be copied verbatim. Case D disproves
it. The `TriggerCustomEvent` argument holds an `APIEventParameter` expression whose `%p.event_id`
is a **back-reference to the enclosing workflow's own event id** - and the editor rewrote it:

| field | source (`api.bTGOS`) | copy (`api.bTGOj`) | |
|-------|----------------------|--------------------|---|
| slot key | `bTGOS` | `bTGOj` | new |
| `body.id` (event) | `bTGOQ` | `bTGOd` | **remapped** |
| action `id` | `bTGOX` | `bTGOi` | **remapped** |
| `%p.parameters.0.param_id` | `bTGOc` | `bTGOc` | preserved |
| `%p.custom_event` | `bTGNt` | `bTGNt` | preserved |
| `arguments.0.param_id` | `bTGOA` | `bTGOA` | preserved |
| `arg_value.%p.event_id` | `bTGOQ` | **`bTGOd`** | **remapped** |

So the substitution must walk into every expression subtree, not stop at the action boundary.

Do not confuse the two `param_id` fields sitting next to each other: `arguments.0.param_id` is an
**id** (a parameter of the *target* custom event), while `arg_value.%p.param_id` is
`"Parameter 1"` - a **name**, matching `param_name`.

Note also that the workflow's own parameter definition id (`%p.parameters.0.param_id`) is
**preserved**, not regenerated. The copy shares it with the source.

## Envelope

One POST does the whole duplication, atomically. Top level:

```json
{"appname": "mcp-test-app", "app_version": "test", "v": 1, "changes": [ ... ]}
```

Every change except the `id_counter` one carries:

```json
{"version_control_api_version": 4, "changelog_data": [], "session_id": "<editor session>"}
```

`session_id` is constant for the whole editor session. `intent.id` is a per-session sequential
counter. `intent.source_appname` is `""`.

## Change order

The index entries are written **before** the node, not after:

| # | intent | path_array | body |
|---|--------|------------|------|
| 1 | `Update index` | `_index.id_to_path.<new_event_id>` | dotted path to the new slot |
| 2..n | `Update index` | `_index.id_to_path.<new_action_id>` | dotted path `....actions.<k>` |
| n+1 | `CreateEvent` | the new slot path | the node body |
| n+2 | `Update index` | `_index.issues_list.<object_id>` | JSON **string**; only when there is an issue |
| n+3 | `Update index` | `_index.issues_sub.<sub_id>` | JSON **string** list of ids, new id appended |
| last | (no `path_array`, no `intent`) | - | `{"type": "id_counter", "value": <n>}` |

One `id_to_path` entry per regenerated id, and only for regenerated ids - the preserved parameter
id gets none.

## Page root vs backend root

| | page workflow (A, B) | backend workflow (C, D) |
|---|---|---|
| node path | `["%p3", "<page>", "%wf", "<slot>"]` | `["api", "<slot>"]` |
| `id_to_path` body | `"%p3.<page>.%wf.<slot>"` | `"api.<slot>"` |
| `%x` | the event type, e.g. `ButtonClicked` | `APIEvent` |
| name | none - identified by trigger | `%p.wf_name`, and the editor appends `_copy` |

Case C produced `"wf_name": "teste_copy"` and case D `"wf_name": "test custom_copy"`. A
`clone_workflow` has to generate a non-colliding name for the backend case; the page case has no
name to collide.

## The slot key is not the node id

In case A the path slot is `bTGNC` but `body.id` is `bTGMw`, and the `id_to_path` entry is keyed
by the **id** with a value naming the **slot**. Case C repeats it: slot `bTGNo`, id `bTGNi`. The
same split holds per action - the actions map key is `"0"`, the action carries its own `id`, and
that id gets its own `id_to_path` entry.

This is independent confirmation of the key-vs-id defect the branch fixed in `afa40ae` and
`a2b7892`: the editor itself keeps the two apart everywhere.

## What is carried over untouched

Case B's node body:

```json
{"%p": {"%ei": "bVoQt"}, "%x": "ButtonClicked", "id": "bTGNE",
 "actions": {
   "0": {"%x": "LogIn", "id": "bTGNJ",
         "%p": {"%em": {"%n": {"%x": "Message", "%nm": "get_data", "is_slidable": false},
                        "%p": {"%ei": "btTmX"}, "%x": "GetElement", "is_slidable": false},
                "%pw": {"%n": {"%x": "Message", "%nm": "get_data", "is_slidable": false},
                        "%p": {"%ei": "b0sDN"}, "%x": "GetElement", "is_slidable": false},
                "stay_logged_in": true}},
   "1": {"%p": {"%ei": "bq8bK"}, "%x": "ChangePage", "id": "bTGNK"}}}
```

The `%ei` element references nested inside the expressions (`btTmX`, `b0sDN`) point at elements
that already exist on the page, so they are not in the mapping and must not be rewritten. The
event's own trigger ref (`%p.%ei`) is likewise carried over - the duplicate fires on the same
element as the original.

## The two conditional indexes

Neither is mandatory. Cases A and C wrote neither; B and D's source wrote them.

- `_index.issues_list.<object_id>` - keyed by whatever object carries the issue, **not always the
  event**. Case B keyed it by the event id (`bTGNE`, body `"[{\"cross_page\":\"bTGNK\"}]"`); a
  capture from case D's build keyed it by an action id (`bTGOX`, body `"[]"`). When the source has
  issues, the entries have to be remapped through the same id mapping as the node.
- `_index.issues_sub.<sub_id>` - a JSON string holding a list of ids, read-modify-written. Case A
  produced `["b3eD6","b2MHp","b0pRF","bTGMw","bO4rF"]`; case B then produced
  `["b3eD6","b2MHp","b0pRF","bTGMw","bTGNE","bO4rF"]` - A's id still present, B's inserted in
  place. Not a fresh value.

Both bodies are JSON **strings**, not objects.

## `id_counter`

The last change has no `path_array` and no `intent`; it is `{"type": "id_counter", "value": <n>}`.
Observed values: 10000060, 10000072, 10000084 (run 1), then 10000114 and 10000156 (run 2). The
12-id gaps in run 1 were an artifact of two duplications happening back to back with nothing in
between; run 2's gap of 42 spans the user's other edits. The value is the app-wide counter at
write time, so read it and echo it forward - do not compute it from how many ids the clone needs.

## What was built from this

`bubble_clone_workflow` (`clone_live_workflow` in `execution/node_edit.py`, pure layer in
`execution/raw_node_edit.py`) implements the shape above:

1. Read the source node raw - `["%p3","<page>","%wf","<slot>"]` for a page workflow,
   `["api","<slot>"]` for a backend one.
2. `workflow_id_mapping` mints a new event id and one new action id per action, and covers
   nothing else.
3. `remap_node_ids` deep-copies the body and applies the mapping **recursively over every
   value**, expression subtrees included. Ids not in the mapping stay as they are.
4. `wf_name` renames the copy for the backend case; a page workflow has no name.
5. `clone_workflow_changes` emits `id_to_path` entries first, then `CreateEvent`, then
   `id_counter` when one is known.
6. The copy is read back at its new pointer and compared to the intent, since
   `/appeditor/write` answers 200 either way.

`bubble_node_edit` could not express this - its `SUPPORTED_OPS` are `("patch", "reorder")`.

The golden test `test_clone_workflow_changes_matches_the_change_list_the_editor_sent` asserts the
emitted change list is byte-equal to case D's captured request.

Two gaps carried over from the captures rather than solved:

- `issues_list` / `issues_sub` are not emitted. Neither appeared in cases A or C, and reproducing
  `issues_sub` means read-modify-writing a list this code cannot currently read. A clone of a
  workflow whose source has issues will therefore not carry the issue entries.
- `id_counter` is a parameter, not something read from the editor. Left out when the caller does
  not supply it, on the grounds that inventing a counter value is worse than leaving it alone.

Not captured: duplicating a page workflow that carries custom-event parameters (D covers the
backend root only), and duplicating a workflow whose actions reference a reusable element's custom
events.

## The path API drops null-valued keys

Measured 2026-08-27, after this document was first written.

The copy in case D was written with `%n`, `optional` and `in_url` all null - they are in the
captured request. Reading that same node back through
`POST /appeditor/load_multiple_paths` returns it WITHOUT any of them:

```
copy read back - arg_value keys: ['%p', '%x', 'is_slidable']       # written with '%n' too
copy read back - %p keys        : ['btype_id', 'event_id', 'param_id', 'param_name']
                                                                    # written with optional, in_url too
```

So the path API is a lossy read for anything that will be written back. A clone sourced from it
would silently delete every null-valued key, and `/appeditor/write` would answer 200.

Use `read_live_node` - the editor's own `_raw()` through the browser - whenever the node is going
to be rewritten. `read_nodes_over_http` in `execution/deploy_preview.py` carries
`for_rewrite = False` to mark the contract, and it is safe there only because a deploy diff reads
both sides the same way, so the loss is symmetric.

Unverified: whether `read_live_node` itself preserves the null-valued keys. The write payloads
prove they exist on the server; nothing here proves how the browser read returns them.

## Why the clone does not emit `id_counter`

A second app's session measured the counter's behaviour precisely
(`a second app's capture report, 2026-08-27`, section 1.2): it is proposed by the client and
echoed by the server without correction, and it advances six units per object created.

That is a description of the EDITOR minting ids, and the editor mints them from the counter. This
clone does not: `BubbleIDGenerator.element_id()` draws four random base62 characters, and the
clone now checks each draw against the app's own `_index.id_to_path` so it cannot land on an id
that already exists.

The two id spaces therefore do not touch. Advancing the counter by six per cloned object would
reserve room in a sequence the clone never draws from, protecting nothing - while writing a value
the server accepts uncorrected into the field the editor uses for its own minting.

The remaining exposure is a future editor-minted id colliding with a random one this clone wrote.
Advancing the counter does not address it, because the counter does not describe where the random
ids landed. Closing it properly would mean minting from the counter the way the editor does, and
the mapping from counter value to id string was not derivable from eleven samples.
