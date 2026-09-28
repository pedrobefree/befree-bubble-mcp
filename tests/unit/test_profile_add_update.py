"""bubble_profile_add changes only what it is told to, and never drops an argument silently.

On the team server an agent changed a profile's app_version with bubble_profile_add and lost its
context_path: the tool rebuilt the profile from the arguments alone, and did not know
context_path at all.
"""

from __future__ import annotations

import pytest

from bubble_mcp.core.config import load_settings
from bubble_mcp.server.tools import call_tool


@pytest.fixture(autouse=True)
def _config_dir(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))


def _profile(name: str = "kaimia"):  # type: ignore[no-untyped-def]
    return load_settings().profiles[name]


def test_a_new_profile_stores_context_path_and_crawler_index_path() -> None:
    result = call_tool(
        "bubble_profile_add",
        {
            "name": "kaimia",
            "app_id": "kaimia-app",
            "context_path": "/srv/contexts/kaimia.json",
            "crawler_index_path": "/srv/contexts/kaimia-crawler.json",
        },
    )

    assert result["created"] is True
    assert _profile().context_path == "/srv/contexts/kaimia.json"
    assert _profile().crawler_index_path == "/srv/contexts/kaimia-crawler.json"
    assert _profile().app_version == "test"
    assert result["stored"]["context_path"] == "/srv/contexts/kaimia.json"


def test_an_update_keeps_every_field_it_does_not_name() -> None:
    call_tool(
        "bubble_profile_add",
        {
            "name": "kaimia",
            "app_id": "kaimia-app",
            "editor_url": "https://bubble.io/page?id=kaimia-app",
            "context_path": "/srv/contexts/kaimia.json",
            "app_json_path": "/srv/kaimia.bubble",
        },
    )

    result = call_tool("bubble_profile_add", {"name": "kaimia", "app_id": "kaimia-app", "app_version": "93k8b"})

    profile = _profile()
    assert result["created"] is False
    assert result["changed"] == ["app_version"]
    assert profile.app_version == "93k8b"
    assert profile.context_path == "/srv/contexts/kaimia.json"
    assert profile.editor_url == "https://bubble.io/page?id=kaimia-app"
    assert profile.app_json_path == "/srv/kaimia.bubble"


def test_an_empty_value_clears_a_field_on_purpose() -> None:
    call_tool("bubble_profile_add", {"name": "kaimia", "app_id": "kaimia-app", "context_path": "/srv/c.json"})

    result = call_tool("bubble_profile_add", {"name": "kaimia", "app_id": "kaimia-app", "context_path": ""})

    assert result["changed"] == ["context_path"]
    assert _profile().context_path is None


def test_an_argument_the_profile_cannot_store_is_an_error() -> None:
    with pytest.raises(ValueError, match="does not store context_file"):
        call_tool("bubble_profile_add", {"name": "kaimia", "app_id": "kaimia-app", "context_file": "/srv/c.json"})

    assert "kaimia" not in load_settings().profiles


def test_the_schema_offers_the_new_fields() -> None:
    from bubble_mcp.server.schemas import list_tool_schemas

    schema = {tool["name"]: tool for tool in list_tool_schemas()}["bubble_profile_add"]

    assert {"context_path", "crawler_index_path"} <= set(schema["inputSchema"]["properties"])
