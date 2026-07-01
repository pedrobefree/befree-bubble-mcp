# Figma Bridge

This repository includes only the local bridge service. It does not include
Figma-side integration code.

Bridge endpoints:

```text
GET /health
GET /profiles
POST /sync
```

The bridge is meant to receive design payloads from external local tooling and
hand them to the Bubble MCP workflow running on the user's computer.
