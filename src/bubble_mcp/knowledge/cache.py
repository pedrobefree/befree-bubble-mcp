"""Local-first knowledge cache for normalized Bubble manual records."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.knowledge.models import KnowledgeRecord


_SAFE_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def knowledge_root() -> Path:
    return get_config_dir() / "knowledge"


def _safe_source(source: str) -> str:
    normalized = str(source or "").strip()
    if not _SAFE_SOURCE_RE.fullmatch(normalized):
        raise ValueError("Knowledge source must be a safe path segment.")
    if normalized in {".", ".."}:
        raise ValueError("Knowledge source must be a safe path segment.")
    return normalized


def source_records_path(source: str) -> Path:
    return knowledge_root() / _safe_source(source) / "records.jsonl"


def _load_jsonl_records(path: Path) -> list[KnowledgeRecord]:
    records: list[KnowledgeRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed knowledge JSONL at {path}:{line_number}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Malformed knowledge JSONL at {path}:{line_number}: expected object")
            record = KnowledgeRecord.from_dict(payload)
            if not record.id:
                raise ValueError(f"Malformed knowledge JSONL at {path}:{line_number}: missing id")
            records.append(record)
    return records


def import_knowledge_records(path: Path, *, source: str) -> dict[str, Any]:
    """Replace one source cache with normalized records from a local JSONL file."""

    normalized_source = _safe_source(source)
    input_path = Path(path).expanduser()
    records_by_id: dict[str, KnowledgeRecord] = {}
    for record in _load_jsonl_records(input_path):
        records_by_id[record.id] = KnowledgeRecord.from_dict({**record.to_dict(), "source": normalized_source})
    records = list(records_by_id.values())
    output_path = source_records_path(normalized_source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".jsonl.tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    temporary_path.replace(output_path)
    return {"ok": True, "source": normalized_source, "imported": len(records), "path": str(output_path)}


def _all_records() -> list[KnowledgeRecord]:
    """Load cached records with deterministic global id dedupe.

    If multiple source caches contain the same record id, the record from the
    newer cache file wins. If mtimes tie, the lexicographically later source
    directory wins. Explicit source priorities can be added later without
    changing search/fetch semantics.
    """

    root = knowledge_root()
    if not root.exists():
        return []
    records_by_id: dict[str, KnowledgeRecord] = {}
    paths = sorted(
        root.glob("*/records.jsonl"),
        key=lambda path: (path.stat().st_mtime_ns, path.parent.name),
    )
    for path in paths:
        for record in _load_jsonl_records(path):
            records_by_id[record.id] = record
    return list(records_by_id.values())


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_]+", value.lower()) if token]


def _record_search_text(record: KnowledgeRecord) -> str:
    return " ".join(
        [
            record.title,
            record.summary,
            record.content,
            " ".join(record.tags),
        ]
    ).lower()


def _freshness(record: KnowledgeRecord) -> dict[str, Any]:
    return {
        "retrieved_at": record.retrieved_at,
        "ttl_seconds": record.ttl_seconds,
        "cache_only": True,
        "remote_refresh": "disabled",
    }


def knowledge_search(query: str, *, limit: int = 8) -> dict[str, Any]:
    query_text = str(query or "").strip()
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return {"ok": False, "reason": "empty_query", "query": query_text}
    bounded_limit = max(1, min(int(limit or 8), 25))
    scored: list[tuple[int, KnowledgeRecord]] = []
    for record in _all_records():
        search_text = _record_search_text(record)
        score = sum(1 for token in query_tokens if token in search_text)
        if score > 0:
            scored.append((score, record))
    if not scored:
        return {"ok": False, "reason": "cache_miss_remote_disabled", "query": query_text}
    scored.sort(key=lambda item: (-item[0], item[1].title.lower(), item[1].id))
    results = []
    for score, record in scored[:bounded_limit]:
        results.append(
            {
                "id": record.id,
                "source": record.source,
                "source_url": record.source_url,
                "title": record.title,
                "section_path": list(record.section_path),
                "summary": record.summary,
                "tags": list(record.tags),
                "score": score,
                "retrieved_at": record.retrieved_at,
                "content_hash": record.content_hash,
                "freshness": _freshness(record),
                "confidence": record.confidence,
            }
        )
    return {
        "ok": True,
        "query": query_text,
        "limit": bounded_limit,
        "count": len(results),
        "cache_only": True,
        "results": results,
    }


def fetch_knowledge_record(record_id: str) -> dict[str, Any]:
    normalized_id = str(record_id or "").strip()
    for record in _all_records():
        if record.id == normalized_id:
            return {"ok": True, "record": record.to_dict(), "cache_only": True}
    return {"ok": False, "reason": "cache_miss_remote_disabled", "record_id": normalized_id}
