import os

from scripts import package_smoke


def test_package_smoke_subprocess_environment_excludes_source_path(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("PYTHONPATH", "src")
    monkeypatch.setenv("PYTHONHOME", "/tmp/python-home")
    monkeypatch.setenv("PACKAGE_SMOKE_SENTINEL", "preserved")

    env = package_smoke._subprocess_env()

    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert env["PACKAGE_SMOKE_SENTINEL"] == "preserved"
    assert os.environ["PYTHONPATH"] == "src"


def test_package_smoke_checks_catalog_quality_from_installed_wheel() -> None:
    assert "catalog_quality_report" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
    assert "catalog_ambiguity_report" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
    assert "cli_leaf_map_report" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
    assert "catalog_schema_precision_report" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
    assert "schema_precision_ok" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
    assert "schema_precision_tool_count" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
    assert "leaf_count" in package_smoke.INSTALLED_CATALOG_QUALITY_CHECK
