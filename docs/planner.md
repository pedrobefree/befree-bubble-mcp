# Planner

The planner converts Bubble developer intent into structured, inspectable plans
without requiring a paid model provider.

Current flow:

```text
message -> packaged example matcher -> regex fallback -> structured plan -> semantic validation -> structural validation -> compile write_payload -> preview/apply
```

The packaged corpus lives in `src/bubble_mcp/planner/corpus.json`. It provides
public-safe examples for common edit, import, context, and eval requests. The
matcher emits routing metadata in each plan:

```json
{
  "routing": {
    "parser": "example_match",
    "corpus_entry": "import.create_from_html",
    "score": 0.42
  }
}
```

The planner response is intentionally agent-oriented:

- `validation`: semantic support and required-argument checks.
- `structural_validation`: step ids, dependency graph, write payload readiness, destructive confirmation.
- `operation_snapshot.next_user_action`: compact instruction for what the agent should do next.

Model adapters can improve routing later, but deterministic paths and corpus
examples should cover common Bubble operations first.
