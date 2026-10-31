from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import pytest

from bubble_mcp.context.export_rebuild import (
    build_rebuilt_export,
    canonical,
    merge_section,
    rebuild_export,
    validate_rebuilt,
)
from bubble_mcp.execution.live_section_read import (
    EditorSetupFailed,
    build_section_ready_script,
    build_section_script,
    read_editor_snapshot,
)


def _reusable(name: str, **extra: Any) -> dict[str, Any]:
    return {"id": name, "type": "CustomDefinition", "name": name, "properties": {}, **extra}


def _export() -> dict[str, Any]:
    """A tiny export with the three measured faults: shrunk, stub and stale reusables."""

    return {
        "_index": {
            "id_to_path": {
                "rA": "%ed.rA",
                "rB": "%ed.rB",
                "rC": "%ed.rC",
                "pg": "%p3.pg",
            },
            "page_name_to_id": {"index": "pg"},
        },
        "element_definitions": {
            # Hydrated from the path API: shrunk keys, plus an exported long key colliding.
            "rA": {"%x": "CustomDefinition", "%nm": "header", "id": "rA", "%p": {}, "type": "CustomDefinition"},
            # Export stub: only workflows.
            "rB": {"workflows": {"w1": {"type": "ButtonClicked"}}},
            # Stale: the editor has another width.
            "rC": _reusable("card", properties={"width": 100}),
        },
        "api": {
            "a1": {"type": "APIEvent", "properties": {"wf_name": "ping"}},
            # Staging fault: API workflow without wf_name/parameters.
            "a2": {"type": "APIEvent", "properties": {}},
        },
        "pages": {"pg": {"type": "Page", "name": "index", "id": "pg"}},
        "user_types": {"user": {"display": "User", "fields": {}}},
        "styles": {},
        "option_sets": {},
        "settings": {"client_safe": {"x": 1}},
    }


def _snapshot() -> dict[str, Any]:
    return {
        "sections": {
            "element_definitions": {
                "rA": {"type": "CustomDefinition", "name": "header", "id": "rA", "properties": {}},
                "rB": _reusable("footer", workflows={"w1": {"type": "ButtonClicked"}}),
                "rC": _reusable("card", properties={"width": 240}),
                # Things the editor returns that must never be added:
                "gone": None,
                "frag1": {"elements": {"x": {}}},
                "frag2": {"properties": {}},
                "length": 3,
            },
            "api": {
                "a1": {"type": "APIEvent", "properties": {"wf_name": "ping"}},
                "a2": {"type": "APIEvent", "properties": {"wf_name": "sync", "parameters": []}},
            },
            "user_types": {"user": {"display": "User", "fields": {}}},
            "styles": {},
            "option_sets": {},
            "settings": {"client_safe": {"x": 1}},
            "_index": {"page_name_to_id": {"index": "pg"}},
        },
        # The editor spells some absent keys as null; the export never writes null.
        "pages": {"pg": {"type": "Page", "name": "index", "id": "pg", "is_mobile_view": None}},
        "refetched_reusables": [],
        "errors": {},
    }


def test_merge_section_counts_and_never_adds_fragments() -> None:
    merged, report = merge_section(
        "element_definitions",
        {"keep": _reusable("keep"), "stale": _reusable("s", x=1), "lost": _reusable("lost")},
        {
            "keep": _reusable("keep"),
            "stale": _reusable("s", x=2),
            "new": _reusable("new"),
            "lost": None,
            "frag": {"elements": {}},
            "length": 3,
        },
    )

    assert merged["stale"]["x"] == 2
    assert merged["new"] == _reusable("new")
    assert merged["lost"] == _reusable("lost")
    assert "frag" not in merged and "length" not in merged
    assert report["same"] == 1
    assert report["different"] == 1
    assert report["replaced"] == [{"id": "stale", "name": "s"}]
    assert report["editor_only"] == 1
    assert report["added"] == [{"id": "new", "name": "new"}]
    assert report["editor_incomplete_ids"] == ["lost"]
    assert report["editor_ignored"] == 2


