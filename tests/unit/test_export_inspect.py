import json

import pytest

from bubble_mcp.context.export_inspect import inspect_bubble_export


def _write(tmp_path, payload, name="app.bubble"):  # type: ignore[no-untyped-def]
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_inspect_reports_sparse_export_with_named_index_only_reusables(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        {
            "_id": "bovichain-g3",
            "pages": {"pgIndex": {"%p": {"%nm": "index"}}},
            "_index": {
                "id_to_path": {
                    "rootCard": "%ed.reCard",
                    "childCard": "%ed.reCard.%el.childCard",
                    "rootMenu": "%ed.reMenu",
                    "pageRoot": "%p3.pgIndex",
                },
                "custom_name_to_id": {
                    "Card Header": {"custom_id": "reCard", "display": "Card Header"},
                },
            },
        },
    )

    report = inspect_bubble_export(path)

    assert report["app_id"] == "bovichain-g3"
    assert report["reusables"]["material_count"] == 0
    assert report["reusables"]["index_reusable_count"] == 2
    assert report["reusables"]["index_only_count"] == 2
    assert report["reusables"]["sparse_export"] is True
    assert {"id": "reCard", "name": "Card Header"} in report["reusables"]["index_only_sample"]
    assert report["verdict"].startswith("sparse:")


def test_inspect_separates_orphan_index_refs_from_real_reusables(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        {
            "_id": "app",
            "element_definitions": {},
            "_index": {
                "id_to_path": {
                    "rootReal": "%ed.reReal",
                    "childReal": "%ed.reReal.%el.child",
                    "ghostAction": "%ed.reGhost.%wf.wfX.actions.0",
                }
            },
        },
    )

    report = inspect_bubble_export(path)

    assert report["reusables"]["index_reusable_count"] == 1
    assert report["reusables"]["index_only_count"] == 1
    assert report["reusables"]["orphan_index_ref_count"] == 1
    assert report["reusables"]["hint"] and "hydrate-reusables" in report["reusables"]["hint"]


def test_inspect_reports_material_export_and_provenance_meta(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        {
            "_id": "cliente2-app",
            "element_definitions": {
                "reCard": {
                    "%x": "CustomDefinition",
                    "%p": {"%nm": "Card"},
                    "%wf": {"wfLoad": {}},
                }
            },
            "_index": {"id_to_path": {"rootCard": "%ed.reCard"}},
        },
    )
    meta_path = tmp_path / "app.bubble.meta.json"
    meta_path.write_text(
        json.dumps({"app_version": "23347", "url": "https://bubble.io/appeditor/export/23347/x.bubble"}),
        encoding="utf-8",
    )

    report = inspect_bubble_export(path)

    assert report["reusables"]["material_by_source"] == {"element_definitions": 1}
    assert report["reusables"]["index_only_count"] == 0
    assert report["reusables"]["sparse_export"] is False
    assert report["provenance"]["app_version"] == "23347"
    assert report["verdict"].startswith("ok:")


def test_inspect_flags_reusable_payloads_under_unexpected_roots(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        {
            "_id": "odd-app",
            "reusable_blobs": {
                "reHidden": {"%x": "CustomDefinition", "%p": {"%nm": "Hidden"}},
                "notReusable": {"foo": "bar"},
            },
            "_index": {"id_to_path": {"rootHidden": "%ed.reHidden"}},
        },
    )

    report = inspect_bubble_export(path)

    assert report["reusable_payloads_under_unexpected_roots"] == {"reusable_blobs": 1}
    assert report["reusables"]["index_only_count"] == 1


def test_inspect_unwraps_console_style_app_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        {
            "app": {
                "_id": "wrapped-app",
                "element_definitions": {
                    "reCard": {"%x": "CustomDefinition", "%p": {"%nm": "Card"}}
                },
            },
            "deployment": {},
        },
    )

    report = inspect_bubble_export(path)

    assert report["wrapped_app_payload"] is True
    assert report["app_id"] == "wrapped-app"
    assert report["reusables"]["material_count"] == 1


def test_inspect_surfaces_version_hints(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = _write(
        tmp_path,
        {
            "_id": "hint-app",
            "app_version": "23347",
            "settings": {"client_safe": {"minimum_bubble_version": "3"}},
        },
    )

    report = inspect_bubble_export(path)

    assert report["version_hints"]["app_version"] == "23347"
    assert report["version_hints"]["settings.client_safe.minimum_bubble_version"] == "3"


def test_inspect_rejects_non_object_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "bad.bubble"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(TypeError, match="JSON object"):
        inspect_bubble_export(path)
