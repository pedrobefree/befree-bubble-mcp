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

No real project snapshots should be committed to this repository.
