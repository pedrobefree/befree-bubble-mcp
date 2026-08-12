#!/usr/bin/env python3
"""Print the Bubble CLI-to-MCP catalog parity report as JSON."""

from __future__ import annotations

import json

from bubble_mcp.catalog_audit import cli_catalog_parity_report
from bubble_mcp.server.schemas import list_tool_schemas


def main() -> int:
    report = cli_catalog_parity_report(str(tool.get("name") or "") for tool in list_tool_schemas())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
