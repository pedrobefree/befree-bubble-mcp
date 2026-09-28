"""An inline flow runs on each version and comes back side by side.

No browser: the run-as call, the per-version case runner and the video composer are injected,
so what is checked here is the flow's own job - validating steps, one impersonated session per
version kept apart, one run per version, and the comparison built from whatever each produced.
The step callable is exercised against a fake page separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubble_mcp.e2e.flow import FlowError, flow_case, run_e2e_flow, validate_steps

STEPS = [
    {"goto": "login_page"},
    {"click": "Fazer login"},
    {"fill": "Email", "value": "a@b.c"},
    {"expect_text": "Entrar"},
    {"screenshot": "open"},
]


@pytest.fixture(autouse=True)
def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "bubble_mcp.e2e.target._domain_from_export",
        lambda profile, app_id: ("https://mcp-test-app.bubbleapps.io", "bubbleapps", ()),
    )
    from bubble_mcp.server.tools import call_tool

    call_tool("bubble_profile_add", {"name": "mcp-test", "app_id": "mcp-test-app"})


@pytest.mark.parametrize(
    ("steps", "fragment"),
    [
        ([], "non-empty"),
        ([{"click": "A", "goto": "b"}], "exactly one action"),
        ([{"hover": "A"}], "exactly one action"),
        ([{"fill": "Email"}], "needs 'value'"),
        ([{"wait": "soon"}], "milliseconds"),
        ([{"click": ""}], "needs a target"),
    ],
)
def test_malformed_steps_are_refused_before_a_browser(steps: Any, fragment: str) -> None:
    with pytest.raises(FlowError, match=fragment):
        validate_steps(steps)


def test_preview_resolves_every_version_without_running_anything() -> None:
    def must_not_run(**kwargs: Any) -> Any:
        raise AssertionError("a preview must not run the flow")

    result = run_e2e_flow(
        profile="mcp-test", steps=STEPS, versions=["test", "63kqi"], email="a@b.c", run_case=must_not_run
    )

    assert result["ok"] is True and result["mode"] == "preview"
    assert result["targets"]["63kqi"]["base_url"] == "https://mcp-test-app.bubbleapps.io/version-63kqi"
    assert result["targets"]["test"]["base_url"] == "https://mcp-test-app.bubbleapps.io/version-test"


def test_live_is_refused() -> None:
    result = run_e2e_flow(profile="mcp-test", steps=STEPS, versions=["live"], email="a@b.c")

    assert result["ok"] is False
    assert "production" in result["error"]


def test_a_user_is_required() -> None:
    result = run_e2e_flow(profile="mcp-test", steps=STEPS, versions=["test"])

    assert "user_id or email" in result["error"]


def _fake_run_as(config_dir: Path, calls: list[tuple[str, str]]):  # type: ignore[no-untyped-def]
    from bubble_mcp.execution.run_as import storage_state_path

    def run_as(profile: str, user_id: str, *, email: str | None, app_id: str, app_version: str) -> dict[str, Any]:
        calls.append((email or user_id, app_version))
        path = storage_state_path(profile, app_id, "u1")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cookies": [{"name": f"{app_version}_u2main", "value": "x"}], "origins": []}))
        return {"ok": True, "user_id": "u1", "storage_state_path": str(path)}

    return run_as


def test_execute_runs_each_version_with_its_own_session_and_compares(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    runs: list[dict[str, Any]] = []

    def run_case(**kwargs: Any) -> dict[str, Any]:
        runs.append(kwargs)
        cookie = json.loads(Path(kwargs["session"].path).read_text())["cookies"][0]["name"]
        video = Path(kwargs["artifact_dir"]) / "video.webm"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"webm")
        return {
            "ok": True,
            "status": "passed",
            "ran_with": cookie,
            "steps": [{"name": "01-goto", "status": "passed"}],
            "artifacts": {"video": str(video)},
        }

    composed: list[Any] = []

    def compose(videos: Any, output: Path) -> str:
        composed.append([version for version, _ in videos])
        return str(output)

    result = run_e2e_flow(
        profile="mcp-test",
        steps=STEPS,
        versions=["test", "63kqi"],
        email="a@b.c",
        execute=True,
        run_as=_fake_run_as(tmp_path, calls),
        run_case=run_case,
        compose_video=compose,
    )

    assert result["ok"] is True
    assert calls == [("a@b.c", "test"), ("a@b.c", "63kqi")]
    # Each version ran with ITS session, not the one the next run_as overwrote.
    assert result["results"]["test"]["ran_with"] == "test_u2main"
    assert result["results"]["63kqi"]["ran_with"] == "63kqi_u2main"
    assert [run["target"].branch for run in runs] == ["test", "63kqi"]
    assert all(callable(run["case_callable"]) for run in runs)
    assert composed == [["test", "63kqi"]]
    page = Path(result["comparison"]["html"]).read_text(encoding="utf-8")
    assert "Play both" in page and "63kqi" in page and "video.webm" in page
    assert Path(result["artifacts_dir"], "flow-result.json").exists()


def test_a_version_whose_user_cannot_be_impersonated_is_reported_and_the_others_still_run(tmp_path: Path) -> None:
    def run_as(profile: str, user_id: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs["app_version"] == "63kqi":
            return {"ok": False, "error": "user_not_found", "message": "no such user"}
        return _fake_run_as(tmp_path, [])(profile, user_id, **kwargs)

    result = run_e2e_flow(
        profile="mcp-test",
        steps=STEPS,
        versions=["test", "63kqi"],
        email="a@b.c",
        execute=True,
        run_as=run_as,
        run_case=lambda **kwargs: {"ok": True, "status": "passed", "steps": [], "artifacts": {}},
        compose_video=lambda videos, output: None,
    )

    assert result["ok"] is False
    assert result["results"]["test"]["ok"] is True
    assert "no such user" in result["results"]["63kqi"]["message"]


class _Locator:
    def __init__(self, log: list[str], label: str) -> None:
        self.log = log
        self.label = label
        self.first = self

    def count(self) -> int:
        return 1

    def wait_for(self, **kwargs: Any) -> None:
        self.log.append(f"wait {self.label}")


class _Page:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def locator(self, value: str) -> _Locator:
        return _Locator(self.log, f"selector {value}")

    def get_by_text(self, value: str, exact: bool = False) -> _Locator:
        return _Locator(self.log, f"text {value}")

    def get_by_placeholder(self, value: str) -> _Locator:
        return _Locator(self.log, f"placeholder {value}")

    def wait_for_load_state(self, *args: Any, **kwargs: Any) -> None:
        pass


class _Ctx:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.page = _Page(self.log)
        self.options = type("O", (), {"default_timeout_ms": 1000})()
        self.names: list[str] = []

    def step(self, name: str):  # type: ignore[no-untyped-def]
        import contextlib

        self.names.append(name)
        return contextlib.nullcontext()

    def goto(self, path: str) -> None:
        self.log.append(f"goto {path}")

    def mark_ready(self) -> None:
        self.log.append("ready")

    def click(self, target: _Locator) -> None:
        self.log.append(f"click {target.label}")

    def fill(self, target: _Locator, text: str) -> None:
        self.log.append(f"fill {target.label}={text}")

    def expect(self, target: _Locator) -> Any:
        log = self.log

        class Expect:
            def to_be_visible(self, **kwargs: Any) -> None:
                log.append(f"visible {target.label}")

        return Expect()

    def shot(self, name: str) -> None:
        self.log.append(f"shot {name}")


def test_the_steps_drive_the_context_in_order() -> None:
    ctx = _Ctx()

    flow_case(validate_steps([*STEPS[:4], {"click": "#save"}, STEPS[4]]))(ctx)  # type: ignore[arg-type]

    assert ctx.log == [
        "goto login_page",
        "ready",
        "wait text Fazer login",
        "click text Fazer login",
        "fill placeholder Email=a@b.c",
        "visible text Entrar",
        "wait selector #save",
        "click selector #save",
        "shot open",
    ]
    assert len(ctx.names) == 6


def test_the_tool_is_exposed_and_previews_by_default() -> None:
    from bubble_mcp.server.agent_catalog import tool_annotations
    from bubble_mcp.server.schemas import list_tool_schemas
    from bubble_mcp.server.tools import call_tool

    schema = {tool["name"]: tool for tool in list_tool_schemas()}["bubble_e2e_flow"]
    assert schema["inputSchema"]["required"] == ["profile", "steps", "versions"]
    assert schema["inputSchema"]["properties"]["execute"]["default"] is False
    assert tool_annotations("bubble_e2e_flow")["readOnlyHint"] is False

    result = call_tool(
        "bubble_e2e_flow",
        {"profile": "mcp-test", "steps": STEPS, "versions": ["test", "63kqi"], "email": "a@b.c"},
    )
    assert result["mode"] == "preview"


def test_tool_search_finds_it_for_before_after_evidence() -> None:
    from bubble_mcp.server.agent_guide import search_tool_catalog

    for query in ("before after video evidence of a change on two versions", "run a quick browser flow click and check"):
        names = [match["name"] for match in search_tool_catalog(query, limit=5)["matches"]]
        assert "bubble_e2e_flow" in names, (query, names)
