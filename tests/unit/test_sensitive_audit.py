from pathlib import Path

from scripts.audit_sensitive_paths import audit_path


def test_sensitive_audit_flags_project_graph(tmp_path: Path) -> None:
    public_file = tmp_path / "fixture.json"
    public_file.write_text('{"source": "befree-page-project-graph"}', encoding="utf-8")

    findings = audit_path(tmp_path)

    assert findings


def test_sensitive_audit_allows_safe_file(tmp_path: Path) -> None:
    public_file = tmp_path / "fixture.json"
    public_file.write_text('{"source": "synthetic-app"}', encoding="utf-8")

    findings = audit_path(tmp_path)

    assert findings == []


def test_sensitive_audit_skips_tmp_directory(tmp_path: Path) -> None:
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    local_file = tmp_dir / "implementation-control.md"
    local_file.write_text("mutation-overlay local note", encoding="utf-8")

    findings = audit_path(tmp_path)

    assert findings == []
