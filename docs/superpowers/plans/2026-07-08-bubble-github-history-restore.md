# Bubble GitHub History Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Bubble app history module that snapshots sanitized parsed `.bubble` modules into Git/GitHub and can preview-first restore earlier versions of pages, reusables, elements, workflows, styles, API Connector structure, and schema artifacts.

**Architecture:** Add a `bubble_mcp.history` package that treats detected `.bubble` exports and split `bubble_modules` as the versioned source of truth, with Git branches mapped from Bubble app versions. Restoration is a two-phase workflow: locate historical module data, compile a redacted restore plan into Bubble `/appeditor/write` payloads or existing tool operations, then execute only with explicit confirmation.

**Tech Stack:** Python 3.11, existing `bubble_mcp.vendor.bubble_modules`, existing context detector output under `BUBBLE_MCP_CONFIG_DIR`, subprocess Git CLI, existing branch/changelog/profile APIs, pytest.

---

## Scope Check

This plan covers Git-backed Bubble snapshots and restoration planning/execution. It does not implement cross-project transfer; that belongs to the separate `bubble_mcp.transfer` plan. This module restores previous versions inside the same Bubble app/profile/branch lineage.

## Existing Code Anchors

- `src/bubble_mcp/context/detector.py`: creates cached `.bubble`, split `bubble_modules`, compact context, and crawler fallback.
- `src/bubble_mcp/vendor/bubble_modules.py`: split/merge implementation for `.bubble` exports.
- `src/bubble_mcp/execution/editor_api.py`: authenticated Bubble editor API client primitives.
- `src/bubble_mcp/compiler/payload.py`: existing payload compilation helpers for supported object families.
- `src/bubble_mcp/server/schema_families.py`: MCP schema definitions.
- `src/bubble_mcp/server/tools.py`: MCP dispatch.
- `src/bubble_mcp/cli/main.py`: branch and changelog command patterns.
- `docs/context-engine.md`: documents cached raw export and split module paths.
- `docs/source-audit.md`: documents sensitive generated project data that must not be committed publicly by default.

## File Structure

- Create `src/bubble_mcp/history/__init__.py`: public exports.
- Create `src/bubble_mcp/history/models.py`: dataclasses for repository config, snapshots, historical references, restore plans, and evidence.
- Create `src/bubble_mcp/history/paths.py`: resolve profile context paths and snapshot repository layout.
- Create `src/bubble_mcp/history/sanitize.py`: redact private values before Git commit.
- Create `src/bubble_mcp/history/git_store.py`: isolated Git operations with allowlisted commands.
- Create `src/bubble_mcp/history/snapshot.py`: create sanitized snapshots from current detected context.
- Create `src/bubble_mcp/history/locator.py`: locate historical modules by ref and object selector.
- Create `src/bubble_mcp/history/restore.py`: build preview-first restore plans.
- Create `src/bubble_mcp/history/runtime.py`: MCP/CLI runtime entrypoints.
- Create `tests/fixtures/history/current_modules/`: sanitized minimal module fixture.
- Create `tests/fixtures/history/previous_modules/`: sanitized previous-version fixture.
- Create `tests/unit/test_history_sanitize.py`
- Create `tests/unit/test_history_git_store.py`
- Create `tests/unit/test_history_snapshot.py`
- Create `tests/unit/test_history_locator.py`
- Create `tests/unit/test_history_restore.py`
- Modify `src/bubble_mcp/server/schema_families.py`: expose history tools.
- Modify `src/bubble_mcp/server/tools.py`: dispatch history tools.
- Modify `src/bubble_mcp/server/agent_catalog.py`: descriptions and routing hints.
- Modify `src/bubble_mcp/server/agent_guide.py`: route history/version/restore requests.
- Modify `src/bubble_mcp/runtime_coverage.py`: include history native tools.
- Modify `src/bubble_mcp/cli/main.py`: add `bubble-mcp history ...` commands.
- Modify `docs/context-engine.md`, `docs/cli-reference.md`, `docs/mcp-clients.md`, and `docs/source-audit.md`: document snapshot, branch mapping, redaction, and restore safety.
- Modify `tests/unit/test_mcp_server.py` and `tests/unit/test_cli_commands.py`: schema, dispatch, and CLI coverage.

## Repository Layout

Default local snapshot repo:

```text
${BUBBLE_MCP_CONFIG_DIR}/history/{profile}/{app_id}/repo
```

Sanitized committed tree:

```text
manifest.json
modules/{app_id}/root.json
modules/{app_id}/manifest.json
modules/{app_id}/pages/...
modules/{app_id}/styles/...
modules/{app_id}/workflows/...
modules/{app_id}/user_types/...
modules/{app_id}/option_sets/...
modules/{app_id}/settings/...
```

Git branch mapping:

```text
Bubble app_version "test" -> Git branch "bubble/test"
Bubble app_version "live" -> Git branch "bubble/live"
Bubble app_version "feature-x" -> Git branch "bubble/feature-x"
```

