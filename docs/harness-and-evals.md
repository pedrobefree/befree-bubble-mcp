# Harness And Evals

The harness measures whether natural-language requests route to the expected
Bubble tools and arguments, and can optionally compile the generated plans into
Bubble `/appeditor/write` payloads.

Implemented metrics:

- matched cases
- correct tool
- correct args
- missing required argument status
- validation result
- expected warning coverage
- compilation result
- presence of `args.write_payload`
- parser summary
- fallback/failure reason summary
- step count
- deterministic estimated token count

Dataset cases accept either standalone snake_case keys or Aria-style camelCase
keys:

```json
{
  "id": "create_text_hello",
  "message": "Create a text saying \"Hello\"",
  "expected_tool": "create_text",
  "expected_args": {
    "context": "index",
    "content": "Hello"
  },
  "expected_warnings_includes": []
}
```

The same case can also use `expectedTool`, `expectedArgs`, and
`expectedWarningsIncludes`. Reports include per-case `parser`,
`fallback_reason`, `fallback_reasons`, `warnings`, and `validation_errors`
fields so agent-routing failures can be diagnosed without opening logs.

Run a dataset:

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --report reports/basic.json
```

Run a cheap focused subset:

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --filter create_text_hello
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --offset 20 --limit 10
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --failed-from reports/basic.json
```

Run the same dataset and require compiler coverage:

```bash
bubble-mcp eval run \
  --dataset tests/fixtures/evals/basic-routing.json \
  --compile \
  --app-id my-bubble-app \
  --report reports/basic-compiled.json
```

The MCP tool `bubble_eval_run` accepts the same `dataset`, `compile`, and
`app_id` fields, plus `filter`, `failed_from`, `offset`, and `limit` for focused
reruns. A compiled report includes `summary.compile_ok`,
`summary.estimated_tokens`, and per-case `has_write_payload` evidence.
The summary also includes `parser_summary` and `fallback_summary` for quick
regression triage.
