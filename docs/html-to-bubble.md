# HTML To Bubble

The HTML converter turns simple HTML component input into Bubble plans.

Convert HTML into a validated Bubble plan:

```bash
bubble-mcp import html --file component.html --context index --parent index
```

Compile the generated plan directly into Bubble `/appeditor/write` payloads:

```bash
bubble-mcp import html --file component.html --context index --parent index --compile --app-id my-bubble-app
```

MCP clients can call the same flow through `bubble_import_html`:

```json
{
  "html": "<section><h1>Welcome</h1></section>",
  "context": "index",
  "parent": "index",
  "compile": true,
  "app_id": "my-bubble-app"
}
```

Implemented stages:

```text
HTML -> Bubble plan -> semantic validation -> optional write_payload compilation -> execute-plan
```

Supported conservative mapping:

- layout containers such as `div`, `section`, `main`, `article`, `header`, `footer`, `nav`, and `form` become `create_group` steps.
- textual tags such as `h1`, `h2`, `h3`, `p`, `span`, `label`, `button`, and `a` become `create_text` steps.
- compiled output can be previewed or executed with `bubble-mcp execute-plan --compile --execute` after a session is imported.
