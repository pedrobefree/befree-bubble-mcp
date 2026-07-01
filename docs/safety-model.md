# Safety Model

Safety defaults:

- Local session required before mutation.
- Preview before mutation unless the caller passes `execute=true` or `--execute`.
- Explicit confirmation for destructive actions.
- Savepoint recommendation for schema, workflow, API, and security-sensitive changes.
- Secret redaction in logs and reports.
- Local-only session material.

The MCP server exposes mutating tools. They do not post to Bubble unless the
caller explicitly opts into execution.
