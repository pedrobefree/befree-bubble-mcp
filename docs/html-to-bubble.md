# HTML To Bubble

The package exposes two HTML-to-Bubble paths:

- `bubble-mcp import html` without `--runtime`: conservative compatibility converter that returns a validated plan.
- `bubble-mcp import html --runtime`: Aria's advanced `create-from-html` runtime, with selector support, style translation, rendered DOM support, and direct Bubble writes when `--execute` is set.

The advanced runtime resolves Bubble contexts from the same unified discovery shape
used by Aria: the current `.bubble` export is the base, then the crawler index and
the local mutation overlay are applied when present. Successful MCP writes append
to the mutation overlay, so pages or elements created through MCP can be resolved
before the next `.bubble` export catches up.

Convert HTML into a validated Bubble plan:

```bash
bubble-mcp import html --file component.html --context index --parent index
```

Run the advanced Aria importer in preview mode:

```bash
bubble-mcp import html \
  --file component.html \
  --runtime \
  --profile smoke \
  --app-id my-bubble-app \
  --context index \
  --parent root \
  --selector '.pricing-card' \
  --translate-to-existing-styles
```

Execute the advanced import against Bubble:

```bash
bubble-mcp import html \
  --file component.html \
  --runtime \
  --profile smoke \
  --app-id my-bubble-app \
  --context index \
  --parent root \
  --execute
```

Compile the generated plan directly into Bubble `/appeditor/write` payloads:

```bash
bubble-mcp import html --file component.html --context index --parent index --compile --app-id my-bubble-app
```

MCP clients can call the conservative plan flow through `bubble_import_html`:

```json
{
  "html": "<section><h1>Welcome</h1></section>",
  "context": "index",
  "parent": "index",
  "compile": true,
  "app_id": "my-bubble-app"
}
```

MCP clients can call the advanced Aria runtime through the ported catalog tool `create_from_html`:

```json
{
  "profile": "smoke",
  "app_id": "my-bubble-app",
  "context": "index",
  "parent": "root",
  "html": "<section><h1>Welcome</h1></section>",
  "execute": false,
  "selector": "section",
  "translate_to_existing_styles": true
}
```

Implemented stages:

```text
Conservative: HTML -> Bubble plan -> semantic validation -> optional write_payload compilation -> execute-plan
Advanced: HTML/file/URL -> Aria parser -> mapper -> BubbleCLI create-from-html -> optional /appeditor/write
```

Supported conservative mapping:

- layout containers such as `div`, `section`, `main`, `article`, `header`, `footer`, `nav`, and `form` become `create_group` steps.
- textual tags such as `h1`, `h2`, `h3`, `p`, `span`, `label`, `button`, and `a` become `create_text` steps.
- compiled output can be previewed or executed with `bubble-mcp execute-plan --compile --execute` after a session is imported.
