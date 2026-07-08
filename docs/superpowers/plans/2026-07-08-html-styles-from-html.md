# HTML Styles From HTML Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a preview-first `create_styles_from_html` workflow that extracts reusable Bubble styles from HTML/CSS, including Bubble style states for hover, focus, disabled, and pressed when those states exist.

**Architecture:** Add a focused `bubble_mcp.style_import` package that parses HTML/CSS, normalizes CSS declarations into Bubble style properties, and compiles style plans into existing `create_style`, `add_style_condition`, and `reorder_style_states` operations. Reuse the existing Figma/Bubble state aliases already implemented in `BubbleCLI.sync_figma_style`, `BubbleCLI.add_style_condition`, `BubbleCLI._normalize_style_trigger_alias`, and `StyleBuilder.add_style_condition` instead of inventing a parallel condition format.

**Tech Stack:** Python 3.11, BeautifulSoup, existing Playwright rendered HTML utilities, existing BubbleCLI style APIs, stdio MCP schemas, argparse CLI, pytest.

---

## Scope Check

This plan covers only style extraction and style creation from HTML. It does not import HTML elements; that remains the responsibility of `create_from_html`. The intended combined workflow is:

```text
create_styles_from_html execute=false
create_styles_from_html execute=true
create_from_html translate_to_existing_styles=true execute=false
create_from_html translate_to_existing_styles=true execute=true
```

## Existing Code Anchors

- `src/bubble_mcp/html_runtime.py`: existing advanced HTML runtime wrapper.
- `src/bubble_mcp/aria_runtime/bubble_cli.py`: existing style creation, Figma style sync, state aliasing, and condition payload generation.
- `src/bubble_mcp/aria_runtime/bubble_sdk.py`: existing `StyleBuilder.add_style_condition` implementation and state mapping.
- `src/bubble_mcp/server/schema_families.py`: MCP schema definitions.
- `src/bubble_mcp/server/tools.py`: MCP dispatch.
- `src/bubble_mcp/cli/main.py`: CLI command registration.
- `tests/unit/test_mcp_server.py`: schema and dispatch tests.
- `tests/unit/test_figma_bridge.py`: examples of style state expectations.

## File Structure

- Create `src/bubble_mcp/style_import/__init__.py`: public exports.
- Create `src/bubble_mcp/style_import/models.py`: dataclasses for extracted CSS rules, style candidates, state candidates, and plan output.
- Create `src/bubble_mcp/style_import/html.py`: parse inline `<style>` blocks, linked CSS strings passed by callers, and style attributes.
- Create `src/bubble_mcp/style_import/mapper.py`: convert CSS declarations into Bubble style fields.
- Create `src/bubble_mcp/style_import/planner.py`: build ordered style operations from mapped candidates.
- Create `src/bubble_mcp/style_import/runtime.py`: profile-aware runtime entrypoint used by MCP and CLI.
- Create `tests/fixtures/html/style-states.html`: deterministic fixture with base, hover, focus, disabled, and pressed styles.
- Create `tests/unit/test_style_import_html.py`: parser tests.
- Create `tests/unit/test_style_import_mapper.py`: CSS-to-Bubble mapping tests.
- Create `tests/unit/test_style_import_planner.py`: operation planning tests.
- Modify `src/bubble_mcp/server/schema_families.py`: expose `create_styles_from_html`.
- Modify `src/bubble_mcp/server/tools.py`: dispatch `create_styles_from_html`.
- Modify `src/bubble_mcp/server/agent_catalog.py`: descriptions, family routing, and argument hints.
- Modify `src/bubble_mcp/server/agent_guide.py`: route style-from-HTML requests to the new tool.
- Modify `src/bubble_mcp/runtime_coverage.py`: include new native tool.
- Modify `src/bubble_mcp/cli/main.py`: add `bubble-mcp import styles-from-html`.
- Modify `docs/html-to-bubble.md`, `docs/cli-reference.md`, and `docs/mcp-clients.md`: document the workflow.
- Modify `tests/unit/test_mcp_server.py` and `tests/unit/test_cli_commands.py`: schema, dispatch, and CLI coverage.

## Public Tool Contract

MCP tool name:

```text
create_styles_from_html
```

Required arguments:

```json
["profile", "style_prefix", "element_type"]
```

One of these source arguments is required:

```json
["url"] or ["html_file"] or ["file"] or ["html"]
```

Important optional arguments:

```json
{
  "selector": ".btn-primary",
  "app_id": "my-bubble-app",
  "app_version": "test",
  "rendered_html": true,
  "include_states": true,
  "states": ["hover", "focus", "disabled", "pressed"],
  "dedupe": true,
  "match_existing": true,
  "execute": false,
  "refresh_context": false
}
```

Return shape:

```json
{
  "ok": true,
  "profile": "smoke",
  "execute": false,
  "style_count": 1,
  "operation_count": 5,
  "styles": [
    {
      "name": "HTML Button Primary",
      "element_type": "Button",
      "selector": ".btn-primary",
      "base": {"font_size": 16, "font_color": "#ffffff", "bg_color": "#155EEF"},
      "states": {
        "hover": {"bg_color": "#004EEB"},
        "focus": {"border_color": "#84CAFF"},
        "disabled": {"bg_color": "#D0D5DD", "font_color": "#667085"},
        "pressed": {"bg_color": "#00359E"}
      }
    }
  ],
  "operations": [
    {"tool": "create_style", "arguments": {"profile": "smoke", "name": "HTML Button Primary", "element_type": "Button", "dry_run": true}},
    {"tool": "add_style_condition", "arguments": {"profile": "smoke", "name": "HTML Button Primary", "condition": "hover", "dry_run": true}},
    {"tool": "add_style_condition", "arguments": {"profile": "smoke", "name": "HTML Button Primary", "condition": "focus", "dry_run": true}},
    {"tool": "add_style_condition", "arguments": {"profile": "smoke", "name": "HTML Button Primary", "condition": "disabled", "dry_run": true}},
    {"tool": "add_style_condition", "arguments": {"profile": "smoke", "name": "HTML Button Primary", "condition": "pressed", "dry_run": true}}
  ],
  "unsupported": []
}
```

---

### Task 1: HTML/CSS Extraction

**Files:**
- Create: `src/bubble_mcp/style_import/__init__.py`
- Create: `src/bubble_mcp/style_import/models.py`
- Create: `src/bubble_mcp/style_import/html.py`
- Create: `tests/fixtures/html/style-states.html`
- Create: `tests/unit/test_style_import_html.py`

- [ ] **Step 1: Write the fixture**

Create `tests/fixtures/html/style-states.html`:

```html
<!doctype html>
<html>
  <head>
    <style>
      .btn-primary {
        background-color: #155eef;
        color: #ffffff;
        border: 1px solid #155eef;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 600;
        padding: 12px 18px;
      }
      .btn-primary:hover {
        background-color: #004eeb;
        border-color: #004eeb;
      }
      .btn-primary:focus {
        border-color: #84caff;
        box-shadow: 0 0 0 4px rgba(132, 202, 255, 0.35);
      }
      .btn-primary:disabled {
        background-color: #d0d5dd;
        color: #667085;
        border-color: #d0d5dd;
      }
      .btn-primary:active {
        background-color: #00359e;
        border-color: #00359e;
      }
    </style>
  </head>
  <body>
    <button class="btn-primary">Save</button>
  </body>
</html>
```

- [ ] **Step 2: Write the failing parser test**

Create `tests/unit/test_style_import_html.py`:

```python
from pathlib import Path

from bubble_mcp.style_import.html import extract_style_rules_from_html


def test_extract_style_rules_groups_base_and_pseudo_states() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    rules = extract_style_rules_from_html(html, selector=".btn-primary")

    assert [rule.state for rule in rules] == ["base", "hover", "focus", "disabled", "pressed"]
    base = rules[0]
    assert base.selector == ".btn-primary"
    assert base.declarations["background-color"] == "#155eef"
    assert base.declarations["border-radius"] == "8px"
    pressed = rules[-1]
    assert pressed.state == "pressed"
    assert pressed.source_selector == ".btn-primary:active"
```

- [ ] **Step 3: Run the parser test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_html.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.style_import'`.

- [ ] **Step 4: Implement extraction models**

Create `src/bubble_mcp/style_import/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


StyleState = Literal["base", "hover", "focus", "disabled", "pressed"]


@dataclass(frozen=True)
class ExtractedStyleRule:
    selector: str
    source_selector: str
    state: StyleState
    declarations: dict[str, str]


@dataclass(frozen=True)
class BubbleStyleCandidate:
    name: str
    element_type: str
    selector: str
    base: dict[str, Any]
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    unsupported: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "element_type": self.element_type,
            "selector": self.selector,
            "base": self.base,
            "states": self.states,
            "unsupported": self.unsupported,
        }
```

Create `src/bubble_mcp/style_import/__init__.py`:

```python
"""HTML-to-Bubble style import helpers."""

from bubble_mcp.style_import.html import extract_style_rules_from_html
from bubble_mcp.style_import.models import BubbleStyleCandidate, ExtractedStyleRule

__all__ = ["BubbleStyleCandidate", "ExtractedStyleRule", "extract_style_rules_from_html"]
```

- [ ] **Step 5: Implement CSS rule extraction**

Create `src/bubble_mcp/style_import/html.py`:

