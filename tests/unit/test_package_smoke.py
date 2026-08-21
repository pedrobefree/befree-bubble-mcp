import os

import pytest

import bubble_mcp.catalog_schema_precision as precision_module
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


@pytest.mark.parametrize(
    ("tool_count", "failure_count"),
    [(27, 0), (28, 1)],
)
def test_package_smoke_rejects_non_exact_installed_precision_report(
    monkeypatch: pytest.MonkeyPatch,
    tool_count: int,
    failure_count: int,
) -> None:
    monkeypatch.setattr(
        precision_module,
        "catalog_schema_precision_report",
        lambda: {
            "ok": True,
            "summary": {
                "tool_count": tool_count,
                "failure_count": failure_count,
            },
        },
    )

    with pytest.raises(AssertionError):
        exec(package_smoke.INSTALLED_CATALOG_QUALITY_CHECK, {})
