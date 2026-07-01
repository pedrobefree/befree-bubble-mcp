# Session Capture

Session storage is enabled through manual import and optional browser-assisted
login.

Current manual format:

```json
{
  "appId": "my-bubble-app",
  "url": "https://bubble.io/page?id=my-bubble-app",
  "headers": {
    "Cookie": "...",
    "User-Agent": "..."
  },
  "appVersion": "test"
}
```

Import:

```bash
bubble-mcp session import --profile my-app --file ./bubble-session.json
```

Provider roadmap:

- `manual`: import a local session.
- `browser`: open a local Chromium browser for Bubble login through Playwright.
- `extension`: receive session metadata from a browser extension.
- `aria-adapter`: optional private adapter outside the open source core.

Rules:

- Full session data stays local.
- Session data is stored locally under the configured config directory.
- UI clients receive only metadata.
- Logs and reports redact secret-like fields.
