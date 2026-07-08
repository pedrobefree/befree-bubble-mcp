# HTML To Bubble

The package exposes two HTML-to-Bubble paths:

- `bubble-mcp import html` without `--runtime`: conservative compatibility converter that returns a validated plan.
- `bubble-mcp import html --url ...`: Aria's advanced `create-from-html` runtime, with selector support, style translation, rendered DOM support, and direct Bubble writes when `--execute` is set.
- `bubble-mcp import html-styles`: extracts reusable Bubble style definitions from HTML/CSS without creating page elements.

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
  --url https://example.com/page.html \
  --profile smoke \
  --app-id my-bubble-app \
  --context index \
  --parent root \
  --selector '.pricing-card' \
  --translate-to-existing-styles
```

Create Bubble styles from local HTML/CSS before importing elements:

```bash
bubble-mcp import html-styles \
  --file component.html \
  --profile smoke \
  --selector '.btn-primary' \
  --style-name 'Primary Button' \
  --element-type Button
```

For a live URL, pass the URL and the exact element selector. The command uses a
browser-rendered DOM by default, so class-based styles, CSS variables, external
stylesheets, and active viewport media queries are resolved from
`getComputedStyle` before mapping:

```bash
bubble-mcp import html-styles \
  --url https://example.com/page.html \
  --profile smoke \
  --selector '.btn-primary' \
  --style-name 'Primary Button' \
  --element-type Button
```

The style workflow maps supported CSS into `create_style`, `add_style_condition`,
and `reorder_style_states` operations. It preserves independent border width,
style, color, and corner radius fields when they are present, and imports
`:hover`, `:focus`/`:focus-visible`, `:disabled`, and `:active` as Bubble hover,
focus, disabled, and pressed style states. Style identity is explicit:
`style_name + element_type`. If a style with the same name and element type
already exists, the existing Bubble style runtime updates it; otherwise it
creates a new style. Property-equivalent styles with different names are not
reused. With `--execute`, the workflow refreshes context/cache and verifies the
style identity, plus base/state properties when the refreshed export exposes
raw Bubble style fields. For URL sources, rendered extraction also attempts
browser state deltas for hover, focus, disabled, and pressed.

Execute the advanced import against Bubble:

```bash
bubble-mcp import html \
  --url https://example.com/page.html \
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

MCP clients should call the advanced Aria runtime through `create_from_html`:

```json
{
  "profile": "smoke",
  "app_id": "my-bubble-app",
  "context": "index",
  "parent": "root",
  "url": "https://example.com/page.html",
  "execute": false,
  "selector": "#home-area",
  "rendered_html": true,
  "translate_to_existing_styles": true
}
```

MCP clients should call `create_styles_from_html` when they only need style
definitions from a URL, HTML file, or raw HTML snippet:

```json
{
  "profile": "smoke",
  "url": "https://example.com/page.html",
  "selector": ".btn-primary",
  "style_name": "Primary Button",
  "element_type": "Button",
  "rendered_html": true,
  "execute": false
}
```

Implemented stages:

```text
Conservative: HTML -> Bubble plan -> semantic validation -> optional write_payload compilation -> execute-plan
Advanced: HTML/file/URL -> Aria parser -> mapper -> BubbleCLI create-from-html -> optional /appeditor/write
Styles: HTML/file/snippet/URL -> static or rendered CSS extractor -> Bubble style mapper -> style upsert -> optional verification
```

Supported conservative mapping:

- layout containers such as `div`, `section`, `main`, `article`, `header`, `footer`, `nav`, and `form` become `create_group` steps.
- textual tags such as `h1`, `h2`, `h3`, `p`, `span`, `label`, `button`, and `a` become `create_text` steps.
- compiled output can be previewed or executed with `bubble-mcp execute-plan --compile --execute` after a session is imported.
