# CLI Reference

## `bubble-mcp init`

Creates a local config directory and empty `settings.json`.

```bash
bubble-mcp init
```

## `bubble-mcp profile add`

Adds or updates a Bubble profile.

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
```

Optional fields:

```bash
bubble-mcp profile add my-app \
  --app-id my-bubble-app \
  --appname my-bubble-app \
  --editor-url https://bubble.io/page?id=my-bubble-app
```

## `bubble-mcp profile list`

Lists local profiles.

```bash
bubble-mcp profile list
```
