# HTML Style Import Evolution

This document defines the next implementation contract for `create_styles_from_html`.

## Implemented In This Step

- `style_name` is the explicit style identity requested by the caller.
- `element_type` is required and must be supplied by the caller.
- The workflow behaves as an upsert by `style_name + element_type`.
- Existing Bubble styles with the same name and element type are updated by the existing style runtime.
- Missing styles are created.
- State conditions are applied after the base style upsert.
- `execute=true` performs post-execution verification through refreshed profile context/cache and style lookup.
- The generated `create_style` operation disables property-based matching, so a visually equivalent style with a different name is not reused.

## Identity Rules

The style identity is:

```text
style_name + element_type
```

No property-based dedupe is part of this contract. A style with equivalent visual properties but a different name is not reused.

## Verification Rules

After `execute=true`, the workflow must:

1. Dispatch base style upsert and state operations.
2. Refresh the profile context/cache when the host runtime provides that capability.
3. Look up the resulting style by `style_name + element_type`.
4. Compare mapped base properties against Bubble `%p` values when the refreshed context exposes them.
5. Compare expected state triggers and mapped state properties against Bubble `%s` values when the refreshed context exposes them.
6. Return verification status with the expected state names, property checks, and state checks.

Verification failure must not be hidden behind write success. The response should include `verified=false` and a reason.
If the refreshed context only exposes normalized style metadata and omits raw `%p` or `%s`, the response must report the relevant check as `checked=false` instead of claiming field-level confirmation.

## CSS Compatibility Rules

The mapper should normalize CSS only into Bubble-supported style fields.

- CSS variables should be resolved when the source provides enough information.
- `rgb()`, `rgba()`, `hsl()`, and `hsla()` colors should be normalized where Bubble accepts colors.
- Unsupported CSS must be returned in `unsupported` with a reason.
- Multiple backgrounds, multiple images, or CSS constructs without Bubble equivalents must not be forced into invalid Bubble fields.
- Media-query handling belongs to the rendered/computed pipeline and reflects the active browser viewport instead of creating a separate responsive style engine.

## URL/Rendered Pipeline

URL support uses the existing browser renderer from the Aria HTML importer:

1. Accept `url + selector`.
2. Load the URL with a browser.
3. Select the requested element.
4. Extract `getComputedStyle(element)` for the base style.
5. Resolve external CSS, cascade, inherited values, CSS variables, and active viewport media queries through the browser.
6. Extract state deltas for hover, focus, disabled, and pressed through browser simulation where practical.
7. Serialize computed base style as inline HTML and state deltas as synthetic CSS.
8. Feed the normalized result into the same Bubble mapper and upsert planner.

If browser rendering is disabled with `rendered_html=false`, URL imports fetch the raw HTML response and only static CSS present in that response can be mapped.
