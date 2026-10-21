# Live Node Read and In-Place Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two MCP tools — `bubble_live_node_read` and `bubble_node_edit` — that read a node out of the running Bubble editor's own memory, change one part of it, write it back, and prove the write landed by reading it again.

**Architecture:** Three new pure-ish modules under `src/bubble_mcp/execution/`, layered downward with no imports from the server package: `node_keys.py` translates the node root between the editor's decoded key space and the write endpoint's encoded one; `live_node_read.py` runs `window.appquery` in a Playwright-driven editor page behind an injectable evaluator; `node_edit.py` orchestrates read → modify → encode → write → re-read → compare on top of the existing, untouched primitives in `raw_node_edit.py`. Only the two tools are public; the primitives stay internal.

**Tech Stack:** Python 3.12, pytest, Playwright (sync API, optional `[browser]` extra), the existing `BubbleEditorClient` write path.

**Spec:** `docs/superpowers/specs/2026-08-26-live-node-read-and-inplace-edit-design.md`

## Global Constraints

- Nothing in `src/bubble_mcp/execution/` may import from `bubble_mcp.server`.
- `raw_node_edit.py` and `tests/unit/test_raw_node_edit.py` are not modified by this plan.
- No test in this plan launches a browser or contacts Bubble. Playwright is imported lazily, inside the function that needs it, exactly as `browser_automation/scheduled_deploy.py:834` already does.
- Manual validation runs only against profile `mcp-test` (app `mcp-test-app`). Never `orana` (`~/.bubble-mcp`), never `auto-on`.
- This machine has 14 unit tests that fail on Windows regardless of this work (symlink / chmod / path separator / routing count). Verification compares against the pre-change baseline captured in Task 0, never against an absolute pass count.
- Type annotations use `from __future__ import annotations` and PEP 604 unions, matching the surrounding modules.

---

### Task 0: Capture the test baseline

**Files:**
- Create: nothing. This task produces a recorded number, not a diff.

**Interfaces:**
- Consumes: nothing.
- Produces: the pre-change failure list every later task compares against.

- [ ] **Step 1: Run the unit suite and record what already fails**

Run: `python -m pytest tests/unit -q`

Write the resulting `N failed, M passed` line and the list of failing test ids into your working notes. Do not attempt to fix any of them — they are pre-existing Windows failures and are out of scope.

- [ ] **Step 2: Confirm the fixture this plan asserts against exists**

Run: `python -c "import json,pathlib; d=json.loads(pathlib.Path('tests/fixtures/expressions/api-event-parameter-golden.json').read_text(encoding='utf-8')); print(sorted(d['action']['properties']))"`

Expected: a list including `to_change`, `condition`, and `changes`. If this fails, stop — the fixture is the ground truth for Task 1 and Task 3.

---

### Task 1: Node root key translation

**Files:**
- Create: `src/bubble_mcp/execution/node_keys.py`
- Test: `tests/unit/test_node_keys.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `encode_node_root(node: dict[str, Any]) -> dict[str, Any]`
  - `decode_node_root(node: dict[str, Any]) -> dict[str, Any]`
  - both raise `ValueError` on an ambiguous root and `TypeError` on a non-dict.

Background an implementer needs: the Bubble editor holds its app tree with decoded keys (`type`, `properties`), while `/appeditor/write` requires encoded keys (`%x`, `%p`) **at the node root only**. The interior of `properties` — the expression chain, its `Message` nodes — stays decoded on both sides. `src/bubble_mcp/execution/write_lint.py:19` already encodes this mapping and deliberately omits `name`, because `name` means `%nm` on an element root and an internal field name inside a `Message`. Translating it would be a guess, and guessing is what produces nodes the server accepts and the editor renders as `[missing: null]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_node_keys.py`:

```python
"""The editor and the write endpoint spell node keys differently; only the root translates."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bubble_mcp.execution.node_keys import decode_node_root, encode_node_root

GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "expressions"
    / "api-event-parameter-golden.json"
)


def test_encode_node_root_translates_the_root_and_nothing_else() -> None:
    node = {
        "id": "act-1",
        "type": "ChangeThing",
        "properties": {"to_change": {"type": "APIEventParameter", "is_slidable": False}},
    }

    encoded = encode_node_root(node)

    assert encoded == {
        "id": "act-1",
        "%x": "ChangeThing",
        "%p": {"to_change": {"type": "APIEventParameter", "is_slidable": False}},
    }


def test_encode_node_root_leaves_the_expression_interior_byte_identical() -> None:
    action = json.loads(GOLDEN.read_text(encoding="utf-8"))["action"]
    interior = copy.deepcopy(action["properties"])

    encoded = encode_node_root(action)

    assert encoded["%p"] == interior


def test_encode_node_root_does_not_mutate_its_argument() -> None:
    node = {"type": "ChangeThing", "properties": {"k": {"type": "Message"}}}
    original = copy.deepcopy(node)

    encode_node_root(node)

    assert node == original


def test_encode_node_root_refuses_a_root_that_carries_name() -> None:
    with pytest.raises(ValueError, match="name"):
        encode_node_root({"type": "Text", "name": "Header"})


def test_encode_node_root_passes_an_already_encoded_node_through() -> None:
    node = {"id": "a", "%x": "ChangeThing", "%p": {"k": 1}}

    assert encode_node_root(node) == node


def test_encode_node_root_rejects_a_non_node() -> None:
    with pytest.raises(TypeError):
        encode_node_root(["not", "a", "node"])  # type: ignore[arg-type]


def test_decode_node_root_closes_the_round_trip() -> None:
    node = {"id": "act-1", "type": "ChangeThing", "properties": {"k": {"type": "Message"}}}

    assert decode_node_root(encode_node_root(node)) == node


def test_decode_node_root_refuses_an_encoded_element_name() -> None:
    with pytest.raises(ValueError, match="%nm"):
        decode_node_root({"%x": "Text", "%nm": "Header"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_node_keys.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'bubble_mcp.execution.node_keys'`.

- [ ] **Step 3: Write the implementation**

Create `src/bubble_mcp/execution/node_keys.py`:

```python
"""Translation of node ROOT keys between the editor's tree and the write endpoint.

