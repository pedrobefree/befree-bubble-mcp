#!/usr/bin/env python3
"""Print the Bubble CLI-to-MCP catalog parity report as JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from bubble_mcp.catalog_audit import cli_catalog_parity_report  # noqa: E402
from bubble_mcp.server.schemas import list_tool_schemas  # noqa: E402


def main() -> int:
    report = cli_catalog_parity_report(str(tool.get("name") or "") for tool in list_tool_schemas())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
