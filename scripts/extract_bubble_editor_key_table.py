#!/usr/bin/env python3
"""Re-extract the Bubble editor key-shrink table from a saved editor bundle.

Usage:
    python scripts/extract_bubble_editor_key_table.py path/to/edit.js [--write]

Without --write it prints what changed against the versioned table. With --write it updates
src/bubble_mcp/context/data/editor_key_table.json. See docs/export-rebuild.md for how to save the
bundle from a logged-in editor.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bubble_mcp.context.editor_keys import KEY_TABLE_PATH, extract_key_table_from_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", type=Path, help="Saved editor bundle (edit.js or edit_optional.js).")
    parser.add_argument("--write", action="store_true", help="Update the versioned table.")
    args = parser.parse_args(argv)

    extracted = extract_key_table_from_bundle(args.bundle.read_text(encoding="utf-8"))
    current_doc = json.loads(KEY_TABLE_PATH.read_text(encoding="utf-8"))
    current = current_doc.get("mapping") or {}
    added = sorted(set(extracted) - set(current))
    removed = sorted(set(current) - set(extracted))
    changed = sorted(key for key in set(extracted) & set(current) if extracted[key] != current[key])
    print(
        json.dumps(
            {
                "pairs": len(extracted),
                "added": {key: extracted[key] for key in added},
                "removed": {key: current[key] for key in removed},
                "changed": {key: [current[key], extracted[key]] for key in changed},
            },
            indent=2,
        )
    )
    if args.write:
        current_doc["mapping"] = dict(sorted(extracted.items()))
        current_doc.setdefault("source", {})["extracted_at"] = time.strftime("%Y-%m-%d", time.gmtime())
        KEY_TABLE_PATH.write_text(json.dumps(current_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {KEY_TABLE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
