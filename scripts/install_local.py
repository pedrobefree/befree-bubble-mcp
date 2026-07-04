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
import tempfile
from pathlib import Path


PACKAGE_NAME = "befree-bubble-mcp"
DIST_NAME = "befree_bubble_mcp"
LOCAL_PTH_NAME = "befree_bubble_mcp_local.pth"
CONSOLE_SCRIPTS = {
    "bubble-mcp": "bubble_mcp.cli.main:main",
    "bubble-mcp-server": "bubble_mcp.server.stdio:main",
    "bubble-mcp-figma-bridge": "bubble_mcp.figma_bridge:main",
}


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _venv_script(venv: Path, name: str) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, check=False)


def _capture(command: list[str], *, cwd: Path) -> str:
    return _capture_result(command, cwd=cwd).stdout_text


class CapturedProcess:
    def __init__(self, returncode: int, stdout_text: str) -> None:
        self.returncode = returncode
        self.stdout_text = stdout_text


def _capture_result(command: list[str], *, cwd: Path) -> CapturedProcess:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CapturedProcess(result.returncode, (result.stdout + result.stderr).strip())


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
        LOCAL_PTH_NAME,
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


def _clear_macos_hidden_flag(path: Path) -> None:
    if sys.platform != "darwin" or not path.exists():
        return
    subprocess.run(["chflags", "nohidden", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _repair_pth_visibility(site_packages: Path) -> None:
    for path in site_packages.glob("*.pth"):
        _clear_macos_hidden_flag(path)


def _repair_venv_visibility(venv: Path) -> None:
    if sys.platform != "darwin" or not venv.exists():
        return
    subprocess.run(["chflags", "-R", "nohidden", str(venv)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    for path in bindir.glob("python*"):
        subprocess.run(["chflags", "-h", "nohidden", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _repair_native_extension_policy(site_packages: Path) -> None:
    if sys.platform != "darwin" or not site_packages.exists():
        return
    for path in site_packages.rglob("*"):
        if not path.is_file() or path.suffix not in {".so", ".dylib"}:
            continue
        subprocess.run(["xattr", "-d", "com.apple.quarantine", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["codesign", "--force", "--sign", "-", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write_local_editable_pth(site_packages: Path, source_dir: Path) -> Path:
    path = site_packages / LOCAL_PTH_NAME
    path.write_text(f"{source_dir}\n", encoding="utf-8")
    _clear_macos_hidden_flag(path)
    return path


def _write_console_bootstrap(script_path: Path, python: Path, source_dir: Path, target: str) -> None:
    module_name, function_name = target.split(":", 1)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    if script_path.exists() or script_path.is_symlink():
        script_path.unlink()
    executable_name = script_path.name.removesuffix(".exe")
    body = "\n".join(
        [
            f"#!{python}",
            "import sys",
            f"sys.path.insert(0, {str(source_dir)!r})",
            f"from {module_name} import {function_name}",
            "",
            "if __name__ == '__main__':",
            f"    sys.argv[0] = {executable_name!r}",
            f"    raise SystemExit({function_name}())",
            "",
        ]
    )
    script_path.write_text(body, encoding="utf-8")
    script_path.chmod(0o755)
    _clear_macos_hidden_flag(script_path)


def _write_console_bootstraps(venv: Path, python: Path, source_dir: Path) -> None:
    for script_name, target in CONSOLE_SCRIPTS.items():
        _write_console_bootstrap(_venv_script(venv, script_name), python, source_dir, target)


def _ensure_venv(venv: Path) -> Path:
    python = _venv_python(venv)
    if not python.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    return python


def install_local(*, root: Path, venv: Path, extras: str, repair: bool) -> int:
    python = _ensure_venv(venv)
    _repair_venv_visibility(venv)
    site_packages = _site_packages(python, root)

    if repair:
        print(f"Repairing editable install metadata in {site_packages}", flush=True)
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

    _repair_venv_visibility(venv)
    _repair_pth_visibility(site_packages)
    _repair_native_extension_policy(site_packages)
    source_dir = root / "src"
    _write_local_editable_pth(site_packages, source_dir)
    _write_console_bootstraps(venv, python, source_dir)
    _repair_venv_visibility(venv)

    with tempfile.TemporaryDirectory(prefix="bubble-mcp-install-check-") as temp_dir:
        import_check = _capture_result(
            [str(python), "-c", "import bubble_mcp; print(bubble_mcp.__file__)"],
            cwd=Path(temp_dir),
        )
    if import_check.returncode != 0:
        print(import_check.stdout_text)
        return import_check.returncode
    print("Bubble MCP local install is importable.")

    console_script = _venv_script(venv, "bubble-mcp")
    if console_script.exists():
        help_output = _capture_result([str(console_script), "--help"], cwd=root)
        if help_output.returncode != 0 or "Manage Bubble app profiles." not in help_output.stdout_text:
            print(help_output.stdout_text)
            return help_output.returncode or 1
        print("bubble-mcp console script is runnable.")
    if "browser" in {extra.strip() for extra in extras.split(",")}:
        browser_check = _capture_result(
            [str(python), "-c", "from playwright.sync_api import sync_playwright; print(sync_playwright)"],
            cwd=root,
        )
        if browser_check.returncode != 0:
            print(browser_check.stdout_text)
            return browser_check.returncode
        print("Playwright browser dependency is importable.")
    return 0


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