def test_merge_section_keeps_export_only_entries_and_reports_them() -> None:
    merged, report = merge_section("api", {"a": {"type": "APIEvent"}}, {})

    assert merged == {"a": {"type": "APIEvent"}}
    assert report["export_only"] == 1
    assert report["export_only_ids"] == ["a"]


def test_null_valued_keys_do_not_count_as_a_difference() -> None:
    assert canonical({"a": 1, "b": None, "c": {"d": None}}) == canonical({"a": 1, "c": {}})
    _, report = merge_section("pages", {"p": {"type": "Page"}}, {"p": {"type": "Page", "is_mobile_view": None}})
    assert report["same"] == 1 and report["different"] == 0


def test_build_rebuilt_export_decodes_completes_and_validates() -> None:
    data, report = build_rebuilt_export(_export(), _snapshot())

    reusables = data["element_definitions"]
    assert set(reusables) == {"rA", "rB", "rC"}
    assert reusables["rA"] == {"type": "CustomDefinition", "name": "header", "id": "rA", "properties": {}}
    assert reusables["rB"]["name"] == "footer"
    assert reusables["rC"]["properties"] == {"width": 240}
    assert data["api"]["a2"]["properties"] == {"wf_name": "sync", "parameters": []}
    assert "is_mobile_view" not in data["pages"]["pg"]

    assert report["decode"]["collisions"] == 1
    assert report["decode"]["decoded_keys"] == 3
    sections = report["sections"]
    assert sections["element_definitions"]["same"] == 1
    assert {item["id"] for item in sections["element_definitions"]["replaced"]} == {"rB", "rC"}
    assert sections["element_definitions"]["editor_ignored"] == 4
    assert sections["api"]["replaced"] == [{"id": "a2", "name": "sync"}]
    assert sections["pages"]["same"] == 1
    assert report["validation"]["ok"] is True
    assert report["counts"]["element_definitions"] == 3


def test_validation_flags_undecoded_nameless_and_typeless_reusables() -> None:
    validation = validate_rebuilt(
        {
            "element_definitions": {
                "ok": _reusable("ok"),
                "pct": {**_reusable("pct"), "%el": {}},
                "noname": {"type": "CustomDefinition"},
                "notype": {"name": "x"},
            }
        }
    )

    assert validation["ok"] is False
    assert validation["percent_key_paths"] == [["pct", "%el"]]
    assert validation["missing_name"] == ["noname"]
    assert validation["missing_type"] == ["notype"]


def _write_export(tmp_path: Path) -> Path:
    path = tmp_path / "source.bubble"
    path.write_text(json.dumps(_export()), encoding="utf-8")
    return path


