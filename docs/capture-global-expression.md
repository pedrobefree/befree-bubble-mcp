# Captured: how a Bubble global expression is stored

Captured 2026-08-28 against `mcp-test-app` (version `test`). Two nodes were compared:

| node | how it was made | file |
|------|-----------------|------|
| `bTGOw0` "User email" | authored by hand in the Bubble editor | `capture-global-expression-editor-authored.json` |
| `bpOVa` "mcp-probe-user-email" | written by the four MCP tools | `capture-global-expression-mcp-write.json` |

Both were read back with `bubble_live_node_read`, which goes through `window.appquery` and is the
only source of the **raw** encoding. The `.bubble` export is decoded and cannot be inverted - it is
what makes the two key spaces below diverge.

## The node

```json
{
  "id": "bTGOw0",
  "%nm": "User email",
  "btype_id": "text",
  "is_list": false,
  "parameters": {
    "bTGPA0": {"param_id": "bTGPA0", "param_name": "user", "btype_id": "user", "is_list": false}
  },
  "expression": {
    "%x": "GlobalExpressionParameter",
    "%p": {"global_expression_id": "bTGOw0", "param_id": "bTGPA0"},
    "%n": {"%x": "Message", "%nm": "email", "is_slidable": false},
    "is_slidable": false
  }
}
```

The hand-authored node and the MCP-written node are structurally identical: same keys, same nesting,
same `%x` constructors. Nothing in the editor's own encoding is missing from what the tools write.

`folder_id` appears on global expressions that live inside an editor folder and is **absent** on
both nodes here, so it is optional and a create does not have to supply it.

## Two key spaces for the same field

The name is `%nm` in the wire/live encoding and `name` in the decoded `.bubble` export. A reader that
only knows one of them silently falls back to the id. `list_global_expressions` accepts both; so does
name-based resolution in `GlobalExpressionService`.

The parameter map has no such split: `param_id`, `param_name`, `btype_id` and `is_list` carry the
same names in both spaces.

## Creation writes three changes

```
_index.id_to_path.<id>     -> "global_expressions.<id>"          Update index
global_expressions.<id>    -> {%nm, btype_id, id, is_list}       CreateGlobalExpression
_index.issues_list.<id>    -> [{message, node}] as a JSON string  Update index
```

The `issues_list` entry is what keeps the editor's issue checker reporting
`Global expression: remember to fill out expression` until a body is set. It carries a
`constructor_name` of `GlobalExpression` and one `json` arg holding the node's own path.

Parameters and the body are separate `ModifyGlobalExpression` writes against
`global_expressions.<id>.parameters.<param_id>` and `global_expressions.<id>.expression`. So an
expression is only usable after its body is set - creation alone leaves it flagged.

## Confirmed in the editor

`write_verify` reads every written path back and compares bytes, and all three writes passed. That is
not a render check on its own - a wrongly assembled interior can round-trip byte-identically. So the
written expression was also opened in the editor, under the `Expressions` tab next to `Styles` and
`Variables`, and it renders as intended:

- return type `text`, `List?` unchecked
- one parameter, `user`, of type `User`, `List?` unchecked
- expression body displayed as `user's email`, not as a raw node

It sits in the `Uncategorized` folder, which is what an absent `folder_id` means.

## Folders, deletion, and the editor's own creation order

`capture-global-expression-changelog.json` holds hand-made editor actions read back from
`/appeditor/fetch_changelog_entries`. The changelog reports the **decoded** key space
(`next`/`type`/`properties`/`name`), which maps to the wire keys `%n`/`%x`/`%p`/`%nm`.

### Folders are an app setting, not a node

```
settings.client_safe.global_expression_folder_list.<folder_id>
```

That is why they are absent from `_index.id_to_path` and from any top-level
`global_expression_folders` key - both were probed and returned nothing.

The value stored at that path is the folder's **name as a plain string**: creating one writes
`"New folder"`, and renaming it reports `before_value: "New folder"` / `after_value: "folder test"`
at the same path. There is no member list; membership lives on the expression instead, as
`global_expressions.<id>.folder_id`. Moving an expression into a folder is a single write of that
one field.

### Deleting a folder orphans its children

The capture pins this by ordering. Folder `bTGPN` was deleted at `…108795`; its only member,
`bTGPM`, was still there and got deleted separately six seconds later at `…115187`. No entry ever
clears `bTGPM.folder_id`, so a child keeps a dangling reference to a folder that no longer exists.
Anything that deletes a folder has to decide what to do about that; the editor does nothing.

### The editor creates, then renames

An editor-made expression is `added` under the default display name `Global expression`, and only a
separate `%nm` change gives it its real name. Parameters behave the same way: they appear as
`{is_list: false, btype_id: "text", param_id, param_name: "Parameter 1"}` and are then renamed and
retyped by further writes.

The tools do not reproduce that two-step - they set the final name in the create body - and the
result renders correctly, so the intermediate default is an editor UI artifact, not a requirement.

### `%n: null` is real

The body's first write is recorded as `{next: null, type: "GlobalExpressionParameter", properties:
{...}, is_slidable: false}`. The explicit `next: null` matches what `set_global_expression_expression`
writes when no field is chained. Chaining `email` then replaces it with
`{args: null, name: "email", next: null, type: "Message", is_slidable: false}` - note `args: null`,
which the tools omit and which the editor renders fine without.

### A description is a separate node

Adding a description writes `comments.<expression_id>`, outside `global_expressions` entirely.

## What the capture could not answer, and how it was settled

The changelog records `operation: "deleted"`, never the write intent behind it, so the delete
payload was the one piece with no capture behind it. It was resolved by trying the shape the SDK
already uses for style deletion - `DeleteGlobalExpression` with a null body, plus a bare
`IdToPathFixer` clearing the id alias - against the real app. The write returned 200, and a
`bubble_live_node_read` afterwards shows the node gone.

The same run validated the folder tools end to end: the folder was created, an expression moved into
it, the folder deleted with the member's `folder_id` cleared in the same payload, and the expression
deleted. Each step was confirmed by reading the live tree back, not by the write's own status.

### These writes do not appear in the editor changelog

Every change the SDK builds carries `changelog_data: []`, so none of the writes above show up in
`fetch_changelog_entries` - the newest entry there is still the last hand-made edit. This is not
specific to global expressions; it holds for the whole toolchain. It means the changelog is a record
of what a human did in the editor, and cannot be used to audit what the tools did.

### Deleting writes a null, but Bubble drops the key

Verifying the folder deletion reported `expected: null, actual: "absent"`. The write sends a null
body; Bubble removes the path rather than storing the null. Two consequences:

- `write_verify` reports `verified: false` on any null-body delete, because reading the path back
  gives "absent" instead of the null it expected. The delete still succeeded.
- The local mutation overlay *does* keep the null it wrote, so a reader working from the overlay
  sees folder ids whose value is null. Those name folders that no longer exist and must be skipped.
