"""MCP schema conversion for enabled declarative extension tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.context.mutation_overlay import record_mutation_overlay
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.extensions.models import ExtensionManifest
from bubble_mcp.extensions.runners import ExtensionRunnerCompileResult, compile_extension_runner
from bubble_mcp.extensions.store import extension_packs_dir, load_extension_manifest
from bubble_mcp.extensions.validator import validate_extension_pack
from bubble_mcp.server.agent_catalog import enhance_tool_schema
from bubble_mcp.sessions.store import load_session


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


def _compile_preview(
    template: dict[str, Any],
    args: dict[str, Any],
) -> ExtensionRunnerCompileResult | None:
    preview_session = load_session(str(args.get("profile") or "")) if args.get("profile") else None
    return compile_extension_runner(template, args, session=preview_session)


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
        raw_template = payload.get("template")
        template: dict[str, Any] = raw_template if isinstance(raw_template, dict) else {}
        compile_result = _compile_preview(template, args)
        compiled_payload = compile_result.write_payload if compile_result else None
        warnings = compile_result.warnings if compile_result else []
        compile_errors = compile_result.errors if compile_result else []
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
            "compiled_payload": redact_sensitive(compiled_payload) if compiled_payload else None,
            "warnings": warnings,
            "runner": compile_result.runner if compile_result else None,
            "runner_metadata": compile_result.metadata if compile_result else {},
            "message": (
                "Declarative extension tool preview generated locally. "
                "No Bubble write was executed."
            ),
        }
        if compile_result is not None and not compile_result.ok:
            return {
                **preview,
                "ok": False,
                "execute": execute,
                "error": "extension_runner_compile_failed",
                "runner_errors": compile_errors,
            }
        if execute:
            profile = str(args.get("profile") or "").strip()
            if compile_result is not None and compile_result.write_payload is not None:
                if not profile:
                    raise ValueError("Executable extension tools require profile.")
                write_session = load_session(profile)
                if write_session is None:
                    raise ValueError(f"No Bubble session stored for profile '{profile}'.")
                compile_result = compile_extension_runner(template, args, session=write_session)
                if compile_result is None or compile_result.write_payload is None:
                    return {
                        **preview,
                        "ok": False,
                        "error": "extension_tool_execution_not_implemented",
                        "execute": True,
                        "message": (
                            "This extension tool has no executable runner. "
                            "Call with execute=false to preview the enabled extension tool."
                        ),
                    }
                if not compile_result.ok:
                    return {
                        **preview,
                        "ok": False,
                        "error": "extension_runner_compile_failed",
                        "execute": True,
                        "runner": compile_result.runner,
                        "runner_errors": compile_result.errors,
                        "warnings": compile_result.warnings,
                    }
                compiled_payload = compile_result.write_payload
                write_result = BubbleEditorClient().write(compiled_payload, write_session, dry_run=False)
                if write_result.get("ok"):
                    record_mutation_overlay(
                        profile=profile,
                        app_id=str(
                            write_result.get("request", {}).get("payload", {}).get("appname")
                            or write_session.app_id
                        ),
                        payload=write_result.get("request", {}).get("payload") or compiled_payload,
                        source=name,
                        response=write_result.get("response"),
                    )
                return {
                    **preview,
                    "ok": bool(write_result.get("ok")),
                    "mode": "executed",
                    "execute": True,
                    "compiled_payload": redact_sensitive(compiled_payload),
                    "warnings": compile_result.warnings,
                    "runner": compile_result.runner,
                    "runner_metadata": compile_result.metadata,
                    "result": write_result,
                    "message": "Extension tool executed through its declared Bubble write runner.",
                }
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
