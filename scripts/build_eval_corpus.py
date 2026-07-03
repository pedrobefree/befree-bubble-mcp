#!/usr/bin/env python3
"""Build a public-safe planner corpus from eval datasets and optional tool hints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must contain a JSON array.")
    return [item for item in payload if isinstance(item, dict)]


def build_corpus(paths: list[Path]) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for path in paths:
        for case in _load_json_array(path):
            tool_name = str(case.get("expected_tool") or case.get("expectedTool") or "").strip()
            message = str(case.get("message") or "").strip()
            if not tool_name or not message:
                continue
            key = tool_name
            entry = entries.setdefault(
                key,
                {
                    "id": f"generated.{tool_name}",
                    "tool_name": tool_name,
                    "risk": "routine_visual_mutation",
                    "utterances": [],
                    "default_args": {},
                },
            )
            if message not in entry["utterances"]:
                entry["utterances"].append(message)
            expected_args = case.get("expected_args") or case.get("expectedArgs")
            if isinstance(expected_args, dict):
                entry["default_args"].update(expected_args)
    return sorted(entries.values(), key=lambda item: str(item["id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="+", help="Eval dataset JSON files.")
    parser.add_argument("--output", required=True, help="Corpus JSON output path.")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus([Path(value) for value in args.dataset])
    output.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "entries": len(corpus), "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