The editor holds nodes with decoded keys (``type``/``properties``); ``/appeditor/write``
requires encoded keys (``%x``/``%p``) at the node root, with the very same interior. Only the
root is translated here. The interior - the expression chain and its ``Message`` nodes - is
copied verbatim, because the interior is exactly the part that cannot be reconstructed, and
touching it is how a node ends up rendering as "[missing: null]".
"""

from __future__ import annotations

import copy
from typing import Any


# Mirrors write_lint._DECODED_TO_ENCODED. ``name`` is deliberately absent: it is ``%nm`` on an
# element root and an internal field name inside a Message, and there is no way to tell which
# one a caller meant without inspecting the interior this module refuses to inspect.
_DECODED_TO_ENCODED = {
    "type": "%x",
    "properties": "%p",
    "default_name": "%dn",
}
_ENCODED_TO_DECODED = {encoded: decoded for decoded, encoded in _DECODED_TO_ENCODED.items()}


def encode_node_root(node: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``node`` with its root keys encoded for ``/appeditor/write``."""

    if not isinstance(node, dict):
        raise TypeError("encode_node_root expects a node object")
    if any(key in node for key in _ENCODED_TO_DECODED):
        return copy.deepcopy(node)
    if "name" in node:
        raise ValueError(
            "node root carries 'name', which is '%nm' on an element and an internal field name "
            "inside a Message; this path edits workflow action nodes only"
        )
    return {
        _DECODED_TO_ENCODED.get(key, key): copy.deepcopy(value) for key, value in node.items()
    }


