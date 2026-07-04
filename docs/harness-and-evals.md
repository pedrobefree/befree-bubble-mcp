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
- optional structured visual snapshot comparison
- structural validation status when plans are inspected through planning/execution tools

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

## Visual Snapshot Harness

Use `bubble-mcp eval capture-visual` or MCP tool `bubble_visual_capture` to
capture a structured snapshot from a URL, HTML file, or raw HTML snippet. Then
use `bubble-mcp eval visual` or MCP tool `bubble_visual_compare` to compare two
snapshots. This is the first lightweight perceptual gate for HTML/Figma/Bubble
conversion quality before a full authenticated screenshot diff is available.

```bash
bubble-mcp eval capture-visual \
  --source tests/fixtures/html/hero.html \
  --selector '#hero' \
  --no-rendered-html \
  --output /tmp/hero-reference.json

bubble-mcp eval visual \
  --reference /tmp/hero-reference.json \
  --actual tests/fixtures/visual-snapshots/hero-actual-ok.json \
  --require-images
```

Eval cases can also include `visual_reference` / `visual_actual` paths or
`visualReference` / `visualActual` objects. They can also include
`visual_reference_source` / `visual_actual_source` or camelCase equivalents to
capture snapshots during the eval run. Use `visual_selector`,
`visual_rendered_html`, `visual_viewport_width`, `visual_viewport_height`, and
`visual_wait_ms` to control capture. Visual comparison checks layout geometry,
required text, image dimensions, typography, max-width, and gradient
direction/color order with configurable `visual_tolerance_px` and
`visual_tolerance_ratio`.

## Agent Routing Smoke

Use the `agent-routing` runtime smoke suite to verify that representative user
requests route through the MCP catalog instead of causing the agent to inspect
CLI help or repository code:

```bash
bubble-mcp smoke runtime --suite agent-routing
```

This local-only suite exercises `bubble_task_runbook`, `bubble_agent_guide`,
`bubble_task_recipe`, and `bubble_tool_search` against natural-language tasks
for HTML import, page creation, Figma/style sync, branches/changelog,
setup/context refresh, interactive session login, and workflow actions. It
performs no Bubble writes.

## Exporting Redacted Expert Captures

Use `bubble-mcp eval export-expert` or MCP tool `bubble_eval_export_expert` to
turn local captured editor writes into eval-friendly cases:

```bash
bubble-mcp eval export-expert \
  --input /tmp/captures.json \
  --output /tmp/generated-evals.json
```

The exporter:

- accepts arrays or objects with `entries`, `captures`, `requests`, or `events`;
- detects Bubble write payloads under `payload`, `write_payload`, `body`, or `request.payload`;
- classifies operation families such as visual element, page, workflow, data schema, option set, style, and delete;
- adds `expectedTool` hints when the payload maps cleanly to a tool family;
- adds basic `expectedArgs` and `visualReference` data for supported visual element captures;
- redacts sensitive keys and long secret-like values before writing the output.

Do not commit captured project data unless it has been reviewed and intentionally
sanitized.