Remote GitHub is optional and explicit. The module can create local snapshots without a remote.

## Public Tool Contract

Tools:

```text
bubble_history_snapshot
bubble_history_list
bubble_history_diff
bubble_history_restore_plan
bubble_history_restore_execute
```

Restore plan arguments:

```json
{
  "profile": "smoke",
  "app_id": "bovichain-g3",
  "app_version": "test",
  "git_ref": "bubble/test~3",
  "object_type": "style",
  "object_ref": "Primary Button",
  "target_context": "index",
  "target_parent": "root",
  "execute": false
}
```

Restore execution requires:

```json
{
  "profile": "smoke",
  "plan_path": "/absolute/path/to/restore-plan.json",
  "execute": true,
  "confirm": true
}
```

---

### Task 1: Models and Path Resolution

**Files:**
- Create: `src/bubble_mcp/history/__init__.py`
- Create: `src/bubble_mcp/history/models.py`
- Create: `src/bubble_mcp/history/paths.py`
- Test: `tests/unit/test_history_paths.py`

- [ ] **Step 1: Write failing path/model tests**

Create `tests/unit/test_history_paths.py`:

```python
from pathlib import Path

from bubble_mcp.history.paths import branch_name_for_app_version, history_repo_dir


def test_branch_name_for_app_version_is_stable_and_safe() -> None:
    assert branch_name_for_app_version("test") == "bubble/test"
    assert branch_name_for_app_version("live") == "bubble/live"
    assert branch_name_for_app_version("feature checkout") == "bubble/feature-checkout"
    assert branch_name_for_app_version("feature/foo") == "bubble/feature-foo"


def test_history_repo_dir_uses_config_profile_and_app(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    assert history_repo_dir("cliente2", "courselaunch") == Path(tmp_path) / "history" / "cliente2" / "courselaunch" / "repo"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_paths.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history'`.

- [ ] **Step 3: Implement models**

Create `src/bubble_mcp/history/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


HistoryObjectType = Literal["page", "reusable", "element", "workflow", "style", "api_connector", "data_type", "option_set"]
RestoreStatus = Literal["planned", "executed", "failed"]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SnapshotRequest:
    profile: str
    app_id: str
    app_version: str
    remote_url: str | None = None
    push: bool = False


@dataclass(frozen=True)
class SnapshotResult:
    ok: bool
    profile: str
    app_id: str
    app_version: str
    branch: str
    repo_dir: Path
    commit: str | None
    changed: bool
    sanitized_files: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile": self.profile,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "branch": self.branch,
            "repo_dir": str(self.repo_dir),
            "commit": self.commit,
            "changed": self.changed,
            "sanitized_files": self.sanitized_files,
        }


@dataclass(frozen=True)
class RestoreTarget:
    object_type: HistoryObjectType
    object_ref: str
    target_context: str | None = None
    target_parent: str | None = None


@dataclass(frozen=True)
class RestorePlan:
    plan_id: str
    profile: str
    app_id: str
    app_version: str
    git_ref: str
    target: RestoreTarget
    payloads: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: RestoreStatus = "planned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "profile": self.profile,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "git_ref": self.git_ref,
            "target": {
                "object_type": self.target.object_type,
                "object_ref": self.target.object_ref,
                "target_context": self.target.target_context,
                "target_parent": self.target.target_parent,
            },
            "payloads": self.payloads,
            "warnings": self.warnings,
            "status": self.status,
        }
```

- [ ] **Step 4: Implement path helpers**

Create `src/bubble_mcp/history/paths.py`:

```python
from __future__ import annotations

import os
import re
from pathlib import Path


def _config_dir() -> Path:
    return Path(os.environ.get("BUBBLE_MCP_CONFIG_DIR", Path.home() / ".config" / "bubble-mcp")).expanduser()


def safe_branch_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip("-./")
    return cleaned or "test"


def branch_name_for_app_version(app_version: str) -> str:
    version = app_version or "test"
    return f"bubble/{safe_branch_segment(version)}"


def history_base_dir(profile: str, app_id: str) -> Path:
    return _config_dir() / "history" / profile / app_id


def history_repo_dir(profile: str, app_id: str) -> Path:
    return history_base_dir(profile, app_id) / "repo"


def context_modules_dir(profile: str, app_id: str) -> Path:
    return _config_dir() / "contexts" / profile / "bubble_modules" / app_id
```

Create `src/bubble_mcp/history/__init__.py`:

```python
"""Git-backed Bubble history and restore workflows."""

from bubble_mcp.history.paths import branch_name_for_app_version, history_repo_dir

__all__ = ["branch_name_for_app_version", "history_repo_dir"]
```

- [ ] **Step 5: Run path tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_paths.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 6: Commit model/path slice**

Run:

```bash
git add src/bubble_mcp/history/__init__.py src/bubble_mcp/history/models.py src/bubble_mcp/history/paths.py tests/unit/test_history_paths.py
git commit -m "feat: add bubble history models and paths"
```

---

