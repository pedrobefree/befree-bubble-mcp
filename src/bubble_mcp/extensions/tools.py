"""MCP schema conversion for enabled declarative extension tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.extensions.store import extension_packs_dir, load_extension_manifest
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.server.agent_catalog import enhance_tool_schema


def _pack_state(pack_path: Path) -> str:
    state_path = pack_path / "state.json"
    if not state_path.exists():
        return "pending"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "pending"
    if not isinstance(payload, dict):
        return "pending"
    return str(payload.get("state") or "pending")


def _enabled_pack_paths() -> list[Path]:
    packs = extension_packs_dir()
    if not packs.exists():
        return []
    return [
        path
        for path in sorted(packs.iterdir())
        if path.is_dir() and (path / "extension.json").exists() and _pack_state(path) == "enabled"
    ]


def enabled_extension_tool_schemas() -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for pack_path in _enabled_pack_paths():
        report = validate_extension_pack(pack_path)
        if not report.ok:
            continue
        try:
            manifest = load_extension_manifest(pack_path / "extension.json")
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for relative in manifest.exports.tools:
            try:
                payload = json.loads((pack_path / relative).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            schema = enhance_tool_schema(payload)
            if isinstance(payload.get("description"), str):
                schema["description"] = payload["description"]
            if isinstance(payload.get("annotations"), dict):
                schema["annotations"] = payload["annotations"]
            name = str(schema.get("name") or "")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            schemas.append(schema)
    return schemas
