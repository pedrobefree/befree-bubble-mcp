"""Small shared helpers for execution modules."""

from __future__ import annotations

from typing import Any


def extract_write_payload(step: dict[str, Any]) -> dict[str, Any] | None:
    raw_args = step.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    candidate = args.get("write_payload") or args.get("payload") or step.get("write_payload")
    return candidate if isinstance(candidate, dict) else None