### Task 2: Sanitization

**Files:**
- Create: `src/bubble_mcp/history/sanitize.py`
- Test: `tests/unit/test_history_sanitize.py`

- [ ] **Step 1: Write failing sanitization test**

Create `tests/unit/test_history_sanitize.py`:

```python
from bubble_mcp.history.sanitize import sanitize_module_data


def test_sanitize_module_data_redacts_private_connector_and_session_values() -> None:
    raw = {
        "api": {
            "call1": {
                "properties": {
                    "name": "Private call",
                    "headers": {"Authorization": "Bearer secret", "X-Public": "ok"},
                    "private_key": "abc",
                    "url": "https://api.example.com",
                }
            }
        },
        "settings": {"cookies": "session-cookie", "normal": "kept"},
    }

    sanitized = sanitize_module_data(raw)

    assert sanitized["api"]["call1"]["properties"]["headers"]["Authorization"] == "[REDACTED]"
    assert sanitized["api"]["call1"]["properties"]["headers"]["X-Public"] == "ok"
    assert sanitized["api"]["call1"]["properties"]["private_key"] == "[REDACTED]"
    assert sanitized["settings"]["cookies"] == "[REDACTED]"
    assert sanitized["settings"]["normal"] == "kept"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_sanitize.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history.sanitize'`.

- [ ] **Step 3: Implement sanitizer**

Create `src/bubble_mcp/history/sanitize.py`:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any


SECRET_KEY_FRAGMENTS = (
    "authorization",
    "bearer",
    "cookie",
    "cookies",
    "secret",
    "token",
    "password",
    "private_key",
    "client_secret",
    "access_token",
    "refresh_token",
    "api_key",
)


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def sanitize_module_data(value: Any) -> Any:
    data = deepcopy(value)
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for key, child in data.items():
            if _is_secret_key(str(key)):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_module_data(child)
        return sanitized
    if isinstance(data, list):
        return [sanitize_module_data(item) for item in data]
    return data
```

- [ ] **Step 4: Run sanitizer tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_sanitize.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit sanitizer slice**

Run:

```bash
git add src/bubble_mcp/history/sanitize.py tests/unit/test_history_sanitize.py
git commit -m "feat: redact sensitive bubble history data"
```

---

### Task 3: Git Store

**Files:**
- Create: `src/bubble_mcp/history/git_store.py`
- Test: `tests/unit/test_history_git_store.py`

- [ ] **Step 1: Write failing Git store tests**

Create `tests/unit/test_history_git_store.py`:

```python
from pathlib import Path

from bubble_mcp.history.git_store import ensure_repo, git_current_branch, git_has_changes


def test_ensure_repo_creates_repo_and_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"

    ensure_repo(repo, branch="bubble/test", remote_url=None)

    assert (repo / ".git").exists()
    assert git_current_branch(repo) == "bubble/test"
    assert git_has_changes(repo) is False
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_git_store.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history.git_store'`.

- [ ] **Step 3: Implement Git store**

Create `src/bubble_mcp/history/git_store.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def ensure_repo(repo: Path, *, branch: str, remote_url: str | None) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _run_git(repo, ["init"])
    _run_git(repo, ["checkout", "-B", branch])
    if remote_url:
        remotes = _run_git(repo, ["remote"]).splitlines()
        if "origin" in remotes:
            _run_git(repo, ["remote", "set-url", "origin", remote_url])
        else:
            _run_git(repo, ["remote", "add", "origin", remote_url])


def git_current_branch(repo: Path) -> str:
    return _run_git(repo, ["branch", "--show-current"])


def git_has_changes(repo: Path) -> bool:
    return bool(_run_git(repo, ["status", "--porcelain"]))


def commit_all(repo: Path, message: str) -> str | None:
    _run_git(repo, ["add", "."])
    if not git_has_changes(repo):
        return None
    _run_git(repo, ["commit", "-m", message])
    return _run_git(repo, ["rev-parse", "HEAD"])


def push_branch(repo: Path, branch: str) -> None:
    _run_git(repo, ["push", "-u", "origin", branch])


def show_file(repo: Path, git_ref: str, path: str) -> str:
    return _run_git(repo, ["show", f"{git_ref}:{path}"])
```

- [ ] **Step 4: Run Git store tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_git_store.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit Git store slice**

Run:

```bash
git add src/bubble_mcp/history/git_store.py tests/unit/test_history_git_store.py
git commit -m "feat: add git store for bubble history"
```

---

### Task 4: Snapshot Creation

**Files:**
- Create: `src/bubble_mcp/history/snapshot.py`
- Test: `tests/unit/test_history_snapshot.py`

- [ ] **Step 1: Write failing snapshot test**

Create `tests/unit/test_history_snapshot.py`:

