# Source Audit

The public repository excludes all Aria-monitored project data, including Bubble snapshots, crawler indexes, project graphs, mutation overlays, logs, captures, sessions, cookies, headers, transcripts, local databases, and generated profile artifacts.

Allowed source categories:

- Generic CLI/runtime code.
- Generic MCP server code.
- Generic parsers, builders, validators, and schemas.
- Synthetic fixtures.
- Documentation.

Blocked source categories:

- Any real Bubble project export.
- Any file containing app-specific tokens, cookies, headers, API keys, or private app IDs.
- Any generated Aria userData file.
