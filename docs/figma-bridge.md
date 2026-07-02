# Figma Bridge

This repository includes only the local bridge service. It does not include
Figma-side integration code.

Bridge endpoints:

```text
GET /health
GET /profiles
POST /sync
```

By default the bridge listens on `http://127.0.0.1:47831`. Override with
`BUBBLE_MCP_BRIDGE_HOST` and `BUBBLE_MCP_BRIDGE_PORT` when the Figma-side
integration expects a different local endpoint.

The bridge responds to CORS preflight requests so browser-based plugin UIs can
fetch these local endpoints from Figma's iframe environment.

The bridge is meant to receive design payloads from external local tooling and
hand them to the Bubble MCP workflow running on the user's computer.
