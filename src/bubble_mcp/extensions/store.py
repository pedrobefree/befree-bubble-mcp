"""Local config-dir storage for extension packs."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.extensions.models import (
    ExtensionManifest,
    ExtensionOperationReport,
    InstalledExtension,
)


STATE_FILENAME = "state.json"


def _validate_extension_id(extension_id: str) -> str:
    safe_id = str(extension_id or "").strip()
    if not safe_id:
        raise ValueError("Extension id is required.")
    if safe_id in {".", ".."} or "/" in safe_id or "\\" in safe_id:
        raise ValueError(f"Extension id must be a safe path segment: {extension_id}")
    return safe_id


def _ensure_under_base(path: Path, base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    resolved_base = base.resolve()
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Extension path escapes storage directory: {path}") from exc
    return resolved_path


def _extension_pack_path(extension_id: str) -> Path:
    packs = extension_packs_dir()
    path = packs / _validate_extension_id(extension_id)
    _ensure_under_base(path, packs)
    return path


def _iter_pack_paths(root: Path) -> Iterable[Path]:
    if root.is_symlink():
        raise ValueError(f"Extension packs cannot contain symlinks: {root}")
    resolved_root = root.resolve(strict=True)
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Extension packs cannot contain symlinks: {path}")
        resolved_path = path.resolve(strict=True)
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"Extension pack file escapes pack root: {path}") from exc
        yield path


def _validate_pack_tree(root: Path) -> None:
    if not root.is_dir():
        raise ValueError(f"Extension pack source must be a directory: {root}")
    for _path in _iter_pack_paths(root):
        pass


def extensions_dir() -> Path:
    return get_config_dir() / "extensions"


def extension_packs_dir() -> Path:
    return extensions_dir() / "packs"


def extension_state_path(extension_id: str) -> Path:
    return _extension_pack_path(extension_id) / STATE_FILENAME


def load_extension_manifest(path: Path) -> ExtensionManifest:
    if path.is_symlink():
        raise ValueError(f"Extension manifest cannot be a symlink: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected extension manifest object in {path}")
    return ExtensionManifest.from_dict(payload)


def _write_state(extension_id: str, state: str) -> None:
    path = extension_state_path(extension_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"state": state}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_state(extension_id: str) -> str:
    path = extension_state_path(extension_id)
    if not path.exists():
        return "pending"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload.get("state") or "pending")


def import_extension(source_dir: Path) -> ExtensionOperationReport:
    _validate_pack_tree(source_dir)
    manifest = load_extension_manifest(source_dir / "extension.json")
    extension_id = _validate_extension_id(manifest.id)
    target = _extension_pack_path(extension_id)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source_dir, target)
    _write_state(extension_id, "pending")
    return ExtensionOperationReport(ok=True, extension_id=extension_id, state="pending", path=target)


def _installed_from_path(path: Path) -> InstalledExtension:
    _validate_pack_tree(path)
    manifest = load_extension_manifest(path / "extension.json")
    return InstalledExtension(
        extension_id=manifest.id,
        state=_read_state(manifest.id),
        path=path,
        manifest=manifest,
    )


def list_extensions() -> list[InstalledExtension]:
    packs = extension_packs_dir()
    if not packs.exists():
        return []
    return [
        _installed_from_path(path)
        for path in sorted(packs.iterdir())
        if path.is_dir() and (path / "extension.json").exists()
    ]


def get_installed_extension(extension_id: str) -> InstalledExtension:
    path = _extension_pack_path(extension_id)
    if not (path / "extension.json").exists():
        raise ValueError(f"Unknown extension: {extension_id}")
    return _installed_from_path(path)


def enable_extension(extension_id: str) -> ExtensionOperationReport:
    installed = get_installed_extension(extension_id)
    _write_state(extension_id, "enabled")
    return ExtensionOperationReport(ok=True, extension_id=extension_id, state="enabled", path=installed.path)


def disable_extension(extension_id: str) -> ExtensionOperationReport:
    installed = get_installed_extension(extension_id)
    _write_state(extension_id, "disabled")
    return ExtensionOperationReport(ok=True, extension_id=extension_id, state="disabled", path=installed.path)


def export_extension(extension_id: str, output: Path) -> ExtensionOperationReport:
    installed = get_installed_extension(extension_id)
    _ensure_under_base(installed.path, extension_packs_dir())
    files: dict[str, Any] = {}
    for path in sorted(_iter_pack_paths(installed.path)):
        if path.is_file() and path.name != STATE_FILENAME:
            relative = path.relative_to(installed.path).as_posix()
            files[relative] = json.loads(path.read_text(encoding="utf-8"))
    payload = {"manifest": installed.manifest.to_dict(), "files": files}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ExtensionOperationReport(ok=True, extension_id=extension_id, state=installed.state, path=output)