```python
import json
from pathlib import Path

from bubble_mcp.history.snapshot import copy_sanitized_modules


def test_copy_sanitized_modules_writes_clean_repo_tree(tmp_path: Path) -> None:
    source = tmp_path / "bubble_modules" / "app"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text(json.dumps({"format": "bubble-modules"}), encoding="utf-8")
    (source / "styles").mkdir()
    (source / "styles" / "style1.json").write_text(
        json.dumps({"name": "Primary", "private_key": "secret"}),
        encoding="utf-8",
    )
    repo = tmp_path / "repo"

    count = copy_sanitized_modules(source, repo, app_id="app")

    assert count == 2
    assert (repo / "modules" / "app" / "manifest.json").exists()
    style = json.loads((repo / "modules" / "app" / "styles" / "style1.json").read_text(encoding="utf-8"))
    assert style["private_key"] == "[REDACTED]"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_snapshot.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history.snapshot'`.

- [ ] **Step 3: Implement snapshot copy**

Create `src/bubble_mcp/history/snapshot.py`:

```python
from __future__ import annotations

import json
import shutil
from pathlib import Path

from bubble_mcp.history.git_store import commit_all, ensure_repo, push_branch
from bubble_mcp.history.models import SnapshotRequest, SnapshotResult, utc_now_iso
from bubble_mcp.history.paths import branch_name_for_app_version, context_modules_dir, history_repo_dir
from bubble_mcp.history.sanitize import sanitize_module_data


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_sanitized_modules(source_modules: Path, repo: Path, *, app_id: str) -> int:
    target = repo / "modules" / app_id
    if target.exists():
        shutil.rmtree(target)
    count = 0
    for source_file in source_modules.rglob("*.json"):
        relative = source_file.relative_to(source_modules)
        raw = json.loads(source_file.read_text(encoding="utf-8"))
        _write_json(target / relative, sanitize_module_data(raw))
        count += 1
    return count


def create_snapshot(request: SnapshotRequest) -> SnapshotResult:
    branch = branch_name_for_app_version(request.app_version)
    repo = history_repo_dir(request.profile, request.app_id)
    modules = context_modules_dir(request.profile, request.app_id)
    if not modules.exists():
        raise FileNotFoundError(f"Missing split Bubble modules: {modules}. Run bubble-mcp context detect first.")
    ensure_repo(repo, branch=branch, remote_url=request.remote_url)
    sanitized_files = copy_sanitized_modules(modules, repo, app_id=request.app_id)
    _write_json(
        repo / "manifest.json",
        {
            "format": "bubble-history-snapshot",
            "version": 1,
            "profile": request.profile,
            "app_id": request.app_id,
            "app_version": request.app_version,
            "branch": branch,
            "generated_at": utc_now_iso(),
            "modules": f"modules/{request.app_id}",
        },
    )
    commit = commit_all(repo, f"snapshot({request.app_id}): {request.app_version}")
    if request.push and request.remote_url and commit:
        push_branch(repo, branch)
    return SnapshotResult(
        ok=True,
        profile=request.profile,
        app_id=request.app_id,
        app_version=request.app_version,
        branch=branch,
        repo_dir=repo,
        commit=commit,
        changed=commit is not None,
        sanitized_files=sanitized_files,
    )
```

- [ ] **Step 4: Run snapshot tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_snapshot.py tests/unit/test_history_sanitize.py tests/unit/test_history_git_store.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit snapshot slice**

Run:

```bash
git add src/bubble_mcp/history/snapshot.py tests/unit/test_history_snapshot.py
git commit -m "feat: snapshot sanitized bubble modules"
```

---

### Task 5: Historical Object Locator

**Files:**
- Create: `src/bubble_mcp/history/locator.py`
- Test: `tests/unit/test_history_locator.py`

- [ ] **Step 1: Write failing locator test**

Create `tests/unit/test_history_locator.py`:

```python
import json
from pathlib import Path

from bubble_mcp.history.git_store import commit_all, ensure_repo
from bubble_mcp.history.locator import locate_history_object


def test_locate_style_by_name_from_git_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    ensure_repo(repo, branch="bubble/test", remote_url=None)
    style_dir = repo / "modules" / "app" / "styles" / "Button"
    style_dir.mkdir(parents=True)
    (style_dir / "style1.json").write_text(json.dumps({"name": "Primary Button", "element_type": "Button"}), encoding="utf-8")
    commit = commit_all(repo, "snapshot")
    assert commit is not None

    found = locate_history_object(repo, app_id="app", git_ref=commit, object_type="style", object_ref="Primary Button")

    assert found["path"] == "modules/app/styles/Button/style1.json"
    assert found["data"]["name"] == "Primary Button"
```

- [ ] **Step 2: Run locator test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_locator.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history.locator'`.

- [ ] **Step 3: Implement locator**

Create `src/bubble_mcp/history/locator.py`:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from bubble_mcp.history.models import HistoryObjectType


OBJECT_DIRS: dict[HistoryObjectType, str] = {
    "page": "pages",
    "reusable": "pages",
    "element": "pages/parts",
    "workflow": "workflows",
    "style": "styles",
    "api_connector": "api_connector",
    "data_type": "user_types",
    "option_set": "option_sets",
}