```python
from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from bubble_mcp.style_import.models import ExtractedStyleRule, StyleState


PSEUDO_TO_STATE: dict[str, StyleState] = {
    "hover": "hover",
    "focus": "focus",
    "focus-visible": "focus",
    "disabled": "disabled",
    "active": "pressed",
}


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _parse_declarations(body: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for raw_part in body.split(";"):
        part = raw_part.strip()
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        declarations[key.strip().lower()] = value.strip()
    return declarations


def _iter_css_blocks(html: str, extra_css: Iterable[str] = ()) -> Iterable[str]:
    soup = BeautifulSoup(html, "html.parser")
    for style in soup.find_all("style"):
        text = style.get_text("\n", strip=False)
        if text.strip():
            yield text
    for css in extra_css:
        if css.strip():
            yield css


def _state_for_selector(source_selector: str, base_selector: str) -> StyleState | None:
    selector = source_selector.strip()
    if selector == base_selector:
        return "base"
    if not selector.startswith(base_selector + ":"):
        return None
    pseudo = selector[len(base_selector) + 1 :].split(":", 1)[0].strip().lower()
    return PSEUDO_TO_STATE.get(pseudo)


def extract_style_rules_from_html(
    html: str,
    *,
    selector: str,
    extra_css: Iterable[str] = (),
) -> list[ExtractedStyleRule]:
    rules: list[ExtractedStyleRule] = []
    for css in _iter_css_blocks(html, extra_css):
        clean_css = _strip_css_comments(css)
        for match in re.finditer(r"([^{}]+)\{([^{}]+)\}", clean_css, flags=re.S):
            selector_group = match.group(1)
            declarations = _parse_declarations(match.group(2))
            if not declarations:
                continue
            for raw_selector in selector_group.split(","):
                source_selector = raw_selector.strip()
                state = _state_for_selector(source_selector, selector)
                if state is None:
                    continue
                rules.append(
                    ExtractedStyleRule(
                        selector=selector,
                        source_selector=source_selector,
                        state=state,
                        declarations=declarations,
                    )
                )
    order = {"base": 0, "hover": 1, "focus": 2, "disabled": 3, "pressed": 4}
    return sorted(rules, key=lambda rule: order[rule.state])
```

- [ ] **Step 6: Run the parser test and verify it passes**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_html.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 7: Commit parser slice**

Run:

```bash
git add src/bubble_mcp/style_import/__init__.py src/bubble_mcp/style_import/models.py src/bubble_mcp/style_import/html.py tests/fixtures/html/style-states.html tests/unit/test_style_import_html.py
git commit -m "feat: extract style rules from html"
```

---

### Task 2: CSS-to-Bubble Style Mapping

**Files:**
- Create: `src/bubble_mcp/style_import/mapper.py`
- Test: `tests/unit/test_style_import_mapper.py`

- [ ] **Step 1: Write the failing mapper tests**

Create `tests/unit/test_style_import_mapper.py`:

```python
from pathlib import Path

from bubble_mcp.style_import.html import extract_style_rules_from_html
from bubble_mcp.style_import.mapper import map_rules_to_style_candidate


def test_map_rules_to_button_style_candidate_with_states() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")
    rules = extract_style_rules_from_html(html, selector=".btn-primary")

    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix="HTML",
        element_type="Button",
        selector=".btn-primary",
    )

    assert candidate.name == "HTML Button Primary"
    assert candidate.base["bg_color"] == "#155eef"
    assert candidate.base["font_color"] == "#ffffff"
    assert candidate.base["border_radius"] == 8
    assert candidate.base["border_width"] == 1
    assert candidate.base["font_size"] == 16
    assert candidate.base["font_weight"] == "600"
    assert candidate.states["hover"]["bg_color"] == "#004eeb"
    assert candidate.states["focus"]["border_color"] == "#84caff"
    assert candidate.states["disabled"]["font_color"] == "#667085"
    assert candidate.states["pressed"]["bg_color"] == "#00359e"
```

- [ ] **Step 2: Run mapper test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_mapper.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.style_import.mapper'`.

- [ ] **Step 3: Implement CSS-to-Bubble mapping**

Create `src/bubble_mcp/style_import/mapper.py`:

