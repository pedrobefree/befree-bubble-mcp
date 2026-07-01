# Troubleshooting

## `bubble-mcp` command not found

Install with `pipx` or activate your virtual environment:

```bash
. .venv/bin/activate
```

## No profiles returned

Run:

```bash
bubble-mcp init
bubble-mcp profile add my-app --app-id my-bubble-app
```

## MCP server starts but has no mutation tools

This is expected in the bootstrap version. Mutation tools will be exposed only after session capture, planner, validation, and dry-run gates are extracted.
