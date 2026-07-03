from pathlib import Path

from scripts.install_local import _stale_install_paths


def test_stale_install_paths_detects_interrupted_editable_metadata(tmp_path: Path) -> None:
    editable = tmp_path / "__editable__.befree_bubble_mcp-0.1.0.pth"
    duplicate_editable = tmp_path / "__editable__.befree_bubble_mcp-0.1.0 2.pth"
    dist_info = tmp_path / "befree_bubble_mcp-0.1.0.dist-info"
    duplicate_package = tmp_path / "bubble_mcp 2"
    unrelated = tmp_path / "bubble_mcp"

    editable.write_text("src\n", encoding="utf-8")
    duplicate_editable.write_text("src\n", encoding="utf-8")
    dist_info.mkdir()
    duplicate_package.mkdir()
    unrelated.mkdir()

    stale_paths = {path.name for path in _stale_install_paths(tmp_path)}

    assert stale_paths == {
        "__editable__.befree_bubble_mcp-0.1.0.pth",
        "__editable__.befree_bubble_mcp-0.1.0 2.pth",
        "befree_bubble_mcp-0.1.0.dist-info",
        "bubble_mcp 2",
    }
