"""What a deploy would push: the diff between the deployed `live` version and `test`.

No network. Both versions are served by an injected reader keyed by dotted pointer.
"""

from __future__ import annotations

from typing import Any

from bubble_mcp.execution.deploy_preview import (
    changed_pointers,
    diff_versions,
    preview_deploy,
)


def _overlay(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "profile": "dev", "app_id": "mcp-test-app", "entries": list(entries)}


def _entry(*paths: list[str], captured_at: str = "2026-08-27T12:00:00+00:00") -> dict[str, Any]:
    return {
        "captured_at": captured_at,
        "source": "add_action",
        "changes": [{"path_array": path, "body": {"%x": "ShowElement"}} for path in paths],
    }


def test_changed_pointers_collects_every_path_the_overlay_wrote() -> None:
    overlay = _overlay(_entry(["api", "wf-1"]), _entry(["%p3", "index", "%el", "btn"]))

    assert changed_pointers(overlay) == [("api", "wf-1"), ("%p3", "index", "%el", "btn")]


def test_changed_pointers_reports_each_path_once() -> None:
    overlay = _overlay(_entry(["api", "wf-1"]), _entry(["api", "wf-1"]))

    assert changed_pointers(overlay) == [("api", "wf-1")]


def test_changed_pointers_skips_the_editors_own_bookkeeping() -> None:
    """`_index` is the editor's lookup tree, not something an author changed."""

    overlay = _overlay(_entry(["_index", "id_to_path", "bTGOd"], ["api", "wf-1"]))

    assert changed_pointers(overlay) == [("api", "wf-1")]


def test_changed_pointers_can_start_from_an_instant() -> None:
    overlay = _overlay(
        _entry(["api", "old"], captured_at="2026-08-26T10:00:00+00:00"),
        _entry(["api", "new"], captured_at="2026-08-27T10:00:00+00:00"),
    )

    pointers = changed_pointers(overlay, since="2026-08-27T00:00:00+00:00")

    assert pointers == [("api", "new")]


def test_diff_reports_a_node_that_changed_and_where() -> None:
    before = {("api", "wf-1"): {"%x": "APIEvent", "%p": {"wf_name": "old"}}}
    after = {("api", "wf-1"): {"%x": "APIEvent", "%p": {"wf_name": "new"}}}

    [entry] = diff_versions(before, after)

    assert entry["status"] == "changed"
    assert entry["pointer"] == ["api", "wf-1"]
    assert entry["divergence"] == "%p.wf_name"


def test_diff_reports_a_node_the_deploy_would_add() -> None:
    [entry] = diff_versions({}, {("api", "wf-1"): {"%x": "APIEvent"}})

    assert entry["status"] == "added"
    assert entry["after"] == {"%x": "APIEvent"}


def test_diff_reports_a_node_the_deploy_would_remove() -> None:
    [entry] = diff_versions({("api", "wf-1"): {"%x": "APIEvent"}}, {})

    assert entry["status"] == "removed"
    assert entry["before"] == {"%x": "APIEvent"}


def test_diff_stays_silent_about_a_node_the_deploy_would_not_touch() -> None:
    same = {("api", "wf-1"): {"%x": "APIEvent"}}

    assert diff_versions(same, dict(same)) == []


class _Versions:
    """An injected reader answering per app version, keyed by dotted pointer."""

    def __init__(self, live: dict[str, Any], test: dict[str, Any]) -> None:
        self.by_version = {"live": live, "test": test}
        self.reads: list[tuple[str, int]] = []

    def __call__(self, profile, pointers, *, app_id=None, app_version="test"):  # type: ignore[no-untyped-def]
        self.reads.append((app_version, len(list(pointers))))
        held = self.by_version.get(app_version, {})
        return {
            tuple(pointer): held[".".join(pointer)]
            for pointer in pointers
            if ".".join(pointer) in held
        }