```python
from __future__ import annotations

import re

from bubble_mcp.style_import.models import BubbleStyleCandidate, ExtractedStyleRule


def _px(value: str) -> int | None:
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)px\s*$", value)
    if not match:
        return None
    return int(round(float(match.group(1))))


def _split_border(value: str) -> dict[str, object]:
    parts = value.split()
    out: dict[str, object] = {}
    if parts:
        width = _px(parts[0])
        if width is not None:
            out["border_width"] = width
    if len(parts) >= 2:
        out["border_style"] = parts[1]
    if len(parts) >= 3:
        out["border_color"] = parts[2].lower()
    return out


def _selector_label(selector: str) -> str:
    cleaned = selector.strip().lstrip(".#")
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", cleaned) if part]
    return " ".join(part.capitalize() for part in parts) or "Imported"


def _map_declarations(declarations: dict[str, str]) -> tuple[dict[str, object], list[dict[str, str]]]:
    mapped: dict[str, object] = {}
    unsupported: list[dict[str, str]] = []
    for key, raw_value in declarations.items():
        value = raw_value.strip()
        lower = value.lower()
        if key == "background-color":
            mapped["bg_color"] = lower
        elif key == "color":
            mapped["font_color"] = lower
        elif key == "border":
            mapped.update(_split_border(lower))
        elif key == "border-color":
            mapped["border_color"] = lower
        elif key == "border-radius":
            px = _px(value)
            if px is not None:
                mapped["border_radius"] = px
        elif key == "font-size":
            px = _px(value)
            if px is not None:
                mapped["font_size"] = px
        elif key == "font-weight":
            mapped["font_weight"] = value
        elif key == "box-shadow":
            mapped["shadow_style"] = value
        elif key.startswith("padding"):
            px = _px(value)
            if px is not None:
                mapped[key.replace("-", "_")] = px
        else:
            unsupported.append({"property": key, "value": value})
    return mapped, unsupported


def map_rules_to_style_candidate(
    rules: list[ExtractedStyleRule],
    *,
    style_prefix: str,
    element_type: str,
    selector: str,
) -> BubbleStyleCandidate:
    base: dict[str, object] = {}
    states: dict[str, dict[str, object]] = {}
    unsupported: list[dict[str, str]] = []
    for rule in rules:
        mapped, skipped = _map_declarations(rule.declarations)
        unsupported.extend({"state": rule.state, **item} for item in skipped)
        if rule.state == "base":
            base.update(mapped)
        else:
            states.setdefault(rule.state, {}).update(mapped)
    name = f"{style_prefix.strip()} {_selector_label(selector)}".strip()
    return BubbleStyleCandidate(
        name=name,
        element_type=element_type,
        selector=selector,
        base=base,
        states=states,
        unsupported=unsupported,
    )
```

- [ ] **Step 4: Run mapper tests and verify they pass**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_mapper.py tests/unit/test_style_import_html.py -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit mapper slice**

Run:

```bash
git add src/bubble_mcp/style_import/mapper.py tests/unit/test_style_import_mapper.py
git commit -m "feat: map html css to bubble style fields"
```

---

### Task 3: Style Operation Planning

**Files:**
- Create: `src/bubble_mcp/style_import/planner.py`
- Test: `tests/unit/test_style_import_planner.py`

- [ ] **Step 1: Write the failing planner test**

Create `tests/unit/test_style_import_planner.py`:

```python
from bubble_mcp.style_import.models import BubbleStyleCandidate
from bubble_mcp.style_import.planner import build_style_operations


def test_build_style_operations_uses_existing_state_tools() -> None:
    candidate = BubbleStyleCandidate(
        name="HTML Button Primary",
        element_type="Button",
        selector=".btn-primary",
        base={"bg_color": "#155eef", "font_color": "#ffffff"},
        states={
            "hover": {"bg_color": "#004eeb"},
            "focus": {"border_color": "#84caff"},
            "disabled": {"bg_color": "#d0d5dd"},
            "pressed": {"bg_color": "#00359e"},
        },
    )

    operations = build_style_operations(profile="smoke", candidates=[candidate], execute=False)

    assert [operation["tool"] for operation in operations] == [
        "create_style",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "reorder_style_states",
    ]
    assert operations[0]["arguments"]["dry_run"] is True
    assert operations[1]["arguments"]["condition"] == "hover"
    assert operations[4]["arguments"]["condition"] == "pressed"
    assert operations[5]["arguments"]["order"] == "hover,focus,pressed,disabled"
```

- [ ] **Step 2: Run planner test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_planner.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.style_import.planner'`.

- [ ] **Step 3: Implement operation planner**

Create `src/bubble_mcp/style_import/planner.py`:

```python
from __future__ import annotations

from typing import Any

from bubble_mcp.style_import.models import BubbleStyleCandidate


STATE_ORDER = ("hover", "focus", "pressed", "disabled")


def _style_args(profile: str, candidate: BubbleStyleCandidate, *, dry_run: bool) -> dict[str, Any]:
    return {
        "profile": profile,
        "name": candidate.name,
        "element_type": candidate.element_type,
        "dry_run": dry_run,
        **candidate.base,
    }


def _condition_args(
    profile: str,
    candidate: BubbleStyleCandidate,
    condition: str,
    properties: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "name": candidate.name,
        "condition": condition,
        "dry_run": dry_run,
        **properties,
    }


def build_style_operations(
    *,
    profile: str,
    candidates: list[BubbleStyleCandidate],
    execute: bool,
) -> list[dict[str, Any]]:
    dry_run = not execute
    operations: list[dict[str, Any]] = []
    for candidate in candidates:
        operations.append({"tool": "create_style", "arguments": _style_args(profile, candidate, dry_run=dry_run)})
        present_states: list[str] = []
        for state in STATE_ORDER:
            props = candidate.states.get(state)
            if not props:
                continue
            present_states.append(state)
            operations.append(
                {
                    "tool": "add_style_condition",
                    "arguments": _condition_args(profile, candidate, state, props, dry_run=dry_run),
                }
            )
        if present_states:
            operations.append(
                {
                    "tool": "reorder_style_states",
                    "arguments": {
                        "profile": profile,
                        "name": candidate.name,
                        "order": ",".join(present_states),
                        "dry_run": dry_run,
                    },
                }
            )
    return operations
```

