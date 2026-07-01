# Session Capture

Session capture is not enabled in the first bootstrap commit.

The planned model is provider-based:

- `manual`: import a local session for debugging.
- `headless`: open a local browser for Bubble login.
- `extension`: receive session metadata from a browser extension.
- `aria-adapter`: let Aria provide a session through a private adapter.

Rules:

- Full session data stays local.
- Session data is volatile by default.
- UI clients receive only metadata.
- Logs and reports redact secret-like fields.
