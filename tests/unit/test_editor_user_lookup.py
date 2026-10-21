"""An email resolved to a Bubble user id from the editor's Data tab, without a Data API token.

No browser: the page is a fake that serves the Data tab's search answers - plain JSON shaped
like the ones captured on mcp-test-app (2026-09-28) - first unfiltered, then after the email is
typed into the tab's search box.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from bubble_mcp.execution.editor_user_lookup import (
    SEARCH_BOX_PLACEHOLDER,
    find_user_id_in_editor,
    user_ids_by_email,
)


def _answer(*users: tuple[str, str]) -> dict[str, Any]:
    return {
        "hits": {
            "hits": [
                {
                    "_id": user_id,
                    "_type": "user",
                    "_source": {"_id": user_id, "_type": "user", "authentication": {"email": {"email": email}}},
                }
                for user_id, email in users
            ],
            "total": len(users),
        }
    }


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.url = "https://bubble.io/elasticsearch/search"
        self._payload = payload

    def text(self) -> str:
        return json.dumps(self._payload)


class _Box:
    def __init__(self, page: _Page) -> None:
        self.page = page

    def fill(self, value: str) -> None:
        self.page.typed = value

    def press(self, key: str) -> None:
        self.page.emit(self.page.filtered)


class _Page:
    def __init__(self, first: dict[str, Any], filtered: dict[str, Any]) -> None:
        self.first = first
        self.filtered = filtered
        self.handler: Any = None
        self.typed = ""
        self.placeholders: list[str] = []

    def on(self, event: str, handler: Any) -> None:
        self.handler = handler

    def emit(self, payload: dict[str, Any]) -> None:
        self.handler(_Response(payload))

    def reload(self, **kwargs: Any) -> None:
        self.emit(self.first)

    def get_by_placeholder(self, text: str) -> _Box:
        self.placeholders.append(text)
        return _Box(self)


def _opener(page: _Page, seen: dict[str, Any]):  # type: ignore[no-untyped-def]
    @contextlib.contextmanager
    def open_page(**kwargs: Any):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        yield page

    return open_page


def _clock():  # type: ignore[no-untyped-def]
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    return sleep, (lambda: now[0])


def test_a_user_on_the_first_page_is_found_without_searching() -> None:
    page = _Page(_answer(("1788x1", "test@test.com")), _answer())
    seen: dict[str, Any] = {}
    sleep, monotonic = _clock()

    result = find_user_id_in_editor(
        "mcp-test", "mcp-test-app", "TEST@test.com", open_page=_opener(page, seen), sleep=sleep, monotonic=monotonic
    )

    assert result == {"ok": True, "user_id": "1788x1", "email": "TEST@test.com", "source": "editor_data_tab"}
    assert page.placeholders == []
    assert "tab=Data" in seen["url"] and "type_id=user" in seen["url"]


def test_a_user_past_the_first_page_is_found_through_the_search_box() -> None:
    page = _Page(_answer(("1788x1", "someone@else.com")), _answer(("1788x9", "late@example.com")))
    sleep, monotonic = _clock()

    result = find_user_id_in_editor(
        "p", "app", "late@example.com", open_page=_opener(page, {}), sleep=sleep, monotonic=monotonic
    )

    assert result["user_id"] == "1788x9"
    assert page.placeholders == [SEARCH_BOX_PLACEHOLDER]
    assert page.typed == "late@example.com"


def test_an_email_nobody_has_is_user_not_found() -> None:
    page = _Page(_answer(), _answer())
    sleep, monotonic = _clock()

    result = find_user_id_in_editor("p", "app", "x@y.z", open_page=_opener(page, {}), sleep=sleep, monotonic=monotonic)

    assert result["error"] == "user_not_found"


def test_live_is_refused_because_the_tab_reads_the_development_database() -> None:
    result = find_user_id_in_editor("p", "app", "x@y.z", app_version="live", open_page=lambda **kwargs: None)

    assert result["error"] == "live_lookup_unsupported"


def test_only_user_hits_count() -> None:
    other = {"hits": {"hits": [{"_id": "1", "_source": {"_id": "1", "_type": "custom.client", "email": "a@b.c"}}]}}

    assert user_ids_by_email([other, _answer(("2", "A@B.c"))]) == {"a@b.c": "2"}
