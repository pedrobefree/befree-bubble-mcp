# Architecture

Befree Bubble MCP is organized around standalone, headless modules:

- `bubble_mcp.core`: configuration, redaction, shared errors, and Bubble command contracts.
- `bubble_mcp.cli`: user-facing command line interface.
- `bubble_mcp.server`: MCP protocol surface.
- `bubble_mcp.sessions`: local session capture and volatile session storage.
- `bubble_mcp.context`: `.bubble` parsing, crawler indexes, and project graph context.
- `bubble_mcp.planner`: intent planning and execution-plan construction.
- `bubble_mcp.validators`: semantic validation and safety gates.
- `bubble_mcp.converters`: HTML and Figma conversion flows.
- `bubble_mcp.harness`: evals, replay, and accuracy/token reports.

Aria should consume this project as a downstream adapter. The open source package must not depend on Electron, Aria IPC, Aria databases, or Aria UI components.
