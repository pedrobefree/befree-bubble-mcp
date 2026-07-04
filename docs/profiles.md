# Profiles

A profile maps a friendly local name to a Bubble app.

Create the settings file:

```bash
bubble-mcp init
```

Add a profile:

```bash
bubble-mcp profile add my-app --app-id my-bubble-app
```

List profiles:

```bash
bubble-mcp profile list
```

Check whether one profile is ready for MCP work:

```bash
bubble-mcp profile status --profile my-app
```

`profile status` checks the local profile mapping, stored session metadata,
context freshness, and app id consistency. A profile is ready for reliable MCP
mutations only after session capture/import and context detection are complete.

Settings are stored in:

```text
~/.config/bubble-mcp/settings.json
```

Override the location:

```bash
BUBBLE_MCP_CONFIG_DIR=/path/to/config bubble-mcp profile list
```

Do not store cookies, passwords, or API keys in profile settings.
