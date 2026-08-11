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


def test_sensitive_audit_allows_runtime_cookie_expression(tmp_path: Path) -> None:
    public_file = tmp_path / "client.py"
    public_file.write_text('cookie = str(session.cookies or "")', encoding="utf-8")

    assert audit_path(tmp_path) == []


def test_sensitive_audit_allows_obvious_bearer_placeholder(tmp_path: Path) -> None:
    public_file = tmp_path / "fixture.py"
    public_file.write_text('header = "Bearer abcdefghijklmnopqrstuvwxyz"', encoding="utf-8")

    assert audit_path(tmp_path) == []


def test_sensitive_audit_flags_literal_credential(tmp_path: Path) -> None:
    public_file = tmp_path / "config.py"
    public_file.write_text('access_token = "live_opaque_value_12345"', encoding="utf-8")

    assert audit_path(tmp_path)


def test_sensitive_audit_checks_past_placeholder_values(tmp_path: Path) -> None:
    public_file = tmp_path / "config.py"
    public_file.write_text(
        'access_token = "synthetic-token"\naccess_token = "live_opaque_value_12345"',
        encoding="utf-8",
    )

    assert audit_path(tmp_path)


def test_sensitive_audit_flags_sensitive_artifact_filename(tmp_path: Path) -> None:
    artifact = tmp_path / "sample-mutation-overlay.json"
    artifact.write_text("{}", encoding="utf-8")

    assert audit_path(tmp_path)
