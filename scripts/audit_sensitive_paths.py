#!/usr/bin/env python3
"""Fail when public files contain obvious sensitive Bubble/Aria artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SENSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bcookie\s*[:=]\s*[^,\n]{12,}",
        r"\bauthorization\s*[:=]\s*[^,\n]{12,}",
        r"\bbearer\s+[a-z0-9._~+/-]{12,}",
        r"\bapi[_-]?token\s*[:=]\s*[^,\n]{8,}",
        r"\baccess[_-]?token\s*[:=]\s*[^,\n]{8,}",
        r"\brefresh[_-]?token\s*[:=]\s*[^,\n]{8,}",
        r"\bclient[_-]?secret\s*[:=]\s*[^,\n]{8,}",
        r"\bpassword\s*[:=]\s*[^,\n]{8,}",
        r"\bcredentials\.enc\b",
        r"\baria\.db\b",
        r"\bbefree-page\b",
        r"\bcli-test-project-graph\b",
        r"\b(?:befree|cli-test|prod|live)[a-z0-9_-]*-crawler-index\.json\b",
        r"\bmutation-overlay\b",
        r"\bproject-graph\b",
    ]
]

SKIP_DIRS = {
    ".git",
    ".local",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "node_modules",
}

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".txt",
    ".example",
}

ALLOWLIST = {
    ".gitignore",
    "SECURITY.md",
    "docs/source-audit.md",
    "src/bubble_mcp/core/redaction.py",
    "src/bubble_mcp/context/mutation_overlay.py",
    "src/bubble_mcp/execution/client.py",
    "bridge/figma/server.mjs",
    "scripts/audit_sensitive_paths.py",
    "test-node/figma-bridge.test.mjs",
    "tests/unit/test_redaction.py",
    "tests/unit/test_html_converter.py",
    "tests/unit/test_mcp_server.py",
    "tests/unit/test_sensitive_audit.py",
}


def is_text_candidate(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in {".gitignore", ".env.example"}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and is_text_candidate(path):
            yield path


def audit_path(root: Path) -> list[str]:
    findings: list[str] = []
    for path in iter_files(root):
        relative = path.relative_to(root)
        if str(relative) in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SENSITIVE_PATTERNS:
            match = pattern.search(text)
            if match:
                findings.append(f"{relative}: matched {pattern.pattern!r}")
                break
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Paths to audit.")
    args = parser.parse_args(argv)

    findings: list[str] = []
    for raw_path in args.paths:
        findings.extend(audit_path(Path(raw_path).resolve()))

    if findings:
        print("Sensitive public-source audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Sensitive public-source audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
