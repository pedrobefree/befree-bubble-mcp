"""Validation for declarative extension packs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.extensions.models import ExtensionValidationReport
from bubble_mcp.extensions.store import _validate_pack_tree, load_extension_manifest
from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES
from bubble_mcp.server.schema_families import native_tool_schemas


SECRET_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9_-]{8,}|bearer\s+[a-zA-Z0-9._-]+|"
    r"(?:api[_-]?key|authorization|password|secret)\s*[:=]\s*\S{6,})",
    re.IGNORECASE,
)


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(_walk_strings(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_walk_strings(child))
        return result
    if isinstance(value, str):
        return [value]
    return []


def _tool_path(pack_path: Path, relative: str) -> Path:
    root = pack_path.resolve(strict=True)
    tool_path = (pack_path / relative).resolve(strict=False)
    try:
        tool_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"exported tool escapes extension pack: {relative}") from exc
    return tool_path


def _load_tool_payload(tool_path: Path, relative: str) -> dict[str, Any]:
    if tool_path.is_symlink():
        raise ValueError(f"exported tool cannot be a symlink: {relative}")
    payload = json.loads(tool_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected exported tool object: {relative}")
    return payload


def validate_extension_pack(path: Path) -> ExtensionValidationReport:
    extension_id = ""
    errors: list[str] = []

    try:
        _validate_pack_tree(path)
        manifest = load_extension_manifest(path / "extension.json")
        extension_id = manifest.id
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return ExtensionValidationReport(ok=False, extension_id=extension_id, errors=[str(exc)])

    if not manifest.id:
        errors.append("manifest.id is required")
    if manifest.risk not in {"read_only", "mutating", "destructive"}:
        errors.append(f"unsupported risk: {manifest.risk}")

    native_names = {str(tool["name"]) for tool in native_tool_schemas()}
    blocked_names = native_names | set(ARIA_BUBBLE_TOOL_NAMES)
    seen_names: set[str] = set()

    for relative in manifest.exports.tools:
        try:
            tool_path = _tool_path(path, relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not tool_path.exists():
            errors.append(f"missing exported tool: {relative}")
            continue
        try:
            payload = _load_tool_payload(tool_path, relative)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            continue

        name = str(payload.get("name") or "").strip()
        if not name:
            errors.append(f"{relative} requires name")
        if name in blocked_names:
            errors.append(f"{relative} collides with existing tool: {name}")
        if name in seen_names:
            errors.append(f"{relative} duplicates extension tool: {name}")
        seen_names.add(name)

        for text in _walk_strings(payload):
            if SECRET_PATTERN.search(text):
                errors.append(f"{relative} contains possible secret")
                break

    return ExtensionValidationReport(ok=not errors, extension_id=manifest.id, errors=errors)