def _git(repo: Path, args: list[str]) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def _candidate_paths(repo: Path, git_ref: str, prefix: str) -> list[str]:
    output = _git(repo, ["ls-tree", "-r", "--name-only", git_ref, prefix])
    return [line.strip() for line in output.splitlines() if line.strip().endswith(".json")]


def _load_json_at_ref(repo: Path, git_ref: str, path: str) -> Any:
    output = _git(repo, ["show", f"{git_ref}:{path}"])
    return json.loads(output)


def _matches_ref(data: Any, object_ref: str, path: str) -> bool:
    if object_ref in path:
        return True
    if isinstance(data, dict):
        values = [
            data.get("name"),
            data.get("%nm"),
            data.get("display"),
            data.get("label"),
            data.get("db_value"),
        ]
        return any(str(value) == object_ref for value in values if value is not None)
    return False


def locate_history_object(
    repo: Path,
    *,
    app_id: str,
    git_ref: str,
    object_type: HistoryObjectType,
    object_ref: str,
) -> dict[str, Any]:
    object_dir = OBJECT_DIRS[object_type]
    prefix = f"modules/{app_id}/{object_dir}"
    for path in _candidate_paths(repo, git_ref, prefix):
        data = _load_json_at_ref(repo, git_ref, path)
        if _matches_ref(data, object_ref, path):
            return {"path": path, "data": data}
    raise FileNotFoundError(f"Could not find {object_type} '{object_ref}' at {git_ref}.")
```

- [ ] **Step 4: Run locator tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_locator.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit locator slice**

Run:

```bash
git add src/bubble_mcp/history/locator.py tests/unit/test_history_locator.py
git commit -m "feat: locate historical bubble modules"
```

---

### Task 6: Restore Planning

**Files:**
- Create: `src/bubble_mcp/history/restore.py`
- Test: `tests/unit/test_history_restore.py`

- [ ] **Step 1: Write failing restore tests**

Create `tests/unit/test_history_restore.py`:

```python
from bubble_mcp.history.restore import build_restore_payloads


def test_build_restore_payloads_for_style() -> None:
    payloads = build_restore_payloads(
        app_id="app",
        object_type="style",
        object_ref="Primary Button",
        data={"name": "Primary Button", "element_type": "Button", "font_size": 16},
    )

    assert payloads == [
        {
            "tool": "create_style",
            "arguments": {
                "profile": "",
                "name": "Primary Button",
                "element_type": "Button",
                "font_size": 16,
                "dry_run": True,
            },
        }
    ]


def test_build_restore_payloads_for_api_connector_redacts_structure_only_warning() -> None:
    payloads = build_restore_payloads(
        app_id="app",
        object_type="api_connector",
        object_ref="Stripe",
        data={"name": "Stripe", "private_key": "[REDACTED]", "url": "https://api.stripe.com"},
    )

    assert payloads[0]["tool"] == "restore_api_connector_structure"
    assert payloads[0]["arguments"]["private_key"] == "[REDACTED]"
    assert payloads[0]["requires_manual_secrets"] is True
```

- [ ] **Step 2: Run restore tests and verify they fail**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_restore.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history.restore'`.

- [ ] **Step 3: Implement restore payload planner**

Create `src/bubble_mcp/history/restore.py`:

```python
from __future__ import annotations

from typing import Any

from bubble_mcp.history.models import HistoryObjectType, RestorePlan, RestoreTarget, utc_now_iso


def _style_payload(data: dict[str, Any]) -> dict[str, Any]:
    args = {
        "profile": "",
        "name": str(data.get("name") or data.get("%nm") or "Restored Style"),
        "element_type": str(data.get("element_type") or data.get("type") or "Group"),
        "dry_run": True,
    }
    for key in ("font_size", "font_color", "bg_color", "border_radius", "font_weight", "border_color", "border_width"):
        if key in data:
            args[key] = data[key]
    return {"tool": "create_style", "arguments": args}


def _raw_module_payload(object_type: HistoryObjectType, object_ref: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "bubble_editor_write",
        "arguments": {
            "profile": "",
            "payload": {
                "restore_object_type": object_type,
                "restore_object_ref": object_ref,
                "module_data": data,
            },
            "execute": False,
        },
    }


def build_restore_payloads(
    *,
    app_id: str,
    object_type: HistoryObjectType,
    object_ref: str,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    if object_type == "style":
        return [_style_payload(data)]
    if object_type == "api_connector":
        return [
            {
                "tool": "restore_api_connector_structure",
                "arguments": data,
                "requires_manual_secrets": True,
            }
        ]
    return [_raw_module_payload(object_type, object_ref, data)]


def build_restore_plan(
    *,
    profile: str,
    app_id: str,
    app_version: str,
    git_ref: str,
    object_type: HistoryObjectType,
    object_ref: str,
    data: dict[str, Any],
    target_context: str | None = None,
    target_parent: str | None = None,
) -> RestorePlan:
    payloads = build_restore_payloads(app_id=app_id, object_type=object_type, object_ref=object_ref, data=data)
    for payload in payloads:
        arguments = payload.get("arguments")
        if isinstance(arguments, dict) and "profile" in arguments:
            arguments["profile"] = profile
    warnings = []
    if object_type == "api_connector":
        warnings.append("API Connector restore is structure-only. Re-enter secrets manually in Bubble.")
    return RestorePlan(
        plan_id=f"restore_{utc_now_iso().replace(':', '').replace('-', '')}",
        profile=profile,
        app_id=app_id,
        app_version=app_version,
        git_ref=git_ref,
        target=RestoreTarget(
            object_type=object_type,
            object_ref=object_ref,
            target_context=target_context,
            target_parent=target_parent,
        ),
        payloads=payloads,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run restore tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_restore.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit restore planning slice**

Run:

```bash
git add src/bubble_mcp/history/restore.py tests/unit/test_history_restore.py
git commit -m "feat: plan bubble history restore payloads"
```

---

### Task 7: Runtime, MCP Tools, CLI, and Docs

**Files:**
- Create: `src/bubble_mcp/history/runtime.py`
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/server/agent_guide.py`
- Modify: `src/bubble_mcp/runtime_coverage.py`
- Modify: `src/bubble_mcp/cli/main.py`
- Modify: `docs/context-engine.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/mcp-clients.md`
- Modify: `docs/source-audit.md`
- Test: `tests/unit/test_mcp_server.py`
- Test: `tests/unit/test_cli_commands.py`

