from pathlib import Path

from bubble_mcp.core.config import (
    BubbleMcpSettings,
    BubbleProfile,
    load_settings,
    resolve_profile,
    save_settings,
    with_profile,
)


def test_save_load_and_resolve_profile(tmp_path: Path) -> None:
    settings = BubbleMcpSettings(config_dir=tmp_path, default_profile=None, profiles={})
    updated = with_profile(
        settings,
        BubbleProfile(name="cli-test", app_id="sample-app", appname="sample-app", app_version="test"),
    )

    save_settings(updated)
    loaded = load_settings(tmp_path)

    assert loaded.default_profile == "cli-test"
    assert resolve_profile(loaded, "cli_test") is not None
    assert resolve_profile(loaded, "cli_test").app_id == "sample-app"  # type: ignore[union-attr]
    assert resolve_profile(loaded, "cli_test").app_version == "test"  # type: ignore[union-attr]
