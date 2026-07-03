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

Browser-assisted capture:

```bash
python -m pip install "befree-bubble-mcp[browser]"
python -m playwright install chromium
bubble-mcp session login --profile my-app --app-id my-bubble-app --app-version test --wait-seconds 180
bubble-mcp session list
bubble-mcp session inspect --profile my-app
```

`session login` uses a persistent local Chromium profile under the Bubble MCP
config directory, opens the Bubble editor, and polls Bubble cookies while the
window is open. `--wait-seconds` is the maximum capture window. After logging
in, leave the editor open for a few seconds before closing the browser so the
latest cookies can be captured. If you close the window early, the command saves
the most recent cookies captured during that run.

The login command writes progress to stderr. Wait for:

```text
[bubble-mcp session] Session cookies detected. You can close the browser now; the CLI will save the newest captured session.
```

After this message appears, it is safe to close the browser. The command will
save the session and print the final redacted JSON result to stdout. Pass
`--quiet` to disable progress output in automated scripts.

Use `session inspect` to verify, without printing secrets, which session header
keys were stored and which Bubble write headers will be computed for
`/appeditor/write`.

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
