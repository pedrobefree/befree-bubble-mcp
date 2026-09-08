"""Run as, exercised without touching Bubble.

The flow is two GETs whose interesting content is entirely in headers, so a fake transport
that answers with a Location and a cookie jar reproduces every branch: the happy path, an
expired editor session, preview password protection, and a redirect that succeeds but
impersonates nobody.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.execution import run_as as run_as_module
from bubble_mcp.execution.run_as import (
    CookieRecord,
    HttpReply,
    build_storage_state,
    run_as_user,
)


APP_ID = "mcp-test-app"
USER_ID = "1700000000000x000000000000000001"
TOKEN = "1700000000000x000000000000000002"
REDIRECT = (
    f"https://{APP_ID}.bubbleapps.io/version-test/api/1.1/u/redirect"
    f"?access_token={TOKEN}&debug_mode=true&page=index"
)


@dataclass
class FakeTransport:
    replies: list[HttpReply]
    jar: list[CookieRecord] = field(default_factory=list)
    calls: list[tuple[str, dict[str, str], bool]] = field(default_factory=list)

    def get(self, url: str, headers: dict[str, str], *, follow_redirects: bool) -> HttpReply:
        self.calls.append((url, dict(headers), follow_redirects))
        return self.replies[len(self.calls) - 1]

    @property
    def cookies(self) -> list[CookieRecord]:
        return list(self.jar)


@dataclass
class FakeSession:
    app_id: str = APP_ID
    headers: dict[str, str] | None = None
    cookies: str = "editor-cookie"

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {"user-agent": "chrome", "cookie": "stale-should-be-replaced"}


def _session_cookies() -> list[CookieRecord]:
    return [
        CookieRecord(
            name=f"{APP_ID}_test_u2main",
            value="a" * 69,
            domain=f"{APP_ID}.bubbleapps.io",
            expires=1788638317.0,
        ),
        CookieRecord(
            name=f"{APP_ID}_test_u2main.sig",
            value="b" * 27,
            domain=f"{APP_ID}.bubbleapps.io",
        ),
    ]


@pytest.fixture
def stored_session(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    session = FakeSession()
    monkeypatch.setattr(run_as_module, "load_session", lambda profile: session)
    return session


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(run_as_module, "get_config_dir", lambda: tmp_path)
    # Point the export lookup at the sandbox too. Without this the tests read whatever .bubble
    # export happens to be cached on the developer's machine, so a run's outcome would depend
    # on which apps that person happens to have refreshed.
    monkeypatch.setattr(
        run_as_module,
        "default_bubble_export_path",
        lambda profile, app_id: tmp_path / "exports" / f"{profile}-{app_id}.bubble",
    )
    return tmp_path


def _write_export(config_dir: Path, profile: str, app_id: str, secure: dict[str, Any]) -> None:
    path = config_dir / "exports" / f"{profile}-{app_id}.bubble"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"settings": {"secure": secure}}), encoding="utf-8")


def test_happy_path_returns_landing_url_and_writes_storage_state(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(
        replies=[
            HttpReply(status=302, location=REDIRECT),
            HttpReply(status=200, final_url=f"https://{APP_ID}.bubbleapps.io/version-test/index"),
        ],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport, preview_username="u", preview_password="p")

    assert result["ok"] is True
    assert result["user_id"] == USER_ID
    assert result["landing_url"].endswith("/version-test/index")

    state = json.loads(Path(result["storage_state_path"]).read_text(encoding="utf-8"))
    assert [cookie["name"] for cookie in state["cookies"]] == [
        f"{APP_ID}_test_u2main",
        f"{APP_ID}_test_u2main.sig",
    ]


def test_cookie_values_never_appear_in_the_result(
    stored_session: FakeSession, config_dir: Path
) -> None:
    # The result is logged and shown to the user; the storage-state file is the only place a
    # live session cookie is allowed to exist.
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    serialized = json.dumps(result)
    assert "a" * 69 not in serialized
    assert "b" * 27 not in serialized
    assert result["cookies"][0]["value_length"] == 69


def test_first_call_must_not_follow_redirects(stored_session: FakeSession, config_dir: Path) -> None:
    # The token only exists in the 302's Location; following it here would consume the redirect
    # without the app-domain headers and lose the token.
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    run_as_user("mcp-test", USER_ID, transport=transport)

    assert transport.calls[0][2] is False
    assert transport.calls[1][2] is True


def test_editor_session_cookie_replaces_any_stale_header(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    run_as_user("mcp-test", USER_ID, transport=transport)

    assert transport.calls[0][1]["cookie"] == "editor-cookie"


def test_missing_session_says_which_tool_fixes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_as_module, "load_session", lambda profile: None)

    result = run_as_user("mcp-test", USER_ID, transport=FakeTransport(replies=[]))

    assert result["ok"] is False
    assert result["error"] == "not_logged_in"
    assert "bubble_session_login" in result["message"]


def test_redirect_without_token_is_reported_as_such(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(replies=[HttpReply(status=200, location="")])

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["ok"] is False
    assert result["error"] == "no_access_token"


def test_success_without_an_app_cookie_is_a_failure(
    stored_session: FakeSession, config_dir: Path
) -> None:
    # A 200 that sets nothing means the next page load is anonymous - reporting ok here would
    # send the caller off to write tests against a logged-out app.
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)], jar=[]
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["ok"] is False
    assert result["error"] == "no_session_cookie"


def test_cookies_from_other_domains_are_not_treated_as_the_session(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=[CookieRecord(name="_ga", value="x", domain=".google-analytics.com")],
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["ok"] is False
    assert result["error"] == "no_session_cookie"


def test_cookies_on_a_custom_domain_are_still_the_session(
    stored_session: FakeSession, config_dir: Path
) -> None:
    # An app with redirect_all_to_domain sends the Run as redirect on to its own domain, and
    # Bubble sets the session there. Nothing in that hostname mentions the app id - the cookie
    # NAME is what carries it - so matching on the domain alone loses a working session.
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=[
            CookieRecord(
                name=f"{APP_ID}_test_u2main", value="live", domain=".app.example.org.au"
            ),
            CookieRecord(
                name=f"{APP_ID}_test_u2main.sig", value="sig", domain=".app.example.org.au"
            ),
        ],
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["ok"] is True
    assert [cookie["domain"] for cookie in result["cookies"]] == [
        ".app.example.org.au",
        ".app.example.org.au",
    ]


def test_storage_state_shape_matches_what_playwright_accepts() -> None:
    state = build_storage_state(_session_cookies())

    assert set(state) == {"cookies", "origins"}
    first = state["cookies"][0]
    assert set(first) == {"name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite"}
    # Playwright wants -1 for a session cookie, not None.
    assert state["cookies"][1]["expires"] == -1


def test_storage_state_can_be_skipped(stored_session: FakeSession, config_dir: Path) -> None:
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport, write_storage_state=False)

    assert result["ok"] is True
    assert "storage_state_path" not in result
    assert not list(config_dir.glob("run-as/*.json"))


def test_preview_credentials_are_sent_as_basic_auth(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    run_as_user("mcp-test", USER_ID, transport=transport, preview_username="ana", preview_password="s3cr3t")

    # base64("ana:s3cr3t")
    assert transport.calls[1][1]["authorization"] == "Basic YW5hOnMzY3IzdA=="


def test_preview_credentials_fall_back_to_the_environment(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BUBBLE_PREVIEW_USER", "ana")
    monkeypatch.setenv("BUBBLE_PREVIEW_PW", "s3cr3t")
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    run_as_user("mcp-test", USER_ID, transport=transport)

    assert transport.calls[1][1]["authorization"] == "Basic YW5hOnMzY3IzdA=="


def test_no_credentials_sends_no_authorization_header(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BUBBLE_PREVIEW_USER", raising=False)
    monkeypatch.delenv("BUBBLE_PREVIEW_PW", raising=False)
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    run_as_user("mcp-test", USER_ID, transport=transport)

    assert "authorization" not in transport.calls[1][1]


def test_app_id_argument_overrides_the_profile(
    stored_session: FakeSession, config_dir: Path
) -> None:
    other = "other-app"
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=[CookieRecord(name=f"{other}_test_u2main", value="z", domain=f"{other}.bubbleapps.io")],
    )

    result = run_as_user("mcp-test", USER_ID, app_id=other, transport=transport)

    assert result["ok"] is True
    assert result["app_id"] == other
    assert f"/appeditor/authenticate_as/{other}/test/" in transport.calls[0][0]


def test_page_and_version_reach_the_authenticate_url(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    run_as_user("mcp-test", USER_ID, page="checkout", app_version="staging", transport=transport)

    assert transport.calls[0][0].endswith(f"/{APP_ID}/staging/{USER_ID}/true/checkout")


def test_storage_state_path_is_outside_the_repository(config_dir: Path) -> None:
    path = run_as_module.storage_state_path("mcp-test", APP_ID, USER_ID)

    assert path.is_relative_to(config_dir)
    assert path.name.endswith(".json")


def test_a_401_with_no_credentials_retries_with_the_bubble_defaults(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Agency-plan apps ship with preview password protection on and seeded with this pair, and
    # owners routinely leave it. Failing here would send the caller hunting for a credential
    # that is published in Bubble's own defaults.
    monkeypatch.delenv("BUBBLE_PREVIEW_USER", raising=False)
    monkeypatch.delenv("BUBBLE_PREVIEW_PW", raising=False)
    transport = FakeTransport(
        replies=[
            HttpReply(status=302, location=REDIRECT),
            HttpReply(status=401),
            HttpReply(status=200),
        ],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["ok"] is True
    assert result["used_default_preview_credentials"] is True
    # base64("username:password")
    assert transport.calls[2][1]["authorization"] == "Basic dXNlcm5hbWU6cGFzc3dvcmQ="


def test_supplied_credentials_are_never_replaced_by_the_defaults(
    stored_session: FakeSession, config_dir: Path
) -> None:
    # A 401 despite real credentials means those credentials are wrong. Retrying with the
    # defaults could succeed and hide that the caller's own pair is broken.
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=401)],
        jar=_session_cookies(),
    )

    result = run_as_user(
        "mcp-test", USER_ID, transport=transport, preview_username="ana", preview_password="wrong"
    )

    assert result["ok"] is False
    assert result["error"] == "preview_password_required"
    assert len(transport.calls) == 2
    assert "credentials supplied were rejected" in result["message"]


def test_defaults_rejected_says_so_and_points_at_the_owner(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BUBBLE_PREVIEW_USER", raising=False)
    monkeypatch.delenv("BUBBLE_PREVIEW_PW", raising=False)
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=401), HttpReply(status=401)]
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["ok"] is False
    assert result["error"] == "preview_password_required"
    assert "default pair (username/password) was tried and rejected" in result["message"]
    assert "agency plan" in result["message"]
    # The caller has to know which knobs exist, not just that something was refused.
    assert "BUBBLE_PREVIEW_USER" in result["message"]
    assert "BUBBLE_PREVIEW_PW" in result["message"]


def test_a_working_app_does_not_report_default_credentials(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport, preview_username="ana", preview_password="p")

    assert result["used_default_preview_credentials"] is False


def test_preview_credentials_come_from_the_app_export_when_the_environment_is_empty(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bubble keeps the preview pair at settings.secure.username/password, and the profile
    # already downloads that export - so the pair is discoverable rather than something a human
    # has to be asked for, and it stays right for an owner who changed it.
    monkeypatch.delenv("BUBBLE_PREVIEW_USER", raising=False)
    monkeypatch.delenv("BUBBLE_PREVIEW_PW", raising=False)
    _write_export(config_dir, "mcp-test", APP_ID, {"username": "ana", "password": "s3cr3t"})
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["preview_credential_source"] == "app_export"
    assert transport.calls[1][1]["authorization"] == "Basic YW5hOnMzY3IzdA=="


def test_the_environment_beats_the_app_export(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stale export must not override what the operator set deliberately.
    monkeypatch.setenv("BUBBLE_PREVIEW_USER", "ana")
    monkeypatch.setenv("BUBBLE_PREVIEW_PW", "s3cr3t")
    _write_export(config_dir, "mcp-test", APP_ID, {"username": "old", "password": "old"})
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["preview_credential_source"] == "environment"
    assert transport.calls[1][1]["authorization"] == "Basic YW5hOnMzY3IzdA=="


def test_an_export_without_the_pair_is_not_a_source(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BUBBLE_PREVIEW_USER", raising=False)
    monkeypatch.delenv("BUBBLE_PREVIEW_PW", raising=False)
    _write_export(config_dir, "mcp-test", APP_ID, {"use_algolia_integration": False})
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", USER_ID, transport=transport)

    assert result["preview_credential_source"] == "none"
    assert "authorization" not in transport.calls[1][1]


def test_neither_user_id_nor_email_is_refused_before_any_request(
    stored_session: FakeSession, config_dir: Path
) -> None:
    transport = FakeTransport(replies=[])

    result = run_as_user("mcp-test", transport=transport)

    assert result["ok"] is False
    assert result["error"] == "missing_user"
    assert transport.calls == []


def test_an_email_with_no_bubble_cli_project_says_what_to_pass_instead(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BUBBLE_CLI_PROJECT_DIR", raising=False)
    monkeypatch.delenv("BUBBLE_CLI_ROOT", raising=False)
    transport = FakeTransport(replies=[])

    result = run_as_user("mcp-test", email="a@b.com", transport=transport)

    assert result["ok"] is False
    assert result["error"] == "no_data_api_config"
    assert "bubble.json" in result["message"]
    assert transport.calls == []


def test_a_resolved_email_impersonates_the_id_it_found(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The lookup and the impersonation are separate concerns; this is the seam between them.
    monkeypatch.setattr(
        run_as_module,
        "_user_id_from_email",
        lambda email, app_id, folder, version: {"ok": True, "user_id": USER_ID},
    )
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user("mcp-test", email="a@b.com", transport=transport)

    assert result["ok"] is True
    assert result["user_id"] == USER_ID
    assert f"/true/index" in transport.calls[0][0]
    assert USER_ID in transport.calls[0][0]


def test_a_failed_email_lookup_is_returned_untouched(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The lookup's own message explains which of three settings is missing; wrapping it in a
    # generic impersonation error would throw that away.
    failure = {"ok": False, "error": "user_not_found", "message": "no such row"}
    monkeypatch.setattr(run_as_module, "_user_id_from_email", lambda *a: failure)
    transport = FakeTransport(replies=[])

    assert run_as_user("mcp-test", email="a@b.com", transport=transport) is failure
    assert transport.calls == []


def _project(config_dir: Path, version: str) -> Path:
    folder = config_dir / "cli-project"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bubble.json").write_text(
        json.dumps({"app_id": APP_ID, "api_key": "k" * 32, "version": version}), encoding="utf-8"
    )
    return folder


def test_a_live_config_refuses_to_resolve_an_email_for_a_test_impersonation(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bubble keeps test and live data in separate databases, so an id found in live simply does
    # not exist in test. Left unchecked this surfaces much later as authenticate_as answering
    # without a token, which reads as "no such user" and sends the caller hunting the wrong bug.
    monkeypatch.delenv("BUBBLE_DATA_API_TOKEN", raising=False)
    folder = _project(config_dir, "live")
    transport = FakeTransport(replies=[])

    result = run_as_user(
        "mcp-test", email="a@b.com", app_version="test", data_api_dir=str(folder), transport=transport
    )

    assert result["ok"] is False
    assert result["error"] == "data_api_version_mismatch"
    assert "SEPARATE databases" in result["message"]
    # Refused before any request: nothing was looked up and nothing was impersonated.
    assert transport.calls == []


def test_a_test_config_refuses_a_live_impersonation(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BUBBLE_DATA_API_TOKEN", raising=False)
    folder = _project(config_dir, "test")

    result = run_as_user(
        "mcp-test",
        email="a@b.com",
        app_version="live",
        data_api_dir=str(folder),
        transport=FakeTransport(replies=[]),
    )

    assert result["error"] == "data_api_version_mismatch"


def test_matching_versions_are_allowed_through(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BUBBLE_DATA_API_TOKEN", raising=False)
    folder = _project(config_dir, "live")
    seen: list[str] = []
    def fake_lookup(email: str, app_id: str, folder_arg: str | None, version: str) -> dict[str, Any]:
        seen.append(version)
        return {"ok": True, "user_id": USER_ID}

    monkeypatch.setattr(run_as_module, "_user_id_from_email", fake_lookup)
    transport = FakeTransport(
        replies=[HttpReply(status=302, location=REDIRECT), HttpReply(status=200)],
        jar=_session_cookies(),
    )

    result = run_as_user(
        "mcp-test", email="a@b.com", app_version="live", data_api_dir=str(folder), transport=transport
    )

    assert result["ok"] is True
    assert seen == ["live"]


def test_any_branch_counts_as_the_test_side(
    stored_session: FakeSession, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # bubble-cli maps anything that is not "live" onto version-test, and a feature branch shares
    # that database, so a non-live config must not be refused for a branch.
    monkeypatch.delenv("BUBBLE_DATA_API_TOKEN", raising=False)
    assert run_as_module._versions_disagree("feature-checkout", "test") is False
    assert run_as_module._versions_disagree("live", "live") is False
    assert run_as_module._versions_disagree("test", "live") is True
