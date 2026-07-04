import json
import shutil
from pathlib import Path

import pytest

from bubble_mcp.extensions.models import ExtensionManifest
from bubble_mcp.extensions.store import (
    disable_extension,
    enable_extension,
    export_extension,
    get_installed_extension,
    import_extension,
    list_extensions,
    load_extension_manifest,
)


FIXTURE_DIR = Path("tests/fixtures/extensions/simple-pack")


def test_import_extension_copies_pack_to_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    report = import_extension(FIXTURE_DIR)

    assert report.ok is True
    assert report.extension_id == "local.simple-pack"
    assert (tmp_path / "extensions" / "packs" / "local.simple-pack" / "extension.json").exists()
    assert report.state == "pending"


def test_enable_disable_extension_updates_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(FIXTURE_DIR)

    enabled = enable_extension("local.simple-pack")
    disabled = disable_extension("local.simple-pack")

    assert enabled.state == "enabled"
    assert disabled.state == "disabled"
    assert [item.extension_id for item in list_extensions()] == ["local.simple-pack"]
    assert list_extensions()[0].state == "disabled"


def test_export_extension_writes_archive_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(FIXTURE_DIR)
    output = tmp_path / "exported-pack.json"

    result = export_extension("local.simple-pack", output)

    assert result.ok is True
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["manifest"]["id"] == "local.simple-pack"
    assert "tools/create-plugin-widget.tool.json" in payload["files"]


def test_load_extension_manifest_parses_expected_fields() -> None:
    manifest = load_extension_manifest(FIXTURE_DIR / "extension.json")

    assert manifest.id == "local.simple-pack"
    assert manifest.capabilities == ["tools", "recipes", "skills", "evals"]
    assert manifest.exports.tools == ["tools/create-plugin-widget.tool.json"]


def test_import_extension_rejects_traversal_manifest_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    source = tmp_path / "malicious-pack"
    shutil.copytree(FIXTURE_DIR, source)
    payload = json.loads((source / "extension.json").read_text(encoding="utf-8"))
    payload["id"] = "../../../outside"
    (source / "extension.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="safe path segment"):
        import_extension(source)

    assert not (tmp_path / "config" / "extensions" / "packs").exists()


def test_extension_operations_reject_traversal_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    import_extension(FIXTURE_DIR)

    with pytest.raises(ValueError, match="safe path segment"):
        enable_extension("../local.simple-pack")


def test_import_extension_rejects_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    source = tmp_path / "symlink-pack"
    shutil.copytree(FIXTURE_DIR, source)
    external_file = tmp_path / "external.tool.json"
    external_file.write_text("{}", encoding="utf-8")
    (source / "tools" / "external.tool.json").symlink_to(external_file)

    with pytest.raises(ValueError, match="symlink"):
        import_extension(source)


def test_import_extension_rejects_manifest_symlink_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    source = tmp_path / "manifest-symlink-pack"
    shutil.copytree(FIXTURE_DIR, source)
    external_manifest = tmp_path / "external-extension.json"
    external_manifest.write_text("not-json", encoding="utf-8")
    (source / "extension.json").unlink()
    (source / "extension.json").symlink_to(external_manifest)

    with pytest.raises(ValueError, match="symlink"):
        import_extension(source)

    assert not (tmp_path / "config" / "extensions" / "packs").exists()


def test_export_extension_rejects_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    import_extension(FIXTURE_DIR)
    external_file = tmp_path / "external.tool.json"
    external_file.write_text("{}", encoding="utf-8")
    installed_link = (
        tmp_path
        / "config"
        / "extensions"
        / "packs"
        / "local.simple-pack"
        / "tools"
        / "external.tool.json"
    )
    installed_link.symlink_to(external_file)

    with pytest.raises(ValueError, match="symlink"):
        export_extension("local.simple-pack", tmp_path / "exported-pack.json")


def test_installed_manifest_symlink_is_rejected_by_all_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path / "config"))
    import_extension(FIXTURE_DIR)
    installed_manifest = (
        tmp_path / "config" / "extensions" / "packs" / "local.simple-pack" / "extension.json"
    )
    external_manifest = tmp_path / "external-extension.json"
    external_manifest.write_text((FIXTURE_DIR / "extension.json").read_text(encoding="utf-8"))
    installed_manifest.unlink()
    installed_manifest.symlink_to(external_manifest)

    operations = [
        lambda: list_extensions(),
        lambda: get_installed_extension("local.simple-pack"),
        lambda: enable_extension("local.simple-pack"),
        lambda: disable_extension("local.simple-pack"),
        lambda: export_extension("local.simple-pack", tmp_path / "exported-pack.json"),
    ]

    for operation in operations:
        with pytest.raises(ValueError, match="symlink"):
            operation()


def test_manifest_ignores_non_list_capabilities_and_non_dict_exports() -> None:
    manifest = ExtensionManifest.from_dict(
        {
            "id": "local.simple-pack",
            "capabilities": "tools",
            "exports": "tools/create-plugin-widget.tool.json",
        }
    )

    assert manifest.capabilities == []
    assert manifest.exports.tools == []
