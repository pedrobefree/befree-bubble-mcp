# Release Checklist

Run these checks before publishing a package or tagging a release.

## Source Safety

```bash
python scripts/audit_sensitive_paths.py .
```

Expected:

- No secrets, sessions, local Bubble project data, generated context exports, or
  private comparison notes in public source.

## Python Quality Gate

```bash
python -m ruff check src tests scripts
python -m mypy src
python -m pytest -q
python -m bubble_mcp.cli.main smoke runtime --suite coverage
python -m bubble_mcp.cli.main smoke runtime --suite agent-routing
```

Expected:

- Ruff passes.
- Mypy passes.
- Pytest passes.
- Runtime coverage reports `ok: true` and no uncovered exposed tools.
- Agent routing reports `ok: true`.

## Bridge Quality Gate

```bash
npm test
```

Expected:

- Figma bridge Node tests pass.

## Packaging Smoke

Build a wheel into a temporary directory:

```bash
rm -rf /tmp/befree-bubble-mcp-wheel
mkdir -p /tmp/befree-bubble-mcp-wheel
python -m pip wheel . -w /tmp/befree-bubble-mcp-wheel
```

Install the generated wheel in a clean Python 3.11 venv and verify imports,
CLI, and MCP initialize:

```bash
tmpdir=$(mktemp -d /tmp/befree-bubble-mcp-install.XXXXXX)
python3.11 -m venv "$tmpdir/.venv"
"$tmpdir/.venv/bin/python" -m pip install /tmp/befree-bubble-mcp-wheel/befree_bubble_mcp-0.1.0-py3-none-any.whl
"$tmpdir/.venv/bin/python" - <<'PY'
import bubble_mcp
from bubble_mcp.server.stdio import handle_request

print(bubble_mcp.__version__)
print(handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["serverInfo"])
PY
"$tmpdir/.venv/bin/bubble-mcp" --help >/tmp/befree-wheel-cli-help.txt
"$tmpdir/.venv/bin/bubble-mcp-server" <<'EOF' >/tmp/befree-wheel-server-init.json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
EOF
python - <<'PY'
import json

payload = json.load(open("/tmp/befree-wheel-server-init.json"))
assert payload["result"]["serverInfo"]["name"] == "befree-bubble-mcp"
assert "instructions" in payload["result"]
print("wheel smoke passed")
PY
rm -rf "$tmpdir"
```

Expected:

- Wheel build succeeds.
- Clean install succeeds.
- `bubble-mcp` console script starts.
- `bubble-mcp-server` responds to MCP `initialize` and includes server
  instructions.

## Local Setup Smoke

```bash
bubble-mcp init
bubble-mcp profile add release-smoke --app-id example-app --app-version test
bubble-mcp profile status --profile release-smoke
```

Expected:

- Local config can be created.
- Profile creation works.
- Profile status returns JSON with `next_actions` when session/context are not
  configured yet.