- [ ] **Step 1: Write failing runtime test**

Create `tests/unit/test_history_runtime.py`:

```python
import json
from pathlib import Path

from bubble_mcp.history.git_store import commit_all, ensure_repo
from bubble_mcp.history.runtime import history_restore_plan


def test_history_restore_plan_loads_historical_style(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    repo = tmp_path / "history" / "smoke" / "app" / "repo"
    ensure_repo(repo, branch="bubble/test", remote_url=None)
    style_dir = repo / "modules" / "app" / "styles" / "Button"
    style_dir.mkdir(parents=True)
    (style_dir / "primary.json").write_text(json.dumps({"name": "Primary Button", "element_type": "Button"}), encoding="utf-8")
    commit = commit_all(repo, "snapshot")
    assert commit is not None

    result = history_restore_plan(
        profile="smoke",
        app_id="app",
        app_version="test",
        git_ref=commit,
        object_type="style",
        object_ref="Primary Button",
    )

    assert result["ok"] is True
    assert result["plan"]["target"]["object_type"] == "style"
    assert result["plan"]["payloads"][0]["tool"] == "create_style"
```

- [ ] **Step 2: Run runtime test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.history.runtime'`.

- [ ] **Step 3: Implement runtime**

Create `src/bubble_mcp/history/runtime.py`:

```python
from __future__ import annotations

from typing import Any

from bubble_mcp.history.locator import locate_history_object
from bubble_mcp.history.models import HistoryObjectType, SnapshotRequest
from bubble_mcp.history.paths import history_repo_dir
from bubble_mcp.history.restore import build_restore_plan
from bubble_mcp.history.snapshot import create_snapshot


def history_snapshot(
    *,
    profile: str,
    app_id: str,
    app_version: str = "test",
    remote_url: str | None = None,
    push: bool = False,
) -> dict[str, Any]:
    result = create_snapshot(
        SnapshotRequest(
            profile=profile,
            app_id=app_id,
            app_version=app_version,
            remote_url=remote_url,
            push=push,
        )
    )
    return result.to_dict()


def history_restore_plan(
    *,
    profile: str,
    app_id: str,
    app_version: str,
    git_ref: str,
    object_type: HistoryObjectType,
    object_ref: str,
    target_context: str | None = None,
    target_parent: str | None = None,
) -> dict[str, Any]:
    repo = history_repo_dir(profile, app_id)
    located = locate_history_object(repo, app_id=app_id, git_ref=git_ref, object_type=object_type, object_ref=object_ref)
    plan = build_restore_plan(
        profile=profile,
        app_id=app_id,
        app_version=app_version,
        git_ref=git_ref,
        object_type=object_type,
        object_ref=object_ref,
        data=located["data"],
        target_context=target_context,
        target_parent=target_parent,
    )
    return {"ok": True, "source_path": located["path"], "plan": plan.to_dict()}
```

- [ ] **Step 4: Run runtime tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_runtime.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Add MCP schema and dispatch tests**

Add to `tests/unit/test_mcp_server.py`:

```python
def test_history_tools_are_exposed() -> None:
    tools = {tool["name"]: tool for tool in list_tool_schemas()}

    assert tools["bubble_history_snapshot"]["inputSchema"]["required"] == ["profile", "app_id"]
    assert tools["bubble_history_restore_plan"]["inputSchema"]["required"] == ["profile", "app_id", "git_ref", "object_type", "object_ref"]
    assert tools["bubble_history_restore_execute"]["annotations"]["destructiveHint"] is True


def test_history_snapshot_dispatches_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("bubble_mcp.server.tools.history_snapshot", lambda **kwargs: {"ok": True, "received": kwargs})
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 701,
            "method": "tools/call",
            "params": {
                "name": "bubble_history_snapshot",
                "arguments": {"profile": "smoke", "app_id": "app", "app_version": "test"},
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["received"]["app_id"] == "app"
```

