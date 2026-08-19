#!/usr/bin/env python3
"""Print the deterministic MCP catalog-ambiguity audit as JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from bubble_mcp.harness.catalog_ambiguity import catalog_ambiguity_report  # noqa: E402


def main() -> int:
    report = catalog_ambiguity_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
