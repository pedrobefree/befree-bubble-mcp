# Harness And Evals

The harness measures whether natural-language requests route to the expected
Bubble tools and arguments, and can optionally compile the generated plans into
Bubble `/appeditor/write` payloads.

Implemented metrics:

- matched cases
- correct tool
- correct args
- validation result
- compilation result
- presence of `args.write_payload`
- step count
- deterministic estimated token count

Run a dataset:

```bash
bubble-mcp eval run --dataset tests/fixtures/evals/basic-routing.json --report reports/basic.json
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
`app_id` fields. A compiled report includes `summary.compile_ok`,
`summary.estimated_tokens`, and per-case `has_write_payload` evidence.
