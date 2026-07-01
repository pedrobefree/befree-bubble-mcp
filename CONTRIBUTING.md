# Contributing

This project is in early extraction. Keep changes small, tested, and scoped.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests scripts
```

## Rules

- Do not add real Bubble project data.
- Add synthetic fixtures only.
- Prefer dry-run examples.
- Add tests for every new command, parser, validator, or safety rule.
- Run the sensitive-data audit before opening a pull request.
