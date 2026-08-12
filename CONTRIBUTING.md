# Contributing

This project is in early extraction. Keep changes small, tested, and scoped.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m coverage run -m pytest -q
python -m coverage report
python -m ruff check src tests scripts
python -m mypy src
python scripts/audit_sensitive_paths.py .
```

The coverage gate includes the legacy `aria_runtime` package. Its 32.5% floor is a ratchet:
new work must not reduce it, and focused runtime tests should raise it over time.

For local environments with a short process window, collect the large MCP test
module and the remaining unit suite as two `coverage run --append` shards. The
combined data must still pass the same global ratchet.

## Rules

- Do not add real Bubble project data.
- Add synthetic fixtures only.
- Prefer dry-run examples.
- Add tests for every new command, parser, validator, or safety rule.
- Run the sensitive-data audit before opening a pull request.
