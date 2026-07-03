#!/usr/bin/env python3
"""Install or repair a local editable Bubble MCP checkout.

This script is intentionally stdlib-only so it can run before the package is
importable. It repairs stale editable-install metadata left by interrupted pip
installs, then installs the checkout into the selected virtual environment.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PACKAGE_NAME = "befree-bubble-mcp"
DIST_NAME = "befree_bubble_mcp"


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, check=False)


def _capture(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def _site_packages(python: Path, cwd: Path) -> Path:
    code = "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    output = _capture([str(python), "-c", code], cwd=cwd)
    if not output:
        raise RuntimeError(f"Could not resolve site-packages for {python}")
    return Path(output.splitlines()[-1]).expanduser()


def _stale_install_paths(site_packages: Path) -> list[Path]:
    candidates: list[Path] = []
    patterns = [
        f"__editable__.{DIST_NAME}-*.pth",
        f"__editable__.{DIST_NAME}-*",
        f"{DIST_NAME}-*.dist-info",
        "bubble_mcp *",
    ]
    for pattern in patterns:
        candidates.extend(site_packages.glob(pattern))
    return sorted(set(candidates))


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _ensure_venv(venv: Path) -> Path:
    python = _venv_python(venv)
    if not python.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    return python


def install_local(*, root: Path, venv: Path, extras: str, repair: bool) -> int:
    python = _ensure_venv(venv)
    site_packages = _site_packages(python, root)

    if repair:
        print(f"Repairing editable install metadata in {site_packages}")
        _capture([str(python), "-m", "pip", "uninstall", "-y", PACKAGE_NAME, "bubble-mcp"], cwd=root)
        for path in _stale_install_paths(site_packages):
            _remove_path(path)

    upgrade_result = _run([str(python), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"], cwd=root)
    if upgrade_result.returncode != 0:
        return upgrade_result.returncode

    target = "-e"
    spec = f".[{extras}]" if extras else "."
    install_result = _run([str(python), "-m", "pip", "install", target, spec], cwd=root)
    if install_result.returncode != 0:
        return install_result.returncode

    import_result = _run([str(python), "-c", "import bubble_mcp; print(bubble_mcp.__file__)"], cwd=root)
    if import_result.returncode == 0:
        print("Bubble MCP local install is importable.")
    return import_result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install or repair a local Bubble MCP editable checkout.")
    parser.add_argument("--venv", default=".venv", help="Virtual environment path. Defaults to .venv.")
    parser.add_argument(
        "--extras",
        default="browser",
        help='Optional extras to install, for example "browser" or "browser,dev".',
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Remove stale editable-install metadata before installing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd().resolve()
    return install_local(
        root=root,
        venv=(root / args.venv).resolve(),
        extras=args.extras,
        repair=args.repair,
    )


if __name__ == "__main__":
    raise SystemExit(main())
