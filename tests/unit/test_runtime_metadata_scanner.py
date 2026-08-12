import json
from pathlib import Path

from bubble_mcp.aria_runtime import metadata_scanner


def test_scan_metadata_builds_option_and_custom_type_map(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / "metadata.json"
    monkeypatch.setattr(metadata_scanner, "METADATA_FILE", str(output))

    assert metadata_scanner.scan_metadata(
        {
            "option_sets": {
                "status": {"display": "OS: Status"},
                "ignored": "invalid",
            },
            "user_types": {
                "user": {"display": "User"},
                "invoice": {"%d": "Invoice"},
                "fallback": {},
                "ignored": "invalid",
            },
        }
    ) is True

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "OS: Status": "option.status",
        "Status": "option.status",
        "User": "user",
        "Invoice": "custom.invoice",
        "fallback": "custom.fallback",
    }
    assert "5 entries" in capsys.readouterr().out


def test_scan_metadata_reads_configured_app_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "app.bubble"
    source.write_text('{"user_types":{"item":{"display":"Item"}}}', encoding="utf-8")
    output = tmp_path / "metadata.json"
    monkeypatch.setattr(metadata_scanner, "APP_FILE", str(source))
    monkeypatch.setattr(metadata_scanner, "METADATA_FILE", str(output))

    assert metadata_scanner.scan_metadata() is True
    assert json.loads(output.read_text(encoding="utf-8")) == {"Item": "custom.item"}


def test_scan_metadata_reports_missing_invalid_and_unwritable_inputs(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    missing = tmp_path / "missing.bubble"
    monkeypatch.setattr(metadata_scanner, "APP_FILE", str(missing))
    assert metadata_scanner.scan_metadata() is False
    assert "not found" in capsys.readouterr().out

    invalid = tmp_path / "invalid.bubble"
    invalid.write_text("{", encoding="utf-8")
    monkeypatch.setattr(metadata_scanner, "APP_FILE", str(invalid))
    assert metadata_scanner.scan_metadata() is False
    assert "Error reading" in capsys.readouterr().out

    output_directory = tmp_path / "output"
    output_directory.mkdir()
    monkeypatch.setattr(metadata_scanner, "METADATA_FILE", str(output_directory))
    assert metadata_scanner.scan_metadata([]) is False
    assert "Error scanning metadata" in capsys.readouterr().out
