from pathlib import Path

import sys
import subprocess

import pytest

from scripts import install_local
from scripts.install_local import (
    _clear_macos_execution_metadata,
    _repair_native_extension_policy,
    _remove_stale_console_script_duplicates,
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

    payload = (tmp_path / "bin" / "bubble-mcp.py").read_text(encoding="utf-8")
    assert f"sys.path.insert(0, {str(source_dir)!r})" in payload
    assert "from bubble_mcp.cli.main import main" in payload
    if script_path.read_bytes().startswith(b"#!"):
        text = script_path.read_text(encoding="utf-8")
        assert str(python) in text
        assert text.startswith("#!/bin/sh")
    assert script_path.stat().st_mode & 0o111


def test_write_console_bootstrap_runs_directly(tmp_path: Path) -> None:
    script_path = tmp_path / "bin" / "bubble-mcp"
    source_dir = tmp_path / "checkout" / "src"
    module_dir = source_dir / "bubble_mcp" / "cli"
    module_dir.mkdir(parents=True)
    (source_dir / "bubble_mcp" / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "main.py").write_text(
        "import sys\n"
        "def main():\n"
        "    print(sys.argv[0])\n"
        "    print('|'.join(sys.argv[1:]))\n"
        "    return 0\n",
        encoding="utf-8",
    )

    _write_console_bootstrap(script_path, Path(sys.executable), source_dir, "bubble_mcp.cli.main:main")

    result = subprocess.run(
        [str(script_path), "tools", "search", "--query", "html selector import"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "bubble-mcp",
        "tools|search|--query|html selector import",
    ]


def test_remove_stale_console_script_duplicates(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    canonical = bindir / "bubble-mcp"
    duplicate = bindir / "bubble-mcp 2"
    server_duplicate = bindir / "bubble-mcp-server 3"
    unrelated = bindir / "pytest 2"
    for path in [canonical, duplicate, server_duplicate, unrelated]:
        path.write_text("script\n", encoding="utf-8")

    _remove_stale_console_script_duplicates(tmp_path)

    assert canonical.exists()
    assert not duplicate.exists()
    assert not server_duplicate.exists()
    assert unrelated.exists()


def test_clear_macos_execution_metadata_removes_quarantine_and_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "bubble-mcp"
    script.write_text("script\n", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        install_local.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )

    _clear_macos_execution_metadata(script)

    assert ["xattr", "-d", "com.apple.quarantine", str(script)] in calls
    assert ["xattr", "-d", "com.apple.provenance", str(script)] in calls


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
