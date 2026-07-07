"""Validation for declarative extension packs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.extensions.models import ExtensionValidationReport
from bubble_mcp.extensions.store import _validate_extension_id, _validate_pack_tree, load_extension_manifest
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


def _export_path(pack_path: Path, relative: str, *, label: str) -> Path:
    root = pack_path.resolve(strict=True)
    exported_path = (pack_path / relative).resolve(strict=False)
    try:
        exported_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"exported {label} escapes extension pack: {relative}") from exc
    return exported_path


def _load_tool_payload(tool_path: Path, relative: str) -> dict[str, Any]:
    if tool_path.is_symlink():
        raise ValueError(f"exported tool cannot be a symlink: {relative}")
    payload = json.loads(tool_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected exported tool object: {relative}")
    return payload


def _native_available_tool_names() -> set[str]:
    names = {str(tool.get("name") or "") for tool in native_tool_schemas()}
    names.update(ARIA_BUBBLE_TOOL_NAMES)
    return {name for name in names if name}


def _validate_tool_input_schema(relative: str, payload: dict[str, Any], errors: list[str]) -> None:
    raw_schema = payload.get("inputSchema")
    if not isinstance(raw_schema, dict):
        errors.append(f"{relative} requires object inputSchema")
        return
    if raw_schema.get("type") != "object":
        errors.append(f"{relative} inputSchema.type must be object")
    raw_properties = raw_schema.get("properties", {})
    if not isinstance(raw_properties, dict):
        errors.append(f"{relative} inputSchema.properties must be an object")
        raw_properties = {}
    for property_name, property_schema in raw_properties.items():
        if not isinstance(property_name, str) or not property_name.strip():
            errors.append(f"{relative} inputSchema property names must be non-empty strings")
        if not isinstance(property_schema, dict):
            errors.append(f"{relative} inputSchema property {property_name} must be an object")
    raw_required = raw_schema.get("required", [])
    if raw_required is None:
        raw_required = []
    if not isinstance(raw_required, list):
        errors.append(f"{relative} inputSchema.required must be a list")
        raw_required = []
    for required_name in raw_required:
        if not isinstance(required_name, str) or not required_name.strip():
            errors.append(f"{relative} inputSchema.required entries must be non-empty strings")
            continue
        if raw_properties and required_name not in raw_properties:
            errors.append(f"{relative} requires unknown inputSchema property: {required_name}")

    risk = str(payload.get("risk") or "").strip()
    annotations = payload.get("annotations")
    is_mutating = risk in {"mutating", "destructive"}
    if isinstance(annotations, dict) and annotations.get("readOnlyHint") is False:
        is_mutating = True
    if not is_mutating:
        return
    execute_schema = raw_properties.get("execute")
    if not isinstance(execute_schema, dict):
        errors.append(f"{relative} mutating tools require boolean execute input")
        return
    if execute_schema.get("type") != "boolean":
        errors.append(f"{relative} execute input must be boolean")
    if execute_schema.get("default") is not False:
        errors.append(f"{relative} execute input default must be false")


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
    else:
        try:
            _validate_extension_id(manifest.id)
        except ValueError as exc:
            errors.append(str(exc))
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
        if name:
            seen_names.add(name)

        _validate_tool_input_schema(relative, payload, errors)

        for text in _walk_strings(payload):
            if SECRET_PATTERN.search(text):
                errors.append(f"{relative} contains possible secret")
                break

    for relative in manifest.exports.skills:
        try:
            skill_path = _export_path(path, relative, label="skill")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not skill_path.exists():
            errors.append(f"missing exported skill: {relative}")
            continue
        if skill_path.is_symlink():
            errors.append(f"exported skill cannot be a symlink: {relative}")
            continue
        from bubble_mcp.skills.validator import validate_skill_file

        report = validate_skill_file(skill_path, available_tools=_native_available_tool_names())
        if not report.get("ok"):
            for error in report.get("errors", []):
                errors.append(f"{relative}: {error}")
            continue
        for text in _walk_strings(json.loads(skill_path.read_text(encoding="utf-8"))):
            if SECRET_PATTERN.search(text):
                errors.append(f"{relative} contains possible secret")
                break

    return ExtensionValidationReport(ok=not errors, extension_id=manifest.id, errors=errors)
