"""The email-to-user_id lookup, without touching a Bubble app.

Everything here is either filesystem (finding the right bubble.json) or one HTTP GET whose
body is JSON, so a fake fetch covers every branch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.execution.data_api import (
    DataApiConfig,
    DataApiError,
    find_data_api_config,
    find_user_id,
)


APP_ID = "mcp-test-app"
USER_ID = "1700000000000x000000000000000001"


def _config(**overrides: Any) -> DataApiConfig:
    base = {"app_id": APP_ID, "api_key": "k" * 32, "version": "test"}
    base.update(overrides)
    return DataApiConfig(**base)  # type: ignore[arg-type]


def _write_project(folder: Path, app_id: str, *, version: str = "live") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "bubble.json"
    path.write_text(
        json.dumps({"app_id": app_id, "api_key": "k" * 32, "version": version, "db_path": "x.sqlite"}),
        encoding="utf-8",
    )
    return path


def _replies(payload: Any) -> tuple[Any, list[tuple[str, dict[str, str]]]]:
    calls: list[tuple[str, dict[str, str]]] = []

    def fetch(url: str, headers: dict[str, str]) -> str:
        calls.append((url, dict(headers)))
        if isinstance(payload, Exception):
            raise payload
        return json.dumps(payload)

    return fetch, calls


def test_live_version_has_no_version_segment() -> None:
    # Same rule bubble-cli uses. Two tools disagreeing about which version they read would be a
    # miserable bug to chase.
    assert _config(version="live").base_url == f"https://{APP_ID}.bubbleapps.io/api/1.1"


def test_any_other_version_reads_version_test() -> None:
    assert _config(version="test").base_url == f"https://{APP_ID}.bubbleapps.io/version-test/api/1.1"


def test_describe_never_carries_the_api_key() -> None:
    described = json.dumps(_config().describe())

    assert "k" * 32 not in described
    assert "api_key" not in described


def test_config_is_matched_by_app_id_not_by_being_found_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A machine with several mirrored apps would otherwise answer about the wrong one, and the
    # lookup would succeed while being about somebody else's data.
    _write_project(tmp_path / "aaa-other", "other-app")
    wanted = _write_project(tmp_path / "zzz-target", APP_ID)
    monkeypatch.setenv("BUBBLE_CLI_ROOT", str(tmp_path))

    found = find_data_api_config(APP_ID)

    assert found is not None
    assert found.source_path == wanted


def test_a_folder_argument_is_checked_directly(tmp_path: Path) -> None:
    _write_project(tmp_path, APP_ID)

    found = find_data_api_config(APP_ID, folder=tmp_path)

    assert found is not None and found.app_id == APP_ID


def test_a_project_without_a_key_is_not_a_config(tmp_path: Path) -> None:
    (tmp_path / "bubble.json").write_text(json.dumps({"app_id": APP_ID}), encoding="utf-8")

    assert find_data_api_config(APP_ID, folder=tmp_path) is None


def test_no_matching_project_returns_none(tmp_path: Path) -> None:
    _write_project(tmp_path, "some-other-app")

    assert find_data_api_config(APP_ID, folder=tmp_path) is None


def test_lookup_returns_the_bubble_unique_id() -> None:
    fetch, calls = _replies({"response": {"results": [{"_id": USER_ID, "email": "a@b.com"}]}})

    result = find_user_id(_config(), "a@b.com", fetch=fetch)

    assert result == {"ok": True, "user_id": USER_ID, "app_id": APP_ID, "version": "test"}
    url, headers = calls[0]
    assert headers["authorization"] == "Bearer " + "k" * 32
    assert "/obj/user?" in url


def test_the_email_constraint_is_sent_as_bubble_expects() -> None:
    fetch, calls = _replies({"response": {"results": [{"_id": USER_ID}]}})

    find_user_id(_config(), "a@b.com", fetch=fetch)

    from urllib.parse import parse_qs, urlparse

    raw = parse_qs(urlparse(calls[0][0]).query)["constraints"][0]
    assert json.loads(raw) == [{"key": "email", "constraint_type": "equals", "value": "a@b.com"}]


def test_an_empty_result_is_not_reported_as_a_missing_user_alone() -> None:
    # Privacy rules hide rows from a token, and a hidden row looks exactly like an absent one.
    # Saying so is what keeps someone from concluding the account was deleted.
    fetch, _ = _replies({"response": {"results": []}})

    result = find_user_id(_config(), "a@b.com", fetch=fetch)

    assert result["ok"] is False
    assert result["error"] == "user_not_found"
    assert "privacy rules" in result["message"]


def test_two_rows_with_one_email_refuse_to_guess() -> None:
    fetch, _ = _replies({"response": {"results": [{"_id": "a"}, {"_id": "b"}]}})

    result = find_user_id(_config(), "a@b.com", fetch=fetch)

    assert result["ok"] is False
    assert result["error"] == "ambiguous_email"


def test_a_transport_failure_names_the_three_things_that_cause_it() -> None:
    fetch, _ = _replies(DataApiError("Data API answered 401: unauthorized"))

    result = find_user_id(_config(), "a@b.com", fetch=fetch)

    assert result["ok"] is False
    assert result["error"] == "data_api_failed"
    assert "api-data-enabled" in result["message"]
    assert "set_data_type_api_exposure" in result["message"]


def test_a_row_without_an_id_is_a_failure_not_an_empty_id() -> None:
    fetch, _ = _replies({"response": {"results": [{"email": "a@b.com"}]}})

    result = find_user_id(_config(), "a@b.com", fetch=fetch)

    assert result["ok"] is False
    assert result["error"] == "no_id_in_row"


def test_an_empty_email_is_refused_before_any_request() -> None:
    fetch, calls = _replies({"response": {"results": []}})

    result = find_user_id(_config(), "   ", fetch=fetch)

    assert result["error"] == "missing_email"
    assert calls == []


def test_a_non_json_body_is_reported_as_such() -> None:
    def fetch(url: str, headers: dict[str, str]) -> str:
        return "<html>gateway</html>"

    result = find_user_id(_config(), "a@b.com", fetch=fetch)

    assert result["ok"] is False
    assert result["error"] == "data_api_failed"


def test_an_environment_token_needs_no_bubble_cli_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This server is distributed on its own. Requiring another tool to be installed before an
    # email can be resolved would make the feature unreachable for anyone who does not use it.
    monkeypatch.setenv("BUBBLE_DATA_API_TOKEN", "t" * 32)
    monkeypatch.delenv("BUBBLE_DATA_API_APP", raising=False)
    monkeypatch.delenv("BUBBLE_CLI_PROJECT_DIR", raising=False)
    monkeypatch.delenv("BUBBLE_CLI_ROOT", raising=False)

    found = find_data_api_config(APP_ID)

    assert found is not None
    assert found.api_key == "t" * 32
    assert found.source_path is None


def test_the_environment_token_wins_over_a_project_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_project(tmp_path, APP_ID)
    monkeypatch.setenv("BUBBLE_DATA_API_TOKEN", "t" * 32)

    found = find_data_api_config(APP_ID, folder=tmp_path)

    assert found is not None and found.source_path is None


def test_a_token_scoped_to_another_app_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sending one app's token to another app's endpoint would leak it to a third party.
    monkeypatch.setenv("BUBBLE_DATA_API_TOKEN", "t" * 32)
    monkeypatch.setenv("BUBBLE_DATA_API_APP", "some-other-app")
    monkeypatch.delenv("BUBBLE_CLI_PROJECT_DIR", raising=False)
    monkeypatch.delenv("BUBBLE_CLI_ROOT", raising=False)

    assert find_data_api_config(APP_ID) is None
