"""Dependency and placeholder resolution for framework programs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{\{steps\.([a-zA-Z0-9_-]+)\.output\.([a-zA-Z0-9_-]+)\}\}")


@dataclass
class DependencyState:
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)


def record_step_outputs(
    state: DependencyState,
    *,
    step_id: str,
    declared_outputs: dict[str, str],
    result: dict[str, Any],
) -> None:
    output_values: dict[str, Any] = {}
    for output_name in declared_outputs:
        if output_name in result:
            output_values[output_name] = result[output_name]
    for key in ("element_id", "id", "call_id", "collection_id", "workflow_id", "field_id"):
        if key in result and key not in output_values:
            output_values[key] = result[key]
    if output_values:
        state.outputs[step_id] = output_values


def _resolve_string(value: str, state: DependencyState) -> str:
    def replace(match: re.Match[str]) -> str:
        step_id, output_name = match.group(1), match.group(2)
        step_outputs = state.outputs.get(step_id, {})
        if output_name not in step_outputs:
            placeholder = match.group(0)
            if placeholder not in state.unresolved:
                state.unresolved.append(placeholder)
            return placeholder
        return str(step_outputs[output_name])

    return PLACEHOLDER_RE.sub(replace, value)


def _resolve_value(value: Any, state: DependencyState) -> Any:
    if isinstance(value, str):
        return _resolve_string(value, state)
    if isinstance(value, dict):
        return {key: _resolve_value(item, state) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, state) for item in value]
    return value


def resolve_step_arguments(args: dict[str, Any], state: DependencyState) -> dict[str, Any]:
    return {key: _resolve_value(value, state) for key, value in args.items()}
