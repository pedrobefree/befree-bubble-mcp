import json

from bubble_mcp.frameworks import (
    framework_status,
    generate_framework_artifacts,
    list_frameworks,
    sync_framework_evidence,
)


def test_list_frameworks_returns_supported_adapters() -> None:
    result = list_frameworks()

    assert result["ok"] is True
    frameworks = {item["id"]: item for item in result["frameworks"]}
    assert set(frameworks) == {"bmad", "sdd", "superpowers"}
    assert "prd.md" in frameworks["bmad"]["artifacts"]
    assert "implementation-plan.md" in frameworks["superpowers"]["artifacts"]
    assert "acceptance-tests.md" in frameworks["sdd"]["artifacts"]


def test_generate_framework_artifacts_for_each_supported_framework(tmp_path) -> None:
    expected = {
        "bmad": "prd.md",
        "superpowers": "implementation-plan.md",
        "sdd": "specification.md",
    }

    for framework, required_file in expected.items():
        result = generate_framework_artifacts(
            framework=framework,
            profile="cliente2",
            objective="Build checkout",
            scope="page checkout",
            context_summary={"pages": 3, "api_keys": "sk-secret-value"},
            output_dir=tmp_path,
        )

        assert result["ok"] is True
        assert result["framework"] == framework
        artifact_dir = tmp_path / framework / "cliente2"
        assert artifact_dir.exists()
        generated_dir = next(path for path in artifact_dir.iterdir() if path.is_dir())
        assert (generated_dir / required_file).exists()
        assert (generated_dir / "framework.json").exists()
        metadata = json.loads((generated_dir / "framework.json").read_text(encoding="utf-8"))
        assert metadata["context_summary"]["api_keys"] == "[REDACTED]"
        assert "preview-first MCP tools" in metadata["execution_policy"]


def test_sync_framework_evidence_redacts_sensitive_values_and_status_counts(tmp_path) -> None:
    generated = generate_framework_artifacts(
        framework="bmad",
        profile="Cliente 2",
        objective="Review security",
        output_dir=tmp_path,
    )
    artifact_dir = generated["artifact_dir"]

    synced = sync_framework_evidence(
        framework="bmad",
        profile="Cliente 2",
        artifact_dir=tmp_path / "bmad" / "cliente-2" / artifact_dir.rsplit("/", 1)[-1],
        evidence={
            "summary": "Preview passed",
            "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
            "nested": {"password": "secret"},
        },
    )

    assert synced["ok"] is True
    evidence_path = tmp_path / "bmad" / "cliente-2" / artifact_dir.rsplit("/", 1)[-1] / "evidence.jsonl"
    record = json.loads(evidence_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["evidence"]["authorization"] == "[REDACTED]"
    assert record["evidence"]["nested"]["password"] == "[REDACTED]"

    status = framework_status(framework="bmad", profile="Cliente 2", output_dir=tmp_path)
    assert status["ok"] is True
    assert status["status"][0]["artifact_count"] == 1
    assert status["status"][0]["evidence_count"] == 1
