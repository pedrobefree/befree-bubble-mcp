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
