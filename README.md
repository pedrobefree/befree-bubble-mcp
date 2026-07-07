# Befree Bubble MCP

Local-first Bubble automation toolkit for developers who want safer, more accurate agent-assisted Bubble work.

The package provides:

- `bubble-mcp`: CLI for local setup, profiles, sessions, context, smoke checks, and utilities.
- `bubble_mcp.server.stdio`: stdio MCP server for IDEs and agent clients.

Until this package is published to a Python package index, install it from a local repository clone.

## Requirements

- Python 3.11 or newer.
- A Bubble account with editor access to the target app.
- The Bubble app id from the editor URL, for example `my-bubble-app` from `https://bubble.io/page?id=my-bubble-app`.
- An IDE or agent client that can connect to a stdio MCP server.

Node.js 20 or newer is needed only for optional bridge integrations, such as the Figma bridge.

## Quick Start

Use a short profile name for each Bubble project. The examples below use:

- Profile: `my-app`
- Bubble app id: `my-bubble-app`

Replace both with your real values.

### 1. Clone The Repository

```bash
git clone https://github.com/pedrobefree/befree-bubble-mcp.git
cd befree-bubble-mcp
```

### 2. Create The Python Environment And Install

macOS / Linux / Git Bash:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python scripts/install_local.py --extras browser,dev
python -m playwright install chromium
bubble-mcp --help
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python scripts\install_local.py --extras browser,dev
python -m playwright install chromium
bubble-mcp --help
```

If PowerShell blocks virtualenv activation in the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Initialize Bubble MCP Settings

```bash
bubble-mcp init
```

Default local config directory:

```text
macOS / Linux: ~/.config/bubble-mcp
Windows: %USERPROFILE%\.config\bubble-mcp
```

### 4. Add A Bubble Project Profile

```bash
bubble-mcp profile add my-app --app-id my-bubble-app --app-version test
bubble-mcp profile list
```

Use `--app-version test` when you work in Bubble's development version. Omit it if you want the profile to use the default version.

### 5. Log In And Capture The Bubble Session

```bash
bubble-mcp session login --profile my-app --app-id my-bubble-app --wait-seconds 180
```

The command opens a local Chromium window. Log in to Bubble and keep the editor tab open until the terminal prints:

```text
[bubble-mcp session] Session cookies detected. You can close the browser now; the CLI will save the newest captured session.
```

Then verify the stored session:

```bash
bubble-mcp session list
bubble-mcp session inspect --profile my-app
```

`session inspect` redacts cookies and only confirms that the session can be used by the MCP.

### 6. Load The Bubble Project Context

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --app-version test --force
```

Refresh context whenever pages, reusable elements, workflows, data types, styles, or app structure change outside this MCP.

### 7. Check Readiness

```bash
bubble-mcp profile status --profile my-app
bubble-mcp readiness --profile my-app --context index --parent root
```

The profile is ready when `profile status` reports `ready: true`.

### 8. Configure Your IDE MCP Client

Configure the MCP server as a stdio server.

macOS / Linux example:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "/absolute/path/to/befree-bubble-mcp/.venv/bin/python",
      "args": ["-m", "bubble_mcp.server.stdio"],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "/Users/me/.config/bubble-mcp"
      }
    }
  }
}
```

Windows JSON example:

```json
{
  "mcpServers": {
    "befree-bubble-mcp": {
      "command": "C:\\path\\to\\befree-bubble-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "bubble_mcp.server.stdio"],
      "env": {
        "BUBBLE_MCP_CONFIG_DIR": "C:\\Users\\me\\.config\\bubble-mcp"
      }
    }
  }
}
```

Windows paths use double backslashes in JSON because `\` is an escape character. In a visual IDE field, use normal single backslashes, for example:

```text
C:\path\to\befree-bubble-mcp\.venv\Scripts\python.exe
```

If your IDE has form fields instead of JSON, use:

```text
Name: befree-bubble-mcp
Transport: STDIO
Command: /absolute/path/to/befree-bubble-mcp/.venv/bin/python
Arguments: -m bubble_mcp.server.stdio
Environment variable: BUBBLE_MCP_CONFIG_DIR=/absolute/path/to/bubble-mcp-config
Working directory: /absolute/path/to/befree-bubble-mcp
```

On Windows form fields:

```text
Command: C:\path\to\befree-bubble-mcp\.venv\Scripts\python.exe
Arguments: -m bubble_mcp.server.stdio
Environment variable: BUBBLE_MCP_CONFIG_DIR=C:\Users\me\.config\bubble-mcp
Working directory: C:\path\to\befree-bubble-mcp
```

After connecting the MCP, ask naturally and reference the profile name:

```text
Using befree-bubble-mcp with profile my-app, create a page called mcp-01.
```

## Common Maintenance Commands

Repair an interrupted editable install:

macOS / Linux / Git Bash:

```bash
python scripts/install_local.py --repair --extras browser,dev
```

Windows PowerShell:

```powershell
python scripts\install_local.py --repair --extras browser,dev
```

Refresh project context:

```bash
bubble-mcp context detect --profile my-app --app-id my-bubble-app --app-version test --force
```

Run local catalog and readiness checks:

```bash
bubble-mcp tools quality
bubble-mcp tools coverage
bubble-mcp readiness --profile my-app --context index --parent root
```

Run an authenticated write smoke only when you intentionally want to mutate the Bubble app:

```bash
bubble-mcp smoke runtime --suite execute-write --profile my-app --execute --verify-context --cleanup
```

## Optional Figma Bridge

The Figma plugin itself is outside this repository. This repository includes only the local bridge.

macOS / Linux / Git Bash:

```bash
BUBBLE_MCP_CONFIG_DIR=/Users/me/.config/bubble-mcp npm run figma:bridge
```

Windows PowerShell:

```powershell
$env:BUBBLE_MCP_CONFIG_DIR="$env:USERPROFILE\.config\bubble-mcp"; npm run figma:bridge
```

The bridge listens on `http://localhost:3333`.

## Documentation

- [Installation](docs/installation.md)
- [Getting started](docs/getting-started.md)
- [MCP clients](docs/mcp-clients.md)
- [CLI reference](docs/cli-reference.md)
- [Context engine](docs/context-engine.md)
- [Session capture](docs/session-capture.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Extension packs](docs/extension-packs.md)
- [Knowledge sources](docs/knowledge-sources.md)
- [Tool authoring](docs/tool-authoring.md)
- [Skills](docs/skills.md)

## Safety Defaults

- No real project data is included in this repository.
- Session credentials stay local.
- Mutating tools require a local session and explicit `execute=true` or `--execute`.
- Without execution opt-in, write commands preview the normalized request.
- Sensitive values are redacted before logs or reports.
- Local extension, learning, knowledge, skill, and tool-authoring state stays under `BUBBLE_MCP_CONFIG_DIR`.

## Status

Early alpha. Real Bubble editor writes are supported when you provide a valid local Bubble session and an exact project context. Generated plans preview by default and only write when execution is explicitly enabled.
