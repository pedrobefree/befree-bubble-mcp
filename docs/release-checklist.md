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
python -m bubble_mcp.cli.main smoke runtime --suite visual-repair
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

Build and install a wheel in a clean Python 3.11 venv, then verify imports,
CLI, MCP initialize, and the packaged catalog-quality/ambiguity corpus:

```bash
python scripts/package_smoke.py --python python3.11
```

Expected:

- Wheel build succeeds.
- Clean install succeeds.
- `bubble-mcp` console script starts.
- `bubble-mcp-server` responds to MCP `initialize` and includes server
  instructions.
- Catalog quality and all 27 packaged ambiguity cases pass from the clean wheel
  installation without access to the source checkout.
- The packaged data-schema precision audit reports `schema_precision_ok: true`
  and `schema_precision_tool_count: 28`.

## Data-Schema Precision Gate

```bash
PYTHONPATH=src python scripts/audit_catalog_schema_precision.py
```

Expected:

- `ok: true`
- `tool_count: 28`
- `failure_count: 0`

## Local Setup Smoke

```bash
python scripts/setup_smoke.py
```

Expected:

- Local config can be created.
- Profile creation works.
- Profile status returns `ready=false` with `next_actions` when
  session/context are not configured yet.
- Readiness fails in the expected controlled way for a fresh profile without
  credentials or context.
