# MCP Clients

Start the server locally:

```bash
bubble-mcp-server
```

Example MCP configuration:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "bubble-mcp-server",
      "args": [],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

Initial tools:

- `bubble_health_check`: reports local server capabilities.
- `bubble_profile_list`: lists configured local Bubble profiles.

Mutating Bubble tools are intentionally not exposed until the planner, session capture, validation, and dry-run safety gates are extracted.
