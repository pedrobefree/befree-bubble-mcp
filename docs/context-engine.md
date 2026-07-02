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