def decode_node_root(node: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``node`` with its root keys decoded, the inverse of ``encode_node_root``."""

    if not isinstance(node, dict):
        raise TypeError("decode_node_root expects a node object")
    if any(key in node for key in _DECODED_TO_ENCODED):
        return copy.deepcopy(node)
    if "%nm" in node:
        raise ValueError(
            "node root carries '%nm', which decodes to the ambiguous 'name'; this path edits "
            "workflow action nodes only"
        )
    return {
        _ENCODED_TO_DECODED.get(key, key): copy.deepcopy(value) for key, value in node.items()
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_node_keys.py -q`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/execution/node_keys.py tests/unit/test_node_keys.py
git commit -m "feat: translate node root keys between editor and write endpoint"
```

---

### Task 2: Live node read

**Files:**
- Create: `src/bubble_mcp/execution/live_node_read.py`
- Test: `tests/unit/test_live_node_read.py`

**Interfaces:**
- Consumes: `bubble_mcp.core.config.load_settings`, `bubble_mcp.sessions.store.load_session`.
- Produces:
  - `build_appquery_script(pointer: Sequence[str]) -> str`
  - `read_live_node(profile: str, pointer: Sequence[str], *, evaluator: Callable[[str], Any] | None = None, app_id: str | None = None, app_version: str = "test", headless: bool = True, timeout_sec: int = DEFAULT_READ_TIMEOUT_SEC) -> dict[str, Any]` returning `{"ok": True, "pointer": list[str], "node": dict, "app_id": str}` or `{"ok": False, "error": ..., "message": ..., "pointer": list[str]}`
  - `DEFAULT_READ_TIMEOUT_SEC: int`
  - exceptions `PlaywrightMissing`, `EditorNotReady`

Background: the raw form was first recovered by hand on 2026-08-24 with `window.appquery.app().json._child('api')._child('<wf_id>').raw()` in the running editor. `app.raw()` on the root is refused by Bubble itself "for performance reasons", so a pointer must name at least one child. The browser launch mirrors `src/bubble_mcp/browser_automation/scheduled_deploy.py:856`: a persistent context under `settings.config_dir / "browser-profiles" / profile`, so the editor session the user already has is reused.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_live_node_read.py`:

```python
"""Reading a node out of the running editor, with the browser replaced by a fake."""

from __future__ import annotations

from typing import Any

import pytest

from bubble_mcp.execution.live_node_read import (
    build_appquery_script,
    read_live_node,
)


def test_build_appquery_script_chains_one_child_per_pointer_segment() -> None:
    script = build_appquery_script(["api", "wf-1", "actions", "3"])

    assert script == (
        '() => window.appquery.app().json._child("api")._child("wf-1")'
        '._child("actions")._child("3").raw()'
    )


def test_build_appquery_script_refuses_an_empty_pointer() -> None:
    with pytest.raises(ValueError, match="at least one child"):
        build_appquery_script([])


def test_build_appquery_script_refuses_an_empty_segment() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_appquery_script(["api", ""])


def test_build_appquery_script_escapes_a_segment_with_a_quote() -> None:
    script = build_appquery_script(['we"ird'])

    assert '._child("we\\"ird")' in script


def test_read_live_node_returns_the_node_the_page_produced() -> None:
    captured: dict[str, Any] = {}

    def fake_evaluator(script: str) -> Any:
        captured["script"] = script
        return {"id": "act-1", "type": "ChangeThing", "properties": {}}

    result = read_live_node(
        "mcp-test", ["api", "wf-1"], evaluator=fake_evaluator, app_id="mcp-test-app"
    )

    assert result["ok"] is True
    assert result["node"]["id"] == "act-1"
    assert result["pointer"] == ["api", "wf-1"]
    assert result["app_id"] == "mcp-test-app"
    assert captured["script"] == build_appquery_script(["api", "wf-1"])


def test_read_live_node_reports_a_pointer_that_did_not_resolve() -> None:
    result = read_live_node(
        "mcp-test", ["api", "nope"], evaluator=lambda _script: None, app_id="mcp-test-app"
    )

    assert result == {
        "ok": False,
        "error": "pointer_not_found",
        "pointer": ["api", "nope"],
        "message": (
            "window.appquery returned nothing for pointer 'api.nope'. Check the pointer against "
            "the app tree; a wrong segment reads as an absent node, not as an error."
        ),
    }


def test_read_live_node_rejects_a_page_value_that_is_not_a_node() -> None:
    result = read_live_node(
        "mcp-test", ["api"], evaluator=lambda _script: "a string", app_id="mcp-test-app"
    )

    assert result["ok"] is False
    assert result["error"] == "unexpected_node_shape"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_live_node_read.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'bubble_mcp.execution.live_node_read'`.

- [ ] **Step 3: Write the implementation**

Create `src/bubble_mcp/execution/live_node_read.py`:

```python
"""Read a node from the running Bubble editor's own memory.

The raw encoding of Bubble expressions is not derivable from the .bubble export - the export
is the decoded projection and the decoding happens server-side - so the only source of truth
is the tree the editor holds in the page. ``window.appquery`` exposes it. Everything here is
built so the page call is one injectable function: tests pass a fake and never open a browser.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from bubble_mcp.core.config import load_settings
from bubble_mcp.sessions.store import load_session


DEFAULT_READ_TIMEOUT_SEC = 90
EDITOR_URL_TEMPLATE = "https://bubble.io/page?name=index&id={app_id}&version={app_version}"
APPQUERY_READY_SCRIPT = "() => typeof window.appquery !== 'undefined'"

Evaluator = Callable[[str], Any]


class PlaywrightMissing(RuntimeError):
    """Raised when the browser extra is not installed."""


class EditorNotReady(RuntimeError):
    """Raised when the editor page never exposes window.appquery."""


def build_appquery_script(pointer: Sequence[str]) -> str:
    """Return the page script that reads the node at ``pointer`` out of editor memory."""

    segments = [str(part) for part in pointer]
    if not segments:
        raise ValueError(
            "pointer must name at least one child: app.raw() on the root is refused by Bubble "
            "'for performance reasons'"
        )
    if any(not part for part in segments):
        raise ValueError("pointer segments must be non-empty")
    chain = "".join(f"._child({json.dumps(part)})" for part in segments)
    return f"() => window.appquery.app().json{chain}.raw()"


def _resolve_app_id(profile: str, app_id: str | None) -> str:
    explicit = str(app_id or "").strip()
    if explicit:
        return explicit
    session = load_session(profile)
    from_session = str(getattr(session, "app_id", "") or "").strip()
    if from_session:
        return from_session
    raise ValueError(f"No app id for profile '{profile}'; pass app_id explicitly.")


def _playwright_evaluator(
    *, profile: str, app_id: str, app_version: str, headless: bool, timeout_sec: int
) -> Evaluator:
    """Return an evaluator that runs one script in the editor page for this app."""

    def evaluate(script: str) -> Any:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # noqa: BLE001 - re-raised as a typed, reportable failure
            raise PlaywrightMissing(
                "Playwright is required to read the live editor. Install with: "
                'python -m pip install "befree-bubble-mcp[browser]" '
                "&& python -m playwright install chromium"
            ) from exc

        settings = load_settings()
        user_data_dir = settings.config_dir / "browser-profiles" / profile
        url = EDITOR_URL_TEMPLATE.format(app_id=app_id, app_version=app_version)
        timeout_ms = timeout_sec * 1000
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(user_data_dir), headless=headless
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_function(APPQUERY_READY_SCRIPT, timeout=timeout_ms)
                except Exception as exc:  # noqa: BLE001 - Playwright raises its own timeout type
                    raise EditorNotReady(
                        f"window.appquery never appeared on {url} within {timeout_sec}s"
                    ) from exc
                return page.evaluate(script)
            finally:
                context.close()

    return evaluate


def read_live_node(
    profile: str,
    pointer: Sequence[str],
    *,
    evaluator: Evaluator | None = None,
    app_id: str | None = None,
    app_version: str = "test",
    headless: bool = True,
    timeout_sec: int = DEFAULT_READ_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Read the node at ``pointer`` from the live editor, as a structured result."""

    segments = [str(part) for part in pointer]
    script = build_appquery_script(segments)
    resolved_app_id = _resolve_app_id(profile, app_id)
    run = evaluator or _playwright_evaluator(
        profile=profile,
        app_id=resolved_app_id,
        app_version=app_version,
        headless=headless,
        timeout_sec=timeout_sec,
    )
    try:
        node = run(script)
    except PlaywrightMissing as exc:
        return {"ok": False, "error": "playwright_missing", "pointer": segments, "message": str(exc)}
    except EditorNotReady as exc:
        return {"ok": False, "error": "editor_not_ready", "pointer": segments, "message": str(exc)}

    if node is None:
        return {
            "ok": False,
            "error": "pointer_not_found",
            "pointer": segments,
            "message": (
                f"window.appquery returned nothing for pointer '{'.'.join(segments)}'. Check the "
                "pointer against the app tree; a wrong segment reads as an absent node, not as an "
                "error."
            ),
        }
    if not isinstance(node, dict):
        return {
            "ok": False,
            "error": "unexpected_node_shape",
            "pointer": segments,
            "message": f"Expected a node object at '{'.'.join(segments)}', got {type(node).__name__}.",
        }
    return {"ok": True, "pointer": segments, "node": node, "app_id": resolved_app_id}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_live_node_read.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/execution/live_node_read.py tests/unit/test_live_node_read.py
git commit -m "feat: read a raw node from the running Bubble editor"
```

---

### Task 3: The patch cycle

**Files:**
- Create: `src/bubble_mcp/execution/node_edit.py`
- Test: `tests/unit/test_node_edit.py`

**Interfaces:**
- Consumes: `read_live_node` (Task 2), `encode_node_root` (Task 1), `patch_expression_leaf` and `first_divergence` from `raw_node_edit.py`, `BubbleEditorClient` and `load_session`.
- Produces:
  - `edit_live_node(*, profile, pointer, op, leaf_pointer=None, patch=None, order=None, execute=False, app_id=None, reader=None, writer=None) -> dict[str, Any]`
  - `build_patch_changes(pointer: Sequence[str], node: dict[str, Any]) -> list[dict[str, Any]]`
  - Task 4 adds `build_reorder_changes` to the same module.

The write granularity is the whole node at `pointer`, never the patched leaf. Writing the leaf directly would put an expression interior in a body at a path containing `actions`, which `write_lint._is_node_position` classifies as a node position, so `lint_editor_write_changes` would reject the decoded interior — correctly by its own rules, and wrongly for this case. Sending the whole node keeps exactly one translation point (the root) and leaves the interior where the lint does not look.

The comparison after the write happens in the **decoded** key space, against the intent as it stood before `encode_node_root`. Encoding both sides would measure the write with the ruler that produced it, so an encoding mistake would cancel itself out and the tool would certify a broken node.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_node_edit.py`:

```python
"""The read -> patch -> write -> re-read -> compare cycle, with no browser and no Bubble."""

from __future__ import annotations

import copy
from typing import Any

from bubble_mcp.execution.node_edit import edit_live_node


def _action() -> dict[str, Any]:
    return {
        "id": "act-1",
        "type": "ChangeThing",
        "properties": {
            "to_change": {
                "type": "APIEventParameter",
                "is_slidable": False,
                "properties": {
                    "btype_id": "custom.client",
                    "event_id": "ev-1",
                    "param_id": "Client",
                    "param_name": "Client",
                },
            }
        },
    }


class _Reader:
    """Returns a fresh copy of whatever the fake editor currently holds."""

    def __init__(self, node: dict[str, Any]) -> None:
        self.node = node
        self.calls = 0

    def __call__(self, profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return {
            "ok": True,
            "pointer": list(pointer),
            "node": copy.deepcopy(self.node),
            "app_id": "mcp-test-app",
        }


def _writer_that_applies(reader: _Reader, *, drop_key: str | None = None):  # type: ignore[no-untyped-def]
    """A fake write endpoint that stores the body, optionally losing one key on the way."""

    def write(payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        if not dry_run:
            body = copy.deepcopy(payload["changes"][0]["body"])
            if drop_key is not None:
                body["%p"]["to_change"]["properties"].pop(drop_key, None)
            reader.node = {
                "id": body["id"],
                "type": body["%x"],
                "properties": body["%p"],
            }
        return {"ok": True, "dry_run": dry_run, "request": {"payload": payload}}

    return write


def test_patch_previews_without_writing_when_execute_is_false() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["properties", "to_change", "properties"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is True
    assert result["execute"] is False
    assert "verified" not in result
    assert reader.calls == 1
    change = result["write"]["request"]["payload"]["changes"][0]
    assert change["path_array"] == ["api", "wf-1", "actions", "0"]
    assert change["body"]["%x"] == "ChangeThing"
    assert change["body"]["%p"]["to_change"]["properties"]["param_id"] == "Order"


def test_patch_verifies_the_write_by_reading_the_node_back() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["properties", "to_change", "properties"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=True,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["verified"] is True
    assert result["divergence"] is None
    assert reader.calls == 2


def test_patch_names_the_path_where_a_lossy_write_diverged() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["properties", "to_change", "properties"],
        patch={"param_id": "Order", "param_name": "Order"},
        execute=True,
        reader=reader,
        writer=_writer_that_applies(reader, drop_key="btype_id"),
    )

    assert result["verified"] is False
    assert result["divergence"] == "properties.to_change.properties.btype_id"


def test_patch_refuses_a_leaf_pointer_that_does_not_exist() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="patch",
        leaf_pointer=["properties", "to_change", "nope"],
        patch={"param_id": "Order"},
        execute=False,
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "pointer_not_resolved"
    assert "nope" in result["message"]


def test_patch_propagates_a_failed_read_untouched() -> None:
    def failing_reader(profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        return {"ok": False, "error": "pointer_not_found", "pointer": list(pointer)}

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "nope"],
        op="patch",
        leaf_pointer=["properties"],
        patch={"a": 1},
        reader=failing_reader,
        writer=lambda *a, **k: None,
    )

    assert result == {"ok": False, "error": "pointer_not_found", "pointer": ["api", "nope"]}


def test_unknown_op_is_refused_before_anything_is_read() -> None:
    reader = _Reader(_action())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions", "0"],
        op="rewrite",
        reader=reader,
        writer=_writer_that_applies(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "unknown_op"
    assert reader.calls == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_node_edit.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'bubble_mcp.execution.node_edit'`.

- [ ] **Step 3: Write the implementation**

Create `src/bubble_mcp/execution/node_edit.py`:

```python
"""One in-place edit of a live editor node: read, change one part, write back, prove it landed.

/appeditor/write answers HTTP 200 for any body and performs no semantic validation, so a
successful response is not evidence. The only evidence is reading the node back and comparing
it to what was intended, which is what this module does on every executed edit.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Sequence

from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.live_node_read import read_live_node
from bubble_mcp.execution.node_keys import encode_node_root
from bubble_mcp.execution.raw_node_edit import (
    first_divergence,
    patch_expression_leaf,
)
from bubble_mcp.sessions.store import load_session


SUPPORTED_OPS = ("patch", "reorder")

Reader = Callable[..., dict[str, Any]]
Writer = Callable[..., dict[str, Any]]


def _change(path_array: Sequence[str], body: Any, *, intent: str = "SetData") -> dict[str, Any]:
    """Return one /appeditor/write change entry in the shape PayloadBuilder already produces."""

    return {
        "intent": {"name": intent},
        "path_array": [str(part) for part in path_array],
        "body": body,
        "version_control_api_version": 4,
        "changelog_data": [],
    }


def build_patch_changes(pointer: Sequence[str], node: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the single change that writes the whole edited node back at ``pointer``."""

    return [_change(pointer, encode_node_root(node))]


def edit_live_node(
    *,
    profile: str,
    pointer: Sequence[str],
    op: str,
    leaf_pointer: Sequence[str] | None = None,
    patch: dict[str, Any] | None = None,
    order: Sequence[str] | None = None,
    execute: bool = False,
    app_id: str | None = None,
    reader: Reader | None = None,
    writer: Writer | None = None,
) -> dict[str, Any]:
    """Run one read -> modify -> write -> re-read -> compare cycle over a live editor node."""

    segments = [str(part) for part in pointer]
    if op not in SUPPORTED_OPS:
        return {
            "ok": False,
            "error": "unknown_op",
            "message": f"op must be one of {', '.join(SUPPORTED_OPS)}; got '{op}'",
        }

    read = reader or read_live_node
    before = read(profile, segments, app_id=app_id)
    if not before.get("ok"):
        return before
    current = before["node"]

    try:
        intended, changes = _apply(op, segments, current, leaf_pointer, patch, order)
    except KeyError as error:
        return {"ok": False, "error": "pointer_not_resolved", "message": str(error).strip("'\"")}
    except (ValueError, TypeError) as error:
        return {"ok": False, "error": "invalid_edit", "message": str(error)}

    payload: dict[str, Any] = {"changes": changes}
    if app_id or before.get("app_id"):
        payload["appname"] = str(app_id or before.get("app_id"))

    write = writer
    session = None
    if write is None:
        session = load_session(profile)
        if session is None:
            raise ValueError(f"No Bubble session stored for profile '{profile}'.")
        write = BubbleEditorClient().write

    write_result = write(payload, session, dry_run=not execute)

    result: dict[str, Any] = {
        "ok": True,
        "execute": execute,
        "pointer": segments,
        "before": current,
        "intended": intended,
        "write": write_result,
    }
    if not execute:
        return result
    if not write_result.get("ok"):
        return {**result, "ok": False, "verified": False, "divergence": None}

    after = read(profile, segments, app_id=app_id)
    if not after.get("ok"):
        return {**result, "ok": False, "verified": False, "divergence": None, "after": after}
    result["after"] = after["node"]
    result["divergence"] = first_divergence(intended, after["node"])
    result["verified"] = result["divergence"] is None
    return result


def _apply(
    op: str,
    pointer: Sequence[str],
    current: dict[str, Any],
    leaf_pointer: Sequence[str] | None,
    patch: dict[str, Any] | None,
    order: Sequence[str] | None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Return (intended node in the decoded key space, changes to write)."""

    if op == "patch":
        if not leaf_pointer:
            raise ValueError("patch requires leaf_pointer")
        if not isinstance(patch, dict):
            raise ValueError("patch requires a patch object")
        intended = patch_expression_leaf(current, [str(part) for part in leaf_pointer], patch)
        return intended, build_patch_changes(pointer, intended)
    raise ValueError(f"op '{op}' is not implemented")
```

Note for the implementer: `_apply` deliberately raises for `reorder` right now. Task 4 adds that branch; leaving it unimplemented keeps this task independently reviewable.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_node_edit.py -q`
Expected: 6 passed.

- [ ] **Step 5: Run the whole execution test group for regressions**

Run: `python -m pytest tests/unit/test_node_keys.py tests/unit/test_live_node_read.py tests/unit/test_node_edit.py tests/unit/test_raw_node_edit.py -q`
Expected: all pass; `test_raw_node_edit.py` is unchanged and must stay green.

- [ ] **Step 6: Commit**

```bash
git add src/bubble_mcp/execution/node_edit.py tests/unit/test_node_edit.py
git commit -m "feat: run the read-patch-write-verify cycle over a live node"
```

---

### Task 4: The reorder cycle and its index update

**Files:**
- Modify: `src/bubble_mcp/execution/node_edit.py`
- Test: `tests/unit/test_node_edit.py`

**Interfaces:**
- Consumes: everything from Task 3, plus `reorder_actions` from `raw_node_edit.py`.
- Produces: `build_reorder_changes(pointer: Sequence[str], actions: dict[str, Any]) -> list[dict[str, Any]]`, and `op="reorder"` support in `edit_live_node`.

Background: renumbering moves each action to a new path, but `_index.id_to_path` still points at the old one. `bubble_cli` already pairs an action write with an `Update index` change (`src/bubble_mcp/aria_runtime/bubble_cli.py:24006-24012`), body being the dotted path (`"api.<wf_id>.actions.1"`). A reorder must emit one such change per action, otherwise the editor's index and its tree disagree. For `reorder`, `pointer` addresses the actions **map**, not one action.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_node_edit.py`:

```python
def _actions_map() -> dict[str, Any]:
    return {
        "0": {"id": "act-a", "type": "SetCustomState", "properties": {"value": 1}},
        "1": {"id": "act-b", "type": "SetCustomState", "properties": {"value": 2}},
        "2": {"id": "act-c", "type": "SetCustomState", "properties": {"value": 3}},
    }


def _map_writer(reader: _Reader):  # type: ignore[no-untyped-def]
    def write(payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        if not dry_run:
            body = copy.deepcopy(payload["changes"][0]["body"])
            reader.node = {
                key: {"id": value["id"], "type": value["%x"], "properties": value["%p"]}
                for key, value in body.items()
            }
        return {"ok": True, "dry_run": dry_run, "request": {"payload": payload}}

    return write


def test_reorder_renumbers_the_map_and_encodes_every_action_root() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    body = result["write"]["request"]["payload"]["changes"][0]["body"]
    assert list(body) == ["0", "1", "2"]
    assert [entry["id"] for entry in body.values()] == ["act-c", "act-a", "act-b"]
    assert all("%x" in entry and "%p" in entry for entry in body.values())


def test_reorder_repoints_the_index_at_every_moved_action() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    changes = result["write"]["request"]["payload"]["changes"]
    index_changes = [change for change in changes if change["intent"]["name"] == "Update index"]
    assert [(change["path_array"], change["body"]) for change in index_changes] == [
        (["_index", "id_to_path", "act-c"], "api.wf-1.actions.0"),
        (["_index", "id_to_path", "act-a"], "api.wf-1.actions.1"),
        (["_index", "id_to_path", "act-b"], "api.wf-1.actions.2"),
    ]


def test_reorder_verifies_by_reading_the_map_back() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0", "1"],
        execute=True,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["verified"] is True
    assert result["divergence"] is None


def test_reorder_refuses_an_order_that_would_drop_a_step() -> None:
    reader = _Reader(_actions_map())

    result = edit_live_node(
        profile="mcp-test",
        pointer=["api", "wf-1", "actions"],
        op="reorder",
        order=["2", "0"],
        execute=False,
        reader=reader,
        writer=_map_writer(reader),
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_edit"
    assert "1" in result["message"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_node_edit.py -q -k reorder`
Expected: FAIL — `op 'reorder' is not implemented` surfaces as `error == "invalid_edit"` where the tests expect a built payload.

- [ ] **Step 3: Write the implementation**

In `src/bubble_mcp/execution/node_edit.py`, extend the import from `raw_node_edit`:

```python
from bubble_mcp.execution.raw_node_edit import (
    first_divergence,
    patch_expression_leaf,
    reorder_actions,
)
```

Add `build_reorder_changes` next to `build_patch_changes`:

```python
def build_reorder_changes(
    pointer: Sequence[str], actions: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return the map write plus one index repoint per action.

    Renumbering moves every action to a new path while ``_index.id_to_path`` still points at
    the old one, so the map write alone would leave the editor's index disagreeing with its
    tree. This mirrors the SetData + "Update index" pairing bubble_cli already uses.
    """

    encoded = {key: encode_node_root(value) for key, value in actions.items()}
    changes = [_change(pointer, encoded)]
    prefix = ".".join(str(part) for part in pointer)
    for key, value in actions.items():
        action_id = value.get("id")
        if not action_id:
            continue
        changes.append(
            _change(
                ["_index", "id_to_path", str(action_id)],
                f"{prefix}.{key}",
                intent="Update index",
            )
        )
    return changes
```

Replace the `raise ValueError(f"op '{op}' is not implemented")` line at the end of `_apply` with:

```python
    if not order:
        raise ValueError("reorder requires order")
    intended = reorder_actions(current, [str(part) for part in order])
    return intended, build_reorder_changes(pointer, intended)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_node_edit.py -q`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bubble_mcp/execution/node_edit.py tests/unit/test_node_edit.py
git commit -m "feat: reorder live actions and repoint the editor index"
```

---

### Task 5: Expose the two MCP tools

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py` (FIELD_LIBRARY entries; `planning_execution_tools()` around line 1596)
- Modify: `src/bubble_mcp/server/tools.py` (new branches in `call_tool`, near the `bubble_editor_write` branch at line 1572)
- Modify: `src/bubble_mcp/server/agent_catalog.py` (`NATIVE_TOOL_DESCRIPTIONS` at line 525; `_is_read_only` at line 2076; `_is_mutating` at line 2120; the `openWorldHint` set at line 1952)
- Modify: `src/bubble_mcp/runtime_coverage.py` (`NATIVE_SPECIAL_TOOLS`)
- Modify: `tests/unit/test_catalog_audit.py:44`, `tests/unit/test_catalog_inventory.py:15`, `tests/unit/test_catalog_quality.py:38`, `tests/unit/test_catalog_selection.py:16-20,40,41,159`, `tests/unit/test_mcp_server.py:3114` — the hardcoded tool count `327` becomes `329`
- Test: `tests/unit/test_node_edit_tools.py`

**Interfaces:**
- Consumes: `read_live_node` (Task 2), `edit_live_node` (Tasks 3-4).
- Produces: MCP tools `bubble_live_node_read` and `bubble_node_edit`.

The catalog is self-checking. `catalog_quality_report()` verifies that every exposed tool has a description of at least 20 characters, a description no other tool shares, a description of at least 8 characters on every property, all four annotations, and runtime coverage. Five tests assert the exact tool count, which is why they are listed above — an added tool is expected to move that number, and moving it is part of this task, not a regression.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_node_edit_tools.py`:

```python
"""The two live-node tools must be exposed, annotated, and routed."""

from __future__ import annotations

from typing import Any

from bubble_mcp.server.agent_catalog import tool_annotations
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.tools import call_tool


def _schema(name: str) -> dict[str, Any]:
    return {tool["name"]: tool for tool in list_tool_schemas()}[name]


def test_both_tools_are_exposed_with_their_required_arguments() -> None:
    read = _schema("bubble_live_node_read")
    edit = _schema("bubble_node_edit")

    assert read["inputSchema"]["required"] == ["profile", "pointer"]
    assert edit["inputSchema"]["required"] == ["profile", "pointer", "op"]
    assert edit["inputSchema"]["properties"]["op"]["enum"] == ["patch", "reorder"]


def test_the_read_tool_is_annotated_read_only_and_the_edit_tool_is_not() -> None:
    assert tool_annotations("bubble_live_node_read")["readOnlyHint"] is True
    assert tool_annotations("bubble_node_edit")["readOnlyHint"] is False


def test_the_edit_tool_defaults_to_preview() -> None:
    edit = _schema("bubble_node_edit")

    assert edit["inputSchema"]["properties"]["execute"]["default"] is False


def test_read_tool_routes_to_read_live_node(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_read(profile, pointer, **kwargs):  # type: ignore[no-untyped-def]
        seen.update({"profile": profile, "pointer": list(pointer), **kwargs})
        return {"ok": True, "pointer": list(pointer), "node": {"id": "act-1"}}

    monkeypatch.setattr("bubble_mcp.server.tools.read_live_node", fake_read)

    result = call_tool(
        "bubble_live_node_read", {"profile": "mcp-test", "pointer": ["api", "wf-1"]}
    )

    assert result["ok"] is True
    assert seen["profile"] == "mcp-test"
    assert seen["pointer"] == ["api", "wf-1"]


def test_edit_tool_routes_to_edit_live_node(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, Any] = {}

    def fake_edit(**kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return {"ok": True, "execute": False}

    monkeypatch.setattr("bubble_mcp.server.tools.edit_live_node", fake_edit)

    call_tool(
        "bubble_node_edit",
        {
            "profile": "mcp-test",
            "pointer": ["api", "wf-1", "actions", "0"],
            "op": "patch",
            "leaf_pointer": ["properties"],
            "patch": {"param_id": "Order"},
        },
    )

    assert seen["op"] == "patch"
    assert seen["execute"] is False
    assert seen["leaf_pointer"] == ["properties"]


def test_edit_tool_requires_a_profile() -> None:
    try:
        call_tool("bubble_node_edit", {"pointer": ["api"], "op": "patch"})
    except ValueError as error:
        assert "profile" in str(error)
    else:
        raise AssertionError("a missing profile must not reach the editor")
```

`call_tool` is `call_tool(name, arguments=None, *, cancelled=None, progress=None)` (`src/bubble_mcp/server/tools.py:688`), so the positional calls above are correct. It runs `_arguments_with_profile_defaults` first, which only fills `app_id`/`appname`/`app_version` from the profile and never invents a `profile`, so the missing-profile test reaches the handler's own check.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_node_edit_tools.py -q`
Expected: FAIL with `KeyError: 'bubble_live_node_read'`.

- [ ] **Step 3: Add the schema fields**

In `src/bubble_mcp/server/schema_families.py`, add to `FIELD_LIBRARY`:

```python
    "pointer": _prop(
        "array",
        "Child keys addressing a node in the live editor tree, from the app root: "
        '["api", "<workflow_id>", "actions", "3"] for one action, ["api", "<workflow_id>", '
        '"actions"] for the map holding it.',
        items={"type": "string"},
    ),
    "leaf_pointer": _prop(
        "array",
        "Keys addressing the dict to patch, relative to the node at pointer. Every key must "
        "already exist; a missing key is refused rather than created.",
        items={"type": "string"},
    ),
    "patch": _prop(
        "object",
        "Values merged into the dict at leaf_pointer. A value may be a whole subtree, which "
        "is how a field is retargeted from an action that already works.",
        additional_properties=True,
    ),
    "order": _prop(
        "array",
        "Every existing action key, each exactly once, in the new order. An order that would "
        "drop a step is refused.",
        items={"type": "string"},
    ),
    "op": _prop(
        "string",
        "Which in-place edit to run: 'patch' replaces one leaf inside a node, 'reorder' "
        "renumbers an actions map.",
        enum=["patch", "reorder"],
    ),
    "read_headless": _prop(
        "boolean",
        "Run the editor browser without a visible window while reading the node.",
        default=True,
    ),
    "read_timeout_sec": _prop(
        "integer",
        "Seconds to wait for the editor page to expose window.appquery.",
        default=90,
        minimum=10,
    ),
```

Verified against the current library: `profile`, `app_id`, `app_version`, `execute`, and `headless` already exist and must not be redefined. `headless` is deliberately **not** reused — it defaults to `false` and is worded for the interactive login flow, whereas these tools default to headless; hence the separate `read_headless`. The six new keys are named exactly as the tools reference them, because `tool_schema` resolves every entry in its `fields` list through `field(name)` before any override is applied — a name that is not in the library raises `KeyError` at import time.

Then, inside `planning_execution_tools()`, right after the `bubble_editor_write` entry, add:

```python
        tool_schema(
            "bubble_live_node_read",
            "Read one node exactly as the running Bubble editor holds it, through window.appquery in "
            "a browser driven with the stored session. This is the only source for the raw expression "
            "encoding: the .bubble export is the decoded projection and cannot be inverted. Use it to "
            "inspect a working action before editing one, or to learn the shape of an action type the "
            "compiler does not support.",
            ["profile", "pointer", "app_id", "app_version", "read_headless", "read_timeout_sec"],
            required=["profile", "pointer"],
        ),
        tool_schema(
            "bubble_node_edit",
            "Edit a live Bubble node in place: read it from the editor, change one leaf (op='patch') or "
            "renumber an actions map (op='reorder'), write it back with only the node root re-encoded, "
            "then read it again and report where the result diverged from the intent. Prefer this over "
            "recomposing an action, which cannot reproduce expression encodings. execute=false previews; "
            "execute=true mutates and verifies.",
            [
                "profile",
                "pointer",
                "op",
                "leaf_pointer",
                "patch",
                "order",
                "app_id",
                "app_version",
                "execute",
            ],
            required=["profile", "pointer", "op"],
        ),
```

- [ ] **Step 4: Add the handlers**

In `src/bubble_mcp/server/tools.py`, add to the imports:

```python
from bubble_mcp.execution.live_node_read import read_live_node
from bubble_mcp.execution.node_edit import edit_live_node
```

In `call_tool`, immediately after the `bubble_editor_write` branch ends, add:

```python
    if name == "bubble_live_node_read":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_live_node_read requires a profile.")
        pointer = args.get("pointer")
        if not isinstance(pointer, list) or not pointer:
            raise ValueError("bubble_live_node_read requires a non-empty pointer array.")
        return read_live_node(
            profile,
            [str(part) for part in pointer],
            app_id=str(args.get("app_id") or "") or None,
            app_version=str(args.get("app_version") or "test"),
            headless=bool(args.get("read_headless", True)),
            timeout_sec=int(args.get("read_timeout_sec") or 90),
        )
    if name == "bubble_node_edit":
        args = arguments or {}
        profile = str(args.get("profile") or "").strip()
        if not profile:
            raise ValueError("bubble_node_edit requires a profile.")
        pointer = args.get("pointer")
        if not isinstance(pointer, list) or not pointer:
            raise ValueError("bubble_node_edit requires a non-empty pointer array.")
        leaf_pointer = args.get("leaf_pointer")
        order = args.get("order")
        return edit_live_node(
            profile=profile,
            pointer=[str(part) for part in pointer],
            op=str(args.get("op") or ""),
            leaf_pointer=[str(part) for part in leaf_pointer] if isinstance(leaf_pointer, list) else None,
            patch=args.get("patch") if isinstance(args.get("patch"), dict) else None,
            order=[str(part) for part in order] if isinstance(order, list) else None,
            execute=bool(args.get("execute")),
            app_id=str(args.get("app_id") or "") or None,
        )
```

- [ ] **Step 5: Register descriptions, annotations, and coverage**

In `src/bubble_mcp/server/agent_catalog.py`:

- add to `NATIVE_TOOL_DESCRIPTIONS`:

```python
    "bubble_live_node_read": (
        "Read one node as the running Bubble editor holds it, via window.appquery in a browser using "
        "the stored session. The only source of the raw expression encoding; the .bubble export is "
        "decoded and cannot be inverted."
    ),
    "bubble_node_edit": (
        "Edit a live Bubble node in place - patch one leaf or reorder an actions map - re-encoding only "
        "the node root, then re-read the node and report where it diverged from the intent. "
        "execute=false previews."
    ),
```

- add `"bubble_live_node_read"` to the set inside `_is_read_only`;
- add `"bubble_node_edit"` to the `name in {...}` set at the end of `_is_mutating`;
- add both names to the `openWorldHint` set in `tool_annotations` — both drive a browser or the editor endpoint.

In `src/bubble_mcp/runtime_coverage.py`, add both names to `NATIVE_SPECIAL_TOOLS`.

- [ ] **Step 6: Move the tool count**

Two tools are added, so the catalog holds 329. Update every hardcoded occurrence:

Run: `python -m pytest tests/unit/test_catalog_quality.py -q` and read the reported actual count. It must be exactly 329; if it is not, a tool was registered twice or one is missing, and that is the bug to fix rather than the assertion.

Then change `327` to `329` at: `tests/unit/test_catalog_audit.py:44`, `tests/unit/test_catalog_inventory.py:15`, `tests/unit/test_catalog_quality.py:38`, `tests/unit/test_catalog_selection.py` (lines 16-20, 40, 41, 159), `tests/unit/test_mcp_server.py:3114`.

- [ ] **Step 7: Run the tool and catalog tests**

Run: `python -m pytest tests/unit/test_node_edit_tools.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_selection.py tests/unit/test_catalog_audit.py tests/unit/test_catalog_inventory.py tests/unit/test_catalog_descriptions.py -q`
Expected: all pass. A failure in `test_catalog_descriptions.py` means a description here duplicates an existing one — reword this one, never the existing tool's.

- [ ] **Step 8: Run the whole unit suite and compare to the Task 0 baseline**

Run: `python -m pytest tests/unit -q`
Expected: the same failures recorded in Task 0, and no others. Any new failure belongs to this task.

- [ ] **Step 9: Commit**

```bash
git add src/bubble_mcp/server/schema_families.py src/bubble_mcp/server/tools.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/runtime_coverage.py tests/unit/test_node_edit_tools.py tests/unit/test_catalog_audit.py tests/unit/test_catalog_inventory.py tests/unit/test_catalog_quality.py tests/unit/test_catalog_selection.py tests/unit/test_mcp_server.py
git commit -m "feat: expose bubble_live_node_read and bubble_node_edit"
```

---

### Task 6: Point the agent at the new route

**Files:**
- Modify: `src/bubble_mcp/server/agent_guide.py:129` (the workflow-editing note) and `:165-166` (the payload-tools list)
- Modify: `src/bubble_mcp/server/tool_descriptions.py:89` (the `add_action` note)
- Test: `tests/unit/test_agent_guide.py` if one exists; otherwise assert through `tests/unit/test_node_edit_tools.py`

**Interfaces:**
- Consumes: the tool names registered in Task 5.
- Produces: no new API. This is the routing guidance that makes the tools findable.

Today the guide tells an agent that editing an existing expression-heavy action is impossible and to fall back to captured traffic or manual Copy/Paste in the editor. That advice was correct while no live read existed. It is now the wrong default and will keep agents on the broken path if left alone.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_node_edit_tools.py`:

```python
def test_the_workflow_guidance_routes_editing_to_the_new_tool() -> None:
    from bubble_mcp.server.agent_guide import agent_guide

    text = str(agent_guide("edit an action in an existing workflow"))

    assert "bubble_node_edit" in text
    assert "bubble_live_node_read" in text
```

The public entry point is `agent_guide(task="", *, include_knowledge_advice=True)` at `src/bubble_mcp/server/agent_guide.py:1437`; it returns a dict, which is why the test stringifies it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_node_edit_tools.py -q -k guidance`
Expected: FAIL — the names do not appear yet.

- [ ] **Step 3: Update the guidance**

In `src/bubble_mcp/server/agent_guide.py`, in the workflow `notes` string at line 129, replace the sentence that ends `...configure one action by hand and Copy/Paste it in the editor.` with:

```
To EDIT an action that already exists, use bubble_node_edit: it reads the node from the live editor, changes one leaf, and re-reads to prove the write landed. Never recompose an existing action from the export - the expression encoding is not derivable from it. Use bubble_live_node_read first when you need to see the real shape of an action type. For creating a new expression-heavy action, capturing real editor traffic with bubble_tool_wizard_start is still the route.
```

Add `"bubble_live_node_read"` and `"bubble_node_edit"` to the `tools` list at line 165 and extend the note at line 166 to name them.

In `src/bubble_mcp/server/tool_descriptions.py:89`, append to the `add_action` note: `To change an action that already exists, use bubble_node_edit rather than adding a replacement.`

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_node_edit_tools.py -q`
Expected: all pass.

- [ ] **Step 5: Run the full unit suite once more**

Run: `python -m pytest tests/unit -q`
Expected: identical to the Task 0 baseline. `test_catalog_descriptions.py` and any guide snapshot test are the likely places a wording change bites.

- [ ] **Step 6: Commit**

```bash
git add src/bubble_mcp/server/agent_guide.py src/bubble_mcp/server/tool_descriptions.py tests/unit/test_node_edit_tools.py
git commit -m "docs: route existing-action edits to bubble_node_edit"
```

---

### Task 7: Manual validation in the editor

**Files:**
- Create: `docs/session-findings-2026-08-26.md` (the record of what the editor actually did)

**Interfaces:**
- Consumes: both tools, working end to end.
- Produces: the evidence that decides whether the encoding contract in `node_keys.py` is right.

This task needs a human at the Bubble editor and a real profile. It runs only against `mcp-test` (`mcp-test-app`) — never `orana` (`~/.bubble-mcp`), never `auto-on`. Do not start it without the user present.

- [ ] **Step 1: Confirm the browser extra is installed**

Run: `python -c "import playwright; print(playwright.__version__)"`
If it fails: `python -m pip install "befree-bubble-mcp[browser]" && python -m playwright install chromium`.

- [ ] **Step 2: Read a workflow that already works**

Call `bubble_live_node_read` with `profile="mcp-test"` and a pointer to an existing backend workflow. Save the returned node — it is the before-image and the fallback if step 4 fails.

- [ ] **Step 3: Preview one small, reversible edit**

Call `bubble_node_edit` with `execute=false`. Read the previewed `changes`: the body must carry `%x`/`%p` at its root and the untouched interior verbatim. If the body's root still shows `type`/`properties`, stop — the encoder did not run, and writing would produce `[missing: null]`.

- [ ] **Step 4: Execute and let the tool verify**

Re-run with `execute=true`. Expected: `verified: true` and `divergence: null`. If `verified` is false, record the reported path — that path is the bug, and it is a `node_keys.py` or `node_edit.py` bug, not a Bubble one.

- [ ] **Step 5: The human check that cannot be automated**

Open the Bubble editor on `mcp-test-app`, find the edited action, and confirm it renders as a real action rather than `[missing: null]` or an empty field. Identical bytes can still render broken; this step is the only thing that proves the encoding contract.

- [ ] **Step 6: Record the outcome and revert the edit**

Write what happened into `docs/session-findings-2026-08-26.md`: the pointer used, the previewed body, the verification result, and what the editor showed. Then restore the original leaf with a second `bubble_node_edit` call using the before-image from step 2.

- [ ] **Step 7: Commit**

```bash
git add docs/session-findings-2026-08-26.md
git commit -m "docs: record the editor validation of in-place node edit"
```

---

## Notes for the reviewer

Two things in this plan are load-bearing and worth rejecting a task over if they drift:

1. **Only the node root is translated.** Any recursion into `properties` breaks the expression chains this work exists to preserve. If a diff shows `encode_node_root` walking children, that is the bug.
2. **Verification compares in the decoded key space.** If a change ever encodes the intent before calling `first_divergence`, verification becomes self-confirming and the whole point of the re-read is lost.
