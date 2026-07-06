"""MCP schema conversion for enabled declarative extension tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.extensions.models import ExtensionManifest
from bubble_mcp.extensions.store import extension_packs_dir, load_extension_manifest
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.server.agent_catalog import enhance_tool_schema


EXTENSION_TOOL_USAGE_HINT = (
    " Use bubble_extension_call with execute=false for a safe preview when direct calling is unavailable."
)


@dataclass(frozen=True)
class EnabledExtensionTool:
    pack_path: Path
    manifest: ExtensionManifest
    relative_path: str
    payload: dict[str, Any]
    schema: dict[str, Any]


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
    return [entry.schema for entry in enabled_extension_tool_entries()]


def enabled_extension_tool_entries() -> list[EnabledExtensionTool]:
    tools: list[EnabledExtensionTool] = []
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
                description = payload["description"].strip()
                schema["description"] = (
                    description
                    if len(description) >= 80
                    else f"{description}{EXTENSION_TOOL_USAGE_HINT}"
                )
            if isinstance(payload.get("annotations"), dict):
                schema["annotations"] = payload["annotations"]
            name = str(schema.get("name") or "")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            tools.append(
                EnabledExtensionTool(
                    pack_path=pack_path,
                    manifest=manifest,
                    relative_path=relative,
                    payload=payload,
                    schema=schema,
                )
            )
    return tools


def preview_extension_tool_call(tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Return a safe preview for one enabled declarative extension tool."""

    name = str(tool_name or "").strip()
    if not name:
        raise ValueError("bubble_extension_call requires tool.")

    args = dict(arguments or {})
    for entry in enabled_extension_tool_entries():
        manifest = entry.manifest
        payload = entry.payload
        schema = entry.schema
        if str(schema.get("name") or "") != name:
            continue

        raw_input_schema = schema.get("inputSchema")
        input_schema = raw_input_schema if isinstance(raw_input_schema, dict) else {}
        raw_required = input_schema.get("required")
        required = raw_required if isinstance(raw_required, list) else []
        missing = [str(field) for field in required if args.get(str(field)) in (None, "")]
        if missing:
            return {
                "ok": False,
                "error": "extension_tool_missing_required_arguments",
                "tool": name,
                "extension_id": manifest.id,
                "missing": missing,
                "required": [str(field) for field in required],
            }

        execute = bool(args.get("execute", False))
        template = payload.get("template") if isinstance(payload.get("template"), dict) else {}
        preview = {
            "ok": True,
            "tool": name,
            "extension_id": manifest.id,
            "extension_name": manifest.name,
            "extension_version": manifest.version,
            "source": {"pack_path": str(entry.pack_path), "tool_path": entry.relative_path},
            "mode": "preview",
            "execute": False,
            "arguments": redact_sensitive(args),
            "schema": schema,
            "template": redact_sensitive(template),
            "message": (
                "Declarative extension tool preview generated locally. "
                "No Bubble write was executed."
            ),
        }
        if execute:
            return {
                **preview,
                "ok": False,
                "error": "extension_tool_execution_not_implemented",
                "execute": True,
                "message": (
                    "Declarative extension execution is not implemented yet. "
                    "Call with execute=false to preview the enabled extension tool."
                ),
            }
        return preview

    raise ValueError(f"Unknown enabled extension tool: {name}")
