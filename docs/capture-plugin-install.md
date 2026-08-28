# Captured: how the editor knows a plugin's version

Captured 2026-08-28 against `mcp-test-app` by driving the editor's Plugins tab with Playwright on
the stored session and recording every JSON response, then replaying the one call that mattered.

## Why this was needed

`bubble_plugin_install` defaults `plugin_value` to `true`. That is correct for Bubble's own plugins
and wrong for every marketplace plugin, which stores a version string instead. Installing
`1660311476391x288865870778204160` ("Free Toggle") with `true` was accepted by
`/appeditor/write` and then rejected by the very next call:

```
POST /appeditor/calculate_derived -> 400
{"error_class": "OwnerError", "message": "Invalid plugin version: true"}
```

So the write lands and the app is left holding a version the editor refuses to derive from. Nothing
in the tool detects this; the failure only surfaces one call later.

## The catalogue call

```
POST https://bubble.io/apiservice/doapicallfromserver
{
  "service_name": "bubble_plugin",
  "call_name": "get_edit_mode_plugins_list",
  "properties": {"appname": "<appname>", "current_plugins": {<key>: <value>, ...}},
  "serialized_context": {"skip_property_security": true},
  "ret_properties": true
}
```

It returns `ret` keyed by plugin key - 10507 entries, about 42 MB. `current_plugins` is what the app
already has; passing `{}` still returns the full catalogue.

## The rule

**Whether a plugin takes a version or `true` is decided by the catalogue, not by the key's shape.**

| plugin | `last_version` | install value |
|--------|----------------|---------------|
| marketplace, e.g. `1660311476391x288865870778204160` | `"4.2.0"` | that version string |
| Bubble's own, e.g. `apiconnector2` | absent | `true` |

10427 of 10507 entries carry `last_version`; the ones without it are Bubble's own integrations. A
native entry is also visibly thinner - no `price`, no `license`, no `history`, no `deprecated_versions`.

The `_installed_version` companion key belongs only to the `true` case. `auto-on`, which has this
plugin installed by hand, holds `plugins.<key> = "4.2.0"` and no companion key at all.

## What else the entry carries

`price`, `payment_type` and `one_time_price` (3878 entries have a price), `license`, `deprecated_versions`,
`blocked`, `deleted`, `hidden`, and a `history` array of every published version with its timestamp.
Enough for an installer to refuse a paid, blocked or deleted plugin instead of writing a value that
will fail derivation later.

`GET /appeditor/get_raw_plugin?plugin_id=<id>&version=<version>` returns the plugin's own definition,
but it requires the version as input, so it cannot be the source of it.