def _run(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    calls: dict[str, Any] = {}
    snapshot = overrides.pop("snapshot", None) or _snapshot()

    def read_snapshot(**kwargs: Any) -> dict[str, Any]:
        calls.update(kwargs)
        return snapshot

    def download(*_: Any) -> dict[str, Any]:
        raise AssertionError("a bubble_file run must not download")

    arguments: dict[str, Any] = {
        "profile": "p",
        "app_id": "app",
        "bubble_file": _write_export(tmp_path),
        "work_dir": tmp_path / "rebuild",
        "download": download,
        "read_snapshot": read_snapshot,
        **overrides,
    }
    result = rebuild_export(**arguments)
    result["_calls"] = calls
    return result


def test_preview_reports_without_writing(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result["ok"] is True
    assert result["executed"] is False
    assert not Path(result["output"]).exists()
    assert result["_calls"]["page_ids"] == ["pg"]
    assert result["_calls"]["reusable_ids"] == ["rA", "rB", "rC"]
    assert "execute=true" in result["next_user_action"]


def test_execute_writes_a_new_file_that_reads_back(tmp_path: Path) -> None:
    output = tmp_path / "out" / "rebuilt.bubble"
    result = _run(tmp_path, execute=True, output=output)

    assert result["ok"] is True
    assert result["executed"] is True
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["element_definitions"]["rB"]["name"] == "footer"
    assert result["write"]["validation"]["ok"] is True
    assert not output.with_name(output.name + ".partial").exists()


def test_refuses_to_overwrite_the_source_cache_or_an_existing_file(tmp_path: Path) -> None:
    source = _write_export(tmp_path)
    assert _run(tmp_path, execute=True, output=source)["error"] == "output_would_overwrite_source"

    cache = tmp_path / "cache.bubble"
    refused = _run(tmp_path, execute=True, output=cache, protected_paths=[cache])
    assert refused["error"] == "output_would_overwrite_source"

    existing = tmp_path / "exists.bubble"
    existing.write_text("{}", encoding="utf-8")
    assert _run(tmp_path, execute=True, output=existing)["error"] == "output_exists"


def test_editor_read_failure_blocks_the_write(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot["errors"] = {"styles": "PointerNotReady: never loaded"}
    output = tmp_path / "rebuilt.bubble"

    result = _run(tmp_path, execute=True, output=output, snapshot=snapshot)

    assert result["ok"] is False
    assert result["error"] == "editor_read_incomplete"
    assert not output.exists()


def test_setup_failure_and_unknown_sections_are_reported(tmp_path: Path) -> None:
    failed = _run(tmp_path, snapshot={"setup_error": "not_logged_in", "message": "log in"})
    assert failed["error"] == "not_logged_in"

    assert _run(tmp_path, sections=["pages", "nope"])["error"] == "unknown_sections"


def test_download_path_is_used_when_no_bubble_file(tmp_path: Path) -> None:
    downloaded: list[Path] = []

    def download(profile: str, app_id: str, app_version: str, target: Path) -> dict[str, Any]:
        assert (profile, app_id, app_version) == ("p", "app", "test")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(_export()), encoding="utf-8")
        downloaded.append(target)
        return {"ok": True}

    result = rebuild_export(
        profile="p",
        app_id="app",
        work_dir=tmp_path,
        download=download,
        read_snapshot=lambda **_: _snapshot(),
    )

    assert result["ok"] is True
    assert result["export"] == {"source": "download", "path": str(downloaded[0]), "ok": True}


def _fake_reader(tree: dict[str, Any], *, failing: Sequence[str] = ()) -> Any:
    seen: list[list[str]] = []

    def reader(path: Sequence[str]) -> Any:
        seen.append(list(path))
        if ".".join(path) in failing:
            raise RuntimeError("boom")
        node: Any = tree
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        return node

    reader.seen = seen  # type: ignore[attr-defined]
    return reader


def test_read_editor_snapshot_refetches_lazy_reusables_and_finds_pages() -> None:
    tree = {
        "api": {"a": {"type": "APIEvent"}},
        "element_definitions": {"r1": None, "r2": {"type": "CustomDefinition"}},
        "_index": {"page_name_to_id": {"index": "p1", "extra": "p2"}},
        "pages": {"p1": {"type": "Page"}, "p2": {"type": "Page"}},
    }
    reader = _fake_reader(tree)

    snapshot = read_editor_snapshot(
        reader,
        sections=["api", "element_definitions", "_index", "pages"],
        page_ids=["p1"],
        reusable_ids=["r1", "r2"],
    )

    assert snapshot["refetched_reusables"] == ["r1"]
    assert set(snapshot["pages"]) == {"p1", "p2"}
    assert ["pages"] not in reader.seen
    assert snapshot["errors"] == {}


def test_read_editor_snapshot_records_errors_and_stops_on_setup_failure() -> None:
    reader = _fake_reader({"api": {}}, failing=["styles"])
    snapshot = read_editor_snapshot(reader, sections=["api", "styles"])
    assert snapshot["errors"] == {"styles": "RuntimeError: boom"}

    def logged_out(_: Sequence[str]) -> Any:
        raise EditorSetupFailed("not_logged_in", "log in")

    with pytest.raises(EditorSetupFailed):
        read_editor_snapshot(logged_out, sections=["api"])


def test_section_scripts_use_the_decoded_public_accessors() -> None:
    script = build_section_script(["pages", "bTGbC"])
    assert 'node.child("pages")' in script and 'node.child("bTGbC")' in script
    assert "node.raw()" in script and "_raw" not in script
    assert "appname: root.appname()" in script

    gate = build_section_ready_script(["element_definitions"], "my-app")
    assert 'root.appname() !== "my-app"' in gate
    assert "not_ready_key" in gate
    assert "ensure_loading" in gate
    assert "child_names" not in gate


def test_tool_is_registered_read_only_on_bubble_and_routed() -> None:
    from bubble_mcp.server.agent_catalog import tool_annotations
    from bubble_mcp.server.stdio import handle_request
    from bubble_mcp.server.tools import call_tool

    response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    schema = tools["bubble_export_rebuild"]["inputSchema"]
    assert schema["required"] == ["profile"]
    assert schema["properties"]["execute"]["default"] is False
    assert schema["properties"]["app_version"]["default"] == "test"
    assert schema["x-bubble-docs"]["family"] == "export_import"
    annotations = tool_annotations("bubble_export_rebuild")
    assert annotations["destructiveHint"] is False
    assert annotations["openWorldHint"] is True

    guide = call_tool(
        "bubble_agent_guide",
        {"task": "importar o app em outro app, os reutilizáveis vieram vazios"},
    )
    assert guide["recommended_routes"][0]["intent"] == "rebuild_importable_export"
    search = call_tool("bubble_tool_search", {"query": "reconstruir o .bubble importável"})
    assert search["matches"][0]["name"] == "bubble_export_rebuild"


def test_dispatch_defaults_to_main_not_the_profile_version(monkeypatch: pytest.MonkeyPatch) -> None:
    from bubble_mcp.server import tools

    tools.call_tool(
        "bubble_profile_add",
        {"profile": "src", "app_id": "src-app", "app_version": "branch-1"},
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(tools, "rebuild_export", lambda **kwargs: captured.update(kwargs) or {"ok": True})

    tools.call_tool("bubble_export_rebuild", {"profile": "src"})

    assert captured["app_id"] == "src-app"
    assert captured["app_version"] == "test"
    assert captured["execute"] is False
    assert captured["work_dir"].name == "rebuild"
    assert captured["protected_paths"][0].name == "src-app.bubble"
    tools.call_tool("bubble_export_rebuild", {"profile": "src", "app_version": "branch-2"})
    assert captured["app_version"] == "branch-2"


def test_download_hydrated_export_targets_its_own_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bubble_mcp.context import detector

    seen: dict[str, Any] = {}
    monkeypatch.setattr(detector, "load_session", lambda profile: object())

    def fake_download(**kwargs: Any) -> Path:
        seen["download"] = kwargs
        return Path(kwargs["target_path"])

    monkeypatch.setattr(detector, "_try_download_bubble_export", fake_download)
    monkeypatch.setattr(
        detector, "_hydrate_sparse_export", lambda path, **kwargs: seen.setdefault("hydrated", path)
    )
    target = tmp_path / "work.bubble"

    result = detector.download_hydrated_export(profile="p", app_id="a", app_version="test", target=target)

    assert result["ok"] is True
    assert seen["download"]["target_path"] == target
    assert seen["hydrated"] == target


def test_a_reusable_nameless_in_the_editor_too_is_reported_not_failed() -> None:
    exported = _export()
    snapshot = _snapshot()
    exported["element_definitions"]["rN"] = {"%x": "ReusableElement", "id": "other", "%p": {}}
    snapshot["sections"]["element_definitions"]["rN"] = {"type": "ReusableElement", "id": "other", "properties": {}, "name": None}

    _, report = build_rebuilt_export(exported, snapshot)

    assert report["validation"]["ok"] is True
    assert report["validation"]["nameless_in_editor"] == ["rN"]
    assert report["validation"]["missing_name"] == []

    # Nameless with no editor entry to vouch for it: nothing confirms it, so it still fails.
    del snapshot["sections"]["element_definitions"]["rN"]
    _, failing = build_rebuilt_export(exported, snapshot)
    assert failing["validation"]["missing_name"] == ["rN"]
