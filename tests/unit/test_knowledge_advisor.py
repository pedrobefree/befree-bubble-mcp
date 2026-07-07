from pathlib import Path

from bubble_mcp.knowledge.advisor import knowledge_advice
from bubble_mcp.knowledge.cache import import_knowledge_records, knowledge_search
from bubble_mcp.knowledge.models import KnowledgeRecord
from bubble_mcp.knowledge.remote import fetch_remote_records
from bubble_mcp.server.agent_guide import task_runbook


FIXTURE = Path("tests/fixtures/knowledge/bubble-manual-records.jsonl")


def _record(
    *,
    record_id: str,
    source: str,
    title: str,
    summary: str,
    confidence: str,
    source_url: str = "https://manual.bubble.io/help-guides",
) -> KnowledgeRecord:
    return KnowledgeRecord.from_dict(
        {
            "id": record_id,
            "source": source,
            "source_url": source_url,
            "title": title,
            "section_path": ["Knowledge"],
            "content": summary,
            "summary": summary,
            "tags": ["privacy", "schema"],
            "retrieved_at": "2026-07-07T00:00:00Z",
            "content_hash": "sha256:test",
            "ttl_seconds": 604800,
            "license_note": "Test fixture.",
            "confidence": confidence,
        }
    )


def test_advisor_uses_local_cache_for_best_practice_question(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_knowledge_records(FIXTURE, source="bubble_manual_gitbook")

    advice = knowledge_advice(task="What is the best practice for API Connector authentication?")

    assert advice["used"] is True
    assert advice["remote_used"] is False
    assert advice["remote_enabled"] is True
    assert "best_practice_question" in advice["triggers"]
    assert advice["decision_effect"] == "answer_support"
    assert advice["guidance"][0]["source_id"] == "bubble_manual_gitbook"
    assert advice["guidance"][0]["trust_level"] == "official"


def test_advisor_respects_remote_opt_out_on_cache_miss(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BUBBLE_MCP_KNOWLEDGE_REMOTE", "0")

    advice = knowledge_advice(task="Delete a privacy rule and remove a field from a data type")

    assert advice["used"] is False
    assert advice["remote_enabled"] is False
    assert advice["reason"] == "local_knowledge_missing"
    assert advice["missing_knowledge_topics"]
    assert advice["suggested_queries"]


def test_advisor_does_not_trigger_for_simple_visual_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    advice = knowledge_advice(task="Apague o elemento notes_input da página mcp-llm")

    assert advice["used"] is False
    assert advice["reason"] == "no_trigger"


def test_advisor_fetches_remote_selectively_and_caches_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("BUBBLE_MCP_KNOWLEDGE_REMOTE", raising=False)

    fetched = [
        _record(
            record_id="bubble-manual:remote:privacy-rules",
            source="bubble_manual",
            title="Privacy rules",
            summary="Official guidance for configuring privacy rules.",
            confidence="official_cached",
        )
    ]

    def fake_fetch_remote_records(*, queries, max_records):  # type: ignore[no-untyped-def]
        assert queries
        assert max_records > 0
        return fetched

    monkeypatch.setattr("bubble_mcp.knowledge.advisor.fetch_remote_records", fake_fetch_remote_records)

    advice = knowledge_advice(task="Create privacy rules for a data type", family="data_schema")
    cached = knowledge_search("privacy rules", limit=5)

    assert advice["used"] is True
    assert advice["remote_used"] is True
    assert advice["guidance"][0]["source_id"] == "bubble_manual"
    assert cached["ok"] is True
    assert cached["results"][0]["id"] == "bubble-manual:remote:privacy-rules"


def test_advisor_uses_forum_records_for_warnings_not_execution_authorization(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    forum_record = _record(
        record_id="bubble-forum:topic:123",
        source="bubble_forum",
        source_url="https://forum.bubble.io/t/example/123",
        title="Field deletion needs derived refresh",
        summary="Community reports that some schema writes may need calculate_derived before the editor reflects changes.",
        confidence="community_observed",
    )

    monkeypatch.setattr(
        "bubble_mcp.knowledge.advisor.fetch_remote_records",
        lambda *, queries, max_records: [forum_record],  # type: ignore[no-untyped-def]
    )

    advice = knowledge_advice(task="Delete a field from a data type", tool_name="delete_data_field")

    assert advice["used"] is True
    assert advice["remote_used"] is True
    assert advice["decision_effect"] in {"recommendation_adjustment", "validation_requirement"}
    assert any("community" in warning.lower() for warning in advice["warnings"])
    assert advice["execute_authorized"] is False


def test_task_runbook_includes_knowledge_advice_when_triggered(monkeypatch) -> None:
    expected = {
        "used": True,
        "remote_used": False,
        "remote_enabled": True,
        "triggers": ["structural_action"],
        "queries": ["Bubble privacy rules"],
        "source_mix": ["official_docs"],
        "confidence": "official_cached",
        "decision_effect": "validation_requirement",
        "guidance": [],
        "warnings": ["Refresh context after this structural write."],
        "recommended_next_steps": ["Run context refresh."],
        "missing_knowledge_topics": [],
        "execute_authorized": False,
    }

    monkeypatch.setattr("bubble_mcp.server.agent_guide.knowledge_advice", lambda **_: expected)

    runbook = task_runbook("Delete a field from testimonial data type", profile="cliente2")

    assert runbook["knowledge_advice"] == expected


def test_task_runbook_omits_unused_knowledge_advice(monkeypatch) -> None:
    expected = {
        "used": False,
        "reason": "no_trigger",
        "remote_enabled": True,
        "triggers": [],
        "suggested_queries": [],
        "missing_knowledge_topics": [],
    }
    monkeypatch.setattr("bubble_mcp.server.agent_guide.knowledge_advice", lambda **_: expected)

    runbook = task_runbook("Create a text element", profile="cliente2")

    assert "knowledge_advice" not in runbook


def test_remote_fetch_dedupes_records_across_queries(monkeypatch) -> None:
    duplicate = _record(
        record_id="bubble-manual:remote:duplicate",
        source="bubble_manual",
        title="Duplicate",
        summary="Duplicate remote record.",
        confidence="official_cached",
    )

    monkeypatch.setattr(
        "bubble_mcp.knowledge.remote.fetch_bubble_manual_records",
        lambda query, *, max_results: [duplicate],  # type: ignore[no-untyped-def]
    )
    monkeypatch.setattr(
        "bubble_mcp.knowledge.remote.fetch_discourse_records",
        lambda query, *, base_url, source_id, max_results: [],  # type: ignore[no-untyped-def]
    )

    records = fetch_remote_records(["privacy rules", "privacy rules"], max_records=8)

    assert [record.id for record in records] == ["bubble-manual:remote:duplicate"]