- [ ] **Step 6: Expose MCP tools**

In `src/bubble_mcp/server/schema_families.py`, add:

```python
def history_tools() -> list[ToolSchema]:
    return [
        tool_schema("bubble_history_snapshot", "Create a sanitized Git snapshot of the current detected Bubble modules.", ["profile", "app_id", "app_version", "remote_url", "push"], required=["profile", "app_id"]),
        tool_schema("bubble_history_list", "List local Bubble history snapshots and Git refs for a profile/app.", ["profile", "app_id"], required=["profile", "app_id"]),
        tool_schema("bubble_history_diff", "Compare two Bubble history Git refs for a profile/app.", ["profile", "app_id", "base_ref", "head_ref", "path"], required=["profile", "app_id", "base_ref", "head_ref"]),
        tool_schema("bubble_history_restore_plan", "Build a preview-first restore plan from a historical Bubble module object.", ["profile", "app_id", "app_version", "git_ref", "object_type", "object_ref", "target_context", "target_parent"], required=["profile", "app_id", "git_ref", "object_type", "object_ref"]),
        tool_schema("bubble_history_restore_execute", "Execute a previously generated Bubble history restore plan. Requires execute=true and confirm=true.", ["profile", "plan", "plan_path", "execute", "confirm"], required=["profile"]),
    ]
```

Add `*history_tools()` to `list_tool_schemas()`.

In `src/bubble_mcp/server/tools.py`, import:

```python
from bubble_mcp.history.runtime import history_restore_plan, history_snapshot
```

Add dispatch:

```python
    if name == "bubble_history_snapshot":
        return history_snapshot(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            remote_url=args.get("remote_url"),
            push=bool(args.get("push")),
        )
    if name == "bubble_history_restore_plan":
        return history_restore_plan(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or "test"),
            git_ref=str(args.get("git_ref") or ""),
            object_type=str(args.get("object_type") or "style"),
            object_ref=str(args.get("object_ref") or ""),
            target_context=args.get("target_context"),
            target_parent=args.get("target_parent"),
        )
```

- [ ] **Step 7: Run MCP tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_mcp_server.py::test_history_tools_are_exposed tests/unit/test_mcp_server.py::test_history_snapshot_dispatches_runtime -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 8: Add CLI commands and docs**

In `src/bubble_mcp/cli/main.py`, add `history snapshot` and `history restore-plan` command functions that call `history_snapshot` and `history_restore_plan`, print JSON, and return `0` when `ok` is true.

Document in `docs/cli-reference.md`:

```markdown
## `bubble-mcp history`

Create a sanitized Git snapshot for the detected Bubble modules:

```bash
bubble-mcp history snapshot --profile smoke --app-id bovichain-g3 --app-version test
```

Create a restore preview from a historical Git ref:

```bash
bubble-mcp history restore-plan \
  --profile smoke \
  --app-id bovichain-g3 \
  --app-version test \
  --git-ref bubble/test~1 \
  --object-type style \
  --object-ref "Primary Button"
```

History snapshots redact sensitive keys before commit. API Connector restoration is structure-only and requires manual secret re-entry.
```

Update `docs/source-audit.md` with:

```markdown
Bubble history repositories may be pushed to GitHub only after sanitization. Never commit raw `.bubble` exports, sessions, cookies, private API Connector values, local mutation overlays, captures, or generated profile credentials.
```

- [ ] **Step 9: Run focused validation**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_paths.py tests/unit/test_history_sanitize.py tests/unit/test_history_git_store.py tests/unit/test_history_snapshot.py tests/unit/test_history_locator.py tests/unit/test_history_restore.py tests/unit/test_history_runtime.py tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py -q
rtk proxy .venv/bin/python -m ruff check src/bubble_mcp/history tests/unit/test_history_paths.py tests/unit/test_history_sanitize.py tests/unit/test_history_git_store.py tests/unit/test_history_snapshot.py tests/unit/test_history_locator.py tests/unit/test_history_restore.py tests/unit/test_history_runtime.py
```

Expected: pytest passes; ruff reports no issues in `src/bubble_mcp/history` and focused tests.

- [ ] **Step 10: Commit integration slice**

Run:

```bash
git add src/bubble_mcp/history src/bubble_mcp/server/schema_families.py src/bubble_mcp/server/tools.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/agent_guide.py src/bubble_mcp/runtime_coverage.py src/bubble_mcp/cli/main.py docs/context-engine.md docs/cli-reference.md docs/mcp-clients.md docs/source-audit.md tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py tests/unit/test_history_runtime.py
git commit -m "feat: expose bubble history snapshot and restore"
```

---

### Task 8: Restore Execution Gate

**Files:**
- Modify: `src/bubble_mcp/history/runtime.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Test: `tests/unit/test_history_runtime.py`
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Add failing execution-gate tests**

