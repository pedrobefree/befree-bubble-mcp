# Rebuilding an importable `.bubble`

`bubble_export_rebuild` builds a `.bubble` file that Bubble's import accepts when the export
Bubble itself produces is incomplete or corrupted. It reads Bubble only and writes one new local
file; the profile cache is never overwritten.

## Why the export is not enough

Measured on a production app (346 reusables, 601 API workflows, 45 pages) on 2026-10-30:

1. **The export leaves reusables out.** The 14 MB export carried 2 stubs and no other reusable
   body. The existing hydration (`context/hydration.py`) fills them from the editor path API.
2. **Hydration stores them in the editor's shrunk key space** (`%el`, `%p`, `%x`, `%nm`, ...).
   The import does not expand those keys: it escapes them once more (`%el` lands as `%%el`) and
   the reusables arrive empty or nameless.
3. **The export disagrees with the live editor** on some nodes: reusables exported as a stub
   (only `workflows`, only `elements`), reusables with stale data, and, on a staging app, an API
   workflow with no `wf_name`/`parameters`.

## What the tool does

1. Downloads `/appeditor/export/<app_version>/<app>.bubble` and hydrates its reusables, exactly as
   `bubble_profile_cache_refresh` does, into `contexts/<profile>/rebuild/` instead of the cache.
   `app_version` defaults to `test` and never falls back to the profile's version. Pass
   `bubble_file` to start from an export already on disk (a preview returns the one it downloaded).
2. Expands the shrunk keys in `element_definitions` with the versioned key table
   (`src/bubble_mcp/context/data/editor_key_table.json`). `%%key` is an escape for the literal
   key `%key`. When a node carries a key in both forms (`%x` and `type`), the two are merged
   recursively and the shrunk value wins a conflict; collisions and conflicts are reported. A
   shrunk key the table does not know is kept and fails validation (see below).
3. Reads the live editor headless with the profile's stored browser session, through the public
   accessors that return the decoded form: `root.child('<section>').raw()` for `api`,
   `element_definitions`, `user_types`, `option_sets`, `styles`, `settings` and `_index`, and
   `root.child('pages').child(<id>).raw()` for each page (`child_names()` is refused by the
   editor). Sections load lazily, so each read waits for its node to stop throwing
   `NotReadyError`; a reusable the export knows about that the bulk read left incomplete is
   read again on its own path.
4. Compares each entry as canonical JSON (sorted keys, null-valued keys dropped, since the
   editor spells some absent keys as `null` and the export never writes one). Where the editor's
   entry is complete (`type` for api, reusables, styles and pages; `display` for data types and
   option sets) and different, it replaces the export's; a complete entry only the editor has is
   added. `null` entries, loose fragments (an entry with only `elements` or only
   `properties`) and the `length` counter are never added. Entries only the export has are kept
   and listed.
5. Validates: no `%` key left in any reusable, every reusable has a `type` and a `name` (a
   reusable the editor itself holds without a name is listed under `nameless_in_editor` instead
   of failing, since naming it would be inventing data). With `execute=true` it writes to a
   temporary file, reads it back, validates the copy again, and only then moves it into place.

The report gives, per section, how many entries were the same, different (replaced), only in the
export and only in the editor, plus the replaced and added ids with their names.

The output reflects the live editor and nothing else. Business fixes that are not in the editor
do not belong in this file.

## Re-extracting the key table

The table is the `mapping` object of the editor module `lib-browser/lang/shrink.js`, a literal
`mapping={display_sender_name:"d7",...,bgcolor:"bgc",...}` (long name -> abbreviation; the shrunk
key is `"%" + abbreviation`). In October 2026 it shipped in
`https://bubble.io/package/edit_js/<hash>/xfalse/edit.js`; it used to be in `edit_optional.js`.
When validation reports unknown `%` keys, Bubble added an abbreviation:

1. Open the app in the editor while logged in, then in the DevTools console find the bundle:

   ```js
   performance.getEntriesByType('resource').map(e => e.name).filter(n => n.includes('/package/edit'))
   ```

2. Save the bundle that contains `bgcolor:"bgc"` to a file (DevTools > Network > Save as, or
   `await (await fetch(url)).text()` copied out).
3. Compare and then write:

   ```bash
   python scripts/extract_bubble_editor_key_table.py path/to/edit.js
   python scripts/extract_bubble_editor_key_table.py path/to/edit.js --write
   ```

4. Run `pytest tests/unit/test_editor_keys.py` and update the pair count it asserts.

The extractor refuses a bundle with no `mapping={... bgcolor:"bgc" ...}` literal and a table
where two names share one abbreviation, which the editor itself refuses too.
