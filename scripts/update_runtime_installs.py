"""Reinstall the MCP into the runtime projects' virtualenvs from the fork.

Those projects do not run from a checkout: each has its own venv holding a package installed
from the fork, so editing a checkout changes nothing about what their agents execute. Only a
reinstall does, and doing it by hand is three easy mistakes:

* **Leftover path files.** ``pip`` removes ``__editable__.befree_bubble_mcp-*.pth`` on
  reinstall, but never removes ``befree_bubble_mcp_local.pth`` - the one
  ``scripts/install_local.py`` writes with a checkout's ``src`` path. Leave it behind and the
  venv keeps importing that checkout instead of what was just installed, with no error at all.
  This script deletes both before installing.
* **Believing pip.** A successful install says nothing about WHICH commit landed. The check
  here reads ``direct_url.json`` from the installed dist-info afterwards, which records the
  URL, the requested revision and the resolved commit.
* **Forgetting the restart.** A running Claude Code session keeps talking to the MCP process it
  already started. Nothing here can fix that, so it is printed at the end.

Usage:

    python scripts/update_runtime_installs.py               # dry run: what it would do
    python scripts/update_runtime_installs.py --execute
    python scripts/update_runtime_installs.py --execute --revision moabe-2026-09-04
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

FORK_URL = "https://github.com/moabe-br-2019/befree-bubble-mcp.git"
DEFAULT_REVISION = "main"

# Path files that must not survive a reinstall. The first is pip's own and it cleans that one
# up; the second it does not know about.
STALE_PTH_NAMES = ("befree_bubble_mcp_local.pth",)
STALE_PTH_GLOBS = ("__editable__.befree_bubble_mcp-*.pth",)


@dataclass(frozen=True)
class RuntimeProject:
    """One project whose agents run an installed copy rather than a checkout."""

    name: str
    venv: Path

    @property
    def python(self) -> Path:
        # Windows layout; these projects are Windows-only today.
        return self.venv / "Scripts" / "python.exe"

    @property
    def site_packages(self) -> Path:
        return self.venv / "Lib" / "site-packages"


def default_projects(dev_root: Path) -> list[RuntimeProject]:
    return [
        RuntimeProject("auton", dev_root / "auton" / "befree-bubble-mcp" / ".venv"),
        RuntimeProject("Orana", dev_root / "Orana" / "befree-bubble-mcp" / ".venv"),
    ]


def stale_path_files(project: RuntimeProject) -> list[Path]:
    found = [
        project.site_packages / name
        for name in STALE_PTH_NAMES
        if (project.site_packages / name).exists()
    ]
    for pattern in STALE_PTH_GLOBS:
        found.extend(sorted(project.site_packages.glob(pattern)))
    return found


def installed_revision(project: RuntimeProject) -> dict[str, object] | None:
    """What the venv actually holds, straight from pip's own record."""

    for dist_info in sorted(project.site_packages.glob("befree_bubble_mcp-*.dist-info")):
        record = dist_info / "direct_url.json"
        if not record.exists():
            continue
        try:
            payload = json.loads(record.read_text(encoding="utf-8"))
        except ValueError:
            continue
        info = payload.get("vcs_info") or {}
        return {
            "url": payload.get("url"),
            "requested": info.get("requested_revision"),
            "commit": info.get("commit_id"),
        }
    return None


def update(project: RuntimeProject, revision: str, *, execute: bool) -> bool:
    print(f"\n=== {project.name}")
    if not project.python.exists():
        print(f"  SKIPPED: no interpreter at {project.python}")
        return False

    before = installed_revision(project)
    print(f"  before: {before or 'nothing recorded'}")

    for path in stale_path_files(project):
        print(f"  remove: {path.name}")
        if execute:
            path.unlink()

    spec = f"befree-bubble-mcp @ git+{FORK_URL}@{revision}"
    command = [str(project.python), "-m", "pip", "install", "--force-reinstall", spec]
    print(f"  install: {revision}")
    if not execute:
        return True

    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(f"  FAILED ({result.returncode}):\n{result.stdout[-2000:]}{result.stderr[-2000:]}")
        return False

    after = installed_revision(project)
    print(f"  after : {after or 'nothing recorded'}")
    if not after or not after.get("commit"):
        print("  WARNING: pip reported success but recorded no commit; verify by hand.")
        return False
    if before and after.get("commit") == before.get("commit"):
        print("  note: same commit as before - the revision had nothing new.")
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--revision", default=DEFAULT_REVISION, help="branch, tag or commit on the fork")
    parser.add_argument("--dev-root", default=str(Path.home() / "Documents" / "DEV"))
    parser.add_argument("--execute", action="store_true", help="actually install; otherwise dry run")
    args = parser.parse_args(argv)

    projects = default_projects(Path(args.dev_root))
    print(f"fork     : {FORK_URL}")
    print(f"revision : {args.revision}")
    print(f"mode     : {'EXECUTE' if args.execute else 'dry run'}")

    ok = all([update(project, args.revision, execute=args.execute) for project in projects])

    if args.execute:
        print("\nRestart any Claude Code session using these projects: a running session keeps")
        print("talking to the MCP process it already started.")
    else:
        print("\nDry run only. Re-run with --execute to install.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
