from pathlib import Path

import sys

import pytest

from scripts import install_local
from scripts.install_local import (
    _repair_native_extension_policy,
    _stale_install_paths,
    _write_console_bootstrap,
    _write_local_editable_pth,
)


def test_stale_install_paths_detects_interrupted_editable_metadata(tmp_path: Path) -> None:
    editable = tmp_path / "__editable__.befree_bubble_mcp-0.1.0.pth"
    duplicate_editable = tmp_path / "__editable__.befree_bubble_mcp-0.1.0 2.pth"
    dist_info = tmp_path / "befree_bubble_mcp-0.1.0.dist-info"
    local_pth = tmp_path / "befree_bubble_mcp_local.pth"
    duplicate_package = tmp_path / "bubble_mcp 2"
    unrelated = tmp_path / "bubble_mcp"

    editable.write_text("src\n", encoding="utf-8")
    duplicate_editable.write_text("src\n", encoding="utf-8")
    local_pth.write_text("src\n", encoding="utf-8")
    dist_info.mkdir()
    duplicate_package.mkdir()
    unrelated.mkdir()

    stale_paths = {path.name for path in _stale_install_paths(tmp_path)}

    assert stale_paths == {
        "__editable__.befree_bubble_mcp-0.1.0.pth",
        "__editable__.befree_bubble_mcp-0.1.0 2.pth",
        "befree_bubble_mcp-0.1.0.dist-info",
        "befree_bubble_mcp_local.pth",
        "bubble_mcp 2",
    }


def test_write_local_editable_pth_points_to_source_dir(tmp_path: Path) -> None:
    source_dir = tmp_path / "checkout" / "src"
    source_dir.mkdir(parents=True)

    pth = _write_local_editable_pth(tmp_path, source_dir)

    assert pth.name == "befree_bubble_mcp_local.pth"
    assert pth.read_text(encoding="utf-8") == f"{source_dir}\n"


def test_write_console_bootstrap_injects_source_before_import(tmp_path: Path) -> None:
    script_path = tmp_path / "bin" / "bubble-mcp"
    python = tmp_path / "bin" / "python"
    source_dir = tmp_path / "checkout" / "src"

    _write_console_bootstrap(script_path, python, source_dir, "bubble_mcp.cli.main:main")

    text = script_path.read_text(encoding="utf-8")
    assert str(python) in text
    assert f"sys.path.insert(0, {str(source_dir)!r})" in text
    assert "from bubble_mcp.cli.main import main" in text
    assert script_path.stat().st_mode & 0o111


def test_repair_native_extension_policy_targets_only_native_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = tmp_path / "pkg" / "native.so"
    dylib = tmp_path / "pkg" / "native.dylib"
    pure_python = tmp_path / "pkg" / "module.py"
    native.parent.mkdir()
    native.write_bytes(b"native")
    dylib.write_bytes(b"native")
    pure_python.write_text("pass\n", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        install_local.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )

    _repair_native_extension_policy(tmp_path)

    flattened = [" ".join(command) for command in calls]
    assert any(str(native) in command and "codesign" in command for command in flattened)
    assert any(str(dylib) in command and "codesign" in command for command in flattened)
    assert all(str(pure_python) not in command for command in flattened)
