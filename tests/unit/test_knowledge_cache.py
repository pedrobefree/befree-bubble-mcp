import json
import os
from pathlib import Path

import pytest

from bubble_mcp.knowledge.cache import (
    fetch_knowledge_record,
    import_knowledge_records,
    knowledge_search,
    source_records_path,
)
from bubble_mcp.knowledge.sanitize import sanitize_remote_docs_query


FIXTURE = Path("tests/fixtures/knowledge/bubble-manual-records.jsonl")


def test_import_and_search_local_bubble_manual_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    result = import_knowledge_records(FIXTURE, source="bubble_manual_gitbook")
    matches = knowledge_search("API Connector authentication", limit=5)

    assert result["ok"] is True
    assert result["imported"] == 2
    assert matches["ok"] is True
    assert matches["count"] == 1
    assert matches["results"][0]["id"] == "bubble-manual:api-connector:authentication"
    assert matches["results"][0]["confidence"] == "official_cached"


def test_fetch_record_includes_provenance(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_knowledge_records(FIXTURE, source="bubble_manual_gitbook")

    payload = fetch_knowledge_record("bubble-manual:data-types:privacy")

    assert payload["ok"] is True
    assert payload["record"]["source"] == "bubble_manual_gitbook"
    assert payload["record"]["source_url"].startswith("https://manual.bubble.io/")


def test_repeated_refresh_does_not_duplicate_search_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    import_knowledge_records(FIXTURE, source="bubble_manual_gitbook")
    import_knowledge_records(FIXTURE, source="bubble_manual_gitbook")
    matches = knowledge_search("API Connector authentication", limit=5)

    assert matches["ok"] is True
    assert matches["count"] == 1
    assert [result["id"] for result in matches["results"]] == [
        "bubble-manual:api-connector:authentication"
    ]


def test_refresh_replaces_source_cache_and_fetch_returns_refreshed_content(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    record = {
        "id": "bubble-manual:api-connector:authentication",
        "source": "bubble_manual_gitbook",
        "source_url": "https://manual.bubble.io/core-resources/api/the-api-connector",
        "title": "API Connector authentication",
        "section_path": ["APIs", "API Connector"],
        "content": "Old authentication content.",
        "summary": "Old summary.",
        "tags": ["api_connector", "authentication"],
        "retrieved_at": "2026-07-04T00:00:00Z",
        "content_hash": "sha256:old",
        "ttl_seconds": 604800,
        "license_note": "Official Bubble manual excerpt cached for local developer assistance.",
        "confidence": "official_cached",
    }
    first.write_text(json.dumps(record) + "\n", encoding="utf-8")
    refreshed = {**record, "content": "Refreshed authentication content.", "content_hash": "sha256:new"}
    second.write_text(json.dumps(refreshed) + "\n", encoding="utf-8")

    import_knowledge_records(first, source="bubble_manual_gitbook")
    import_knowledge_records(second, source="bubble_manual_gitbook")
    payload = fetch_knowledge_record("bubble-manual:api-connector:authentication")

    assert payload["ok"] is True
    assert payload["record"]["content"] == "Refreshed authentication content."
    assert payload["record"]["content_hash"] == "sha256:new"


def test_records_are_deduped_globally_with_lexicographically_later_source_winning(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    base_record = {
        "id": "bubble-manual:api-connector:authentication",
        "source": "alpha_source",
        "source_url": "https://manual.bubble.io/core-resources/api/the-api-connector",
        "title": "API Connector authentication",
        "section_path": ["APIs", "API Connector"],
        "content": "Alpha source content.",
        "summary": "Shared API Connector authentication summary.",
        "tags": ["api_connector", "authentication"],
        "retrieved_at": "2026-07-04T00:00:00Z",
        "content_hash": "sha256:alpha",
        "ttl_seconds": 604800,
        "license_note": "Official Bubble manual excerpt cached for local developer assistance.",
        "confidence": "official_cached",
    }
    alpha = tmp_path / "alpha.jsonl"
    zulu = tmp_path / "zulu.jsonl"
    alpha.write_text(json.dumps(base_record) + "\n", encoding="utf-8")
    zulu.write_text(
        json.dumps(
            {
                **base_record,
                "source": "zulu_source",
                "content": "Zulu source content.",
                "content_hash": "sha256:zulu",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    import_knowledge_records(alpha, source="alpha_source")
    import_knowledge_records(zulu, source="zulu_source")
    tied_mtime = 1_788_000_000
    os.utime(source_records_path("alpha_source"), (tied_mtime, tied_mtime))
    os.utime(source_records_path("zulu_source"), (tied_mtime, tied_mtime))
    matches = knowledge_search("API Connector authentication", limit=5)
    payload = fetch_knowledge_record("bubble-manual:api-connector:authentication")

    assert matches["ok"] is True
    assert matches["count"] == 1
    assert matches["results"][0]["source"] == "zulu_source"
    assert matches["results"][0]["content_hash"] == "sha256:zulu"
    assert payload["ok"] is True
    assert payload["record"]["source"] == "zulu_source"
    assert payload["record"]["content"] == "Zulu source content."


def test_fetch_record_miss_reports_remote_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    payload = fetch_knowledge_record("bubble-manual:missing")

    assert payload == {
        "ok": False,
        "reason": "cache_miss_remote_disabled",
        "record_id": "bubble-manual:missing",
    }


def test_sanitize_remote_query_removes_project_sensitive_values() -> None:
    query = (
        "app my-client-app Author" "ization: Bearer abc.def API Connector private key "
        "client_id=abc123xyz456 client id abc123xyz456 client_id: abc123xyz456 "
        "client-id: abc123xyz456 client id: abc123xyz456 api-connector-authentication"
    )

    sanitized = sanitize_remote_docs_query(query)

    assert "Bearer" not in sanitized
    assert "Authorization" not in sanitized
    assert "my-client-app" not in sanitized
    assert "client_id" not in sanitized
    assert "abc123xyz456" not in sanitized
    assert "API Connector private key" in sanitized
    assert "api-connector-authentication" in sanitized


def test_sanitize_remote_query_preserves_docs_topic_slugs() -> None:
    query = "API Connector api-connector-authentication api-connector-oauth2-authentication privacy-rules migration"

    sanitized = sanitize_remote_docs_query(query)

    assert "API Connector" in sanitized
    assert "api-connector-authentication" in sanitized
    assert "api-connector-oauth2-authentication" in sanitized
    assert "privacy-rules" in sanitized


def test_import_rejects_malformed_jsonl_with_file_and_line_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"id": "valid"}\n{"id":\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"malformed\.jsonl:2"):
        import_knowledge_records(malformed, source="bubble_manual_gitbook")


def test_import_rejects_unsafe_source_path_segment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="safe path segment"):
        import_knowledge_records(FIXTURE, source="../bubble_manual_gitbook")