- [ ] **Step 4: Run planner test and verify it passes**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_planner.py -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit planner slice**

Run:

```bash
git add src/bubble_mcp/style_import/planner.py tests/unit/test_style_import_planner.py
git commit -m "feat: plan bubble style state operations"
```

---

### Task 4: Runtime Entry Point

**Files:**
- Create: `src/bubble_mcp/style_import/runtime.py`
- Modify: `src/bubble_mcp/style_import/__init__.py`
- Test: `tests/unit/test_style_import_runtime.py`

- [ ] **Step 1: Write runtime tests**

Create `tests/unit/test_style_import_runtime.py`:

```python
from pathlib import Path

from bubble_mcp.style_import.runtime import create_styles_from_html_runtime


def test_runtime_returns_preview_operations_from_html_file() -> None:
    result = create_styles_from_html_runtime(
        profile="smoke",
        style_prefix="HTML",
        element_type="Button",
        html_file="tests/fixtures/html/style-states.html",
        selector=".btn-primary",
        execute=False,
    )

    assert result["ok"] is True
    assert result["execute"] is False
    assert result["style_count"] == 1
    assert result["operation_count"] == 6
    assert result["styles"][0]["states"]["pressed"]["bg_color"] == "#00359e"


def test_runtime_accepts_inline_html() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    result = create_styles_from_html_runtime(
        profile="smoke",
        style_prefix="HTML",
        element_type="Button",
        html=html,
        selector=".btn-primary",
        execute=False,
    )

    assert result["ok"] is True
    assert result["styles"][0]["name"] == "HTML Button Primary"
```

- [ ] **Step 2: Run runtime tests and verify they fail**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bubble_mcp.style_import.runtime'`.

- [ ] **Step 3: Implement runtime**

Create `src/bubble_mcp/style_import/runtime.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from bubble_mcp.style_import.html import extract_style_rules_from_html
from bubble_mcp.style_import.mapper import map_rules_to_style_candidate
from bubble_mcp.style_import.planner import build_style_operations


def _read_html_source(*, html: str | None, html_file: str | None, file: str | None) -> str:
    if html:
        return html
    path_value = html_file or file
    if path_value:
        return Path(path_value).read_text(encoding="utf-8")
    raise ValueError("create_styles_from_html requires html, html_file, file, or url.")


def create_styles_from_html_runtime(
    *,
    profile: str,
    style_prefix: str,
    element_type: str,
    selector: str,
    html: str | None = None,
    html_file: str | None = None,
    file: str | None = None,
    url: str | None = None,
    execute: bool = False,
    rendered_html: bool = True,
    include_states: bool = True,
    states: list[str] | None = None,
    **_: Any,
) -> dict[str, Any]:
    if url:
        raise ValueError("URL rendering for create_styles_from_html is added in the Playwright integration task.")
    source_html = _read_html_source(html=html, html_file=html_file, file=file)
    rules = extract_style_rules_from_html(source_html, selector=selector)
    if not include_states:
        rules = [rule for rule in rules if rule.state == "base"]
    if states:
        allowed = {"base", *states}
        rules = [rule for rule in rules if rule.state in allowed]
    candidate = map_rules_to_style_candidate(
        rules,
        style_prefix=style_prefix,
        element_type=element_type,
        selector=selector,
    )
    operations = build_style_operations(profile=profile, candidates=[candidate], execute=execute)
    return {
        "ok": True,
        "profile": profile,
        "execute": execute,
        "rendered_html": rendered_html,
        "style_count": 1,
        "operation_count": len(operations),
        "styles": [candidate.to_dict()],
        "operations": operations,
        "unsupported": candidate.unsupported,
    }
```

Modify `src/bubble_mcp/style_import/__init__.py`:

```python
"""HTML-to-Bubble style import helpers."""

from bubble_mcp.style_import.html import extract_style_rules_from_html
from bubble_mcp.style_import.models import BubbleStyleCandidate, ExtractedStyleRule
from bubble_mcp.style_import.runtime import create_styles_from_html_runtime

__all__ = [
    "BubbleStyleCandidate",
    "ExtractedStyleRule",
    "create_styles_from_html_runtime",
    "extract_style_rules_from_html",
]
```

