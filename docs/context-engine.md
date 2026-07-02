# Context Engine

The context engine makes Bubble automation more accurate by building compact, queryable project context.

Supported inputs:

- `.bubble`/consolelog-style JSON exports.
- Crawler indexes.
- Synthetic fixtures for public tests.

Outputs:

- Project summary.
- Project graph.
- Context lookup APIs.
- Pages, reusables, nested elements, workflows, data types, option sets, Bubble ids, and path arrays.

## Import

```bash
bubble-mcp context import \
  --file ./my-app-crawler-index.json \
  --kind crawler \
  --output ./my-app-context.json
```

```bash
bubble-mcp context import \
  --file ./my-app.bubble.json \
  --kind bubble \
  --output ./my-app-context.json
```

The compiler can use imported context to place new elements under an existing
parent by name.

## Detection

For real editor writes, prefer detecting context before executing plans. The
detector follows the same source priority used by Aria's Bubble tooling:

1. Use a provided `.bubble` export when available.
2. Use a provided `console.log(app)` capture when available.
3. Attempt best-effort `.bubble` export discovery.
4. Fall back to the editor path crawler using the captured Bubble session.

```bash
bubble-mcp context detect \
  --profile smoke \
  --app-id bovichain-g3 \
  --force
```

The detector writes a compact context file under the local Bubble MCP config
directory and, when the crawler runs, also writes a `{appId}-crawler-index.json`
artifact next to it. These files are local project data and should not be
committed.

You can also seed the detector with local artifacts:

```bash
bubble-mcp context detect --profile smoke --app-id bovichain-g3 --bubble-file ./app.bubble
bubble-mcp context detect --profile smoke --app-id bovichain-g3 --consolelog-file ./consolelog-app.txt
```

For real Bubble editor writes, context is also used to resolve the internal page
or reusable key used in write paths. Visual creation payloads must update Bubble
editor indexes as well as create the element body:

- `_index.id_to_path.<object-id>` points to the full element path.
- `_index.issues_list.<object-id>` initializes the issue list for the new
  element.
- `_index.issues_sub.<parent-or-root-id>` adds the new object id to the
  parent's indexed children.

If the imported context does not include a parent/root id, include it in the
plan step as `root_id` or `parent_id`. Existing children can be supplied as
`existing_children` or `parent_children` so the compiler preserves the current
editor tree while appending the new element.

```json
{
  "steps": [
    {
      "id": "smoke_text",
      "tool_name": "create_text",
      "args": {
        "context": "index",
        "context_key": "bTKhs",
        "root_id": "bTKhr",
        "existing_children": ["bTilt", "bTKiP", "bTimd"],
        "content": "Befree Bubble MCP smoke test",
        "name": "mcp_smoke_text"
      }
    }
  ]
}
```

No real project snapshots should be committed to this repository.
