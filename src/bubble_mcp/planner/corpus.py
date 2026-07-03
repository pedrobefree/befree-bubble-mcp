"""Public-safe planner corpus helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any


@dataclass(frozen=True)
class CorpusEntry:
    id: str
    tool_name: str
    risk: str
    utterances: tuple[str, ...]
    default_args: dict[str, Any]


@lru_cache(maxsize=1)
def load_corpus() -> tuple[CorpusEntry, ...]:
    """Load the packaged natural-language routing corpus."""

    raw = resources.files("bubble_mcp.planner").joinpath("corpus.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Planner corpus must be a JSON array.")
    entries: list[CorpusEntry] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        utterances = item.get("utterances")
        defaults = item.get("default_args")
        if not isinstance(utterances, list) or not isinstance(defaults, dict):
            continue
        entries.append(
            CorpusEntry(
                id=str(item.get("id") or ""),
                tool_name=str(item.get("tool_name") or ""),
                risk=str(item.get("risk") or "routine_visual_mutation"),
                utterances=tuple(str(utterance) for utterance in utterances if str(utterance).strip()),
                default_args=dict(defaults),
            )
        )
    return tuple(entry for entry in entries if entry.id and entry.tool_name and entry.utterances)
