"""Where E2E suites, cases, fixtures and run artifacts live on disk.

Everything sits under the MCP config directory rather than inside the package, so a suite
belongs to whoever owns the machine's profiles - the same place ``settings.json`` and the
``run-as`` storage states already live. Nothing here is importable from the repository, and
run artifacts (video, screenshots) never land in a checkout.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bubble_mcp.core.config import get_config_dir

SUITE_SUFFIX = ".suite.json"
RESULT_FILENAME = "result.json"


def _is_within(path: Path, root: Path) -> bool:
    """Containment that survives Windows case folding and short-name spellings."""

    normalized = os.path.normcase(os.path.normpath(str(path)))
    base = os.path.normcase(os.path.normpath(str(root)))
    return normalized == base or normalized.startswith(base + os.sep)


def safe_slug(value: str, *, limit: int = 60) -> str:
    """Normalize a suite, case or profile name into something safe for a path segment."""

    text = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip())
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:limit]


def case_key(value: str) -> str:
    """Fold a case id to the identity a suite compares by.

    ``ks1-t23`` and ``KS1_T23`` are the same case: the module file a scaffold writes for either
    is ``ks1_t23.py``, so letting both into one manifest would have two entries fight over one
    file. Dash, underscore and case are therefore all the same thing here.
    """

    return re.sub(r"[-_]+", "-", safe_slug(value).lower()).strip("-")


def new_run_id() -> str:
    """A run id that sorts chronologically and never collides within a second."""

    return f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"


def safe_run_id(run_id: str = "") -> str:
    """Accept a caller supplied run id only in a shape that cannot escape the runs directory."""

    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(run_id or "").strip())
    value = re.sub(r"_+", "_", value).strip("_")[:40]
    return value or new_run_id()


def e2e_root(config_dir: Path | None = None) -> Path:
    return (config_dir or get_config_dir()) / "e2e"


def profile_root(profile: str, config_dir: Path | None = None) -> Path:
    return e2e_root(config_dir) / safe_slug(profile)


def suites_dir(profile: str, config_dir: Path | None = None) -> Path:
    return profile_root(profile, config_dir) / "suites"


def cases_dir(profile: str, config_dir: Path | None = None) -> Path:
    return profile_root(profile, config_dir) / "cases"


def fixtures_dir(profile: str, config_dir: Path | None = None) -> Path:
    return profile_root(profile, config_dir) / "fixtures"


def runs_dir(profile: str, config_dir: Path | None = None) -> Path:
    return profile_root(profile, config_dir) / "runs"


def suite_path(profile: str, suite: str, config_dir: Path | None = None) -> Path:
    return suites_dir(profile, config_dir) / f"{safe_slug(suite)}{SUITE_SUFFIX}"


def run_dir(profile: str, run_id: str, config_dir: Path | None = None) -> Path:
    return runs_dir(profile, config_dir) / safe_run_id(run_id)


def case_artifact_dir(
    profile: str, run_id: str, case_id: str, config_dir: Path | None = None
) -> Path:
    return run_dir(profile, run_id, config_dir) / safe_slug(case_id)


def result_path(profile: str, run_id: str, config_dir: Path | None = None) -> Path:
    return run_dir(profile, run_id, config_dir) / RESULT_FILENAME


def resolve_cases_root(
    profile: str, cases_root: str = "", config_dir: Path | None = None
) -> Path:
    """The directory a suite's case modules live in.

    By default that is the profile's own cases directory under the config dir. A suite may
    instead point at a checkout - an app's tests belong in the app's repository, and copying
    them here would create the second, drifting copy this harness exists to remove. The root
    is declared once, in the manifest; individual cases still cannot escape it.
    """

    raw = str(cases_root or "").strip()
    if not raw:
        return cases_dir(profile, config_dir)
    root = Path(raw).expanduser()
    if not root.is_absolute():
        root = (profile_root(profile, config_dir) / root).resolve()
    if not root.is_dir():
        raise ValueError(
            f"The suite's cases_root {root} is not an existing directory. Point it at the "
            "checkout that holds the case modules, or drop it to use the profile's own "
            "cases directory."
        )
    return root


def resolve_fixtures_root(
    profile: str, cases_root: str = "", config_dir: Path | None = None
) -> Path:
    """Where a case's upload fixtures live: beside its modules, wherever those are."""

    if not str(cases_root or "").strip():
        return fixtures_dir(profile, config_dir)
    root = resolve_cases_root(profile, cases_root, config_dir)
    # A checkout usually keeps e2e/cases/ and e2e/fixtures/ as siblings, so look one level
    # up as well before falling back to the profile's own fixtures.
    for candidate in (root / "fixtures", root.parent / "fixtures"):
        if candidate.is_dir():
            return candidate
    return fixtures_dir(profile, config_dir)


def resolve_case_module(
    profile: str,
    module_ref: str,
    config_dir: Path | None = None,
    *,
    cases_root: str = "",
) -> Path:
    """Resolve a suite's ``module`` reference, refusing anything outside the cases root.

    Case modules are executed, so the reference is the one place a suite file could turn into
    arbitrary code from somewhere else on disk. An absolute path, a ``..`` segment or a symlink
    pointing out of the tree is rejected rather than normalized.
    """

    raw = str(module_ref or "").strip()
    if not raw:
        raise ValueError("A case needs a module path, relative to the suite's cases directory.")
    candidate = Path(raw)
    if candidate.is_absolute() or candidate.drive or raw.startswith(("/", "\\")):
        raise ValueError(
            f"Case module {raw!r} must be relative to the cases directory, not an absolute path."
        )
    if any(part == ".." for part in candidate.parts):
        raise ValueError(f"Case module {raw!r} must not step outside the cases directory with '..'.")

    base = resolve_cases_root(profile, cases_root, config_dir)
    # Build from the resolved base so the containment check below compares like with like:
    # on Windows, Path.resolve() returns the on-disk spelling ("Documents\\DEV"), which a
    # plain string comparison against the configured spelling would reject.
    resolved_base = base.resolve() if base.exists() else base
    parts = list(candidate.parts)
    if parts and parts[0] == resolved_base.name:
        parts = parts[1:]
    target = resolved_base.joinpath(*parts) if parts else resolved_base
    if target.suffix != ".py":
        target = target.with_suffix(".py")

    # Only an existing file can be a symlink out of the tree; a path that is merely planned
    # is contained by construction, since '..' and absolute references were already refused.
    if target.exists() and not _is_within(target.resolve(), resolved_base):
        raise ValueError(f"Case module {raw!r} resolves outside {resolved_base}.")
    return target
