# Installation

## Recommended

```bash
pipx install befree-bubble-mcp
```

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
bubble-mcp --help
```

## Requirements

- Python 3.11 or newer.
- Node.js 20 or newer for bridge integrations.
- A Bubble account for authenticated editor operations.

The initial alpha exposes setup and read-only MCP tools. Mutating Bubble commands will be enabled after session capture, planning, validation, and dry-run safety gates are extracted.
