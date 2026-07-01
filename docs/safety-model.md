# Safety Model

Safety defaults:

- Read-only first.
- Dry-run before mutation.
- Explicit confirmation for destructive actions.
- Savepoint recommendation for schema, workflow, API, and security-sensitive changes.
- Secret redaction in logs and reports.
- Local-only session material.

The MCP server currently exposes only read-only/local-safe tools.
