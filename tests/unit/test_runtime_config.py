import json
import os
from pathlib import Path

from bubble_mcp.aria_runtime.config import (
    _normalize_profile_name,
    load_env_file,
    load_settings_file,
    resolve_profile,
)


def test_normalize_profile_name_is_separator_tolerant() -> None:
    assert _normalize_profile_name(None) == ""
    assert _normalize_profile_name(" CLI_Test profile ") == "clitestprofile"


def test_load_env_file_is_optional_and_non_destructive(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    load_env_file(str(tmp_path / "missing.env"))
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nINVALID\nEXISTING=replaced\nQUOTED=\"value\"\nSINGLE='other'\n =ignored\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "preserved")

    load_env_file(str(env_file))

    assert os.environ["EXISTING"] == "preserved"
    assert os.environ["QUOTED"] == "value"
    assert os.environ["SINGLE"] == "other"


def test_load_env_file_ignores_read_errors(tmp_path: Path) -> None:
    directory = tmp_path / "directory.env"
    directory.mkdir()
    load_env_file(str(directory))


def test_load_settings_merges_profile_fragments(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"default_profile": "base", "profiles": {"base": {"app_id": "base"}}}),
        encoding="utf-8",
    )
    profiles_dir = tmp_path / "profiles.d"
    profiles_dir.mkdir()
    (profiles_dir / "wrapped.json").write_text(
        json.dumps({"profiles": {"wrapped": {"app_id": "wrapped"}}}),
        encoding="utf-8",
    )
    (profiles_dir / "direct.json").write_text(
        json.dumps({"direct": {"app_id": "direct"}}),
        encoding="utf-8",
    )
    (profiles_dir / "invalid.json").write_text("{", encoding="utf-8")
    (profiles_dir / "ignored.txt").write_text("{}", encoding="utf-8")

    settings = load_settings_file(str(settings_path))

    assert set(settings["profiles"]) == {"base", "wrapped", "direct"}


def test_load_settings_handles_missing_and_invalid_files(tmp_path: Path) -> None:
    assert load_settings_file(str(tmp_path / "missing.json")) == {}
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert load_settings_file(str(invalid)) == {}


def test_load_settings_rejects_non_object_root_before_merging_fragments(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("[]", encoding="utf-8")
    profiles_dir = tmp_path / "profiles.d"
    profiles_dir.mkdir()
    (profiles_dir / "profile.json").write_text(
        json.dumps({"local": {"app_id": "local"}}),
        encoding="utf-8",
    )

    assert load_settings_file(str(settings_path)) == {
        "profiles": {"local": {"app_id": "local"}}
    }


def test_resolve_profile_uses_explicit_env_default_and_tolerant_names(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = {
        "default_profile": "default",
        "profiles": {
            "explicit": {"app_id": "explicit"},
            "from-env": {"app_id": "env"},
            "default": {"app_id": "default"},
            "cli_test": {"app_id": "tolerant"},
        },
    }

    assert resolve_profile(settings, "explicit")["app_id"] == "explicit"
    monkeypatch.setenv("BUBBLE_CLI_PROFILE", "from-env")
    assert resolve_profile(settings, None)["app_id"] == "env"
    monkeypatch.delenv("BUBBLE_CLI_PROFILE")
    assert resolve_profile(settings, None)["app_id"] == "default"
    assert resolve_profile(settings, "cli-test") == {"name": "cli_test", "app_id": "tolerant"}


def test_resolve_profile_rejects_ambiguous_or_non_object_profiles() -> None:
    settings = {
        "profiles": {
            "same-name": {"app_id": "one"},
            "same_name": {"app_id": "two"},
            "invalid": "not-an-object",
        }
    }

    assert resolve_profile(settings, "same name") == {"name": None}
    assert resolve_profile(settings, "invalid") == {"name": None}
    assert resolve_profile({"profiles": []}, "missing") == {"name": None}
