# Figma Plugin

The planned Befree Figma plugin communicates with a local bridge running on the user's computer.

Planned bridge endpoints:

```text
GET /health
GET /profiles
POST /sync
```

The plugin should default to dry-run and require an active local bridge before enabling sync.

Manifest guidance:

```json
{
  "networkAccess": {
    "allowedDomains": ["http://localhost:3333"],
    "reasoning": "The plugin sends selected Figma component data to the user's local Bubble MCP bridge."
  }
}
```
