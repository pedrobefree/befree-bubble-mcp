import json
import os
import re
from typing import Any, Dict, Optional


def _normalize_profile_name(value: Optional[str]) -> str:
    """Normalize profile identifiers for tolerant matching (cli-test == cli_test)."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


def load_env_file(path: str) -> None:
    """Load simple KEY=VALUE pairs into environment if file exists."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"").strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Silent failure: env files are optional
        return


def load_settings_file(path: str) -> Dict[str, Any]:
    """Load settings.json if present, and merge profiles.d/*.json if available."""
    settings: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            settings = {}

    # Merge profiles.d/*.json (non-destructive)
    base_dir = os.path.dirname(path) or "."
    profiles_dir = os.path.join(base_dir, "profiles.d")
    if os.path.isdir(profiles_dir):
        for filename in os.listdir(profiles_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(profiles_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            # Accept either {"profiles": {...}} or direct {"name": {...}} object
            profiles = data.get("profiles") if isinstance(data, dict) else None
            if isinstance(profiles, dict):
                settings.setdefault("profiles", {}).update(profiles)
            elif isinstance(data, dict):
                settings.setdefault("profiles", {}).update(data)

    return settings


def resolve_profile(settings: Dict[str, Any], profile: Optional[str]) -> Dict[str, Any]:
    """Resolve profile configuration from settings.json and env fallback."""
    profiles = settings.get("profiles") if isinstance(settings, dict) else None
    if not isinstance(profiles, dict):
        profiles = {}

    name = profile or os.getenv("BUBBLE_CLI_PROFILE") or settings.get("default_profile")
    if name:
        if name in profiles:
            cfg = profiles.get(name, {})
            if isinstance(cfg, dict):
                return {"name": name, **cfg}

        # Tolerant match: treat separators as equivalent (cli-test == cli_test)
        normalized_target = _normalize_profile_name(name)
        if normalized_target:
            matching_keys = [
                key for key in profiles.keys()
                if _normalize_profile_name(key) == normalized_target
            ]
            if len(matching_keys) == 1:
                resolved_name = matching_keys[0]
                cfg = profiles.get(resolved_name, {})
                if isinstance(cfg, dict):
                    return {"name": resolved_name, **cfg}

    return {"name": None}