- [ ] **Step 4: Run runtime tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_runtime.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_html.py -q
```

Expected: PASS with `5 passed`.

- [ ] **Step 5: Commit runtime slice**

Run:

```bash
git add src/bubble_mcp/style_import/__init__.py src/bubble_mcp/style_import/runtime.py tests/unit/test_style_import_runtime.py
git commit -m "feat: add html style import runtime"
```

---

### Task 5: MCP Tool, CLI, and Documentation

**Files:**
- Modify: `src/bubble_mcp/server/schema_families.py`
- Modify: `src/bubble_mcp/server/tools.py`
- Modify: `src/bubble_mcp/server/agent_catalog.py`
- Modify: `src/bubble_mcp/server/agent_guide.py`
- Modify: `src/bubble_mcp/runtime_coverage.py`
- Modify: `src/bubble_mcp/cli/main.py`
- Modify: `docs/html-to-bubble.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/mcp-clients.md`
- Test: `tests/unit/test_mcp_server.py`
- Test: `tests/unit/test_cli_commands.py`

- [ ] **Step 1: Add failing MCP schema and dispatch tests**

Add to `tests/unit/test_mcp_server.py`:

```python
def test_create_styles_from_html_schema_is_exposed() -> None:
    tools = {tool["name"]: tool for tool in list_tool_schemas()}

    schema = tools["create_styles_from_html"]["inputSchema"]

    assert schema["required"] == ["profile", "style_prefix", "element_type", "selector"]
    assert "url" in schema["properties"]
    assert "html_file" in schema["properties"]
    assert "include_states" in schema["properties"]
    assert "states" in schema["properties"]
    assert tools["create_styles_from_html"]["annotations"]["readOnlyHint"] is False