Append to `tests/unit/test_history_runtime.py`:

```python
import pytest

from bubble_mcp.history.runtime import history_restore_execute


def test_history_restore_execute_previews_without_execute() -> None:
    plan = {
        "plan_id": "restore_test",
        "payloads": [
            {"tool": "create_style", "arguments": {"profile": "smoke", "name": "Primary", "dry_run": True}}
        ],
    }

    result = history_restore_execute(profile="smoke", plan=plan, execute=False, confirm=False)

    assert result["ok"] is True
    assert result["executed"] is False
    assert result["operation_count"] == 1


def test_history_restore_execute_requires_confirm_for_real_execution() -> None:
    with pytest.raises(ValueError, match="confirm=true"):
        history_restore_execute(profile="smoke", plan={"payloads": []}, execute=True, confirm=False)
```

- [ ] **Step 2: Run execution-gate tests and verify they fail**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_runtime.py::test_history_restore_execute_previews_without_execute tests/unit/test_history_runtime.py::test_history_restore_execute_requires_confirm_for_real_execution -q
```

Expected: FAIL because `history_restore_execute` is not defined.

- [ ] **Step 3: Implement execution gate**

Append to `src/bubble_mcp/history/runtime.py`:

```python
def history_restore_execute(
    *,
    profile: str,
    plan: dict[str, Any],
    execute: bool,
    confirm: bool,
) -> dict[str, Any]:
    payloads = plan.get("payloads")
    if not isinstance(payloads, list):
        raise ValueError("Restore execution requires a plan with a payloads list.")
    if execute and not confirm:
        raise ValueError("Restore execution requires confirm=true when execute=true.")
    if not execute:
        return {
            "ok": True,
            "profile": profile,
            "executed": False,
            "operation_count": len(payloads),
            "operations": payloads,
        }
    executable = []
    blocked = []
    for payload in payloads:
        tool = payload.get("tool") if isinstance(payload, dict) else None
        if tool == "bubble_editor_write":
            executable.append(payload)
        else:
            blocked.append({"tool": tool, "reason": "Execute this restore operation through its native MCP tool after preview."})
    return {
        "ok": not blocked,
        "profile": profile,
        "executed": False,
        "operation_count": len(payloads),
        "executable_count": len(executable),
        "blocked": blocked,
    }
```

- [ ] **Step 4: Wire MCP dispatch for restore execution**

Modify `src/bubble_mcp/server/tools.py` import:

```python
from bubble_mcp.history.runtime import history_restore_execute, history_restore_plan, history_snapshot
```

Add dispatch:

```python
    if name == "bubble_history_restore_execute":
        plan = args.get("plan")
        if not isinstance(plan, dict):
            raise ValueError("bubble_history_restore_execute requires a plan object in this implementation slice.")
        return history_restore_execute(
            profile=str(args.get("profile") or ""),
            plan=plan,
            execute=bool(args.get("execute")),
            confirm=bool(args.get("confirm")),
        )
```

- [ ] **Step 5: Add MCP execution dispatch test**

Append to `tests/unit/test_mcp_server.py`:

```python
def test_history_restore_execute_dispatches_preview() -> None:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 702,
            "method": "tools/call",
            "params": {
                "name": "bubble_history_restore_execute",
                "arguments": {
                    "profile": "smoke",
                    "execute": False,
                    "confirm": False,
                    "plan": {"payloads": [{"tool": "create_style", "arguments": {"name": "Primary"}}]},
                },
            },
        }
    )

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["executed"] is False
    assert payload["operation_count"] == 1
```

- [ ] **Step 6: Run execution tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_history_runtime.py::test_history_restore_execute_previews_without_execute tests/unit/test_history_runtime.py::test_history_restore_execute_requires_confirm_for_real_execution tests/unit/test_mcp_server.py::test_history_restore_execute_dispatches_preview -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 7: Commit execution gate slice**

Run:

```bash
git add src/bubble_mcp/history/runtime.py src/bubble_mcp/server/tools.py tests/unit/test_history_runtime.py tests/unit/test_mcp_server.py
git commit -m "feat: gate bubble history restore execution"
```

## Self-Review

- Spec coverage: The plan covers Git/GitHub snapshots, parsed `.bubble` module usage, branch mapping, historical lookup, restore planning, preview-first execution boundary, and structure-only API Connector safety.
- Placeholder scan: The plan includes explicit tasks for snapshot, sanitize, locate, restore plan, restore execution gate, MCP exposure, CLI exposure, docs, and validation.
- Type consistency: `SnapshotRequest`, `SnapshotResult`, `RestoreTarget`, `RestorePlan`, `HistoryObjectType`, `history_snapshot`, and `history_restore_plan` are consistently named across model, runtime, tests, MCP, and CLI steps.
