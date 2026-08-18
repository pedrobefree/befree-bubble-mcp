import json

import pytest

from bubble_mcp.context.hydration import (
    hydrate_bubble_export_file,
    hydrate_reusable_definitions_payload,
    index_only_reusable_ids,
    orphan_reusable_ids,
    reusable_root_ids,
)
from bubble_mcp.context.path_api import _encode_path_segment


def test_encode5_matches_editor_base32() -> None:
    # Captured from a live editor load_single_path URL for est_pp_del_produto:
    # .../{hash}/4njp8/c9b58kv364 where the raw path was ["%ed", "bVTOc1"].
    assert _encode_path_segment("%ed") == "4njp8"
    assert _encode_path_segment("bVTOc1") == "c9b58kv364"
    assert _encode_path_segment("%el") == "4njpr"
    assert _encode_path_segment("%wf") == "4nvpc"


def _sparse_payload() -> dict:
    return {
        "_id": "app",
        "element_definitions": {},
        "_index": {
            "id_to_path": {
                "rootReal": "%ed.reReal",
                "childReal": "%ed.reReal.%el.child",
                # orphan: appears only in a deep path, no %ed.reOrphan root entry
                "orphanAction": "%ed.reOrphan.%wf.wfX.actions.0",
            }
        },
    }


def test_root_ids_exclude_orphans() -> None:
    payload = _sparse_payload()
    assert reusable_root_ids(payload) == {"reReal"}
    assert orphan_reusable_ids(payload) == ["reOrphan"]
    assert index_only_reusable_ids(payload) == ["reReal"]


class _FakeApi:
    def __init__(self, definitions: dict) -> None:
        self.definitions = definitions
        self.calls: list = []

    def resolve_multiple(self, path_arrays):
        from bubble_mcp.context.path_api import PathResult

        results = []
        for path in path_arrays:
            self.calls.append(list(path))
            if len(path) == 2 and path[0] == "%ed" and path[1] in self.definitions:
                results.append(PathResult(type="data", data=self.definitions[path[1]]))
            else:
                results.append(PathResult(type="data", data=None))
        return 0, results


def test_hydrate_payload_fills_only_real_reusables() -> None:
    payload = _sparse_payload()
    api = _FakeApi(
        {
            "reReal": {
                "%x": "CustomDefinition",
                "id": "rootReal",
                "%nm": "Real Card",
                "%el": {"child": {"%x": "Text"}},
                "%wf": {},
            }
        }
    )

    report = hydrate_reusable_definitions_payload(payload, api)

    assert report["requested"] == 1
    assert report["hydrated"] == 1
    assert report["failed"] == {}
    assert payload["element_definitions"]["reReal"]["%nm"] == "Real Card"
    # orphan reOrphan must never be requested
    assert ["%ed", "reOrphan"] not in api.calls


def test_hydrate_reports_failed_ids_without_writing_them() -> None:
    payload = {
        "_id": "app",
        "element_definitions": {},
        "_index": {"id_to_path": {"rootGhost": "%ed.reGhost"}},
    }
    api = _FakeApi({})  # server returns null for everything

    report = hydrate_reusable_definitions_payload(payload, api)

    assert report["requested"] == 1
    assert report["hydrated"] == 0
    assert "reGhost" in report["failed"]
    assert "reGhost" not in payload["element_definitions"]


def test_hydrate_file_updates_meta_sidecar(tmp_path) -> None:
    path = tmp_path / "app.bubble"
    path.write_text(json.dumps(_sparse_payload()), encoding="utf-8")
    path.with_name("app.bubble.meta.json").write_text(
        json.dumps({"app_version": "23347", "url": "https://bubble.io/x"}), encoding="utf-8"
    )

    class _SessionlessApiFactory(_FakeApi):
        pass

    import bubble_mcp.context.hydration as hydration_module

    definitions = {
        "reReal": {"%x": "CustomDefinition", "id": "rootReal", "%nm": "Real", "%el": {}, "%wf": {}}
    }

    def fake_client(*, app_id, app_version, session):  # type: ignore[no-untyped-def]
        return _FakeApi(definitions)

    original = hydration_module.BubblePathApiClient
    hydration_module.BubblePathApiClient = fake_client  # type: ignore[assignment]
    try:
        report = hydrate_bubble_export_file(
            path, session=object(), app_id="app", app_version="23347"
        )
    finally:
        hydration_module.BubblePathApiClient = original

    assert report["hydrated"] == 1
    assert report["orphan_index_refs"] == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["element_definitions"]["reReal"]["%nm"] == "Real"
    meta = json.loads(path.with_name("app.bubble.meta.json").read_text(encoding="utf-8"))
    assert meta["hydration"]["hydrated"] == 1
    assert meta["hydration"]["source"] == "editor_path_api"


def test_hydrate_file_rejects_non_object(tmp_path) -> None:
    path = tmp_path / "bad.bubble"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError):
        hydrate_bubble_export_file(path, session=object(), app_id="app", app_version="test")
