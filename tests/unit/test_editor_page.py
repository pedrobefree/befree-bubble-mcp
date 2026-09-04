"""Choosing which editor page a pointer needs open, with the cache replaced by a fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bubble_mcp.execution.editor_page import (
    INDEX_EDITOR_URL_TEMPLATE,
    editor_url,
    editor_url_for_pointer,
    pointer_context,
    resolve_context_name,
)


def test_pointer_context_reads_a_reusable_key_from_an_ed_pointer() -> None:
    assert pointer_context(["%ed", "bTZyj", "%el", "bTaCn"]) == ("reusable", "bTZyj")


def test_pointer_context_accepts_the_decoded_spelling_of_the_reusable_bucket() -> None:
    assert pointer_context(["element_definitions", "bTZyj"]) == ("reusable", "bTZyj")


def test_pointer_context_reads_a_page_key_from_a_p3_pointer() -> None:
    assert pointer_context(["%p3", "bTGbC", "%el", "bTTWc"]) == ("page", "bTGbC")


def test_pointer_context_accepts_the_decoded_spelling_of_the_page_bucket() -> None:
    assert pointer_context(["pages", "bTGbC"]) == ("page", "bTGbC")


@pytest.mark.parametrize(
    "pointer",
    [["api", "bTTlo"], ["styles", "s1"], ["%ed"], ["option_sets", "x"], []],
)
def test_pointer_context_returns_none_for_a_pointer_that_names_no_context(pointer: list[str]) -> None:
    """`api`, `styles` and friends are app-wide: they load with the app on any editor page.

    A bucket name with no key after it (``["%ed"]``) names no single reusable either, so there
    is no page to derive - the caller falls back to the app's default editor page.
    """

    assert pointer_context(pointer) is None


def test_editor_url_defaults_to_the_index_page() -> None:
    url = editor_url("app-1", "test")

    assert url == INDEX_EDITOR_URL_TEMPLATE.format(app_id="app-1", app_version="test")
    assert "name=index" in url


def test_editor_url_for_a_page_names_that_page() -> None:
    url = editor_url("app-1", "test", kind="page", name="dashboard")

    assert "name=dashboard" in url
    assert "type=reusable" not in url


def test_editor_url_for_a_reusable_asks_for_the_reusable_page() -> None:
    url = editor_url("app-1", "test", kind="reusable", name="New Client Form")

    assert "type=reusable" in url
    assert "name=New%20Client%20Form" in url
    assert "id=app-1" in url
    assert "version=test" in url


def test_editor_url_percent_encodes_a_name_with_a_slash_or_ampersand() -> None:
    url = editor_url("app-1", "test", kind="reusable", name="Client & Notes/Form")

    assert "Client%20%26%20Notes%2FForm" in url


def test_editor_url_for_pointer_derives_the_reusable_page_from_the_pointer() -> None:
    url = editor_url_for_pointer(
        ["%ed", "bTZyj", "%el", "bTaCn"],
        profile="p",
        app_id="app-1",
        app_version="test",
        resolver=lambda profile, app_id, kind, key: "New Client Form",
    )

    assert "type=reusable" in url
    assert "name=New%20Client%20Form" in url


def test_editor_url_for_pointer_falls_back_to_index_for_an_app_wide_pointer() -> None:
    url = editor_url_for_pointer(
        ["api", "bTTlo"],
        profile="p",
        app_id="app-1",
        app_version="test",
        resolver=lambda *args: pytest.fail("an app-wide pointer must not need a name lookup"),
    )

    assert url == INDEX_EDITOR_URL_TEMPLATE.format(app_id="app-1", app_version="test")


def test_editor_url_for_pointer_uses_the_key_itself_when_no_name_resolves() -> None:
    """An unresolvable key is still a better guess than `index`, which is certainly wrong.

    Some context payloads key reusables and pages by their name already; and when the cache is
    simply absent, the key at least addresses the right kind of page, so the failure that
    follows names a page that does not exist instead of silently reading the wrong one.
    """

    url = editor_url_for_pointer(
        ["%ed", "bTZyj"],
        profile="p",
        app_id="app-1",
        app_version="test",
        resolver=lambda *args: None,
    )

    assert "type=reusable" in url
    assert "name=bTZyj" in url


def _write_modules_index(root: Path, bucket: str, payload: dict[str, str]) -> None:
    target = root / bucket
    target.mkdir(parents=True, exist_ok=True)
    (target / "__index.json").write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_context_name_reads_the_reusable_name_from_the_module_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tmp_path / "bubble_modules" / "app-1"
    _write_modules_index(modules, "element_definitions", {"bTZyj": "CustomDefinition:New Client Form"})
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_modules_dir",
        lambda profile, app_id: modules,
    )

    assert resolve_context_name("p", "app-1", "reusable", "bTZyj") == "New Client Form"


def test_resolve_context_name_keeps_a_colon_inside_the_name_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The module index stores ``<Type>:<Name>``; only the FIRST colon separates them."""

    modules = tmp_path / "bubble_modules" / "app-1"
    _write_modules_index(modules, "element_definitions", {"bTZyj": "CustomDefinition:Form: Client"})
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_modules_dir",
        lambda profile, app_id: modules,
    )

    assert resolve_context_name("p", "app-1", "reusable", "bTZyj") == "Form: Client"


def test_resolve_context_name_reads_a_page_name_from_the_module_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    modules = tmp_path / "bubble_modules" / "app-1"
    _write_modules_index(modules, "pages", {"bTGbC": "index", "bTVso": "dashboard"})
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_modules_dir",
        lambda profile, app_id: modules,
    )

    assert resolve_context_name("p", "app-1", "page", "bTVso") == "dashboard"


def test_resolve_context_name_falls_back_to_the_bubble_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = tmp_path / "app-1.bubble"
    export.write_text(
        json.dumps({"element_definitions": {"bTZyj": {"id": "bTZyf", "name": "New Client Form"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_modules_dir",
        lambda profile, app_id: tmp_path / "absent",
    )
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_export_path",
        lambda profile, app_id: export,
    )

    assert resolve_context_name("p", "app-1", "reusable", "bTZyj") == "New Client Form"


def test_resolve_context_name_returns_none_when_no_cache_holds_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_modules_dir",
        lambda profile, app_id: tmp_path / "absent",
    )
    monkeypatch.setattr(
        "bubble_mcp.execution.editor_page.default_bubble_export_path",
        lambda profile, app_id: tmp_path / "absent.bubble",
    )

    assert resolve_context_name("p", "app-1", "reusable", "bTZyj") is None