def test_preview_reads_the_same_pointers_in_both_versions() -> None:
    reader = _Versions(
        live={"api.wf-1": {"%x": "APIEvent", "%p": {"wf_name": "old"}}},
        test={"api.wf-1": {"%x": "APIEvent", "%p": {"wf_name": "new"}}},
    )

    result = preview_deploy(
        profile="dev",
        app_id="mcp-test-app",
        overlay=_overlay(_entry(["api", "wf-1"])),
        reader=reader,
    )

    assert sorted(version for version, _ in reader.reads) == ["live", "test"]
    assert result["ok"] is True
    assert result["source"] == "overlay"
    assert result["changes"][0]["divergence"] == "%p.wf_name"


def test_preview_reports_nothing_to_deploy_without_reading_anything() -> None:
    reader = _Versions(live={}, test={})

    result = preview_deploy(
        profile="dev", app_id="mcp-test-app", overlay=_overlay(), reader=reader
    )

    assert result["ok"] is True
    assert result["changes"] == []
    assert reader.reads == []


def test_preview_scans_the_app_roots_when_asked_for_a_full_scan() -> None:
    """The overlay only knows what the MCP wrote; a full scan also sees hand edits."""

    reader = _Versions(live={}, test={})

    preview_deploy(
        profile="dev",
        app_id="mcp-test-app",
        overlay=_overlay(),
        source="full_scan",
        reader=reader,
    )

    scanned = {version for version, _ in reader.reads}
    assert scanned == {"live", "test"}
    assert all(count > 1 for _, count in reader.reads)


def test_preview_refuses_a_source_it_does_not_know() -> None:
    result = preview_deploy(
        profile="dev",
        app_id="mcp-test-app",
        overlay=_overlay(),
        source="guess",
        reader=_Versions(live={}, test={}),
    )

    assert result["ok"] is False
    assert result["error"] == "unknown_source"


class _FakePathClient:
    """Stands in for BubblePathApiClient, answering per dotted path."""

    def __init__(self, nodes: dict[str, Any]) -> None:
        self.nodes = nodes
        self.asked: list[list[list[str]]] = []

    def resolve_multiple(self, path_arrays):  # type: ignore[no-untyped-def]
        from bubble_mcp.context.path_api import PathResult

        self.asked.append([list(p) for p in path_arrays])
        results = []
        for path in path_arrays:
            key = ".".join(str(part) for part in path)
            if key in self.nodes:
                results.append(PathResult(type="data", data=self.nodes[key]))
            else:
                # A path the version does not hold answers data=None, not an error - measured
                # against the live editor 2026-08-27.
                results.append(PathResult(type="data", data=None))
        return 1, results


def test_http_read_returns_nodes_keyed_by_pointer() -> None:
    from bubble_mcp.execution.deploy_preview import read_nodes_over_http

    client = _FakePathClient({"api.wf-1": {"%x": "APIEvent"}})

    nodes = read_nodes_over_http(
        "dev", [("api", "wf-1")], app_id="mcp-test-app", app_version="test", client=client
    )

    assert nodes == {("api", "wf-1"): {"%x": "APIEvent"}}


def test_http_read_omits_a_path_the_version_does_not_have() -> None:
    """A path missing from `live` is an addition, not an empty node - it must not be keyed."""

    from bubble_mcp.execution.deploy_preview import read_nodes_over_http

    client = _FakePathClient({})

    nodes = read_nodes_over_http(
        "dev", [("api", "wf-1")], app_id="mcp-test-app", app_version="live", client=client
    )

    assert nodes == {}


class _BrokenPathClient:
    """A client whose reads fail the way a network or auth problem fails."""

    def resolve_multiple(self, path_arrays):  # type: ignore[no-untyped-def]
        from bubble_mcp.context.path_api import PathResult

        return 0, [PathResult(type="error", message="401 not logged in") for _ in path_arrays]


def test_http_read_raises_when_the_read_itself_failed() -> None:
    """A failed read is not an absent node: treating it as absence reports the app as emptied."""

    from bubble_mcp.execution.deploy_preview import PathReadError, read_nodes_over_http

    try:
        read_nodes_over_http(
            "dev",
            [("api", "wf-1")],
            app_id="mcp-test-app",
            app_version="live",
            client=_BrokenPathClient(),
        )
    except PathReadError as error:
        assert "401" in str(error)
    else:
        raise AssertionError("a read failure must never be reported as a missing node")


