# Security Policy

Befree Bubble MCP is local-first. It may interact with authenticated Bubble editor sessions, so sensitive data handling is part of the product contract.

## Sensitive Data Rules

Do not commit:

- Cookies, headers, tokens, API keys, passwords, private keys, or credentials.
- Bubble project exports from real customer or production apps.
- Crawler indexes, project graphs, mutation overlays, logs, captures, or transcripts from real apps.
- Local databases or encrypted credential stores.

## Reporting

For private security issues, report through the repository owner before opening a public issue.

## Runtime Expectations

- Session material must stay local.
- Full session data must not be sent to UI clients.
- Logs and eval reports must redact secret-like fields.
- Mutating operations should support dry-run and explicit confirmation.
