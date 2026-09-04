"""Catalog-wide schema-vs-runtime contract snapshot.

Every argument a tool's MCP schema advertises should reach the runtime method
(by name, via ARG_ALIASES, or through **kwargs). Args that do NOT are silently
dropped — the bug class behind event_ref (add_action), reusable_name
(create_reusable_instance), and min_width (create_shape).

The known gaps are frozen in tests/fixtures/schema_runtime_contract_gaps.json.
This test fails when a NEW gap appears (regression) or when a gap is fixed but
not removed from the snapshot (so the baseline only shrinks, never grows).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path


def _compute_gaps() -> dict[str, list[str]]:
    from bubble_mcp.aria_dispatch import ARG_ALIASES, CONTROL_ARG_KEYS, RUNTIME_TOOL_ALIASES
    from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI
    from bubble_mcp.server.agent_catalog import _legacy_fields_for_name
    from bubble_mcp.server.catalog import ARIA_BUBBLE_TOOL_NAMES

    # One alias can feed several runtime params ("type" -> field_type and value_type),
    # so keep every target: a flat dict silently drops all but the last and reports
    # tools whose runtime does accept the arg.
    alias_targets: dict[str, set[str]] = {}
    for param, aliases in ARG_ALIASES.items():
        for alias in aliases:
            alias_targets.setdefault(alias, set()).add(param)
    ignorable = set(CONTROL_ARG_KEYS) | {"profile", "dry_run", "settings_path"}
    report: dict[str, list[str]] = {}
    for tool in ARIA_BUBBLE_TOOL_NAMES:
        fields = _legacy_fields_for_name(tool)
        if not fields:
            continue
        method = getattr(BubbleCLI, RUNTIME_TOOL_ALIASES.get(tool, tool), None)
        if method is None:
            report[tool] = ["<NO RUNTIME METHOD>"]
            continue
        signature = inspect.signature(method)
        params = set(signature.parameters)
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())
        missing = sorted({
            field
            for field in (*fields[0], *fields[1])
            if field not in ignorable
            and field not in params
            and not (alias_targets.get(field, set()) & params)
            and not has_kwargs
        })
        if missing:
            report[tool] = missing
    return report


def test_no_new_schema_args_are_dropped_by_runtime_signatures() -> None:
    snapshot = json.loads(
        Path("tests/fixtures/schema_runtime_contract_gaps.json").read_text(encoding="utf-8")
    )
    current = _compute_gaps()

    regressions = {
        tool: sorted(set(args) - set(snapshot.get(tool, [])))
        for tool, args in current.items()
        if set(args) - set(snapshot.get(tool, []))
    }
    assert regressions == {}, f"NEW dropped schema args (fix the runtime or alias them): {regressions}"

    stale = {
        tool: sorted(set(snapshot.get(tool, [])) - set(current.get(tool, [])))
        for tool in snapshot
        if set(snapshot.get(tool, [])) - set(current.get(tool, []))
    }
    assert stale == {}, (
        f"Snapshot entries no longer dropped — remove them from the fixture so the baseline shrinks: {stale}"
    )


def test_create_reusable_instance_source_has_a_public_runtime_path() -> None:
    """The precision audit must cover the source -> reusable_name dispatch contract."""

    assert "create_reusable_instance" not in _compute_gaps()