def test_http_read_treats_a_null_data_result_as_absence() -> None:
    """Measured against the live editor: a path that does not exist answers data=None."""

    from bubble_mcp.context.path_api import PathResult
    from bubble_mcp.execution.deploy_preview import read_nodes_over_http

    class _Absent:
        def resolve_multiple(self, path_arrays):  # type: ignore[no-untyped-def]
            return 1, [PathResult(type="data", data=None) for _ in path_arrays]

    nodes = read_nodes_over_http(
        "dev", [("api", "wf-1")], app_id="mcp-test-app", app_version="live", client=_Absent()
    )

    assert nodes == {}


def test_http_read_raises_when_a_hash_never_resolved() -> None:
    """An unresolved chunk means the node was not read - not that the node is gone."""

    from bubble_mcp.context.path_api import PathResult
    from bubble_mcp.execution.deploy_preview import PathReadError, read_nodes_over_http

    class _Unresolved:
        def resolve_multiple(self, path_arrays):  # type: ignore[no-untyped-def]
            return 1, [PathResult(type="hash", hash="deadbeef") for _ in path_arrays]

    try:
        read_nodes_over_http(
            "dev", [("api", "wf-1")], app_id="mcp-test-app", app_version="live",
            client=_Unresolved(),
        )
    except PathReadError as error:
        assert "hash" in str(error)
    else:
        raise AssertionError("an unresolved chunk must not be reported as a missing node")


def test_preview_reports_a_failed_read_instead_of_an_empty_diff() -> None:
    from bubble_mcp.execution.deploy_preview import PathReadError, preview_deploy

    def failing_reader(profile, pointers, *, app_id=None, app_version="test"):  # type: ignore[no-untyped-def]
        raise PathReadError("401 not logged in")

    result = preview_deploy(
        profile="dev",
        app_id="mcp-test-app",
        overlay=_overlay(_entry(["api", "wf-1"])),
        reader=failing_reader,
    )

    assert result["ok"] is False
    assert result["error"] == "read_failed"
    assert "401" in result["message"]


def test_diff_names_every_path_that_differs_under_one_pointer() -> None:
    """A root that changed in three places is three changes, not one."""

    before = {("%p3",): {"a": {"x": 1}, "b": 1}}
    after = {("%p3",): {"a": {"x": 2}, "b": 2}}

    [entry] = diff_versions(before, after)

    assert sorted(entry["divergences"]) == ["a.x", "b"]


def test_preview_says_when_it_compared_nothing_at_all() -> None:
    """changes=[] from an empty overlay means "nothing recorded", not "nothing to deploy"."""

    reader = _Versions(live={}, test={})

    result = preview_deploy(
        profile="dev", app_id="mcp-test-app", overlay=_overlay(), reader=reader
    )

    assert result["complete"] is False
    assert "full_scan" in result["message"]


def test_preview_from_a_full_scan_reports_itself_as_complete() -> None:
    reader = _Versions(live={"%p3": {"a": 1}}, test={"%p3": {"a": 1}})

    result = preview_deploy(
        profile="dev",
        app_id="mcp-test-app",
        overlay=_overlay(),
        source="full_scan",
        reader=reader,
    )

    assert result["complete"] is True


def test_preview_from_a_non_empty_overlay_is_still_not_complete() -> None:
    """The overlay cannot see an edit made by hand in the editor, however many it holds."""

    reader = _Versions(live={"api.wf-1": {"a": 1}}, test={"api.wf-1": {"a": 2}})

    result = preview_deploy(
        profile="dev",
        app_id="mcp-test-app",
        overlay=_overlay(_entry(["api", "wf-1"])),
        reader=reader,
    )

    assert result["complete"] is False


def test_the_http_reader_refuses_to_be_used_as_a_source_for_a_write() -> None:
    """Measured 2026-08-27: the path API drops null-valued keys on read.

    A node was written with `%n`, `optional` and `in_url` all null
    (docs/capture-duplicate-workflow-custom-event.json) and read back through the path API
    without them. Anything that reads a node here and writes it back would silently drop those
    keys, and /appeditor/write would answer 200.
    """

    from bubble_mcp.execution.deploy_preview import read_nodes_over_http

    assert read_nodes_over_http.for_rewrite is False
