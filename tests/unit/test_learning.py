import pytest

from bubble_mcp.learning.store import append_learning_record, list_learning_records


def test_learning_records_are_scoped_and_append_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    append_learning_record(
        scope="project",
        key="naming.page_language",
        value={"language": "pt-BR"},
        source="user_declared",
        confidence="confirmed",
        project="client-app",
    )
    append_learning_record(
        scope="global",
        key="workflow.preview_required",
        value={"enabled": True},
        source="user_declared",
        confidence="confirmed",
    )

    project_records = list_learning_records(scope="project", project="client-app")
    all_records = list_learning_records()

    assert len(project_records) == 1
    assert project_records[0].key == "naming.page_language"
    assert len(all_records) == 2


@pytest.mark.parametrize(
    ("scope", "message"),
    [
        ("profile", "Learning record scope 'profile' requires profile."),
        ("project", "Learning record scope 'project' requires project."),
        ("extension", "Learning record scope 'extension' requires extension_id."),
    ],
)
def test_learning_records_require_scope_discriminators(
    tmp_path,
    monkeypatch,
    scope: str,
    message: str,
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    with pytest.raises(ValueError, match=message):
        append_learning_record(
            scope=scope,
            key="naming.page_language",
            value={"language": "pt-BR"},
            source="user_declared",
            confidence="confirmed",
        )

    assert list_learning_records() == []


def test_learning_records_raise_clear_error_for_malformed_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    records_path = tmp_path / "learning" / "records.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"Malformed learning record JSONL at .*records\.jsonl:2"):
        list_learning_records()