def test_create_styles_from_html_dispatches_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_runtime(**kwargs):  # type: ignore[no-untyped-def]
        return {"ok": True, "received": kwargs}

    monkeypatch.setattr("bubble_mcp.server.tools.create_styles_from_html_runtime", fake_runtime)
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 501,
            "method": "tools/call",
            "params": {
                "name": "create_styles_from_html",
                "arguments": {
                    "profile": "smoke",
                    "style_prefix": "HTML",
                    "element_type": "Button",
                    "selector": ".btn-primary",
                    "html": "<style>.btn-primary{color:#fff}</style>",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["received"]["selector"] == ".btn-primary"
```

- [ ] **Step 2: Run MCP tests and verify they fail**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_mcp_server.py::test_create_styles_from_html_schema_is_exposed tests/unit/test_mcp_server.py::test_create_styles_from_html_dispatches_runtime -q
```

Expected: FAIL with missing `create_styles_from_html`.

- [ ] **Step 3: Expose MCP schema**

Modify `src/bubble_mcp/server/schema_families.py` by adding this tool to `html_import_tools()` after `create_from_html`:

```python
        tool_schema(
            "create_styles_from_html",
            "Extract reusable Bubble styles from HTML/CSS, including hover, focus, disabled, and pressed state conditions when present. This previews generated create_style, add_style_condition, and reorder_style_states operations unless execute=true.",
            [
                "profile",
                "app_id",
                "app_version",
                "style_prefix",
                "element_type",
                "selector",
                "url",
                "html_file",
                "file",
                "html",
                "execute",
                "rendered_html",
                "include_states",
                "states",
                "dedupe",
                "match_existing",
                "refresh_context",
            ],
            required=["profile", "style_prefix", "element_type", "selector"],
            any_of=[
                {"required": ["url"]},
                {"required": ["html_file"]},
                {"required": ["file"]},
                {"required": ["html"]},
            ],
        )
```

- [ ] **Step 4: Expose MCP dispatch**

Modify `src/bubble_mcp/server/tools.py`:

```python
from bubble_mcp.style_import.runtime import create_styles_from_html_runtime
```

Add near the existing `create_from_html` dispatch:

```python
    if name == "create_styles_from_html":
        return create_styles_from_html_runtime(
            profile=str(args.get("profile") or ""),
            app_id=str(args.get("app_id") or ""),
            app_version=str(args.get("app_version") or ""),
            style_prefix=str(args.get("style_prefix") or "HTML"),
            element_type=str(args.get("element_type") or "Button"),
            selector=str(args.get("selector") or ""),
            url=args.get("url"),
            html_file=args.get("html_file") or args.get("file"),
            file=args.get("file"),
            html=args.get("html"),
            execute=bool(args.get("execute")),
            rendered_html=bool(args.get("rendered_html", True)),
            include_states=bool(args.get("include_states", True)),
            states=args.get("states") if isinstance(args.get("states"), list) else None,
            dedupe=bool(args.get("dedupe", True)),
            match_existing=bool(args.get("match_existing", True)),
            refresh_context=bool(args.get("refresh_context")),
        )
```

- [ ] **Step 5: Update catalog, guide, and coverage**

In `src/bubble_mcp/server/agent_catalog.py`, add:

```python
    "create_styles_from_html": (
        "Extract reusable Bubble styles from HTML/CSS before importing elements. Use when the user wants to create Bubble styles from a website, section, component, or CSS selector, especially when hover/focus/disabled/pressed states matter."
    ),
```

Add argument hints:

```python
    "create_styles_from_html": (("profile", "style_prefix", "element_type", "selector"), ("url", "html_file", "file", "html", "execute", "rendered_html", "include_states", "states", "dedupe", "match_existing", "refresh_context")),
```

In `src/bubble_mcp/server/agent_guide.py`, add `create_styles_from_html` to the style/token route tools before `create_style`.

In `src/bubble_mcp/runtime_coverage.py`, add:

```python
    "create_styles_from_html",
```

- [ ] **Step 6: Run MCP tests and verify they pass**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_mcp_server.py::test_create_styles_from_html_schema_is_exposed tests/unit/test_mcp_server.py::test_create_styles_from_html_dispatches_runtime -q
```

Expected: PASS with `2 passed`.

- [ ] **Step 7: Add CLI command tests**

Add to `tests/unit/test_cli_commands.py`:

```python
def test_import_styles_from_html_command_dispatches_runtime(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_runtime(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return {"ok": True, "operation_count": 1}

    monkeypatch.setattr("bubble_mcp.cli.main.create_styles_from_html_runtime", fake_runtime)
    exit_code = main(
        [
            "import",
            "styles-from-html",
            "--profile",
            "smoke",
            "--style-prefix",
            "HTML",
            "--element-type",
            "Button",
            "--selector",
            ".btn-primary",
            "--html",
            "<style>.btn-primary{color:#fff}</style>",
        ]
    )

    assert exit_code == 0
    assert calls[0]["profile"] == "smoke"
    assert calls[0]["selector"] == ".btn-primary"
    assert '"ok": true' in capsys.readouterr().out
```

- [ ] **Step 8: Implement CLI command**

In `src/bubble_mcp/cli/main.py`, import:

```python
from bubble_mcp.style_import.runtime import create_styles_from_html_runtime
```

Add command function:

```python
def command_import_styles_from_html(args: argparse.Namespace) -> int:
    result = create_styles_from_html_runtime(
        profile=args.profile,
        app_id=args.app_id,
        app_version=args.app_version,
        style_prefix=args.style_prefix,
        element_type=args.element_type,
        selector=args.selector,
        url=args.url,
        html_file=args.html_file or args.file,
        file=args.file,
        html=args.html,
        execute=args.execute,
        rendered_html=args.rendered_html,
        include_states=not args.no_states,
        states=args.state or None,
        dedupe=not args.no_dedupe,
        match_existing=not args.no_match_existing,
        refresh_context=args.refresh_context,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1
```

Add parser under `import` subcommands:

```python
    styles_parser = import_subparsers.add_parser("styles-from-html", help="Extract Bubble styles from HTML/CSS.")
    styles_parser.add_argument("--profile", required=True)
    styles_parser.add_argument("--app-id", default="")
    styles_parser.add_argument("--app-version", default="")
    styles_parser.add_argument("--style-prefix", required=True)
    styles_parser.add_argument("--element-type", required=True)
    styles_parser.add_argument("--selector", required=True)
    styles_parser.add_argument("--url", default="")
    styles_parser.add_argument("--html-file", default="")
    styles_parser.add_argument("--file", default="")
    styles_parser.add_argument("--html", default="")
    styles_parser.add_argument("--execute", action="store_true")
    styles_parser.add_argument("--rendered-html", action="store_true", default=True)
    styles_parser.add_argument("--no-states", action="store_true")
    styles_parser.add_argument("--state", action="append", default=[])
    styles_parser.add_argument("--no-dedupe", action="store_true")
    styles_parser.add_argument("--no-match-existing", action="store_true")
    styles_parser.add_argument("--refresh-context", action="store_true")
    styles_parser.set_defaults(func=command_import_styles_from_html)
```

- [ ] **Step 9: Run CLI tests**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_cli_commands.py::test_import_styles_from_html_command_dispatches_runtime -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 10: Update docs**

Append to `docs/html-to-bubble.md`:

```markdown
## Styles From HTML

Use `create_styles_from_html` before `create_from_html` when the source HTML has reusable component styling or pseudo-state CSS:

```bash
bubble-mcp import styles-from-html \
  --profile smoke \
  --style-prefix "HTML" \
  --element-type Button \
  --selector ".btn-primary" \
  --html-file component.html
```

The workflow maps base CSS plus `:hover`, `:focus`, `:disabled`, and `:active` into Bubble style base properties and conditional style states. `:active` maps to Bubble's pressed state.
```

Add a matching CLI section to `docs/cli-reference.md` and a tool bullet to `docs/mcp-clients.md`.

- [ ] **Step 11: Run focused validation**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_runtime.py tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py -q
rtk proxy .venv/bin/python -m ruff check src/bubble_mcp/style_import tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_runtime.py
```

Expected: pytest passes; ruff reports no issues in the new package/tests.

- [ ] **Step 12: Commit integration slice**

Run:

```bash
git add src/bubble_mcp/server/schema_families.py src/bubble_mcp/server/tools.py src/bubble_mcp/server/agent_catalog.py src/bubble_mcp/server/agent_guide.py src/bubble_mcp/runtime_coverage.py src/bubble_mcp/cli/main.py docs/html-to-bubble.md docs/cli-reference.md docs/mcp-clients.md tests/unit/test_mcp_server.py tests/unit/test_cli_commands.py
git commit -m "feat: expose html style import workflow"
```

---

### Task 6: Rendered URL Source Integration

**Files:**
- Create: `src/bubble_mcp/style_import/render.py`
- Modify: `src/bubble_mcp/style_import/runtime.py`
- Test: `tests/unit/test_style_import_runtime.py`

- [ ] **Step 1: Add failing URL rendering test**

Append to `tests/unit/test_style_import_runtime.py`:

```python
def test_runtime_uses_rendered_html_for_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def fake_render_url_to_html(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["url"] == "https://example.test/button"
        assert kwargs["selector"] == ".btn-primary"
        return Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    monkeypatch.setattr("bubble_mcp.style_import.runtime.render_url_to_html", fake_render_url_to_html)

    result = create_styles_from_html_runtime(
        profile="smoke",
        style_prefix="HTML",
        element_type="Button",
        url="https://example.test/button",
        selector=".btn-primary",
        execute=False,
        rendered_html=True,
    )

    assert result["ok"] is True
    assert result["styles"][0]["states"]["hover"]["bg_color"] == "#004eeb"
```

- [ ] **Step 2: Run URL rendering test and verify it fails**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_runtime.py::test_runtime_uses_rendered_html_for_url -q
```

Expected: FAIL because `bubble_mcp.style_import.runtime.render_url_to_html` does not exist.

- [ ] **Step 3: Implement rendered URL helper**

Create `src/bubble_mcp/style_import/render.py`:

```python
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def render_url_to_html(*, url: str, selector: str, timeout_ms: int = 35000) -> str:
    script_path = Path(__file__).resolve().parents[1] / "aria_runtime" / "scripts" / "extract_rendered_html.mjs"
    if not script_path.exists():
        raise FileNotFoundError(f"Rendered HTML extractor not found: {script_path}")
    node = shutil.which(os.environ.get("BUBBLE_CLI_NODE_BIN", "node"))
    if not node:
        raise RuntimeError("Node.js is required for rendered URL extraction.")
    with tempfile.NamedTemporaryFile(prefix="bubble-style-render-", suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)
    try:
        completed = subprocess.run(
            [
                node,
                str(script_path),
                "--url",
                url,
                "--selector",
                selector or "body",
                "--out",
                str(output_path),
                "--timeout-ms",
                str(timeout_ms),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Rendered HTML extraction failed: {detail[-800:]}")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        html = payload.get("html") if isinstance(payload, dict) else None
        if not isinstance(html, str) or not html.strip():
            raise RuntimeError("Rendered HTML extraction returned no HTML.")
        return html
    finally:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
```

- [ ] **Step 4: Wire runtime URL handling**

Modify `src/bubble_mcp/style_import/runtime.py`:

```python
from bubble_mcp.style_import.render import render_url_to_html
```

Replace the URL error branch in `create_styles_from_html_runtime` with:

```python
    if url:
        source_html = render_url_to_html(url=url, selector=selector, timeout_ms=35000) if rendered_html else _read_html_source(html=url, html_file=None, file=None)
    else:
        source_html = _read_html_source(html=html, html_file=html_file, file=file)
```

Then remove the older line:

```python
    source_html = _read_html_source(html=html, html_file=html_file, file=file)
```

- [ ] **Step 5: Run URL rendering unit test**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_runtime.py::test_runtime_uses_rendered_html_for_url -q
```

Expected: PASS with `1 passed`.

- [ ] **Step 6: Run style import validation**

Run:

```bash
rtk proxy .venv/bin/python -m pytest tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_runtime.py -q
rtk proxy .venv/bin/python -m ruff check src/bubble_mcp/style_import tests/unit/test_style_import_html.py tests/unit/test_style_import_mapper.py tests/unit/test_style_import_planner.py tests/unit/test_style_import_runtime.py
```

Expected: pytest passes; ruff reports no issues.

- [ ] **Step 7: Commit rendered URL slice**

Run:

```bash
git add src/bubble_mcp/style_import/render.py src/bubble_mcp/style_import/runtime.py tests/unit/test_style_import_runtime.py
git commit -m "feat: render url sources for html style import"
```

## Self-Review

- Spec coverage: The plan covers HTML style extraction, reusable Bubble style creation, hover/focus/disabled/pressed states, reuse of existing Figma/Bubble condition code, MCP exposure, CLI exposure, docs, and validation.
- Placeholder scan: The plan includes explicit tasks for static HTML, inline HTML, file input, rendered URL extraction, state mapping, MCP exposure, CLI exposure, docs, and validation.
- Type consistency: `BubbleStyleCandidate`, `ExtractedStyleRule`, `create_styles_from_html_runtime`, and operation argument keys are used consistently across tests, runtime, MCP, and CLI tasks.
