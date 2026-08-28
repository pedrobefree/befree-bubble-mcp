from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from bubble_mcp.execution.plugins import install_plugin, resolve_plugin_install_values

MARKETPLACE_ENTRY = {
    "display": "Free Toggle",
    "last_version": "4.2.0",
    "license": "open_source",
    "price": None,
}
NATIVE_ENTRY = {"display": "API Connector", "official": True}


def test_a_marketplace_plugin_installs_under_its_latest_version() -> None:
    resolved = resolve_plugin_install_values(MARKETPLACE_ENTRY, plugin_key="1660311476391x288865870778204160")

    assert resolved["plugin_value"] == "4.2.0"
    assert resolved["include_installed_version"] is False


def test_a_plugin_without_a_version_installs_as_true() -> None:
    resolved = resolve_plugin_install_values(NATIVE_ENTRY, plugin_key="apiconnector2")

    assert resolved["plugin_value"] is True
    assert resolved["include_installed_version"] is True


def test_a_plugin_missing_from_the_catalogue_is_refused() -> None:
    with pytest.raises(ValueError, match="catalogue"):
        resolve_plugin_install_values(None, plugin_key="nope")


@pytest.mark.parametrize(
    ("field", "value"),
    [("price", 12), ("blocked", True), ("deleted", True)],
)
def test_a_plugin_that_cannot_be_installed_is_refused_before_any_write(field: str, value: Any) -> None:
    entry = {**MARKETPLACE_ENTRY, field: value}

    with pytest.raises(ValueError):
        resolve_plugin_install_values(entry, plugin_key="1660311476391x288865870778204160")


def test_a_deprecated_latest_version_is_refused() -> None:
    entry = {**MARKETPLACE_ENTRY, "deprecated_versions": ["4.2.0"]}

    with pytest.raises(ValueError, match="deprecated"):
        resolve_plugin_install_values(entry, plugin_key="1660311476391x288865870778204160")


class _FakeClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def write(self, payload: dict[str, Any], session: Any, *, dry_run: bool = False) -> dict[str, Any]:
        self.payloads.append(payload)
        return {"ok": True, "dry_run": dry_run}


def _session() -> Any:
    return SimpleNamespace(app_id="mcp-test-app", app_version="test")


def _install(plugin_key: str, entry: dict[str, Any] | None, **kwargs: Any) -> tuple[dict[str, Any], _FakeClient]:
    client = _FakeClient()
    result = install_plugin(
        profile="mcp-test",
        session=_session(),
        plugin_key=plugin_key,
        client=client,
        catalogue_lookup=lambda key: entry,
        post_check_conflicts=False,
        calculate_derived=False,
        notify_ai_context_change=False,
        **kwargs,
    )
    return result, client


def test_install_resolves_the_version_from_the_catalogue_by_default() -> None:
    result, client = _install("1660311476391x288865870778204160", MARKETPLACE_ENTRY)

    assert result["plugin_value"] == "4.2.0"
    paths = [change["path_array"] for change in client.payloads[0]["changes"]]
    assert paths == [["settings", "client_safe", "plugins", "1660311476391x288865870778204160"]]


def test_an_explicit_plugin_value_is_not_overridden_by_the_catalogue() -> None:
    result, client = _install("1660311476391x288865870778204160", MARKETPLACE_ENTRY, plugin_value="3.0.0")

    assert result["plugin_value"] == "3.0.0"
    assert client.payloads[0]["changes"][0]["body"] == "3.0.0"


def test_install_refuses_a_paid_plugin_without_writing() -> None:
    with pytest.raises(ValueError):
        _install("1660311476391x288865870778204160", {**MARKETPLACE_ENTRY, "price": 25})
